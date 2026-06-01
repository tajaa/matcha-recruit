"""PII / patient-PHI redaction for OSHA 300 log + 301 form output.

OSHA recordable incidents carry free-text fields (``description``,
``location``, ``treatment``) that, for **healthcare** clients, can leak
*patient*-identifiable information (PHI) into documents that are exported,
filed, and — for the 300A summary — posted publicly. A description like
"Nurse stuck by needle drawing blood from patient John Doe, MRN 44321,
HIV+" must not carry the patient's name/MRN into the log.

This module redacts those fields at generation time. Design:

- **Structured identifiers** (SSN, phone, email, DOB, street address) are
  redacted for **every** client — they never belong on an OSHA log.
- **Patient/PHI identifiers** (MRN, "patient <Name>", NPI, chart/account
  numbers, labeled DOB) are redacted additionally for **healthcare**
  clients (``industry`` healthcare/medical, or any ``healthcare_specialties``).
- **Injury terminology is preserved.** OSHA still requires the log to
  describe the injury and body part. We only strip identifiers; words like
  "laceration", "needlestick", "left wrist" are untouched. The structured
  injury fields (``injury_type``, ``body_parts``, ``classification``) are
  passed through separately and are never run through redaction.

Reuses ``app.core.services.pii_scrubber.PIIScrubber`` for the base
structured patterns; healthcare patterns are layered on as custom patterns.
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.services.pii_scrubber import PIIScrubber

# Healthcare / patient identifiers beyond PIIScrubber's structured set.
# Each value is (regex, replacement). PIIScrubber emits its own
# ``[NAME-N]`` token per pattern; the replacement string here only needs to
# be non-None (None means "skip"). Patterns are intentionally label-anchored
# (MRN:, patient <Name>, NPI …) so they fire on real identifiers, not on
# injury wording.
_HEALTHCARE_PATTERNS: dict[str, tuple[str, str]] = {
    # "MRN 44321", "MRN: 44321", "MR# 4432", "medical record number 88321"
    "mrn": (
        r"\b(?:MRN|MR#|medical\s+record(?:\s*(?:no\.?|number|#))?)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{2,}\b",
        "[MRN-REDACTED]",
    ),
    # National Provider Identifier (10 digits), label-anchored.
    "npi": (
        r"\bNPI\s*[:#]?\s*\d{10}\b",
        "[NPI-REDACTED]",
    ),
    # "patient John Doe", "pt. Jane Smith", "resident Mary Q. Public",
    # "patient name: John Doe". Captures the trailing 1-3 capitalized tokens.
    "patient_name": (
        r"\b(?:patient|pt\.?|resident|client)\s+(?:name\s*[:]?\s*)?"
        r"[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,2}\b",
        "[PATIENT-REDACTED]",
    ),
    # "chart 88321", "account no 4432", "acct# A1234"
    "account_no": (
        r"\b(?:acct|account|chart)\s*(?:no\.?|number|#)?\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{3,}\b",
        "[ACCT-REDACTED]",
    ),
    # "DOB 03/14/1980", "DOB: 1980-03-14", "date of birth 3/14/80"
    "dob_labeled": (
        r"\b(?:DOB|date\s+of\s+birth)\s*[:#]?\s*\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b",
        "[DOB-REDACTED]",
    ),
}

# Base structured patterns we DON'T want for OSHA free text. ``zip_code``
# (\d{5}) and the broad ``drivers_license`` / ``passport`` shapes fire on
# room numbers, asset tags, and case numbers that legitimately belong in a
# "where/how" description. SSN / phone / email / DOB / street address stay on.
_SKIP_BASE_PATTERNS = {"zip_code", "drivers_license", "passport", "bank_account"}


def redact_osha_text(text: Optional[str], *, healthcare: bool) -> Optional[str]:
    """Redact PII (and patient PHI when ``healthcare``) from one free-text field.

    Returns the redacted string, or the input unchanged if it's empty/None.
    Idempotent on already-redacted text (the ``[...-REDACTED]`` /
    ``[NAME-N]`` tokens contain no PII to re-match).
    """
    if not text or not text.strip():
        return text

    custom = _HEALTHCARE_PATTERNS if healthcare else None
    scrubber = PIIScrubber(custom_patterns=custom, skip_patterns=_SKIP_BASE_PATTERNS)
    scrubbed, _ = scrubber.scrub(text)
    return scrubbed


def osha_text_has_phi(text: Optional[str], *, healthcare: bool) -> bool:
    """Return True if ``text`` still contains detectable PII/PHI.

    Used by tests (and an optional pre-commit guard) to assert that a field
    was actually scrubbed before it lands in exported output. Mirrors the
    pattern set used by :func:`redact_osha_text`.
    """
    if not text:
        return False

    base = {
        name: pat
        for name, (pat, repl) in PIIScrubber.PATTERNS.items()
        if repl is not None and name not in _SKIP_BASE_PATTERNS
    }
    patterns = dict(base)
    if healthcare:
        patterns.update({name: pat for name, (pat, _r) in _HEALTHCARE_PATTERNS.items()})

    for pat in patterns.values():
        if re.search(pat, text):
            return True
    return False


async def company_is_healthcare(conn, company_id) -> bool:
    """Whether a company is a healthcare/medical client.

    Mirrors the detection in ``er_copilot`` (industry in healthcare/medical,
    or any healthcare_specialties set) so PHI redaction triggers consistently.
    """
    row = await conn.fetchrow(
        "SELECT industry, healthcare_specialties FROM companies WHERE id = $1",
        company_id,
    )
    if not row:
        return False
    industry = (row["industry"] or "").lower()
    return industry in ("healthcare", "health care", "medical") or bool(
        row["healthcare_specialties"]
    )
