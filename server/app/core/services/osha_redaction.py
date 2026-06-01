"""PII / patient-PHI redaction for OSHA 300 log + 301 form output.

OSHA recordable incidents carry free-text fields (``description``,
``location``, ``treatment``) that can leak *patient*-identifiable
information (PHI) into documents that are exported, filed, and — for the
300A summary — posted publicly. A description like "Nurse stuck by needle
drawing blood from patient John Doe, MRN 44321, HIV+" must not carry the
patient's name/MRN onto the log (HIPAA).

This module redacts those fields at generation time. Design:

- **Always-on.** Patient info does not belong on *any* employer's OSHA log,
  so redaction is NOT gated on whether the company is tagged "healthcare"
  (an earlier healthcare-only gate silently let PHI through for everyone
  else — the bug this revision fixes).
- **Identifiers, not injuries.** OSHA still requires the log to describe the
  injury and body part, so only identifiers are stripped — "laceration",
  "needlestick", "left wrist" are untouched. The structured injury fields
  (``injury_type``, ``body_parts``, ``classification``) are passed through
  separately and never run through redaction.
- **Two layers:** PIIScrubber's structured patterns (SSN, phone, email, DOB,
  street address) + the PHI patterns below (MRN, "patient <Name>", NPI,
  chart/account, labeled DOB, titled names).

Keyword anchors are case-insensitive (scoped ``(?i:…)``) so "Patient" at a
sentence start matches as well as "patient"; the name capitalization anchor
stays case-sensitive so injury wording isn't swept up.

Reuses ``app.core.services.pii_scrubber.PIIScrubber``.
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.services.pii_scrubber import PIIScrubber

# Patient / PHI identifiers beyond PIIScrubber's structured set. Each value is
# (regex, replacement); PIIScrubber emits its own ``[NAME-N]`` token per
# pattern, so the replacement string only needs to be non-None (None = skip).
# The KEYWORD in each pattern is wrapped in ``(?i:…)`` so it matches in any
# case; the capitalized-name anchor is left case-sensitive (PIIScrubber.scrub
# applies no global IGNORECASE flag) so it keys on real names, not injury text.
_PHI_PATTERNS: dict[str, tuple[str, str]] = {
    # "MRN 44321", "mrn: 44321", "MR# 4432", "Medical Record Number 88321"
    "mrn": (
        r"(?i:\bMRN|\bMR#|\bmedical\s+record(?:\s*(?:no\.?|number|#))?)"
        r"\s*[:#]?\s*[A-Za-z0-9][A-Za-z0-9-]{2,}\b",
        "[MRN-REDACTED]",
    ),
    # National Provider Identifier (10 digits), label-anchored.
    "npi": (
        r"(?i:\bNPI)\s*[:#]?\s*\d{10}\b",
        "[NPI-REDACTED]",
    ),
    # Two orders, one token (key stays "patient_name" → [PATIENT_NAME-N]):
    #   branch 1 keyword-first:  "patient John Doe", "Patient John", "pt. Jane Smith",
    #     "the patient, Mary Q. Public", "patient named John Doe", "resident: Jane Doe".
    #   branch 2 name-first appositive: "Jazmine, the patient", "Mary Smith, a resident".
    #     Comma is REQUIRED so "Helped the patient" / "Moved the resident" (verb + the
    #     patient — common in injury narratives) don't false-positive. A stoplist
    #     negative-lookahead drops sentence-leading temporal/transition words that
    #     legitimately precede ", the patient" (e.g. "Yesterday, the patient fell").
    "patient_name": (
        r"(?:"
        r"(?i:\b(?:patient|pt\.?|resident|client))"
        r"\s*[:,]?\s*(?:(?i:named|name)\s*:?\s*)?"
        r"[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[A-Z]\.)){0,2}"
        r"|"
        r"\b(?!(?:The|An?|Yesterday|Today|Tonight|Earlier|Later|Then|When|While|During|"
        r"After|Before|Suddenly|Meanwhile|However|Although|Unfortunately|Initially|"
        r"Eventually|Finally|Now|Once|Soon|Subsequently|Apparently|Reportedly)\b)"
        r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}"
        r"\s*,\s+(?i:the|an?)\s+"
        r"(?i:patient|resident|client)\b"
        r")",
        "[PATIENT-REDACTED]",
    ),
    # Titled third-party names that show up in descriptions: "Dr. Smith",
    # "Mr Jones", "Ms. Mary Public". (The employee's own name is a separate
    # OSHA column, not the free-text description.)
    "title_name": (
        r"(?i:\b(?:Mr|Mrs|Ms|Mx|Dr))\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}",
        "[NAME-REDACTED]",
    ),
    # "chart 88321", "account no 4432", "acct# A1234"
    "account_no": (
        r"(?i:\b(?:acct|account|chart))\s*(?:no\.?|number|#)?\s*[:#]?\s*[A-Za-z0-9][A-Za-z0-9-]{3,}\b",
        "[ACCT-REDACTED]",
    ),
    # "DOB 03/14/1980", "dob: 1980-03-14", "Date of Birth 3/14/80"
    "dob_labeled": (
        r"(?i:\bDOB|\bdate\s+of\s+birth)\s*[:#]?\s*\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b",
        "[DOB-REDACTED]",
    ),
}

# Base PIIScrubber patterns we DON'T want for OSHA free text. ``zip_code``
# (\d{5}) and the broad ``drivers_license`` / ``passport`` shapes fire on
# room numbers, asset tags, and case numbers that legitimately belong in a
# "where/how" description. SSN / phone / email / DOB / street address stay on.
_SKIP_BASE_PATTERNS = {"zip_code", "drivers_license", "passport", "bank_account"}


def redact_osha_text(text: Optional[str]) -> Optional[str]:
    """Redact PII + patient PHI from one OSHA free-text field.

    Applied to every company (patient info belongs on no employer's log).
    Returns the input unchanged when empty/None. Idempotent on already-
    redacted text (the ``[...-REDACTED]`` / ``[NAME-N]`` tokens hold no PII
    to re-match).
    """
    if not text or not text.strip():
        return text

    scrubber = PIIScrubber(custom_patterns=_PHI_PATTERNS, skip_patterns=_SKIP_BASE_PATTERNS)
    scrubbed, _ = scrubber.scrub(text)
    return scrubbed


def osha_text_has_phi(text: Optional[str]) -> bool:
    """Return True if ``text`` still contains detectable PII/PHI.

    Used by tests (and an optional pre-export guard) to assert a field was
    actually scrubbed. Mirrors the pattern set in :func:`redact_osha_text`.
    """
    if not text:
        return False

    base = {
        name: pat
        for name, (pat, repl) in PIIScrubber.PATTERNS.items()
        if repl is not None and name not in _SKIP_BASE_PATTERNS
    }
    patterns = dict(base)
    patterns.update({name: pat for name, (pat, _r) in _PHI_PATTERNS.items()})

    for pat in patterns.values():
        if re.search(pat, text):
            return True
    return False


async def company_is_healthcare(conn, company_id) -> bool:
    """Whether a company is a healthcare/medical client.

    No longer gates redaction (PHI is stripped for all companies), but kept
    for callers that want to branch healthcare-specific behaviour elsewhere.
    Mirrors the detection in ``er_copilot`` (industry healthcare/medical, or
    any healthcare_specialties set).
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
