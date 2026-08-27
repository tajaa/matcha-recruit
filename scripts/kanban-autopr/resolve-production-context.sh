#!/usr/bin/env bash
# Resolve the code and schema that are actually live in production. This is a
# trusted harness step: the result may be attached to model context, but the
# SSH key and unrestricted production access never are.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

: "${SSH_KEY:?SSH_KEY must point to the production EC2 private key}"

PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"
PROD_SITE_URL="${PROD_SITE_URL:-https://hey-matcha.com}"
PROD_DB_HOST="${PROD_DB_HOST:-13.56.253.173}"

# The active blue/green port is authoritative. Config.Image says :latest, so
# resolve the running image digest through ECR and recover its immutable SHA
# tag instead of trusting the host checkout (which can be ahead of the image).
containers="$({
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "$PROD_USER@$PROD_HOST" bash -s <<'REMOTE'
set -euo pipefail

component_json() {
    component="$1"
    conf="/etc/nginx/upstream/matcha-${component}-active.conf"
    port="$(sed -n 's/.*:\([0-9][0-9]*\).*/\1/p' "$conf" | head -1)"
    container="matcha-${component}-${port}"
    if ! docker inspect "$container" >/dev/null 2>&1; then
        container="matcha-${component}"
    fi

    image_id="$(docker inspect -f '{{.Image}}' "$container")"
    image_ref="$(docker inspect -f '{{.Config.Image}}' "$container")"
    started_at="$(docker inspect -f '{{.State.StartedAt}}' "$container")"
    repo_digest="$(docker image inspect -f '{{index .RepoDigests 0}}' "$image_id")"
    digest="${repo_digest##*@}"
    repository="$(printf '%s' "$image_ref" | sed -E 's#^.*/##;s#:[^:]+$##')"
    tags="$(aws ecr describe-images --region us-west-1 \
        --repository-name "$repository" --image-ids "imageDigest=$digest" \
        --query 'imageDetails[0].imageTags' --output json)"
    git_sha="$(printf '%s' "$tags" | jq -r '.[] | select(test("^[0-9a-f]{7,40}$"))' | head -1)"
    [ -n "$git_sha" ] || {
        echo "no immutable git SHA tag for $component digest $digest" >&2
        exit 1
    }

    jq -n --arg container "$container" --arg image_ref "$image_ref" \
        --arg image_id "$image_id" --arg digest "$digest" \
        --arg git_sha "$git_sha" --arg started_at "$started_at" \
        '{container:$container,image_ref:$image_ref,image_id:$image_id,digest:$digest,git_sha:$git_sha,started_at:$started_at}'
}

backend="$(component_json backend)"
frontend="$(component_json frontend)"
jq -n --argjson backend "$backend" --argjson frontend "$frontend" \
    '{backend:$backend,frontend:$frontend}'
REMOTE
} 2>&1)" || die "could not resolve active production containers: $containers"

printf '%s' "$containers" | jq -e '.backend.git_sha and .frontend.git_sha' >/dev/null \
    || die "production container resolver returned invalid JSON"

# Prefer a future stable manifest when present. Existing builds expose the
# number in the marketing footer's compiled bundle, so retain a bounded
# fallback that fails closed if the marker cannot be found.
build_number=""
manifest_sha=""
manifest="$(curl -fsS --max-time 15 -H 'Cache-Control: no-cache' \
    "$PROD_SITE_URL/version.json?check=$(date +%s)" 2>/dev/null || true)"
if printf '%s' "$manifest" | jq -e . >/dev/null 2>&1; then
    build_number="$(printf '%s' "$manifest" | jq -r '.build_number // .build // empty')"
    manifest_sha="$(printf '%s' "$manifest" | jq -r '.git_sha // empty')"
