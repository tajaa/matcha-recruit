import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.services import card_vault
from app.matcha.routes.matcha_work import payment_cards
from app.werk.routes import channels_ws

VISA = "4242 4242 4242 4242"


def _user(role="admin"):
    return SimpleNamespace(id=uuid4(), role=role)


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
])
async def test_add_card_rejects_bad_input(conn, over, code):
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_payment_card(_body(**over), _user())
    assert exc.value.status_code == code
    assert "4242" not in str(exc.value.detail)
    assert conn["conn"].inserted is None


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


# ── chat socket helpers ───────────────────────────────────────────────────────

def test_ws_helpers_wrap_the_chat_flow():
    pid = uuid4()
    assert channels_ws._agent_card_prompt_reference({"kind": "agent_card_prompt", "prompt_id": str(pid)}) == pid
    assert channels_ws._agent_card_prompt_reference({}) is None
    assert channels_ws._agent_card_might_answer("yes please")
    assert not channels_ws._agent_card_might_answer("see you at 5")
    assert channels_ws._contains_card_number(f"here {VISA}")
    assert channels_ws._redact_card_numbers(f"here {VISA}") == f"here {card_vault.REDACTED}"


@pytest.mark.asyncio
async def test_prompt_lookup_failure_fails_closed():
    class Broken:
        async def fetchval(self, *_a):
            raise RuntimeError("relation does not exist")

    assert await channels_ws._channel_has_agent_prompt(Broken(), uuid4()) is True


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


@pytest.mark.asyncio
async def test_redaction_only_happens_at_agent_card_questions(monkeypatch):
    class C:
        def __init__(self, open_):
            self.open_, self.calls = open_, 0

        async def fetchval(self, *_a):
            self.calls += 1
            return self.open_

    text = f"pay with {VISA}"
    quiet = C(False)
    assert await channels_ws._agent_card_redaction(quiet, uuid4(), "hello", None) == ("hello", False)
    assert quiet.calls == 0  # ordinary chat never queries
    assert await channels_ws._agent_card_redaction(quiet, uuid4(), text, None) == (text, False)
    assert quiet.calls == 1
    removed = (f"pay with {card_vault.REDACTED}", True)
    assert await channels_ws._agent_card_redaction(C(True), uuid4(), text, None) == removed
    threaded = C(False)
    assert await channels_ws._agent_card_redaction(threaded, uuid4(), text, uuid4()) == removed
    assert threaded.calls == 0
    assert await channels_ws._agent_card_redaction(quiet, uuid4(), None, None) == (None, False)


def test_routing_answers_to_agent_card_questions(monkeypatch):
    route = channels_ws._routes_to_agent_card
    base = dict(agent_prompt_id=None, card_number_removed=False, reply_to_id=None,
                mention_handles=[], content="yes", room_key=str(uuid4()))
    assert route(**base)
    assert route(**{**base, "agent_prompt_id": uuid4(), "content": "anything"})
    assert route(**{**base, "card_number_removed": True, "content": "x"})
    assert not route(**{**base, "content": "see you at 5"})
    assert not route(**{**base, "reply_to_id": uuid4()})  # a reply to someone else
    assert not route(**{**base, "mention_handles": ["espresso"]})
    monkeypatch.setattr(channels_ws, "_channel_recently_ems_drafted", lambda _k: True)
    assert not route(**base)  # a live Huume event-draft pill keeps its "yes"
