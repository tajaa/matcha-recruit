"""extraction._coerce_result — the kind whitelist applied to whatever the
model returns. Pure, no Gemini call.

    cd server && ./venv/bin/python -m pytest tests/inventory/test_extraction.py -q
"""

from app.matcha.services.inventory.extraction import _coerce_result


def test_valid_kinds_pass_through_actionable():
    for kind in ("movement", "stockout", "receipt", "order_request", "return"):
        result = _coerce_result({"actionable": True, "kind": kind, "lines": []})
        assert result["actionable"] is True
        assert result["kind"] == kind


def test_hallucinated_kind_is_forced_non_actionable():
    # A kind the caller's dispatch doesn't recognize (e.g. "adjust" or
    # "transfer") used to fall into the else-branch — auto-creating an
    # item and staging a real order from an unvalidated model field.
    result = _coerce_result({"actionable": True, "kind": "adjust", "lines": []})
    assert result["actionable"] is False


def test_missing_kind_falls_back_to_movement_default():
    # No "kind" in the model's JSON merges onto _FALLBACK_RESULT's own
    # kind="movement" — a valid kind, so actionable is left untouched.
    result = _coerce_result({"actionable": True, "lines": []})
    assert result["kind"] == "movement"
    assert result["actionable"] is True


def test_null_kind_is_forced_non_actionable():
    result = _coerce_result({"actionable": True, "kind": None, "lines": []})
    assert result["actionable"] is False


def test_already_non_actionable_stays_non_actionable():
    result = _coerce_result({"actionable": False, "kind": "movement"})
    assert result["actionable"] is False
