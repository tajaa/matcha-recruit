"""Small pure text/state helpers shared across the package: company-context
rendering, JSON fence stripping, reply-field extraction, and skill inference
from a thread's current_state.
"""
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _build_company_context(profile: dict) -> str:
    """Format non-null company profile fields into a labeled block for the system prompt."""
    if not profile:
        return ""
    # Personal (individual) workspaces should NOT receive the HR/business framing.
    # They are auto-created companies that exist for billing/ownership only.
    if profile.get("is_personal"):
        return "\n(Personal workspace — no business/HR context. Respond as a general-purpose assistant.)\n"
    lines = []
    label_map = {
        "name": "Company Name",
        "industry": "Industry",
        "size": "Company Size",
        "headquarters_state": "Headquarters State",
        "headquarters_city": "Headquarters City",
        "work_arrangement": "Work Arrangement",
        "default_employment_type": "Default Employment Type",
        "benefits_summary": "Benefits Package",
        "pto_policy_summary": "PTO Policy",
        "compensation_notes": "Compensation Structure",
        "company_values": "Company Values",
        "ai_guidance_notes": "Special Instructions",
        "compliance_locations": "Compliance Locations (active)",
        "jurisdiction_requirements_summary": "Jurisdiction Requirements by Category",
    }
    for key, label in label_map.items():
        value = profile.get(key)
        if value:
            lines.append(f"- {label}: {value}")
    if not lines:
        return ""
    return "\nCompany profile:\n" + "\n".join(lines) + "\n"


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences and fix common JSON issues from model output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Fix raw newlines inside JSON string values.
    # Gemini sometimes wraps long strings across lines, producing bare newlines
    # inside JSON strings which json.loads() rejects.
    # Strategy: replace newlines that occur inside quoted strings with \\n.
    try:
        json.loads(text)
        return text  # Already valid
    except json.JSONDecodeError:
        pass

    # Escape unescaped newlines within string values
    fixed = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            fixed.append(ch)
            escape_next = False
            continue
        if ch == '\\':
            fixed.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            fixed.append(ch)
            continue
        if in_string and ch == '\n':
            fixed.append('\\n')
            continue
        if in_string and ch == '\r':
            continue
        fixed.append(ch)
    return ''.join(fixed)


def _extract_reply_field(raw_text: str) -> Optional[str]:
    """Best-effort salvage of the `reply` value from a malformed Gemini JSON
    response. Used when json.loads has already failed — we don't want the
    client to see the full `{"mode":..., "reply":"...", ...}` envelope.

    Strategy:
    1. Try to locate `"reply":"..."` with a tolerant regex that handles
       escaped quotes inside the string.
    2. If found, unescape standard JSON escapes (\\n, \\", \\\\) and return.
    3. Return None if nothing looks like a reply field.
    """
    if not raw_text:
        return None
    # Tolerant match: "reply" (with optional whitespace) : "value-with-escapes"
    # (?:\\.|[^"\\])*  matches any char that isn't an unescaped quote, including
    # escaped sequences. re.DOTALL lets the value span newlines.
    match = re.search(
        r'"reply"\s*:\s*"((?:\\.|[^"\\])*)"',
        raw_text,
        re.DOTALL,
    )
    if not match:
        return None
    value = match.group(1)
    # Unescape common JSON escape sequences. json.loads handles this correctly
    # if we wrap the value in quotes — safer than manual replacement.
    try:
        return json.loads('"' + value + '"')
    except json.JSONDecodeError:
        # Fall back to the raw captured value.
        return value


# State keys written only by the thread resume-batch route
# (routes/matcha_work/thread_uploads.py:upload_thread_resume). Filtered as a
# set: `candidates` alone maps to resume_batch, but the leftover
# `batch_status` would then match the onboarding branch below.
_RESUME_BATCH_KEYS = frozenset({"candidates", "batch_status", "total_count", "analyzed_count"})


def _infer_skill_from_state(current_state: dict, *, huume_mode: bool = False) -> str:
    """Infer the active skill from current_state contents.

    huume_mode: a Huume thread poisoned with resume-batch state (uploaded PDFs
    auto-classified before the huume_mode guard existed) must not surface as
    resume_batch/onboarding — the panel and prompt injection re-latch the model.
    Non-destructive: the keys stay in state, so toggling Huume off restores the
    recruiting view.
    """
    if huume_mode and current_state:
        current_state = {k: v for k, v in current_state.items() if k not in _RESUME_BATCH_KEYS}
    if not current_state:
        return "chat"
    if "hr_action" in current_state:
        return "hr_pilot"
    if "language_tutor" in current_state:
        return "language_tutor"
    if any(k in current_state for k in ("candidate_name", "position_title", "salary", "salary_range_min")):
        return "offer_letter"
    if any(k in current_state for k in ("overall_rating", "review_title", "review_request_statuses", "review_expected_responses")):
        return "review"
    if any(k.startswith("handbook_") for k in current_state):
        return "handbook"
    # Policy threads can accumulate generic workbook-like keys over time.
    # Keep explicit policy_* state authoritative so the UI renders the policy preview.
    if any(k.startswith("policy_") for k in current_state):
        return "policy"
    if "sections" in current_state or "workbook_title" in current_state:
        return "workbook"
    if "project_sections" in current_state or "project_title" in current_state:
        return "project"
    if "inventory_items" in current_state:
        return "inventory"
    if "candidates" in current_state:
        return "resume_batch"
    if any(k in current_state for k in ("employees", "batch_status")):
        return "onboarding"
    if any(k in current_state for k in ("presentation_title", "slides")):
        return "presentation"
    return "chat"
