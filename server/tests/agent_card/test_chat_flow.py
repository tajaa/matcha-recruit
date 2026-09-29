import json
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_card import chat_flow
from app.matcha.services.matcha_work.agent_card.chat_flow import Answer, parse_answer

RESULT = {
    "schema": "agent_result.v1",
    "headline": "Best organic lip balm: Dr. Bronner's",
    "summary": "Certified organic, cheap, well reviewed.",
    "answer_type": "recommendation",
    "top_pick": {
        "name": "Organic Lip Balm", "brand": "Dr. Bronner's",
        "why": ["USDA organic", "Fair trade", "Under $5", "Fourth reason"],
        "price": {"amount": 4.49, "currency": "USD", "source_url": "https://shop.example.com/p"},
        "rating": {"value": 4.7, "scale": 5.0, "count": 1203, "source_url": "https://shop.example.com/p"},
        "reviews": [], "images": [],
        "buy_links": [{"retailer": "Shop", "url": "https://shop.example.com/p", "price": 4.29}],
    },
    "alternatives": [{"name": "Badger Balm", "brand": "", "why": [], "price": None, "rating": None,
                      "reviews": [], "images": [], "buy_links": []}],
    "sections": [], "caveats": [], "sources": [], "confidence": "high",
}


# ── parsing and formatting ────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("yes", Answer("yes")), ("Yes!", Answer("yes")), ("@espresso yes please", Answer("yes")),
    ("sure", Answer("yes")), ("no thanks", Answer("no")), ("Nope.", Answer("no")),
    ("4242", Answer("last4", "4242")), ("the card ending in 4242", Answer("last4", "4242")),
    ("use 4242", Answer("last4", "4242")),
    ("yes but only vegan ones", None), ("what about cheaper ones?", None), ("", None),
    ("y" * 61, None),
])
def test_parse_answer(text, expected):
    assert parse_answer(text) == expected


def test_only_platform_admins_can_buy_in_v1():
    assert chat_flow.purchases_allowed("admin")
    assert not chat_flow.purchases_allowed("client")
    assert not chat_flow.purchases_allowed(None)


def test_format_result_is_a_short_read_with_ticket_chip():
    task_id = uuid4()
    text = chat_flow.format_result(RESULT, task_id=task_id, title="Find a | balm", column="review")
    assert text.startswith(f"⟦ticket:{task_id}|Find a / balm|Review⟧")
    assert "Top pick: Organic Lip Balm by Dr. Bronner's · $4.49 · 4.7/5 from 1,203 ratings" in text
    assert "• Fourth reason" not in text  # at most 3 reasons
    assert "Buy at Shop: https://shop.example.com/p" in text
    assert "• Badger Balm" in text
    assert text.endswith("is on the card.")


def test_format_result_for_a_plain_answer_lists_sections_and_caps_length():
    result = {"headline": "H", "summary": "S" * 5000, "answer_type": "answer", "top_pick": None,
              "alternatives": [], "sections": [{"heading": "History", "body_md": "x"}]}
    text = chat_flow.format_result(result, task_id=uuid4(), title="t", column=None)
    assert len(text) <= chat_flow.MAX_MESSAGE_CHARS
    result["summary"] = "short"
    assert "Covers: History" in chat_flow.format_result(result, task_id=uuid4(), title="t", column=None)


def test_purchase_offer_freezes_item_store_link_and_price():
    offer = chat_flow.purchase_offer(RESULT)
    assert offer == {
        "item_name": "Organic Lip Balm", "brand": "Dr. Bronner's", "retailer": "Shop",
        "checkout_url": "https://shop.example.com/p", "amount": 4.29, "currency": "USD",
    }
    assert chat_flow.purchase_offer({**RESULT, "answer_type": "answer"}) is None
    no_link = json.loads(json.dumps(RESULT))
    no_link["top_pick"]["buy_links"] = [{"retailer": "x", "url": "javascript:alert(1)", "price": None}]
    assert chat_flow.purchase_offer(no_link) is None
    assert chat_flow.purchase_offer(None) is None


