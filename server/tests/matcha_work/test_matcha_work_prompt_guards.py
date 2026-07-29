"""Pins two invariants in `MATCHA_WORK_STATIC_PROMPT_TEMPLATE` that must not
drift apart from each other: the generic assistant CAN author documents the
user asks it to compose (DOCUMENT EXPORT), but must NEVER reconstruct the
contents of a company record it wasn't given (COMPANY RECORDS ARE NOT
DOCUMENTS TO AUTHOR). A real incident report was fabricated in production
testing — a fake time, address, first-aid steps, and PEP referral for a
record whose actual description was two sentences — because the generic
matcha-work path has zero company-record grounding (every mode context
builder is gated on its own `mw_threads` column; all off means empty
context) and the DOCUMENT EXPORT rule alone reads as "write the report".

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_matcha_work_prompt_guards.py -q
"""

from app.matcha.services.matcha_work.matcha_work_ai._prompts import MATCHA_WORK_STATIC_PROMPT_TEMPLATE


def test_document_export_rule_present():
    assert "DOCUMENT EXPORT" in MATCHA_WORK_STATIC_PROMPT_TEMPLATE
    assert "WRITE THE COMPLETE DOCUMENT" in MATCHA_WORK_STATIC_PROMPT_TEMPLATE


def test_company_records_are_not_documents_to_author_rule_present():
    assert "COMPANY RECORDS ARE NOT DOCUMENTS TO AUTHOR" in MATCHA_WORK_STATIC_PROMPT_TEMPLATE
    assert "NEVER reconstruct, expand, or fill in a record" in MATCHA_WORK_STATIC_PROMPT_TEMPLATE


def test_no_fabrication_rule_follows_document_export_rule():
    # Placement matters: it's the direct counterweight to DOCUMENT EXPORT
    # (the instruction that caused the fabrication), so it must sit right
    # after it rather than somewhere the model is less likely to connect
    # the two.
    export_idx = MATCHA_WORK_STATIC_PROMPT_TEMPLATE.index("DOCUMENT EXPORT")
    no_fabrication_idx = MATCHA_WORK_STATIC_PROMPT_TEMPLATE.index("COMPANY RECORDS ARE NOT DOCUMENTS TO AUTHOR")
    assert export_idx < no_fabrication_idx
    between = MATCHA_WORK_STATIC_PROMPT_TEMPLATE[export_idx:no_fabrication_idx]
    assert between.count("\n") <= 2


def test_example_pair_present_for_the_reported_failure():
    assert 'show me the whole incident report' in MATCHA_WORK_STATIC_PROMPT_TEMPLATE
    assert "I don't have that incident's full record" in MATCHA_WORK_STATIC_PROMPT_TEMPLATE
