# Auto-scheduling audit — 2026-10-02

This audit found **14 actionable defects (2 P1, 11 P2, 1 P3)** and **4 efficiency opportunities** in the existing main implementation. Highest priority: recipient-side wage authorization and durable recurring-job recovery. This report records the original main-snapshot audit. PR #665 now also implements the fixes and efficiency changes; see [the implementation and validation record](auto-schedule-fixes-2026-10-03.md). The pinned evidence below preserves the original reproductions.

## Reviewed range and scope

- Repository: `tajaa/matcha-recruit`.
- Code baseline: `main` / `origin/main` at `dfe2b7124f3bde34bfffef512886ca6c089748c5`.
- Audit branch: `codex/auto-schedule-audit`, initially at the same SHA; initial merge base was the baseline and the code diff was empty.
- This is a system audit of that main snapshot, not a claim that these defects were introduced by the report PR. Source links below are pinned to the audited SHA.
- Initial audit commit: `a63a3acf81ffb153634898d29e882e8aa700bbc7`, containing only this report. The subsequent implementation scope, coverage and validation are recorded in `auto-schedule-fixes-2026-10-03.md`; the current PR base/head SHAs and merge base are recorded in the PR description.
- The primary main checkout had unrelated uncommitted scheduling-commercial/landing-media changes. They were excluded and preserved. All review source came from an isolated main-based worktree.
- Reviewed surfaces: recurring automation timing/dispatch, deterministic Autopilot demand, week planning/preflight/apply, automatic proposal adoption and authorization, API/model contracts, wizard/configuration/chat UI and related tests.
- Independent reviews covered planner/data, worker/operations, and client/contracts; the coordinating reviewer checked reported defects against source, guards and reproductions and deduplicated them.

## Findings by severity

### 1. [P1] Automatic proposal adoption discloses wage data to employee managers

