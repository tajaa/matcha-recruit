"""Pure-function tests for agent.py's helpers and onboarding_skill's plan
builder (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_agent_helpers.py -q

Covers: `_cap_payload` truncation, `_StepRecorder` args capture, `is_sole_finish`
(a batched `finish` must be deferred), `_to_contents` per-message text cap +
capped image-part attachment, and the onboarding plan builder carrying
`employment_type` through from the offer.
"""

from decimal import Decimal

from google.genai import types

from app.matcha.services.huume.agent import (
    _MAX_IMAGE_BYTES_TOTAL,
    _MAX_IMAGE_PARTS,
    _MAX_MESSAGE_CHARS,
    _STEP_PAYLOAD_CAP_CHARS,
    _StepRecorder,
    _cap_payload,
    _json_safe,
    _rate_limit_disposition,
    _send_offer_confirming,
    _to_contents,
    is_sole_finish,
)
from app.matcha.services.huume.onboarding_skill import build_onboarding_plan


class TestJsonSafe:
    """Pins the Decimal fix: asyncpg returns NUMERIC columns (e.g.
    inventory_items.current_quantity) as Decimal, and json.dumps has no
    built-in handling for it (unlike date/UUID, no `default=str` fallback
    saves it at the Gemini function-response boundary) — a raw Decimal
    reaching that call crashes the WHOLE turn, not just one tool result."""

    def test_decimal_becomes_float(self):
        assert _json_safe(Decimal("24")) == 24.0
        assert isinstance(_json_safe(Decimal("24")), float)

    def test_decimal_inside_nested_dict_and_list(self):
        value = {"items": [{"current_quantity": Decimal("46.5")}, {"current_quantity": None}]}
        safe = _json_safe(value)
        assert safe["items"][0]["current_quantity"] == 46.5
        assert safe["items"][1]["current_quantity"] is None
        import json
        json.dumps(safe)  # must not raise


class TestCapPayload:
    def test_small_value_unchanged(self):
        value = {"a": 1, "b": "hello"}
        assert _cap_payload(value) == value

    def test_none_stays_none(self):
        assert _cap_payload(None) is None

    def test_oversized_value_truncated(self):
        value = {"blob": "x" * (_STEP_PAYLOAD_CAP_CHARS + 500)}
        capped = _cap_payload(value)
        assert capped["_truncated"] is True
        assert len(capped["preview"]) <= _STEP_PAYLOAD_CAP_CHARS


class TestStepRecorder:
    def test_record_captures_args(self):
        recorder = _StepRecorder()
        step = recorder.record(tool="lookup_context", kind="read", label="Looked up roster", status="ok", args={"topic": "roster"})
        assert step["args"] == {"topic": "roster"}
        assert step["seq"] == 1

    def test_record_without_args_omits_key(self):
        recorder = _StepRecorder()
        step = recorder.record(tool="finish", kind="finish", label="Done", status="ok")
        assert "args" not in step

    def test_seq_is_monotonic(self):
        recorder = _StepRecorder()
        s1 = recorder.record(tool="a", kind="read", label="A", status="ok")
        s2 = recorder.record(tool="b", kind="read", label="B", status="ok")
        assert s1["seq"] == 1 and s2["seq"] == 2


class TestIsSoleFinish:
    def test_finish_alone_ends_the_turn(self):
        assert is_sole_finish(["finish"]) is True

    def test_finish_batched_with_other_tools_is_deferred(self):
        # The other tools still execute; finish has to wait for their results.
        assert is_sole_finish(["lookup_context", "finish"]) is False
        assert is_sole_finish(["finish", "draft_offer_letter"]) is False

    def test_no_finish_in_batch(self):
        assert is_sole_finish(["lookup_context"]) is False
        assert is_sole_finish([]) is False


class TestToContentsMessageCap:
    def test_long_message_truncated(self):
        long_text = "y" * (_MAX_MESSAGE_CHARS + 1000)
        contents = _to_contents([{"role": "user", "content": long_text}])
        text = contents[-1].parts[-1].text
        assert len(text) < len(long_text)
        assert text.endswith("[truncated]")

    def test_short_message_unchanged(self):
        contents = _to_contents([{"role": "user", "content": "hello"}])
        assert contents[-1].parts[-1].text == "hello"

    def test_empty_history_gets_hello_fallback(self):
        contents = _to_contents([])
        assert contents[0].parts[0].text == "Hello."


