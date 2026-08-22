# Critique + remediation: Schedule Huume assistant surface

## Context

`c84f296` (branch `ops/scheduling-8-21v2`, PR #239) replaced the schedule editor's
narrow command parser with a durable, location-scoped Huume conversation, per
`SCHEDULE_HUUME_IMPLEMENTATION_PLAN.md`. The feature is already implemented; this
document critiques the plan against what actually shipped and lists the fixes.

**Verdict.** The security design is the strongest part — scoping, allow-listing,
and per-turn re-authorization all do what the plan says. But **three defects make
the four new staged actions non-functional**, and the digest ships with a
content-rendering bug plus no tenant filter. The plan's own verification block is
green-by-construction, so none of this was caught: three of its five backend
targets are pre-existing files the commit never touched, and its frontend target
is a now-dead component's suite.

---

## What the plan claimed and the code delivers

| Plan claim | Verdict |
|---|---|
| Tool allow-list confined to `SCHEDULE_TOOLS` | **Holds.** Declaration filter (`agent.py:1624`) *and* runtime guard as the first statement in `call_tool` (`agent.py:655`) |
| Scope re-derived server-side each turn, never client-supplied | **Holds.** Client sends only `thread_id`; `turn_pipeline.py:931-946` builds the context solely from the session row |
| Session owner must match caller every turn | **Holds.** `schedule_assistant_session.py:165` (404) + `_assert_manager_location` re-run per turn (`:167`). A demoted manager is cut off on the next message |
| Authorization model | **Holds.** `resolve_eligibility_manager_scope` gives admin/client every location, employee-manager only their own, plain employee none. 404 for existence, 403 for authz — correct codes |
| Per-turn cost bounds from the Aug-5 runaway-spend incident | **Holds.** `_MAX_SCHEDULE_PROPOSALS_PER_TURN` / `_MAX_TURN_PROMPT_TOKENS` / fingerprint dedupe survive the refactor (`agent.py:65-67`, `:1734-1753`) |
| Migration safe on existing rows | **Holds.** `surface VARCHAR(32) NOT NULL DEFAULT 'workspace'` is a PG11+ fast default, CHECK added after. Only child of `empsched08`; repo already runs 21 heads via `upgrade heads` |
| Digest scheduler row seeded disabled | **Holds.** `huumesched01:89-94`, double-gated at `celery_app.py:233` + `schedule_daily_digest.py:13` (fail-closed) |
| Writers re-verify location/assignment in their own transaction | **Mostly.** 3 of 4 correct; `record_meal_break_waiver_core` never checks the location belongs to the company (F9) |
| Panel never fabricates assistant content | **Holds.** Only the user's own echo is optimistic (`ScheduleHuumePanel.tsx:81-82`), replaced by the persisted `response.user_message` at `:91-93` |

---

## Tier 0 — blockers (the feature does not work as shipped)

### B1 — Staging an eligibility decision silently destroys the whole turn's state

`agent.py:1115` puts `case["expires_at"]` into the staged dict raw.
`schedule_eligibility_cases.expires_at` is `DATE NOT NULL`
(`empsched07:26`), so asyncpg hands back a `datetime.date`. `_json_safe` is applied
only to the *return payload* (`agent.py:1149`), not to `state_updates`. At turn end
`versions.py:38` calls `json.dumps(merged_state)` with no `default=` →
`TypeError: Object of type date is not JSON serializable` — swallowed whole by the
bare `except Exception: logger.exception(...)` at `turn_pipeline.py:1006-1007`.

Result: **the entire turn's `state_updates` are dropped** — not just `huume_action`
but any `huume_er`/`huume_records` written the same turn. The model says "staged,
reply confirm"; nothing persisted; the confirm turn finds no `pre_turn_action` and
re-stages. Infinite loop, no error visible to the user.

**Fix:** `"expires_at": case["expires_at"].isoformat()` — or run `staged` through
`_json_safe` before assigning, which also protects the other three new arms.

### B2 — The four new actions can never be confirmed: `confirm_id` never reaches the model

`prompt.py` has a per-type `build_state_block` branch for every staged type,
including `schedule_change` (`:190-194`). The four types this commit added —
`assignment_note`, `meal_break_waiver`, `work_permit`, `eligibility_decision` —
have **no branch** and fall to the generic `else` at `:206-207`, which prints the
type and omits `confirm_id`. They are also absent from the staged-tool list the
prompt recites at `:330`.

The stage-turn tool payload does carry `confirm_id` (`agent.py:1138`), but that
lives in the in-turn `contents` list and `huume_steps` metadata — not in the
persisted history the next turn reconstructs. So the model has no source for the
id, guesses, `agent.py:1058-1065`'s equality match misses, and the tool re-stages
while the model reports success.

This is the *exact* failure `services/huume/CLAUDE.md` already documents for
`schedule_change`, ending: *"Every other staged action type has this per-type
branch for the same reason; a new one needs it too, not just a registry entry."*

**Fix:** four `elif` branches in `build_state_block` naming `confirm_id`, plus the
four tool names in the `:330` list.

### B3 — Digest emails a serialized JSON blob instead of the guidance summary

`workers/utils.py:28-35` opens a raw `asyncpg.connect` with **no `jsonb` codec**
(hence `parse_jsonb` at `utils.py:37`). So `row["compliance_guidance"]` is a `str`,
`isinstance(value, dict)` at `daily_digest.py:14` is `False`, and `_guidance_text`
falls to `str(value)` at `:16` — HTML-escaping the whole payload
(`schema_version`, `rule_set_hash`, every requirement object, citations — see
`schedule_breaks.py:270-295`) into both emails. `summary` never renders.

**Fix:** `parse_jsonb(...)` before `_guidance_text`, or set a codec on the worker
connection.

### B4 — The `matcha_work` bypass is dead code; scheduling-only tenants 403 at the door

`actions.py:235` adds `if not features.get("matcha_work") and not schedule_surface:`
and `tests/huume/test_schedule_action_envelope.py:8` asserts it with
`"matcha_work": False`. But the client posts to
`/matcha-work/threads/{id}/messages/stream`, and that router carries
`require_feature("matcha_work")` **twice** — at the mount (`routes/__init__.py:251`)
and in the package constructor (`routes/matcha_work/__init__.py:19`). A
scheduling-only tenant never reaches `evaluate_huume_action`. The bypass and its
test assert a property the deployment does not have.

Compounding it: `assistant.py` sits behind `require_all_features("matcha_ops", "employee_schedule")`
(`routes/__init__.py:227-229`) and checks neither `huume` nor `matcha_work` — so
session creation succeeds and writes an `mw_threads` row for a tenant that can
never send a message to it.

**Fix:** pick one. Either give the schedule turn its own endpoint under
`/employee-schedule` (which is what the bypass implies), or delete the bypass +
test and document `matcha_work` + `huume` as hard prerequisites — and have
`assistant.py` check them so session creation fails cleanly instead of orphaning a
thread.

---

## Tier 1 — correctness, before enabling anything

### F5 — Digest has no feature gate; enabling it mails every tenant

`schedule_daily_digest.py:16-18` selects `FROM business_locations WHERE is_active IS NOT FALSE`
— every location of **every company in the database**, no
`enabled_features->>'employee_schedule'` filter. Not the house pattern
(`handbook_watch`'s worker filters on the stored flag, per `app/workers/CLAUDE.md`).
First enable mails every `is_manager`/`is_supervisor` employee at every location of
every tenant, most of whom never bought scheduling.

### F6 — Digest emails draft and declined shifts

`daily_digest.py:66-82` filters `s.status <> 'cancelled'`, but the column is
`CHECK (status IN ('draft','published','cancelled'))` (`empsched01:82-83`) —
**unpublished drafts go to employees**, contradicting the `employee_schedule`
invariant that employees see only published shifts. No `a.status` filter either, so
`'declined'` assignments (`empsched01:107-108`) go out; and the employee loop never
checks `employment_status` (the manager query does, `:89`).

**Fix:** `s.status = 'published'`, exclude declined, apply
`INACTIVE_EMPLOYMENT_STATUSES` on both arms.

### F7 — Manager digest leaks named per-employee compliance data to arbitrary mailboxes

`_manager_html` (`:33-47`) renders **every assigned employee's name plus full
break/compliance guidance** into one email, sent (`:100-104`) to the union at
`:84-97` — whose second arm is `schedule_location_notification_recipients`, an
admin-entered address including `recipient_type='operational_mailbox'`
(`empsched08:33`). Only the free-text *note* is gated
(`manager_note_include_in_location_digest`); the guidance has no gate and there is
no per-recipient redaction.

**Fix:** gate guidance like the note, or redact names for non-employee recipient
types. State the decision in the plan.

### F8 — Digest claim/release breaks in both directions

The claim is race-safe — `INSERT … ON CONFLICT … DO NOTHING RETURNING id`
(`daily_digest.py:22-29`) is atomic, ordered before the send (`:102`/`:104`). The
release is not:

- **A raised exception keeps the claim.** `send_email` returning `False` releases
  (`:106`, `:119`); raising propagates with the claim committed, permanently
  suppressing that recipient for that date. No `try/finally`.
- **A permanent failure becomes an infinite retry.** The reserved-test-domain guard
  returns `False`, not raises (`core/services/email/client.py:130-136`), as does
  "Gmail not configured" (`:120-122`). Every seeded tenant claims → fails →
  releases → retries every worker restart, forever.
- **Employee dedupe key omits `shift_id`.** Two shifts that day (`:109` iterates one
  row per assignment) → one claim at `:115`, second shift's guidance dropped silently.
- **Case-sensitive email dedupe.** `UNIQUE(..., recipient_email, ...)`
  (`huumesched01:83`) is plain `VARCHAR`; the sibling table uses `LOWER(email)`
  (`empsched08:39`). `Bob@x.com` and `bob@x.com` are two claims, and the `UNION` at
  `:92` doesn't collapse them.

### F9 — `record_meal_break_waiver_core` never checks the location belongs to the company

`schedule_assistant_actions.py:82-98` verifies `employees.org_id=$2` then either
`work_location_id != location_id` or an `EXISTS` on assignments — but never
`SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2`, which its sibling
does three lines below at `:153-155`. Not exploitable today (`location_id` is
always server-derived), but it is the one writer that would break if that ever
changed.

Same function, second issue: `:109-123` refreshes break guidance for **every future
assignment of that employee company-wide** — no `s.location_id` filter, no `LIMIT`
on the driving query, all inside the open transaction. A location-scoped surface
writing unbounded cross-location rows, holding row locks for the duration. That's
the N+1 and the long-transaction risk in one.

### F10 — Flag-off falls through to the generic Matcha Work AI

`_run_huume_dispatch` bare-`return`s on three paths — `huume_mode` false (`:882`),
`huume` off (`:893`), and new here, `employee_schedule` off on a schedule thread
(`:894-895`). None sets `tc.terminated`, so `messaging.py:192-203` continues into
`_inject_mode_contexts` → `_generate_turn`: the generic skill engine answers.

An `employee`-role caller is admitted to `send_message_stream` **because** the
thread is `schedule_assistant` (`messaging.py:66-68`). If any flag is off, that
caller reaches the generic workspace AI — precisely the surface the guard denies.

### F11 — `messaging.py` role gate widened past what the plan describes

`messaging.py:54` went `require_admin_or_client` → `require_company_member`
(= `admin, client, individual, employee`, `dependencies.py:24`). The guard at
`:66-68` is a denylist on one role, so **`individual` is newly admitted to every
generic Matcha Work/Huume thread in the company**, with no surface check and no
test. The plan never mentions it. (An `individual` can't *create* a schedule
session — they fail `permits()` — but that isn't what this line controls.)

**Fix:** invert to an allow-list — `admin`/`client` on any thread, `employee` only
when `surface == 'schedule_assistant'`, everything else 403.

Related: three role lists must stay hand-synced — `dependencies.py:24`,
`actions.py:248`, `schedule_eligibility_authorization.py:20`.

### F12 — Authorization runs after the rate limit and the run row, and never surfaces as 403

`resolve_schedule_assistant_scope` is called at `turn_pipeline.py:932`, *after*
the `huume_turn` rate-limit consumption (`:909`) and `huume_store.create_run`
(`:917`). An unauthorized caller burns tenant rate-limit budget and leaves orphaned
`huume_runs` rows. Then, because headers are already sent (`:915` yields a status
frame), `messaging.py:233`'s `except BaseException` converts the `HTTPException`
into `"Failed to process message. Please try again."` and logs ERROR — which the
root handler persists to `server_error_reports`. A demoted manager retries forever
and never sees a 403.

**Fix:** resolve the scope in `send_message_stream` before the stream starts, and
pass the `HuumeSurfaceContext` down through `TurnContext`.

### F13 — Staged actions are replayable within a single turn

`pre_turn_action` is frozen at `agent.py:618` and never mutated. Two
`propose_work_permit(confirm_id=X)` calls in one batch (Gemini emits parallel
function calls) both see `status == "proposed"` and both execute → two permit rows,
two attestations, two audit entries. `propose_schedule_change` has a per-turn
fingerprint guard (`:1733-1752`); the four new arms have none. `send_offer` shares
the flaw, so it's a pattern defect — but now attached to writers that create
duplicate compliance records.

Related durability seam: the writer commits its own transaction (`:1142`), the
`status: "applied"` marker is in-memory (`:1147`), and `apply_update` runs in a
different transaction at turn end (`turn_pipeline.py:1003`) inside a swallowing
`except`. A crash between them leaves the DB written and the action still
`proposed` → replayable next turn. B1 makes this path fire today.

---

## Tier 2 — the model reads the wrong data

### F14 — `get_schedule_overview` truncates mid-shift and counts cancelled shifts

`schedule_assistant_context.py:38-57` returns one row per (shift × assignment) with
`LIMIT 500`. 120 shifts × 5 assignees = 600 rows → the last ~20 shifts vanish and
one shift comes back with a partial roster. `open_staffing_count` (`:94-96`) then
overstates understaffing for the truncated shift and understates it for the dropped
ones, with no `truncated` flag reaching the model. Separately there is no
`s.status` filter (`:49-51`), so cancelled shifts count toward `shift_count` and
`open_staffing_count` — every other reader in the package filters them
(`schedule_assistant_actions.py:93, 113, 162`).

**Fix:** aggregate assignments in SQL (`json_agg`) with `LIMIT` on shifts; return a
truncation marker; add `s.status <> 'cancelled'`.

### F15 — The week bound is advertised but not enforced

`HuumeSurfaceContext.week_start/week_end` bound only `get_schedule_overview`. They
do not bound `propose_assignment_note` (`update_assignment_note_core` checks
company + location, never the week) or `propose_schedule_change`
(`_resolve_shift_ref`, `schedule_chat.py:1040-1054`, windows forward from **today**
and is unbounded when an exact date is given). A manager on the Aug-23 week can
cancel a shift in October — while the system prompt tells them the workspace is
"week {week_start} through {week_end}".

### F16 — `write_mode` is dead, and the prompt promises drafts it doesn't deliver

`write_mode="draft"` is set in three places (`scope.py:17`,
`schedule_assistant_session.py:27,105`, `turn_pipeline.py:945`) and read in **zero**.
The prompt says *"changes are drafts until the manager explicitly publishes them"*,
but `propose_schedule_change` → `schedule_skill.execute` (`:179-216`) calls
`execute_edit_proposal`/`execute_proposal` with no draft flag — a `retime`/`cancel`/
`reassign` mutates **published** shifts immediately.

**Fix:** implement it or delete both the field and the prompt sentence.

### F17 — `build_state_block`'s empty state leaks workspace tools into the schedule prompt

`prompt.py:277` returns *"Nothing is currently staged. Any send_offer,
build_onboarding_plan, or execute_approved_steps call today starts fresh."* — the
schedule system prompt names three tools this surface removed.
`tests/huume/test_schedule_surface.py:32-43` asserts `"send_offer" not in prompt`
but passes a literal `state_block`, so it never exercises the real
`build_state_block({})` path. **False-negative test.**

### F18 — Three smaller model-facing defects

- **`find_shift_coverage` defaults to the wrong date** (`agent.py:1155`): with no
  date it silently answers for Monday of the displayed week. Previously an omitted
  date produced a clean clarify. A good clarify became a confidently wrong answer.
  It is also the one schedule tool with no `is_schedule` re-assertion.
- **`propose_work_permit` declares a required `location_id` the server overrides**
  (`agent.py:1121-1124` refuses on mismatch). The model's only source is the raw
  UUID in the prompt; any paraphrase → hard refusal. Drop it from `required`.
- **`propose_assignment_note` / `propose_meal_break_waiver` stage unvalidated ids**
  (`agent.py:1073, 1083`) — `evaluate_huume_action` checks UUID *shape* only
  (`actions.py:369-371`). `propose_eligibility_case_decision` does it right
  (`:1101-1110` fetches the case scoped to company+location first). The other two
  discover a hallucinated id only after the user has confirmed a plausible summary.

---

## Tier 3 — coverage, hygiene, docs

### F19 — Zero tests on every DB-touching module the commit added

Pure/unit claims: 7 of 7 covered. **Integration claims: 0 of 7.** No test at all
for `schedule_assistant_session.py` (182 ln), `schedule_assistant_actions.py`
(297 ln), `schedule_assistant_context.py` (130 ln), `daily_digest.py` (122 ln),
`schedule_daily_digest.py` (35 ln), `assistant.py` (36 ln), or
`ScheduleHuumePanel.tsx` (135 ln).

Uncovered plan claims: session reuse/differentiation (`plan:119`), 403/404 authz
(`plan:120`), thread hidden from generic listing (`plan:121`), overview scoped to
location + 7 days (`plan:122`), tool calls can't escape the location (`plan:123`),
writer audit data + transaction safety (`plan:124`), digest idempotency + retry
(`plan:126`).

Two existing tests **overstate themselves**:
`test_schedule_action_envelope.py:37`, named
`test_location_manager_can_confirm_scoped_schedule_action`, carries no manager or
location fact — `actions.py:248` is
`schedule_manager_authorized = schedule_surface and role in {"admin","client","employee"}`,
i.e. **any** employee. The real manager check
(`schedule_assistant_session.py:37-53`) has zero tests. And F17's prompt test.

**Fix:** rename both to what they prove; add the seven integration tests, starting
with `_assert_manager_location` 403/404, session-reuse keying, and the digest
claim/release.

### F20 — Frontend defects

- **Re-reloads the schedule on every message after the first write.**
  `ScheduleHuumePanel.tsx:29-33` reads `current_state.huume_action.status === 'applied'`,
  but that is persistent thread state (`agent.py:1147/:1260` →
  `turn_pipeline.py:1003,1021-1023`) and stays until a new action is staged. Every
  later `complete` frame re-triggers `onApplied()` → `useScheduleEditor.reload()`.
  Dedupe on `confirm_id` / `huume_run_id`. Drop the dead `'created'`/`'updated'`
  cases at `:32`.
- **Session-fetch failure leaves a silently inert chat box.** `:59-64` fires one
  transient toast, leaves `threadId` null, and renders the normal greeting with a
  permanently disabled composer — no error state, no retry. In the ops surface the
  toast may not render at all: `ScheduleEditor` sits under `WorkLayout` and
  `components/ui/Toast.tsx:23`'s default context is a no-op without a `ToastProvider`.
- **Stale closure at `:94`** — `metadata?.huume_steps || steps` reads `steps` from
  the render that invoked `send()`, i.e. before `setSteps([])` at `:80`. The
  fallback can only be `[]` or leftovers from a failed turn.
- **Stream-error handler `:101-106`** never clears `steps` (live timeline pulses
  forever) and never reconciles the optimistic bubble.
- **Unsound reset guard** — `mounted` (`:43,47`) is one shared ref reset to `true`
  each effect run; sound only because `ScheduleEditor.tsx:204` force-remounts via
  `key`. Use a per-run `let cancelled = false`.
- **Duplicated message rendering** (`:120-125`) instead of
  `work/components/panels/MessageBubble.tsx`: no markdown (shift tables render as
  literal `|`/`**`), no `React.memo` (every step frame re-renders the list), and
  **no `HuumeActionCard`** — the two-turn confirm protocol is text-only, and a
  `proposed` action in a resumed session is invisible (`current_state`/`version`
  are fetched at `scheduleChat.ts:16-17` and discarded). Also missing: auto-scroll,
  `aria-live`/`role="log"`, input label, dialog semantics on the `z-30` `<section>`.
- **Voice dictation regressed.** `ScheduleChatPanel.tsx:14,292` had
  `useVoiceDictation` push-to-talk, documented as shipped in
  `services/scheduling/CLAUDE.md` §"Schedule Assistant voice turns". The new panel
  has no mic. Port it or correct that doc.

### F21 — The legacy parser was removed from the UI, not from the API

`routes/employee_schedule/chat.py` is still mounted
(`employee_schedule/__init__.py:29`): `POST /chat`, `/chat/{id}/apply`,
`/chat/{id}/discard`, `/chat/voice-transcribe` remain reachable by any
authenticated company member. Dead on the client but pinned by its own test:
`ScheduleChatPanel.tsx` (341 ln) + `ScheduleChatPanel.test.tsx` (14 tests, still in
CI, still named in the plan's verification block), plus four unused exports in
`api/employees/scheduleChat.ts:27-52`.

`schedule_chat` the *service* is shared with the channel `@huume` path
(`schedule_chat_proposals`) — check before deleting. The router and the dead client
files can go regardless.

### F22 — Data-shape and consistency nits

- **`session_id` means two things.** `schedule_assistant_session.py:139` returns the
  session row id on reuse, the `thread_id` on first create (the INSERT has no
  `RETURNING id`). A client keying on it sees the value change on second mount.
- **`current_state` is returned as a JSON string.** No global jsonb codec on the
  pool (hence `_coerce.py:17-23`); `get_or_create_schedule_assistant_session`
  returns it raw from `fetchrow` in both branches (`:97, :122`) while
  `scheduleChat.ts:16` types it `Record<string, unknown>`. Compare `threads.py:107`,
  which parses.
- **`_week_end` inclusive vs `get_schedule_overview` exclusive-by-7** —
  `schedule_assistant_session.py:33` and `schedule_assistant_context.py:24-25`
  derive the same boundary independently in two files.
- **Registry spread.** `SCHEDULE_TOOLS`/`SCHEDULE_LOOKUP_TOPICS` live in `scope.py`,
  `_HUUME_ACTION_REQUIRED_FEATURE` in `actions.py`, the state-block branch in
  `prompt.py`, the arm in `agent.py`. Adding a fifth schedule action means four
  files with no compile-time link — which is exactly how B2 happened.
- **`create_thread`'s new kwargs are dead code.** `surface`/`initial_state`/
  `huume_mode` were added but the only caller (`routes/matcha_work/threads.py:154`)
  passes none; the session service writes its own raw INSERT
  (`schedule_assistant_session.py:108-120`) because it needs the caller's
  transaction, and thereby skips `_upsert_element_from_thread_row`. Give
  `create_thread` an optional `conn`, or drop the kwargs and comment the raw INSERT.
- **Thread exclusion is incomplete.** Only `list_threads` was filtered
  (`threads.py:141,147,176,209`). `routes/matcha_work/workspace.py:164`'s
  `recent_threads` CTE has no `surface` filter → schedule sessions appear in the
  workspace home recent-activity feed company-wide. Also `doc_svc.get_thread`
  matches on `company_id IS NOT DISTINCT FROM $2` (`threads.py:77-85`), so any
  company member can `GET /matcha-work/threads/{id}` on another manager's schedule
  thread and read `current_state` — the staged action included. The *turn* is
  blocked; the read is not.
- **`idx_mw_threads_surface` can't serve the listing sort.** It is
  `(company_id, surface, updated_at DESC)` but the queries
  `ORDER BY is_pinned DESC, updated_at DESC`. Also stray indentation in the SQL
  literal at `threads.py:155`.
- **`schedule_digest_deliveries` has no retention** — grows at
  locations × recipients rows/day forever, no prune task, no `digest_date` index.
- **Digest worker robustness** — no per-location `try/except` (`:20-24`), so one
  failure kills the rest and the retry restarts at location #1; `date.today()`
  (`:22`) is the worker host's date with no time-of-day gate, so a US-West tenant
  gets "Good morning / Today's breaks" around 5pm the previous local day;
  `escape(row['name'])` (`:39`) raises `AttributeError` when the COALESCE yields
  NULL, aborting the run; `max_per_cycle=500` is seeded and never read.
- **Migration lock note** — `huumesched01:36-42` adds the CHECK without `NOT VALID`,
  taking ACCESS EXCLUSIVE on `mw_threads` and full-scanning. Fine at current size;
  split into `NOT VALID` + `VALIDATE CONSTRAINT` if it grows. `downgrade()` is
  correct but destructive without saying so in the docstring.
- **`finish` and the schedule fingerprint bookkeeping run before the allow-list**
  (`agent.py:1713`, `:1733-1772`, vs `call_tool` at `:1785`). Latent only — both are
  in `SCHEDULE_TOOLS` — but "the allow-list is checked in `call_tool`" is not a
  whole-truth invariant.

### F23 — Rollout checklist under-specifies the flags

`/employee-schedule` is behind `require_all_features("matcha_ops", "employee_schedule")`
(`routes/__init__.py:227-229`); `/matcha-work` behind `require_feature("matcha_work")`
(`:247-251`). The plan's step 2 lists only `employee_schedule`, `huume`, "the
relevant product entitlement". Without `matcha_ops` session creation 403s; without
`matcha_work` every turn 403s (see B4).

### F24 — Docs not updated

No `CLAUDE.md` was touched. Stale against this change:
`services/scheduling/CLAUDE.md` (documents the editor assistant + voice turns —
see F20), `services/huume/CLAUDE.md` (the huume full spec: new surface, `scope.py`,
and the capability-bypass invariant below), `routes/matcha_work/CLAUDE.md`
(documents `messaging.py`'s role gate).

**Undocumented invariant worth writing down:** the schedule branch never calls
`resolve_work_access` (`turn_pipeline.py:947-951` is the `else`), so
`tc.work_access` stays `None` → `work_capabilities = None` (`agent.py:610`) →
`_effective_capabilities` falls to the legacy role path (`actions.py:49-53`),
returning everything for admin/client. Combined with `actions.py:248`'s explicit
bypass, the Work-capability gate is doubly neutered here: **role alone authorizes
writes, with location authz carried entirely by the per-turn
`_assert_manager_location`.** A client whose Work access was explicitly revoked
still executes schedule writes. Defensible, but F11 already shows how quietly a
role-gate widening propagates.

---

## Plan-document fixes

1. Add an **Invariants** section carrying the capability-bypass fact (F24) and the
   F10 fail-closed rule.
2. Correct the rollout flag list (F23): `matcha_ops` + `employee_schedule` +
   `matcha_work` + `huume`.
3. Add a **"new staged action" checklist** — registry entry, `agent.py` arm,
   `build_state_block` branch with `confirm_id`, prompt tool list, per-turn replay
   guard, `_json_safe` on the staged dict. B2 and B1 are both "forgot one of four
   files" bugs (F22).
4. Rewrite the verification block; it is green-by-construction today.
5. Add a **Digest safety** section: the F5 feature gate, the F6 published-only
   rule, the F7 recipient-redaction decision. It is the only part of this change
   that mails real people and it got the least specification.
6. Add the per-turn cost bounds inherited from `HUUME_SCHEDULE_RETRY_PLAN.md` to
   Architecture — this surface widens who can drive Gemini turns (employee-managers
   at every location), and that plan exists because of a real production spend
   incident ($3.44 / 32 turns, 167k-token runaway turns).
7. Say what happens to `routes/employee_schedule/chat.py` (F21).
8. Move the doc to `docs/plans/`, or note why it lives at root.

## Verification

```bash
cd server
pytest -q tests/huume/ tests/employee_schedule/ --disable-warnings
python3 -m compileall -q app/matcha/services/huume app/matcha/services/scheduling app/workers/tasks

cd ../client
npx tsc -p tsconfig.app.json --noEmit          # bare `npx tsc --noEmit` checks NOTHING
npm test -- --run src/ops/pages/ScheduleEditor.test.tsx
```

Manual, dev only (never prod):
1. **B1/B2 regression:** stage an eligibility `keep`, reply "confirm" → must execute
   once. Today it re-stages forever and drops the turn's state silently.
2. Manager at location A opens the panel → session hydrates; same week returns the
   same `thread_id`, a different week a different one.
3. Employee-manager at location B posts to location A's `thread_id` → real 404 at
   the client, not "Failed to process message" (F12), and no `huume_runs` row.
4. Turn off `employee_schedule` mid-session, send a turn → must refuse, **must not**
   produce a generic workspace answer (F10).
5. Confirm a staged note / waiver / permit / eligibility remove; verify each audit
   row, that the editor reloads **once**, and that a follow-up message does not
   re-reload (F20).
6. Workspace home recent-activity feed shows no schedule threads (F22).
7. **Digest:** run `send_location_daily_digest` against a dev location with a
   `compliance_guidance` row — rendered HTML must contain the `summary` string and
   **not** `schema_version` (B3); a draft shift must be absent (F6).
