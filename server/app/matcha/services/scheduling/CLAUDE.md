# Employee scheduling + schedule intelligence — feature spec(s)

Moved verbatim from root `CLAUDE.md`'s Feature Flags table. Root keeps a one-line summary + `→ full spec:` pointer here. Default column below matches `DEFAULT_COMPANY_FEATURES` in `server/app/core/feature_flags.py`.

## Schedule assistant surface (2026-08-21)

`routes/employee_schedule/assistant.py` owns the durable session endpoint and
the voice-transcription endpoint. The editor panel sends typed or transcribed
turns to the canonical Matcha Work SSE route; it does not use the retired
`routes/employee_schedule/chat.py` parser. Voice captures a maximum 45-second
16 kHz mono WAV, is transcribed only, and is not persisted.

`schedule_assistant_session.py` is the auth boundary for the
`(company, user, location, week_start)` tuple. `schedule_assistant_context.py`
returns complete, non-cancelled shifts and aggregates assignments before its
500-shift cap. `schedule_chat.py` and `schedule_assistant_actions.py` enforce
the inclusive selected-week bound at both stage and confirm time. Huume writes
remain confirmation-gated. Individual schedule edits may affect published
shifts; the whole-week builder applies only editable drafts and never publishes.

### Automatic weekly suggestions (migration `empsched18`)

`schedule_auto_generation` is the review-only Celery sweep for the upcoming
Sunday-starting editor week. The global scheduler row is enabled by the
migration; each location still requires the merged `employee_schedule`,
`huume`, and `matcha_work` feature flags. The worker uses existing draft shifts
as staffing demand or the one unambiguous saved week template, then calls the
same deterministic `week_builder.propose_week_draft` path as conversational
Huume. It creates only a `schedule_generation_runs` proposal (`origin=automatic`)
and is idempotent per company/location/week. Existing manual proposals and
applied plans suppress it; cancelling an automatic proposal suppresses it for
the rest of that week rather than recreating it on the next worker restart.

An automatic run has no manager thread up front. The authorized
`schedule_assistant_session` adopts it into that manager's durable
location/week session when opened, minting the normal confirmation token. The
editor's lightweight suggestion-status read can point a manager from the
current week to the prepared upcoming week. Confirmation reuses
`apply_week_draft`, including its input-hash, live-week, availability,
qualification, conflict, and compliance rechecks. The manager can approve,
request a replacement proposal, cancel, or edit the applied drafts before
publishing; no worker path creates or publishes a shift.

The daily digest is fail-closed behind `schedule_daily_digest` plus the
`employee_schedule`/`matcha_ops` feature flags. It groups employee rows before
claiming a recipient, redacts operational mailboxes, releases claims after a
transient send failure, prunes deliveries older than 90 days, uses each
location's timezone, and respects the scheduler row's bounded `max_per_cycle`.
Tests for these DB-facing seams use fake connections; do not run them against a
live or automatically mutating test database.

In the full editor, an assignment-time meal-break advisory opens the affected
shift inspector so the manager can set planned break minutes. It must not fall
through to the generic force-through confirmation used for other advisories.

## `employee_schedule` (default ❌)

### Employee scheduling inputs (migration `empsched16`)

Employee job qualifications now live on `schedule_job_employees` with an
optional active primary job, qualification status/effective dates, and notes.
Employee-centric replacement uses `schedule_profiles.replace_employee_jobs_core`;
the older job-centric checkbox endpoint remains supported and preserves the
metadata on retained rows. Newly active jobs materialize their credential
requirements immediately.

`employee_schedule_profiles` stores min/target/max weekly minutes, consecutive-
day and overtime preferences, and an explicit recurring-availability state.
Existing employees are intentionally not backfilled from full-time/part-time
status: a missing row reads as `unconfirmed`. Manual scheduling keeps the
legacy zero-window = fully-available rule, while future auto-assignment treats
`unconfirmed` as missing input. Both admin and employee availability PUTs call
`replace_availability_core`, so windows and the confirmed state commit in one
caller-owned transaction. Legacy request bodies remain compatible: omitted
state derives `always_available` for zero windows and `windows` otherwise.

