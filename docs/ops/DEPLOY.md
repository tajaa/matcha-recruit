# Deploy — full detail

Moved from root `CLAUDE.md`'s Deploying section. Read root `CLAUDE.md` first for the normal rollout command, the hotfix path, and the blue-green rule — those stay there.

## Dispatch from GitHub Actions / mobile

**Or dispatch from the Actions tab / GitHub mobile app** (`.github/workflows/deploy.yml`, `workflow_dispatch` — no `git push`/laptop needed once the branch carrying the workflow file is merged): pick `target` (`matcha`/`backend`/`frontend`) + optional `hotfix` toggle, same `update-ec2.sh` underneath ("verbatim laptop path" per the workflow's own step name). Build job (`build`) runs on the free `ubuntu-24.04-arm` runner via OIDC (`AWS_ROLE_ARN`, no long-lived AWS keys — trust + ECR-push policy in `deploy/github-oidc/`); deploy job (`deploy`) SSHs in with `EC2_SSH_KEY` (`secrets/roonMT-arm.pem`, the same key used from the laptop). All third-party actions are SHA-pinned — the deploy job writes the prod key to runner disk, so a mutable-tag action is a real risk there, not a hypothetical one. Landing-page build-version marker derives from `GITHUB_RUN_NUMBER + 500` under CI instead of the laptop's gitignored counter file (`scripts/build-and-push.sh:bump_landing_build_version` — CI has no persisted state to increment).

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
the PR `production-verification-needed`. The AutoPR dashboard shows the resulting state.
The operator records a completed manual check through
`record-production-verification.yml`; it accepts only a merged PR with that outstanding
label and writes the actor, bounded evidence, result, and workflow link back to the PR.
As with the other post-deploy dispatches, dispatch failure warns but does not roll back a
healthy blue/green swap.
