# HR cases — `hr_cases` (default ❌)

The incident → write-up → HR approval → delivery → signed-copy workflow, on
business `/work`. Requires `matcha_work` + `matcha_drive`. Migration
`hrcase01`. Routes `routes/matcha_work/hr_cases.py` (`/matcha-work/hr-cases/*`),
page `client/src/work/pages/HrCases.tsx`.

**Standalone on purpose.** The old progressive-discipline product is retired
(`discipline` is in `RETIRED_COMPANY_FEATURES`) and will be rebuilt later. HR
cases never write `progressive_discipline` and revive no discipline flag,
route or page. They reuse two discipline modules as plain libraries only:
`discipline_policy_check.check_incident_against_handbook` (grounded handbook
check) and, from 5/6, the protected-leave gate + AI wording review.

## Lifecycle (`stages.py`, pure)

`flagged → drafting → hr_review ⇄ changes_requested → approved → delivered →
verifying → closed`, with `needs_attention` between `verifying` and `closed`
and `dismissed` from any pre-approval stage. `case_service.apply_event` is the
**only** writer of `hr_cases.stage`: it row-locks, asks `stages.next_stage`,
writes an allow-listed column set, and appends `hr_case_events` in one
transaction. An event that doesn't apply raises (409) — a stale button can't
skip a step.

## Invariants

- **One open case per incident** (partial unique index). The intake flag, the
  close re-check, a GM draft and Huume all converge on it (`open_case` returns
  the existing case with `created=False`).
- **Triage** (`triage.py`) runs as a background task on every new incident
  (`ir_incident_create.create_incident_core`) and fire-and-forget on close
  (both close paths: `routes/ir_incidents/crud.update_incident` and
  `ir_copilot_flow._close_incident_via_copilot`). One check per
  `(incident, phase)` — the `hr_case_triage_log` row is claimed before the
  model call. A check that couldn't run is `implicated = NULL` and opens
  nothing; it is never read as clean. It is retried once in the same run, and
  a finished "couldn't check" row stays re-claimable by a later trigger up to
  `MAX_ATTEMPTS` (3; the count lives in `result.attempts`). No connection is
  held across the model call: flag, claim, incident and handbook corpus are
  read on a short pooled connection (`discipline_policy_check.build_check_corpus`
  / `check_with_corpus`), then the result is written on another.
- **A case HR closed or dismissed stays closed.** A later check on that
  incident records `<phase>_check_match|clean` on it; it never opens a new
  case or notifies anyone again. The model only reports matches; the flag
  is the deterministic `decide_flag` (violated/bent ≥ company threshold,
  default 0.60). A clean close check on an existing case is an event for HR,
  never an auto-dismissal.
- **No narrative leaves the incident.** Cases store policy titles, relevance
  and confidence (`triage.summarize`) — not the model's free-text summary. Notification bodies are fixed templates
  (incident number, case number, policy titles, names copied).
- **HR access** (`access.has_hr_access`) = Work `admin`, or READ on Drive's
  `HR / Discipline` folder. Every route re-checks it; non-HR gets **404**.
  The case list is a dedicated page, NOT an `mw_projects` kanban board: every
  business user can list every company project, and ~38 cross-project queries
  would each need a filter to keep HR cases private.
- **Who is told**: the GM (incident `created_by`, else the member matching
  `reported_by_email`; anonymous intake has none) and HR
  (`clients.is_hr_approver` — its documented notification-targeting purpose —
  else the owner, else anyone in the company), **every tier filtered through
  `has_hr_access`**, so nobody hears about an HR matter they couldn't open and
  no link 404s. Nobody with access means nobody is told. Notification type
  `hr_case_flagged`. A reporter who isn't an active member is said so, not
  called anonymous.
- **Settings** (`PUT /hr-cases/settings`, the company-wide triage threshold)
  need Work `admin` or MANAGE on `HR / Discipline`
  (`access.can_change_hr_settings`); seeing cases isn't enough.
- **Case numbers** don't burn on a duplicate open: `open_case` takes a
  per-incident advisory lock and returns an existing open case before
  drawing a number.
- **Not in the HR Pilot corpus, deliberately.** That corpus is served to every
  business supervisor with no per-viewer access check; adding case records
  there would bypass HR access.

