"""OSHA Privacy Case determination + clinical-description composition.

OSHA's privacy-case rule (29 CFR 1904.29(b)(6)-(b)(10)) requires the injured
employee's NAME to be withheld from the 300 log / 301 form — replaced with the
literal string ``"Privacy Case"`` — when the case falls into one of six
sensitive categories, while the real name is kept on a separate confidential
list (resolved by a privileged endpoint, not on the public log).

This module is the deterministic core: given the structured incident signals it
returns ``(is_privacy_case, reason)``. It holds NO free-text/PHI logic and calls
NO model — masking must never depend on an LLM or a network call (a fail-open
redactor is exactly the bug this replaces). Free-text is organized into these
structured fields upstream (the IR Copilot / Gemini "data organization" layer);
here we only apply the rule.

Pairs with :mod:`app.core.services.osha_redaction` (which still scrubs the
structured-ID regex patterns out of the Location field). The 300-log
*Description* is no longer the raw reporter narrative —
:func:`compose_clinical_description` builds an OSHA-format injury phrase from the
structured fields, so no third-party name can reach the export by construction.
"""
from __future__ import annotations

from typing import Optional


PRIVACY_NAME = "Privacy Case"
PRIVACY_DESCRIPTION_PLACEHOLDER = "Description withheld — see confidential incident record"

# Reasons in evaluation order; determine_privacy_case returns the first match.
PRIVACY_CASE_REASONS = (
    "intimate_injury",
    "sexual_assault",
    "mental_illness",
    "infectious_pathogen",
    "contaminated_sharps",
    "voluntary_opt_out",
)

# category_data.body_parts values that make a case an intimate-injury privacy
# case. Canonical lowercased keys — the frontend body-part picker uses the same.
INTIMATE_BODY_PARTS = frozenset({
    "genitals",
    "reproductive_system",
    "groin",
    "breast",
    "buttocks",
    "perineum",
    "anus",
})

# infectious_agent values that trigger the pathogen privacy case (HIV / Hep / TB).
INFECTIOUS_PRIVACY_AGENTS = frozenset({"hiv", "hepatitis", "tuberculosis"})


def _truthy(value) -> bool:
    """Coerce a structured-signal value to bool.

    The signals may arrive as a real JSON bool (the opt-out checkbox) or as a
    string/number from the Gemini extraction layer ("true", "yes", 1). A bare
    ``bool("false")`` is ``True``, so route strings through here instead.
    """
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "y", "t")
    return bool(value)


def _is_illness(osha_injury_type: Optional[str]) -> bool:
    """True when the OSHA M-column class is an illness, not a standard injury.

    The OSHA injury/illness type is the M-column class on the 300A
    (``injury`` | ``skin_disorder`` | ``respiratory`` | ``poisoning`` |
    ``hearing_loss`` | ``mental_illness`` | ``other_illness``). Everything that
    is not ``injury`` (or empty) counts as an illness for the opt-out rule.
    """
    if not osha_injury_type:
        return False
    return osha_injury_type.strip().lower() not in ("", "injury")


def determine_privacy_case(
    category_data: Optional[dict],
    osha_injury_type: Optional[str],
    employee_privacy_requested: bool,
) -> tuple[bool, Optional[str]]:
    """Decide whether an incident is an OSHA privacy case, and why.

    Pure + defensive: tolerates ``None`` / missing keys. Returns
    ``(True, reason)`` for the first matching condition in
    :data:`PRIVACY_CASE_REASONS` order, else ``(False, None)``.

    Args:
        category_data: the incident's ``category_data`` JSONB (safety fields).
        osha_injury_type: the OSHA M-column class (``osha_form_301_data.injury_type``).
        employee_privacy_requested: the employee's explicit withhold-name opt-out.
    """
    cd = category_data or {}

    # 1. Intimate / reproductive body part.
    body_parts = cd.get("body_parts") or []
    if any(str(bp).strip().lower() in INTIMATE_BODY_PARTS for bp in body_parts):
        return True, "intimate_injury"

    # 2. Sexual assault.
    if _truthy(cd.get("from_sexual_assault")):
        return True, "sexual_assault"

    # 3. Work-related mental illness.
    if (osha_injury_type or "").strip().lower() == "mental_illness":
        return True, "mental_illness"

    # 4. HIV / Hepatitis / Tuberculosis.
    if (cd.get("infectious_agent") or "").strip().lower() in INFECTIOUS_PRIVACY_AGENTS:
        return True, "infectious_pathogen"

    # 5. Needlestick / cut from a contaminated sharp.
    if _truthy(cd.get("contaminated_sharps")):
        return True, "contaminated_sharps"

    # 6. Voluntary opt-out — illness AND the employee asked to withhold the name.
    if _truthy(employee_privacy_requested) and _is_illness(osha_injury_type):
        return True, "voluntary_opt_out"

    return False, None


def _humanize(token: str) -> str:
    """Canonical body-part / field key -> display phrase ("left_hand" -> "left hand")."""
    return str(token).replace("_", " ").strip()


def compose_clinical_description(category_data: Optional[dict]) -> Optional[str]:
    """Build an OSHA-format injury phrase from structured fields.

    e.g. ``"Laceration to left hand from needlestick"``. Returns ``None`` when
    there is no structured content to describe (the caller substitutes
    :data:`PRIVACY_DESCRIPTION_PLACEHOLDER`).

    Intentionally consumes ONLY structured fields (``injury_type``,
    ``body_parts``, ``equipment_involved``) — never the free-text narrative — so
    no patient/third-party name can reach the OSHA export.
    """
    cd = category_data or {}

    injury_type = (cd.get("injury_type") or "").strip()
    body_parts = [b for b in (cd.get("body_parts") or []) if str(b).strip()]
    equipment = (cd.get("equipment_involved") or "").strip()

    if not injury_type and not body_parts and not equipment:
        return None

    nature = injury_type.capitalize() if injury_type else "Injury"
    if body_parts:
        joined = ", ".join(_humanize(b) for b in body_parts)
        phrase = f"{nature} to {joined}"
    else:
        phrase = nature
    if equipment:
        phrase = f"{phrase} from {equipment}"
    return phrase
