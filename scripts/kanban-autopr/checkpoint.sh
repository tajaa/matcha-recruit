#!/usr/bin/env bash
# Save interrupted model work under protected .git metadata for a later run.
#
# Usage:
#   checkpoint.sh save CARD REPORT DECISION STARTED_AT_EPOCH TIMEOUT_MINUTES
#   checkpoint.sh snapshot CARD
#   checkpoint.sh snapshot-arm
#   checkpoint.sh snapshot-halt
#   checkpoint.sh latest CARD
#   checkpoint.sh consume CARD
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AUTOPR_WORKSPACE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

GIT_DIR="$(git -C "$REPO_ROOT" rev-parse --absolute-git-dir)"
CHECKPOINT_ROOT="${AUTOPR_CHECKPOINT_ROOT:-$GIT_DIR/matcha-kanban-autopr-checkpoints}"
RUNTIME_ROOT="${AUTOPR_SANDBOX_RUNTIME_ROOT:-$GIT_DIR/matcha-kanban-autopr-sandbox}"
SANDBOX_WORKSPACE="$RUNTIME_ROOT/workspace"
LIVE_LOG="${AUTOPR_LIVE_LOG:-$HOME/Library/Logs/matcha-kanban-autopr-live.log}"
MAX_PATCH_BYTES="${AUTOPR_SANDBOX_MAX_PATCH_BYTES:-5242880}"
MAX_REPORT_BYTES="${AUTOPR_SANDBOX_MAX_REPORT_BYTES:-1048576}"
MAX_DECISION_BYTES="${AUTOPR_SANDBOX_MAX_DECISION_BYTES:-262144}"
# The transcript is re-attached as a model input on the approved continuation.
# A multi-megabyte tail of ANSI-laden scrollback would consume most of that
# run's context window; a bounded, escape-stripped tail carries the signal.
MAX_TRANSCRIPT_BYTES="${AUTOPR_CHECKPOINT_MAX_TRANSCRIPT_BYTES:-131072}"
# Nothing else ever reclaims a checkpoint (`consume` only clears the active
# pointer, by design), and the runner's workspace is checked out with
# `clean: false`, so bound the footprint here.
CHECKPOINT_MAX_PER_TASK="${AUTOPR_CHECKPOINT_MAX_PER_TASK:-3}"
CHECKPOINT_RETENTION_DAYS="${AUTOPR_CHECKPOINT_RETENTION_DAYS:-14}"
# A patch that still applies weeks later is not evidence that it is still the
# right patch for today's main. Resume only recent work.
CHECKPOINT_MAX_AGE_HOURS="${AUTOPR_CHECKPOINT_MAX_AGE_HOURS:-24}"
# investigate.sh records its own exit status here. Absence (or a signal
# status) is the only trustworthy evidence that the step was killed at its
# time limit rather than failing on its own.
INVESTIGATION_EXIT_FILE="${AUTOPR_INVESTIGATION_EXIT_FILE:-${RUNNER_TEMP:+$RUNNER_TEMP/investigation-exit-code}}"
# In-flight snapshots run against a LIVE container, which owns
# $SANDBOX_WORKSPACE/.git/index. Keep a private index outside the workspace so
# a snapshot never contends for index.lock with the model's own git commands,
# and persist it across snapshots so its stat cache keeps each pass cheap.
SNAPSHOT_INDEX="${AUTOPR_SNAPSHOT_INDEX:-$RUNTIME_ROOT/snapshot.index}"
SNAPSHOT_INDEX_BASE="$SNAPSHOT_INDEX.base"
# A snapshot runs concurrently with the foreground investigation, so `save` and
# `consume` have to be able to STOP one and wait for it. A pass that lands after
# `consume` would re-point a run whose PR is already published back at its own
# leftovers, and the next round would then replay published work.
SNAPSHOT_LOCK="${AUTOPR_SNAPSHOT_LOCK:-$RUNTIME_ROOT/snapshot.lock}"
SNAPSHOT_STOP_FILE="${AUTOPR_SNAPSHOT_STOP_FILE:-$RUNTIME_ROOT/snapshot.stop}"
SNAPSHOT_SKIP_FILE="$RUNTIME_ROOT/snapshot.unsettled"
# How long `halt` waits for a pass that is already running, and how long a pass
# waits for another one (it should simply skip; the next pass is 4 minutes out).
SNAPSHOT_HALT_WAIT_SECONDS="${AUTOPR_SNAPSHOT_HALT_WAIT_SECONDS:-120}"
SNAPSHOT_PASS_WAIT_SECONDS="${AUTOPR_SNAPSHOT_PASS_WAIT_SECONDS:-0}"
# A holder killed with SIGKILL never releases; reclaim rather than disabling
# snapshots for the rest of the run.
SNAPSHOT_LOCK_STALE_SECONDS="${AUTOPR_SNAPSHOT_LOCK_STALE_SECONDS:-600}"
# Diffing a tree the model is actively writing can capture a truncated file, and
# `git apply --check` accepts a valid patch of a broken file. Skip a pass whose
# newest changed file is younger than this — but never skip forever: a
# possibly-unsettled patch still beats losing the whole investigation.
SNAPSHOT_SETTLE_SECONDS="${AUTOPR_SNAPSHOT_SETTLE_SECONDS:-2}"
SNAPSHOT_MAX_UNSETTLED_SKIPS="${AUTOPR_SNAPSHOT_MAX_UNSETTLED_SKIPS:-2}"
# The workflow writes this immediately before investigate.sh starts. A sandbox
# clone older than it belongs to a PREVIOUS run: the task-id stamp alone cannot
# tell two rounds of the SAME card apart.
INVESTIGATION_STARTED_FILE="${AUTOPR_INVESTIGATION_STARTED_FILE:-${RUNNER_TEMP:+$RUNNER_TEMP/investigation-started-at}}"

