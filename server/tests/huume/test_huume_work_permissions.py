"""Huume's execution envelope uses Work capabilities when supplied."""

from app.matcha.services.huume.actions import (
    evaluate_huume_action,
    evaluate_plan_execution,
)
from app.matcha.services.matcha_work.work_permissions import WorkCapability


FEATURES = {"huume": True, "matcha_work": True, "offer_letters": True}


def _staged():
    return {"type": "send_offer", "offer_id": "offer-1", "status": "proposed"}


def test_member_can_stage_but_cannot_execute():
    member = {WorkCapability.ACTION_PROPOSE}
    staged = evaluate_huume_action(
        staged_action=_staged(),
        features=FEATURES,
        capabilities=member,
        thread_huume_mode=True,
        this_turn_staged_new=True,
    )
    confirmed = evaluate_huume_action(
        staged_action=_staged(),
        features=FEATURES,
        capabilities=member,
        thread_huume_mode=True,
        this_turn_staged_new=False,
    )
    assert staged.kind == "stage"
    assert confirmed.kind == "refuse"


def test_operator_can_execute_plan():
    assert evaluate_plan_execution(
        capabilities={WorkCapability.ACTION_EXECUTE}, features=FEATURES
    ) is None


def test_reviewer_cannot_execute_plan():
    reason = evaluate_plan_execution(
        capabilities={WorkCapability.EVENT_RESOLVE}, features=FEATURES
    )
    assert reason and "Operator" in reason
