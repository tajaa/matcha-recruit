"""Regression coverage for canonical EMS action state in channel history."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.werk.routes.channels import _resolve_event_draft_action_statuses


@pytest.mark.asyncio
async def test_history_replaces_stale_pending_card_with_confirmed_draft_status():
    draft_id = uuid4()
    channel_id = uuid4()
    conn = AsyncMock()
    conn.fetch.return_value = [{"id": draft_id, "status": "confirmed"}]
    messages = [{
        "id": uuid4(),
        "metadata": json.dumps({
            "action": {"kind": "event_draft", "id": str(draft_id), "status": "pending"},
        }),
    }]

    resolved = await _resolve_event_draft_action_statuses(
        conn, messages, channel_id=channel_id,
    )

    assert resolved[0]["metadata"]["action"]["status"] == "confirmed"
    assert conn.fetch.await_args.args[2] == channel_id


@pytest.mark.asyncio
async def test_history_keeps_a_distinct_new_pending_draft_actionable():
    draft_id = uuid4()
    channel_id = uuid4()
    conn = AsyncMock()
    conn.fetch.return_value = [{"id": draft_id, "status": "pending"}]
    messages = [{
        "id": uuid4(),
        "metadata": {
            "action": {"kind": "event_draft", "id": str(draft_id), "status": "pending"},
        },
    }]

    resolved = await _resolve_event_draft_action_statuses(
        conn, messages, channel_id=channel_id,
    )

    assert resolved[0]["metadata"]["action"]["status"] == "pending"


@pytest.mark.asyncio
async def test_history_without_event_draft_cards_does_not_query_drafts():
    conn = AsyncMock()
    messages = [{"id": uuid4(), "metadata": {"action": {"kind": "event_assignment"}}}]

    resolved = await _resolve_event_draft_action_statuses(
        conn, messages, channel_id=uuid4(),
    )

    assert resolved is messages
    conn.fetch.assert_not_awaited()
