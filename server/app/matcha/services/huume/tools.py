"""Huume's tool registry — the loop's vocabulary.

Mirrors the shape of `cappe/services/merlin_ops.py` (frozen-dataclass entries
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
    "employee", "training_status", "schedule", "incidents",
)


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
        "schedule for the next 7 days, recent incident counts by type/severity "
        "(never named individuals — that's a legal record), or credential/"
        "license expirations. Call this before drafting an offer if you're "
        "unsure whether the candidate already has one, or before building a "
        "plan to check what integrations are actually connected.",
        properties={
            "topic": types.Schema(type=types.Type.STRING, enum=list(LOOKUP_TOPICS)),
            "query": types.Schema(type=types.Type.STRING, description="Optional free-text filter, e.g. a candidate/employee name or email."),
        },
        required=["topic"],
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
        "admin changes their mind. target='action' voids the pending "
        "send_offer (it will no longer execute even if confirmed). "
        "target='plan' discards the onboarding plan for offer_id — refused "
        "once it's already executing or done, since steps that already ran "
        "can't be undone from here. Pass offer_id whenever more than one "
        "plan is active.",
        properties={
            "target": types.Schema(type=types.Type.STRING, enum=["action", "plan"]),
            "offer_id": types.Schema(type=types.Type.STRING, description="Required for target='plan' when more than one plan is active."),
        },
        required=["target"],
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
        "section drafts become ONE new draft handbook, policy drafts become "
        "draft policies. Only call this when the admin explicitly asks to "
        "promote, on a LATER message than the one that drafted them. Pass "
        "draft_ids naming exactly which drafts (see Current staged state), "
        "or omit it to promote all pending drafts from earlier turns. "
        "Everything promoted still lands as a DRAFT handbook/policy the "
        "admin publishes through the normal flow.",
        properties={
            "draft_ids": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="Pending draft ids to promote. Omit for all pending drafts from earlier turns.",
            ),
            "handbook_title": types.Schema(type=types.Type.STRING, description="Title for the new draft handbook when promoting section drafts."),
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
