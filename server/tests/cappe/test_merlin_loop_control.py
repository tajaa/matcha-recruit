"""Pure policy tests for Merlin's shared tool-loop bounds.

No database or Gemini client is involved: these pin the retry rules that both
the setup concierge and page-editor agent rely on.
"""
from app.cappe.services.merlin.loop_control import (
    NoProgressGuard,
    ToolObservation,
    TurnTokenBudget,
    tool_call_fingerprint,
)


def _failed(args, reason="invalid target"):
    return ToolObservation("apply_ops", "failed", args, reason)


def test_json_string_and_object_payloads_share_a_fingerprint():
    object_call = tool_call_fingerprint("stage_action", {"type": "create_page", "payload": {"title": "About"}})
    json_call = tool_call_fingerprint("stage_action", {"type": "create_page", "payload": '{"title":"About"}'})

    assert object_call == json_call


def test_same_failure_after_an_informational_lookup_stops():
    guard = NoProgressGuard()
    first = guard.observe_batch([_failed({"ops": '[{"op":"set_field","block":"ghost"}]'})])
    lookup = guard.observe_batch([ToolObservation("inspect_block", "informed", {"block_id": "b1"})])
    second = guard.observe_batch([_failed({"ops": '[{"op":"set_field","block":"ghost"}]'})])

    assert not first.stop
    assert not lookup.stop
    assert second.stop
    assert second.reason == "invalid target"


def test_successful_change_clears_previous_failure_counts():
    guard = NoProgressGuard()
    args = {"ops": '[{"op":"set_field","block":"ghost"}]'}

    assert not guard.observe_batch([_failed(args)]).stop
    assert not guard.observe_batch([ToolObservation("apply_ops", "changed", {"ops": "[]"})]).stop
    assert not guard.observe_batch([_failed(args)]).stop


def test_failed_sibling_does_not_stop_a_batch_with_progress():
    guard = NoProgressGuard()
    decision = guard.observe_batch([
        _failed({"ops": '[{"op":"set_field","block":"ghost"}]'}),
        ToolObservation("apply_ops", "changed", {"ops": '[{"op":"set_field","block":"b1"}]'}),
    ])

    assert not decision.stop


def test_token_budget_uses_response_metadata_and_blocks_next_large_retry():
    usage = type("Usage", (), {"prompt_token_count": 170_000, "total_token_count": 175_000})()
    response = type("Response", (), {"usage_metadata": usage})()
    budget = TurnTokenBudget(max_prompt_tokens=180_000, max_total_tokens=225_000)

    budget.record_response(response, fallback_prompt_tokens=1)

    assert budget.reason_before_next_call(estimated_next_prompt_tokens=170_000)


def test_token_budget_falls_back_when_usage_metadata_is_missing():
    budget = TurnTokenBudget(max_prompt_tokens=100, max_total_tokens=200)

    budget.record_response(object(), fallback_prompt_tokens=75)

    assert budget.prompt_tokens == 75
    assert budget.total_tokens == 75
    assert budget.reason_before_next_call(estimated_next_prompt_tokens=75)
