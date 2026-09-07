# Employee scheduling + schedule intelligence — feature spec(s)

Moved verbatim from root `CLAUDE.md`'s Feature Flags table. Root keeps a one-line summary + `→ full spec:` pointer here. Default column below matches `DEFAULT_COMPANY_FEATURES` in `server/app/core/feature_flags.py`.

## Schedule assistant surface (2026-08-21)

`routes/employee_schedule/assistant.py` owns the durable session endpoint and
the voice-transcription endpoint. The editor panel sends typed or transcribed
turns to the canonical Matcha Work SSE route; it does not use the retired
`routes/employee_schedule/chat.py` parser. Voice captures a maximum 45-second
16 kHz mono WAV, is transcribed only, and is not persisted.

`schedule_assistant_session.py` is the auth boundary for the
`(company, user, location, week_start)` tuple. That tuple is no longer UNIQUE
(migration `huumesched02`): opening the panel starts a NEW chat and the manager
picks an earlier one out of `GET /assistant/sessions`, passing its `session_id`
back to the POST to resume it. Three rules keep that from becoming clutter or a
back door: a latest session nobody has spoken in yet is REUSED rather than
duplicated (open/close/open leaves no empty-thread trail); a resume is scoped to
the same company/user/location/week or it is a 404; and archiving
(`POST /assistant/sessions/{id}/archive`, `mw_threads.status='archived'`, never a
delete — the Huume runs are the audit trail behind applied schedule writes) also
makes `resolve_schedule_assistant_scope` refuse further turns, so a chat removed
from history cannot keep staging writes. A chat is titled read-time from the
first line of its first user message — the editor appends selected-shift context
after a blank line, and that is not what the manager asked. `schedule_assistant_context.py`
returns complete, non-cancelled shifts and aggregates assignments before its
500-shift cap. `schedule_chat.py` and `schedule_assistant_actions.py` enforce
the inclusive selected-week bound at both stage and confirm time. Huume writes
remain confirmation-gated. Individual schedule edits may affect published
shifts; the whole-week builder applies only editable drafts and never publishes.

### Assignment guard + `ScheduleReview` (2026-09-07) — POLICY vs statute, reject-at-stage

Why: "fill the vacant shift-leader shifts" put ONE employee on nine shifts, some overlapping, and Huume
could not say whether it was legal. Audit found the structural causes: stage-time review of an assign
op ran only `check_shift_compliance` (no overlap, no cumulative hours, no availability, no "state not
researched" signal — that function returns `[]` for an ordinary adult shift in an unmapped state), the
batch was never evaluated as a set, and confirm-time dropped the self-inflicted overlaps with copy that
blamed drift. Every adult statutory check is `advisory`; the only hard stops were strict overlap
(`find_conflicts`), minor caps and credential eligibility.

- **`assignment_guard.py`** — `evaluate_batch(assignments, ledgers, week_start_weekday, allow_split_shift,
  pre_blocked)` walks a batch in op order with a per-employee working set (DB intervals + accepted ops), so
  op N sees ops 1..N-1. `blocked` (removed from the proposal): `existing_overlap`, `intra_batch_overlap`,
  plus the caller's DB refusals (`not_qualified`, `outside_availability`, `shift_full` — counting earlier
  assigns to the same shift). `warn` (stays, with the line in the pill): `second_shift_same_day`,
  `rest_gap` (< `POLICY_MIN_REST_HOURS`=8), `consecutive_days` (> profile `max_consecutive_days` else
  `POLICY_MAX_CONSECUTIVE_DAYS`=6), `weekly_cap` (> profile `max_weekly_minutes`) or
  `weekly_overtime_policy` (> 40h without `allow_overtime`). **These `POLICY_*` constants are operational
  defaults, not law** — every reason carries `policy: True/False`; statutes stay in `schedule_compliance`
  / the catalog and are cited verbatim. Applies to agent/planner paths ONLY; manual REST routes and
  `force` are untouched. `build_ledgers` is one query over the batch's employees (same predicate as
  `find_conflicts`) + `employee_schedule_profiles` caps — the knobs the week builder already honoured
  and the chat paths never read.
  The ledger preserves net worked minutes separately from full overlap windows. Its query window
  expands for the largest employee consecutive-day cap, including the supported 14-day setting.
  `ProposedRemoval` mirrors confirm's two phases: unassigns and eligible reassignment sources are
  removed first; cancellations apply in operation order. A rejected reassignment restores its source
  and triggers another review pass so later assignments cannot depend on phantom free time or seats.
  Shift headroom is consumed only after the overlap and eligibility verdict accepts an assignment.
- **`shift_compliance.jurisdiction_rule_status`** → `{state, status ∈ curated|catalog|unmapped|unavailable}`.
  `schedule_review.jurisdiction_message` turns it into the one sentence every surface renders.
  `compliance_status` = `verified` / `advisory` (rules on file) / `unmapped` / `unavailable`. On agent
  paths `unavailable` REFUSES to stage (fail closed; there is no `force` to click through); `unmapped`
  stages with the honesty line and a confirm line that says confirming means you checked the state's
  rules yourself. Result text repeats "Legality was NOT verified for {ST} … you confirmed with that in
  view." The create pill's `rules_unmapped` line now derives from the same helper.
  Standalone creates use the same unavailable refusal as edits/batches. Cross-store swaps retain
  both locations; an unlocated shift is included as unmapped even alongside a curated location.
- **`schedule_review.build_review(doc)`** — the `ScheduleReview` contract (`assignments`, `rejected`,
  `unfilled`, `employees[before/after/warnings]`, `advisories`, `findings`, `jurisdiction`,
  `compliance_status`). Stored on the proposal doc (`doc["review"]`, `doc["compliance_status"]`,
  `doc["rejected"]`, `doc["jurisdiction"]`), returned on `ProposalBuild.review`, merged into Huume's
  staged dict, echoed in the stage-turn tool response (`agent.py`: same reason as `findings`), summarized
  in the state block, and rendered by the pill. Later consumers: the REST preview and the Schedule
  Pilot review pane.
