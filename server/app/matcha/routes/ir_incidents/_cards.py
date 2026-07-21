"""IR Copilot card builders — the presentational card vocabulary.

Split out of ``_shared.py`` (L5): the pure ``build_*_card`` factories, their
constants (OSHA injury types, emergency-alert copy, root-cause prompt labels)
and ``compose_root_cause_text``. These are self-contained (stdlib only) — they
build the Copilot card dicts and hold no DB or request state. The DB-backed card
plumbing (``next_case_step``, ``ensure_osha_case_rows``, ``fetch_osha_case_rows``,
``_persist_osha_emergency_alert``) stays in ``_shared.py`` and imports these.

``_shared.py`` re-exports every name here, so existing
``from ._shared import build_osha_...`` / ``from ._shared import OSHA_INJURY_...``
imports keep working unchanged.
"""

from typing import Optional

from app.core.services.osha_privacy import (
    PRIVACY_CASE_REASONS,
    PRIVACY_CASE_REASON_LABELS,
)

# The three root-cause interview steps, in order. Lives here with the card
# builders + compose_root_cause_text that walk it; re-exported by _shared.
ROOT_CAUSE_INTERVIEW_STEPS: tuple[str, ...] = ("hazard", "why", "prevention")

# OSHA 300 form M-column injury/illness type values. Stashed in
# ir_incidents.osha_form_301_data->>'injury_type' so 300A aggregation
# can group on them without an Alembic migration.
OSHA_INJURY_TYPES = {
    "injury", "skin_disorder", "respiratory",
    "poisoning", "hearing_loss", "mental_illness", "other_illness",
}

OSHA_INJURY_TYPE_LABELS = {
    "injury": "Standard Injury",
    "skin_disorder": "Skin Disorder",
    "respiratory": "Respiratory Condition",
    "poisoning": "Poisoning",
    "hearing_loss": "Hearing Loss",
    # mental_illness is also an OSHA Privacy Case trigger (29 CFR 1904.29) — its
    # presence masks the employee name on the 300/301 log. Aggregates under the
    # 300A "All Other Illnesses" M-column (see _aggregate_300a fallback).
    "mental_illness": "Mental Illness",
    "other_illness": "All Other",
}

OSHA_EMERGENCY_ALERT_CARD_ID = "osha_emergency_alert"

OSHA_EMERGENCY_HOTLINE = "1-800-321-6742"

OSHA_REPORTING_WINDOW = "8 to 24 hours"

def build_osha_emergency_alert_card() -> dict:
    """Build the static emergency alert card payload (29 CFR 1904.39).

    Same shape every emit so the frontend can render it with a fixed
    component. ``content`` is the title (used as message_type='card'
    content column); the full card sits under ``metadata.card`` per the
    transcript convention.
    """
    return {
        "id": OSHA_EMERGENCY_ALERT_CARD_ID,
        "title": "⚠️ CRITICAL: OSHA Reporting Required",
        "recommendation": (
            "Based on the severity of this incident, you may be legally "
            "required to report this directly to OSHA within "
            f"{OSHA_REPORTING_WINDOW}."
        ),
        "rationale": (
            "29 CFR 1904.39 mandates calling OSHA within 8 hours for any "
            "work-related fatality and within 24 hours for any in-patient "
            "hospitalization, amputation, or loss of an eye."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "osha_emergency_alert",
            "label": "I've reported it",
            "phone": OSHA_EMERGENCY_HOTLINE,
            "deadline": OSHA_REPORTING_WINDOW,
        },
    }

