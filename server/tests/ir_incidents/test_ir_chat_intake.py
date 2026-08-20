"""Pure-logic tests for the IR chat-intake field merger.

No network / no DB — only _coerce_chat_fields / _is_complete / _required_fields
(the merge/validate step that turns Gemini's raw per-turn JSON into the
accumulated create-form field state). The Gemini call itself (next_turn) is
exercised by a manual dev smoke, same posture as test_ir_voice_parser.py.
"""

from app.matcha.services.ir.ir_chat_intake import (
    MAX_WITNESSES,
    _build_public_turn_prompt,
    _coerce_chat_fields,
    _coerce_public_chat_fields,
    _is_complete,
    _public_chat_is_complete,
    _required_fields,
)

LOCS = {"11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"}
LOC_OPTIONS = [{"id": "11111111-1111-1111-1111-111111111111", "label": "Main"}]

EMPTY_KNOWN = {
    "reported_by_name": None,
    "occurred_at_text": None,
    "location_id": None,
    "description": None,
    "witnesses": [],
}


def _coerce(raw, known=EMPTY_KNOWN):
    return _coerce_chat_fields(raw, known, LOCS)


def test_empty_turn_leaves_known_state_untouched():
    known = {**EMPTY_KNOWN, "reported_by_name": "Jane Doe", "description": "slipped on ice"}
    merged = _coerce({}, known)
    assert merged["reported_by_name"] == "Jane Doe"
    assert merged["description"] == "slipped on ice"
    assert merged["occurred_at_text"] is None
    assert merged["location_id"] is None


def test_new_turn_adds_previously_null_field():
    merged = _coerce({"occurred_at_text": "yesterday around 3pm"})
    assert merged["occurred_at_text"] == "yesterday around 3pm"


def test_new_turn_refines_but_never_blanks_known_field():
    known = {**EMPTY_KNOWN, "reported_by_name": "Jane Doe"}
    # Model returns null/blank for reported_by_name this turn (not re-asked) — must
    # not wipe the already-known value.
    merged = _coerce({"reported_by_name": None, "description": "new detail"}, known)
    assert merged["reported_by_name"] == "Jane Doe"
    assert merged["description"] == "new detail"

    merged2 = _coerce({"reported_by_name": "   "}, known)
    assert merged2["reported_by_name"] == "Jane Doe"


def test_hallucinated_location_dropped_known_preserved():
    good = "11111111-1111-1111-1111-111111111111"
    known = {**EMPTY_KNOWN, "location_id": good}
    merged = _coerce({"location_id": "99999999-9999-9999-9999-999999999999"}, known)
    assert merged["location_id"] == good

    merged2 = _coerce({"location_id": good})
    assert merged2["location_id"] == good

    merged3 = _coerce({"location_id": "not-a-uuid"})
    assert merged3["location_id"] is None


def test_witnesses_union_dedup_across_turns():
    known = {**EMPTY_KNOWN, "witnesses": [{"name": "Bob Smith"}]}
    merged = _coerce({"witnesses": [{"name": "bob smith"}, {"name": "Jane Doe"}]}, known)
    assert merged["witnesses"] == [{"name": "Bob Smith"}, {"name": "Jane Doe"}]


def test_witnesses_capped():
    raw = {"witnesses": [{"name": f"P{i}"} for i in range(MAX_WITNESSES + 10)]}
    merged = _coerce(raw)
    assert len(merged["witnesses"]) == MAX_WITNESSES


def test_empty_new_witness_list_does_not_erase_earlier_witnesses():
    """The easiest merge-direction bug: an empty `witnesses` list from a later
    turn (model didn't mention any this turn) must not blank witnesses a prior
    turn already collected — only a NON-empty new list may extend the set."""
    known = {**EMPTY_KNOWN, "witnesses": [{"name": "Bob Smith"}]}
    merged = _coerce({"witnesses": []}, known)
    assert merged["witnesses"] == [{"name": "Bob Smith"}]

    merged_missing_key = _coerce({}, known)
    assert merged_missing_key["witnesses"] == [{"name": "Bob Smith"}]


def test_required_fields_drops_location_when_none_on_file():
    assert "location_id" in _required_fields(LOC_OPTIONS)
    assert "location_id" not in _required_fields([])


def test_is_complete_requires_all_fields_with_locations():
    fields = {
        "reported_by_name": "Jane Doe",
        "occurred_at_text": "yesterday",
        "location_id": "11111111-1111-1111-1111-111111111111",
        "description": "slipped",
        "witnesses": [],
    }
    assert _is_complete(fields, LOC_OPTIONS) is True
    assert _is_complete({**fields, "location_id": None}, LOC_OPTIONS) is False


def test_is_complete_waives_location_when_no_locations_on_file():
    fields = {
        "reported_by_name": "Jane Doe",
        "occurred_at_text": "yesterday",
        "location_id": None,
        "description": "slipped",
        "witnesses": [],
    }
    assert _is_complete(fields, []) is True


def test_public_anonymous_chat_requires_only_description():
    fields = _coerce_public_chat_fields(
        {"description": "A box fell from a shelf."},
        {},
        intake_kind="anonymous",
    )
    assert _public_chat_is_complete(fields, intake_kind="anonymous") is True
    assert fields["reported_by_name"] is None


def test_public_location_chat_requires_reporter_and_description():
    fields = _coerce_public_chat_fields(
        {"description": "A box fell from a shelf."},
        {},
        intake_kind="location",
    )
    assert _public_chat_is_complete(fields, intake_kind="location") is False
    fields = _coerce_public_chat_fields(
        {"reported_by_name": "Jane Doe", "description": "A box fell from a shelf."},
        fields,
        intake_kind="location",
    )
    assert _public_chat_is_complete(fields, intake_kind="location") is True


def test_public_location_chat_never_accepts_location_or_location_id():
    fields = _coerce_public_chat_fields(
        {"location": "Back room", "location_id": "not-client-controlled", "description": "A box fell."},
        {},
        intake_kind="location",
    )
    assert fields["location"] is None
    assert "location_id" not in fields


def test_public_chat_preserves_known_fields_and_deduplicates_witnesses():
    known = {
        "reported_by_name": "Jane Doe",
        "description": "A box fell.",
        "witnesses": [{"name": "Bob Smith"}],
    }
    fields = _coerce_public_chat_fields(
        {"reported_by_name": "", "witnesses": [{"name": " bob smith "}, {"name": "Sam Lee"}]},
        known,
        intake_kind="location",
    )
    assert fields["reported_by_name"] == "Jane Doe"
    assert fields["description"] == "A box fell."
    assert fields["witnesses"] == [{"name": "Bob Smith"}, {"name": "Sam Lee"}]


def test_public_chat_prompt_does_not_request_anonymous_identity():
    prompt = _build_public_turn_prompt(
        [{"role": "assistant", "content": "Tell me what happened."}],
        {},
        intake_kind="anonymous",
    )
    assert "Do not ask for the reporter's name" in prompt