card_identity() {
    local card_file="$1" task_id
    task_id="$(jq -r '.task_id // empty' "$card_file")"
    [[ "$task_id" =~ ^[0-9a-fA-F-]{36}$ ]] || die "invalid checkpoint task id"
    printf '%s' "$task_id" | tr '[:upper:]' '[:lower:]'
}

# Both entry points feed id8 to the model as the checkpoint's identity, so both
# have to validate it. A blank id8 resumes a checkpoint that names no branch.
card_id8() {
    local id8
    id8="$(jq -r '.id8 // empty' "$1")"
    [[ "$id8" =~ ^[0-9a-fA-F]{8}$ ]] || die "invalid checkpoint id8"
    printf '%s' "$id8"
}

task_root() {
    printf '%s/%s' "$CHECKPOINT_ROOT" "$(card_identity "$1")"
}

snapshot_warn() {
    printf 'kanban-autopr: snapshot: %s\n' "$1" >&2
}

file_mtime_epoch() {
    [ -e "$1" ] || return 0
    date -r "$1" +%s 2>/dev/null || true
}

# Epoch before which a sandbox clone cannot belong to this run. Empty when the
# marker is absent, which leaves the freshness guard inert.
investigation_floor_epoch() {
    local floor
    [ -n "$INVESTIGATION_STARTED_FILE" ] && [ -s "$INVESTIGATION_STARTED_FILE" ] || return 0
    floor="$(tr -dc '0-9' < "$INVESTIGATION_STARTED_FILE" | head -c 12)"
    [ -n "$floor" ] || return 0
    printf '%s' "$floor"
}

# mkdir is the only atomic create-or-fail primitive available on both the
# self-hosted macOS runner and Linux without flock.
snapshot_lock_acquire() {
    local wait_seconds="$1" waited=0 lock_epoch now
    mkdir -p "$RUNTIME_ROOT" 2>/dev/null || true
    while ! mkdir "$SNAPSHOT_LOCK" 2>/dev/null; do
        lock_epoch="$(file_mtime_epoch "$SNAPSHOT_LOCK")"
        now="$(date +%s)"
        if [ -n "$lock_epoch" ] \
            && [ $((now - lock_epoch)) -gt "$SNAPSHOT_LOCK_STALE_SECONDS" ]; then
            snapshot_warn "reclaiming a stale snapshot lock"
            rmdir "$SNAPSHOT_LOCK" 2>/dev/null || true
        fi
        [ "$waited" -lt "$wait_seconds" ] || return 1
        sleep 1
        waited=$((waited + 1))
    done
}

snapshot_lock_release() {
    rmdir "$SNAPSHOT_LOCK" 2>/dev/null || true
}

# Stop in-flight snapshots AND wait for one already running to finish, so a pass
# that started a second ago cannot write after this returns. Both `save` and
# `consume` call it before they touch the active pointer.
halt_snapshots() {
    mkdir -p "$RUNTIME_ROOT" 2>/dev/null || true
    : > "$SNAPSHOT_STOP_FILE" 2>/dev/null || true
    if snapshot_lock_acquire "$SNAPSHOT_HALT_WAIT_SECONDS"; then
        snapshot_lock_release
    else
        snapshot_warn "timed out waiting for an in-flight snapshot to finish"
    fi
}

arm_snapshots() {
    mkdir -p "$RUNTIME_ROOT" 2>/dev/null || true
    rm -f "$SNAPSHOT_STOP_FILE" "$SNAPSHOT_SKIP_FILE" 2>/dev/null || true
}

checkpoint_age_seconds() {
    local dir="$1" created epoch=0 now
    created="$(jq -r '.created_at // empty' "$dir/metadata.json" 2>/dev/null || true)"
    if [ -n "$created" ]; then
        epoch="$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$created" +%s 2>/dev/null \
            || date -u -d "$created" +%s 2>/dev/null || printf 0)"
    fi
    [ "$epoch" -gt 0 ] 2>/dev/null || epoch="$(date -r "$dir" +%s 2>/dev/null || printf 0)"
    now="$(date +%s)"
    printf '%s' "$(( now - epoch ))"
}

