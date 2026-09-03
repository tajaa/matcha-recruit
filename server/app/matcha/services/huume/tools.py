"""Huume's tool registry — the loop's vocabulary.

Mirrors the shape of `cappe/services/merlin/ops.py` (frozen-dataclass entries
+ a single dict lookup), scaled down to what a Gemini-native function-calling
tool declaration needs: no client-side applier, no op-shape prompt lines
(each tool's own `description` carries that instead, since Huume's tools are
typed function-call parameters, not a JSON-blob mini-language like Merlin's
ops). `tool_declarations()` is the single source of truth both the loop
(agent.py) and the prompt (prompt.py) read from, so the two can't drift.

Kinds, mirroring the `huume_steps.kind` CHECK constraint:
  read   — no side effect (lookup_context, check_offer_status)
  write  — writes a draft/non-terminal record, no confirm needed (draft_offer_letter)
  staged — proposes something that only executes on a LATER confirm turn
           (send_offer, build_onboarding_plan)
  finish — ends the turn
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from google.genai import types

LOOKUP_TOPICS = (
    "roster", "templates", "integrations", "training", "credentials", "offers",
    "employee", "training_status", "schedule", "incidents", "er_cases",
    "pto_leave", "policies", "discipline", "compliance", "documents", "events",
    "wage_floors", "inventory", "locations",
)

# record_type values show_record accepts — the single source both the tool
# schema's enum and record_view.py's dispatch table read from.
SHOW_RECORD_TYPES = ("incident", "er_case", "employee", "credential", "discipline", "ems_event", "inventory_item")


@dataclass(frozen=True)
class HuumeTool:
    name: str
    kind: str  # read | write | staged | finish
    declaration: types.FunctionDeclaration
    # `discovery=True` marks a "which X need attention?" batch entry point —
    # prompt.build_discovery_block and routing.resolve_tier both read this
    # registry so a new skill gets prompt teaching + deep-tier routing by
    # declaring the tool, with no harness edits. `intent_hints` are lowercase
    # phrases that mean "the user wants THIS tool" for the same two readers.
    discovery: bool = False
    intent_hints: tuple[str, ...] = ()


def _tool(
    name: str, kind: str, description: str, *, properties: dict | None = None,
    required: list[str] | None = None, discovery: bool = False, intent_hints: tuple[str, ...] = (),
) -> HuumeTool:
    return HuumeTool(
        name=name,
        kind=kind,
        declaration=types.FunctionDeclaration(
            name=name,
            description=description,
            parameters=types.Schema(type=types.Type.OBJECT, properties=properties or {}, required=required or []),
        ),
        discovery=discovery,
        intent_hints=tuple(h.lower() for h in intent_hints),
    )


_SCHEDULE_EDIT_PROPERTIES = {
    "kind": types.Schema(
        type=types.Type.STRING,
        enum=["reassign", "assign", "unassign", "retime", "cancel", "swap"],
    ),
    "target_shift_id": types.Schema(
        type=types.Type.STRING,
        description="Exact shift id returned by get_schedule_overview.",
    ),
    "target_employee_name": types.Schema(type=types.Type.STRING),
    "target_date": types.Schema(type=types.Type.STRING, description="YYYY-MM-DD"),
    "target_time_hint": types.Schema(
        type=types.Type.STRING,
        description="Start time of the shift, e.g. '12:30pm', '8am', or '08:00'.",
    ),
    "target_role_hint": types.Schema(type=types.Type.STRING),
    "target_staffing_hint": types.Schema(
        type=types.Type.STRING,
        enum=["staffed", "unstaffed"],
        description="Use only to distinguish otherwise identical staffed and open shifts.",
    ),
    "to_employee_name": types.Schema(type=types.Type.STRING),
    "second_employee_name": types.Schema(type=types.Type.STRING, description="For kind='swap'."),
    "second_date": types.Schema(type=types.Type.STRING, description="YYYY-MM-DD, for kind='swap'."),
    "second_time_hint": types.Schema(type=types.Type.STRING, description="Other shift's start time for kind='swap'."),
    "second_role_hint": types.Schema(type=types.Type.STRING, description="For kind='swap'."),
    "new_date": types.Schema(type=types.Type.STRING, description="YYYY-MM-DD, for kind='retime'."),
    "new_start_time": types.Schema(type=types.Type.STRING, description="HH:MM 24h, for kind='retime'."),
    "new_end_time": types.Schema(type=types.Type.STRING, description="HH:MM 24h, for kind='retime'."),
    "shift_by_minutes": types.Schema(
        type=types.Type.INTEGER,
        description="For a relative retime with no clock time given.",
    ),
}


TOOLS: tuple[HuumeTool, ...] = (
    _tool(
        "lookup_context", "read",
        "Look up read-only grounding data before drafting or acting, or to "
        "answer a general HR question: the existing roster, onboarding task "
        "templates, connected integrations (Google Workspace/Slack), new-hire "
        "training rules, prior offers, one employee's detail record, "
        "company-wide training completion/overdue status, the published "
        "schedule for the next 7 days, recent incidents — counts by "
        "type/severity plus a per-incident list (id, number, type, severity, "
        "status, date, location — never the description or named individuals, "
        "that's a legal record), ER (employment-relations) case "
        "counts by status plus a recent list (id, case number, title, status, "
        "category, outcome — never the description or involved employees), "
        "credential/license expirations, upcoming approved PTO/leave plus "
        "PENDING PTO requests awaiting a decision, active policy titles, "
        "discipline record counts by status (never narrative details), open "
        "compliance requirement counts by category, documents still "
        "awaiting employee signature, or statutory minimum-wage/exempt-salary"
        "-threshold FLOORS for a state (topic='wage_floors', query=the "
        "2-letter state code) — ALWAYS use this for any statutory wage/salary "
        "figure ('minimum salary', 'minimum wage', 'exempt threshold'); "
        "training-data numbers go stale every January and must never be "
        "quoted from memory. Call this before drafting an offer if "
        "you're unsure whether the candidate already has one, or before "
        "building a plan to check what integrations are actually connected. "
        "Use show_record with an id from a list here (incident/er_case/"
        "employee/credential/inventory_item) to open that record in the "
        "admin's side panel. topic='inventory' lists stock items with "
        "current count and any open order. topic='locations' lists the "
        "company's stores (id, name, city, state) — call this first to get "
        "a location_id for any inventory tool when the admin names a store; "
        "omit location_id entirely for company-wide inventory.",
        properties={
            "topic": types.Schema(type=types.Type.STRING, enum=list(LOOKUP_TOPICS)),
            "query": types.Schema(type=types.Type.STRING, description="Optional free-text filter, e.g. a candidate/employee name or email. For topic='wage_floors', the 2-letter state code (e.g. 'CA')."),
            "days": types.Schema(type=types.Type.INTEGER, description="Lookback window in days for topic='incidents'. Default 90, max 365."),
        },
        required=["topic"],
    ),
    _tool(
        "show_record", "read",
        "Open one or more records in the admin's side panel for review — use "
        "whenever the admin asks to see/show/open/pull up/look at specific "
        "records. Pass EVERY id they asked about in a single call (up to 8). "
        "Strongly prefer this over describing records in chat: the panel is "
        "where the admin reads and keeps them, not your reply. record_type: "
        "incident (ids from lookup_context topic='incidents'), er_case "
        "(topic='er_cases'), employee (topic='roster' or 'employee'), "
        "credential (topic='credentials'), inventory_item "
        "(topic='inventory'). Never guess an id.",
        properties={
            "record_type": types.Schema(type=types.Type.STRING, enum=list(SHOW_RECORD_TYPES)),
            "record_ids": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="One or more ids of the SAME record_type, from a prior lookup_context call.",
            ),
        },
        required=["record_type", "record_ids"],
    ),
    _tool(
        "draft_offer_letter", "write",
        "Create or revise a DRAFT offer letter. Never sends anything to the "
        "candidate — that's the separate send_offer tool, which requires a "
        "confirm. Pass offer_id to revise an existing draft; omit it to "
        "create a new one. Existing drafts can revise reporting_to, the "
        "candidate's supervisor or manager. A new draft needs at minimum "
        "candidate_name and position_title. When those two fields are known, "
        "create the draft now: candidate_email and reporting_to are optional "
        "draft fields and must not block drafting. Unknown fields can be added "
        "later; candidate_email becomes required only when sending.",
        properties={
            "offer_id": types.Schema(type=types.Type.STRING, description="UUID of an existing draft to revise. Omit to create a new offer."),
            "candidate_name": types.Schema(type=types.Type.STRING),
            "candidate_email": types.Schema(type=types.Type.STRING, description="Optional while drafting; required before send_offer can execute."),
            "position_title": types.Schema(type=types.Type.STRING),
            "salary": types.Schema(type=types.Type.STRING, description="Free-text salary, e.g. '$95,000/year'."),
            "start_date": types.Schema(type=types.Type.STRING, description="ISO date YYYY-MM-DD."),
            "employment_type": types.Schema(type=types.Type.STRING, description="e.g. 'Full-Time Exempt', 'Part-Time', 'Contract'."),
            "location": types.Schema(type=types.Type.STRING, description="Work location or state, e.g. 'Remote' or 'CA'."),
            "reporting_to": types.Schema(type=types.Type.STRING, description="Optional while drafting. Name of the candidate's supervisor or manager, if known."),
        },
    ),
    _tool(
        "send_offer", "staged",
        "Send an existing DRAFT offer letter to the candidate as a sign "
        "link. This is a real, user-facing action — it STAGES the send for "
        "the admin's confirmation and does not actually send until they "
        "reply confirming on a later turn. The staged proposal names the "
        "EXACT recipient email — always tell the admin that email before "
        "they confirm. Identify the offer by offer_id, OR by candidate_name "
        "('Maria' -> her latest draft offer) when the admin refers to it by "
        "name instead of an id. If the admin wants it sent somewhere else, "
        "pass recipient_email — that re-stages with the override and needs "
        "a fresh confirm.",
        properties={
            "offer_id": types.Schema(type=types.Type.STRING),
            "candidate_name": types.Schema(type=types.Type.STRING),
            "recipient_email": types.Schema(type=types.Type.STRING),
        },
        intent_hints=("send the offer", "send her offer", "send his offer",
                      "email the offer letter", "send the offer letter"),
    ),
    _tool(
        "check_offer_status", "read",
        "Check whether a sent offer has been accepted, declined, or is "
        "still pending the candidate's response.",
        properties={"offer_id": types.Schema(type=types.Type.STRING)},
        required=["offer_id"],
    ),
    _tool(
        "build_onboarding_plan", "staged",
        "Build the full new-hire onboarding plan for an ACCEPTED offer — "
        "employee record, portal invitation, onboarding tasks, credential "
        "requirements, training assignment, Google Workspace + Slack "
        "provisioning, and read-only schedule/benefits/jurisdiction notes. "
        "This STAGES the plan as a checklist the admin reviews and approves "
        "(in full or step by step) before anything executes — it does not "
        "run any step itself. The offer must already be accepted.",
        properties={"offer_id": types.Schema(type=types.Type.STRING)},
        required=["offer_id"],
    ),
    _tool(
        "execute_approved_steps", "write",
        "Approve and run steps of a staged onboarding plan. Only call this "
        "after the admin has explicitly said to go ahead on a LATER message "
        "than the one that built the plan — either with all of it "
        "('approve everything', 'go ahead') or specific steps by name "
        "('just create the employee and send the invite'). Pass step_keys "
        "naming exactly which steps they approved, or omit it / pass an "
        "empty list to mean all remaining proposed steps. Pass offer_id "
        "when more than one plan is active (see Current staged state); it "
        "may be omitted only when exactly one plan is active. Steps missing "
        "a required feature or integration are skipped and reported, not "
        "executed — that's not an error.",
        properties={
            "offer_id": types.Schema(type=types.Type.STRING, description="Which candidate's plan. Omit only if exactly one plan is active."),
            "step_keys": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="Plan step keys to approve+run, e.g. ['create_employee','portal_invitation']. Omit for all remaining proposed steps.",
            ),
        },
    ),
    _tool(
        "cancel_staged", "write",
        "Cancel a staged action or discard a staged onboarding plan when the "
        "admin changes their mind. target='action' voids whatever's pending "
        "(it will no longer execute even if confirmed). target='plan' discards the onboarding "
        "plan for offer_id — refused once it's already executing or done, "
        "since steps that already ran can't be undone from here. Pass "
        "offer_id whenever more than one plan is active.",
        properties={
            "target": types.Schema(type=types.Type.STRING, enum=["action", "plan"]),
            "offer_id": types.Schema(type=types.Type.STRING, description="Required for target='plan' when more than one plan is active."),
        },
        required=["target"],
    ),
    _tool(
        "draft_discipline", "staged",
        "Draft a progressive-discipline write-up for an attendance, "
        "performance, or policy-violation issue. This STAGES the write-up "
        "for the admin's confirmation — nothing is filed until they confirm "
        "on a LATER turn (pass confirm_id back exactly as given). NEVER for "
        "safety, harassment, discrimination, or other legal/leave topics — "
        "route those to corporate HR instead of drafting them. Needs "
        "specific occurrence date(s), not a vague timeframe — ask if the "
        "admin didn't give one.",
        properties={
            "employee_name": types.Schema(type=types.Type.STRING),
            "infraction_type": types.Schema(type=types.Type.STRING, enum=["attendance", "performance", "policy_violation"]),
            "severity": types.Schema(type=types.Type.STRING, enum=["minor", "moderate", "severe"], description="Defaults to 'moderate' if omitted."),
            "occurrence_dates": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="ISO date(s) YYYY-MM-DD when the conduct occurred.",
            ),
            "description": types.Schema(type=types.Type.STRING, description="Brief factual account of what happened, in the admin's words."),
            "expected_improvement": types.Schema(type=types.Type.STRING, description="Optional — what improvement is expected going forward."),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state' to file it.",
            ),
        },
        required=["employee_name", "infraction_type", "occurrence_dates", "description"],
    ),
    # ---- HR ops skills (each re-checks its own subsystem flag) ---------------
    _tool(
        "report_incident", "staged",
        "File a safety, behavioral, property, or near-miss incident into the "
        "company's IR log. This STAGES the report for the admin's confirmation "
        "— nothing is filed until they confirm on a LATER turn (pass confirm_id "
        "back exactly as given). An incident is a legal record: use the admin's "
        "own account of what happened and never invent details. Leave "
        "incident_type/severity out unless the admin was explicit — the IR "
        "classifier infers them. Named individuals belong in the description "
        "only if the admin named them; the record is editable in Incidents "
        "afterwards.",
        properties={
            "description": types.Schema(type=types.Type.STRING, description="Factual account of what happened, in the admin's words."),
            "occurred_at": types.Schema(type=types.Type.STRING, description="ISO datetime of the incident. Omit to use now."),
            "incident_type": types.Schema(type=types.Type.STRING, enum=["safety", "behavioral", "property", "near_miss", "other"]),
            "severity": types.Schema(type=types.Type.STRING, enum=["critical", "high", "medium", "low"]),
            "location": types.Schema(type=types.Type.STRING, description="Where it happened, e.g. 'Warehouse B loading dock'."),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state' to file it.",
            ),
        },
        required=["description"],
    ),
    _tool(
        "open_er_case", "staged",
        "Open an employment-relations (ER) case — the investigation file for a "
        "workplace complaint or dispute. This STAGES the case for the admin's "
        "confirmation; nothing is created until they confirm on a LATER turn "
        "(pass confirm_id back exactly as given). Involved employees are NEVER "
        "inferred from the narrative — the admin adds them on the ER page. Use "
        "the admin's own words for the description.",
        properties={
            "description": types.Schema(type=types.Type.STRING, description="What was reported or is in dispute, in the admin's words."),
            "title": types.Schema(type=types.Type.STRING, description="Short case title. Omit to derive one from the description."),
            "category": types.Schema(
                type=types.Type.STRING,
                enum=["harassment", "discrimination", "safety", "retaliation", "policy_violation", "misconduct", "wage_hour", "other"],
            ),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state'.",
            ),
        },
        required=["description"],
    ),
    _tool(
        "assign_training", "staged",
        "Assign a training requirement to specific employees. This STAGES the "
        "assignment for the admin's confirmation; nothing is assigned until "
        "they confirm on a LATER turn. Takes ids, never names — call "
        "lookup_context(topic='training') for the requirement catalog and "
        "topic='roster' (or 'employee') for employee ids first. An employee "
        "who already has this training open keeps the earlier due date.",
        properties={
            "requirement_id": types.Schema(type=types.Type.STRING, description="UUID of the training requirement, from lookup_context(topic='training')."),
            "employee_ids": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="UUIDs of employees to assign, from lookup_context(topic='roster').",
            ),
            "due_date": types.Schema(type=types.Type.STRING, description="ISO date YYYY-MM-DD. Omit to use the requirement's own default."),
        },
        required=["requirement_id", "employee_ids"],
    ),
    _tool(
        "decide_pto_request", "staged",
        "Approve or deny a PENDING PTO request. This STAGES the decision for "
        "the admin's confirmation; nothing changes until they confirm on a "
        "LATER turn. Takes the request's id — call "
        "lookup_context(topic='pto_leave') to list pending requests and their "
        "ids first. Approving also draws the hours down from the employee's "
        "balance.",
        properties={
            "request_id": types.Schema(type=types.Type.STRING, description="UUID of the pending PTO request, from lookup_context(topic='pto_leave')."),
            "decision": types.Schema(type=types.Type.STRING, enum=["approve", "deny"]),
            "note": types.Schema(type=types.Type.STRING, description="Optional note recorded with the decision."),
        },
        required=["request_id", "decision"],
    ),
    # ---- Incident-triggered discipline skill (feature `discipline`) ---------
    _tool(
        "find_discipline_candidates", "read",
        "Scan recently-closed incidents for candidate policy violations, "
        "ranked by severity — the answer to 'which incidents need "
        "disciplinary action?' or 'did anyone break policy?'. Cached-first: "
        "incidents already checked (by this tool, check_incident_policy, or "
        "the nightly sweep) cost nothing to re-report; unchecked ones get a "
        "bounded fresh check. Names NOBODY — use show_record to open an "
        "incident and see who was involved. If not_yet_checked is nonzero, "
        "say plainly that the scan was bounded — never imply it covered "
        "every closed incident.",
        properties={
            "days": types.Schema(type=types.Type.INTEGER, description="Lookback window over closed incidents, in days. Default 30, max 180."),
            "limit": types.Schema(type=types.Type.INTEGER, description="Max candidates to return, ranked. Default 5, max 10."),
            "recheck": types.Schema(type=types.Type.BOOLEAN, description="Re-run the check on already-checked incidents too. Default false."),
        },
        discovery=True,
        intent_hints=(
            "which incidents", "need discipline", "need disciplinary action", "disciplinary action",
            "broke policy", "broke a policy", "policy violation", "policy violations", "require a write-up",
        ),
    ),
    _tool(
        "check_incident_policy", "read",
        "Check a CLOSED incident's narrative against the company's handbook "
        "and active policies for candidate policy violations, with citations. "
        "Read-only — it reports possible matches, it never decides discipline "
        "level or legality. Call this before draft_disciplinary_action when "
        "the admin wants to know what an incident implicates.",
        properties={"incident_id": types.Schema(type=types.Type.STRING)},
        required=["incident_id"],
    ),
    _tool(
        "draft_disciplinary_action", "staged",
        "Stage a disciplinary action, optionally from a specific incident. "
        "This STAGES it for the admin's confirmation — nothing is created "
        "until they confirm on a LATER turn (pass confirm_id back exactly as "
        "given). Unlike draft_discipline, a filed record here goes to HR "
        "APPROVAL first — it is NOT issued directly. Takes employee_id, "
        "never a name — call lookup_context first. NEVER for safety, "
        "harassment, discrimination, or other legal/leave topics — route "
        "those to corporate HR instead of drafting them.",
        properties={
            "employee_id": types.Schema(type=types.Type.STRING),
            "incident_id": types.Schema(type=types.Type.STRING, description="Source incident, if any."),
            "infraction_type": types.Schema(type=types.Type.STRING, enum=["attendance", "performance", "safety", "policy_violation"]),
            "severity": types.Schema(type=types.Type.STRING, enum=["minor", "moderate", "severe"]),
            "discipline_type": types.Schema(type=types.Type.STRING, enum=["verbal_warning", "written_warning", "pip", "final_warning", "suspension"]),
            "occurrence_dates": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="ISO date(s) YYYY-MM-DD when the conduct occurred. Defaults to the incident's own date when omitted and incident_id is given.",
            ),
            "description": types.Schema(type=types.Type.STRING, description="Factual account of what happened, in the admin's words."),
            "expected_improvement": types.Schema(type=types.Type.STRING),
            "template_id": types.Schema(type=types.Type.STRING, description="Optional letter template id. Omit to let the server resolve the best match, or draft from scratch."),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state' to file it.",
            ),
        },
        required=["employee_id", "infraction_type", "description"],
    ),
    _tool(
        "decide_disciplinary_action", "staged",
        "Approve, deny, or send back for revision a discipline record that is "
        "pending HR approval. This STAGES the decision for the admin's "
        "confirmation; nothing changes until they confirm on a LATER turn. "
        "'deny' is TERMINAL — the record is dead, a new one would need to be "
        "drafted from scratch. 'revise' sends it back to whoever drafted it "
        "so they can fix it and resubmit — use this when the substance is "
        "right but something needs to change, not when the whole thing "
        "should be dropped. Both 'deny' and 'revise' REQUIRE a written "
        "reason (at least 20 characters) — it becomes part of the legal "
        "record. Call list_pending_approvals first if you don't already "
        "have the record_id.",
        properties={
            "record_id": types.Schema(type=types.Type.STRING),
            "decision": types.Schema(type=types.Type.STRING, enum=["approve", "deny", "revise"]),
            "reason": types.Schema(type=types.Type.STRING, description="Required when decision='deny' or 'revise' — at least 20 characters."),
        },
        required=["record_id", "decision"],
    ),
    _tool(
        "list_pending_approvals", "read",
        "List this company's discipline records awaiting HR approval, with "
        "their ids, employee, infraction type, and how long they've been "
        "waiting.",
        discovery=True,
        intent_hints=("pending approvals", "awaiting approval", "waiting for approval", "approval queue"),
    ),
    # ---- Legal Pilot skill (feature `legal_defense`) -------------------------
    _tool(
        "list_legal_matters", "read",
        "List the company's legal matters (litigation-readiness case files "
        "from the Legal Pilot) — id, title, type, status, jurisdiction, "
        "deadline. Call this before asking about or acting on a matter when "
        "you don't already have its matter_id.",
    ),
    _tool(
        "open_legal_matter", "write",
        "Open a new legal matter (subpoena, class_action, eeoc_charge, "
        "single_plaintiff, audit, or other) — the case file the Legal Pilot "
        "organizes evidence into. Creates a real record the admin also sees "
        "on the Legal Pilot page. Confirm the title and what's being alleged "
        "with the admin before opening one; don't invent details.",
        properties={
            "title": types.Schema(type=types.Type.STRING),
            "matter_type": types.Schema(type=types.Type.STRING, enum=["subpoena", "class_action", "eeoc_charge", "single_plaintiff", "audit", "other"]),
            "allegation": types.Schema(type=types.Type.STRING, description="What is being alleged or claimed, in the admin's words."),
            "jurisdiction_state": types.Schema(type=types.Type.STRING, description="Two-letter US state code, e.g. 'CA'."),
            "evidence_start": types.Schema(type=types.Type.STRING, description="ISO date YYYY-MM-DD — start of the relevant evidence window."),
            "evidence_end": types.Schema(type=types.Type.STRING, description="ISO date YYYY-MM-DD — end of the relevant evidence window."),
        },
        required=["title"],
    ),
    _tool(
        "ask_legal_pilot", "write",
        "Ask the Legal Pilot a question about a matter. It gathers the "
        "company's own records (incidents, ER cases, discipline, training, "
        "policies, compliance, and more) into an evidence corpus and returns "
        "a citation-validated factual analysis — observations tied to real "
        "record ids, plus open questions for counsel. It may instead ask for "
        "missing intake material; relay those requests. The exchange is "
        "saved to the matter's transcript on the Legal Pilot page. Pass "
        "matter_id when more than one matter is open (see Current staged "
        "state / list_legal_matters).",
        properties={
            "question": types.Schema(type=types.Type.STRING),
            "matter_id": types.Schema(type=types.Type.STRING, description="Which matter. Omit to use the thread's active matter, or when exactly one matter is open."),
        },
        required=["question"],
    ),
    _tool(
        "generate_legal_packet", "write",
        "Generate the attorney-facing evidence packet for a matter — a "
        "defense-memo PDF citing only real records and/or a ZIP of the "
        "underlying source documents. Requires at least one prior "
        "ask_legal_pilot analysis on the matter (the memo is built from it). "
        "The files are stored on the matter; the admin downloads them from "
        "the Legal Pilot page. Only call this when the admin explicitly asks "
        "for the packet/export.",
        properties={
            "matter_id": types.Schema(type=types.Type.STRING, description="Which matter. Omit to use the thread's active matter."),
            "kind": types.Schema(type=types.Type.STRING, enum=["pdf", "zip", "both"]),
        },
    ),
    # ---- Handbook Pilot skill (feature `handbook_pilot`) ---------------------
    _tool(
        "draft_handbook_content", "write",
        "Draft handbook sections and/or standalone policies grounded in the "
        "company's own profile, applicable jurisdiction requirements, "
        "existing handbook and policies, and open audit/freshness findings. "
        "Pass the admin's request verbatim (e.g. 'a lactation accommodation "
        "policy for our CA and NY offices'). Proposals are saved as PENDING "
        "DRAFTS — reviewable and editable on the Handbook Pilot page — and "
        "are NOT part of the real handbook until promoted. Never call "
        "promote_handbook_drafts in the same turn you drafted.",
        properties={
            "request": types.Schema(type=types.Type.STRING, description="What to draft, in the admin's words — topic, jurisdictions, any constraints."),
        },
        required=["request"],
    ),
    _tool(
        "promote_handbook_drafts", "write",
        "Promote reviewed pending drafts into the real tables: handbook-"
        "section drafts become ONE new draft handbook (or amend an existing "
        "handbook when target_handbook_id is given), policy drafts become "
        "draft policies. Only call this when the admin explicitly asks to "
        "promote, on a LATER message than the one that drafted them. Pass "
        "draft_ids naming exactly which drafts (see Current staged state), "
        "or omit it to promote all pending drafts from earlier turns. "
        "Without a target, everything promoted still lands as a DRAFT "
        "handbook/policy the admin publishes through the normal flow; "
        "amending an existing handbook edits its live sections in place and "
        "auto-resolves any pending change requests raised by freshness "
        "findings the promoted drafts cite.",
        properties={
            "draft_ids": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="Pending draft ids to promote. Omit for all pending drafts from earlier turns.",
            ),
            "handbook_title": types.Schema(type=types.Type.STRING, description="Title for the new draft handbook when promoting section drafts."),
            "target_handbook_id": types.Schema(
                type=types.Type.STRING,
                description=(
                    "Existing handbook id to amend INSTEAD of creating a new "
                    "draft handbook: matching sections update in place, new "
                    "ones append. Only pass an id the admin explicitly chose. "
                    "Omit to create a new draft handbook. This edits a LIVE "
                    "handbook and is NOT a one-shot action: the first call "
                    "STAGES the amendment for review; you must call this tool "
                    "again with the SAME target_handbook_id after the admin "
                    "explicitly confirms before it actually applies."
                ),
            ),
        },
    ),
    # ---- ER Copilot bridge (feature `er_copilot`) ----------------------------
    _tool(
        "er_case_brief", "read",
        "Get a name-free summary of an ER (employee-relations) case — status, "
        "category, document count/titles, which analyses have been run and a "
        "one-line headline for each, note count, and how long it's been open. "
        "No Gemini call, read-only. Names NOBODY involved — use show_record "
        "with record_type='er_case' to open the case and see who's involved.",
        properties={"case_id": types.Schema(type=types.Type.STRING)},
        required=["case_id"],
    ),
    _tool(
        "ask_er_copilot", "write",
        "Ask a grounded question about a specific ER case — pulls the case's "
        "own uploaded document text, its stored AI analyses (timeline, "
        "discrepancies, policy check, similar cases), and applicable "
        "jurisdiction requirements, and returns an answer with bracketed "
        "citations to real records. NOT a lawyer and NOT legal advice — it "
        "relays what the company's own records show. Call er_case_brief "
        "first if you don't have a case_id. Pass case_id when more than one "
        "case is in play; omit it to use the thread's active case.",
        properties={
            "case_id": types.Schema(type=types.Type.STRING, description="Which case. Omit to use the thread's active case (see Current staged state)."),
            "question": types.Schema(type=types.Type.STRING),
        },
        required=["question"],
        intent_hints=(
            "employee relations", "er case", "er issue", "complaint about",
            "grievance", "investigation", "workplace complaint",
        ),
    ),
    # ---- EMS events skill (feature `ems`; promotion also needs `incidents`) --
    _tool(
        "promote_ems_event", "staged",
        "Promote a logged EMS event into a real IR incident. This STAGES the "
        "promotion for the admin's confirmation — nothing is filed until they "
        "confirm on a LATER turn by calling this again with EXACTLY the same "
        "event_id. Get event ids from lookup_context(topic='events'). The "
        "event's own title/suggested type/severity are used unless overridden. "
        "Promotion is one-way; the incident is a legal record editable in Incidents.",
        properties={
            "event_id": types.Schema(type=types.Type.STRING, description="The EMS event id, from lookup_context(topic='events') or show_record."),
            "title": types.Schema(type=types.Type.STRING),
            "incident_type": types.Schema(type=types.Type.STRING, enum=["safety", "behavioral", "property", "near_miss", "other"]),
            "severity": types.Schema(type=types.Type.STRING, enum=["critical", "high", "medium", "low"]),
            "occurred_at": types.Schema(type=types.Type.STRING, description="ISO datetime. Omit to use the event's logged time."),
            "location": types.Schema(type=types.Type.STRING),
        },
        required=["event_id"],
        intent_hints=("promote the event", "logged event", "make it an incident", "escalate the event"),
    ),
    # ---- IR Copilot bridge (feature `ir_copilot`) ----------------------------
    _tool(
        "ask_ir_copilot", "write",
        "Ask the IR Copilot for guidance on an incident — a grounded summary, "
        "open questions, and suggested next steps from the incident's own "
        "record and cached analyses. The exchange is saved to the incident's "
        "Copilot transcript on the IR detail page, where the admin can "
        "continue it. Pass incident_id when more than one is in play; omit to "
        "use the thread's active incident (e.g. one just promoted).",
        properties={
            "question": types.Schema(type=types.Type.STRING),
            "incident_id": types.Schema(type=types.Type.STRING),
        },
        required=["question"],
        intent_hints=("incident copilot", "incident report pilot", "guidance on the incident"),
    ),
    _tool(
        "run_incident_analysis", "write",
        "Run one AI analysis on an incident and cache it to the incident's AI "
        "Analysis panels: root_cause (primary cause, contributing factors, "
        "prevention) or recommendations (corrective actions). Returns the "
        "cached result instantly if it already ran — pass refresh=true to "
        "recompute instead (e.g. the incident was edited since the last run).",
        properties={
            "analysis_type": types.Schema(type=types.Type.STRING, enum=["root_cause", "recommendations"]),
            "incident_id": types.Schema(type=types.Type.STRING),
            "refresh": types.Schema(type=types.Type.BOOLEAN, description="Recompute even if a cached analysis exists."),
        },
        required=["analysis_type"],
        intent_hints=("root cause analysis", "corrective action recommendations"),
    ),
    # ---- Inventory ops skill (feature `inventory`) ---------------------------
    _tool(
        "record_stock_movement", "staged",
        "Record stock going out, a stockout, or a count adjustment for an "
        "item. This STAGES the movement for the admin's confirmation — "
        "nothing changes until they confirm on a LATER turn by calling this "
        "again with EXACTLY the same confirm_id. Get item ids from "
        "lookup_context(topic='inventory'); pass new_item_name instead of "
        "item_id to auto-create one. kind='adjust' sets the count to an exact "
        "known value (a physical count), not a delta. kind='stockout' zeroes "
        "the count regardless of quantity. Use lookup_context(topic='locations') "
        "for location_id when the admin names a specific store; omit it for "
        "the shared company-wide item pool. Received stock/deliveries are "
        "NEVER recorded here — receive an open order with "
        "decide_inventory_order(decision='receive'), or attach the "
        "delivery's invoice CSV and use stage_receipt_from_attachment.",
        properties={
            "kind": types.Schema(type=types.Type.STRING, enum=["out", "stockout", "adjust"]),
            "item_id": types.Schema(type=types.Type.STRING, description="UUID from lookup_context(topic='inventory')."),
            "new_item_name": types.Schema(type=types.Type.STRING, description="Create a new item with this name instead of using item_id."),
            "quantity": types.Schema(type=types.Type.NUMBER, description="Required for out/adjust. Ignored for stockout."),
            "location_id": types.Schema(type=types.Type.STRING, description="UUID from lookup_context(topic='locations'). Omit for company-wide."),
            "note": types.Schema(type=types.Type.STRING, description="Optional short note recorded on the movement."),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state'.",
            ),
        },
        required=["kind"],
        discovery=True,
        intent_hints=("we used", "we ran out", "out of stock", "ran out of", "used up", "we went through", "stock count", "count is"),
    ),
    _tool(
        "stage_inventory_order", "write",
        "Queue a restock order for an item — a real record the admin (or "
        "anyone) can approve, and the same queue the Inventory page shows. "
        "This does NOT need a later confirm — queuing is itself the staging "
        "step; use decide_inventory_order to approve/receive/cancel it. "
        "Omit quantity to use the deterministic reorder suggestion from the "
        "item's consumption history, if any.",
        properties={
            "item_id": types.Schema(type=types.Type.STRING, description="UUID from lookup_context(topic='inventory')."),
            "new_item_name": types.Schema(type=types.Type.STRING, description="Create a new item with this name instead of using item_id."),
            "quantity": types.Schema(type=types.Type.NUMBER, description="Omit to use the reorder-history suggestion."),
            "location_id": types.Schema(type=types.Type.STRING, description="UUID from lookup_context(topic='locations'). Omit for company-wide."),
        },
        discovery=True,
        intent_hints=("running low", "restock", "order more", "need to order", "place an order"),
    ),
    _tool(
        "decide_inventory_order", "staged",
        "Approve, receive, or cancel a queued/ordered restock order. This "
        "STAGES the decision for the admin's confirmation; nothing changes "
        "until they confirm on a LATER turn. Get order_id from "
        "lookup_context(topic='inventory') (an item's open_order) or "
        "show_record. decision='receive' records the delivery as stock — "
        "pass quantity if it differs from what was ordered.",
        properties={
            "order_id": types.Schema(type=types.Type.STRING),
            "decision": types.Schema(type=types.Type.STRING, enum=["approve", "receive", "cancel"]),
            "quantity": types.Schema(type=types.Type.NUMBER, description="For decision='receive' when the delivered amount differs from what was ordered."),
        },
        required=["order_id", "decision"],
    ),
    _tool(
        "create_inventory_item", "staged",
        "Add a new inventory item outright (not via a movement). This STAGES "
        "the item for the admin's confirmation — nothing is created until "
        "they confirm on a LATER turn by calling this again with EXACTLY the "
        "same confirm_id. Prefer record_stock_movement with new_item_name "
        "when the admin is really describing a delivery or usage, not just "
        "adding a catalog entry.",
        properties={
            "name": types.Schema(type=types.Type.STRING),
            "unit": types.Schema(type=types.Type.STRING, description="e.g. 'BX', 'CS', 'EA'."),
            "initial_quantity": types.Schema(type=types.Type.NUMBER),
            "low_stock_threshold": types.Schema(type=types.Type.NUMBER),
            "location_id": types.Schema(type=types.Type.STRING, description="UUID from lookup_context(topic='locations'). Omit for company-wide."),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state'.",
            ),
        },
        required=["name"],
    ),
    _tool(
        "archive_inventory_item", "staged",
        "Archive (soft-delete) an inventory item — it stops appearing in "
        "lookups and on the Inventory page. This STAGES the archive for the "
        "admin's confirmation; nothing changes until they confirm on a LATER "
        "turn. Get item_id from lookup_context(topic='inventory').",
        properties={"item_id": types.Schema(type=types.Type.STRING)},
        required=["item_id"],
    ),
    _tool(
        "stage_receipt_from_attachment", "staged",
        "Parse a vendor invoice/packing-slip CSV the admin attached to their "
        "message, and STAGE the resulting stock-in lines for confirmation — "
        "nothing is recorded until they confirm on a LATER turn by calling "
        "this again with EXACTLY the same confirm_id. The server parses the "
        "attachment itself and matches its lines against existing items — "
        "do NOT retype or invent line items yourself. Only CSV attachments "
        "are supported here (ask the admin to export PDF/photo invoices as "
        "CSV, or use the Inventory page's Receive Delivery for those). If no "
        "attachment or no parseable lines are found, say so plainly. If the "
        "staged state shows a duplicate-invoice warning, confirming anyway "
        "commits it — there's no separate override step.",
        properties={
            "location_id": types.Schema(type=types.Type.STRING, description="UUID from lookup_context(topic='locations'). Omit for company-wide."),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state'.",
            ),
        },
        discovery=True,
        intent_hints=("received a delivery", "got a delivery", "invoice attached", "packing slip"),
    ),
    _tool("record_waste_movement", "staged", "Stage observed discarded stock with a reason; this only records after a later confirmation.", properties={
        "item_id": types.Schema(type=types.Type.STRING), "quantity": types.Schema(type=types.Type.NUMBER),
        "waste_reason": types.Schema(type=types.Type.STRING, enum=["spoilage","expired","prep_error","overproduction","breakage","contamination","theft","comp","recall","unknown"]),
        "note": types.Schema(type=types.Type.STRING), "location_id": types.Schema(type=types.Type.STRING), "confirm_id": types.Schema(type=types.Type.STRING),
    }, required=["item_id", "quantity", "waste_reason"]),
    _tool("apply_waste_par_change", "staged", "Stage a manager-approved predictive par change from a forecast run.", properties={"run_id": types.Schema(type=types.Type.STRING), "item_id": types.Schema(type=types.Type.STRING)}, required=["run_id", "item_id"]),
    _tool("correct_waste_recipe", "staged", "Stage a recipe mapping correction; components are existing item ids and quantities per sale.", properties={"sold_name": types.Schema(type=types.Type.STRING), "components": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.OBJECT)), "location_id": types.Schema(type=types.Type.STRING), "confirm_id": types.Schema(type=types.Type.STRING)}, required=["sold_name", "components"]),
    _tool(
        "propose_assignment_note", "staged",
        "Stage one visible manager note on an employee's shift. Use a shift "
        "and employee id from the schedule overview. Nothing is written or "
        "emailed until a later confirmation.",
        properties={
            "shift_id": types.Schema(type=types.Type.STRING),
            "employee_id": types.Schema(type=types.Type.STRING),
            "note": types.Schema(type=types.Type.STRING),
            "visible_to_employee": types.Schema(type=types.Type.BOOLEAN),
            "include_in_location_digest": types.Schema(type=types.Type.BOOLEAN),
            "send_employee_notice": types.Schema(type=types.Type.BOOLEAN),
            "confirm_id": types.Schema(type=types.Type.STRING),
        },
        required=["shift_id", "employee_id", "note"],
    ),
    _tool(
        "propose_meal_break_waiver", "staged",
        "Stage a manager confirmation that an employee's signed meal-break "
        "waiver is or is not on file. Include the effective date and note; "
        "future assignment break guidance is refreshed only after confirmation.",
        properties={
            "employee_id": types.Schema(type=types.Type.STRING),
            "on_file": types.Schema(type=types.Type.BOOLEAN),
            "effective_from": types.Schema(type=types.Type.STRING),
            "note": types.Schema(type=types.Type.STRING),
            "confirm_id": types.Schema(type=types.Type.STRING),
        },
        required=["employee_id", "on_file", "effective_from"],
    ),
    _tool(
        "propose_work_permit", "staged",
        "Stage entry of a confirmed minor work permit for one employee and "
        "the selected schedule location. The location is supplied by the "
        "server-scoped workspace; permit dates are checked again when confirmed.",
        properties={
            "employee_id": types.Schema(type=types.Type.STRING),
            "issued_at": types.Schema(type=types.Type.STRING),
            "expires_at": types.Schema(type=types.Type.STRING),
            "confirm_id": types.Schema(type=types.Type.STRING),
        },
        required=["employee_id", "expires_at"],
    ),
    _tool(
        "list_schedule_eligibility_cases", "read",
        "List open credential/permit eligibility cases and recurring "
        "escalations for this schedule location. The case expiration is "
        "historical; use the returned canonical current credential status, "
        "expiration, and block reason when explaining assignment eligibility.",
        properties={},
        discovery=True,
        intent_hints=("who is blocked", "expired permits", "expired credentials", "compliance issues"),
    ),
    _tool(
        "propose_eligibility_case_decision", "staged",
        "Stage a decision on one open credential or work-permit eligibility "
        "case. Choose remove to take the employee off the affected future "
        "shifts, or keep only when the manager explicitly acknowledges the "
        "cited legal/compliance risk with a written explanation. Nothing "
        "changes until a later confirmation.",
        properties={
            "case_id": types.Schema(type=types.Type.STRING),
            "decision": types.Schema(type=types.Type.STRING, enum=["remove", "keep"]),
            "acknowledgement_confirmed": types.Schema(type=types.Type.BOOLEAN),
            "acknowledgement_note": types.Schema(type=types.Type.STRING),
            "confirm_id": types.Schema(type=types.Type.STRING),
        },
        required=["case_id", "decision"],
    ),
    _tool(
        "get_schedule_overview", "read",
        "Read the selected location's full schedule-builder week, including "
        "draft and published shifts, open staffing, assignment notes visible "
        "to the manager, and deterministic break/compliance guidance. Use "
        "this for 'what needs attention?' before proposing a change.",
        properties={},
        discovery=True,
        intent_hints=("what needs attention", "review this week", "schedule overview", "check the schedule"),
    ),
    _tool(
        "get_week_build_readiness", "read",
        "Check whether Huume has enough confirmed availability and staffing "
        "demand to build the selected location's entire week. Returns the "
        "available demand sources, roster readiness, and exact blockers. "
        "Call this before building a week when the inputs are uncertain.",
        properties={},
        discovery=True,
        intent_hints=("build this week", "create the schedule", "schedule readiness", "staff the week"),
    ),
    _tool(
        "build_week_schedule", "staged",
        "Build and stage a deterministic whole-week schedule proposal from "
        "confirmed employee availability and either the week's existing draft "
        "shifts or a saved week template. Existing assignments are preserved. "
        "Nothing is added to the editor until the manager confirms on a LATER "
        "turn with the exact confirm_id; the resulting shifts remain drafts.",
        properties={
            "source_mode": types.Schema(
                type=types.Type.STRING, enum=["auto", "existing", "template"],
                description="Use auto unless the manager selected a specific source.",
            ),
            "week_template_id": types.Schema(
                type=types.Type.STRING,
                description="Required when source_mode=template; use an id returned by readiness.",
            ),
            "exclude_employee_ids": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="Employees the manager explicitly asked not to schedule in this proposal.",
            ),
            "employee_hour_caps": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "employee_id": types.Schema(type=types.Type.STRING),
                        "max_weekly_minutes": types.Schema(type=types.Type.INTEGER),
                    },
                    required=["employee_id", "max_weekly_minutes"],
                ),
                description="Optional manager overrides that can only tighten weekly hour caps.",
            ),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit when staging; after explicit approval, echo the staged confirm_id exactly.",
            ),
        },
        required=[],
        discovery=True,
        intent_hints=("build my week", "generate weekly schedule", "fill the whole schedule", "make this week's schedule"),
    ),
    _tool(
        "find_shift_coverage", "read",
        "Find who is free to cover shifts on one date — use for 'who can "
        "cover / replace / fill in for X' questions. date must be YYYY-MM-DD. "
        "Returns each published shift's current assignees plus ranked "
        "candidates who are free and available that day. Read-only — never "
        "assigns anyone; follow up with propose_schedule_change once you "
        "have a candidate.",
        properties={
            "date": types.Schema(type=types.Type.STRING, description="YYYY-MM-DD"),
            "role_hint": types.Schema(
                type=types.Type.STRING,
                description="Optional — filter to shifts whose role matches, e.g. 'opener'.",
            ),
        },
        required=["date"],
        discovery=True,
        intent_hints=("who can cover", "who's free", "call out", "called in sick", "coverage"),
    ),
    _tool(
        "propose_schedule_change", "staged",
        "Stage one schedule proposal for the admin to confirm. Use `changes` "
        "to batch up to four related edits (swap, reassign, assign, unassign, "
        "retime, or cancel) into one confirmation; use the legacy flat `kind` "
        "fields for one edit or a brand new shift. When the manager explicitly "
        "asks to assign one employee to every vacant shift in the selected "
        "editor week, set all_vacant_shifts=true and to_employee_name instead "
        "of enumerating changes. Do not mix creates and edits. "
        "Nothing happens until they confirm on a LATER turn by calling this "
        "again with EXACTLY the same confirm_id. Use real names/dates from "
        "lookup_context(topic='schedule') or find_shift_coverage — never "
        "invent one.",
        properties={
            "kind": types.Schema(
                type=types.Type.STRING,
                enum=["create", "reassign", "assign", "unassign", "retime", "cancel", "swap"],
            ),
            "changes": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties=_SCHEDULE_EDIT_PROPERTIES,
                    required=["kind"],
                ),
                min_items=1,
                max_items=4,
                description="One to four edit operations resolved and confirmed as one proposal. Creates are not allowed here.",
            ),
            "all_vacant_shifts": types.Schema(
                type=types.Type.BOOLEAN,
                description="True only when the manager explicitly requested assigning to every vacant shift in the selected editor week.",
            ),
            "location_name": types.Schema(
                type=types.Type.STRING,
                description="Store name if the company has more than one location — get exact "
                            "names from lookup_context(topic='locations'). Omit if there's only one.",
            ),
            **{key: value for key, value in _SCHEDULE_EDIT_PROPERTIES.items() if key != "kind"},
            "label": types.Schema(type=types.Type.STRING, description="For kind='create'."),
            "date": types.Schema(type=types.Type.STRING, description="YYYY-MM-DD, for kind='create'."),
            "start_time": types.Schema(type=types.Type.STRING, description="For kind='create', HH:MM 24h."),
            "end_time": types.Schema(type=types.Type.STRING, description="For kind='create', HH:MM 24h."),
            "count": types.Schema(type=types.Type.INTEGER, description="For kind='create'."),
            "employee_names": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="For kind='create'.",
            ),
            "confirm_id": types.Schema(
                type=types.Type.STRING,
                description="Omit on the first (staging) call. On the confirm turn, pass back EXACTLY the confirm_id from 'Current staged state'.",
            ),
        },
        # A stage call needs either `changes` or flat `kind`; a confirm call
        # needs only confirm_id, so enforcing `kind` in the provider schema
        # made the model invent/repeat an irrelevant field on confirmation.
        required=[],
        discovery=True,
        # Every hint here is deliberately multi-word — a bare "assign"
        # substring-matches "assign the food-safety training to Maria" and
        # routing.HINT_INDEX / prompt.build_discovery_block would then steer
        # a training-assignment ask at this tool instead of assign_training.
        intent_hints=("swap shift", "reassign shift", "assign a shift", "put someone on",
                      "move shift", "cancel shift", "cover for"),
    ),
    _tool(
        "list_assets", "read",
        "List the assets (offer letters, incident reports, discipline "
        "records, schedule changes, inventory rows, ...) created from this "
        "thread — or the whole company with scope='company'. Use this to "
        "answer 'what have we made' and to find an existing artifact before "
        "creating a duplicate.",
        properties={
            "scope": types.Schema(type=types.Type.STRING, enum=["thread", "company"]),
            "asset_type": types.Schema(type=types.Type.STRING),
            "limit": types.Schema(type=types.Type.INTEGER),
        },
        intent_hints=("what have we made", "what did we create", "assets we created",
                      "list the assets", "offer letters we created"),
    ),
    _tool(
        "finish", "finish",
        "End the turn. Call this once you've done what was asked, or to "
        "explain why you couldn't — describe ONLY what actually happened, "
        "never what you intended to do.",
        properties={"message": types.Schema(type=types.Type.STRING)},
        required=["message"],
    ),
)

TOOLS_BY_NAME: dict[str, HuumeTool] = {t.name: t for t in TOOLS}


def tool_declarations(*, allowed_names=None) -> list[types.FunctionDeclaration]:
    if allowed_names is None:
        return [t.declaration for t in TOOLS]
    allowed = set(allowed_names)
    return [t.declaration for t in TOOLS if t.name in allowed]
