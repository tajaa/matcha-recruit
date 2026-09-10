"""Pure tests for the channel event-draft confirmation protocol."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.ems.event_drafts import (
    _sync_confirmation_card_status,
    confirm_event_draft,
    may_decide_event_draft,
)
from app.matcha.services.ops.permissions import (
    OpsAccess,
    OpsCapability,
)
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
    channel_id = uuid4()
    confirmation_message_id = uuid4()
    created_at = datetime.now(timezone.utc)
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
            "channel_id": channel_id,
            "confirmation_message_id": confirmation_message_id,
            "created_at": created_at,
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
    primary_update, duplicate_update = conn.execute.await_args_list
    assert "WHERE id = $1" in primary_update.args[0]
    assert primary_update.args[1:] == (
        confirmation_message_id,
        channel_id,
        str(draft_id),
        "confirmed",
    )
    assert "created_at >= $4" in duplicate_update.args[0]
    assert duplicate_update.args[1:] == (
        channel_id,
        str(draft_id),
        "confirmed",
        created_at,
        confirmation_message_id,
    )


@pytest.mark.asyncio
async def test_confirmation_status_updates_every_card_with_the_same_draft_action():
    from uuid import uuid4

    conn = AsyncMock()
    channel_id = uuid4()
    draft_id = uuid4()
    confirmation_message_id = uuid4()
    created_at = datetime.now(timezone.utc)

    await _sync_confirmation_card_status(
        conn,
        channel_id=channel_id,
        draft_id=draft_id,
        confirmation_message_id=confirmation_message_id,
        draft_created_at=created_at,
        status="rejected",
    )

    primary_update, duplicate_update = conn.execute.await_args_list
    primary_query, *primary_args = primary_update.args
    assert "WHERE id = $1" in primary_query
    assert primary_args == [
        confirmation_message_id,
        channel_id,
        str(draft_id),
        "rejected",
    ]

    duplicate_query, *duplicate_args = duplicate_update.args
    assert "created_at >= $4" in duplicate_query
    assert "id IS DISTINCT FROM $5" in duplicate_query
    assert "metadata #>> '{action,id}' = $2" in duplicate_query
    assert duplicate_args == [
        channel_id,
        str(draft_id),
        "rejected",
        created_at,
        confirmation_message_id,
    ]