latest_checkpoint() {
    local card_file="$1" root active checkpoint
    root="$(task_root "$card_file")"
    active="$root/active"
    [ -f "$active" ] || return 0
    checkpoint="$(tr -d '\r\n' < "$active")"
    [[ "$checkpoint" =~ ^[A-Za-z0-9._-]+$ ]] || return 0
    [ -d "$root/$checkpoint" ] || return 0
    # An expired checkpoint stays on disk for forensics but is no longer
    # resumable: applying stale model work into a fresh branch would fold
    # unreviewed edits from another week into today's PR diff.
    [ "$(checkpoint_age_seconds "$root/$checkpoint")" \
        -le $((CHECKPOINT_MAX_AGE_HOURS * 3600)) ] || return 0
    printf '%s\n' "$root/$checkpoint"
}

prune_checkpoints() {
    local root="$1" kept=0 entry active=''
    # The empty-save guard lets `active` point at a directory that is no longer
    # the newest. Deleting it would destroy the only resumable work while the
    # pointer still names it, so it never counts against the cap and is never
    # swept by age.
    [ ! -f "$root/active" ] || active="$(tr -d '\r\n' < "$root/active")"
    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        entry="${entry%/}"
        [ "$entry" != "$active" ] || continue
        kept=$((kept + 1))
        [ "$kept" -gt "$CHECKPOINT_MAX_PER_TASK" ] || continue
        rm -rf -- "$root/$entry"
    done < <(cd "$root" && ls -1td -- */ 2>/dev/null || true)
    find "$CHECKPOINT_ROOT" -mindepth 2 -maxdepth 2 -type d \
        -mtime "+$CHECKPOINT_RETENTION_DAYS" -exec rm -rf -- {} + 2>/dev/null || true
    find "$CHECKPOINT_ROOT" -mindepth 2 -maxdepth 2 -type f -name 'consumed-*' \
        -mtime "+$CHECKPOINT_RETENTION_DAYS" -delete 2>/dev/null || true
}

# The card this sandbox clone was created for, or empty when it carries no
# stamp (a clone from before this guard, or one never reached by the bridge).
sandbox_workspace_task_id() {
    [ -f "$SANDBOX_WORKSPACE/.git/autopr-io/task-id" ] || return 0
    tr -d '\r\n' < "$SANDBOX_WORKSPACE/.git/autopr-io/task-id" \
        | tr '[:upper:]' '[:lower:]'
}

# When this clone was created. Unique per run, and the only signal that
# distinguishes two rounds of the same card.
sandbox_clone_epoch() {
    file_mtime_epoch "$SANDBOX_WORKSPACE/.git/autopr-io/model-base-sha"
}

# The clone's model base SHA, but ONLY when the clone belongs to $1 and that
# commit is really present. Empty otherwise, which is what makes a leftover
# workspace from another card unharvestable.
sandbox_base_sha() {
    local task_id="$1" base_sha floor stamp
    [ "$(sandbox_workspace_task_id)" = "$task_id" ] || return 0
    [ -d "$SANDBOX_WORKSPACE/.git" ] || return 0
    [ -f "$SANDBOX_WORKSPACE/.git/autopr-io/model-base-sha" ] || return 0
    # run-codex-sandboxed.sh rewrites this stamp every time it re-clones, so its
    # mtime is the clone's creation time. A clone older than this run's start is
    # the PREVIOUS round's workspace — same card, wrong base — and a snapshot
    # taken during pre-model evidence collection would otherwise harvest it.
    floor="$(investigation_floor_epoch)"
    if [ -n "$floor" ]; then
        stamp="$(sandbox_clone_epoch)"
        { [ -n "$stamp" ] && [ "$stamp" -ge "$floor" ]; } || return 0
    fi
    base_sha="$(tr -d '\r\n' < "$SANDBOX_WORKSPACE/.git/autopr-io/model-base-sha")"
    [[ "$base_sha" =~ ^[0-9a-f]{40}$ ]] || return 0
    git -C "$SANDBOX_WORKSPACE" cat-file -e "$base_sha^{commit}" 2>/dev/null || return 0
    printf '%s' "$base_sha"
}

bounded_copy() {
    local source_file="$1" destination="$2" max_bytes="$3" size
    [ -s "$source_file" ] || return 0
    size="$(wc -c < "$source_file" | tr -d '[:space:]')"
    if [ "$size" -le "$max_bytes" ]; then
        cp "$source_file" "$destination"
    else
        head -c "$max_bytes" "$source_file" > "$destination"
    fi
    chmod 600 "$destination"
}

# bounded_copy through a temp file, so a reader never sees a half-written
# input. Returns non-zero when there was nothing to copy.
atomic_bounded_copy() {
    local source_file="$1" destination="$2" max_bytes="$3"
    [ -s "$source_file" ] || return 1
    bounded_copy "$source_file" "$destination.tmp" "$max_bytes"
    [ -s "$destination.tmp" ] || { rm -f "$destination.tmp"; return 1; }
    mv "$destination.tmp" "$destination"
}