def test_format_money():
    assert chat_flow.format_money(4.5, "usd") == "$4.50"
    assert chat_flow.format_money(10, "EUR") == "10.00 EUR"
    assert chat_flow.format_money(None, "USD") is None
    assert chat_flow.format_money("x", "USD") is None


def test_prompt_reference():
    pid = uuid4()
    assert chat_flow.prompt_reference({"kind": "agent_card_prompt", "prompt_id": str(pid)}) == pid
    assert chat_flow.prompt_reference(json.dumps({"kind": "agent_card_prompt", "prompt_id": str(pid)})) == pid
    assert chat_flow.prompt_reference({"kind": "autopr_context_request"}) is None
    assert chat_flow.prompt_reference({"kind": "agent_card_prompt", "prompt_id": "nope"}) is None
    assert chat_flow.prompt_reference("not json") is None


# ── a small in-memory database ────────────────────────────────────────────────

class _DB:
    def __init__(self, *, access=True, result=RESULT, cards=None):
        self.access = access
        self.result = result
        self.cards = cards or []
        self.prompts: dict = {}
        self.purchases: list = []
        self.executed: list = []

    def add_prompt(self, kind="show_result", *, owner=None, payload=None, status="open", live=True):
        pid = uuid4()
        self.prompts[pid] = {
            "id": pid, "company_id": self.company_id, "project_id": self.project_id,
            "task_id": self.task_id, "run_id": self.run_id, "channel_id": self.channel_id,
            "kind": kind, "owner_user_id": owner, "payload": json.dumps(payload or {}),
            "status": status, "live": live and status == "open", "seq": len(self.prompts),
        }
        return pid

    company_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    channel_id = uuid4()

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *args):
        if "FROM mw_agent_card_prompts WHERE id = $1" in query:
            p = self.prompts.get(args[0])
            return dict(p) if p and p["channel_id"] == args[1] else None
        if "FROM mw_agent_card_prompts" in query and "ORDER BY created_at DESC" in query:
            open_ = [p for p in self.prompts.values() if p["channel_id"] == args[0] and p["live"]]
            return dict(max(open_, key=lambda p: p["seq"])) if open_ else None
        if "r.result, t.title" in query:
            return {"result": json.dumps(self.result) if self.result else None,
                    "title": "Find a balm", "board_column": "review"}
        if "FROM mw_payment_cards WHERE id = $1" in query:
            return next((c for c in self.cards if c["id"] == args[0] and c["user_id"] == args[1]), None)
        raise AssertionError(query)

    async def fetch(self, query, *args):
        assert "FROM mw_payment_cards" in query
        return [c for c in self.cards if c["user_id"] == args[0]]

    async def fetchval(self, query, *args):
        if "mw_project_collaborators" in query:
            return self.access
        if query.lstrip().startswith("UPDATE mw_agent_card_prompts"):
            p = self.prompts[args[0]]
            if not p["live"]:
                return None
            p.update(status="answered", live=False, answer=args[1], answered_by=args[2])
            return True
        if "INSERT INTO mw_agent_card_prompts" in query:
            pid = uuid4()
            self.prompts[pid] = {
                "id": pid, "company_id": args[0], "project_id": args[1], "task_id": args[2],
                "run_id": args[3], "channel_id": args[4], "kind": args[5], "owner_user_id": args[6],
                "payload": args[7], "status": "open", "live": True, "seq": len(self.prompts),
                "ttl": args[8],
            }
            return pid
        raise AssertionError(query)

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "INSERT INTO mw_agent_purchase_requests" in query:
            self.purchases.append(args)


@pytest.fixture
def env(monkeypatch):
    holder = {"db": _DB(), "said": [], "broadcast": []}

    @asynccontextmanager
    async def cod():
        yield holder["db"]

    async def persist(conn, company_id, channel_id, content, *, metadata=None):
        message = {"id": str(uuid4()), "channel_id": str(channel_id), "content": content, "metadata": metadata or {}}
        holder["said"].append(message)
        return message

    async def broadcast(payload):
        holder["broadcast"].append(payload)

    monkeypatch.setattr(chat_flow, "connection_or_direct", cod)
    monkeypatch.setattr(chat_flow, "persist_espresso_message", persist)
    monkeypatch.setattr(chat_flow, "broadcast_espresso_message", broadcast)
    return holder