def build_osha_recordable_query_card() -> dict:
    """Yes/No: does the incident qualify as an OSHA recordable event?"""
    return {
        "id": "osha_recordable_query",
        "title": "OSHA Recordable Event",
        "recommendation": "Does this qualify as an OSHA recordable event?",
        "rationale": (
            "Treatment beyond on-site first aid generally makes an injury "
            "OSHA recordable (29 CFR 1904.7). Confirm so we can populate "
            "the OSHA 300/300A logs."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "osha_recordable_query",
            "choices": [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        },
    }

def build_osha_days_type_query_card(*, case_key: str = "reporter", employee_name: Optional[str] = None) -> dict:
    """Days Away / Job Restriction / Neither — drives this case's classification.

    Per injured employee: ``case_key`` identifies the ir_osha_case_details row
    the answer writes to; ``employee_name`` is shown so a multi-injured chain is
    unambiguous about who each answer is for.
    """
    who = f" for {employee_name}" if employee_name else ""
    return {
        "id": "osha_days_type_query",
        "title": "OSHA Case Classification",
        "recommendation": (
            f"Did this result in days away from work or a temporary job restriction{who}?"
        ),
        "rationale": (
            "Drives column J/K/L on OSHA Form 300 (case classification). "
            "Pick Neither for medical-treatment-only cases."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "osha_days_type_query",
            "case_key": case_key,
            "employee_name": employee_name,
            "choices": [
                {"label": "Days Away", "value": "days_away"},
                {"label": "Job Restriction", "value": "restricted_duty"},
                {"label": "Neither", "value": "neither"},
            ],
        },
    }

def build_osha_days_count_card(*, target_field: str, pending_classification: str,
                               case_key: str = "reporter", employee_name: Optional[str] = None) -> dict:
    """Numeric input: how many days away / restricted for this case?"""
    label_word = "away from work" if target_field == "days_away_from_work" else "on job restriction"
    who = f" ({employee_name})" if employee_name else ""
    return {
        "id": f"osha_days_count__{pending_classification}",
        "title": f"Days {label_word.title()}",
        "recommendation": f"How many days {label_word}{who}?",
        "rationale": "Enter the total days (1-365). This populates the OSHA 300 day-count columns.",
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "numeric_input",
            "label": "Save",
            "target_field": target_field,
            "pending_classification": pending_classification,
            "case_key": case_key,
            "input_label": "Days",
            "input_min": 1,
            "input_max": 365,
        },
    }

def build_osha_injury_type_query_card(*, case_key: str = "reporter", employee_name: Optional[str] = None) -> dict:
    """6-button picker — OSHA 300 M-column injury/illness type for this case."""
    who = f" for {employee_name}" if employee_name else ""
    return {
        "id": "osha_injury_type_query",
        "title": "Injury / Illness Type",
        "recommendation": f"How would you classify this injury{who}?",
        "rationale": (
            "Drives the M-columns on OSHA Form 300A (Injury / Skin Disorder / "
            "Respiratory / Poisoning / Hearing Loss / All Other Illnesses)."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "osha_injury_type_query",
            "case_key": case_key,
            "employee_name": employee_name,
            "choices": [
                {"label": OSHA_INJURY_TYPE_LABELS[k], "value": k}
                for k in ("injury", "skin_disorder", "respiratory", "poisoning", "hearing_loss", "mental_illness", "other_illness")
            ],
        },
    }

def build_privacy_case_query_card(*, employee_key: str, employee_name: str, suggested_reason: Optional[str] = None) -> dict:
    """Per-injured-employee OSHA Privacy Case prompt (29 CFR 1904.29(b)(6)-(b)(10)).

    Extends the OSHA recordable chain: fires only after an incident is confirmed
    recordable (so it WILL be posted on the 300/301 log). Asks whether THIS
    injured employee's name must be withheld — shown as "Privacy Case" — forcing
    one of the 6 sensitive categories or "Not a privacy case". The answer is the
    source of truth, stored per employee in ``category_data.privacy_cases[key]``;
    the real name always stays on the confidential reference list. The
    ``determine_privacy_case`` suggestion is pre-highlighted, but the human decides.
    """
    choices = [{"label": PRIVACY_CASE_REASON_LABELS[r], "value": r} for r in PRIVACY_CASE_REASONS]
    choices.append({"label": "Not a privacy case", "value": "none"})
    return {
        "id": "privacy_case_query",
        "title": "OSHA Privacy Case?",
        "recommendation": f"Is this a privacy case for {employee_name}?",
        "rationale": (
            "OSHA 29 CFR 1904.29(b)(6)-(b)(10): for these 6 sensitive categories the "
            "employee's name is withheld from the posted 300/301 log (shown as "
            "\"Privacy Case\"). The real name stays on the confidential reference list."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "privacy_case_query",
            "employee_key": employee_key,
            "employee_name": employee_name,
            "suggested_value": suggested_reason or "none",
            "choices": choices,
        },
    }