write_transcript() {
    local destination="$1"
    [ -s "$LIVE_LOG" ] || return 1
    tail -c $((MAX_TRANSCRIPT_BYTES * 4)) "$LIVE_LOG" \
        | LC_ALL=C sed -e "s/$(printf '\033')\[[0-9;?]*[a-zA-Z]//g" -e 's/\r//g' \
        | tail -c "$MAX_TRANSCRIPT_BYTES" > "$destination.tmp"
    [ -s "$destination.tmp" ] || { rm -f "$destination.tmp"; return 1; }
    chmod 600 "$destination.tmp"
    mv "$destination.tmp" "$destination"
}

# True when the investigation was killed rather than exiting on its own. A
# harness or model failure late in the window is NOT a legitimate conclusion
# and must never write the marker that blocks the card behind a human
# approval; only a real timeout may.
investigation_was_killed() {
    local status
    [ -n "$INVESTIGATION_EXIT_FILE" ] && [ -s "$INVESTIGATION_EXIT_FILE" ] || return 0
    status="$(tr -dc '0-9' < "$INVESTIGATION_EXIT_FILE" | head -c 5)"
    [ -n "$status" ] || return 0
    [ "$status" -ge 128 ]
}

# The pause note replaces the card's progress_note wholesale, so every durable
# marker the rest of the system reads out of that field has to be carried
# forward: the standing [autopr:directives …] grant, the [autopr:no-spec …]
# ledger, and any question form or human-authored text below the header.
preserved_note_parts() {
    local card_file="$1" existing header body
    existing="$(jq -r '.progress_note // ""' "$card_file")"
    if [ -z "$existing" ]; then
        printf '\t'
        return
    fi
    header="${existing%%$'\n'*}"
    if [ "$header" = "$existing" ]; then
        body=""
    else
        body="${existing#*$'\n'}"
    fi
    local extras='' directives_marker no_spec_marker
    directives_marker="$(printf '%s' "$header" \
        | grep -o '\[autopr:directives [^]]*\]' | head -1 || true)"
    no_spec_marker="$(printf '%s' "$header" | sed -nE \
        's/.*(\[autopr:no-spec [^]]*\] (already_fixed|migration_required|policy_blocked|external_dependency)).*/\1/p' \
        | head -1 || true)"
    [ -z "$directives_marker" ] || extras=" · $directives_marker"
    [ -z "$no_spec_marker" ] || extras="$extras · $no_spec_marker"

    # A non-system note is entirely human-authored; keep all of it.
    case "$header" in
        "🤖 AUTO SETUP"*|"from auto setup"*) ;;
        *) body="$existing" ;;
    esac
    local preserved
    preserved="$(printf '%s\n' "$body" | awk '
        /^(Why more time|Done so far|Latest progress|Next step):/ { next }
        NF { seen = 1 }
        seen { lines[n++] = $0 }
        END {
            while (n > 0 && lines[n-1] ~ /^[[:space:]]*$/) n--
            for (i = 0; i < n; i++) print lines[i]
        }
    ')"
    printf '%s\t%s' "$extras" "$preserved"
}

# One in-flight snapshot, taken WHILE the model is still working.
# save_checkpoint is a separate workflow step: it never runs if this machine or
# the runner process dies outright, and the next run's `rm -rf` on the sandbox
# then destroys the only copy. This timer is what turns a hard kill into losing
# minutes of model work instead of the entire investigation.
snapshot_checkpoint() {
    local card_file="$1" status=0
    [ ! -f "$SNAPSHOT_STOP_FILE" ] || return 0
    # One pass at a time, and never concurrently with `save`/`consume`.
    snapshot_lock_acquire "$SNAPSHOT_PASS_WAIT_SECONDS" || return 0
    # `die` inside the pass would otherwise leave the lock held until the stale
    # reclaim, and `halt` would block on it for two minutes.
    trap snapshot_lock_release EXIT
    if [ -f "$SNAPSHOT_STOP_FILE" ]; then
        # halt_snapshots landed while this pass was waiting for the lock.
        snapshot_lock_release
        trap - EXIT
        return 0
    fi
    if snapshot_pass "$card_file"; then
        status=0
    else
        status=$?
    fi
    snapshot_lock_release
    trap - EXIT
    return "$status"
}

