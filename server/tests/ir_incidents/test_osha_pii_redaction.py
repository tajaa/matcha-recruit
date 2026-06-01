"""Tests for OSHA 300 log / 301 form PII + patient-PHI redaction.

Pure-helper unit tests — no app boot, no DB. The redaction utility runs at
OSHA log generation time so patient-identifiable information from healthcare
incident descriptions never lands in exported/posted OSHA documents, while
the injury description itself (required by OSHA) is preserved.

Covers checklist items:
- structured PII stripped for ALL clients (SSN/phone/email/DOB/street)
- patient PHI stripped for HEALTHCARE clients (MRN/patient name/NPI/chart)
- injury terminology preserved (laceration, needlestick, body parts)
- detector ``osha_text_has_phi`` agrees with ``redact_osha_text``
- empty/None/idempotent safety
"""
from app.core.services.osha_redaction import (
    redact_osha_text,
    osha_text_has_phi,
)


# ── structured PII: redacted for every client ───────────────────────────────

def test_ssn_redacted_all_clients():
    text = "Employee fell; SSN 123-45-6789 on file."
    for hc in (True, False):
        out = redact_osha_text(text, healthcare=hc)
        assert "123-45-6789" not in out
        assert "REDACTED" in out or "SSN" in out


def test_phone_email_redacted_all_clients():
    text = "Contact worker at 555-867-5309 or jane.doe@example.com."
    for hc in (True, False):
        out = redact_osha_text(text, healthcare=hc)
        assert "555-867-5309" not in out
        assert "jane.doe@example.com" not in out


def test_street_address_redacted():
    text = "Slip at 1234 Industrial Blvd loading dock."
    out = redact_osha_text(text, healthcare=False)
    assert "1234 Industrial Blvd" not in out


def test_dob_redacted():
    text = "Worker (03/14/1980) sprained ankle."
    out = redact_osha_text(text, healthcare=False)
    assert "03/14/1980" not in out


# ── patient PHI: redacted only for healthcare clients ───────────────────────

def test_patient_name_redacted_for_healthcare():
    text = "Nurse stuck by needle drawing blood from patient John Doe."
    out = redact_osha_text(text, healthcare=True)
    assert "John Doe" not in out
    # injury context preserved
    assert "needle" in out.lower()


def test_patient_name_not_redacted_for_non_healthcare():
    # Non-healthcare clients don't get the patient-name pattern. (A bare name
    # with no structured identifier is not caught by the base patterns.)
    text = "Coworker patient John Doe assisted with the lift."
    out = redact_osha_text(text, healthcare=False)
    assert "John Doe" in out


def test_mrn_redacted_for_healthcare():
    for text in (
        "Exposure incident, patient MRN 44321.",
        "Chart pulled, MR# A1234 reviewed.",
        "Per medical record number 88321.",
    ):
        out = redact_osha_text(text, healthcare=True)
        assert "44321" not in out
        assert "A1234" not in out
        assert "88321" not in out


def test_npi_redacted_for_healthcare():
    text = "Provider NPI 1234567890 documented the injury."
    out = redact_osha_text(text, healthcare=True)
    assert "1234567890" not in out


def test_chart_account_redacted_for_healthcare():
    text = "Filed under account no 99812 and chart C5567."
    out = redact_osha_text(text, healthcare=True)
    assert "99812" not in out
    assert "C5567" not in out


def test_labeled_dob_redacted_for_healthcare():
    text = "Patient DOB 03/14/1980 exposed staff."
    out = redact_osha_text(text, healthcare=True)
    assert "03/14/1980" not in out


# ── injury terminology preserved (OSHA still needs the injury described) ─────

def test_injury_terms_preserved():
    text = "Laceration to left hand from needlestick; sutures required."
    out = redact_osha_text(text, healthcare=True)
    assert "Laceration" in out
    assert "left hand" in out
    assert "needlestick" in out


def test_no_overredaction_of_plain_injury_description():
    text = "Slipped on wet floor in the ICU corridor, twisted right knee."
    out = redact_osha_text(text, healthcare=True)
    assert out == text  # nothing to redact


# ── detector parity + safety ────────────────────────────────────────────────

def test_detector_flags_then_redaction_clears_healthcare():
    text = "Needlestick from patient John Doe, MRN 44321."
    assert osha_text_has_phi(text, healthcare=True) is True
    out = redact_osha_text(text, healthcare=True)
    assert osha_text_has_phi(out, healthcare=True) is False


def test_detector_clears_structured_for_all():
    text = "SSN 123-45-6789 and phone 555-867-5309."
    assert osha_text_has_phi(text, healthcare=False) is True
    out = redact_osha_text(text, healthcare=False)
    assert osha_text_has_phi(out, healthcare=False) is False


def test_empty_and_none_safe():
    assert redact_osha_text(None, healthcare=True) is None
    assert redact_osha_text("", healthcare=True) == ""
    assert redact_osha_text("   ", healthcare=True) == "   "
    assert osha_text_has_phi(None, healthcare=True) is False


def test_idempotent():
    text = "Needlestick from patient John Doe, MRN 44321."
    once = redact_osha_text(text, healthcare=True)
    twice = redact_osha_text(once, healthcare=True)
    assert once == twice
