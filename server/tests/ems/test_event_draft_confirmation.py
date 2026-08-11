"""Pure tests for the channel event-draft confirmation protocol."""

from app.matcha.services.matcha_work.work_permissions import (
    WorkCapability,
    access_from_capabilities,
)
from app.matcha.services.ems.event_drafts import may_decide_event_draft
from app.werk.routes.channels_ws import (
    _draft_reply_decision,
    _event_draft_confirmation_text,
)


def test_confirmation_parser_accepts_only_unambiguous_positive_replies():
    assert _draft_reply_decision("confirm") == "confirm"
    assert _draft_reply_decision("Yes!") == "confirm"
    assert _draft_reply_decision("add it") == "confirm"
    assert _draft_reply_decision("sounds good") is None


def test_confirmation_parser_accepts_negative_replies():
    assert _draft_reply_decision("not an event") == "reject"
    assert _draft_reply_decision("don't add") == "reject"
    assert _draft_reply_decision("maybe") is None


def test_confirmation_prompt_is_category_and_title_specific():
    text = _event_draft_confirmation_text(
        {"category": "equipment", "title": "Broken freezer"}
    )
    assert "equipment" in text
    assert "Broken freezer" in text
    assert "confirm" in text


def test_member_can_decide_own_draft_but_not_another_reporter():
    from uuid import uuid4

    actor = uuid4()
    access = access_from_capabilities(
        company_id=uuid4(),
        user_id=actor,
        level="member",
        capabilities={WorkCapability.EVENT_CONFIRM_OWN},
    )
    assert may_decide_event_draft(
        reporter_user_id=actor, actor_user_id=actor, access=access
    )
    assert not may_decide_event_draft(
        reporter_user_id=uuid4(), actor_user_id=actor, access=access
    )