snapshot_pass() {
    local card_file="$1" task_id id8 base_sha root run_key dir seeded seed_key
    local clone_epoch changed newest_epoch=0 file_epoch now skips=0 settled=true
    local patch_bytes=0 patch_saved=false changed_files_json='[]' changed_file_count=0
    local report_saved=false decision_saved=false transcript_saved=false

    task_id="$(card_identity "$card_file")"
    id8="$(card_id8 "$card_file")"
    base_sha="$(sandbox_base_sha "$task_id")"
    # Not this run's workspace (wrong card, or a clone from a previous round).
    [ -n "$base_sha" ] || return 0
    clone_epoch="$(sandbox_clone_epoch)"
    [ -n "$clone_epoch" ] || return 0

    root="$(task_root "$card_file")"
    # Stable across this run's passes so they overwrite one directory, unique
    # across runs so run N+1 never writes into run N's un-consumed checkpoint.
    run_key="${GITHUB_RUN_ID:-local}-$clone_epoch-inflight"
    dir="$root/$run_key"
    umask 077
    mkdir -p "$dir"
    chmod 700 "$CHECKPOINT_ROOT" "$root" "$dir"

    # The index is only valid for the clone it was built against. The base SHA
    # alone is not: it is unchanged across the mid-run directive retry and
    # across consecutive runs on an unchanged main, both of which re-clone.
    seed_key="$base_sha:$clone_epoch"
    seeded="$(cat "$SNAPSHOT_INDEX_BASE" 2>/dev/null || true)"
    if [ "$seeded" != "$seed_key" ]; then
        rm -f "$SNAPSHOT_INDEX"
        if ! GIT_INDEX_FILE="$SNAPSHOT_INDEX" git -C "$SANDBOX_WORKSPACE" \
                read-tree "$base_sha"; then
            snapshot_warn "could not seed the snapshot index from $base_sha"
            return 1
        fi
        printf '%s' "$seed_key" > "$SNAPSHOT_INDEX_BASE"
    fi
    if ! GIT_INDEX_FILE="$SNAPSHOT_INDEX" git -C "$SANDBOX_WORKSPACE" \
            add --all -- . 2>/dev/null \
        || ! GIT_INDEX_FILE="$SNAPSHOT_INDEX" git -C "$SANDBOX_WORKSPACE" \
            diff --cached --name-only "$base_sha" -- . > "$dir/changed-files.txt.tmp" 2>/dev/null \
        || ! GIT_INDEX_FILE="$SNAPSHOT_INDEX" git -C "$SANDBOX_WORKSPACE" \
            diff --cached --binary --full-index "$base_sha" -- . > "$dir/model.patch.tmp" 2>/dev/null; then
        # Most often the model holds a lock; the next pass sees a settled tree.
        # Either way this is a failure, not a no-op: say so.
        snapshot_warn "could not diff the live workspace"
        rm -f "$dir/changed-files.txt.tmp" "$dir/model.patch.tmp"
        return 1
    fi

    # A file the model is still streaming into would be captured truncated, and
    # `git apply --check` on the resume would accept it. Wait a pass — bounded,
    # so a continuously-writing model still gets checkpointed.
    now="$(date +%s)"
    while IFS= read -r changed; do
        [ -n "$changed" ] || continue
        [ -e "$SANDBOX_WORKSPACE/$changed" ] || continue
        file_epoch="$(file_mtime_epoch "$SANDBOX_WORKSPACE/$changed")"
        [ -n "$file_epoch" ] || continue
        [ "$file_epoch" -le "$newest_epoch" ] || newest_epoch="$file_epoch"
    done < "$dir/changed-files.txt.tmp"
    if [ "$newest_epoch" -gt 0 ] \
        && [ $((now - newest_epoch)) -lt "$SNAPSHOT_SETTLE_SECONDS" ]; then
        skips="$(tr -dc '0-9' < "$SNAPSHOT_SKIP_FILE" 2>/dev/null | head -c 3)"
        [ -n "$skips" ] || skips=0
        if [ "$skips" -lt "$SNAPSHOT_MAX_UNSETTLED_SKIPS" ]; then
            printf '%s' "$((skips + 1))" > "$SNAPSHOT_SKIP_FILE"
            snapshot_warn "workspace still being written; skipping this pass"
            rm -f "$dir/changed-files.txt.tmp" "$dir/model.patch.tmp"
            return 0
        fi
        settled=false
    fi
    printf '0' > "$SNAPSHOT_SKIP_FILE"

    patch_bytes="$(wc -c < "$dir/model.patch.tmp" | tr -d '[:space:]')"
    if [ "$patch_bytes" -gt 0 ] && [ "$patch_bytes" -le "$MAX_PATCH_BYTES" ]; then
        chmod 600 "$dir/model.patch.tmp" "$dir/changed-files.txt.tmp"
        mv "$dir/changed-files.txt.tmp" "$dir/changed-files.txt"
        mv "$dir/model.patch.tmp" "$dir/model.patch"
        patch_saved=true
        changed_files_json="$(jq -Rsc \
            'split("\n") | map(select(length > 0))' "$dir/changed-files.txt")"
        changed_file_count="$(jq 'length' <<< "$changed_files_json")"
    else
        # An earlier pass's patch must not survive as this checkpoint's resume
        # patch: investigate.sh resumes on file presence, so a stale model.patch
        # under metadata that says patch_saved:false is silently replayed — the
        # directive-violation retry's `git reset --hard` would be undone by it.
        rm -f "$dir/changed-files.txt.tmp" "$dir/model.patch.tmp" \
            "$dir/model.patch" "$dir/changed-files.txt"
    fi

    ! atomic_bounded_copy "$SANDBOX_WORKSPACE/.git/autopr-io/output/report.md" \
        "$dir/report.md" "$MAX_REPORT_BYTES" || report_saved=true
    if atomic_bounded_copy "$SANDBOX_WORKSPACE/.git/autopr-io/output/decision.json" \
        "$dir/decision.json" "$MAX_DECISION_BYTES"; then
        # Copied mid-write, this is truncated JSON. It is re-attached as a model
        # input, so keep it only when it still parses.
        if jq -e . "$dir/decision.json" >/dev/null 2>&1; then
            decision_saved=true
        else
            rm -f "$dir/decision.json"
        fi
    fi
    ! write_transcript "$dir/transcript.log" || transcript_saved=true

    jq -n \
        --arg task_id "$task_id" --arg id8 "$id8" --arg run_id "${GITHUB_RUN_ID:-local}" \
        --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg base_sha "$base_sha" \
        --argjson patch_saved "$patch_saved" --argjson patch_bytes "$patch_bytes" \
        --argjson changed_file_count "$changed_file_count" \
        --argjson changed_files "$changed_files_json" \
        --argjson report_saved "$report_saved" --argjson decision_saved "$decision_saved" \
        --argjson transcript_saved "$transcript_saved" --argjson settled "$settled" \
        '{schema_version:1,task_id:$task_id,id8:$id8,run_id:$run_id,
          created_at:$created_at,base_sha:$base_sha,inflight:true,settled:$settled,
          runtime_limited:false,elapsed_seconds:null,timeout_minutes:null,
          patch_saved:$patch_saved,patch_bytes:$patch_bytes,
          changed_file_count:$changed_file_count,changed_files:$changed_files,
          report_saved:$report_saved,decision_saved:$decision_saved,
          transcript_saved:$transcript_saved,progress_excerpt:""}' \
        > "$dir/metadata.json.tmp"
    chmod 600 "$dir/metadata.json.tmp"
    mv "$dir/metadata.json.tmp" "$dir/metadata.json"

    # Only claim the resume pointer once there is real work behind it.
    if [ "$patch_saved" = true ] || [ "$report_saved" = true ] \
        || [ "$decision_saved" = true ]; then
        printf '%s\n' "$run_key" > "$root/active.tmp"
        chmod 600 "$root/active.tmp"
        mv "$root/active.tmp" "$root/active"
        printf '%s\n' "$dir"
    fi
    # `save` runs only when the investigation did NOT succeed, so it is not the
    # place that reclaims a successful run's snapshot directory.
    prune_checkpoints "$root"
}