fi
if [ -z "$build_number" ]; then
    index_html="$(curl -fsS --max-time 15 "$PROD_SITE_URL/")" \
        || die "could not fetch the production frontend"
    asset_path="$(printf '%s' "$index_html" \
        | sed -nE 's#.*src="(/assets/index-[^"]+\.js)".*#\1#p' | head -1)"
    [ -n "$asset_path" ] || die "could not resolve the production frontend bundle"
    build_number="$(curl -fsS --max-time 30 "$PROD_SITE_URL$asset_path" 2>/dev/null \
        | grep -oE -m1 'children:\["build ","[0-9]+"\]' \
        | grep -oE '[0-9]+' | head -1 || true)"
fi
[[ "$build_number" =~ ^[0-9]+$ ]] \
    || die "could not resolve the production frontend build number"
if [ -n "$manifest_sha" ]; then
    active_frontend_sha="$(printf '%s' "$containers" | jq -r '.frontend.git_sha')"
    [ "$manifest_sha" = "$active_frontend_sha" ] \
        || die "frontend manifest SHA $manifest_sha does not match active image SHA $active_frontend_sha"
fi

# A prod SHA outside this checkout's main history means the bot cannot safely
# reason about what is deployed versus what is pending. Refuse to draft a PR.
main_ref="main"
git -C "$REPO_ROOT" rev-parse --verify "$main_ref^{commit}" >/dev/null 2>&1 \
    || main_ref="HEAD"
for component in backend frontend; do
    sha="$(printf '%s' "$containers" | jq -r ".${component}.git_sha")"
    git -C "$REPO_ROOT" rev-parse --verify "$sha^{commit}" >/dev/null 2>&1 \
        || die "production $component SHA $sha is absent from this checkout"
    git -C "$REPO_ROOT" merge-base --is-ancestor "$sha" "$main_ref" \
        || die "production $component SHA $sha is not an ancestor of $main_ref"
done

# Revision state is cheap and read-only. It distinguishes an application bug
# from an unapplied migration without dumping the database or exposing rows.
prod_revisions="$({
    SSH_KEY="$SSH_KEY" PROD_DB_HOST="$PROD_DB_HOST" \
        "$REPO_ROOT/scripts/ops-health/schema-snapshot.sh" prod-revisions
} 2>&1)" || die "could not read production Alembic revisions: $prod_revisions"
printf '%s' "$prod_revisions" | jq -e '.revisions | type == "array"' >/dev/null \
    || die "production Alembic revision snapshot was invalid"

repo_heads="$({
    cd "$REPO_ROOT/server"
    ./venv/bin/alembic heads 2>/dev/null | awk '{print $1}' | jq -Rsc 'split("\n") | map(select(length > 0)) | sort'
} 2>&1)" || die "could not resolve repository Alembic heads: $repo_heads"

repo_revisions="$({
    "$REPO_ROOT/server/venv/bin/python" - "$REPO_ROOT/server" <<'PY'
import json
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

root = Path(sys.argv[1])
config = Config(str(root / "alembic.ini"))
config.set_main_option("script_location", str(root / "alembic"))
script = ScriptDirectory.from_config(config)
print(json.dumps(sorted(rev.revision for rev in script.walk_revisions())))
PY
} 2>&1)" || die "could not resolve the repository migration graph: $repo_revisions"

current_revisions="$(printf '%s' "$prod_revisions" | jq -r '.revisions[]')"
pending="$(
    # Intentional word splitting: each current revision is one argv entry.
    # shellcheck disable=SC2086
    "$REPO_ROOT/server/venv/bin/python" "$REPO_ROOT/scripts/alembic_pending.py" $current_revisions \
        | jq -Rsc 'split("\n") | map(select(length > 0))'
)" || die "could not compare production migrations with the repository"

schema_status="current"
[ "$(printf '%s' "$pending" | jq 'length')" -eq 0 ] || schema_status="behind"
prod_only="$(jq -n --argjson prod "$(printf '%s' "$prod_revisions" | jq '.revisions | sort')" \
    --argjson repo "$repo_revisions" '$prod - $repo')"
[ "$(printf '%s' "$prod_only" | jq 'length')" -eq 0 ] || schema_status="diverged"

backend_sha="$(printf '%s' "$containers" | jq -r '.backend.git_sha')"
frontend_sha="$(printf '%s' "$containers" | jq -r '.frontend.git_sha')"
release_sha=""
[ "$backend_sha" != "$frontend_sha" ] || release_sha="$backend_sha"

jq -n \
    --arg checked_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg host "$PROD_HOST" \
    --arg site_url "$PROD_SITE_URL" \
    --arg build_number "$build_number" \
    --arg release_sha "$release_sha" \
    --arg schema_status "$schema_status" \
    --argjson containers "$containers" \
    --argjson prod_revisions "$prod_revisions" \
    --argjson repo_heads "$repo_heads" \
    --argjson pending "$pending" \
    --argjson prod_only "$prod_only" \
    '{schema_version:1,checked_at:$checked_at,source:"active EC2 containers + ECR + production DB",host:$host,site_url:$site_url,build_number:$build_number,release_sha:(if $release_sha == "" then null else $release_sha end),containers:$containers,database:{status:$schema_status,production_revisions:$prod_revisions.revisions,repository_heads:$repo_heads,pending_migrations:$pending,production_only_revisions:$prod_only}}'