## Write-up workflow (5/6: `workflow.py`, `draft_review.py`)

A manager sends a letter (upload, a Drive file they can read, or a Google Doc
link) → it is stored in Drive `HR / Discipline / Drafts` through the system
path (the manager needs no HR Drive access) → reviewed → either
`draft_submitted` (to `hr_review`) or **held** (`set_fields` + event
`draft_held`, stage unchanged) when the leave check blocks → HR approves or
sends back (reason ≥ 20 chars, shown to the manager) → manager or HR marks it
delivered.

- **Authorization is in `workflow.py`, shared by REST and Huume**: HR on any
  case; the case's manager (`gm_user_id`) on their own case; any business user
  may start a NEW case by submitting a draft and becomes its manager.
  **Naming an incident** needs HR or being its reporter
  (`notifications.resolve_gm_user_id`), and only that person can claim a
  flagged case with no manager (`case_service.claim_manager`, conditional on
  `gm_user_id IS NULL`, and only after the stage check passes). Anyone else
  gets 404, and `GET /incidents` lists only the caller's own reports to
  non-HR. Decisions are HR-only.
- **A draft needs at least one occurrence date** (REST, Huume stage time, and
  the form). The leave gate is a date-overlap check: with no dates it passes
  vacuously. Approval refuses (409) a draft whose frozen `review.input` has
  none.
- **No connection across the model call or the emails.** `submit_draft`
  takes a connection factory: checks + filing on one short connection, the
  Gemini wording pass on none, the write on another, and
  `notifications.send_step` after it's released (`step_recipients` is the
  only DB part of a notice). The write re-checks the stage: a held draft
  goes through `set_fields(require_stages=DRAFTABLE_STAGES)`, a submitted
  one through `apply_event`'s row lock, so a draft that raced another into
  HR review 409s instead of overwriting it.
- **Dates a person types are calendar dates in their own zone**, which the
  server doesn't know: "future" means past today in UTC+14, and "before HR
  approved" means before the approval's date in UTC-12
  (`workflow.latest_local_today` / `earliest_local_date`).
- **The draft download** goes through `drive_service.presign_download`'s
  system path (`actor=None, on_behalf_of=<reader>`), so the HR-space read is
  in `drive_audit_log` like any other.
- **Review layers** (`draft_review.py`): (1) protected-leave gate
  `discipline_compliance.check_discipline_compliance` — deterministic, reads
  leave/PTO/incidents/ER only, a block cannot be overridden; (2) ladder fit vs
  this employee's delivered HR cases in the last year; (3) letter structure
  (name, date, length, expectation, consequence, signature line); (4) one
  Gemini wording pass of this module's own. It deliberately does NOT use
  `discipline_ai`: that corpus build seeds rows into the retired
  `discipline_policy_mapping` table.
- **Approval re-runs the leave gate** from the inputs frozen in
  `review.input` — leave records can change between review and approval.
- **Two audiences.** A manager only ever gets `workflow.manager_view`:
  structure notes, a generic "held for HR" message, HR's send-back reason, and
  their own last `infraction_type`/`occurrence_dates` (so a revision starts
  from them). Never
  the leave findings (medical-adjacent), triage matches, or HR's history.
- Notification types `hr_case_draft_submitted`/`_draft_held`/`_approved`/
  `_changes_requested`/`_delivered`; managers are linked to `/work/write-ups/…`,
  HR to `/work/hr-cases/…`.
- **Huume** (`services/huume/hr_case_skill.py`): `list_write_ups`,
  `search_drive`, `read_drive_file` (read) and `submit_write_up` /
  `decide_write_up` / `mark_write_up_delivered` (staged, action types
  `hr_case_draft`/`_decision`/`_delivered`, feature `hr_cases`). The staged
  draft pins a REFERENCE (thread attachment URL, Drive file id, or Google file
  id) at stage time; the confirm turn re-fetches those bytes. An ambiguous
  employee name refuses with each match's `employee_id` (a name typed in full
  wins outright), so the model can retry with an id instead of the same name. Thread
  attachments reach the loop as `attachment_refs` (`messaging.py` →
  `turn_pipeline` → `run_huume_turn`). HR case actions are in
  `assets._NO_ASSET_TYPES` — the asset panel has no HR-access check.