def _user(role="admin"):
    return SimpleNamespace(id=uuid4(), role=role)


def _card(user, last4="4242", label="Mercury test", exp_year=2031):
    return {"id": uuid4(), "user_id": user.id, "label": label, "brand": "visa", "last4": last4,
            "exp_month": 12, "exp_year": exp_year}


async def _answer(env, user, text, prompt_id=None, **kw):
    return await chat_flow.handle_chat_answer(
        channel_id=env["db"].channel_id, user=user, content=text, prompt_id=prompt_id, **kw,
    )


def _said(env):
    return [m["content"] for m in env["said"]]


# ── the whole conversation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_yes_shows_the_result_then_offers_to_buy_then_records_a_handoff(env):
    db, user = env["db"], _user("admin")
    db.cards = [_card(user)]
    offer_id = db.add_prompt("show_result")

    assert await _answer(env, user, "yes")  # a plain "yes" finds the open question
    assert db.prompts[offer_id]["status"] == "answered"
    assert "Top pick: Organic Lip Balm" in _said(env)[0]
    buy_q = next(p for p in db.prompts.values() if p["kind"] == "purchase")
    assert buy_q["owner_user_id"] == user.id and buy_q["ttl"] == chat_flow.PURCHASE_TTL
    assert "Want me to buy it? Organic Lip Balm at Shop for $4.29" in _said(env)[1]
    assert env["said"][1]["metadata"]["prompt_kind"] == "purchase"

    assert await _answer(env, user, "yes", prompt_id=buy_q["id"])
    pick_q = next(p for p in db.prompts.values() if p["kind"] == "pick_card")
    assert "Use your Visa ending 4242 (Mercury test)?" in _said(env)[2]
    assert json.loads(pick_q["payload"])["checkout_url"] == "https://shop.example.com/p"

    assert await _answer(env, user, "yes")
    assert len(db.purchases) == 1
    args = db.purchases[0]
    assert args[5] == user.id and args[7] == "4242" and args[8] == "Organic Lip Balm"
    assert args[10] == "https://shop.example.com/p" and args[11] == 4.29
    assert "I haven't charged anything" in _said(env)[3]
    assert "https://shop.example.com/p" in _said(env)[3]
    assert len(env["broadcast"]) == len(env["said"])  # every message fanned out after commit


@pytest.mark.asyncio
async def test_non_admins_see_the_result_but_are_never_offered_a_purchase(env):
    db, user = env["db"], _user("client")
    db.add_prompt("show_result")
    assert await _answer(env, user, "yes")
    assert len(env["said"]) == 1
    assert not any(p["kind"] == "purchase" for p in db.prompts.values())


@pytest.mark.asyncio
async def test_no_skips_and_the_question_is_answered_once(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "no", prompt_id=pid)
    assert "on the card whenever you want it" in _said(env)[0]
    # A second reply to the same (now closed) question is told so.
    assert await _answer(env, user, "yes", prompt_id=pid)
    assert "closed" in _said(env)[1]


@pytest.mark.asyncio
async def test_untargeted_chatter_is_left_alone(env):
    db, user = env["db"], _user()
    db.add_prompt("show_result")
    assert await _answer(env, user, "lunch at noon?") is False
    assert env["said"] == []


@pytest.mark.asyncio
async def test_no_open_question_means_not_ours(env):
    assert await _answer(env, _user(), "yes") is False


@pytest.mark.asyncio
async def test_threaded_reply_that_isnt_an_answer_gets_a_hint(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "what did you find?", prompt_id=pid)
    assert _said(env) == [chat_flow._HINTS["show_result"]]