**Employee shift scheduling** over the existing roster. Admins build/publish shifts (date/time, role, location, break, required headcount), assign employees, and generate weeks from reusable **shift templates** (time-of-day + weekday mask → concrete dated shifts via `POST /employee-schedule/templates/{id}/generate`); employees view their published shifts and file **swap / drop / unavailability** requests that admins approve/deny. Tables `schedule_shifts` / `schedule_shift_assignments` / `schedule_shift_templates` / `schedule_requests` / `schedule_audit_log` (migration `empsched01`), all `company_id`-scoped; assignments/requests reference `employees` (`org_id`) and `business_locations`. Gates the `/employee-schedule` router (`routes/employee_schedule/` package), the portal `/v1/portal/me/schedule*` endpoints, and the `/app/employee-schedule` page + portal Schedule tab. Pure rules (who is schedulable, week bounds, template→shift windows, PATCH builder, the two forceable 409 shapes) live in `services/scheduling/schedule_rules.py` — DB-free, so they're unit-tested without a database. Four invariants: **double-booking is guarded on every write path** (create, assign, swap-approval, **and retime** — each 409s with `code: schedule_conflict` and takes `?force=true`; a headcount overrun 409s the same way with `code: shift_full`); **cancelled is terminal** (PUT can't flip a cancelled shift back to published — `POST /publish` already refused it, and a resurrected shift reappears on every assignee's portal); **only the fields the caller sent are written** (`build_patch` over `model_fields_set`, so an explicit null clears a nullable column — COALESCE read "unset" and "clear me" identically); and **nobody who has left stays schedulable** (`INACTIVE_EMPLOYMENT_STATUSES` = terminated + offboarded — the status vocabulary is `employees/crud.py:VALID_EMPLOYMENT_STATUSES`, and a test reads it from source to catch drift). `schedule_audit_log.details` is enriched (before/after shift state, `was_published`, employee-initiated markers on request-approval churn) specifically so `schedule_intelligence` can compute off it — see that flag for the analytics layer. **Linked to `training`** (migration `trainsched01`, gated on the company's own `training`/`credential_templates` flags — silent no-op otherwise): assignment-time lapse advisories, `scheduled_role` auto-assign rules, and `kind='training'` shifts — see the `training` row for the full wiring. **Recurring weekly availability** (table `schedule_employee_availability`, migration `empavail01`): an employee with zero rows is fully available (back-compat default); ≥1 row means a weekday with no rows is unavailable and a weekday with rows is available only inside those windows. `services/scheduling/schedule_rules.availability_violations` is the pure DB-free check; a violation raises the same forceable-409 family as a conflict (`code: outside_availability`, `?force=true`) on create/retime/assign/swap-approval, and in `schedule_chat` an unavailable candidate is pre-filtered out of proposal ranking while an unavailable assignee at execute time is dropped with a reason (same convention as a scheduling conflict there — never a hard failure). Editable by the employee (`GET/PUT /v1/portal/me/schedule/availability`) or an admin on their behalf (`GET/PUT /employee-schedule/availability/{employee_id}`), both full-replacement PUT semantics. **Shift duplication** (`POST /employee-schedule/shifts/{id}/duplicate`): copies a shift onto other calendar dates as drafts, preserving time-of-day/duration (`schedule_rules.shift_window_on_date`); follows the bulk-create convention of `generate_from_template` and `schedule_chat.execute_proposal` — never a per-date 409, a conflicting or unavailable assignee is dropped per-copy and reported in the response's `dropped` list rather than blocking the whole call. **Channel-default location** (migration `oploc01`): a `@huume` schedule request in a channel bound to a `business_locations` row (`channels.location_id`) defaults to that store when the message names no location — `schedule_chat_rules.apply_channel_default_location` skips the "Which location?" clarify round entirely. An explicit location hint in the message always wins, even naming a different store; a channel bound to a deactivated location falls through to the normal match/clarify path. **Coverage suggestions** (`services/scheduling/coverage.py:find_coverage_candidates`) — a standalone extraction of `schedule_chat.build_proposal`'s candidate-assembly steps (busy filter, availability filter, week-hours ranking, lapse annotation), consumed by channel `@huume`'s `find_shift_coverage` tool (`services/ems/channel_grounding.py:run_coverage_lookup`) to answer "who can cover for X" without going through proposal-building; read-only, no compliance check (that's the assignment path's job). **Chat-driven shift EDITS** (2026-08-04): `schedule_chat` is no longer create-only — `parse_schedule_request` returns an `action` discriminator (`create`|`edit`), and an edit routes to `build_edit_proposal` → `execute_edit_proposal` through the SAME propose/confirm pill machinery (`schedule_chat_proposals`, `confirm_message_id` claim, 7-day guard, clarify cap); `proposal["kind"] == "edit"` is what `channels_ws._bg_schedule_reply` dispatches on, so there is **no new table and no migration** — the kind rides in the JSONB doc. Six op kinds: `reassign` / `assign` / `unassign` / `retime` / `cancel` / `swap`. Two people named ("give Cara's shift to Casey and Casey's to Cara") parse as TWO `reassign` ops; two SHIFTS named with no people ("swap the opener and the closer") parse as one `swap` op that exchanges both rosters. **`execute_edit_proposal` is two-phase inside one transaction** — every removal first, then every addition — which is what makes a same-window swap correct without swap-specific conflict handling: by the time op 2's `find_conflicts` runs, op 1's removal already happened, so neither person reads as double-booked against the shift they are leaving. Phase-1 removals for `reassign`/`unassign` are staged via `remove_assignment_core(..., write_audit=False)` and the assignment row kept in a `removed[idx]` map; phase 2 either commits the deferred `assignment.delete` audit row (op succeeded) or undoes the removal with `shift_writes.restore_assignment_raw` (op refused — a conflict, a now-full shift, an availability/compliance block, or the shift going cancelled underneath it) — so a refused reassign never leaves the shift a person short, and a refusal never emits the delete/create audit pair `fair_workweek.RELEVANT_ACTIONS` would otherwise double-count as churn. The `swap` kind stays self-contained (both removals + both additions in its own branch, since which people move is only knowable by reading both rosters live), but checks both directions' conflicts BEFORE either side is removed (excluding each person's own outgoing shift from their own conflict check) — a blocked swap costs zero writes, not a remove-then-restore round trip. `unassign`/`reassign` also refuse (rather than silently no-op) when the phase-1 delete matched zero rows — the person wasn't actually on the shift — so that case can't emit a phantom `assignment.delete`. `assign`/`reassign`'s confirm-time re-check now also enforces `required_staff` (a full shift refuses, matching the REST route's `shift_full` 409) alongside conflict/availability/compliance. Writes go through four shared cores in `shift_writes.py` (`apply_assignment_core` / `remove_assignment_core` / `retime_shift_core` / `cancel_shift_core`) extracted from the route handlers for exactly the reason `create_shift_core` was — `werk → matcha.routes` must stay 0. **The cores reuse the existing audit action names verbatim** (`assignment.create` / `assignment.delete` / `shift.update`): `fair_workweek.RELEVANT_ACTIONS` matches on those four strings, so an invented name like `shift.chat_retime` would be silently invisible to Fair Workweek dollar exposure and the pretext shield; `remove_assignment_core` never writes that audit row on a zero-row delete regardless of caller. Chat-driven edits deliberately count as EMPLOYER-initiated churn (no `schedule_requests` row inside `schedule_intelligence_stats`' 120s window) — a manager typed them, so that is honest. Every op re-runs conflict/availability/compliance against CURRENT state at confirm time and is dropped with the violation quoted rather than failing the batch (`execute_proposal`'s convention). Ad-hoc shifts now persist the manager's own label as `role` when they named no explicit role — without it "opener" was lost at the DB boundary and nothing could find the shift again by what it was called; `_resolve_shift_ref` additionally retries without the role filter before giving up, and an ambiguous match lists candidates **with their assignees** (two same-role, same-window shifts otherwise render as identical, unpickable options) — before falling back to that listing it also narrows by `target_time_hint` when the hint parses to an unambiguous clock time (`schedule_chat_rules.parse_time_hint` — "8am"/"8:30pm"/"08:00"/"20:00", never a bare "8" with no am/pm), so "the 8am shift" resolves directly instead of always clarifying. **Job-derived role labels** (2026-09-02): a shift's `role` is no longer free text a caller chooses — `shift_writes.create_shift_core` overwrites it with the job's current name whenever `job_id` is set, so the REST route, chat confirms and week generation cannot disagree about what a shift is called (a job that isn't the company's degrades to the caller's own label rather than raising, matching `check_job_qualification`'s treatment of a stale id). `ShiftCreate.job_id` is REQUIRED — the manual create form picks a company job, never types a label — while `ShiftUpdate.job_id` stays optional and mirrors the name into `role` on the way through, including to NULL (clearing the job clears the label; a kept label would describe a job the shift no longer has). The free-text paths converge through `shift_writes.resolve_job_by_name`: a manager typing "@huume add an opener Tuesday", or a legacy template block with a role and no job, resolves that label to a real job when one matches (location-scoped wins over company-wide) and stays free text when none does — refusing would break a working conversational flow. `assert_job_in_company` is the scope guard: a location-scoped job is refused on any shift/block at a different location **and on a location-less one**, `location_id` omitted means "this caller has no location to check against", and `lock=True` (FOR SHARE) is what actually stops a concurrent rename from persisting a stale name. **An empty qualified roster means UNGATED** (`check_job_qualification`): gating is opted into by naming who is qualified, not by the mere existence of a job — with a mandatory `job_id` on create, the other reading would 409 every assignment for any company that defines jobs but has not filled in the per-job lists yet. Migration `empsched20` is what makes the mandatory `job_id` survivable for existing tenants: it derives one job per distinct `role` label per (company, location) from `schedule_shifts` + `schedule_shift_templates`, gives a company that labelled nothing a single company-wide **General** job, then points every unlinked row at the job its label became and normalizes the label to that job's name. Set-based (TEMP plan table + LATERAL, `ORDER BY (location_id IS NULL), created_at, id` for the deterministic LIMIT 1), re-runnable, and its `downgrade` removes only jobs carrying the derived-note marker that nobody has qualified anyone on.

**Two more entry points into the same edit machinery** (2026-08-05): channel `@huume`'s ASK-loop write tool `propose_schedule_change` (`services/ems/channel_agent.py`/`channel_grounding.run_schedule_change`) and thread Huume's staged tool of the same name (`services/huume/schedule_skill.py`) both call `build_proposal`/`build_edit_proposal`/`coerce_edit_request` directly rather than reimplementing shift resolution a third time — `schedule_chat_proposals` is shared scratch storage across three different "who confirms it" mechanisms (the deterministic fork's reply-to-pill claim, the ASK-loop's same claim via a stamped `pending_proposal_id`, and thread Huume's own two-turn stage/confirm loop via `evaluate_huume_action`, which never touches `confirm_message_id` at all). The thread skill has no channel-scoped location to fall back on, so its `create` args need an explicit `location_name` → `parsed["location_hint"]`; a `build_edit_proposal` clarify has no thread-side round-trip (v1 scope cut) and surfaces as a plain refusal asking the admin to be more specific. `_resolve_shift_ref`'s ambiguous-match rendering (assignee names) is what makes that clarify listing pickable from either surface. Intent widened for edit phrasings (`intent.py` — six new `_SCHEDULE_PATTERNS`, plus `_INTERROGATIVE_LEAD` now accepts a short lead-in clause before the question, so "Dana called out for Wednesday, can you put someone else on it?" reaches ASK instead of LOG); `services/ems/CLAUDE.md` has the ASK-loop tool's own gate/budget details. Default off; admin-toggle (paid add-on); NOT bundled.

**Relative day-hint resolution + deterministic location-clarify resume + time-range narrowing** (2026-08-05, fixes from a live-prod battery on the edit machinery above): edit ops had no symbolic day field at all in the parse prompt (create has `weekdays[]`/`week_hint`; edits only had ISO-exact `target_date`/`second_date`/`new_date`), so "push **tomorrow's** shift back an hour" or "cancel **Friday's** shift" resolved zero date filter and fell straight to an ambiguous multi-day listing. `target_day_hint`/`second_day_hint`/`new_day_hint` (`"today"|"tomorrow"|weekday name`) now ride alongside each date field; `schedule_chat_rules.resolve_day_hint(hint, today)` resolves them deterministically (a named weekday's NEXT occurrence, `today` counting as a match for its own weekday) BEFORE `_resolve_shift_ref` runs, in `build_edit_proposal`'s per-op loop — a day-hint-only op (no exact date, no employee, no role) also had to be added to `coerce_edit_request`'s per-kind minimum-shape gate, or it was dropped before ever reaching resolution. `parse_time_hint` also gained a range split (`_TIME_RANGE_SPLIT_RE`, on `-`/`–`/`—`/"to"/"until") so "9am-5pm" narrows on its first endpoint the same way a bare "8am" always did — a bare-hour-before-"to" ("9 to 5pm") still returns `None` by the pre-existing bare-hour rule, unchanged on purpose (no am/pm to disambiguate). Separately, the **location-clarify round for a NEW shift** (create, not edit) is the channel's own multiple-choice offer (`build_proposal`'s options list, `LOCATION_CLARIFY_QUESTION` constant shared with `channels_ws.py`) — a reply to it used to always re-run the composed follow-up through a fresh `parse_schedule_request` Gemini call, and a real prod miss showed that call coming back non-actionable even when `resolve_clarify_answer` had already snapped the reply onto one of the offered options, cancelling the whole proposal with the generic `CLARIFY_BAIL_TEXT`. `_bg_schedule_reply` now also fetches the proposal's stored `parse` column; when the clarify question is the location question and the reply snapped onto a real option, it resumes straight from that ORIGINAL successfully-parsed request with `location_hint` overridden — no second Gemini call — and even for every other clarify question, a re-parse that comes back `None` now retries the builder from the stored parse instead of cancelling outright (bails only when both are unavailable).

### Break staggering (migration `empsched21`)

`schedule_breaks` answers what breaks an employee owes, per person, in
isolation. `schedule_break_stagger.py` is the operational layer on top: given
every assignee's evaluated `BreakPlan`, it spreads the periods apart so the
floor keeps as many people on it as it can. Pure — no DB, no FastAPI.
`schedule_guidance.resolve_shift_stagger_plan` is the read-time orchestration
behind `GET /employee-schedule/shifts/{id}/break-stagger`; nothing on that path
writes.

**Two columns, two owners.** `compliance_guidance` is the legal record,
recomputed by `refresh_assignment_break_guidance` on every write that touches a
shift's window or roster. `planned_breaks` (JSONB, `empsched21`, nullable, no
backfill) is the manager's reviewed answer to "when", saved through
`PUT .../assignments/{employee_id}/break-plan`. Storing the second inside the
first would put a human edit in a column the next retime silently overwrites.

Invariants, each of which has a regression test in
`tests/employee_schedule/test_break_stagger*.py`:

- **The concurrency budget floors at 1.** `assigned_count` can never exceed
  `required_staff` on a normal shift (assignment writes 409 `shift_full`), so a
  spare-headcount-only model would suggest nothing on every real shift. The
  floor is paired with a `coverage_shortfall` advisory — under-covering for 30
  minutes is the manager's call; hiding it is not.
- **A person is not two bodies.** `_fits` refuses any overlap with the same
  employee's other break regardless of budget. With `max_concurrent >= 2` the
  budget alone let one employee's meal and rest land at the same instant.
- **A break that cannot fit its legal window is never `suggested`.** It is
  placed (a manager still needs an actionable time) but emitted as
  `deadline_conflict` with the overrun spelled out, plus a shift-level advisory.
- **Candidate starts include the window boundaries**, not just the 5-minute
  grid walked out from `preferred` — otherwise an off-grid window
  (12:00–12:12 for a 6-minute break) reports `insufficient_coverage` for a slot
  that is schedulable.
- **Saved times are inputs, not outputs.** `locked_breaks_from_planned` reads
  `planned_breaks` back and pre-places those intervals (`status="saved"`)
  before anything else is placed, so the coverage guarantee survives a manager
  editing an accepted time.
- **Stale saved times are pruned, never rendered.** `prune_planned_breaks`
  runs inside `refresh_assignment_break_guidance` — the one seam every
  invalidating write reaches — and drops an entry whose `(kind, ordinal)` is no
  longer a live non-waived requirement or that no longer lands inside the
  shift. The employee portal renders these verbatim; a noon break on a shift
  that now starts at 18:00 is wrong advice, not stale advice.
- **The PUT is validated against the shift, not just typed.**
  `validate_planned_breaks` rejects duplicate `(kind, ordinal)` pairs, entries
  with no matching unwaived requirement, durations under the legal minimum, and
  times outside the shift window.
- **Times are wall clock on both sides.** Schedule timestamps are UTC-tagged
  wall-clock values and `start_local` carries the location offset; compare and
  render the clock fields, never convert.

The location daily digest (`daily_digest.py`) selects `planned_breaks`
alongside `compliance_guidance` and renders each person's own reviewed time —
without that the whole crew reads the same generic legal line and walks off the
floor together, which is what staggering exists to prevent. The redacted
operational digest gets a count only, never times.

### Schedule Assistant voice turns

The full schedule editor's Huume assistant supports push-to-talk turns as part
of `employee_schedule` (no separate feature flag). The browser records a
maximum 45-second WAV with `client/src/hooks/useVoiceDictation.ts` and uploads
it to `POST /employee-schedule/chat/voice-transcribe`. The audio-tier Gemini
call in `services/scheduling/schedule_voice.py` returns a verbatim transcript
only; audio is not persisted. The server independently requires 16 kHz mono
PCM, caps uploads at 2 MiB, and rejects recordings over 50 seconds. That
transcript then enters the existing
`POST /employee-schedule/chat` proposal builder exactly like typed input, so
voice has no alternate parser or writer. Confirm/cancel speech is classified
with `schedule_chat_rules.parse_confirm_reply`, never by Gemini. A clean spoken
confirmation may apply the active proposal with `as_draft=true`; it is refused
while Edit published is enabled, and voice has no path to `publishWeek`.
Every proposal executor locks and re-checks the proposal row in its write
transaction, so editor, channel, and thread confirmations cannot apply it twice.

## `schedule_intelligence` (default ❌)

**Schedule Intelligence** — analytics over the `employee_schedule` data that no competing scheduler offers, because it cross-joins scheduling against data only Matcha holds. Four read-time, deterministic (no LLM) modules: (1) **incident × schedule correlation** (`services/scheduling/schedule_intelligence.py:build_incident_correlation`) — incident rate on understaffed vs adequately staffed shifts, by location and day/night window, plus fatigue flags (short rest gap or long consecutive-day streak for a named `involved_employee_id`); suppressed to counts-only below 10 incidents / 50 shifts (`schedule_intelligence_stats.small_n_guard`) — directional, never causal. (2) **Fair Workweek / predictive-scheduling $ exposure** (`services/scheduling/fair_workweek.py`) — a curated, individually-cited ordinance table (same idiom as `discipline_compliance`/`schedule_compliance`: partial by design, unmapped jurisdiction ⇒ `applicability: "unmapped"`, never "no exposure") priced against the tenant's OWN `schedule_audit_log` history; **only NYC and Los Angeles are populated** (verified via the `compliance_evals` golden fixtures) — the other ~8 US Fair Workweek cities are real ordinances but unverified here, so they ship absent rather than guessed. Employee-initiated churn (an approved swap/drop/unavailability request) is excluded before any dollar math; a change with no `pay_rate` on file or predating the audit enrichment degrades to a count-only line item, never zero-priced. (3) **Discipline pretext shield** (module 3 of the same service) — attendance discipline records (`discipline_compliance.ATTENDANCE_INFRACTION_TYPES`) flagged when the employee's own schedule shows elevated employer-initiated churn/short-notice changes/hour volatility beforehand — an advisory pattern, not a verdict; **report-only in v1** (no discipline-gate integration — the metric depends on audit history that only accumulates after this feature ships). (4) **Qualified coverage** — per upcoming published shift, qualified-vs-assigned headcount from `employee_credential_requirements` / `employee_credentials` expirations / `training_records`, three-state gated on `credential_templates`/`training` (`None`=module off, `[]`=on-but-clean, matching the `hr_pilot_corpus` idiom). Gates `/schedule-intelligence/*` (mounted on this flag ALONE — each endpoint checks `employee_schedule` itself and returns `{"available": false}` rather than double-gating the mount, so the FE can render "turn on Scheduling first") + the `/app/schedule-intelligence` page. **Grounds three pilots** (the 2026-07-20 pilot-grounding review's own rule: a new analytics engine ships wired into whatever pilots ground on its domain) — HR Pilot corpus `schedint:` group (supervisor-only, stripped by `hr_pilot_corpus.redact_for_employee` since it names understaffed shifts/discipline/lapsed individuals), Broker Pilot `platform:schedule` headline cid (`_tenant_context(..., include_schedule_intel=True)`, gated on the CLIENT's own flag), and the Analysis Pilot `schedule_weekly` platform source (26-week scheduled-hours/understaffing/employer-change series). No new tables — read-time compute only. Default off; admin-toggle; NOT bundled.
