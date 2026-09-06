# Make Huume week generation operationally compliant

## Context

The whole-week builder (`services/scheduling/week_builder.py`) now builds from a store's saved
pattern, but it only knows headcount: fill each block to `required_staff`. It has no idea when
the store is open, how much prep time comes before open or cleanup after close, whether the
day's assignments leave the close uncovered, or whether the floor stays staffed while people
take the breaks the law requires. It fills 20/20 and says so, and a manager reads that as
"done" when the schedule may have nobody on for the last hour and no one to relieve a meal
break. Verified:

- The only profile read is `default_week_template_id` (`week_builder.py:640`). `operating_hours`
  exists on `schedule_location_profiles` (`schedloc01`) and nothing consumes it. No buffer columns.
- `_preflight_compliance_blocks` (`:339-384`) only blocks on `severity=="block"`; meal/rest/OT
  from `check_shift_compliance` are `advisory` and silently dropped. "Break relief impossible"
  cannot come from that gate.
- The stagger engine is pure and needs no shift row —
  `schedule_break_stagger.stagger_shift_breaks(*, shift_start_local, shift_end_local,
  required_staff, assignments)` (`:270`) — so it can run on the in-memory plan. Its
  `coverage_shortfall` fires on every normally-staffed shift that owes a break (`:383`), so a raw
  relay would be noise (handled below).
- `unfilled[]` is the only reason channel and it is per-slot; the state block (`prompt.py:212-224`)
  renders counts only, so a follow-up turn never sees why.
- The worker's automatic run rebuilds the staged action from `proposal["unfilled"]`, not `review`
  (`schedule_assistant_session._automatic_action:48-70`) — new data must live on the plan.
- `_input_hash` (`:54`, `:982`) hashes the snapshot, not the plan — adding findings cannot stale a
  run, and the profile must stay OUT of the snapshot so a buffer edit doesn't stale a proposal.

**Decisions (user, 2026-09-06):** buffer rule = ≥1 person during the opening buffer (N min before
open) and closing buffer (M min after close); a set `leader_job_id` absent from the buffer is a
softer `leader_absent_at_open|close` advisory, not a gap. Break relief = report the stagger
engine's shortfall as a per-shift finding; never auto-inflate headcount. Standing rule (memory
`feedback-legal-thresholds-codify`): break rules come from the catalog (`schedule_break_rule_sets`,
already wired); buffer minutes and the 15-min slice are operational policy, in feature code,
labelled as such.

**Non-negotiables:** staged/confirm-first throughout; the builder applies only editable drafts
and never publishes (`apply_week_draft` is untouched); the summary never says "compliant" — it
says what needs review. Severity vocabulary is `gap | advisory` — `block` already means "cannot
stage" elsewhere, and nothing here prevents staging.

---

## 1. Migration `schedloc02` — `server/alembic/versions/schedloc02_location_profile_buffers.py`
`revision="schedloc02"`, `down_revision="schedloc01"`.
```sql
ALTER TABLE schedule_location_profiles
  ADD COLUMN IF NOT EXISTS open_buffer_minutes  SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS close_buffer_minutes SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE schedule_location_profiles
  ADD CONSTRAINT ck_schedule_location_profiles_open_buffer  CHECK (open_buffer_minutes  BETWEEN 0 AND 240),
  ADD CONSTRAINT ck_schedule_location_profiles_close_buffer CHECK (close_buffer_minutes BETWEEN 0 AND 240);
-- downgrade: DROP COLUMN both
```
`services/scheduling/location_profile.py`: `PROFILE_COLS` += both; `MAX_BUFFER_MINUTES = 240` +
`validate_buffer_minutes(value, *, label) -> int` (docstring: operational policy, not law);
`upsert_location_profile` kwargs `open_buffer_minutes=UNSET, close_buffer_minutes=UNSET`;
`profile_context_lines` line `Prep/close buffer: {o}m before open, {c}m after close` (or `none set`).
NOT in `missing_fields` — optional. Route `_serialize` + PUT pass-through; model
`LocationScheduleProfileUpdate` gains `Optional[int] = Field(None, ge=0, le=240)` ×2.

## 2. Coverage evaluator — `services/scheduling/schedule_coverage.py` (new, pure)
```python
SLICE_MINUTES = 15   # policy, not law
GAP_KINDS = {"coverage_gap", "open_buffer_uncovered", "close_buffer_uncovered",
             "break_relief_uncovered", "break_relief_impossible"}
Finding = {kind, severity: "gap"|"advisory", day: "YYYY-MM-DD"|None, weekday: int(0=Sun),
           window: {"start":"HH:MM","end":"HH:MM"}|None, shift_key, job_id, job_name,
           employee_name, minutes: int|None, detail: str}

def evaluate_week_coverage(*, plan_shifts: list[dict], baseline_shifts: list[dict] = (),
    operating_hours: dict, open_buffer_minutes: int, close_buffer_minutes: int,
    leader_job_id: str | None, week_start: date,
    headcount: Literal["assigned", "required"] = "assigned",
    slice_minutes: int = SLICE_MINUTES) -> list[Finding]
```
- `headcount`: `"assigned"` = `len(fixed_employee_ids) + len(proposed_assignments)` (unfilled
  never counts); `"required"` = `required_staff` (readiness: judge the pattern itself).
