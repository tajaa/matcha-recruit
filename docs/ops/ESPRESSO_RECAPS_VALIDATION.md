# Espresso recap implementation review and validation

## Reviewed range

Branch: `codex/espresso-task-recaps`, based on main at
`2faec1812bfd6338acf3c58bc76ddb88b34d7dda`. Review scope is that merge base through
the PR head. Main advanced independently in TellUs release files; those changes
are outside this branch. Three independent reviewers inspected the initial
`b46fea463875d542184f39e1057e1a058d4ebd4c` checkpoint, then the
`53fbb2b050b2bf63051145858546bcc9625f54a6` follow-up and final correction hunks.
The final published head SHA is recorded in the PR.

A concurrent local edit restoring the planning document's earlier wording was
preserved outside the final implementation commit. It is not an implementation
change or part of the reviewed PR range. No other unrelated working-tree changes
were included.

## Findings and failure paths

No unresolved confirmed findings remain from the independent reviews. Fixes
address individually executable migration statements, durable completion-mail
ownership during flag rollback, empty-chat mail suppression, opted-out retry
grants, event-cap outcome loss, timestamp/cursor ordering, waiting research
follow-ups, stale phase epochs, owner-before-root capture locking, and media
process deadlines/scratch recovery. Frontend fixes cover account/source round
trips, transient polling, stale request responses, private-player denial and
shared preference cache updates.

Final producer checks use real persisted research constraints, explicit suppressed
email outcomes, and safe local calendar/reminder audit snapshots. Result scenes
precede overflow warning actions; warning details remain in the transcript. The
media process owns no provider session and never replays task actions.

Separate passes covered correctness/edge cases; transitions/failure/retry;
producer/consumer parity/version skew; concurrency/idempotency/order; database,
serialization, time and bounds; authorization/privacy/injection; resource budgets;
and validation/documentation/operations. Important traces:

- Enqueue/continuation/child lineage -> original dispatch epoch -> accepted source
  mutation -> immutable snapshot -> frozen manifest -> read/player.
- Owner row lock -> capture epoch predicate -> root/event budget -> upload with
  cleanup intent -> repeated owner/root fence -> optional media attachment.
- Source completion/prompt/child settlement -> 30-second grace -> queue repair ->
  render token/lease/attempt budget -> isolated media child -> publication fence.
- Supervised process -> OS timeout -> descendant kill/reap -> parent-owned TMPDIR
  removal, including incomplete Chromium scratch; archive copy removed after unpack.
- Existing mail eligibility -> persisted sender ownership -> grace/combined summary
  -> current recipient/preference/source validation -> structured send outcome;
  ambiguous acceptance never automatically falls back or resends.
- Source/account invalidation or Delete -> immediate tombstone -> independent
  cleanup intent -> bounded removal of current objects, versions and delete markers.

## Validation

Final command results are also recorded in the PR. The test Python used locally
was `/Users/diego/Documents/github/matcha/server/venv/bin/python`; the worktree has
no separate venv. No dependency files or installed shared environments were modified.

- Full server unit suite: `python -m pytest tests -q --cov=app`, after final review
  fixes, with a separate temporary coverage data/XML path. Loopback tests require
  execution outside the macOS sandbox. Final result: **14,219 passed, 58 skipped,
  9 expected failures**, plus seven passing subtests, in 214.55 seconds.
- Changed-line coverage: `diff-cover <coverage.xml> --compare-branch=<base>
  --fail-under=80`: **86%** (1,336 executable changed lines, 179 uncovered).
  No exclusions or lowered thresholds were introduced.
- Frontend: `NODE_OPTIONS=--no-experimental-webstorage npm exec vitest run` over
  seven touched/related suites: 45 passed. Node 26's experimental Web Storage
  requires that flag locally; CI uses Node 22.
- `npm run build` and `npm run build:recaps`: passed. Existing chunk/import warnings
  remain; changed-client ESLint and changed-Python Ruff fatal checks passed.
- `RUN_RECAP_MEDIA_TESTS=1 python -m pytest tests/recaps/test_media.py -q`: nine
  local tests passed, including four synthetic 68-second timelines and a real
  changing-page Chromium capture stitched and decoded by FFmpeg. The synthetic
  cards are explicitly marked demonstrations. These are not capacity benchmarks.
- `DATABASE_URL=<unused-local-url> python -m alembic upgrade agenttask05:recap01
  --sql`: passed, generating offline transactional SQL only. Static graph has
  fourteen heads; recap01 replaces agenttask05. No database connection or DDL apply.
- Compose YAML parsed; dedicated queue and read-only root verified. No image build,
  deployment, migration apply, live database/S3/mail/calendar action was performed.
- `git diff --check`: passed for reviewed checkpoints and final correction hunks.

The first sandboxed full run found nine loopback permission failures and one
missing split-package registry entry. The entry was fixed; all 83 browser and
registry tests passed with loopback access. A later complete run passed 14,217
before the final calendar/email evidence fixes; the final full rerun passed
14,219. Those initial failures are not hidden or treated as a clean run.

## Residual risk / release gates

See [the runbook](ESPRESSO_RECAPS.md). Migration behavior and PostgreSQL lock races
were inspected and unit-tested with fake persistence, not rehearsed against a real
server. Linux subreaper/pidfd/container hard-kill behavior, private S3 CORS/range/
version deletion/lifecycle, real mail transport, Safari playback and resource
benchmarks on target compute remain pre-enablement gates. Feature flags default
off and require an explicit owner allowlist and user opt-in. No production claims
are inferred from local static-card fixture performance.