@pytest.mark.asyncio
async def test_threaded_chatter_on_a_closed_question_is_just_chat(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("show_result", status="answered")
    assert await _answer(env, user, "thanks!", prompt_id=pid)
    assert env["said"] == []


@pytest.mark.asyncio
async def test_people_outside_the_project_cannot_answer(env):
    db, user = env["db"], _user("client")
    db.access = False
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "yes") is False  # untargeted: silently not ours
    assert await _answer(env, user, "yes", prompt_id=pid)
    assert "people on this project" in _said(env)[0]
    assert db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_only_the_buyer_can_answer_purchase_questions(env):
    db, owner, other = env["db"], _user(), _user()
    pid = db.add_prompt("purchase", owner=owner.id, payload=chat_flow.purchase_offer(RESULT))
    assert await _answer(env, other, "yes") is False
    assert await _answer(env, other, "yes", prompt_id=pid)
    assert "Only the person who asked" in _said(env)[0]
    assert db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_yes_to_buy_without_a_saved_card_keeps_the_question_open(env):
    db, user = env["db"], _user()
    db.cards = [_card(user, exp_year=2020)]  # expired cards don't count
    pid = db.add_prompt("purchase", owner=user.id, payload=chat_flow.purchase_offer(RESULT))
    assert await _answer(env, user, "yes", prompt_id=pid)
    assert "Payment cards" in _said(env)[0] and "never paste" in _said(env)[0]
    assert db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_several_cards_are_picked_by_last_four(env):
    db, user = env["db"], _user()
    db.cards = [_card(user, "4242"), _card(user, "5454", label="")]
    pid = db.add_prompt("purchase", owner=user.id, payload=chat_flow.purchase_offer(RESULT))
    await _answer(env, user, "yes", prompt_id=pid)
    assert "Which card? Reply with the last 4 digits: Visa ending 4242 (Mercury test); Visa ending 5454" in _said(env)[0]
    pick = next(p for p in db.prompts.values() if p["kind"] == "pick_card")
    await _answer(env, user, "yes", prompt_id=pick["id"])  # ambiguous with 2 cards
    assert _said(env)[1] == chat_flow._HINTS["pick_card"]
    await _answer(env, user, "1111")
    assert "don't see a saved card ending 1111" in _said(env)[2]
    await _answer(env, user, "card ending 5454")
    assert db.purchases[0][7] == "5454"


@pytest.mark.asyncio
async def test_a_card_removed_before_the_pick_is_refused(env):
    db, user = env["db"], _user()
    card = _card(user)
    pid = db.add_prompt("pick_card", owner=user.id, payload={
        **chat_flow.purchase_offer(RESULT),
        "options": [{"card_id": str(card["id"]), "last4": "4242", "brand": "visa", "label": ""}],
    })
    assert await _answer(env, user, "4242", prompt_id=pid)
    assert "removed or has expired" in _said(env)[0]
    assert db.purchases == [] and db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_no_to_buy_or_to_the_card_cancels(env):
    db, user = env["db"], _user()
    buy = db.add_prompt("purchase", owner=user.id, payload=chat_flow.purchase_offer(RESULT))
    await _answer(env, user, "no", prompt_id=buy)
    pick = db.add_prompt("pick_card", owner=user.id, payload={"options": []})
    await _answer(env, user, "cancel", prompt_id=pick)
    assert _said(env) == ["Okay, I won't buy it.", "Okay, cancelled. Nothing was bought."]
    assert db.purchases == []


@pytest.mark.asyncio
async def test_last_four_is_only_an_answer_to_the_card_question(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "4242") is False
    assert await _answer(env, user, "4242", prompt_id=pid)
    assert _said(env) == [chat_flow._HINTS["show_result"]]


