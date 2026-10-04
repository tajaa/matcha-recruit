# Auto-scheduling fixes — 2026-10-03

These changes address the 14 confirmed defects and four efficiency changes from [the original audit](auto-schedule-audit-2026-10-02.md). A manager must approve a frozen proposal before drafts are created, and publishing remains explicit.

## Range and environment

- PR #665, branch `codex/auto-schedule-audit`, base `main` at `dfe2b7124f3bde34bfffef512886ca6c089748c5`.
- Audit commit before the fixes: `a63a3acf81ffb153634898d29e882e8aa700bbc7`; merge base was the main SHA above.
- The original managed worktree was restored and verified before editing. Unrelated changes in the primary checkout were preserved.
- The implementation was validated in an isolated source copy and then applied to the original managed worktree. No unrelated primary-checkout changes were included.

## Findings in the implementation

Independent final review found no remaining confirmed actionable defect introduced by the implementation. The 14 original audit findings and their remedies are mapped below. This finding is limited by the unavailable live database, broker, and browser/device checks listed under Operational limits.

## Changes mapped to audit findings

| Findings | Result |
|---|---|
| 1, 12 | Saved reviews, state, message metadata and model history use the recipient's current role and labor-cost feature. Authorized readers receive freshly priced frozen automatic assignments; confirmation identity is preserved. Optional pricing queries use savepoints so a failed lookup cannot abort the session save. |
| 2, 7 | A running occurrence stays durable until terminal completion. Per-rule session locks prevent simultaneous execution; version/occurrence predicates protect every status mutation. Bounded dispatch recovers lost publication, stale queue leases and worker death. New saves clear old leases. |
| 3 | Full-week proposals and bulk template writers share company/location materialization and aligned-week transaction locks, acquired in stable order before live-week reads and inserts. The location lock also serializes overlapping weeks after an anchor change; already misaligned proposals become stale. Run-level replay remains idempotent. |
| 4 | Planning and approval inspect every civil date intersecting a shift, with midnight-exclusive ends and final-night spillover included in the time-away query. |
| 5 | Preflight simulates persisted assignments and accepted proposed assignments in chronological order, using exact durations for weekly limits and sibling rest windows. Rejected assignments never inflate later checks. Replans recalculate the accepted plan. |
| 6 | Readiness rejects opening buffers before the week. Demand generation and approval reject shift starts outside either end of the selected week; a valid overnight end remains allowed. Existing affected proposals become stale and must be rebuilt. |
| 8 | Load, save and Run now completions, errors and busy state are bound to a request generation, including A → B → A selection changes. |
| 9 | Resume IDs, history, streaming, archive and voice callbacks are bound to the location/week/session generation. Changing scope opens a valid session and drops old completions. |
| 10 | Active store managers can read location policy using the existing location guard and proceed with its saved choices. Policy writes retain their existing account-role gate; employee managers see disabled tuning fields. |
| 11 | Suggestion discovery includes the location's current aligned week throughout the week and continues to prefer the requested week. |
| 13 | A revoked Autopilot rule can be paused or switched to a template. Re-enabling or running Autopilot still requires the premium grant. |
| 14 | Mobile repair actions select the visible Board pane before opening Week setup or Jobs. |

## Efficiency

- Future occurrences remain in Postgres. Only deliveries within 120 seconds enter Celery; the dispatcher normally runs every 60 seconds and has a bounded configurable batch (default 100, clamped to 1–1000).
- Demand and planning reuse one Autopilot roster snapshot.
- Initial eligibility scarcity is computed once per shift instead of once per seat.
- Rules, Autopilot inputs and findings share an operation-local profile bundle. Readiness and approval retain independent fresh reads.

No production latency, memory or dollar savings are claimed.

## Contract and failure traces

