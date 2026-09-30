"""Espresso's chat rows carry `sender_is_agent`, so the apps can put them on
the other side of the conversation. The flag comes from the bot's no-login
password sentinel, never from its name."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.project_agent import chat, identity
from app.werk.routes import channels

from .helpers import FakeConn


def _row(**over):
    base = {
        "id": uuid4(), "channel_id": uuid4(), "sender_id": uuid4(), "sender_name": "Espresso",
        "sender_avatar_url": None, "content": "On it.", "attachments": [], "reply_to_id": None,
        "created_at": datetime.now(timezone.utc), "edited_at": None, "deleted_at": None,
        "deleted_by": None, "message_type": "user", "metadata": {}, "client_message_id": None,
    }
    base.update(over)
    return base


def test_the_message_query_derives_the_flag_from_the_bot_sentinel_not_the_name():
    assert f"u.password_hash = '{identity.ESPRESSO_NO_LOGIN}'" in channels._MSG_SELECT
    assert "AS sender_is_agent" in channels._MSG_SELECT


def test_rows_map_the_flag_and_default_to_a_person():
    assert channels._row_to_message(_row(sender_is_agent=True)).sender_is_agent is True
    # A person named "Espresso" is still a person.
    assert channels._row_to_message(_row()).sender_is_agent is False


@pytest.mark.asyncio
async def test_the_bot_user_is_created_with_the_sentinel_and_its_posts_say_so():
    company = uuid4()
    conn = FakeConn().on("SELECT id FROM users", uuid4()).on("INSERT INTO channel_messages", {
        "id": uuid4(), "created_at": datetime.now(timezone.utc),
    })
    posted = await chat.persist_espresso_message(conn, company, uuid4(), "On it.")
    insert = conn.ran("INSERT INTO users")[0][2]
    assert insert == (f"espresso@{company}.invalid", identity.ESPRESSO_NO_LOGIN)
    assert posted["sender_is_agent"] is True and posted["sender_name"] == "Espresso"
