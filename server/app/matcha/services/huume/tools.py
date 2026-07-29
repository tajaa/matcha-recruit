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
    "pto_leave", "policies", "discipline", "compliance", "documents",
)

# record_type values show_record accepts — the single source both the tool
# schema's enum and record_view.py's dispatch table read from.
SHOW_RECORD_TYPES = ("incident", "er_case", "employee", "credential")


@dataclass(frozen=True)
class HuumeTool:
    name: str
    kind: str  # read | write | staged | finish
    declaration: types.FunctionDeclaration


def _tool(name: str, kind: str, description: str, *, properties: dict | None = None, required: list[str] | None = None) -> HuumeTool:
    return HuumeTool(
        name=name,
        kind=kind,
        declaration=types.FunctionDeclaration(
            name=name,
            description=description,
            parameters=types.Schema(type=types.Type.OBJECT, properties=properties or {}, required=required or []),
        ),
    )


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
        "status, date, location, a short description snippet — never named "
        "individuals, that's a legal record), ER (employment-relations) case "
        "counts by status plus a recent list (id, case number, title, status, "
        "category, outcome — never the description or involved employees), "
        "credential/license expirations, upcoming approved PTO/leave plus "
        "PENDING PTO requests awaiting a decision, active policy titles, "
        "discipline record counts by status (never narrative details), open "
        "compliance requirement counts by category, or documents still "
        "awaiting employee signature. Call this before drafting an offer if "
        "you're unsure whether the candidate already has one, or before "
        "building a plan to check what integrations are actually connected. "
        "Use show_record with an id from a list here (incident/er_case/"
        "employee/credential) to open that record in the admin's side panel.",
        properties={
            "topic": types.Schema(type=types.Type.STRING, enum=list(LOOKUP_TOPICS)),
            "query": types.Schema(type=types.Type.STRING, description="Optional free-text filter, e.g. a candidate/employee name or email."),
            "days": types.Schema(type=types.Type.INTEGER, description="Lookback window in days for topic='incidents'. Default 90, max 365."),
        },
        required=["topic"],
    ),
    _tool(
        "show_record", "read",
        "Open a specific record in the admin's side panel for review — use "
        "when the admin asks to see/view/open/inspect a record. record_type: "
        "incident (ids from lookup_context topic='incidents'), er_case "
        "(topic='er_cases'), employee (topic='roster' or 'employee'), "
        "credential (topic='credentials'). Never guess an id.",
        properties={
            "record_type": types.Schema(type=types.Type.STRING, enum=list(SHOW_RECORD_TYPES)),
            "record_id": types.Schema(type=types.Type.STRING),
        },
        required=["record_type", "record_id"],
    ),
    _tool(
        "draft_offer_letter", "write",
        "Create or revise a DRAFT offer letter. Never sends anything to the "
        "candidate — that's the separate send_offer tool, which requires a "
        "confirm. Pass offer_id to revise an existing draft; omit it to "
        "create a new one. A new draft needs at minimum candidate_name and "
        "position_title.",
        properties={
            "offer_id": types.Schema(type=types.Type.STRING, description="UUID of an existing draft to revise. Omit to create a new offer."),
            "candidate_name": types.Schema(type=types.Type.STRING),
            "candidate_email": types.Schema(type=types.Type.STRING),
            "position_title": types.Schema(type=types.Type.STRING),
            "salary": types.Schema(type=types.Type.STRING, description="Free-text salary, e.g. '$95,000/year'."),
            "start_date": types.Schema(type=types.Type.STRING, description="ISO date YYYY-MM-DD."),
            "employment_type": types.Schema(type=types.Type.STRING, description="e.g. 'Full-Time Exempt', 'Part-Time', 'Contract'."),
            "location": types.Schema(type=types.Type.STRING, description="Work location or state, e.g. 'Remote' or 'CA'."),
        },
    ),
    _tool(
        "send_offer", "staged",
        "Send an existing DRAFT offer letter to the candidate's email as a "
        "sign link. This is a real, user-facing action — it STAGES the send "
        "for the admin's confirmation and does not actually send until they "
        "reply confirming on a later turn. Requires the offer to already "
        "have a candidate_email set (use draft_offer_letter to add one).",
        properties={"offer_id": types.Schema(type=types.Type.STRING)},
        required=["offer_id"],
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
        "— a send_offer or a draft_discipline write-up (it will no longer "
        "execute even if confirmed). target='plan' discards the onboarding "
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


def tool_declarations() -> list[types.FunctionDeclaration]:
    return [t.declaration for t in TOOLS]
