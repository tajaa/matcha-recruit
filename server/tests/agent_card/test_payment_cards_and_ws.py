import base64
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.services import card_vault
from app.matcha.routes.matcha_work import payment_cards
from app.werk.routes import channels_ws

VISA = "4242 4242 4242 4242"


def _user(role="admin"):
    return SimpleNamespace(id=uuid4(), role=role, email=f"{role}@example.com")


class _Conn:
    def __init__(self, count=0, deleted=True):
        self.count = count
        self.deleted = deleted
        self.inserted = None
        self.locks = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, query, *args):
        assert "pg_advisory_xact_lock" in query
        self.locks.append(args[0])

    async def fetchval(self, query, *args):
        if "COUNT(*)" in query:
            return self.count
        if "DELETE FROM mw_payment_cards" in query:
            assert "user_id = $2" in query
            return args[0] if self.deleted else None
        raise AssertionError(query)

    async def fetchrow(self, query, *args):
        assert "INSERT INTO mw_payment_cards" in query
        self.inserted = args
        return {"id": args[0], "label": args[2], "brand": args[3], "last4": args[4],
                "exp_month": args[5], "exp_year": args[6], "created_at": datetime.now(timezone.utc)}

    async def fetch(self, query, *args):
        assert "pan_ciphertext" not in query  # the number never leaves the table
        return []


@pytest.fixture
def conn(monkeypatch):
    holder = {"conn": _Conn()}

    @asynccontextmanager
    async def gc():
        yield holder["conn"]

    monkeypatch.setattr(payment_cards, "get_connection", gc)
    monkeypatch.setenv(card_vault.KEYS_ENV, f"k1:{base64.b64encode(os.urandom(32)).decode()}")
    return holder


def _body(**over):
    data = {"number": VISA, "exp_month": 12, "exp_year": 2031, "label": "  Mercury   test "}
    data.update(over)
    return payment_cards.PaymentCardCreate(**data)


@pytest.mark.asyncio
async def test_add_card_stores_only_ciphertext_and_returns_last4(conn):
    user = _user()
    out = await payment_cards.add_payment_card(_body(), user)
    assert out["last4"] == "4242" and out["brand"] == "visa" and out["label"] == "Mercury test"
    assert "number" not in out and "pan_ciphertext" not in out
    args = conn["conn"].inserted
    ciphertext, key_id = args[7], args[8]
    assert b"4242424242424242" not in ciphertext and key_id == "k1"
    assert card_vault.decrypt_pan(ciphertext, key_id, card_id=args[0], user_id=user.id) == "4242424242424242"
    assert conn["conn"].locks == [f"{user.id}:payment_cards"]


def test_cvv_is_never_accepted_into_the_model():
    body = payment_cards.PaymentCardCreate(number=VISA, exp_month=1, exp_year=2031, cvv="123")
    assert not hasattr(body, "cvv") and "cvv" not in body.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize("over, code", [
    ({"number": "4242 4242 4242 4241"}, 400),
    ({"exp_year": 2020}, 400),
    ({"exp_month": 13}, 400),
    # The label is plain text shown in chat: no card number, or piece of one.
    ({"label": "Visa 4242 4242 4242 4242"}, 400),
    ({"label": "card 42424"}, 400),
])
async def test_add_card_rejects_bad_input(conn, over, code):
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_payment_card(_body(**over), _user())
    assert exc.value.status_code == code
    assert "4242" not in str(exc.value.detail)
    assert conn["conn"].inserted is None


@pytest.mark.asyncio
async def test_allowlisted_non_admin_can_add_a_card(conn, monkeypatch):
    monkeypatch.setenv("AGENT_PURCHASE_ALLOWED_EMAILS", "haley@example.com")
    user = SimpleNamespace(id=uuid4(), role="individual", email="haley@example.com")
    assert (await payment_cards.add_payment_card(_body(), user))["last4"] == "4242"
    assert (await payment_cards.list_payment_cards(user))["enabled"] is True


@pytest.mark.asyncio
async def test_add_card_is_admin_only_in_v1(conn):
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_payment_card(_body(), _user("client"))
    assert exc.value.status_code == 403 and exc.value.detail["code"] == "purchases_unavailable"


@pytest.mark.asyncio
async def test_add_card_fails_closed_without_a_vault_key(conn, monkeypatch):
    monkeypatch.delenv(card_vault.KEYS_ENV)
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_payment_card(_body(), _user())
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_add_card_caps_saved_cards(conn):
    conn["conn"] = _Conn(count=payment_cards.MAX_CARDS_PER_USER)
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_payment_card(_body(), _user())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_list_reports_whether_buying_is_enabled(conn):
    out = await payment_cards.list_payment_cards(_user("client"))
    assert out == {"enabled": False, "configured": True, "cards": []}
    assert (await payment_cards.list_payment_cards(_user()))["enabled"] is True


@pytest.mark.asyncio
async def test_delete_card_is_scoped_to_its_owner(conn):
    await payment_cards.delete_payment_card(uuid4(), _user("client"))  # anyone may delete their own
    conn["conn"] = _Conn(deleted=False)
    with pytest.raises(HTTPException) as exc:
        await payment_cards.delete_payment_card(uuid4(), _user())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_label_with_up_to_four_digits_is_saved(conn):
    out = await payment_cards.add_payment_card(_body(label="Mercury 2026"), _user())
    assert out["label"] == "Mercury 2026"


# ── chat socket helpers ───────────────────────────────────────────────────────