ROOT_CAUSE_PROMPTS = {
    "hazard": "What was the hazard?",
    "why": "Why did it happen?",
    "prevention": "How can we prevent it?",
}

ROOT_CAUSE_PLAINTEXT_LABELS = {
    "hazard": "Hazard",
    "why": "Why it happened",
    "prevention": "Prevention",
}

def build_log_root_cause_query_card() -> dict:
    """Yes/No: kick off the root-cause interview chain."""
    return {
        "id": "log_root_cause_query",
        "title": "Log Root Cause",
        "recommendation": "Would you like to log the root cause?",
        "rationale": (
            "Capture the hazard, why it happened, and how to prevent it in "
            "your own words. We save the answers verbatim — no AI guesses."
        ),
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "log_root_cause_query",
            "choices": [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        },
    }

def build_root_cause_text_card(*, step: str) -> dict:
    """One text_input card per interview step. ``step`` must be in
    ROOT_CAUSE_INTERVIEW_STEPS — the dispatcher reads it from action.target_field
    to know which JSONB key to write and which step is next."""
    if step not in ROOT_CAUSE_INTERVIEW_STEPS:
        raise ValueError(f"Unknown root-cause step: {step}")
    prompt = ROOT_CAUSE_PROMPTS[step]
    return {
        "id": f"root_cause_interview__{step}",
        "title": f"Root cause — {ROOT_CAUSE_PLAINTEXT_LABELS[step]}",
        "recommendation": prompt,
        "rationale": (
            "Type your answer in your own words. Saved exactly as written."
        ),
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "text_input",
            "label": "Save",
            "target_field": step,
            "prompt_text": prompt,
            "input_label": "Answer",
            "input_rows": 3,
        },
    }

def build_root_cause_logged_ack_card() -> dict:
    """Final 'Root cause logged' ack — informational, no further action."""
    return {
        "id": "root_cause_logged",
        "title": "Root cause logged",
        "recommendation": "Saved your hazard / why / prevention answers.",
        "rationale": (
            "The combined entry is now on the incident and feeds the OSHA 301 "
            "form, broker reports, and the AI Analysis tab."
        ),
        "priority": "low",
        "blockers": [],
        "action": {
            "type": "request_info",
            "label": "Got it",
        },
    }

def compose_root_cause_text(interview: dict) -> str:
    """Render the three interview answers into the plain-text format we
    write to ir_incidents.root_cause TEXT. Missing steps surface as empty
    blocks rather than silently dropping — keeps the schema consistent.
    """
    parts: list[str] = []
    for step in ROOT_CAUSE_INTERVIEW_STEPS:
        answer = (interview or {}).get(step) or ""
        label = ROOT_CAUSE_PLAINTEXT_LABELS[step]
        parts.append(f"{label}: {answer.strip()}")
    return "\n\n".join(parts)

def build_osha_close_confirmation_card() -> dict:
    """Final close card after the OSHA chain completes."""
    return {
        "id": "osha_close_confirmation",
        "title": "Close incident",
        "recommendation": "OSHA capture complete. Close this incident?",
        "rationale": "All OSHA 300 fields recorded. You can close the incident now.",
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "close_incident",
            "label": "Close incident",
        },
    }

def build_treatment_query_card() -> dict:
    """Yes/No: was treatment provided beyond basic on-site first aid?

    The injury-assessment gate. A "yes" makes the injury OSHA-recordable
    (29 CFR 1904.7) and kicks off the recordable chain. Handled by
    ``_handle_quick_reply`` under quick_reply_kind 'treatment_query', which
    writes category_data.treatment_beyond_first_aid.
    """
    return {
        "id": "treatment_query",
        "title": "Injury Assessment",
        "recommendation": "Was any treatment provided beyond basic on-site first aid?",
        "rationale": (
            "Treatment beyond first aid — stitches, prescription medication, "
            "work restrictions, or similar — generally makes an injury OSHA "
            "recordable (29 CFR 1904.7)."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "treatment_query",
            "choices": [
                {"label": "Yes — beyond first aid", "value": "yes"},
                {"label": "No — first aid only", "value": "no"},
            ],
        },
    }

