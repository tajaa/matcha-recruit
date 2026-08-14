"""Pure tests for the channel event-draft confirmation protocol."""

from unittest.mock import AsyncMock

import pytest

from app.matcha.services.ops.permissions import (
    OpsAccess,
    OpsCapability,
)
from app.matcha.services.ems.event_drafts import confirm_event_draft, may_decide_event_draft
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
    access = OpsAccess(
        company_id=uuid4(),
        user_id=actor,
        level="member",
        capabilities=frozenset({OpsCapability.EVENT_CONFIRM_OWN}),
        source="explicit",
    )
    assert may_decide_event_draft(
        reporter_user_id=actor, actor_user_id=actor, access=access
    )
    assert not may_decide_event_draft(
        reporter_user_id=uuid4(), actor_user_id=actor, access=access
    )


@pytest.mark.asyncio
async def test_confirm_accepts_the_public_call_signature_without_reason():
    from uuid import uuid4

    company_id = uuid4()
    draft_id = uuid4()
    event_id = uuid4()
    actor = uuid4()
    access = OpsAccess(
        company_id=company_id,
        user_id=actor,
        level="admin",
        capabilities=frozenset(OpsCapability),
        source="platform_admin",
    )
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        {
            "id": draft_id,
            "company_id": company_id,
            "status": "confirmed",
            "event_id": event_id,
            "reporter_user_id": None,
        },
        {"id": event_id},
    ]

    result = await confirm_event_draft(
        conn,
        draft_id=draft_id,
        actor_user_id=actor,
        access=access,
    )

    assert result.changed is False
    assert result.event == {"id": event_id}