save_checkpoint() {
    local card_file="$1" report_file="$2" decision_file="$3"
    local started_at="$4" timeout_minutes="$5" task_id id8 project_id
    local root run_key checkpoint_dir base_sha patch_bytes=0 patch_saved=false
    local changed_file_count=0 changed_files_json='[]' changed_files_summary=''
    local report_saved=false decision_saved=false transcript_saved=false
    local elapsed=0 runtime_limited=false note reason done progress_excerpt=''
    local saved_outputs='' file_label='' extra_file_count=0
    local workspace_task_id='' header_extras='' preserved_note='' preserved_parts

    # An in-flight snapshot pass must not be running while this harvests the
    # same workspace and rewrites the same active pointer.
    halt_snapshots

    task_id="$(card_identity "$card_file")"
    id8="$(card_id8 "$card_file")"
    project_id="$(jq -r '.project_id // empty' "$card_file")"
    [[ "$project_id" =~ ^[0-9a-fA-F-]{36}$ ]] || die "invalid checkpoint project id"
    [[ "$started_at" =~ ^[0-9]+$ ]] || die "invalid investigation start time"
    [[ "$timeout_minutes" =~ ^(10|20)$ ]] || die "invalid investigation timeout"

    root="$(task_root "$card_file")"
    run_key="${GITHUB_RUN_ID:-local}-$(date -u +%Y%m%dT%H%M%SZ)"
    checkpoint_dir="$root/$run_key"
    umask 077
    mkdir -p "$checkpoint_dir"
    chmod 700 "$CHECKPOINT_ROOT" "$root" "$checkpoint_dir"

    # Stop this lane's container before copying its worktree.
    if [ "${AUTOPR_SANDBOX_TEST_DIRECT:-0}" != 1 ] \
        && [ -x "${AUTOPR_MSANDBOX_BIN:-}" ]; then
        env AGENT_SANDBOX_PROJECT_NAME="${AUTOPR_SANDBOX_PROJECT_NAME:-matcha-kanban-autopr-sandbox}" \
            AGENT_SANDBOX_AUTOPR=1 \
            SANDBOX_WORKSPACE_DIR="$SANDBOX_WORKSPACE" \
            "${AUTOPR_MSANDBOX_BIN}" stop >/dev/null 2>&1 || true
    fi

    # The sandbox runtime root survives between runs and is only wiped when a
    # run actually reaches the model. A run killed during pre-model evidence
    # collection would otherwise harvest the PREVIOUS card's clone and save it
    # as this card's checkpoint, folding unreviewed edits into the wrong PR.
    # run-codex-sandboxed.sh stamps the workspace with the card it belongs to;
    # no stamp, no harvest.
    workspace_task_id="$(sandbox_workspace_task_id)"
    base_sha="$(sandbox_base_sha "$task_id")"
    if [ -z "$base_sha" ] && [ -n "$workspace_task_id" ]; then
        if [ "$workspace_task_id" != "$task_id" ]; then
            printf 'kanban-autopr: sandbox workspace belongs to task %s, not %s; skipping its patch\n' \
                "$workspace_task_id" "$task_id" >&2
        else
            printf 'kanban-autopr: sandbox workspace predates this run; skipping its patch\n' >&2
        fi
    fi
    if [ -n "$base_sha" ]; then
        git -C "$SANDBOX_WORKSPACE" add --intent-to-add --all -- .
        git -C "$SANDBOX_WORKSPACE" diff --name-only "$base_sha" -- . \
            > "$checkpoint_dir/changed-files.txt"
        chmod 600 "$checkpoint_dir/changed-files.txt"
        changed_files_json="$(jq -Rsc \
            'split("\n") | map(select(length > 0))' \
            "$checkpoint_dir/changed-files.txt")"
        changed_file_count="$(jq 'length' <<< "$changed_files_json")"
        changed_files_summary="$(jq -r '.[0:6] | join(", ")' \
            <<< "$changed_files_json")"
        git -C "$SANDBOX_WORKSPACE" diff --binary --full-index "$base_sha" -- . \
            > "$checkpoint_dir/model.patch"
        patch_bytes="$(wc -c < "$checkpoint_dir/model.patch" | tr -d '[:space:]')"
        if [ "$patch_bytes" -gt 0 ] && [ "$patch_bytes" -le "$MAX_PATCH_BYTES" ]; then
            chmod 600 "$checkpoint_dir/model.patch"
            patch_saved=true
        else
            rm -f "$checkpoint_dir/model.patch"
        fi
        bounded_copy "$SANDBOX_WORKSPACE/.git/autopr-io/output/report.md" \
            "$checkpoint_dir/report.md" "$MAX_REPORT_BYTES"
        bounded_copy "$SANDBOX_WORKSPACE/.git/autopr-io/output/decision.json" \
            "$checkpoint_dir/decision.json" "$MAX_DECISION_BYTES"
    fi
    bounded_copy "$report_file" "$checkpoint_dir/report.md" "$MAX_REPORT_BYTES"
    bounded_copy "$decision_file" "$checkpoint_dir/decision.json" "$MAX_DECISION_BYTES"
    write_transcript "$checkpoint_dir/transcript.log" || true

    [ ! -s "$checkpoint_dir/report.md" ] || report_saved=true
    [ ! -s "$checkpoint_dir/decision.json" ] || decision_saved=true
    [ ! -s "$checkpoint_dir/transcript.log" ] || transcript_saved=true
    if [ "$report_saved" = true ]; then
        progress_excerpt="$(jq -Rs -r '
          split("\n")
          | map(
              gsub("\\r"; "")
              | gsub("^[[:space:]]*(#+|[-*])[[:space:]]*"; "")
              | gsub("[[:space:]]+"; " ")
              | select(length > 0)
              | select((ascii_downcase == "summary") | not)
            )
          | (.[0] // "")[0:320]
        ' "$checkpoint_dir/report.md" 2>/dev/null || true)"
    fi

    elapsed=$(( $(date +%s) - started_at ))
    if [ "$elapsed" -ge $((timeout_minutes * 60 - 45)) ] && investigation_was_killed; then
        runtime_limited=true
    fi
    jq -n \
        --arg task_id "$task_id" --arg id8 "$id8" --arg run_id "${GITHUB_RUN_ID:-local}" \
        --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg base_sha "$base_sha" \
        --argjson elapsed_seconds "$elapsed" --argjson timeout_minutes "$timeout_minutes" \
        --argjson runtime_limited "$runtime_limited" --argjson patch_saved "$patch_saved" \
        --argjson patch_bytes "$patch_bytes" --argjson changed_file_count "$changed_file_count" \
        --argjson changed_files "$changed_files_json" --arg progress_excerpt "$progress_excerpt" \
        --argjson report_saved "$report_saved" --argjson decision_saved "$decision_saved" \
        --argjson transcript_saved "$transcript_saved" \
        '{schema_version:1,task_id:$task_id,id8:$id8,run_id:$run_id,
          created_at:$created_at,base_sha:$base_sha,elapsed_seconds:$elapsed_seconds,
          timeout_minutes:$timeout_minutes,runtime_limited:$runtime_limited,
          patch_saved:$patch_saved,patch_bytes:$patch_bytes,
          changed_file_count:$changed_file_count,changed_files:$changed_files,
          report_saved:$report_saved,decision_saved:$decision_saved,
          transcript_saved:$transcript_saved,progress_excerpt:$progress_excerpt}' \
        > "$checkpoint_dir/metadata.json"
    chmod 600 "$checkpoint_dir/metadata.json"
    # A run that died before the model produced anything must not steal the
    # resume pointer from an in-flight snapshot or an earlier round's work.
    if [ "$patch_saved" = true ] || [ "$report_saved" = true ] \
        || [ "$decision_saved" = true ] || [ ! -f "$root/active" ]; then
        printf '%s\n' "$run_key" > "$root/active"
        chmod 600 "$root/active"
    fi
    prune_checkpoints "$root"

    if [ "$runtime_limited" = true ]; then
        if [ "$timeout_minutes" -eq 20 ]; then
            reason="The first 20-minute investigation ended before AutoPR produced a publishable result."
        else
            reason="The approved 10-minute continuation ended before AutoPR produced a publishable result."
        fi
        if [ "$changed_file_count" -eq 1 ]; then
            file_label="1 file"
        else
            file_label="$changed_file_count files"
        fi
        if [ "$changed_file_count" -gt 6 ]; then
            extra_file_count=$((changed_file_count - 6))
            changed_files_summary="$changed_files_summary, plus $extra_file_count more"
        fi
        if [ "$patch_saved" = true ]; then
            done="Saved a partial patch touching $file_label: $changed_files_summary."
        elif [ "$changed_file_count" -gt 0 ]; then
            done="AutoPR touched $file_label, but the patch exceeded the checkpoint size limit and was not saved: $changed_files_summary."
        else
            done="No code patch was ready when the run stopped."
        fi
        [ "$report_saved" != true ] || saved_outputs="partial report"
        if [ "$decision_saved" = true ]; then
            [ -z "$saved_outputs" ] || saved_outputs="$saved_outputs, "
            saved_outputs="${saved_outputs}decision draft"
        fi
        if [ "$transcript_saved" = true ]; then
            [ -z "$saved_outputs" ] || saved_outputs="$saved_outputs, "
            saved_outputs="${saved_outputs}run transcript"
        fi
        [ -z "$saved_outputs" ] || done="$done Also saved: $saved_outputs."
        preserved_parts="$(preserved_note_parts "$card_file")"
        header_extras="${preserved_parts%%$'\t'*}"
        preserved_note="${preserved_parts#*$'\t'}"
        note="$(jq -nr \
            --arg run_id "${GITHUB_RUN_ID:-local}" --arg reason "$reason" \
            --arg done "$done" --arg progress "$progress_excerpt" \
            --arg extras "$header_extras" --arg preserved "$preserved_note" '
              "🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES · checkpoint \($run_id)\($extras)\n" +
              "Why more time: \($reason)\n" +
              "Done so far: \($done)\n" +
              (if $progress == "" then "" else "Latest progress: \($progress)\n" end) +
              "Next step: Approve 10 more minutes to continue from the saved checkpoint." +
              (if $preserved == "" then "" else "\n\n" + $preserved end)
            ')"
        # mw_api dies on a non-2xx response; a failed card write must not
        # abort the checkpoint before it reports where the work was saved.
        ( mw_api PATCH "/matcha-work/projects/$project_id/tasks/$task_id" \
            "$(jq -n --arg note "$note" '{progress_note:$note,board_column:"changes_requested"}')" ) \
            >/dev/null 2>&1 \
            || printf 'kanban-autopr: warning: checkpoint saved but the card pause note could not be written\n' >&2
    fi

    printf '%s\n' "$checkpoint_dir"
}