@pytest.mark.asyncio
async def test_removed_card_number_gets_a_warning_not_an_answer(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("pick_card", owner=user.id, payload={"options": []})
    assert await _answer(env, user, "[card number removed]", card_number_removed=True)
    assert "removed a card number" in _said(env)[0]
    assert db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_a_card_photo_reply_is_refused(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("pick_card", owner=user.id, payload={"options": []})
    assert await _answer(env, user, "", prompt_id=pid, has_attachments=True)
    assert "don't read card photos" in _said(env)[0]


@pytest.mark.asyncio
async def test_a_result_that_no_longer_loads(env):
    db, user = env["db"], _user()
    db.result = None
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "yes", prompt_id=pid)
    assert "couldn't load that result" in _said(env)[0]


# ── the worker's offer ────────────────────────────────────────────────────────

class _OfferConn:
    def __init__(self, row, inserted=True):
        self.row, self.inserted = row, inserted
        self.executed = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *args):
        assert "FROM mw_project_agent_runs r" in query
        return self.row

    async def fetchval(self, query, *args):
        assert "ON CONFLICT (run_id) WHERE kind = 'show_result' DO NOTHING" in query
        assert args[5] == chat_flow.OFFER_TTL
        return uuid4() if self.inserted else None

    async def execute(self, query, *args):
        self.executed.append(query)


def _offer_row(**over):
    row = {"company_id": uuid4(), "project_id": uuid4(), "task_id": uuid4(), "round": 1,
           "status": "done", "title": "Find a balm", "board_column": "review", "channel_id": str(uuid4())}
    row.update(over)
    return row


@pytest.fixture
def offer_env(monkeypatch):
    holder = {"said": []}

    @asynccontextmanager
    async def cod():
        yield holder["conn"]

    async def persist(conn, company_id, channel_id, content, *, metadata=None):
        holder["said"].append((content, metadata))
        return {"id": str(uuid4())}

    monkeypatch.setattr(chat_flow, "connection_or_direct", cod)
    monkeypatch.setattr(chat_flow, "persist_espresso_message", persist)
    holder["broadcast"] = AsyncMock()
    monkeypatch.setattr(chat_flow, "broadcast_espresso_message", holder["broadcast"])
    return holder


@pytest.mark.asyncio
async def test_offer_asks_once_and_supersedes_older_questions(offer_env):
    offer_env["conn"] = conn = _OfferConn(_offer_row())
    assert await chat_flow.offer_result(uuid4())
    content, metadata = offer_env["said"][0]
    assert "I finished \"Find a balm\". Want to see what I found? Reply yes or no." in content
    assert metadata["kind"] == "agent_card_prompt" and metadata["prompt_kind"] == "show_result"
    assert any("pg_advisory_xact_lock" in q for q in conn.executed)
    assert any("SET status = 'superseded'" in q for q in conn.executed)
    assert any("SET message_id" in q for q in conn.executed)
    offer_env["broadcast"].assert_awaited_once()


@pytest.mark.asyncio
async def test_offer_for_a_revision_says_reworked(offer_env):
    offer_env["conn"] = _OfferConn(_offer_row(round=2))
    await chat_flow.offer_result(uuid4())
    assert "I reworked" in offer_env["said"][0][0]


@pytest.mark.asyncio
async def test_offer_is_idempotent_per_run(offer_env):
    offer_env["conn"] = conn = _OfferConn(_offer_row(), inserted=False)
    assert await chat_flow.offer_result(uuid4())
    assert offer_env["said"] == []
    assert not any("superseded" in q for q in conn.executed)


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [None, _offer_row(status="failed"), _offer_row(channel_id=None), _offer_row(channel_id="junk")])
async def test_no_offer_without_a_finished_run_and_a_project_chat(offer_env, row):
    offer_env["conn"] = _OfferConn(row)
    assert await chat_flow.offer_result(uuid4()) is False
    assert offer_env["said"] == []


@pytest.mark.asyncio
async def test_channel_has_open_prompt_and_close_open_prompts():
    class C:
        def __init__(self):
            self.q = []

        async def fetchval(self, query, *args):
            self.q.append(query)
            return True

        async def execute(self, query, *args):
            self.q.append(query)

    conn, cid = C(), uuid4()
    assert await chat_flow.channel_has_open_prompt(conn, cid) is True
    await chat_flow.close_open_prompts(conn, cid)
    assert "expires_at > NOW()" in conn.q[0] and "superseded" in conn.q[1]


def test_ttls_are_sane():
    assert chat_flow.PICK_CARD_TTL < chat_flow.PURCHASE_TTL < chat_flow.OFFER_TTL <= timedelta(days=7)