class TestToContentsImageParts:
    def test_image_bytes_attached_on_user_message(self):
        history = [{"role": "user", "content": "check this photo", "image_parts": [(b"fakejpeg", "image/jpeg")]}]
        contents = _to_contents(history)
        parts = contents[-1].parts
        assert any(getattr(p, "inline_data", None) is not None for p in parts)

    def test_images_not_attached_on_assistant_message(self):
        history = [{"role": "assistant", "content": "ok", "image_parts": [(b"fakejpeg", "image/jpeg")]}]
        contents = _to_contents(history)
        parts = contents[-1].parts
        assert not any(getattr(p, "inline_data", None) is not None for p in parts)

    def test_image_count_capped(self):
        many_images = [(b"x", "image/jpeg")] * (_MAX_IMAGE_PARTS + 5)
        history = [{"role": "user", "content": "many photos", "image_parts": many_images}]
        contents = _to_contents(history)
        image_parts = [p for p in contents[-1].parts if getattr(p, "inline_data", None) is not None]
        assert len(image_parts) == _MAX_IMAGE_PARTS

    def test_image_byte_budget_capped(self):
        big_chunk = b"x" * (_MAX_IMAGE_BYTES_TOTAL // 2 + 1)
        history = [{"role": "user", "content": "big photos", "image_parts": [
            (big_chunk, "image/jpeg"), (big_chunk, "image/jpeg"), (big_chunk, "image/jpeg"),
        ]}]
        contents = _to_contents(history)
        image_parts = [p for p in contents[-1].parts if getattr(p, "inline_data", None) is not None]
        # Only one chunk fits under the total byte budget before the second
        # would exceed it.
        assert len(image_parts) == 1


class TestBuildOnboardingPlanEmploymentType:
    def _offer(self, **overrides):
        base = {
            "id": "offer-1", "candidate_name": "Jane Doe", "candidate_email": "jane@example.com",
            "position_title": "Server", "start_date": None, "location": "CA",
            "employment_type": "Part-Time",
        }
        base.update(overrides)
        return base

    def test_employment_type_carried_from_offer(self):
        plan = build_onboarding_plan(offer=self._offer(), features={}, integrations={})
        assert plan["employee"]["employment_type"] == "Part-Time"

    def test_missing_employment_type_is_none(self):
        plan = build_onboarding_plan(offer=self._offer(employment_type=None), features={}, integrations={})
        assert plan["employee"]["employment_type"] is None


class TestRateLimitDisposition:
    """A mid-loop platform RateLimitExceeded must not discard partial work
    once at least one model call has run — see agent.py's `except
    RateLimitExceeded` handler and the headroom contract documented on
    turn_pipeline._run_quota_gate."""

    def test_before_first_call_raises(self):
        assert _rate_limit_disposition(0) == "raise"

    def test_after_first_call_force_finishes(self):
        assert _rate_limit_disposition(1) == "force_finish"

    def test_mid_loop_force_finishes(self):
        for n in (2, 5, 8):
            assert _rate_limit_disposition(n) == "force_finish"


def _staged_send_offer(**overrides):
    base = {
        "type": "send_offer", "offer_id": "offer-maria", "status": "proposed",
        "candidate_name": "Maria Lopez", "recipient_email": "maria@example.com",
    }
    base.update(overrides)
    return base


class TestSendOfferConfirming:
    def test_bare_confirm_matches_staged_offer(self):
        # "confirm" with no offer_id/candidate_name/recipient_email at all.
        assert _send_offer_confirming(
            _staged_send_offer(), offer_id="", candidate_name="", recipient_override=None,
        ) is True

    def test_same_offer_id_matches(self):
        assert _send_offer_confirming(
            _staged_send_offer(), offer_id="offer-maria", candidate_name="", recipient_override=None,
        ) is True

    def test_same_candidate_name_matches(self):
        assert _send_offer_confirming(
            _staged_send_offer(), offer_id="", candidate_name="Maria", recipient_override=None,
        ) is True

    def test_different_candidate_name_does_not_match(self):
        # The bug this regression-tests: "send Bob's offer" right after
        # staging Maria's must NOT reuse Maria's staged proposal — any
        # non-empty candidate_name used to satisfy the old check.
        assert _send_offer_confirming(
            _staged_send_offer(), offer_id="", candidate_name="Bob", recipient_override=None,
        ) is False

    def test_different_offer_id_does_not_match(self):
        assert _send_offer_confirming(
            _staged_send_offer(), offer_id="offer-other", candidate_name="", recipient_override=None,
        ) is False

    def test_matching_recipient_override_matches(self):
        assert _send_offer_confirming(
            _staged_send_offer(), offer_id="offer-maria", candidate_name="",
            recipient_override="maria@example.com",
        ) is True

    def test_different_recipient_override_re_stages(self):
        assert _send_offer_confirming(
            _staged_send_offer(), offer_id="offer-maria", candidate_name="",
            recipient_override="other@example.com",
        ) is False

    def test_nothing_staged_never_matches(self):
        assert _send_offer_confirming(
            None, offer_id="", candidate_name="Maria", recipient_override=None,
        ) is False

    def test_non_proposed_status_does_not_match(self):
        assert _send_offer_confirming(
            _staged_send_offer(status="sent"), offer_id="offer-maria", candidate_name="", recipient_override=None,
        ) is False

    def test_different_staged_type_does_not_match(self):
        assert _send_offer_confirming(
            {"type": "discipline_draft", "status": "proposed"},
            offer_id="", candidate_name="Maria", recipient_override=None,
        ) is False
