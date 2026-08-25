from app.matcha.services.inventory._codec import decode_jsonb


def test_decode_jsonb_parses_json_string():
    assert decode_jsonb('[{"item_id": "a", "quantity_per_sale": 1}]') == [
        {"item_id": "a", "quantity_per_sale": 1}
    ]


def test_decode_jsonb_passes_non_string_through():
    value = [{"item_id": "a"}]
    assert decode_jsonb(value) is value


def test_decode_jsonb_none_uses_default():
    assert decode_jsonb(None, []) == []
    assert decode_jsonb(None) is None


def test_decode_jsonb_garbage_returns_default():
    assert decode_jsonb("not json", []) == []
