# Deploy — full detail

Moved from root `CLAUDE.md`'s Deploying section. Read root `CLAUDE.md` first for the normal rollout command, the hotfix path, and the blue-green rule — those stay there.

## Dispatch from GitHub Actions / mobile

**Or dispatch from the Actions tab / GitHub mobile app** (`.github/workflows/deploy.yml`, `workflow_dispatch` — no `git push`/laptop needed once the branch carrying the workflow file is merged): pick `target` (`matcha`/`backend`/`frontend`) + optional `hotfix` toggle, same `update-ec2.sh` underneath ("verbatim laptop path" per the workflow's own step name). Build job (`build`) runs on the free `ubuntu-24.04-arm` runner via OIDC (`AWS_ROLE_ARN`, no long-lived AWS keys — trust + ECR-push policy in `deploy/github-oidc/`); deploy job (`deploy`) SSHs in with `EC2_SSH_KEY` (`secrets/roonMT-arm.pem`, the same key used from the laptop). All third-party actions are SHA-pinned — the deploy job writes the prod key to runner disk, so a mutable-tag action is a real risk there, not a hypothetical one. Landing-page build-version marker derives from `GITHUB_RUN_NUMBER + 500` under CI instead of the laptop's gitignored counter file (`scripts/build-and-push.sh:bump_landing_build_version` — CI has no persisted state to increment).

## Change-detected builds (2026-09-07)

`build-and-push.sh` with no target flag no longer builds both images. `detect_changed_targets` asks ECR for the tags on each repo's `:latest` (`aws ecr describe-images --image-ids imageTag=latest`); the script always pushes `<short-sha>` alongside `:latest`, so that tag is "the commit this image was built from". It then runs `git diff --quiet <sha> HEAD -- <paths>` plus `git status --porcelain -- <paths>` (uncommitted edits count as changed):

| Image | Pathspec |
|---|---|
| backend | `server` minus `server/tests`, `server/agent`, `server/agent-ui`, `server/*.md` (mirrors `server/.dockerignore`; agent has its own image) |
| frontend | `client` |

Unknown/unreachable base SHA ⇒ treated as changed (never skip on a guess). Both unchanged ⇒ exit 0, no build. `--remote` runs the same detection to choose `target=` for `deploy.yml`, so a backend-only edit dispatches `backend` rather than rebuilding + swapping both. Explicit flags (`--full`, `--backend-only`, `--frontend-only`, `--all`, gummfit/agent) disable detection; so does `CI=true` (deploy.yml always passes an explicit target and its shallow checkout can't diff anyway). The script ends by printing the `update-ec2.sh` flag that matches what it built.

**Every detection git call runs with `-C "$REPO_ROOT"`.** Git resolves pathspecs against the process CWD, so running the script from `scripts/` made `server`/`client` mean `scripts/server`/`scripts/client`, match nothing, and report "nothing changed" — a silently skipped deploy that still exited 0. A pathspec matching no tracked file now fails open (builds anyway).

## Image push and cache export are sequential (2026-09-07)

`build_image` runs **two** `docker buildx build` passes on the CI registry-cache path, never one:

1. **Image** — `--push --provenance=false --sbom=false` with `--cache-from …:buildcache`, no `--cache-to`. Retried **once** on failure (a re-solve hits the builder's local cache and only re-sends blobs ECR still lacks, so the retry costs seconds).
2. **Cache** — same args, `--output type=cacheonly --cache-to …:buildcache,mode=max,…`. **Non-fatal**: the image is already in ECR by then, and a cold cache next build beats a failed deploy.

Why: both exporters upload the *same* layer digests to the *same* ECR repository, and ECR keeps one upload session per digest. Running them concurrently meant the cache exporter could finalize a blob mid-push, ECR dropped the image exporter's still-open session for that digest, and the push died after minutes with `unknown: The upload with id '…' in the repository with name 'matcha-frontend' … does not exist`. That killed deploy run `34167912548` (frontend only; backend had already pushed). It was always a race — same script, same flags — so re-running "fixed" it; sequential passes remove it.

The per-branch `--cache-from …:buildcache-<branch>` read was dropped at the same time: no such tag has ever existed in these repos, so it only ever logged `failed to configure registry cache importer` into every build log.

## Pending-migration guard (2026-09-07)

`update-ec2.sh` calls `check_pending_migrations` before `ecr_login` on any backend deploy (including `--hotfix`). It reads prod's `alembic_version` via `scripts/ops-health/prod-query.sh alembic` — `docker exec` into the live backend container on the app host, the same read-only path the ops-health workflows use, reachable from GitHub runners — and diffs it against the checkout with `scripts/alembic_graph.py pending <revs...>` (stdlib-only; parses `revision`/`down_revision` with `ast`, verified to match `alembic_pending.py` output).

- Nothing pending ⇒ continue.
- Pending + interactive TTY ⇒ lists them and asks to run `./scripts/migrate-prod.sh` (all of its gates still apply, including typing `migrate prod`); success continues the deploy, anything else aborts.
- Pending + CI/non-TTY ⇒ exit 1 with the list in `$GITHUB_STEP_SUMMARY`. Re-dispatch with `allow_pending_migrations=true` only if the code genuinely doesn't need them.
- Prod at a revision the checkout doesn't contain ⇒ blocks too (you're deploying from the wrong branch). Same override.
- Read failure ⇒ blocks (fail closed); `--allow-pending-migrations` skips.

## PR checks added 2026-09-07 (`ci.yml`, `codeql.yml`)

- `lint` job — changed-files-only: `ruff --select E9,F63,F7,F82` on touched `.py` (main has 16 real `F821` undefined-name errors; whole-tree gating would be permanently red), `eslint` on touched `client/src/**/*.ts(x)` (~490 findings on main), `actionlint` via `rhysd/actionlint:1.7.12` when a workflow changed, and an **Alembic head guard**: `alembic_graph.py heads` on base vs PR; the count may not grow (the repo intentionally has 15 heads — a new migration must chain off an existing one).
- `docker-build` job — build-only `docker buildx build` of `server/Dockerfile` and `client/Dockerfile` on the arm runner with `type=gha` cache, path-filtered, no registry/push/creds. It exists so a broken Dockerfile/lockfile fails the PR, not the deploy runner.
- `codeql.yml` — Python + JS/TS, PRs touching `server/`/`client/` and weekly on main.
- `.github/dependabot.yml` — weekly grouped minor/patch for actions, pip (`playwright` ignored: its pin must move with `server/Dockerfile`'s `ARG PLAYWRIGHT_VERSION`), and the four npm trees. `.github/CODEOWNERS` requests review from the repo owner on every PR, bot-opened ones included.
- `backup-restore-drill.yml` — weekly full `pg_restore` of the newest S3 dump into a throwaway `--memory 1g` `pgvector/pgvector:pg15` (digest-pinned) container on the app EC2; unhealthy ⇒ `ops-health` issue like the other monitors.
- `prune-bot-branches.yml` — weekly delete of `bot/*` / `codex/*` branches whose PRs have all been closed ≥7 days (`scripts/ops-health/prune-merged-bot-branches.sh`, `--dry-run` supported; branches with no PR are never touched). Repo setting `delete_branch_on_merge` is still off — turning it on would make this mostly moot.

## Gitlink footgun

Gitlink footgun: `git clone`-ing a reference doc into the tree instead of downloading it creates a mode-160000 entry with no `.gitmodules` — harmless locally, but `actions/checkout`'s auth teardown runs `git submodule foreach --recursive` and that's fatal under `persist-credentials: false`. Guarded by `scripts/tests/test_ci_guards.sh` case 7; broke deploy run `30132023532`, fixed in `acb1ce1`.

## 2026-07-19 deploy-slowness fixes (don't reintroduce)

Two things used to make every deploy slow, both fixed 2026-07-19 — don't reintroduce them:

- **Never `docker image prune -a` before the pull.** It deletes the cached layers the pull is about to reuse, forcing a cold full-image pull every single deploy. Pruning belongs **after** the swap (running containers keep their images). The pre-pull prune survives only as a `<4GB` free-disk safety valve, and its `df` output is regex-validated — non-numeric output must warn and skip, never abort the deploy under `set -e` and never collapse to `0` (which silently restores the cold-pull cost).
- **The deploy-triggered DB backup is queued and must stay non-fatal.** A normal backend deploy installs `deploy/backup-prod.sh`, `deploy/pg-backup.service`, and `deploy/pg-backup.timer`, enables the twice-daily timer, then uses `systemctl start --no-block` to queue an extra run. The whole install/trigger remains inside an `if`, so a transient scp/SSH/systemd failure warns without killing the deploy. `flock` in the backup script prevents timer/deploy overlap.

The previous `pg-backup.service` ran `~/backup-postgres.sh` and had been **failing silently** because that script targeted a deleted local `matcha-postgres` container. A successful deploy or queued systemd job is not proof of backup completion. `operational-integrity-checks.yml` verifies the newest `postgres-selfhosted/` object after each scheduled backup; for an investigation, also check `systemctl status pg-backup.service` and `~/backup.log`.

## Post-deploy error observation

Every successful Matcha frontend/backend deployment dispatches
`post-deploy-error-regression.yml` from `update-ec2.sh`. The dispatch is
deliberately non-fatal, so a GitHub outage or missing local `gh` session cannot
turn a completed blue-green swap into a failed deploy. It covers laptop and
GitHub Actions deployments, takes a read-only error snapshot immediately, then
compares it with a second snapshot 15 minutes later.

`server_error_reports.occurrences` is a cumulative fingerprint counter, not an
event stream. The monitor therefore detects new normalized error fingerprints
and growth from its own initial snapshot; it is a regression signal, not an
exact request error-rate calculation. A detected spike opens a deduplicated
`deploy-regression` GitHub issue with normalized messages and query-free paths
only. It never creates a PR, changes production data, or blocks deployment.

## Post-deploy admin updates

The same successful-swap hook also dispatches
`admin-updates-autopublish.yml`. It runs on the self-hosted `matcha-autopr` Mac,
checks active backend/frontend commit ancestry and production migration state,
then has Luna/high draft the feature description and usage steps inside the
credential-free AutoPR sandbox. A strict validator and fixed transaction publish
only confirmed deployed entries; partial backend/frontend releases wait until all
required components are live. Dispatch failure never rolls back a healthy deploy,
but workflow failure opens a deduplicated ops issue. Full runbook:
`docs/ops/ADMIN_UPDATES_AUTOPUBLISH.md`.

## Post-deploy AutoPR fix verification

The successful-swap hook also dispatches `post-deploy-fix-verification.yml` for laptop
and GitHub Actions deploys. It examines only merged `autopr` PRs carrying a validated
production-verification trailer and only after the PR's merge commit is contained in the
deployed SHA for its required target.

Safe public GET assertions run automatically and label/comment the PR
`production-verified` or `production-verification-failed`. Authenticated, stateful, and
visual plans are never guessed from CI: the workflow posts the reviewed steps and labels
the PR `production-verification-needed`. Failed automatic checks are not repeated on
every later deploy; after resolving the cause, remove the failure label to request a new
check. The AutoPR dashboard shows the resulting state for Kanban AutoPRs only.
The operator records a completed manual check through
`record-production-verification.yml`; it accepts only a merged PR with that outstanding
label and writes the actor, bounded evidence, result, and workflow link back to the PR.
As with the other post-deploy dispatches, dispatch failure warns but does not roll back a
healthy blue/green swap.
