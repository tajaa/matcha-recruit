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

LOOKUP_TOPICS = ("roster", "templates", "integrations", "training", "credentials", "offers")


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
        "Look up read-only grounding data before drafting or acting: the "
        "existing roster, onboarding task templates, connected integrations "
        "(Google Workspace/Slack), new-hire training rules, or prior offers. "
        "Call this before drafting an offer if you're unsure whether the "
        "candidate already has one, or before building a plan to check what "
        "integrations are actually connected.",
        properties={
            "topic": types.Schema(type=types.Type.STRING, enum=list(LOOKUP_TOPICS)),
            "query": types.Schema(type=types.Type.STRING, description="Optional free-text filter, e.g. a candidate name or email."),
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
        "Approve and run steps of the currently staged onboarding plan. "
        "Only call this after the admin has explicitly said to go ahead — "
        "either with all of it ('approve everything', 'go ahead') or "
        "specific steps by name ('just create the employee and send the "
        "invite'). Pass step_keys naming exactly which steps they approved, "
        "or omit it / pass an empty list to mean all remaining proposed "
        "steps. Steps missing a required feature or integration are "
        "skipped and reported, not executed — that's not an error.",
        properties={
            "step_keys": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="Plan step keys to approve+run, e.g. ['create_employee','portal_invitation']. Omit for all remaining proposed steps.",
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
