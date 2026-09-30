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
  `(incident, phase)` ever — the `hr_case_triage_log` row is claimed before the
  model call. A check that couldn't run is `implicated = NULL` and opens
  nothing; it is never read as clean. The model only reports matches; the flag
  is the deterministic `decide_flag` (violated/bent ≥ company threshold,
  default 0.60). A clean close check on an existing case is an event for HR,
  never an auto-dismissal.
- **No narrative leaves the incident.** Cases store policy titles, relevance
  and confidence (`triage.summarize`). Notification bodies are fixed templates
  (incident number, case number, policy titles, names copied).
- **HR access** (`access.has_hr_access`) = Work `admin`, or READ on Drive's
  `HR / Discipline` folder. Every route re-checks it; non-HR gets **404**.
  The case list is a dedicated page, NOT an `mw_projects` kanban board: every
  business user can list every company project, and ~38 cross-project queries
  would each need a filter to keep HR cases private.
- **Who is told**: the GM (incident `created_by`, else the member matching
  `reported_by_email`; anonymous intake has none) and HR
  (`clients.is_hr_approver` — its documented notification-targeting purpose —
  else the owner, else every business user). Notification type
  `hr_case_flagged`.
- **Not in the HR Pilot corpus, deliberately.** That corpus is served to every
  business supervisor with no per-viewer access check; adding case records
  there would bypass HR access.