def test_ws_helpers_wrap_the_chat_flow():
    pid = uuid4()
    assert channels_ws._agent_card_prompt_reference({"kind": "agent_card_prompt", "prompt_id": str(pid)}) == pid
    assert channels_ws._agent_card_prompt_reference({}) is None
    assert channels_ws._agent_card_plain_yes("yes please")
    assert not channels_ws._agent_card_plain_yes("ok")


@pytest.mark.asyncio
async def test_ws_redaction_delegates_to_the_chat_flow(monkeypatch):
    from app.matcha.services.matcha_work.agent_card import chat_flow

    seen = {}

    async def redact(conn, **kwargs):
        seen.update(kwargs)
        return "x", True

    monkeypatch.setattr(chat_flow, "redact_card_numbers", redact)
    uid, cid, pid = uuid4(), uuid4(), uuid4()
    assert await channels_ws._agent_card_redaction(object(), cid, uid, "text", pid) == ("x", True)
    assert seen == {"channel_id": cid, "user_id": uid, "replied_prompt_id": pid, "content": "text"}


@pytest.mark.asyncio
async def test_bg_reply_never_raises(monkeypatch):
    from app.matcha.services.matcha_work.agent_card import chat_flow

    seen = {}

    async def boom(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("db down")

    monkeypatch.setattr(chat_flow, "handle_chat_answer", boom)
    await channels_ws._bg_agent_card_reply(str(uuid4()), _user(), "yes", None, False, True)
    assert seen["card_number_removed"] is True and seen["content"] == "yes"


def test_routing_answers_to_agent_card_questions(monkeypatch):
    route = channels_ws._routes_to_agent_card
    base = dict(agent_prompt_id=None, card_number_removed=False, reply_to_id=None,
                mention_handles=[], content="yes", room_key=str(uuid4()), is_project_chat=True)
    assert route(**base)
    assert route(**{**base, "agent_prompt_id": uuid4(), "content": "anything", "is_project_chat": False})
    assert route(**{**base, "card_number_removed": True, "content": "x"})
    # Everyday acknowledgements never spawn a task, and nothing outside a
    # project discussion chat does either.
    for text in ("ok", "k", "sure", "no", "4242", "see you at 5"):
        assert not route(**{**base, "content": text})
    assert not route(**{**base, "is_project_chat": False})
    assert not route(**{**base, "reply_to_id": uuid4()})  # a reply to someone else
    assert not route(**{**base, "mention_handles": ["espresso"]})
    monkeypatch.setattr(channels_ws, "_channel_recently_ems_drafted", lambda _k: True)
    assert not route(**base)  # a live Huume event-draft pill keeps its "yes"


# ── message edits ─────────────────────────────────────────────────────────────

class _EditConn:
    def __init__(self, reply_metadata=None, owns_purchase=False):
        self.reply_metadata = reply_metadata
        self.owns_purchase = owns_purchase
        self.stored = None

    async def fetchrow(self, query, *args):
        assert "LEFT JOIN channel_messages r ON r.id = m.reply_to_id" in query
        return {"id": args[0], "sender_id": self.user_id, "deleted_at": None,
                "created_at": datetime.now(timezone.utc), "message_type": "user",
                "reply_metadata": self.reply_metadata}

    async def fetchval(self, query, *args):
        if "mw_agent_card_prompts" in query:
            return self.owns_purchase
        assert "UPDATE channel_messages SET content" in query
        self.stored = args[1]
        return datetime.now(timezone.utc)


@pytest.fixture
def edit_env(monkeypatch):
    from app.matcha.services.matcha_work.agent_card import chat_flow
    from app.werk.routes import channels

    holder = {"broadcast": AsyncMock(), "warn": AsyncMock(return_value=True)}

    @asynccontextmanager
    async def gc():
        yield holder["conn"]

    monkeypatch.setattr(channels, "get_connection", gc)
    monkeypatch.setattr(channels, "_require_channel_capability", AsyncMock())
    monkeypatch.setattr(channels_ws, "broadcast_message_edited", holder["broadcast"])
    monkeypatch.setattr(chat_flow, "handle_chat_answer", holder["warn"])
    holder["channels"] = channels
    return holder


async def _edit(env, user, text, **conn_kw):
    env["conn"] = _EditConn(**conn_kw)
    env["conn"].user_id = user.id
    body = env["channels"].MessageEditRequest(content=text)
    return await env["channels"].edit_channel_message(uuid4(), uuid4(), body, user)


@pytest.mark.asyncio
async def test_editing_a_card_number_into_a_reply_to_a_question_is_redacted(edit_env):
    user, pid = _user(), uuid4()
    await _edit(edit_env, user, f"use {VISA}",
                reply_metadata=json.dumps({"kind": "agent_card_prompt", "prompt_id": str(pid)}))
    assert edit_env["conn"].stored == f"use {card_vault.REDACTED}"
    assert edit_env["broadcast"].await_args.kwargs["content"] == f"use {card_vault.REDACTED}"
    warn = edit_env["warn"].await_args.kwargs
    assert warn["prompt_id"] == pid and warn["card_number_removed"] is True


@pytest.mark.asyncio
async def test_editing_by_the_purchase_owner_is_redacted_and_ordinary_edits_are_not(edit_env):
    user = _user()
    await _edit(edit_env, user, f"here {VISA}", owns_purchase=True)
    assert edit_env["conn"].stored == f"here {card_vault.REDACTED}"
    edit_env["warn"].reset_mock()
    await _edit(edit_env, user, f"here {VISA}", owns_purchase=False)
    assert edit_env["conn"].stored == f"here {VISA}"
    edit_env["warn"].assert_not_awaited()
