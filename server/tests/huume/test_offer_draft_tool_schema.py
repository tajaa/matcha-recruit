"""Huume offer-draft tool exposes all editable offer fields."""

from app.matcha.services.huume.tools import TOOLS_BY_NAME


def test_draft_offer_letter_exposes_reporting_to():
    tool = TOOLS_BY_NAME["draft_offer_letter"]
    assert "reporting_to" in tool.declaration.parameters.properties
    assert "supervisor" in tool.declaration.parameters.properties["reporting_to"].description


def test_draft_offer_letter_marks_send_time_fields_optional():
    tool = TOOLS_BY_NAME["draft_offer_letter"]
    assert "must not block drafting" in tool.declaration.description
    assert "Optional while drafting" in tool.declaration.parameters.properties["candidate_email"].description
    assert "Optional while drafting" in tool.declaration.parameters.properties["reporting_to"].description