**Location:** [schedule_assistant_session.py:77](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/schedule_assistant_session.py#L77).

A business admin with `labor_cost` builds through Run now or `/autopilot/run`. The resulting `origin='automatic'` proposal includes `schedule_review.cost.by_employee`. A store manager whose account role is `employee` can open their authorized schedule session and adopt that same proposal. The serializer copies the saved review and demand model into the response without checking the recipient's role or the current labor-cost flag.

Evidence: the real session-open function, with only DB/message I/O mocked and the actual manager-scope resolver retained, returned the saved per-employee cost to an `employee` even though `labor_cost_visible_from({'labor_cost': True}, 'employee')` returned false. [labor_cost_service.py:30](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/labor_cost_service.py#L30) permits only admin/client; [schedule_eligibility_authorization.py:38](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/schedule_eligibility_authorization.py#L38) admits an active employee manager for their own location; [assistant.py:60](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/routes/employee_schedule/assistant.py#L60) returns the service state directly. This also exposes the frozen cost after entitlement changes.

Fix: apply the live flag/role gate when projecting saved proposals and existing session state. Remove all wage-bearing fields, including nested `review.cost` and `demand_model.labor`, from unauthorized responses/state. Price authorized adoption separately. Test admin-build → employee-adopt and entitlement revocation.

### 2. [P1] A publication failure loses a recurring rule's execution chain

**Location:** [schedule_auto_generation.py:94](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/workers/tasks/schedule_auto_generation.py#L94).

The worker commits its occurrence claim by advancing `next_run_at` and setting `last_status='running'`, then publishes the following occurrence at [schedule_auto_generation.py:107](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/workers/tasks/schedule_auto_generation.py#L107). If publication exhausts retries or the process dies at that boundary, the original task replay exits as `superseded_occurrence` at [schedule_auto_generation.py:67](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/workers/tasks/schedule_auto_generation.py#L67). The current proposal is never built and the future occurrence has no queued task. Worker startup registers the module but has no automation-rule reconciliation.

Evidence: an in-memory, stateful reproduction of the real `_run` function persisted next run `2026-10-08T16:00:00Z` and `running`; after simulated Redis publication failure, replay skipped and the planner was awaited zero times. Initial save has the same commit-before-publish boundary at [auto_schedules.py:199](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/routes/employee_schedule/auto_schedules.py#L199); its error leaves a saved enabled rule without a task.

Fix: persist dispatch/work intent durably, reconcile missing deliveries, and allow an unfinished claimed occurrence to resume. A transactional outbox or bounded due-rule dispatcher should cover initial saves, publication failures and post-claim worker death.

### 3. [P2] Concurrent approvals of different proposals commit duplicate draft shifts

**Location:** [week_builder.py:2718](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L2718).

Two manual proposals for the same empty location/week lock different generation-run rows. Both pass the empty-week and snapshot checks before either creates shifts. Employee locks are acquired only at [week_builder.py:2817](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L2817), after shift creation at [week_builder.py:2784](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L2784). The second apply drops overlapping assignments but commits its duplicate unassigned shifts and marks its run applied.

Evidence: the real apply function under a controlled read-committed interleaving returned two successful applies, two committed shifts with one unique window, one assignment and dropped counts `[0, 1]`. The [empsched18_auto_week_generation.py:40](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/alembic/versions/empsched18_auto_week_generation.py#L40) unique index covers automatic proposals only; `create_shift_core` has no week lock or equivalent uniqueness guard.

Fix: serialize competing full-week applies by company/location/week before checking live state or creating shifts. Coordinate other full-week writers with the same lock. Preserve run-level idempotency.

### 4. [P2] Overnight shifts can staff employees during approved time away

**Location:** [week_builder.py:396](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L396).

The planner tests approved time away only on the shift's start date. With Tuesday October 6 PTO and Monday hours 22:00–02:00, Autopilot clips the Tuesday slots, but minimum-shift cutting extends the two-hour Monday interval to four hours. The real planner accepts Monday 22:00–Tuesday 02:00 as filled. Apply checks overlap, weekly availability, qualification and compliance without checking PTO/leave/unavailability dates.

Evidence: pure Autopilot + planner probe returned one filled seat, zero open seats and an end date on the approved PTO day. [week_builder.py:1173](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L1173) also loads time-away ranges only through the nominal week end, omitting spillover dates. [cutter.py:48](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/autopilot/cutter.py#L48) expands short intervals.

Fix: test every civil date intersected by `[starts_at, ends_at)` during planning and confirmation; load time away across the actual buffered/overnight demand span. Include midnight-exclusive and last-night cases.

### 5. [P2] Preflight ignores other proposed assignments when checking cumulative limits

**Location:** [week_builder.py:634](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L634).

Each proposed pair calls the shared compliance checker separately. [shift_compliance.py:233](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/shift_compliance.py#L233) sums persisted assignments and adds only that shift, so sibling assignments in the in-memory week are absent. This misses cumulative blocks and weekly overtime advisories before approval.

Evidence: a confirmed 15-year-old with `allow_overtime=True` received six 7.5-hour proposed shifts (45 hours); real preflight/evaluators, with DB reads mocked, reported zero blocked pairs and zero advisories. The same evaluator given the full 45-hour week returned its configured 40-hour minor block. Confirm-time checking catches the accumulation later and leaves a seat open after review of six filled seats.

Fix: check against a complete proposed assignment ledger, including persisted rows without double counting inherited/source assignments. Replan around cumulative blocks and retain adult overtime advisories in review.

### 6. [P2] First-day opening buffers create shifts outside the selected week's board and publication

**Location:** [windows.py:56](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/autopilot/windows.py#L56).

For a Sunday-start week of October 4, opening 00:15–04:15 with a 30-minute opening buffer produces a shift starting Saturday October 3 at 23:30. Demand reports one shift and five hours, but the weekly grid uses `starts_within=True` at [shifts.py:328](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/routes/employee_schedule/shifts.py#L328) and publication requires starts within the selected range at [shifts.py:1221](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/routes/employee_schedule/shifts.py#L1221).

Evidence: the real demand generator reported one five-hour shift while the exact selected-week predicate matched zero rows. The start-date ownership also affects week snapshots/cost buckets.

Fix: define business-day ownership consistently through planning, display, costing and publication, or explicitly reject unsupported off-week buffers. Merely changing grid overlap would leave publication inconsistent.

### 7. [P2] A stale worker disables a newer saved automation rule

**Location:** [schedule_auto_generation.py:78](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/workers/tasks/schedule_auto_generation.py#L78).

The feature-disabled branch updates by rule id alone. A worker can read version 1 with Huume disabled, then an admin restores the feature and a manager saves version 2 before the update. The stale worker clears version 2's `next_run_at` and disables it, invalidating its already queued task.

Evidence: a stateful fake connection reproduced version 1's task disabling stored version 2. Normal claiming already compares both version and occurrence.

Fix: use the same version/occurrence compare-and-set for disabling a rule, and treat zero affected rows as obsolete work.

### 8. [P2] Late location responses overwrite another store's automation form

**Location:** [AutoSchedulesTab.tsx:114](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/components/employees/AutoSchedulesTab.tsx#L114).

The component persists across location changes. GET responses and PUT completion at [AutoSchedulesTab.tsx:142](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/components/employees/AutoSchedulesTab.tsx#L142) update form/rule state without a scope token. If location A responds after location B loads, B displays A's enabled state, cadence, target and templates. A subsequent save submits those settings to B; Autopilot has no template-location guard to reject them.

Evidence: two rendered-component reproductions covered late GET and PUT; the former saved A's disabled state and three-week target to B.

Fix: bind all load/mutation completion, error and loading-state updates to the current location/request token. Add reordered-response tests for both operations.

### 9. [P2] Autopilot leaves the old resume-session id active after changing week or location

**Location:** [useScheduleHuumeThread.ts:209](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/hooks/employees/useScheduleHuumeThread.ts#L209).

Autopilot success calls `thread.openChat(thread.sessionId)` at [SchedulePilot.tsx:448](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/ops/pages/SchedulePilot.tsx#L448). The hook retains that id across scope changes and sends it with the new location/week. The server correctly rejects the mismatched session with 404. The composer stays disabled and Try again repeats the invalid request; New chat recovers.

Evidence: a hook reproduction covered Autopilot-style resume, a next-week transition, repeated retry failure and New chat recovery. Existing week-change tests only cover a null resume id.

Fix: associate resume state with its location/week and open a fresh session when scope changes before sending the request.

### 10. [P2] Employee-role store managers cannot complete the Autopilot wizard

**Location:** [location_profile.py:73](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/routes/employee_schedule/location_profile.py#L73).

Autopilot readiness/run admit company members who pass location-manager authorization. The wizard unconditionally fetches the profile at [AutopilotWizard.tsx:53](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/components/employees/schedule-pilot/AutopilotWizard.tsx#L53), but profile GET requires admin/client/individual and rejects employee-role managers. Without a profile/policy, Continue at the tuning step is disabled, even when the manager wants unchanged settings.

Evidence: the actual dependency functions admitted employee role for readiness and returned HTTP 403 for the wizard profile read. Client route/entry gates do not remove this authorized-manager path.

Fix: make profile reading use company-member authentication with the existing location guard. Decide policy-write authorization explicitly, or offer a read-only tuning step for managers who can generate but cannot edit policy.

### 11. [P2] Current-week suggestions disappear from the discovery banner after day one

**Location:** [schedule_assistant_session.py:644](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/schedule_assistant_session.py#L644).

The suggestion-status query requires `week_start >= CURRENT_DATE`. A Sunday proposal for the current week is excluded on Tuesday, even when that exact week is requested. The schedule page and Pilot remove the review banner when `available=false`; a later-week suggestion can be displayed instead.

Evidence: date-boundary probe plus UI traces confirmed the filter and banner removal. Manually opening the exact current-week editor still adopts the proposal; it is not permanently unapprovable.

Fix: derive a lower bound from the location's current aligned week, while preserving requested-week preference and excluding completed past weeks. Test midweek and timezone boundaries.

### 12. [P2] Recurring builds omit labor-cost review for eligible subscribers

**Location:** [schedule_auto_generation.py:134](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/workers/tasks/schedule_auto_generation.py#L134).

The worker passes no actor role. The planner forwards None to `cost_delta_for_rows` at [week_builder.py:2552](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L2552), which deliberately returns no cost before reading features. Adoption copies that unpriced saved review and never prices it for an authorized admin. Run now supplies a client/admin role, so equivalent builds have different cost information.

Evidence: direct DB-free role-gate probe returned None without any DB query; adoption contains no pricing path. Consequently cost delta and Autopilot labor percentage are absent from recurring suggestions even with pay data and the paid flag.

Fix: price the frozen plan when an authorized manager adopts/reads it, keeping recipient authorization from finding 1. Do not simply give the worker an admin role and expose its saved wages to all recipients.

### 13. [P2] Revoking Autopilot blocks pausing or changing its saved rule in the UI

**Location:** [AutoSchedulesTab.tsx:211](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/components/employees/AutoSchedulesTab.tsx#L211).

A saved rule retains mode=autopilot after the premium flag is removed, but the entire mode switch disappears. The manager cannot select template mode. Pausing still submits autopilot mode; the backend checks the premium flag unconditionally at [auto_schedules.py:117](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/routes/employee_schedule/auto_schedules.py#L117) and returns 403 even when enabled=false.

Evidence: saved-form, feature-conditioned rendering and PUT validation were traced together. Worker feature checks still prevent execution; the defect is configuration recovery.

Fix: keep template fallback available for existing premium-mode rules and permit disabling them without the revoked premium entitlement. Test flag removal on an enabled saved rule.

### 14. [P3] The mobile Autopilot repair drawer opens in a hidden pane

**Location:** [SchedulePilot.tsx:343](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/ops/pages/SchedulePilot.tsx#L343).

On mobile, a manager opens Autopilot from Inputs and selects Edit week setup or Edit jobs. The callback closes the wizard and opens the drawer but leaves Inputs selected. The drawer's parent at [SchedulePilot.tsx:738](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/client/src/ops/pages/SchedulePilot.tsx#L738) remains `hidden lg:block`, so the form is invisible until Board is selected manually.

Evidence: a rendered DOM reproduction confirmed the hidden ancestor and retained Inputs selection. This was not a device/browser screenshot test.

Fix: select a visible Board/Review mobile pane when opening either repair drawer.

## Efficiency opportunities

These are distinct from the defects. No production latency, memory or dollar savings were benchmarked.

1. **Replace distant Celery ETAs with durable, bounded dispatch.** [schedule_auto_generation.py:28](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/workers/tasks/schedule_auto_generation.py#L28) enqueues the next weekly occurrence about seven days ahead; one-time rules may be further away. This repository uses Redis and does not override transport visibility timeout. Celery documents that ETA tasks occupy worker memory until due and Redis redelivers tasks beyond visibility timeout; its default is one hour. The occurrence/version guards prevent duplicate proposal generation but do not remove delivery/requeue overhead. A database due-rule dispatcher/outbox can also solve finding 2. [Celery ETA guidance](https://docs.celeryq.dev/en/stable/userguide/calling.html#eta-and-countdown), [Redis caveats](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html#caveats). Installed validation environment: Celery 5.6.3 / Kombu 5.6.2; production transport behavior was not exercised.
2. **Reuse the same roster snapshot for demand and planning.** [week_builder.py:2458](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L2458) loads it for Autopilot; [week_builder.py:2017](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L2017) loads it again via the subsequent planning snapshot. A nonempty roster with no due promotions requires seven data SELECTs per load: employees/profiles, qualifications, due availability promotion candidates, availability windows, assignments, time-away union, and gated jobs. Reuse removes seven repeated SELECTs, excluding transaction controls and due-promotion writes, and keeps capacity and assignment planning on one roster view.
3. **Cache initial scarcity counts per shift.** [week_builder.py:460](https://github.com/tajaa/matcha-recruit/blob/dfe2b7124f3bde34bfffef512886ca6c089748c5/server/app/matcha/services/scheduling/week_builder.py#L460) recomputes the identical employee refusal count for each open seat before the planner mutates its working ledger. Cache by shift and retain seat index for tie-breaking. Initial eligibility work drops from `O(vacant seats × employees)` to `O(shifts × employees)`; a 99-seat block repeats the same initial scan 99 times today.
4. **Reuse operation-local profile bundles.** The rules gate, Autopilot input load and findings independently read the same setup/default-template/leader bundle. Pass one bundle through a build/readiness operation where freshness permits. Keep independent confirm-time reads, and keep the fresh generation-time readiness check. Query savings depend on the configured template/leader set.

## Contract and failure-path traces

| Path | Checks and operational effect inspected |
|---|---|
| Manager payload → rule → task | Cadence/mode Pydantic validation; tenant/location/template ownership; local wall-clock occurrence and week alignment; transactional upsert/audit; publication outside commit; version/occurrence claim; past-week delivery guard; readiness/planner handoff; completion write/retry. Findings 2, 7, 13. |
| Template deletion → pending tasks | Transactional pause, next-run clearing and version increment invalidate queued old occurrences. Both enabled and disabled rule paths were inspected. |
| Autopilot inputs → demand | Company/location-scoped committed/POS-only sales, hourly and published history, weather refresh/persistence/failure, holiday exclusion, qualified confirmed-availability capacity, target labor ceiling, leader/crew allocation, cutting and frozen demand model. Findings 4, 6. |
| Demand → proposed week → review | Scarcity/fairness/caps/rest/consecutive-day ledger, qualifications, approved time away, compliance preflight/replans/strip, break relief/findings, cost, JSON proposal and input hash. Findings 4, 5, 12. |
| Proposal insertion/supersession | Older proposed runs retire in the insert transaction; refused rebuild retains prior suggestion; automatic-only partial unique scope index; manual proposals can coexist. Archive/thread row-lock coordination was traced. |
| Automatic proposal → manager session | Company/user/location/week authorization, empty-session reuse, existing/archived session handling, automatic adoption, fresh confirmation token, saved review/state projection and current-week status query. Findings 1, 11, 12. |
| Explicit confirm → apply → warnings | Huume feature/capability/explicit-confirm gate; tenant/run scope; row-level run idempotency; live rules/week/hash rechecks; shift creation; employee locks; availability/qualification/conflict/compliance checks; transactional assignment/audit/applied status; best-effort warning reconciliation after commit. Findings 3–5. |
| UI state → APIs → navigation | Form serialization, saved-rule Run now semantics, reordered GET/PUT responses, current location/week scoping, wizard profile roles, fresh readiness, resume id and retry, mobile setup repair, premium revocation. Findings 8–10, 13–14. |

Eight distinct passes were performed: correctness/edge cases; state/partial failure/rollback/retries; producer-consumer parity/version compatibility; concurrency/order/replay/idempotency; constraints/time/number/serialization boundaries; security/auth/tenant isolation; query/memory/fan-out scaling; tests/docs/observability/config/migrations. Supported nullable profiles, missing feature configuration, zero/max counts, stale/repeated requests, unknown modes/states, overnight/midnight/week boundaries and Unicode-safe serialized display fields were considered. No unsupported Unicode or injection defect was promoted to a finding.

## Coverage ledger

The only changed file in the PR is this report, **reviewed** in full including source references and validation results. No changed file is excluded. The audit's primary-source ledger below is broader than the PR diff; supporting sections outside it were traced as described afterward.

| Primary source | Status | Scope |
|---|---|---|
| `server/app/matcha/services/scheduling/autopilot/__init__.py` | reviewed | Exports |
| `server/app/matcha/services/scheduling/autopilot/policy.py` | reviewed + traced | Policy bounds and model consumers |
| `server/app/matcha/services/scheduling/autopilot/windows.py` | reviewed + traced | Operating windows, grid and publication boundaries |
| `server/app/matcha/services/scheduling/autopilot/availability.py` | reviewed + traced | Slot capacity, qualification and time-away rules |
| `server/app/matcha/services/scheduling/autopilot/curve.py` | reviewed + traced | Hourly/history shape and cutting |
| `server/app/matcha/services/scheduling/autopilot/cutter.py` | reviewed + traced | Interval expansion, coverage proof and breaks |
| `server/app/matcha/services/scheduling/autopilot/labor.py` | reviewed + traced | Targets, capacity and weekly caps |
| `server/app/matcha/services/scheduling/autopilot/forecast.py` | reviewed + traced | Sales/weather inputs and confidence |
| `server/app/matcha/services/scheduling/autopilot/history.py` | reviewed + traced | Published/hourly history and date normalization |
| `server/app/matcha/services/scheduling/autopilot/holidays.py` | reviewed + traced | Baseline exclusions and target-day notes |
| `server/app/matcha/services/scheduling/autopilot/engine.py` | reviewed + traced | Complete forecast-to-demand pipeline |
| `server/app/matcha/services/scheduling/autopilot/inputs.py` | reviewed + traced | Tenant scope, sales fallback, weather/history/pay inputs |
| `server/app/matcha/services/scheduling/autopilot/weather_store.py` | reviewed + traced | Provider/persistence/retry boundaries |
| `server/app/matcha/services/scheduling/week_builder.py` | reviewed + traced | All functions: planner/preflight/replans/findings/readiness/snapshot/propose/cancel/apply |
| `server/app/matcha/services/scheduling/schedule_automation.py` | reviewed + traced | All timing, guards, stale retirement and generation handoff |
| `server/app/matcha/services/scheduling/schedule_assistant_session.py` | reviewed + traced | Entire session/adoption/archive/suggestion/authorization service |
| `server/app/matcha/services/scheduling/schedule_review.py` | reviewed + traced | Entire review builders, summaries, compact/echo contracts |
| `server/app/matcha/routes/employee_schedule/auto_schedules.py` | reviewed + traced | All endpoints, serialization, gates and save/publication boundary |
| `server/app/matcha/routes/employee_schedule/assistant.py` | reviewed + traced | All endpoints and feature/scope dependencies |
| `server/app/matcha/routes/employee_schedule/location_profile.py` | reviewed + traced | Profile read/write validation and authorization |
| `server/app/matcha/routes/employee_schedule/planning.py` | reviewed + traced | Readiness/run/fill preview/apply/discard contracts |
| `server/app/workers/tasks/schedule_auto_generation.py` | reviewed + traced | Every function, claim, enqueue, completion and retry |
| `server/app/workers/celery_app.py` | reviewed + traced | Entire registration/config/startup recovery |
| `server/alembic/versions/empsched17_week_generation.py` | reviewed + traced | Complete upgrade/downgrade, constraints/indexes/existing rows |
| `server/alembic/versions/empsched18_auto_week_generation.py` | reviewed + traced | Complete upgrade/downgrade, constraints/indexes/existing rows |
| `server/alembic/versions/empsched19_schedule_automation_rules.py` | reviewed + traced | Complete upgrade/downgrade, constraints/indexes/existing rows |
| `server/alembic/versions/autopilot02_autopilot_mode.py` | reviewed + traced | Complete upgrade/downgrade, constraints/indexes/existing rows |
| `server/tests/workers/test_schedule_auto_generation.py` | reviewed | Complete test file |
| `server/tests/employee_schedule/test_auto_schedule_routes.py` | reviewed | Complete test file |
| `server/tests/workers/test_celery_scheduler_dispatch.py` | reviewed | Complete test file |
| `server/tests/employee_schedule/test_week_template_routes.py` | reviewed | Complete test file |
| `client/src/components/employees/AutoSchedulesTab.tsx` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/components/employees/schedule-pilot/AutopilotWizard.tsx` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/components/employees/schedule-pilot/autopilotPolicy.ts` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/components/employees/schedule-pilot/AutopilotPolicyFields.tsx` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/components/employees/schedule-pilot/SchedulePilotToolbar.tsx` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/components/employees/schedule-pilot/InputsRail.tsx` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/ops/pages/SchedulePilot.tsx` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/hooks/employees/useScheduleHuumeThread.ts` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/api/employees/scheduleAssistant.ts` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/api/employees/locationProfile.ts` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/hooks/useLocationScope.ts` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/ops/routes/OpsRoutes.tsx` | reviewed + traced | Complete owned client source and applicable contracts |
| `client/src/components/employees/AutoSchedulesTab.test.tsx` | reviewed | Complete test file |
| `client/src/components/employees/schedule-pilot/AutopilotWizard.test.tsx` | reviewed | Complete test file |
| `client/src/ops/pages/SchedulePilot.test.tsx` | reviewed | Complete test file |
| `client/src/hooks/employees/useScheduleHuumeThread.test.tsx` | reviewed | Complete test file |

**Supporting contract sections, not whole-file coverage claims:** `client/src/api/employees/employeeSchedule.ts` and `types/employeeSchedule.ts` automation/readiness/review shapes; `EmployeeSchedule.tsx` lines 1–300 and banner consumers; Huume schedule-week action gates, execution and explicit-confirm paths in `actions.py`, `agent.py`, `schedule_skill.py` and `turn_pipeline.py`; location-profile validation/bundle/write core; availability promotion/window readers; employee manager/role/feature/tenant dependencies and mount gates; labor-cost role and draft-cost projection; qualification/compliance and eligibility helpers; shared shift creation/assignment/employee locks; week grid/publication; PTO/leave/unavailability producers; DB direct/pool connection helpers; Redis and worker deployment/timer configuration. The engine test file and relevant week-builder test sections were inspected; other executed test files are validation evidence, not implied line-by-line review.

## Validation

All unit/probe DB/provider interactions were mocked. No real database, broker or provider calls, migrations, deployments, production writes or product-source edits were performed. Client build output and extra reproduction tests lived in scratch. Existing checkout dependencies were reused; isolated baseline source excluded uncommitted marketing work.

Set these path aliases when reading the commands below:

```sh
AUDIT_ROOT=/Users/diego/.codex/worktrees/auto-schedule-audit/matcha
AUDIT_PYTHON=/Users/diego/Documents/github/matcha/server/venv/bin/python
AUDIT_CLIENT=/private/tmp/matcha-autoschedule-client-kmv8n4w2/client
```

The paths describe the validation session. The managed audit worktree is archived after submitting/pushing the PR, per repository policy; scratch probes are not committed fixtures.

**Server checks**, from `$AUDIT_ROOT/server`:

```sh
PYTHONDONTWRITEBYTECODE=1 "$AUDIT_PYTHON" -m pytest tests/employee_schedule/test_week_builder.py tests/employee_schedule/test_autopilot_engine.py tests/employee_schedule/test_autopilot_inputs.py tests/employee_schedule/test_autopilot_holidays.py tests/employee_schedule/test_autopilot_weather_store.py -q -p no:cacheprovider
"$AUDIT_PYTHON" -m pytest tests/workers/test_schedule_auto_generation.py tests/employee_schedule/test_auto_schedule_routes.py tests/workers/test_celery_scheduler_dispatch.py tests/employee_schedule/test_week_template_routes.py -q
"$AUDIT_PYTHON" -m pytest tests/employee_schedule/test_schedule_assistant_session.py tests/employee_schedule/test_schedule_assistant_route_gate.py tests/employee_schedule/test_schedule_review.py tests/employee_schedule/test_labor_cost.py tests/huume/test_huume_week_builder.py -q -p no:cacheprovider
```

Results: **147 passed**, **91 passed**, **139 passed**, respectively (**377** tests). Nonblocking dependency deprecations were reported. The worker command's pytest-cache write was denied in the managed worktree; tests still all passed. An earlier planner invocation also passed 147 tests before its cache-disabled final run. An initial coordinating-reviewer command named nonexistent `test_labor_cost_service.py`, exited 4 with no tests run; replacing it with the existing `test_labor_cost.py` produced the 139-pass result above. Whole-server-suite gate after fixes does not apply because this PR makes no code fixes; it must run on implementation follow-ups.

**Client checks**, from `$AUDIT_CLIENT`:

```sh
npm run build
npm run test:run -- src/components/employees/AutoSchedulesTab.test.tsx src/components/employees/schedule-pilot/AutopilotWizard.test.tsx src/ops/pages/SchedulePilot.test.tsx src/hooks/employees/useScheduleHuumeThread.test.tsx
npm run test:run -- src/components/employees/AutoSchedulesTab.audit.test.tsx
npm run test:run -- src/ops/pages/SchedulePilot.audit.test.tsx -t audit
npm run test:run -- src/hooks/employees/useScheduleHuumeThread.audit.test.tsx -t audit
npm run test:run -- src/components/employees/AutoSchedulesTab.audit.test.tsx src/ops/pages/SchedulePilot.audit.test.tsx src/hooks/employees/useScheduleHuumeThread.audit.test.tsx -t audit
```

Results: production build **passed** (`tsc -b && vite build`, 6,966 modules); **65** existing tests passed across four files; **2 + 1 + 1** scratch reproduction tests passed, and the coordinating rerun passed all four (45 unrelated cases skipped by filter). Existing Vite large-bundle/mixed-import and Node storage warnings remain. The first scratch build failed TS2307 because its layout lacked the baseline server Cappe JSON fixture; a read-only baseline-server symlink repaired the scratch layout and the rerun passed. The baseline source was not modified to resolve that environment issue.

**DB-free focused reproductions**, inspected and rerun by the coordinating reviewer:

```sh
PYTHONPATH="$AUDIT_ROOT/server" "$AUDIT_PYTHON" -m pytest /private/tmp/matcha_auto_schedule_audit_probes.py -q -s -p no:cacheprovider
"$AUDIT_PYTHON" /private/tmp/matcha_auto_schedule_publication_repro.py "$AUDIT_ROOT/server"
"$AUDIT_PYTHON" /private/tmp/matcha_auto_schedule_disable_race_repro.py "$AUDIT_ROOT/server"
"$AUDIT_PYTHON" /private/tmp/matcha-auto-schedule-probes/01_apply_race.py
"$AUDIT_PYTHON" /private/tmp/matcha-auto-schedule-probes/02_overnight_pto.py
"$AUDIT_PYTHON" /private/tmp/matcha-auto-schedule-probes/03_week_buffer.py
"$AUDIT_PYTHON" /private/tmp/matcha-auto-schedule-probes/04_cumulative_compliance.py
env PYTHONPATH="$AUDIT_ROOT/server" "$AUDIT_PYTHON" /private/tmp/matcha-autoschedule-client-kmv8n4w2/check_profile_roles.py
```

Results: **3 probes passed** for wage disclosure, worker cost omission and the static SQL date boundary; the **six** standalone worker/planner reproductions exited 0 with the evidence listed in findings; actual dependency-function probe confirmed readiness admission/profile 403. The SQL date probe documents the predicate with an in-memory date model, not execution against PostgreSQL. A first coordinating dependency probe omitted `PYTHONPATH` and failed import; the exact environment command above corrected it.

**Range and artifact checks:** initial `git diff --check origin/main...HEAD`, full `git diff --stat` and changed-file list were empty. Before submission, the report-only `git diff --check` and full changed-file/stat summary are checked again, source-link paths/lines are verified against the baseline, and the PR's exact base/head/merge base and only changed file are recorded. No required unit/build gate remains blocked.

## Fix order and acceptance criteria

1. Close saved-proposal wage disclosure with recipient role/entitlement projection, including resumed state and model-facing summaries; then add authorized adoption-time pricing.
2. Make occurrence work/dispatch durable and replayable, remove distant ETA dependence, and version-guard disable writes. Prove Redis failure and crash recovery without losing current or future work.
3. Serialize full-week writes; recheck whole-span time away; preflight the complete proposed ledger; settle first/last-day ownership. Prove concurrent distinct proposals, midnight/overnight PTO, cumulative minor/adult caps and buffered week publication.
4. Fix UI request scope, resume scope, manager profile parity, midweek discovery, revocation recovery and mobile repair. Carry the scratch scenarios into permanent regression tests with each fix.
5. Reuse roster/profile inputs and scarcity calculations after the above invariants are protected. Benchmark realistic roster/seat counts before assigning latency or cost gains.

## Residual risk and excluded claims

- No PostgreSQL integration, live Redis delivery, actual provider availability, browser/device screenshot or production-performance benchmark ran. Concurrency evidence models independent read-committed transactions; verify shared-lock behavior in an explicitly authorized disposable integration environment during fixes.
- Broad manual scheduling, every historical scheduling migration, all training/credential write paths, POS ingestion internals and every unrelated portion of supporting modules were outside this audit. Coverage is scoped by the ledger and traces, not the whole scheduling ecosystem.
- Source behavior is not automatically legal advice: the preflight reproduction exercises the application's existing configured evaluator and does not validate its entire statute catalog.
- Cancellation documentation says cancellation suppresses a weekly automatic replacement, but tests explicitly permit regeneration after cancellation. Record this as documentation/design drift, not a confirmed behavioral bug; align the intended contract separately.
- Schedule times intentionally use UTC-tagged wall-clock values. UTC week bounds alone are not a confirmed timezone defect.
- Null salary classification versus Autopilot's blended-rate query, capped/truncated history/roster behavior and larger-company assignment fan-out remain follow-up candidates without validated impact in this pass. They are not included in the 14 findings.