- `baseline_shifts` = `snapshot["week_shift_state"]` rows with `status=="published"`, headcount
  `len(employee_ids)` — a half-published week (Po Coffee: 34 published) is judged with the floor
  it already has, not reported as empty.
- Times are UTC-tagged wall clock: `fromisoformat(...).replace(tzinfo=None)`; compare clocks
  against `operating_hours` "HH:MM", NEVER convert. Weekday = `(day.weekday()+1) % 7`; no
  `week_start_weekday` argument — the seven dates are `week_start + i`.
- Per day D:
  ```
  key = str(weekday(D)); shifts_D = shifts overlapping [D 00:00, D+1 06:00)
  key absent  → if shifts_D: one no_hours_known(day)          ; continue
  hours[key] is None → demand_on_closed_day per shift          ; continue
  open_dt  = combine(D, open) - open_buffer
  close_dt = combine(D + (1 if close <= open else 0), close) + close_buffer   # overnight
  shift entirely outside [open_dt, close_dt) → demand_outside_hours (advisory)
  grid = slices over [open_dt, close_dt); staffed[t] = Σ headcount(s) for s covering t
  zero runs → split at the buffer edges: inside opening buffer → open_buffer_uncovered,
              inside closing buffer → close_buffer_uncovered, else coverage_gap  (all "gap")
  leader_job_id set and no gap in the opening buffer and no shift with that job overlaps it
              → leader_absent_at_open (advisory); mirror close
  first_hour = max staffed in [open_dt, +60m); last_hour = max staffed in [close_dt-60m, close_dt)
  first_hour ≥ 2 and last_hour ≤ 1 and no gap touched the last hour → thin_close (advisory); mirror
  ```
  Deterministic order (day, window.start, kind). `thin_*` replaces the brief's `front_loaded_day`,
  which as defined was just a close gap and would double-report.

## 3. Break relief — DB seam + planner hook
New in `services/scheduling/schedule_guidance.py` (mirrors `resolve_open_shift_break_plans:241`'s
per-date cache):
```python
async def resolve_week_break_plans(conn, company_id: UUID, *, location_id: UUID,
    shifts: Sequence[tuple[str, datetime, datetime, Sequence[UUID]]],   # (shift_key, starts_at, ends_at, employee_ids)
) -> tuple[ZoneInfo, dict[str, dict[UUID, BreakPlan]], set[date]]       # (tz, plans_by_shift_key, unmapped_dates)
```
One `business_locations.timezone` read; `resolve_break_rules(conn, company_id=, location_id=,
shift_date=)` cached per local date (`reinterpret_schedule_wall_time(starts_at, tz).date()`) —
it takes a pg advisory lock per call (`schedule_break_rule_store.py:29`), so hoisting is
mandatory (≤7 per build). DOB: one query over all employee ids (SQL as `:186`). Waivers: one
`employee_compliance_attestations` query, then per (employee, date) pick the first
`effective_from <= date` in Python. `evaluate_break_plan(..., employee_age=_age_on(dob, date))`;
`resolved.source == "unmapped"` → date into `unmapped_dates`.

