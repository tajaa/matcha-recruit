import json

from app.matcha.services.inventory.orders import decode_suggestion


def test_decode_suggestion_parses_json_string():
    assert decode_suggestion(json.dumps({"suggested_quantity": 12})) == {"suggested_quantity": 12}


def test_decode_suggestion_passes_dict_through():
    assert decode_suggestion({"suggested_quantity": 12}) == {"suggested_quantity": 12}


def test_decode_suggestion_none():
    assert decode_suggestion(None) is None


def test_decode_suggestion_garbage_returns_none():
    assert decode_suggestion("not json") is None