1. Rule save + audit → version increment + cleared lease → best-effort near-term publication → durable queue lease → per-rule session lock → planner → guarded terminal advance. Redis errors release an unstarted lease; a timeout cannot overwrite a task that already started. A planner/completion exception preserves the occurrence for replay; a committed proposal is found on retry. A stale worker cannot disable or advance a newer rule.
2. Demand → roster → eligibility → accepted-only cumulative compliance → replan → saved proposal → review → explicit confirmation → location/week locks → current anchor + live hash/shift checks → employee locks → live time-away/availability/qualification/compliance → transactional draft/assignment/audit/run status → best-effort warning reconciliation. No publishing path was added.
3. Saved proposal/session → current role + feature gate → copied wage-free state/history or authorized frozen-plan pricing → model input → projected updates/fresh reread → projected message metadata and response. Generic Work reads exclude schedule-only threads. Legacy assistant/system prose with no wage provenance is withheld from unauthorized readers; their own user messages remain visible.
4. Client location/week selection → request token → scoped load/mutation/stream result. Voice scope changes cancel capture and invalidate pending microphone grants, flushes, PCM frames and transcription. The wizard's read permission matches generation permission without widening policy writes. Premium removal exposes pause/template recovery; mobile repair selects its visible pane.

Eight passes cover correctness, state/failure/retry, validation/backward compatibility, concurrency/idempotency, database/time/numeric/serialization bounds, authorization/tenant isolation, scaling, and operations/tests. Independent review and complete file coverage are recorded in the final ledger below.

## Validation

- On the existing PR worktree, `COVERAGE_FILE=/private/tmp/matcha-autoschedule-final.coverage /private/tmp/matcha-autoschedule-final-venv/bin/python -m pytest tests -q -p no:cacheprovider --disable-warnings --cov=app --cov-report=xml:/private/tmp/matcha-autoschedule-final-coverage.xml --cov-report=term:skip-covered` from `server/`: **11,885 passed, 49 skipped, 9 expected failures, 7 subtests passed**, exit 0. A separate isolated-copy run on the same 38-file source patch passed with the same test counts. The first isolated sandbox run had nine loopback-bind permission failures in browser tests; both permitted reruns passed.
- `/private/tmp/matcha-autoschedule-final-venv/bin/diff-cover /private/tmp/matcha-autoschedule-final-coverage.xml --compare-branch=origin/main --fail-under=80` from `server/` after staging all source files: **97% of 362 executable changed lines** covered, 10 missed, exit 0. This is the repository's Git-aware CI threshold of 80%.
- In the existing PR worktree, `npm run test:run -- src/components/employees/AutoSchedulesTab.test.tsx src/components/employees/schedule-pilot/AutopilotWizard.test.tsx src/hooks/employees/useScheduleHuumeThread.test.tsx src/hooks/useVoiceDictation.test.tsx src/ops/pages/SchedulePilot.test.tsx` from `client/`: **90 passed**. `npm run build`, `npx tsc -p tsconfig.app.json --noEmit`, and `npx eslint` on all 11 changed TS/TSX files passed. Client dependencies were installed using `npm ci --legacy-peer-deps --ignore-scripts`.
- `ruff check --no-cache --target-version py312 --select E9,F63,F7,F82` on all 27 changed Python files passed. `git diff --cached --check` passed. The 38-file source patch matches the actual worktree: `git apply --reverse --check --whitespace=error-all` passed, with all 38 expected paths and no extras.

## Operational limits

- No schema migration is required. The dispatcher adds an idempotent row to the existing scheduler settings table, preserves an operator's disable, and supports the existing admin trigger.
- Normal recovery uses the minute dispatcher; killed execution/queue leases become eligible after 660 seconds, longer than the worker's 600-second hard limit. Losing the dispatcher's own countdown message waits for worker startup, currently an hourly systemd recycle. Recovery is durable but is not an exact-time guarantee.
- Advisory lock and broker behavior were tested with controlled fakes; no live database, Redis, worker crash, deployment or migration was exercised.
- Whole-week materialization serializes at each location, including different weeks, to remain safe across changed week anchors and overlapping date ranges. Individual manual shift operations retain their existing locks; simultaneous manual edits still rely on snapshot and assignment revalidation.
- Broader time-away hashes or off-week rejection can require rebuilding older unapproved proposals.
- Browser regressions use rendered DOM tests; device screenshots and production benchmarks were not performed.

## Coverage ledger

Every changed hunk of the 38-file source patch and both review documents was inspected. `reviewed + traced` includes importers, producers, consumers, live checks and failure paths; test and document changes are `reviewed`. No file was excluded.