def build_request_documents_card() -> dict:
    """Prompt the user to attach supporting documents to the incident.

    Handled by the ``request_documents`` action in accept_copilot_card, which
    re-checks the ir_incident_documents count and marks
    category_data.documents_prompted so the flow advances whether the user
    uploads or explicitly skips. The frontend opens the Documents upload zone.
    """
    return {
        "id": "request_documents",
        "title": "Attach supporting documents",
        "recommendation": (
            "Upload any photos, witness statements, medical or first-aid "
            "records, or incident forms related to this report."
        ),
        "rationale": (
            "Documentation strengthens the record for OSHA, insurance, and "
            "legal defense. Attach what you have — or skip if there's nothing "
            "to add."
        ),
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "request_documents",
            "label": "Open upload",
        },
    }

def build_investigation_notes_card(questions: list[str] | None = None) -> dict:
    """Capture investigation findings as free text, with AI-generated
    incident-specific questions shown inline.

    ``questions`` come from the cached ``followup_questions`` analysis. They
    render under the card (interview_questions) so the user has concrete
    prompts to answer instead of a blank box. Handled by the
    ``investigation_notes`` branch of ``_handle_text_input``, which writes
    category_data.investigation_notes + sets investigation_documented.
    """
    qs = [q for q in (questions or []) if isinstance(q, str) and q.strip()][:6]
    return {
        "id": "investigation_notes",
        "title": "Document the investigation",
        "recommendation": (
            "Answer what you can below — who was involved, what happened, what's "
            "been done so far, and anything still unknown."
        ),
        "rationale": (
            "Thorough notes now make the OSHA record, insurance claim, and any "
            "legal review defensible later. This goes on the incident file."
        ),
        "priority": "high",
        "blockers": [],
        "interview_questions": qs or None,
        "action": {
            "type": "text_input",
            "label": "Save findings",
            "target_field": "investigation_notes",
            "prompt_text": "Investigation findings",
            "input_label": "Findings",
            "input_rows": 5,
        },
    }

def build_osha_clean_description_card(prefilled: str = "", *, cleansed: bool = True) -> dict:
    """Approve-or-edit the name-free OSHA 300 Description (Column F).

    Reuses the text_input card type, prefilled with the draft. Two modes:

    - ``cleansed=True`` (default): the prefill is an AI name-stripped draft (or
      the structured clinical phrase) — copy tells the human to approve/edit.
    - ``cleansed=False``: AI was unavailable, so the prefill is the RAW incident
      narrative (may contain names) seeded for the human to rewrite — copy tells
      them to strip names before approving. The raw text is display-only and is
      NOT persisted as a draft; only the approved submission ever prints.

    The submitted text becomes the printed Column F.
    ``target_field='osha_clean_description'`` routes the answer to the dedicated
    branch of ``_handle_text_input``. Emitted once per incident, after
    recordable=yes, before the per-case capture loop.
    """
    if cleansed:
        recommendation = (
            "Confirm the injury/illness description for the OSHA 300 log. We "
            "removed every person's name — the 300 log is a posted record. "
            "Approve it as written, or edit the wording first."
        )
    else:
        recommendation = (
            "Rewrite this description for the OSHA 300 log so it names no one "
            "(e.g. \"John slipped\" → \"An employee slipped\"). We couldn't "
            "auto-draft a name-free version, so the original text is shown "
            "below — strip every person's name, then approve. The 300 log is a "
            "posted record."
        )
    return {
        "id": "osha_clean_description_review",
        "title": "Review the OSHA 300 description",
        "recommendation": recommendation,
        "rationale": (
            "Column F is public, so it must name no one (employee, coworker, "
            "patient, or visitor). Real names stay on the confidential incident "
            "record. Only the text you approve here prints to the log."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "text_input",
            "label": "Approve",
            "target_field": "osha_clean_description",
            "prompt_text": "OSHA 300 description (no names)",
            "input_label": "Description",
            "input_rows": 4,
            "prefilled": prefilled or "",
        },
    }