consume_checkpoint() {
    local card_file="$1" root active consumed
    # A snapshot pass that lands after this would resurrect the resume pointer
    # for a run whose PR is already published.
    halt_snapshots
    root="$(task_root "$card_file")"
    active="$root/active"
    if [ -f "$active" ]; then
        consumed="$root/consumed-${GITHUB_RUN_ID:-local}-$(date -u +%Y%m%dT%H%M%SZ)"
        mv "$active" "$consumed"
        chmod 600 "$consumed"
    fi
    # The successful path never reaches `save`, so this is the only place that
    # bounds the snapshot directories a healthy card leaves behind.
    [ ! -d "$root" ] || prune_checkpoints "$root"
}

case "${1:-}" in
    save)
        [ "$#" -eq 6 ] || die "usage: checkpoint.sh save CARD REPORT DECISION STARTED_AT_EPOCH TIMEOUT_MINUTES"
        save_checkpoint "$2" "$3" "$4" "$5" "$6"
        ;;
    snapshot)
        [ "$#" -eq 2 ] || die "usage: checkpoint.sh snapshot CARD"
        snapshot_checkpoint "$2"
        ;;
    latest)
        [ "$#" -eq 2 ] || die "usage: checkpoint.sh latest CARD"
        latest_checkpoint "$2"
        ;;
    consume)
        [ "$#" -eq 2 ] || die "usage: checkpoint.sh consume CARD"
        consume_checkpoint "$2"
        ;;
    snapshot-arm)
        [ "$#" -eq 1 ] || die "usage: checkpoint.sh snapshot-arm"
        arm_snapshots
        ;;
    snapshot-halt)
        [ "$#" -eq 1 ] || die "usage: checkpoint.sh snapshot-halt"
        halt_snapshots
        ;;
    *)
        die "usage: checkpoint.sh save|snapshot|snapshot-arm|snapshot-halt|latest|consume ..."
        ;;
esac
