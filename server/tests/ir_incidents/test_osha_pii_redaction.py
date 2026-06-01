"""Tests for OSHA 300 log / 301 form PII + patient-PHI redaction.

Pure-helper unit tests — no app boot, no DB. The redaction utility runs at
OSHA log generation time so patient-identifiable info from an incident
description never lands in exported/posted OSHA documents, while the injury
description itself (required by OSHA) is preserved.

Redaction is ALWAYS-ON (not gated on healthcare classification) — the
Round-2 fix: an earlier healthcare-only gate + case-sensitive matching let
patient names through for non-healthcare companies and at sentence starts.
"""
from app.core.services.osha_redaction import (
    redact_osha_text,
    osha_text_has_phi,
)


# ── structured PII ──────────────────────────────────────────────────────────

def test_ssn_redacted():
    out = redact_osha_text("Employee fell; SSN 123-45-6789 on file.")
    assert "123-45-6789" not in out


def test_phone_email_redacted():
    out = redact_osha_text("Contact worker at 555-867-5309 or jane.doe@example.com.")
    assert "555-867-5309" not in out
    assert "jane.doe@example.com" not in out


def test_street_address_redacted():
    out = redact_osha_text("Slip at 1234 Industrial Blvd loading dock.")
    assert "1234 Industrial Blvd" not in out


def test_dob_redacted():
    out = redact_osha_text("Worker (03/14/1980) sprained ankle.")
    assert "03/14/1980" not in out


# ── patient PHI: redacted for EVERY company (Round-2 fix) ────────────────────

def test_patient_name_redacted_regardless_of_company():
    text = "Nurse stuck by needle drawing blood from patient John Doe."
    out = redact_osha_text(text)
    assert "John Doe" not in out
    assert "needle" in out.lower()  # injury context preserved


def test_patient_name_redacted_for_any_industry():
    # Round-2 regression: this used to require a "healthcare" company and so
    # leaked. It must redact regardless of company type now.
    text = "Incident report on Acme: aggression from patient John Doe."
    out = redact_osha_text(text)
    assert "John Doe" not in out


def test_sentence_start_capital_patient_redacted():
    # Round-2 regression: case-sensitive matching missed a capitalized
    # "Patient" at the start of the description.
    out = redact_osha_text("Patient John Smith exposed staff to blood.")
    assert "John Smith" not in out
    assert "exposed staff to blood" in out


def test_single_name_after_keyword_redacted():
    # Round-2 regression: pattern required 2+ name tokens; "patient John" slipped.
    out = redact_osha_text("Bitten by patient John during transfer.")
    assert "John" not in out.split("Bitten by ")[1].split(" during")[0]


def test_patient_named_variant_redacted():
    out = redact_osha_text("Assaulted by patient named John Smith in the ward.")
    assert "John Smith" not in out


def test_patient_comma_variant_redacted():
    out = redact_osha_text("The patient, Jane Doe, became combative.")
    assert "Jane Doe" not in out


def test_resident_client_keywords_redacted():
    assert "Mary Smith" not in redact_osha_text("Lifting injury moving resident Mary Smith.")
    assert "Bob Jones" not in redact_osha_text("Altercation with client Bob Jones.")


# ── name-before-keyword appositive (Round-3 fix) ─────────────────────────────
# The keyword-first pattern missed names that precede the keyword as an
# appositive ("Jazmine, the patient ..."). Branch 2 catches "<Name>, the/a
# patient|resident|client". Comma required so verb phrases don't false-positive.

def test_appositive_name_before_patient_redacted():
    # The exact leak from the screenshot.
    text = ("I just left the senior care center and went to urgent care because "
            "Jazmine, the patient in room 204 stabbed my arm.")
    out = redact_osha_text(text)
    assert "Jazmine" not in out
    assert "stabbed my arm" in out      # injury context preserved
    assert "room 204" in out            # location context preserved


def test_appositive_multiword_name_before_resident_redacted():
    out = redact_osha_text("Mary Smith, a resident, became combative and bit staff.")
    assert "Mary Smith" not in out
    assert "bit staff" in out


def test_appositive_requires_comma_no_overredaction():
    # "verb + the patient" must NOT redact — no comma, no name.
    for text in (
        "Helped the patient to the bed and strained my back.",
        "Moved the resident and twisted my knee.",
        "Assisted a client into the chair.",
    ):
        assert redact_osha_text(text) == text


def test_appositive_stoplist_temporal_lead_preserved():
    # Sentence-leading temporal/transition words before ", the patient" are not names.
    text = "Yesterday, the patient fell and I caught them, hurting my shoulder."
    out = redact_osha_text(text)
    assert "Yesterday" in out
    assert out == text


def test_appositive_idempotent():
    text = "Because Jazmine, the patient in 204 lashed out, I went to the ER."
    once = redact_osha_text(text)
    twice = redact_osha_text(once)
    assert once == twice
    assert "Jazmine" not in once


def test_titled_third_party_name_redacted():
    assert "Smith" not in redact_osha_text("Struck while assisting Dr. Smith with restraint.")
    assert "Jane Public" not in redact_osha_text("Per Ms. Jane Public, the floor was wet.")


def test_mrn_redacted_any_case():
    for text in (
        "Exposure incident, patient MRN 44321.",
        "chart pulled, mr# A1234 reviewed.",
        "Per Medical Record Number 88321.",
    ):
        out = redact_osha_text(text)
        assert "44321" not in out and "A1234" not in out and "88321" not in out


def test_npi_redacted():
    out = redact_osha_text("Provider NPI 1234567890 documented the injury.")
    assert "1234567890" not in out


def test_chart_account_redacted():
    out = redact_osha_text("Filed under account no 99812 and chart C5567.")
    assert "99812" not in out
    assert "C5567" not in out


def test_labeled_dob_lowercase_redacted():
    out = redact_osha_text("patient dob 03/14/1980 exposed staff.")
    assert "03/14/1980" not in out


# ── injury terminology preserved ─────────────────────────────────────────────

def test_injury_terms_preserved():
    out = redact_osha_text("Laceration to left hand from needlestick; sutures required.")
    assert "Laceration" in out
    assert "left hand" in out
    assert "needlestick" in out


def test_no_overredaction_of_plain_injury_description():
    text = "Slipped on wet floor in the ICU corridor, twisted right knee."
    assert redact_osha_text(text) == text


def test_bare_employee_name_not_overredacted():
    # No patient/resident/client keyword, no title → not a redaction target,
    # so an ordinary description naming an employee isn't gutted.
    text = "Operator Mike cut his thumb on the press guard."
    assert redact_osha_text(text) == text


# ── detector parity + safety ─────────────────────────────────────────────────

def test_detector_flags_then_redaction_clears():
    text = "Needlestick from patient John Doe, MRN 44321."
    assert osha_text_has_phi(text) is True
    out = redact_osha_text(text)
    assert osha_text_has_phi(out) is False


def test_detector_clears_structured():
    text = "SSN 123-45-6789 and phone 555-867-5309."
    assert osha_text_has_phi(text) is True
    out = redact_osha_text(text)
    assert osha_text_has_phi(out) is False


def test_empty_and_none_safe():
    assert redact_osha_text(None) is None
    assert redact_osha_text("") == ""
    assert redact_osha_text("   ") == "   "
    assert osha_text_has_phi(None) is False


def test_idempotent():
    text = "Needlestick from patient John Doe, MRN 44321."
    once = redact_osha_text(text)
    twice = redact_osha_text(once)
    assert once == twice