- `schedule_chat._review_assign_ops` (called at the end of `_resolve_edit_ops`) annotates `op["review"]`;
  `build_edit_proposal` / `build_batch_proposal` split accepted vs `rejected`, refuse when nothing
  survives (`ProposalBuild.clarify_kind="refused"` — the skill relays it without the "reply with the
  shift time" hint), and refuse on `unavailable`. `_apply_edit_ops` names an overlap with a shift
  applied earlier in the SAME confirm ("would overlap the … shift applied earlier in this batch") and
  keeps the drift copy only for a real race; acknowledged statutory advisories now reach
  `edit_result_text` and the `schedule_chat.edit_confirm` audit row (`advisories_acknowledged`,
  `compliance_status`).
  Resolved edit operations retain `job_id` for the stage-time qualification check. Confirm-time
  overlap attribution also tracks successful retimes and both sides of a shift swap.
- The bulk `all_vacant_shifts` path is capped by `MAX_BATCH_OPERATIONS` (split plan) like any batch and
  goes through the guard, so "put Dana on everything" lists blocked assignments under
  **Not staged** with reasons; non-overlapping doubles and cap warnings remain stageable policy
  advisories. `propose` reports `operation_count` = what was STAGED, plus
  `rejected_count`, `compliance_status`, `review`.
  `review.operation_count`/`operation_summary` count resolved edits and new shifts before assignments
  are flattened; new shifts have no database IDs yet, and multiple assignees do not inflate the count.
- Tests: `tests/employee_schedule/test_assignment_guard.py` (nine-shift scenario, back-to-back, caps,
  determinism), `test_schedule_review.py`, `test_schedule_chat_guard_integration.py` (split, refused
  clarify, unavailable gate, intra-batch confirm copy), renderer cases in `test_schedule_chat_edits.py`,
  `jurisdiction_rule_status` in `test_shift_compliance.py`, and the all-vacant/state-block cases in
  `tests/huume/`.

### Fill vacant shifts (`week_builder.plan_vacant_fill`, 2026-09-07) — the server picks people

Why: after the guard (above) the assign path was SAFE but still not SMART — "fill the open lead shifts"
still meant the model naming a person per shift with no view of anyone's hours, and the guard then
refusing most of it. The fix is the design rule the week builder already followed: **the server picks
people; the model relays.** Nothing new is invented — `plan_vacant_fill` is `build_plan` + the compliance
preflight/replan loop pointed at the week's OPEN seats, and the result lands as an ordinary `edit`
proposal so the guard, the pill, the confirm turn and the audit row are the ones every other path uses.

- **`build_plan` policy guardrails + fairness** (shared with the whole-week builder): a second shift the
  same day (`policy: second shift that day`, relaxed by `allow_split_shift=True` — which also stops the
  rest rule from firing between the two halves of that split day, never between days), under
  `POLICY_MIN_REST_HOURS` rest against adjacent windows (`policy: less than 8h rest`), and
  `POLICY_MAX_CONSECUTIVE_DAYS` when the profile has no `max_consecutive_days`. They are HARD skips here
  (a planner that stacks the only lead onto every lead block is the failure this exists to stop), with
  the `policy:` prefix in `unfilled.exclusions` so law/eligibility and operational defaults stay
  distinguishable. `candidate_score` puts `shift_count` before `minutes`, so with equal target status the
  person with fewer shifts wins — two leads split seven blocks 4/3 instead of 7/0.
  The roster loader also returns `adjacent_assignments`, looking backward and forward by the largest
  applicable consecutive-day cap. These affect rest and consecutive days, never this week's minutes
  or fairness count. They ride the whole-week snapshot/hash so changes invalidate an older preview.
- **`_load_vacant_demand`** — same row shape as `_load_existing_demand`, but `status IN (draft,
  published)` (an assignment onto a published shift is a routine edit; `_apply_edit_ops` does it today),
  `HAVING COUNT(assignees) < required_staff`, optional `job_id = ANY`, `id = ANY`, `role ILIKE`. Current
  assignees ride as `fixed_employee_ids`. **No `_week_rules_gate`** on this path — the demand is the
  shifts that already exist; store hours/pattern are irrelevant (pinned by `test_fill_vacant.py`).
- **`plan_vacant_fill(conn, company_id, location_id, week_start, week_end?, job_ids?, role_hint?,
  shift_ids?, only_employee_ids?, exclude_employee_ids?, allow_split_shift)`** → `{status ready|clarify|
  refused, assignments[{shift_id, role, starts_at, ends_at, employee_id, employee_name, reason}],
  unfilled[{shift_id, role, starts_at, ends_at, reason, exclusions}], hours_by_employee, metrics,
  roster_size, demand_size, jurisdiction}`. `role_hint` resolves through `resolve_job_by_name` first and
  falls back to an ILIKE on the free-text role. `only_employee_ids` is the old "put Dana on all of them"
  semantics done right: the planner refuses per slot with a reason instead of the model multiplying one
  name. Nothing is persisted here — that is what makes a REST preview a free simulation.
- **Huume tool mode** — `propose_schedule_change(fill_vacant_shifts=true, fill_job_name?, fill_shift_ids?,
  to_employee_name? [only that person], exclude_employee_names?, allow_split_shift?)`.
  `schedule_skill._fill_vacant_requests` plans, turns `assignments` into plain `assign` edit requests and
  the SAME `build_edit_proposal` stages them; `unfilled` is merged into the `ScheduleReview`, echoed on
  the stage turn (`unfilled_count`), and rendered as an "Unfilled:" line in the state block. Zero
  assignments ⇒ a clarify that names the top reasons per seat. The prompt's "Staffing rules" paragraph
  routes every "fill / staff / cover the open shifts" ask here and forbids the model choosing names for
  a fill. `all_vacant_shifts` stays as the literal "one named person on every open shift" path.
  Both REST and Huume use `vacant_fill_edit_requests`: it preserves the selected employee UUID and
  refuses more than `MAX_BATCH_OPERATIONS` seats with the existing day split before resolution or
  persistence. `_resolve_edit_ops` validates that UUID against the active tenant/location roster;
  equal employee names cannot change the choice or trigger a needless name clarification.
- **The model can see load** — `planning_inputs.build_planning_inputs` is ONE builder behind two readers:
  `get_schedule_overview` gains `roster_load` (`compact_roster_load`: per person jobs, availability
  state, scheduled minutes/shift count/days this week, time away, weekly cap, `allow_overtime`),
  `roster_truncated`, `open_slots`, `policy`, `jurisdiction`, `week_rules` (built once per overview, never
  fails it); the REST `planning-inputs` route returns the full shape (adds per-weekday `windows`, all
  caps, `profile` with operating hours + leader job names). `find_coverage_candidates(statuses=…)` lets the
  schedule surface see drafts (channel default stays published-only, SQL byte-identical) and every
  candidate carries `also_suggested_for` (the other shifts that day the same free person was suggested
  for), so taking both suggestions is a choice, not a surprise double.
- **REST backbone** (`routes/employee_schedule/planning.py`, mounted under `/employee-schedule`, feature
  `employee_schedule`, location authz `assert_manager_location`): `GET /locations/{id}/planning-inputs
  ?week_start=`; `POST /locations/{id}/fill-vacant/preview` (`FillVacantPreviewRequest`) → plan →
  `build_edit_proposal(surface="editor", channel_id=None, shift_statuses=(draft, published))` persists
  ONE `schedule_chat_proposals` row for the CALLER whose `parse` carries `editor_location_id` /
  `editor_week_start` / `label` (the doc itself has no location or week; apply reads them back) →
  `{status ready|empty|clarify|refused, proposal_id, pill_text, review(+unfilled), label}`;
  `POST /fill-vacant/{proposal_id}/apply` — creator-only (403), `status='proposed'` (409),
  editor/edit only (400), `execute_edit_proposal` with the week bound from the parse, claim error → 409,
  scope error → 422, returns `touched_shift_ids`; **no `force`** (agent/planner paths never force);
  missing or malformed saved scope → 400 and a request to preview again (including legacy Huume
  editor rows with no saved scope). Location authorization is unconditional before execution.
  `DELETE /fill-vacant/{proposal_id}` → 204 (409 once spent). Each preview is one scenario and the
  proposal row is its handle — the Schedule Pilot workspace (PR4) builds its scenarios strip on exactly
  this. Client: `api/employees/employeeSchedule.ts` (`fetchPlanningInputs`, `previewFillVacant`,
  `applyFillVacant`, `cancelFillVacant`) + `types/employeeSchedule.ts` (`ScheduleReview`,
  `PlanningInputs`, `FillVacant*`) only — no UI in this PR.
- Tests: `test_week_builder.py` (policy refusals, split-shift relaxation, rest, consecutive default,
  4/3 fairness, shift-count-before-minutes, single lead ≤1/day), `test_fill_vacant.py` (narrowing,
  exclusions, replan on a compliance block, role-hint resolution, no rules gate, demand SQL),
  `test_planning_inputs.py`, `test_planning_routes.py`, `test_coverage.py` (statuses,
  `also_suggested_for`), `test_schedule_assistant_context.py` (`roster_load`, built once, never fails
  the overview), and the `fill_vacant_shifts` cases in `tests/huume/`.

### Batched schedule corrections (`schedule_chat_proposals.proposal.kind='batch'`, 2026-09-06)

One clarified correction is one confirmation. `propose_schedule_change`'s
`changes` array takes cancellations, edits AND `kind: create` replacement
shifts together, bounded by `schedule_batch.MAX_BATCH_OPERATIONS` (40 — a
module constant, not a tenant setting: the cap protects the reviewer, and the
tool schema `max_items`, the system prompt copy and the refusal all import the
same number so they cannot drift). `schedule_chat.build_batch_proposal`
resolves BOTH halves before anything persists — `_resolve_edit_ops` and
`_resolve_create_shifts` are the old builder bodies with persistence lifted
out; `build_edit_proposal`/`build_proposal` are now thin wrappers over them —
then writes ONE row `{kind:'batch', edit:{ops}, create:{shifts,location,…},
operation_count}`. A clarify from either half is returned with
`proposal_id=None` and nothing written, so a batch can never be confirmed with
a create the manager never saw resolved. The create half receives the edit
half's cancelled `shift_id`s as `ignore_shift_ids`: those drafts still exist
at stage time, and without it the busy/conflict pre-filter keeps everyone on
the old draft off its own replacement.

`execute_batch_proposal` is one claim + one transaction: `_apply_edit_ops`
(cancels and edits, the two-phase removal/addition write unchanged) THEN
`_apply_create_shifts`, so a replacement's conflict check runs after the
draft it replaces is already cancelled. Per-op refusals inside either half
are reported, not raised (same contract as the single-kind executors — a
stale op shouldn't veto the rest of a reviewed batch), but anything that DOES
raise (`ProposalScopeError`, the claim, an unexpected error) rolls back both
halves; `_create_scope_error` is checked before the claim too, so an
out-of-week replacement never cancels anything. Audit: each half keeps its own
`schedule_chat.edit_confirm` / `schedule_chat.confirm` row with the batch's
`proposal_id`, plus one `schedule_chat.batch_confirm` summary. The review
pill (`batch_proposal_text`) lists every op, every new shift with its
assignees/open slots and verbatim advisories, a per-day "After this:" net
(`schedule_batch.net_per_day`), and exactly one confirm line.

Over the cap, `huume/schedule_skill._coerce_tool_batch` refuses BEFORE any
resolution with `schedule_batch.split_plan_message`: the real total, the cap,
and the smallest day-contiguous split (`plan_batches` — a day's cancellations
and its replacements are never separated; a single day over the cap is
flagged "split that day by kind"). Never a silently staged prefix: the pill
must equal the ask. The one-staged-action-per-turn rule and the two-turn
confirm are unchanged — the batch IS the one action. Channel `@huume` still
uses the single-kind builders; `_MAX_EDIT_REQUESTS`/`_MAX_SHIFT_REQUESTS`
there bound the Gemini parse, not this path.

### Per-location scheduling profile (migration `schedloc01`)

`schedule_location_profiles` (one row per `business_locations` row) is where a
store's own setup lives: `operating_hours` JSONB, `default_week_template_id`,
`leader_job_ids` (+ its `leader_job_id` mirror), `notes`, `week_start_weekday`,
and (migration `schedloc02`) `open_buffer_minutes` / `close_buffer_minutes`. `services/scheduling/
location_profile.py` owns it; `routes/employee_schedule/location_profile.py`
is the hand-editable REST twin of what Huume interviews for
(`services/huume/schedule_profile_skill.py` — see `services/huume/CLAUDE.md`).

**Why it exists:** the whole-week builder derives demand from draft shifts or a
saved week template and nothing else, so a store with an empty week and no
template could not be built at all — the manager just got told to go make one
by hand. The profile is the answer Huume collects once and the builder reads
forever after.

Invariants:

- **No week is built until the rules are established** (migration `schedloc03`).
  `location_profile.missing_fields` is THE predicate — hours answered for all
  seven weekdays with at least one open day, a default template carrying
  blocks, and an answered leader question — and `week_builder._week_rules_gate`
  turns it into the refusal `week_rules_refusal` writes. It runs in
  `propose_week_draft` (before demand resolution: draft shifts are demand, not
  bounds), again in `apply_week_draft` (rules can be edited away between
  staging and confirmation), and as the FIRST entry in
  `get_week_build_readiness`'s `blockers` — readiness saying "ready" and the
  builder then refusing is the loop this surface exists to end. The prompt no
  longer merely suggests the interview; the builder enforces it.
- **The leader rule is a SET (migration `schedloc04`).** `leader_job_ids UUID[]`
  is the rule — any ONE of those jobs on shift is lead coverage — and
  `leader_job_id` is a derived mirror of its first element, kept so the FK's
  `ON DELETE SET NULL` and pre-set readers still see a value. Only
  `upsert_location_profile` writes either and it always writes both
  (`leader_job_id=` is accepted as the one-element spelling; the set wins when
  both arrive — including an explicit `leader_job_ids: null`, which clears the
  rule, so the ROUTE's per-job validation keys on the field being present and
  not on its truthiness or it would bless a job the write throws away). The
  CHECK accepts EITHER spelling (`cardinality(leader_job_ids) > 0 OR
  leader_job_id IS NOT NULL`) — the same thing `profile_leader_job_ids` reads,
  and what keeps the pre-swap image, which writes only the scalar, from taking
  a 422 on every leader save for the length of a deploy.
  The Huume interview still names one job and REPLACES
  the set; extending the tool to several names is the open follow-up.
- **A deleted job leaves the array behind, so the delete has to sweep it.**
  Nothing can FK-null an id INSIDE a `UUID[]`. `load_profile_bundle` and
  `week_builder._coverage_profile` therefore drop unresolvable ids on read —
  which is why `missing_fields` counts `bundle_leader_jobs(bundle)` (the
  resolved list) and never the raw array: reading the array made a rule whose
  only job had been deleted pass the week-rules gate while the evaluator,
  seeing an empty set, emitted no `leader_absent_*` findings at all — a green
  gate over a week nobody checked. `routes/employee_schedule/jobs.py:delete_job`
  calls `location_profile.detach_job_from_leader_rules` BEFORE the delete (after
  it, the FK has already nulled the mirror), which removes the job from both
  spellings and un-answers `leader_required` for any store left with nothing to
  lead with — `true` with nothing named is the one state the CHECK refuses, and
  the interview asks again rather than the rule silently evaporating.
- **A finding's `job_name` is a job's name, never prose.** The coverage
  evaluator emits ONE `leader_absent_*` finding per check for the whole set —
  never one per eligible job — and the readable "Shift Lead or Assistant
  Manager" (`join_or(names)`) belongs to `detail`. `job_id`/`job_name` are
  filled only when exactly one job is eligible; the set rides in `job_names`,
  a key `make_finding` puts on EVERY finding. Findings are persisted verbatim
  into `schedule_generation_runs.proposal`, so a sentence parked in `job_name`
  outlives the run that wrote it.
- **`leader_required` is tri-state, and that is why it is not just
  `leader_job_ids`.** `NULL` never asked, `false` no lead needed, `true` names
  at least one job (DB CHECK, on either spelling of the set). Without the explicit `false` a store that needs no lead
  could never finish setup, so the gate would block it forever. Both surfaces
  can answer it: the interview passes `leader_required`, the Week setup pane
  has a "No leader required" toggle distinct from an unanswered one — and a
  "Yes" with every job un-picked saves as unanswered (`leader_required: null`,
  `leader_job_ids: []`) rather than as the state the CHECK refuses.
- **A retracted leader rule has to give back both halves.** `true` names a job
  AND materializes `<Job> coverage` demand into the default template
  (`schedule_profile_skill._leader_blocks`). A later `false` therefore clears
  the leader set too — otherwise `_coverage_profile` keeps emitting leader
  gaps and `profile_context_lines` keeps saying a lead is required — and strips
  the generated coverage back out for EVERY saved leader job
  (`_strip_leader_coverage`, matched on the generated name AND the job, so a
  manager-written block on a lead job survives). `upsert_location_profile` is symmetric for the same reason:
  naming the job answers the question, clearing it un-answers it rather than
  leaving `leader_required=true` with nothing named — the one state the CHECK
  refuses.
- **`hours_answered` wants all seven weekdays, so existing rows need the
  backfill.** Both the old pane and the old interview wrote only the days
  somebody mentioned, which is every already-configured location. `schedloc03`
  fills the absent days in as closed for any row that already opens at least
  once; a row with no open day is genuinely unanswered and left for the
  interview. Skipping it does not fail loudly — it refuses every week build and
  flips `schedule_automation.generate_review_suggestion` to `not_ready`.
- **The default template is always location-scoped.** `_list_templates` also
  returns company-wide rows (`location_id IS NULL`); one of those as a store's
  default would let another store's edits rewrite this store's week. Both the
  service (`replace_default_pattern`) and the route enforce it.
- **`propose_week_draft`'s auto branch prefers the default** over the
  exactly-one-usable-template rule, and `get_week_build_readiness` drops the
  "choose which template" blocker when one exists. A default with zero blocks
  is not an answer and still clarifies.
- **`operating_hours` has three states per weekday, not two.** A key with a
  window means open, an explicit `null` means closed, and an ABSENT key means
  nobody has said yet. Collapsing the last two makes Huume stop asking.
- **Writes from the chat surface are partial by nature.** The interview asks
  one question per turn, so `schedule_profile_skill.resolve_profile_args` merges
  its answer onto the stored profile before staging, and `upsert_location_profile`
  is only handed the fields that carry a value. An empty `operating_hours` or a
  blank `notes` is "unsaid", not "cleared" — the REST pane is the surface that
  can clear a field, by sending it explicitly.
- **`week_start` must BE the location's week start.** `template_windows`, the
  seven-day demand load and the editor grid all treat it as day one, so a
  Sunday date for a Monday-start store plans a window matching no grid anyone
  can see. `week_builder._misaligned_week` refuses (naming the aligned date)
  in both `propose_week_draft` and `get_week_build_readiness`; the assistant
  session and the automation-rule route gate their own weeks the same way.
- **The chat surface maps blocks onto ids by `(name, start, end)`** before
  calling the id-based reconcile core, so a re-save keeps existing block ids
  and the generated shifts that point at them keep their template link.
- **Week-template create/reconcile live in
  `services/scheduling/week_template_writes.py`**, not in the route — the route
  keeps auth/audit/serialization and maps `WeekTemplateNotFound`→404,
  `JobUnavailable`→422. Services raise `ValueError` subclasses and never
  `HTTPException` (same rule `shift_writes.py` follows).

### Week coverage + break relief findings (`services/scheduling/schedule_coverage.py`)

The planner answers a headcount question and stops: fill each block to its
`required_staff`. It reports 20/20 and a manager reads that as done — while the
week may have nobody in for the open, nobody on for the last hour, and nobody
who can relieve a solo barista for a legally required meal. `evaluate_week_coverage`
is the pure check the planner does not do (no DB, no shift ids), and
`week_builder._break_relief_findings` is its break-time counterpart, running the
pure `schedule_break_stagger.stagger_shift_breaks` over the IN-MEMORY plan.

Both emit the one `make_finding` shape onto `plan["findings"]`, with
`metrics.finding_counts` / `gap_count` / `operating_hours_known` beside it.

Invariants:

- **Findings live on the PLAN, not on `review`.** `schedule_assistant_session.
  _automatic_action` rebuilds the staged action from `proposal["unfilled"]` and
  never reads `review`, so anything parked there is invisible on exactly the
  automatic runs nobody is watching.
- **The profile is deliberately NOT in the planning snapshot.** `_input_hash`
  hashes the snapshot, so a manager fixing a buffer minute would otherwise
  stale an otherwise-good proposal at confirm time. `_coverage_profile` is read
  in `propose_week_draft` and in readiness, never in `_planning_snapshot`.
- **Severity is `gap | advisory`, never `block`.** `block` already means
  "cannot be staged" (`_preflight_compliance`, `check_shift_compliance`),
  and nothing here prevents staging: a manager may knowingly run a thin close,
  and the answer is to say so, not to refuse. A generated week with holes is
  still `ready` and still needs the same explicit confirmation.
- **The summary never contains the word "compliant".** `_coverage_sentence` has
  three endings — gaps found, none found, or hours not saved so nothing was
  checked. "No gaps" and "I could not look" must never read the same.
- **Published shifts are a coverage baseline.** A half-published week is the
  common state; judging the proposal alone reports days that are genuinely
  staffed as empty. Unfilled slots, by contrast, count for nothing — the whole
  point is that a hole the planner could not fill is still a hole.
  (`headcount="required"` is the readiness variant: it judges the PATTERN,
  before anyone is assigned to it, and its `pattern_findings` are reported
  WITHOUT becoming blockers — a hole to fix in the interview is not a refusal
  to build, which is the dead end this surface exists to end.)
- **`coverage_shortfall` fires on nearly every real shift**, because a shift
  staffed to exactly its requirement has no spare cover. It is split by crew
  size: solo → `break_relief_uncovered` (a gap — the floor empties), otherwise
  → `break_relief_thin` (advisory, capped per day in the LIST by
  `_trim_thin_findings`, uncapped in `finding_counts`). Trimming before counting
  would make a week look cleaner the busier it is.
- **Break rules come from the catalog, buffers are policy.** `resolve_break_rules`
  takes a pg advisory lock per call, so `schedule_guidance.resolve_week_break_plans`
  hoists it to one call per local DATE (≤7 a build) and batches DOB + waivers.
  An `unmapped` date becomes one `break_rules_unmapped` finding — a state with
  nothing in the catalog is surfaced, never silently green. A plan that could
  not be evaluated for ONE person (no DOB against age-specific rules) never
  reaches that aggregate: it places no slot, so the coverage advisories go
  quiet too, and without `break_rules_unresolved` (one per person per shift,
  suppressed on an already-unmapped date) a solo shift owing a meal break would
  report nothing at all. The buffer minutes and the 15-minute sampling slice are
  operational policy in feature code and say so in their docstrings (memory:
  `feedback-legal-thresholds-codify`).
- **The findings pass never fails a build**, independently of the assignment
  preflight (which fails closed per proposed pair). `_attach_findings` guards
  profile/coverage/break evaluation as a whole; a jurisdiction lookup failure
  is handled inside the pass so already-computed coverage and break findings
  survive while legality is marked `unavailable`. If coverage evaluation itself
  fails, metrics say it was not checked and `_coverage_sentence` reports that —
  never a clean week.
- **Every findings cap is by severity, not calendar order.** The list is sorted
  day-then-time, so a plain slice would drop Saturday's gaps to keep Sunday's
  advisories. `_cap_findings` gives gaps the budget first and re-sorts, and it
  is what all three truncation points use — the persisted `_MAX_FINDINGS` list,
  the `_FINDINGS_RETURNED` one echoed to the model, and readiness
  `pattern_findings`.
- **Times stay wall clock.** Shift timestamps are UTC-tagged wall clock and are
  compared against `operating_hours` as clock faces; converting would move an
  early shift onto the previous day. An overnight window (`close <= open`) is
  one window, not two holes.

### Week builder hardening (2026-09-07) — advisories surfaced, replans checked, load named

Why: on the one path where the server already picked people, the builder still discarded every
statutory advisory at both boundaries (`_preflight_compliance_blocks` kept only `block`; apply did the
same), sent the final rebuild out UNCHECKED when the replan budget ran out, swallowed a per-pair
preflight exception as "fine", never validated the `fixed_employee_ids` it inherited, and reported
"18/18 positions filled" for nine shifts on one person. A TX week was indistinguishable from a CA week.

- **`_preflight_compliance(conn, company_id, location_id, plan) -> (blocked, advisories)`** replaces
  `_preflight_compliance_blocks`. Advisories are returned per `(shift_key, employee_id)` verbatim
  (`check`, `message`, `statute`, `state`) and persisted on each `proposed_assignment["advisories"]`
  by `_attach_advisories`. **Fails closed per pair**: a checker that raises marks that pair blocked
  (logged) instead of letting it through. Passes `fw_event="assign"` (drafts: `fw_shift_published=False`)
  and prefetches `fetch_lapse_items` ONCE for everyone proposed (feature flags via
  `get_company_features(conn=conn)`); if the prefetch fails, `lapse_items=None` and the checker queries
  per call — only the batching is lost.
- **`_plan_with_preflight(conn, …, build)`** is the loop both `propose_week_draft` and
  `plan_vacant_fill` use: build → preflight → replan around blocks, up to `_MAX_COMPLIANCE_REPLANS`
  more times, and **the plan handed back was always checked**. When the budget runs out with a block
  still in it, `_strip_blocked_pairs` removes that pair, books it as `unfilled` with reason
  `compliance or eligibility block`, and fixes `metrics`/`hours_by_employee` — a manager is never shown
  a seat filled by someone the gate refused.
- **New findings** (`_attach_findings_core`, same `make_finding` shape, counted in full in
  `finding_counts`):
  - `staffing_concentration` (advisory) — one person on ≥ `_CONCENTRATION_MIN_SHIFTS` (7: more shifts
    than days) OR on ≥ 3 shifts that are > 40% of the staffed positions AND ≥ 2× their expected share
    across each shift's eligible pool. Fixed assignments count too. Two qualified leads on 4/3 of seven
    gated blocks stay quiet even alongside an ineligible barista roster; a one-person eligible pool is
    never flagged by share (the absolute 7-shift rule still applies).
  - `existing_double_booking` (**gap**, added to `GAP_KINDS`) — an inherited `fixed_employee_ids`
    booking that overlaps another of theirs (in the plan or elsewhere that week). Still counted as
    filled; the finding is how the manager learns.
  - `compliance_advisory` (advisory) — one per assignment × advisory, `"{name}: {message} ({statute})"`,
    on the shift's day/window. `_trim_thin_findings` caps the LIST at `_MAX_COMPLIANCE_ADVISORY_FINDINGS`
    (5); the count and the review keep every one.
  - `jurisdiction_unmapped` / `jurisdiction_unavailable` (advisory, once) — from
    `jurisdiction_rule_status`; `plan["jurisdiction"]` carries the `jurisdiction_message`. The default
    before the pass runs is `unavailable` ("not an all-clear"), so a findings pass that fails never reads
    as verified.
- **`metrics.top_load`** — top 3 `{employee_id, name, shifts, hours}` heaviest first. The summary adds
  "{name} carries N of the M staffed positions." when concentration fired, and the jurisdiction
  sentence when not verified. Still never the word "compliant".
- **The week-draft `ScheduleReview`** — `schedule_review.build_week_draft_review(plan, employee_names,
  existing_assignments, week_start, week_end, proposal_id, concentration_findings)` → `kind="week_draft"`: `assignments`
  (verdict `warn` when an advisory is attached), `rejected=[]` (the planner refuses before proposing),
  `unfilled` (with `ends_at` looked up), `employees[before/after/warnings]` (the concentration finding
  is the person's warning), `advisories` verbatim, `findings`, `jurisdiction`, `compliance_status`.
  Persisted as `proposal["schedule_review"]` (the older `proposal["review"]` summary/preview payload is
  unchanged) and returned as `review` + `compliance_status` + `jurisdiction`, which `agent.py` merges
  into the staged dict — so the Schedule Pilot review pane renders a week draft and a schedule change
  with one component.
- **`apply_week_draft`** re-checks with `fw_event="assign"` and `fw_shift_published` from the live row,
  keeps the non-block violations of what it applied as `advisories_acknowledged` (returned, and on the
  `schedule_generation.apply` audit row with `compliance_status` + `jurisdiction`), names each dropped
  assignee with role/time/reason in the message ("Left open after current-state rechecks: …", first 5),
  adds a "Heads up on what was applied — …" line (deduped, first 3), and repeats the not-verified
  sentence "… You confirmed with that in view." when the state's law was not evaluated.
- Client: `HuumeActionScheduleWeekDraft` gains `metrics.top_load`, `review`, `compliance_status`,
  `jurisdiction`; the banner appends ", {name} on N shifts" when concentration fired and
  " — compliance NOT verified"; the card shows a "Heaviest load" row and labels the new finding kinds.
- Tests: `test_week_builder.py` (one-lead-holder end to end, two leads unflagged, solo roster unflagged,
  inherited double-booking gap, advisories on assignment/findings/review, list cap vs count, budget-spent
  strip, unmapped state, failed pass ⇒ unavailable, `_preflight_compliance` fail-closed + lapse batching
  + fallback, apply naming dropped/acknowledged/not-verified), `test_schedule_review.py`
  (`build_week_draft_review`), state-block cases in `tests/huume/test_huume_week_builder.py`.

### Per-location week start day

`week_start_weekday` (0=Sunday … 6=Saturday, Sunday-indexed like every other
weekday integer here) replaces the Sunday-start convention that used to be
open-coded in a dozen places. `schedule_rules.align_week_start(d, wsd)` and
`week_day_offset(weekday, wsd)` are the DB-free helpers; both default to 0, so
a location with no profile behaves exactly as before.

**A weekday index is not a day offset** unless the week starts on Sunday.
Anywhere a weekday is added to a week start, it goes through `week_day_offset`
first — `schedule_chat_rules.resolve_dates` is where that was actually wrong.

Threaded through: `schedule_chat_rules.resolve_week`/`resolve_dates` (resolved
after the location, which is why the lookup sits mid-function in
`schedule_chat.build_proposal`), `coverage.find_coverage_candidates`,
`shift_compliance._week_window`/`_week_hours` (which owns resolving its own
anchor — the window and the hours must agree about which seven days they
mean), `schedule_intelligence._employee_weekly_hours` (per employee via
`employees.work_location_id` — bucketing a Monday-start store on Sundays
manufactures the volatility that metric exists to detect),
`schedule_automation.target_week_start`, and `time_off_guard` (joined per
shift on its own `location_id`, never one company-wide constant).

Deliberately NOT converted: `pilots/analysis_platform_sources._week_start`, a
company-wide 26-week trend rollup that has no single correct anchor when a
tenant's stores differ — documented in place. `template_windows`, the
availability weekday keys, `resolve_day_hint`, and the migrations'
`BETWEEN 0 AND 6` checks are weekday-INDEX code and were untouched.

The alignment gate lives in the routes that own a location:
`get_or_create_schedule_assistant_session` and the auto-schedule upsert both
422 a misaligned week. `ScheduleAutomationRuleUpsert` no longer asserts
"must be a Sunday" — the payload does not carry a location, so it cannot know.

### Automatic weekly suggestions (migration `empsched18`)

`schedule_auto_generation` is the review-only Celery sweep for the upcoming
editor week (anchored on each location's own `week_start_weekday`). Migration
`empsched19` REPLACED the tenant-wide sweep with per-location
`schedule_automation_rules` rows carrying their own `next_run_at` — it deletes
the global `schedule_auto_generation` scheduler row the earlier migration
seeded. Each location still requires the merged `employee_schedule`, `huume`,
and `matcha_work` feature flags. The worker uses existing draft shifts
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

**Employee shift scheduling** over the existing roster. Admins build/publish shifts (date/time, role, location, break, required headcount), assign employees, and generate weeks from reusable **shift templates** (time-of-day + weekday mask → concrete dated shifts via `POST /employee-schedule/week-templates/{id}/generate`); employees view their published shifts and file **swap / drop / unavailability** requests that admins approve/deny. Tables `schedule_shifts` / `schedule_shift_assignments` / `schedule_shift_templates` / `schedule_requests` / `schedule_audit_log` (migration `empsched01`), all `company_id`-scoped; assignments/requests reference `employees` (`org_id`) and `business_locations`. Gates the `/employee-schedule` router (`routes/employee_schedule/` package), the portal `/v1/portal/me/schedule*` endpoints, and the `/app/employee-schedule` page + portal Schedule tab. Pure rules (who is schedulable, week bounds, template→shift windows, PATCH builder, the two forceable 409 shapes) live in `services/scheduling/schedule_rules.py` — DB-free, so they're unit-tested without a database. Four invariants: **double-booking is guarded on every write path** (create, assign, swap-approval, **and retime** — each 409s with `code: schedule_conflict` and takes `?force=true`; a headcount overrun 409s the same way with `code: shift_full`); **cancelled is terminal** (PUT can't flip a cancelled shift back to published — `POST /publish` already refused it, and a resurrected shift reappears on every assignee's portal); **only the fields the caller sent are written** (`build_patch` over `model_fields_set`, so an explicit null clears a nullable column — COALESCE read "unset" and "clear me" identically); and **nobody who has left stays schedulable** (`INACTIVE_EMPLOYMENT_STATUSES` = terminated + offboarded — the status vocabulary is `employees/crud.py:VALID_EMPLOYMENT_STATUSES`, and a test reads it from source to catch drift). `schedule_audit_log.details` is enriched (before/after shift state, `was_published`, employee-initiated markers on request-approval churn) specifically so `schedule_intelligence` can compute off it — see that flag for the analytics layer. **Linked to `training`** (migration `trainsched01`, gated on the company's own `training`/`credential_templates` flags — silent no-op otherwise): assignment-time lapse advisories, `scheduled_role` auto-assign rules, and `kind='training'` shifts — see the `training` row for the full wiring. **Recurring weekly availability** (table `schedule_employee_availability`, migration `empavail01`): an employee with zero rows is fully available (back-compat default); ≥1 row means a weekday with no rows is unavailable and a weekday with rows is available only inside those windows. `services/scheduling/schedule_rules.availability_violations` is the pure DB-free check; a violation raises the same forceable-409 family as a conflict (`code: outside_availability`, `?force=true`) on create/retime/assign/swap-approval, and in `schedule_chat` an unavailable candidate is pre-filtered out of proposal ranking while an unavailable assignee at execute time is dropped with a reason (same convention as a scheduling conflict there — never a hard failure). Editable by the employee (`GET/PUT /v1/portal/me/schedule/availability`) or an admin on their behalf (`GET/PUT /employee-schedule/availability/{employee_id}`), both full-replacement PUT semantics. **Shift duplication** (`POST /employee-schedule/shifts/{id}/duplicate`): copies a shift onto other calendar dates as drafts, preserving time-of-day/duration (`schedule_rules.shift_window_on_date`); follows the bulk-create convention of `generate_from_template` and `schedule_chat.execute_proposal` — never a per-date 409, a conflicting or unavailable assignee is dropped per-copy and reported in the response's `dropped` list rather than blocking the whole call. **Channel-default location** (migration `oploc01`): a `@huume` schedule request in a channel bound to a `business_locations` row (`channels.location_id`) defaults to that store when the message names no location — `schedule_chat_rules.apply_channel_default_location` skips the "Which location?" clarify round entirely. An explicit location hint in the message always wins, even naming a different store; a channel bound to a deactivated location falls through to the normal match/clarify path. **Coverage suggestions** (`services/scheduling/coverage.py:find_coverage_candidates`) — a standalone extraction of `schedule_chat.build_proposal`'s candidate-assembly steps (busy filter, availability filter, week-hours ranking, lapse annotation), consumed by channel `@huume`'s `find_shift_coverage` tool (`services/ems/channel_grounding.py:run_coverage_lookup`) to answer "who can cover for X" without going through proposal-building; read-only, no compliance check (that's the assignment path's job). **Chat-driven shift EDITS** (2026-08-04): `schedule_chat` is no longer create-only — `parse_schedule_request` returns an `action` discriminator (`create`|`edit`), and an edit routes to `build_edit_proposal` → `execute_edit_proposal` through the SAME propose/confirm pill machinery (`schedule_chat_proposals`, `confirm_message_id` claim, 7-day guard, clarify cap); `proposal["kind"] == "edit"` is what `channels_ws._bg_schedule_reply` dispatches on, so there is **no new table and no migration** — the kind rides in the JSONB doc. Six op kinds: `reassign` / `assign` / `unassign` / `retime` / `cancel` / `swap`. Two people named ("give Cara's shift to Casey and Casey's to Cara") parse as TWO `reassign` ops; two SHIFTS named with no people ("swap the opener and the closer") parse as one `swap` op that exchanges both rosters. **`execute_edit_proposal` is two-phase inside one transaction** — every removal first, then every addition — which is what makes a same-window swap correct without swap-specific conflict handling: by the time op 2's `find_conflicts` runs, op 1's removal already happened, so neither person reads as double-booked against the shift they are leaving. Phase-1 removals for `reassign`/`unassign` are staged via `remove_assignment_core(..., write_audit=False)` and the assignment row kept in a `removed[idx]` map; phase 2 either commits the deferred `assignment.delete` audit row (op succeeded) or undoes the removal with `shift_writes.restore_assignment_raw` (op refused — a conflict, a now-full shift, an availability/compliance block, or the shift going cancelled underneath it) — so a refused reassign never leaves the shift a person short, and a refusal never emits the delete/create audit pair `fair_workweek.RELEVANT_ACTIONS` would otherwise double-count as churn. The `swap` kind stays self-contained (both removals + both additions in its own branch, since which people move is only knowable by reading both rosters live), but checks both directions' conflicts BEFORE either side is removed (excluding each person's own outgoing shift from their own conflict check) — a blocked swap costs zero writes, not a remove-then-restore round trip. `unassign`/`reassign` also refuse (rather than silently no-op) when the phase-1 delete matched zero rows — the person wasn't actually on the shift — so that case can't emit a phantom `assignment.delete`. `assign`/`reassign`'s confirm-time re-check now also enforces `required_staff` (a full shift refuses, matching the REST route's `shift_full` 409) alongside conflict/availability/compliance. Writes go through four shared cores in `shift_writes.py` (`apply_assignment_core` / `remove_assignment_core` / `retime_shift_core` / `cancel_shift_core`) extracted from the route handlers for exactly the reason `create_shift_core` was — `werk → matcha.routes` must stay 0. **The cores reuse the existing audit action names verbatim** (`assignment.create` / `assignment.delete` / `shift.update`): `fair_workweek.RELEVANT_ACTIONS` matches on those four strings, so an invented name like `shift.chat_retime` would be silently invisible to Fair Workweek dollar exposure and the pretext shield; `remove_assignment_core` never writes that audit row on a zero-row delete regardless of caller. Chat-driven edits deliberately count as EMPLOYER-initiated churn (no `schedule_requests` row inside `schedule_intelligence_stats`' 120s window) — a manager typed them, so that is honest. Every op re-runs conflict/availability/compliance against CURRENT state at confirm time and is dropped with the violation quoted rather than failing the batch (`execute_proposal`'s convention). Ad-hoc shifts now persist the manager's own label as `role` when they named no explicit role — without it "opener" was lost at the DB boundary and nothing could find the shift again by what it was called; `_resolve_shift_ref` additionally retries without the role filter before giving up, and an ambiguous match lists candidates **with their assignees** (two same-role, same-window shifts otherwise render as identical, unpickable options) — before falling back to that listing it also narrows by `target_time_hint` when the hint parses to an unambiguous clock time (`schedule_chat_rules.parse_time_hint` — "8am"/"8:30pm"/"08:00"/"20:00", never a bare "8" with no am/pm), so "the 8am shift" resolves directly instead of always clarifying. **Job-derived role labels** (2026-09-02): a shift's `role` is no longer free text a caller chooses — `shift_writes.create_shift_core` overwrites it with the job's current name whenever `job_id` is set, so the REST route, chat confirms and week generation cannot disagree about what a shift is called (a job that isn't the company's degrades to the caller's own label rather than raising, matching `check_job_qualification`'s treatment of a stale id). `ShiftCreate.job_id` is REQUIRED — the manual create form picks a company job, never types a label — while `ShiftUpdate.job_id` stays optional and mirrors the name into `role` on the way through, including to NULL (clearing the job clears the label; a kept label would describe a job the shift no longer has). The free-text paths converge through `shift_writes.resolve_job_by_name`: a manager typing "@huume add an opener Tuesday", or a legacy template block with a role and no job, resolves that label to a real job when one matches (location-scoped wins over company-wide) and stays free text when none does — refusing would break a working conversational flow. `assert_job_in_company` is the scope guard: a location-scoped job is refused on any shift/block at a different location **and on a location-less one**, `location_id` omitted means "this caller has no location to check against", and `lock=True` (FOR SHARE) is what actually stops a concurrent rename from persisting a stale name. **An empty qualified roster means UNGATED**: gating is opted into by naming who is qualified, not by the mere existence of a job — with a mandatory `job_id` on create, the other reading would 409 every assignment for any company that defines jobs but has not filled in the per-job lists yet. The rule holds in all THREE places qualification is decided, and they must not drift: `_shared.check_job_qualification` (every REST write), `schedule_profiles.fetch_effective_job_employee_ids` (chat assign/reassign/swap, coverage ranking, and `apply_week_draft`'s confirm-time recheck), and `week_builder._job_qualified` (the in-memory planner, which takes the company-wide `gated_job_ids` set `_load_roster_context` loads — a REQUIRED argument, since defaulting it either way hides a wrong answer). They were split for a while and it showed: the same manager could assign someone from the grid, be refused for that person in chat, and get a whole-week plan with every position open. Worse, a planner that ignored the rule while the confirm-time recheck honored it would build a full week and then drop every assignment as "no longer qualified" — so a fix to one of the three is a fix to all three. Migration `empsched20` is what makes the mandatory `job_id` survivable for existing tenants: it derives one job per distinct `role` label per (company, location) from `schedule_shifts` + `schedule_shift_templates`, gives a company that labelled nothing a single company-wide **General** job, then points every unlinked row at the job its label became and normalizes the label to that job's name. Set-based (TEMP plan table + LATERAL, `ORDER BY (location_id IS NULL), created_at, id` for the deterministic LIMIT 1), re-runnable, and its `downgrade` removes only jobs carrying the derived-note marker that nobody has qualified anyone on.

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

- **A suggestion is never the shift's own start time.** Most jurisdictions fix
  only a deadline, so the rule set carries no `earliest_offset_minutes` and
  `_build_slot`'s fallback envelope used to open at the shift's first instant —
  a 06:30–14:30 shift was told to break at 06:30. Two placement rules narrow
  that envelope: a statute-silent requirement does not start before
  `DEFAULT_PLACEMENT_FLOOR_MINUTES` (120), and nothing starts at the first
  instant even where a statute encodes an earliest of zero. Both are **policy,
  not law** — a real statutory earliest always wins in both directions, both
  yield to law and to coverage (next bullet), and `locked` times a manager
  saved are never re-judged against them. The two sit in different fields for a
  reason: `policy_earliest` is a preference placement may drop below, while
  `floor_earliest` bounds every tier, so spilling below the policy floor cannot
  walk all the way back to the shift's opening minute.
- **Placement policy is a preference, never a bound.** `_build_slot` keeps it in
  its own `policy_earliest` field beside the legal `earliest`, and
  `_candidate_starts` only *reorders* the legal window by it: allowed times
  first, discouraged ones after, closest-to-the-floor first. Narrowing the
  window instead is wrong twice — a short shift would gain a false
  `deadline_conflict` (guarded at build time), and, because breaks serialize
  when a shift carries no spare headcount, a window shortened by two hours
  holds four fewer of them, so a crew of 9 on a CA opener lost three lawful
  suggestions to `insufficient_coverage`.
- **Law and placement policy live in different places, on purpose.** California
  has no statutory earliest — § 512(a) and *Brinker* (2012) 53 Cal.4th 1004 fix
  only the deadline, and a first-hour meal is lawful — so
  `_SCHEDULING_RULES["CA"]["meal_break_earliest_after_hours"]` is an explicit
  `None`, not 2 hours. States that DO legislate an earliest (WA:
  WAC 296-126-092(1), 2h; OR: OAR 839-020-0050(2)(d), 2h/3h by work-period
  length) carry it as the `meal_break_earliest_after_hours` extraction key,
  which `schedule_break_rule_store._legacy_rules` turns into the requirement's
  `earliest_offset_minutes` (first meal only). Catalog rows behind that key:
  `scripts/seed/meal_break_timing.sql` — reference data the pilots and the law
  panel cite today; the extraction reads codified rows only and WA/OR are not
  codified yet (that pack's header has the detail).
- **`NO_CAP` is not a number, and `_legacy_rules` now sees it.** An approved
  extraction row with `no_rule=true` arrives as `schedule_compliance.NO_CAP` (a
  bare `object()`), so every threshold read goes through `_threshold` before
  `float()`; only the curated table used to reach those reads, and no meal key
  in it is ever `NO_CAP`.
- **Two thresholds that cannot both hold are reported, not enforced.** The
  earliest and the deadline are approved one row at a time and range-checked
  independently, so `earliest >= meal_break_after_hours` is reachable and
  describes a window no break fits in. `validate_extraction` rejects the
  earliest when its own run carries the deadline; `_legacy_rules` is the
  backstop for rows approved out of separate runs, keeping the deadline (the
  one whose breach is the violation) and emitting `break_rules_inconsistent`
  rather than a permanent unexplained `deadline_conflict` on every shift.
- **The legacy fallback merges approved catalog extractions.** For a state the
  curated table never covered, `resolve_break_rules` now calls
  `shift_compliance._approved_db_rules` so break timing comes from the same
  merged source the write-path gate enforces against; a failed read emits
  `break_rules_catalog_unavailable` rather than reading as "no rules here".
- **The concurrency budget floors at 1.** `assigned_count` can never exceed
  `required_staff` on a normal shift (assignment writes 409 `shift_full`), so a
  spare-headcount-only model would suggest nothing on every real shift. The
  floor is paired with a `coverage_shortfall` advisory — under-covering for 30
  minutes is the manager's call; hiding it is not.
- **The budget is a ceiling, not a target — stagger first, crowd last.**
  `_fit` returns the peak headcount off the floor during a candidate interval
  (`1` = nobody else), and `_choose_start` takes the first `1` anywhere in the
  legal window before it will double up, then the least crowded time, and only
  then a policy-discouraged one. Two openers on a 06:30 shift were both told
  08:30 because a third person clocks in then — lawful, in budget, and the
  wrong suggestion (the 2026-09-06 send-back).
- **The ceiling and the occupancy must describe the same floor.**
  `required_staff` is one row's, but `occupied` is the whole floor's, so a
  caller passing `occupied` passes `floor` too — a `FloorWindow` per co-planned
  row — and the ceiling is read from it at each instant (`_floor_spare`), which
  is how a mid-morning arrival widens it. Deriving it from the opened row
  instead compares a row-sized budget against a floor-sized occupancy: a row
  with no spare of its own would refuse every time a peer's break touches, on a
  floor with six people to spare. Without `floor` the ceiling stays the row's,
  correct for `week_builder`, which plans each shift in isolation. The floor of
  one lives on the ceiling, never on the spare count itself, so
  `coverage_shortfall` can still tell a committed floor from a spare one.
- **Coverage is the shifts that share floor time, not a calendar day.**
  `resolve_shift_stagger_plan` co-plans the target's overlap component
  (`_overlap_component`, widening the query up to `_CO_PLANNED_ROUNDS` times to
  follow the chain), in `(starts_at, ends_at, id)` order, feeding each earlier
  row's suggestions and every other row's saved times to the next as `occupied`
  — a separate input from `locked` so a peer's break is never mistaken for this
  row's saved answer (one employee on two rows has the same `(kind, ordinal)`
  twice in a day). Overlap is symmetric and a calendar day is not: a
  22:00–06:00 row and a 00:00–08:00 row share six hours of floor that no single
  day contains, and the overnighter used to be handed a time the morning crew
  had already saved. Only rows up to and including the target are planned (a
  later row cannot change what the target is offered, and its saved time
  occupies regardless), which also makes the returned zone the target's own.
- **A person is not two bodies.** `_fit` refuses any overlap with the same
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