In `week_builder.py`: `async def _break_relief_findings(conn, *, company_id, location_id, plan)
-> list[Finding]` — shifts with ≥1 assignee → loader once → per shift `stagger_shift_breaks(
shift_start_local=reinterpret(...), shift_end_local=..., required_staff=..., assignments=[
StaggerAssignment(UUID(eid), plans[key][eid])])`. Advisory `code` → finding:
- `coverage_shortfall` & assigned == 1 → `break_relief_uncovered` (**gap**: "Floor is empty for
  {dur}m while {name} takes their {kind}")
- `coverage_shortfall` & assigned ≥ 2 → `break_relief_thin` (advisory, "Floor drops to
  {assigned-1} during each break"; capped first 2 per day, all counted in `finding_counts`)
- `insufficient_coverage` → `break_relief_impossible` (**gap**); `deadline_conflict` →
  `break_window_conflict` (advisory, quote `result.reason`)
- `unmapped_dates` non-empty → ONE `break_rules_unmapped` per location (`day=None`, names dates)
  — a state with no catalog rules is surfaced, never silently green.
Wrapped `try/except Exception: logger.exception(...); return []` exactly like
`_preflight_compliance_blocks:372` — never fails a build.

## 4. Wiring
`week_builder.py` — `_MAX_FINDINGS = 40`, `_FINDINGS_RETURNED = 20`; after the final
`build_plan` at `:975`, before `_review_payload:976` (DB still open; `plan["shifts"]` ISO'd):
```python
profile = await get_location_profile(conn, company_id=company_id, location_id=location_id) or {}
hours = profile.get("operating_hours") or {}
coverage = evaluate_week_coverage(plan_shifts=plan["shifts"],
    baseline_shifts=[s for s in snapshot["week_shift_state"] if s["status"] == "published"],
    operating_hours=hours, open_buffer_minutes=int(profile.get("open_buffer_minutes") or 0),
    close_buffer_minutes=int(profile.get("close_buffer_minutes") or 0),
    leader_job_id=str(profile["leader_job_id"]) if profile.get("leader_job_id") else None,
    week_start=week_start)
breaks = await _break_relief_findings(conn, company_id=company_id, location_id=location_id, plan=plan)
all_findings = coverage + breaks
plan["findings"] = all_findings[:_MAX_FINDINGS]
plan["metrics"]["finding_counts"] = dict(Counter(f["kind"] for f in all_findings))   # plain dict — metrics is its own JSONB column
plan["metrics"]["gap_count"] = sum(f["kind"] in GAP_KINDS for f in all_findings)
plan["metrics"]["operating_hours_known"] = bool(hours)
```
`persisted_plan:980` and `json.dumps(plan["metrics"]):994` pick these up; return dict `:1002` adds
`"findings": findings[:_FINDINGS_RETURNED]`. Profile is read here, NOT added to the snapshot.
- `_review_payload:93` summary suffix, three variants: `"; {gap_count} coverage/break gap(s) and
  {n} advisory finding(s) need your review."` / `"; no coverage gaps found against the store's
  hours."` (hours known, none) / `"; store hours are not set, so coverage at open/close was not
  checked."`. The word "compliant" never appears (test asserts).
- `get_week_build_readiness:725`: load profile after `default_id:751`; `pattern_source` = draft
  demand if any, else `_load_template_demand` for `week_template_id or default_id` (ValueError →
  `[]`); `pattern_findings = evaluate_week_coverage(plan_shifts=pattern_source, baseline_shifts=
  published rows, headcount="required", ...)[:20]`. Add keys `operating_hours_known`,
  `open_buffer_minutes`, `close_buffer_minutes`, `pattern_findings`. `blockers` unchanged — a hole
  in the pattern is something to fix in the interview, not a refusal to build.
- `apply_week_draft`: **no change**.
- `services/huume/agent.py`: tool response echo (`:1700`) add `response["findings"]`;
  `_HR_OPS_TOOL_SPECS["save_location_schedule_profile"]["fields"]` += both buffers.
- `services/huume/tools.py:879` two INTEGER props ("Minutes of prep before open / cleanup after
  close that someone must be scheduled for; 0-240").
- `services/huume/schedule_profile_skill.py`: `resolve_profile_args` parses both via
  `validate_buffer_minutes` (ValueError → clarify); include in the non-empty check (`is not None`)
  and staged dict; `_summarize` appends `prep 30m / close 20m`; `execute` writes each only when
  carried.
- `services/huume/prompt.py`: state block `schedule_week_draft` branch (`:212`) appends
  `"; {gap_count} coverage/break gap(s), {n} findings — top: " + "; ".join(f["detail"] for f in
  findings[:3])`; `:376` → "…explains any open positions AND returns coverage/break `findings` —
  relay every gap to the manager and never describe the week as compliant or fully covered;
  readiness `pattern_findings` show holes in the pattern itself — say so BEFORE building;
  `operating_hours_known=false` means say coverage could not be checked and offer to save hours";
  `:378` interview list adds "how much prep time before open and cleanup after close (minutes)".
- `schedule_assistant_session._automatic_action:52`: `"findings": (proposal.get("findings") or
  [])[:20]` — the worker path reads the plan, not review.
- `workers/tasks/schedule_auto_generation.py`: no change.

## 5. Client
- `client/src/types/employeeSchedule.ts` `LocationScheduleProfile` + `Update`: both buffer ints.
- `WeekStartPane.tsx`: two `type="number" min=0 max=240` inputs in the Operating hours card
  ("Prep before open / cleanup after close — someone must be on the schedule for these minutes"),
  seeded in `applyProfile`, sent by `saveSetup`.
- `client/src/work/types.ts:852` `HuumeActionScheduleWeekDraft`: `unfilled[].exclusions?`,
  `metrics.finding_counts? / gap_count? / operating_hours_known?`, and `findings?: Array<{kind,
  severity: 'gap'|'advisory', day?, window?, shift_key?, job_name?, employee_name?, minutes?, detail}>`.
- `ActionDocViewer.tsx` after `:341`: "Needs review" block grouped by kind (label map:
  `coverage_gap`→"Floor uncovered", `open_buffer_uncovered`→"Nobody for opening prep", …), rows
  `fmtDayLabel(day) · start–end — detail`; gap = existing red chip, advisory = amber; when
  `metrics.operating_hours_known === false` one muted line "Store hours not set — coverage at
  open/close was not checked".
- `huumeActionMeta.tsx:74` banner: `Use this generated week (${filled}/${required} filled${gaps
  ? `, ${gaps} coverage gap${gaps===1?'':'s'} to review` : ''})?`.

## 6. Tests
`tests/employee_schedule/test_schedule_coverage.py` (new, pure, `_shift(day, "08:00", "16:00",
staffed=1, job_id=None)`): open buffer uncovered (30m buffer, shift at open → 07:30–08:00); close
mirror; midday gap 12:00–14:00 minutes=120; unfilled don't count (required=2 assigned=0 → gap;
`headcount="required"` → none); published baseline covers the floor; overnight 18:00–02:00 → [];
unknown-hours day → single `no_hours_known`; closed day → `demand_on_closed_day` per shift; demand
outside hours is advisory; leader absent only when buffer otherwise covered; `thin_close` when 3
open / 1 close; fully covered → []; json-safe + deterministic.

`tests/employee_schedule/test_week_builder.py` (existing `_FakeConn`/`_empty_week`/AsyncMock idiom;
add AsyncMock `get_location_profile`, `_break_relief_findings`): findings + counts persisted in the
`proposal` JSON; summary never says "compliant" and names gap count; hours-unknown wording; return
caps at 20 but counts uncapped; solo-shift `coverage_shortfall` → `break_relief_uncovered`
(monkeypatch `resolve_week_break_plans`, BreakPlans hand-built per `test_break_stagger.py`'s
`_requirement`/`_plan` ladder); one `break_rules_unmapped` per location; loader raises → `[]`,
plan still `ready`; **every candidate blocked → unfilled + findings, plan still `ready` and
stageable (impossible-compliance case)**; readiness reports `pattern_findings` +
`operating_hours_known`; profile edit after propose does NOT stale the run (`_input_hash`).

`test_location_profile.py`: `validate_buffer_minutes` bounds (`-1`, `241`, `"abc"` raise;
`"30"`→30), context line, `resolve_profile_args` stages buffers / clarifies out of range,
`execute` writes only when carried. `test_location_profile_routes.py`: PUT >240 → 422; GET serializes.
`tests/huume/test_huume_week_builder.py`: state block lists gap count + top 3; spec fields include
buffers. `tests/huume/test_huume_schedule_staged_actions.py`: staged action carries `findings` and
the tool response echoes them; **a week with gaps still requires an explicit "confirm"**
(confirm-first preserved). `test_schedule_assistant_session.py`: `_automatic_action` carries findings.
Client: new `ActionDocViewer.test.tsx` (needs-review block, red/amber, hours-not-set line);
`WeekStartPane.test.tsx` (buffers saved with hours).

## 7. Verification
```
cd server && ./venv/bin/python -m pytest tests/employee_schedule tests/huume tests/workers/test_schedule_auto_generation.py -q
cd client && npx tsc -p tsconfig.app.json --noEmit && npx vitest run src/work/components/panels/HuumePanel src/components/employees/schedule-editor
./scripts/migrate-dev.sh     # after commit; prod apply is the user's call
```
Live, on local dev as **Po Coffee Co** (`tessu2022+pocoffee@gmail.com`; company is present locally,
verified read-only 2026-09-06 — no tenant pull needed), location "Po Coffee Co — Mission"
(`c0ffeeee-0001-4001-8001-000000000002`: 34 published Barista shifts, 0 drafts, no profile):
1. Readiness → expect `operating_hours_known=false`, `published_shift_count=34`,
   `existing_draft_shift_count=0`, the existing "already has published shifts" blocker. Huume must
   interview (hours, buffers, pattern, leader), say coverage cannot be checked until hours are
   saved, and tell the manager to add remaining needs as drafts — never build over the published week.
2. Save a profile (e.g. 07:00–19:00, buffers 30/20), add a few draft shifts, build → findings must
   name any 06:30–07:00 hole if no draft starts before open; card shows the Needs-review block;
   banner says "N coverage gaps to review"; Confirm still required; result lands as drafts only.

## Risks
- `coverage_shortfall` is per-shift and frequent → split solo/thin + per-day cap, else the card is
  a wall of amber. `_input_hash` unchanged by design. JSONB growth ≈10 KB at 40 findings — fine.
  Nothing new is minted as an EMS warning event (out of scope; only training/credential kinds exist).
