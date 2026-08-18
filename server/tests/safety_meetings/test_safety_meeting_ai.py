"""Pure tests for safety-meeting Gemini output coercion.

These tests do not call Gemini or touch the database. Live audio/model behavior
is covered by a manual microphone smoke because the service contract is
best-effort and deliberately falls back to manager review on model failure.
"""

from app.matcha.services.safety_meetings.summary import _coerce_summary
from app.matcha.services.safety_meetings.transcription import _coerce_transcript
from app.matcha.models.safety_meetings import SafetyMeetingCreate, SafetyMeetingUpdate


def test_transcript_coercer_trims_blank_and_non_string_values():
    assert _coerce_transcript({}) is None
    assert _coerce_transcript({"transcript": "  ladder safety was discussed  "}) == "ladder safety was discussed"
    assert _coerce_transcript({"transcript": "   "}) is None
    assert _coerce_transcript({"transcript": 42}) is None


def test_meeting_title_cannot_be_blank():
    assert SafetyMeetingCreate(title="  Toolbox   talk ").title == "Toolbox talk"
    try:
        SafetyMeetingCreate(title="   ")
    except ValueError:
        pass
    else:
        raise AssertionError("blank titles must be rejected")


def test_review_title_cannot_be_explicitly_null():
    try:
        SafetyMeetingUpdate(title=None)
    except ValueError:
        pass
    else:
        raise AssertionError("review titles must not accept null")


def test_summary_coercer_returns_canonical_empty_shape():
    assert _coerce_summary({}) == {
        "summary": None,
        "topics": [],
        "action_items": [],
        "attendees_mentioned": [],
    }
    assert _coerce_summary({"action_items": {"description": "not a list"}})["action_items"] == []


def test_summary_coercer_normalizes_and_caps_lists():
    result = _coerce_summary({
        "summary": "  The crew reviewed fall protection. ",
        "topics": [" Fall protection ", "fall protection", 4],
        "action_items": [
            "Inspect harnesses",
            {"description": "  Replace damaged lanyard ", "owner": " Jordan Lee "},
            {"description": ""},
            5,
        ],
        "attendees_mentioned": [" Sam Rivera ", "sam rivera", None],
    })
    assert result == {
        "summary": "The crew reviewed fall protection.",
        "topics": ["Fall protection"],
        "action_items": [
            {"description": "Inspect harnesses", "owner": None},
            {"description": "Replace damaged lanyard", "owner": "Jordan Lee"},
        ],
        "attendees_mentioned": ["Sam Rivera"],
    }