| File | Status |
|---|---|
| `client/src/components/employees/AutoSchedulesTab.test.tsx` | reviewed |
| `client/src/components/employees/AutoSchedulesTab.tsx` | reviewed + traced |
| `client/src/components/employees/schedule-pilot/AutopilotPolicyFields.tsx` | reviewed + traced |
| `client/src/components/employees/schedule-pilot/AutopilotWizard.test.tsx` | reviewed |
| `client/src/components/employees/schedule-pilot/AutopilotWizard.tsx` | reviewed + traced |
| `client/src/hooks/employees/useScheduleHuumeThread.test.tsx` | reviewed |
| `client/src/hooks/employees/useScheduleHuumeThread.ts` | reviewed + traced |
| `client/src/hooks/useVoiceDictation.test.tsx` | reviewed |
| `client/src/hooks/useVoiceDictation.ts` | reviewed + traced |
| `client/src/ops/pages/SchedulePilot.test.tsx` | reviewed |
| `client/src/ops/pages/SchedulePilot.tsx` | reviewed + traced |
| `server/app/core/routes/admin/platform_settings.py` | reviewed + traced |
| `server/app/matcha/routes/employee_schedule/auto_schedules.py` | reviewed + traced |
| `server/app/matcha/routes/employee_schedule/location_profile.py` | reviewed + traced |
| `server/app/matcha/routes/matcha_work/messaging.py` | reviewed + traced |
| `server/app/matcha/services/matcha_work/turn_pipeline.py` | reviewed + traced |
| `server/app/matcha/services/scheduling/autopilot/engine.py` | reviewed + traced |
| `server/app/matcha/services/scheduling/autopilot/windows.py` | reviewed + traced |
| `server/app/matcha/services/scheduling/schedule_assistant_session.py` | reviewed + traced |
| `server/app/matcha/services/scheduling/schedule_cost_projection.py` | reviewed + traced |
| `server/app/matcha/services/scheduling/shift_compliance.py` | reviewed + traced |
| `server/app/matcha/services/scheduling/shift_writes.py` | reviewed + traced |
| `server/app/matcha/services/scheduling/week_builder.py` | reviewed + traced |
| `server/app/workers/celery_app.py` | reviewed + traced |
| `server/app/workers/tasks/schedule_auto_generation.py` | reviewed + traced |
| `server/tests/employee_schedule/test_auto_schedule_routes.py` | reviewed |
| `server/tests/employee_schedule/test_fill_vacant.py` | reviewed |
| `server/tests/employee_schedule/test_location_profile_routes.py` | reviewed |
| `server/tests/employee_schedule/test_schedule_cost_projection.py` | reviewed |
| `server/tests/employee_schedule/test_schedule_saved_projection.py` | reviewed |
| `server/tests/employee_schedule/test_week_builder.py` | reviewed |
| `server/tests/employee_schedule/test_week_builder_audit_regressions.py` | reviewed |
| `server/tests/employee_schedule/test_week_rules_gate.py` | reviewed |
| `server/tests/employee_schedule/test_week_template_generate.py` | reviewed |
| `server/tests/matcha_work/test_schedule_turn_projection.py` | reviewed |
| `server/tests/workers/test_celery_scheduler_dispatch.py` | reviewed |
| `server/tests/workers/test_schedule_auto_generation.py` | reviewed |
| `server/tests/workers/test_schedule_auto_recovery.py` | reviewed |
| `docs/reviews/auto-schedule-audit-2026-10-02.md` | reviewed |
| `docs/reviews/auto-schedule-fixes-2026-10-03.md` | reviewed |

## Residual risk

No live PostgreSQL lock contention, Redis publication loss, worker kill, end-to-end browser/device path, or production load benchmark was exercised. The DB-free race and recovery tests verify the intended transaction/lease decisions with controlled fakes. Current scheduler startup recovers a lost dispatcher countdown on the existing hourly worker recycle. Pending proposals can become stale after the broader time-away/break-minute snapshot or off-week checks and should be rebuilt. Live integration and PR CI checks remain necessary before merge.