## Coverage ledger

Every changed file is listed below. `reviewed + traced` means changed contracts
were followed to relevant producers/consumers beyond the diff; `reviewed` covers
all changed hunks. No generated/binary/vendored artifacts require exclusion, and
no files remain unreviewed. The root verified reported findings against source
and consumers before accepting them.

| File | Status |
|---|---|
| `.gitignore` | reviewed |
| `client/package.json` | reviewed |
| `client/src/work/CLAUDE.md` | reviewed |
| `client/src/work/api/matchaWork/recaps.ts` | reviewed + traced |
| `client/src/work/components/channels/AgentCardMessage.tsx` | reviewed + traced |
| `client/src/work/components/recaps/RecapLink.test.tsx` | reviewed |
| `client/src/work/components/recaps/RecapLink.tsx` | reviewed + traced |
| `client/src/work/components/recaps/RecapPlayer.tsx` | reviewed + traced |
| `client/src/work/components/recaps/RecapPreferences.tsx` | reviewed + traced |
| `client/src/work/components/shell/WorkSidebar.tsx` | reviewed + traced |
| `client/src/work/components/shell/WorkSidebar/CollapsedRail.tsx` | reviewed + traced |
| `client/src/work/hooks/useRecap.test.tsx` | reviewed |
| `client/src/work/hooks/useRecap.ts` | reviewed + traced |
| `client/src/work/hooks/useRecapPreferences.test.tsx` | reviewed |
| `client/src/work/hooks/useRecapPreferences.ts` | reviewed + traced |
| `client/src/work/pages/JobSearch/SearchDetail.tsx` | reviewed + traced |
| `client/src/work/pages/Recap.tsx` | reviewed + traced |
| `client/src/work/pages/Recaps.test.tsx` | reviewed |
| `client/src/work/pages/Recaps.tsx` | reviewed + traced |
| `client/src/work/pages/Tasks/TaskDetail.tsx` | reviewed + traced |
| `client/src/work/pages/WorkSettings.tsx` | reviewed + traced |
| `client/src/work/recaps/render/index.html` | reviewed |
| `client/src/work/recaps/render/main.tsx` | reviewed + traced |
| `client/src/work/recaps/render/scene.css` | reviewed |
| `client/src/work/routes/WorkRouteTree.tsx` | reviewed + traced |
| `client/src/work/types.ts` | reviewed + traced |
| `client/vite.recap.config.ts` | reviewed + traced |
| `deploy/compose.recaps-worker.yml` | reviewed + traced |
| `docs/ops/ESPRESSO_RECAPS.md` | reviewed |
| `docs/ops/ESPRESSO_RECAPS_VALIDATION.md` | reviewed |
| `docs/plans/ESPRESSO_TASK_RECAPS_TECHNICAL_PLAN.md` | reviewed |
| `server/Dockerfile.recaps` | reviewed + traced |
| `server/alembic/versions/recap01_espresso_task_recaps.py` | reviewed + traced |
| `server/app/config.py` | reviewed + traced |
| `server/app/core/services/ai_usage.py` | reviewed + traced |
| `server/app/matcha/models/matcha_work/recaps.py` | reviewed + traced |
| `server/app/matcha/routes/matcha_work/CLAUDE.md` | reviewed |
| `server/app/matcha/routes/matcha_work/__init__.py` | reviewed + traced |
| `server/app/matcha/routes/matcha_work/recaps.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/CLAUDE.md` | reviewed |
| `server/app/matcha/services/matcha_work/agent_runtime/abilities/calendar.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/abilities/screenshots.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/assistant.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/chain.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/chat_entry.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/enqueue.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/phase_run.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_runtime/runner.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_tasks/CLAUDE.md` | reviewed |
| `server/app/matcha/services/matcha_work/agent_tasks/enqueue.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_tasks/intake.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_tasks/job_tasks.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_tasks/mail.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_tasks/model_run.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/agent_tasks/service.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/job_search/CLAUDE.md` | reviewed |
| `server/app/matcha/services/matcha_work/job_search/agent_phase.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/job_search/enqueue.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/job_search/service.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/__init__.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/adapters.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/capture.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/delivery.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/media_job.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/observe.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/reconcile.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/render.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/scope.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/service.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/settings.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/storage.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/storyboard.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/supervisor.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/recaps/transport.py` | reviewed + traced |
| `server/app/workers/CLAUDE.md` | reviewed |
| `server/app/workers/celery_app.py` | reviewed + traced |
| `server/app/workers/tasks/assistant.py` | reviewed + traced |
| `server/app/workers/tasks/recaps.py` | reviewed + traced |
| `server/tests/agent_runtime/test_calendar_ability.py` | reviewed |
| `server/tests/agent_runtime/test_email_ability.py` | reviewed |
| `server/tests/recaps/__init__.py` | reviewed |
| `server/tests/recaps/conftest.py` | reviewed |
| `server/tests/recaps/test_api_scope.py` | reviewed |
| `server/tests/recaps/test_contracts.py` | reviewed |
| `server/tests/recaps/test_delivery.py` | reviewed |
| `server/tests/recaps/test_lifecycle.py` | reviewed |
| `server/tests/recaps/test_media.py` | reviewed |
| `server/tests/recaps/test_recovery.py` | reviewed |
| `server/tests/recaps/test_render_capture_unit.py` | reviewed |
| `server/tests/recaps/test_review_regressions.py` | reviewed |
| `server/tests/recaps/test_worker_storage.py` | reviewed |
