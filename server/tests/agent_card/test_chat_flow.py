import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.models.auth import CurrentUser
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
OFFER = chat_flow.purchase_offer(RESULT)


# ── parsing and formatting ────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("yes", Answer("yes")), ("Yes!", Answer("yes")), ("@espresso yes please", Answer("yes")),
    ("sure", Answer("yes")), ("no thanks", Answer("no")), ("Nope.", Answer("no")),
    ("4242", Answer("last4", "4242")), ("the card ending in 4242", Answer("last4", "4242")),
    ("use 4242", Answer("last4", "4242")), ("2", Answer("choice", "2")), ("card 1", Answer("choice", "1")),
    ("yes but only vegan ones", None), ("what about cheaper ones?", None), ("", None), ("0", None),
    ("y" * 61, None),
])
def test_parse_answer_for_threaded_replies(text, expected):
    assert parse_answer(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("yes", True), ("Yes please!", True), ("show me", True), ("@espresso yes", True),
    # Everyday acknowledgements are never answers without a reply target.
    ("ok", False), ("k", False), ("sure", False), ("please", False), ("no", False),
    ("later", False), ("stop", False), ("4242", False), ("1", False), ("yes " * 10, False),
])
def test_plain_messages_only_count_as_an_explicit_yes(text, expected):
    assert chat_flow.is_plain_yes(text) is expected


@pytest.mark.parametrize("text, expected", [
    ("Buy the best one", True), ("buy it", True), ("please purchase it", True), ("place the order", True),
    ("buy", True), ("go ahead and buy the top pick", True), ("Yes, buy it!", True), ("let's buy it", True),
    ("I want to buy it", True), ("can you order it for me please", True), ("@espresso buy that one", True),
    # New business, not a yes to the open question:
    ("I want to buy new shoes tomorrow", False), ("find me wool socks to buy", False), ("buy new shoes", False),
    # A buy word plus a stray it/this/that inside an ordinary sentence:
    ("find me a rain jacket to buy that is waterproof", False), ("I want to buy a desk, is it worth it", False),
    ("should we buy this for the office or wait", False), ("buy it from a local store instead?", False),
    ("ok", False), ("sure", False), ("don't buy it", False), ("do not purchase", False),
    ("not yet, don't order", False), ("cancel the order", False), ("wait before you buy", False),
    ("buy " * 30, False),
])
def test_buy_intent(text, expected):
    assert chat_flow.is_buy_intent(text) is expected


def test_buying_is_admins_plus_an_email_allowlist(monkeypatch):
    person = lambda role, email: SimpleNamespace(role=role, email=email)  # noqa: E731
    monkeypatch.delenv(chat_flow.PURCHASE_ALLOWLIST_ENV, raising=False)
    assert chat_flow.purchases_allowed(person("admin", "a@example.com"))
    assert not chat_flow.purchases_allowed(person("individual", "haley@example.com"))
    assert not chat_flow.purchases_allowed(None)
    monkeypatch.setenv(chat_flow.PURCHASE_ALLOWLIST_ENV, " Haley@Example.com , other@example.com")
    assert chat_flow.purchases_allowed(person("individual", "haley@example.com"))
    assert not chat_flow.purchases_allowed(person("client", "someone@example.com"))
    assert not chat_flow.purchases_allowed(person("client", ""))


def test_format_result_is_a_short_fallback_without_raw_urls():
    task_id = uuid4()
    text = chat_flow.format_result(RESULT, task_id=task_id, title="Find a | balm", column="review")
    assert text.startswith(f"⟦ticket:{task_id}|Find a / balm|Review⟧")
    assert "Top pick: Organic Lip Balm by Dr. Bronner's · $4.49 · 4.7/5 from 1,203 ratings" in text
    assert "Also compared: Badger Balm" in text
    assert "http" not in text  # links live on the card and in the rich message
    assert text.endswith("is on the card.")


def test_result_view_is_what_the_chat_card_renders():
    result = json.loads(json.dumps(RESULT))
    result["top_pick"]["images"] = [
        {"url": "http://insecure.example.com/a.webp", "page_url": "x", "alt": "a"},
        {"url": "https://cdn.example.com/a.webp", "page_url": "x", "alt": "a"},
    ]
    result["summary"] = "First sentence is here. " + "Long detail " * 60
    view = chat_flow.result_view(result)
    pick = view["top_pick"]
    assert pick["image_url"] == "https://cdn.example.com/a.webp"  # https (our CDN) only
    assert pick["price_text"] == "$4.49" and pick["rating"] == {"value": 4.7, "scale": 5.0, "count": 1203}
    assert pick["why"] == ["USDA organic", "Fair trade", "Under $5"]
    assert pick["buy_url"] == "https://shop.example.com/p" and pick["retailer"] == "Shop"
    assert view["alternatives"] == [{"name": "Badger Balm", "brand": None, "image_url": None,
                                     "price_text": None, "buy_url": None, "retailer": None}]
    assert len(view["summary"]) <= 421 and view["summary"].endswith("…")
    assert view["sections"] == []
    answer = chat_flow.result_view({"headline": "H", "summary": "S", "top_pick": None,
                                    "sections": [{"heading": "History", "body_md": "x"}]})
    assert answer["answer_type"] == "answer" and answer["sections"] == ["History"]


def test_short_clips_at_a_sentence_or_a_word():
    assert chat_flow._short("short", 20) == "short"
    assert chat_flow._short("One two three. Four five six seven", 20) == "One two three."
    assert chat_flow._short("alpha beta gamma delta epsilon", 16) == "alpha beta gamma…"
    assert chat_flow._short("alpha beta gamma delta epsilon", 14) == "alpha beta…"


def test_format_result_for_a_plain_answer_lists_sections_and_caps_length():
    result = {"headline": "H", "summary": "S" * 5000, "answer_type": "answer", "top_pick": None,
              "alternatives": [], "sections": [{"heading": "History", "body_md": "x"}]}
    text = chat_flow.format_result(result, task_id=uuid4(), title="t", column=None)
    assert len(text) <= chat_flow.MAX_MESSAGE_CHARS
    result["summary"] = "short"
    assert "Covers: History" in chat_flow.format_result(result, task_id=uuid4(), title="t", column=None)


def test_purchase_offer_freezes_item_store_link_and_verified_price():
    assert OFFER == {
        "item_name": "Organic Lip Balm", "brand": "Dr. Bronner's", "retailer": "Shop",
        "checkout_url": "https://shop.example.com/p", "amount": 4.49, "currency": "USD",
        "image_url": None,
    }
    assert chat_flow.purchase_offer({**RESULT, "answer_type": "answer"}) is None
    no_link = json.loads(json.dumps(RESULT))
    no_link["top_pick"]["buy_links"] = [{"retailer": "x", "url": "javascript:alert(1)", "price": None}]
    assert chat_flow.purchase_offer(no_link) is None
    assert chat_flow.purchase_offer(None) is None


def test_a_buy_links_own_price_is_never_offered_as_the_total():
    # A UK store's model-asserted 12.99 with no source-checked pick price must
    # not become "$12.99" on the purchase.
    unverified = json.loads(json.dumps(RESULT))
    unverified["top_pick"]["price"] = None
    unverified["top_pick"]["buy_links"] = [{"retailer": "UK Shop", "url": "https://uk.example.com/p", "price": 12.99}]
    offer = chat_flow.purchase_offer(unverified)
    assert offer["amount"] is None and offer["currency"] is None
    assert chat_flow._offer_line(offer) == "Organic Lip Balm at UK Shop (price not confirmed)"
    gbp = json.loads(json.dumps(RESULT))
    gbp["top_pick"]["price"] = {"amount": 9.5, "currency": "GBP", "source_url": "https://uk.example.com/p"}
    assert chat_flow._offer_line(chat_flow.purchase_offer(gbp)).endswith("for 9.50 GBP")


def test_format_money():
    assert chat_flow.format_money(4.5, "usd") == "$4.50"
    assert chat_flow.format_money(10, "EUR") == "10.00 EUR"
    assert chat_flow.format_money(None, "USD") is None
    assert chat_flow.format_money("x", "USD") is None


def test_card_label_redacts_a_card_number_in_an_old_label():
    label = chat_flow._card_label({"brand": "visa", "last4": "4242", "label": "Visa 4242 4242 4242 4242",
                                   "exp_month": 3, "exp_year": 2031}, with_expiry=True)
    assert "4242 4242" not in label
    assert label.endswith("expires 03/31)")


def test_prompt_reference():
    pid = uuid4()
    assert chat_flow.prompt_reference({"kind": "agent_card_prompt", "prompt_id": str(pid)}) == pid
    assert chat_flow.prompt_reference(json.dumps({"kind": "agent_card_prompt", "prompt_id": str(pid)})) == pid
    assert chat_flow.prompt_reference({"kind": "autopr_context_request"}) is None
    assert chat_flow.prompt_reference({"kind": "agent_card_prompt", "prompt_id": "nope"}) is None
    assert chat_flow.prompt_reference("not json") is None
    assert chat_flow.prompt_reference(None) is None


# ── a small in-memory database ────────────────────────────────────────────────

class _DB:
    company_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    channel_id = uuid4()

    def __init__(self, *, result=RESULT, cards=None):
        self.result = result
        self.cards = cards or []
        self.prompts: dict = {}
        self.purchases: list = []
        self.locks: list = []
        self.charge_updates: list = []
        self.newer_run = False

    def add_prompt(self, kind="show_result", *, owner=None, payload=None, status="open", live=True,
                   age=timedelta(0)):
        pid = uuid4()
        self.prompts[pid] = {
            "age": age,
            "id": pid, "company_id": self.company_id, "project_id": self.project_id,
            "task_id": self.task_id, "run_id": self.run_id, "channel_id": self.channel_id,
            "kind": kind, "owner_user_id": owner, "payload": json.dumps(payload or {}),
            "status": status, "live": live and status == "open", "seq": len(self.prompts),
        }
        return pid

    def _newest(self, match):
        found = [p for p in self.prompts.values() if p["live"] and match(p)]
        return dict(max(found, key=lambda p: p["seq"])) if found else None

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *args):
        if "INSERT INTO mw_agent_card_prompts" in query:
            pid = uuid4()
            self.prompts[pid] = {
                "id": pid, "company_id": args[0], "project_id": args[1], "task_id": args[2],
                "run_id": args[3], "channel_id": args[4], "kind": args[5], "owner_user_id": args[6],
                "payload": args[7], "status": "open", "live": True, "seq": len(self.prompts),
                "ttl": args[8],
            }
            return {"id": pid, "expires_at": datetime(2031, 1, 1, tzinfo=timezone.utc)}
        if "FROM mw_agent_card_prompts WHERE id = $1" in query:
            p = self.prompts.get(args[0])
            return dict(p) if p and p["channel_id"] == args[1] else None
        if "FROM mw_agent_card_prompts" in query and "owner_user_id = $2" in query:
            kinds, max_age = args[2], args[3]
            return self._newest(lambda p: p["owner_user_id"] == args[1] and p["kind"] in kinds
                                and (max_age is None or p.get("age", timedelta(0)) < max_age))
        if "FROM mw_agent_card_prompts" in query and "kind = 'show_result'" in query:
            return self._newest(lambda p: p["kind"] == "show_result")
        if "r.result, t.title" in query:
            return {"result": json.dumps(self.result) if self.result else None,
                    "title": "Find a balm", "board_column": "review"}
        if "FROM mw_payment_cards WHERE id = $1" in query:
            return next((c for c in self.cards if c["id"] == args[0] and c["user_id"] == args[1]), None)
        raise AssertionError(query)

    async def fetch(self, query, *args):
        if "SET status = 'superseded'" in query:
            closed = [p for p in self.prompts.values() if p["task_id"] == args[0] and p["live"]]
            for p in closed:
                p.update(status="superseded", live=False)
            return [{"id": p["id"], "channel_id": p["channel_id"], "kind": p["kind"]} for p in closed]
        assert "FROM mw_payment_cards" in query
        return [c for c in self.cards if c["user_id"] == args[0]]

    async def fetchval(self, query, *args):
        if query == chat_flow._NEWER_RUN_SQL:
            return self.newer_run
        if query.lstrip().startswith("UPDATE mw_agent_card_prompts"):
            p = self.prompts[args[0]]
            if not p["live"]:
                return None
            p.update(status="answered", live=False, answer=args[1], answered_by=args[2])
            return True
        if "INSERT INTO mw_agent_purchase_requests" in query:
            self.purchases.append(args)
            return uuid4()
        raise AssertionError(query)

    async def execute(self, query, *args):
        if "pg_advisory_xact_lock" in query:
            self.locks.append(args[0])
        elif "UPDATE mw_agent_purchase_requests" in query:
            self.charge_updates.append(args)


@pytest.fixture
def env(monkeypatch):
    holder = {"db": _DB(), "said": [], "broadcast": [], "access": True, "updates": []}

    @asynccontextmanager
    async def cod():
        yield holder["db"]

    async def persist(conn, company_id, channel_id, content, *, metadata=None):
        message = {"id": str(uuid4()), "channel_id": str(channel_id), "content": content, "metadata": metadata or {}}
        holder["said"].append(message)
        return message

    async def broadcast(payload):
        holder["broadcast"].append(payload)

    async def publish_update(update):
        holder["updates"].append(update)

    async def access(prompt, user):
        return holder["access"]

    monkeypatch.setattr(chat_flow, "connection_or_direct", cod)
    monkeypatch.setattr(chat_flow, "persist_espresso_message", persist)
    monkeypatch.setattr(chat_flow, "broadcast_espresso_message", broadcast)
    monkeypatch.setattr(chat_flow, "_publish_prompt_update", publish_update)
    monkeypatch.setattr(chat_flow, "_can_access_project", access)
    # Handoff-only unless a test opts into the Stripe test charge.
    monkeypatch.setattr(chat_flow.test_charge, "test_key", lambda: None)
    return holder


def _user(role="admin"):
    return SimpleNamespace(id=uuid4(), role=role, email="person@example.com")


def _card(user, last4="4242", label="Mercury test", exp_year=2031, exp_month=12):
    return {"id": uuid4(), "user_id": user.id, "label": label, "brand": "visa", "last4": last4,
            "exp_month": exp_month, "exp_year": exp_year}


async def _answer(env, user, text, prompt_id=None, **kw):
    return await chat_flow.handle_chat_answer(
        channel_id=env["db"].channel_id, user=user, content=text, prompt_id=prompt_id, **kw,
    )


def _said(env):
    return [m["content"] for m in env["said"]]


def _newest(db, kind):
    return max((p for p in db.prompts.values() if p["kind"] == kind), key=lambda p: p["seq"])


# ── the whole conversation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_yes_shows_the_result_then_threaded_replies_buy_it(env):
    db, user = env["db"], _user("admin")
    db.cards = [_card(user)]
    offer_id = db.add_prompt("show_result")

    assert await _answer(env, user, "yes")  # a plain "yes" shows the newest result
    assert db.prompts[offer_id]["status"] == "answered"
    assert "Top pick: Organic Lip Balm" in _said(env)[0]
    result_meta = env["said"][0]["metadata"]
    assert result_meta["kind"] == "agent_card_result" and result_meta["result"]["top_pick"]["price_text"] == "$4.49"
    buy_q = _newest(db, "purchase")
    assert buy_q["owner_user_id"] == user.id and buy_q["ttl"] == chat_flow.PURCHASE_TTL
    assert "Want me to buy it? Organic Lip Balm at Shop for $4.49. Reply yes (or \"buy it\")" in _said(env)[1]
    assert env["said"][1]["metadata"]["prompt_kind"] == "purchase"
    # Only the buyer gets live buttons, and they retire on time.
    assert env["said"][1]["metadata"]["owner_user_id"] == str(user.id)
    assert env["said"][1]["metadata"]["expires_at"] == "2031-01-01T00:00:00+00:00"
    # Every open chat hears the "see it?" question closed.
    assert env["updates"] == [{
        "type": "agent_card_prompt_updated", "channel_id": str(db.channel_id), "prompt_id": str(offer_id),
        "status": "answered", "answer": "yes", "answer_text": "Showed the result",
    }]
    view = env["said"][1]["metadata"]["view"]
    assert view["offer"]["price_text"] == "$4.49" and view["offer"]["item_name"] == "Organic Lip Balm"
    assert [b["reply"] for b in view["buttons"]] == ["Buy it", "No thanks"]
    # Every button reply parses as the answer it stands for.
    assert [parse_answer(b["reply"]).kind for b in view["buttons"]] == ["yes", "no"]
    assert db.locks == [f"{db.task_id}:card_agent"]  # the claim holds enqueue's per-card lock

    assert await _answer(env, user, "yes", prompt_id=buy_q["id"])
    pick_q = _newest(db, "pick_card")
    assert "Use your Visa ending 4242 (Mercury test, expires 12/31)? Reply yes (or 1) to confirm" in _said(env)[2]
    assert json.loads(pick_q["payload"])["checkout_url"] == "https://shop.example.com/p"
    pick_view = env["said"][2]["metadata"]["view"]
    assert pick_view["buttons"][0] == {"label": "Visa •••• 4242", "reply": "Use card 1", "style": "primary",
                                       "detail": "Mercury test, expires 12/31"}
    assert parse_answer(pick_view["buttons"][0]["reply"]) == Answer("choice", "1")
    assert parse_answer(pick_view["buttons"][-1]["reply"]).kind == "no"

    assert await _answer(env, user, "yes", prompt_id=pick_q["id"])
    assert len(db.purchases) == 1
    args = db.purchases[0]
    assert args[5] == user.id and args[7] == "4242" and args[8] == "Organic Lip Balm"
    assert args[10] == "https://shop.example.com/p" and args[11] == 4.49 and args[12] == "USD"
    assert "I haven't charged anything" in _said(env)[3]
    assert [(u["prompt_id"], u["answer"]) for u in env["updates"]] == [
        (str(offer_id), "yes"), (str(buy_q["id"]), "yes"), (str(pick_q["id"]), "card:4242"),
    ]
    assert len(env["broadcast"]) == len(env["said"])  # every message fanned out after commit


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["ok", "sure", "k", "no", "later", "don't buy it", "not yet, don't order"])
async def test_everyday_or_negated_replies_never_answer_a_purchase_question(env, text):
    # An admin's "ok" to a colleague must not approve a purchase or pick a card.
    db, user = env["db"], _user()
    db.cards = [_card(user)]
    buy = db.add_prompt("purchase", owner=user.id, payload=OFFER)
    pick = db.add_prompt("pick_card", owner=user.id, payload={**OFFER, "options": [
        {"n": 1, "card_id": str(db.cards[0]["id"]), "last4": "4242", "brand": "visa", "label": ""}]})
    assert await _answer(env, user, text) is False
    assert env["said"] == [] and db.purchases == []
    assert db.prompts[buy]["status"] == db.prompts[pick]["status"] == "open"


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Buy the best one", "buy it", "yes, purchase it", "go ahead and order it"])
async def test_an_explicit_buy_from_the_owner_answers_their_purchase_question(env, text):
    db, user = env["db"], _user()
    db.cards = [_card(user)]
    buy = db.add_prompt("purchase", owner=user.id, payload=OFFER, age=timedelta(hours=5))
    assert await _answer(env, user, text)  # no reply target needed, even hours later
    assert db.prompts[buy]["status"] == "answered"
    assert "Use your Visa ending 4242" in _said(env)[0]


@pytest.mark.asyncio
async def test_someone_elses_buy_never_answers_the_owners_question(env):
    db, owner, other = env["db"], _user(), _user()
    buy = db.add_prompt("purchase", owner=owner.id, payload=OFFER)
    assert await _answer(env, other, "buy it") is False
    assert db.prompts[buy]["status"] == "open" and env["said"] == []


@pytest.mark.asyncio
async def test_a_plain_yes_answers_a_just_asked_buy_question_only(env):
    db, user = env["db"], _user()
    db.cards = [_card(user)]
    stale = db.add_prompt("purchase", owner=user.id, payload=OFFER, age=timedelta(minutes=30))
    assert await _answer(env, user, "yes") is False  # 30 minutes later: needs a reply or "buy it"
    assert db.prompts[stale]["status"] == "open"
    fresh = db.add_prompt("purchase", owner=user.id, payload=OFFER, age=timedelta(minutes=2))
    assert await _answer(env, user, "yes")
    assert db.prompts[fresh]["status"] == "answered"


@pytest.mark.asyncio
async def test_a_plain_card_number_or_last_four_picks_the_owners_card(env):
    db, user = env["db"], _user()
    card = _card(user)
    db.cards = [card]
    options = [{"n": 1, "card_id": str(card["id"]), "last4": "4242", "brand": "visa", "label": ""}]
    db.add_prompt("pick_card", owner=user.id, payload={**OFFER, "options": options})
    assert await _answer(env, user, "4242")
    assert len(db.purchases) == 1
    db.add_prompt("pick_card", owner=user.id, payload={**OFFER, "options": options})
    assert await _answer(env, user, "1")
    assert len(db.purchases) == 2
    assert await _answer(env, _user(), "1") is False  # not their question


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["no", "later", "stop", "ok", "k"])
async def test_everyday_replies_neither_close_nor_answer_the_show_question(env, text):
    db, user = env["db"], _user()
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, text) is False
    assert env["said"] == [] and db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_a_plain_yes_goes_to_the_newest_show_question_not_a_purchase(env):
    db, owner, other = env["db"], _user(), _user()
    show = db.add_prompt("show_result")
    db.add_prompt("purchase", owner=owner.id, payload=OFFER)  # newer, but never plain-answerable
    assert await _answer(env, other, "yes")
    assert db.prompts[show]["status"] == "answered"


@pytest.mark.asyncio
async def test_non_admins_see_the_result_but_are_never_offered_a_purchase(env):
    db, user = env["db"], _user("client")
    db.add_prompt("show_result")
    assert await _answer(env, user, "yes")
    assert len(env["said"]) == 1
    assert not any(p["kind"] == "purchase" for p in db.prompts.values())


@pytest.mark.asyncio
async def test_threaded_no_skips_and_the_question_is_answered_once(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "no", prompt_id=pid)
    assert "on the card whenever you want it" in _said(env)[0]
    # A second reply to the same (now closed) question is told so.
    assert await _answer(env, user, "yes", prompt_id=pid)
    assert "closed" in _said(env)[1]


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
    db, user = env["db"], _user("employee")
    env["access"] = False
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "yes") is False  # plain: silently not ours
    assert await _answer(env, user, "yes", prompt_id=pid)
    assert "people on this project" in _said(env)[0]
    assert db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_only_the_buyer_can_answer_purchase_questions(env):
    db, owner, other = env["db"], _user(), _user()
    pid = db.add_prompt("purchase", owner=owner.id, payload=OFFER)
    assert await _answer(env, other, "yes", prompt_id=pid)
    assert "Only the person who asked" in _said(env)[0]
    assert db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_yes_to_buy_without_a_saved_card_keeps_the_question_open(env):
    db, user = env["db"], _user()
    db.cards = [_card(user, exp_year=2020)]  # expired cards don't count
    pid = db.add_prompt("purchase", owner=user.id, payload=OFFER)
    assert await _answer(env, user, "yes", prompt_id=pid)
    assert "Payment cards" in _said(env)[0] and "never paste" in _said(env)[0]
    assert db.prompts[pid]["status"] == "open"


async def _pick_question(env, user, cards):
    db = env["db"]
    db.cards = cards
    buy = db.add_prompt("purchase", owner=user.id, payload=OFFER)
    await _answer(env, user, "yes", prompt_id=buy)
    return _newest(db, "pick_card")["id"]


@pytest.mark.asyncio
async def test_several_cards_are_numbered_and_picked_by_number_or_unique_last_four(env):
    db, user = env["db"], _user()
    pick = await _pick_question(env, user, [_card(user, "4242"), _card(user, "5454", label="")])
    assert _said(env)[0].startswith(
        "Which card? Reply with its number: 1. Visa ending 4242 (Mercury test, expires 12/31); "
        "2. Visa ending 5454 (expires 12/31)."
    )
    await _answer(env, user, "yes", prompt_id=pick)  # ambiguous with 2 cards
    assert _said(env)[1] == chat_flow._HINTS["pick_card"]
    await _answer(env, user, "7", prompt_id=pick)
    assert "There's no card 7" in _said(env)[2]
    await _answer(env, user, "1111", prompt_id=pick)
    assert "don't see a saved card ending 1111" in _said(env)[3]
    await _answer(env, user, "card ending 5454", prompt_id=pick)
    assert db.purchases[0][7] == "5454"


@pytest.mark.asyncio
async def test_two_cards_with_the_same_last_four_are_chosen_by_number(env):
    db, user = env["db"], _user()
    old, renewed = _card(user, label="Old", exp_year=2027), _card(user, label="Renewed", exp_year=2031)
    pick = await _pick_question(env, user, [old, renewed])
    await _answer(env, user, "4242", prompt_id=pick)
    assert "More than one saved card ends in 4242. Reply with its number: 1, 2." in _said(env)[1]
    assert db.purchases == []
    await _answer(env, user, "2", prompt_id=pick)
    assert db.purchases[0][6] == renewed["id"]


@pytest.mark.asyncio
async def test_a_card_removed_before_the_pick_is_refused(env):
    db, user = env["db"], _user()
    card = _card(user)
    pid = db.add_prompt("pick_card", owner=user.id, payload={
        **OFFER, "options": [{"n": 1, "card_id": str(card["id"]), "last4": "4242", "brand": "visa", "label": ""}],
    })
    assert await _answer(env, user, "4242", prompt_id=pid)
    assert "removed or has expired" in _said(env)[0]
    assert db.purchases == [] and db.prompts[pid]["status"] == "open"


@pytest.mark.asyncio
async def test_no_to_buy_or_to_the_card_cancels(env):
    db, user = env["db"], _user()
    buy = db.add_prompt("purchase", owner=user.id, payload=OFFER)
    await _answer(env, user, "no", prompt_id=buy)
    pick = db.add_prompt("pick_card", owner=user.id, payload={"options": []})
    await _answer(env, user, "cancel", prompt_id=pick)
    assert _said(env) == ["Okay, I won't buy it.", "Okay, cancelled. Nothing was bought."]
    assert db.purchases == []


@pytest.mark.asyncio
async def test_last_four_or_a_number_only_answers_the_card_question(env):
    db, user = env["db"], _user()
    pid = db.add_prompt("show_result")
    assert await _answer(env, user, "4242", prompt_id=pid)
    assert await _answer(env, user, "2", prompt_id=pid)
    assert _said(env) == [chat_flow._HINTS["show_result"]] * 2


# ── stale results ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("kind, text", [("show_result", "yes"), ("purchase", "yes"), ("pick_card", "1")])
async def test_a_newer_run_on_the_card_closes_the_question_instead_of_answering_it(env, kind, text):
    db, user = env["db"], _user()
    card = _card(user)
    db.cards = [card]
    payload = {**OFFER, "options": [{"n": 1, "card_id": str(card["id"]), "last4": "4242", "brand": "visa", "label": ""}]}
    pid = db.add_prompt(kind, owner=None if kind == "show_result" else user.id, payload=payload)
    db.newer_run = True  # the card was sent back and a new run is queued
    assert await _answer(env, user, text, prompt_id=pid)
    assert _said(env) == [chat_flow.STALE_REPLY]
    assert db.prompts[pid]["status"] == "superseded"
    assert db.purchases == []
    assert [(u["prompt_id"], u["status"]) for u in env["updates"]] == [(str(pid), "superseded")]


# ── card numbers and photos ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_removed_card_number_warns_against_the_senders_own_purchase_question(env):
    db, user, other = env["db"], _user(), _user()
    db.add_prompt("pick_card", owner=other.id, payload={"options": []})
    assert await _answer(env, user, "[card number removed]", card_number_removed=True) is False
    mine = db.add_prompt("pick_card", owner=user.id, payload={"options": []})
    assert await _answer(env, user, "[card number removed]", card_number_removed=True)
    assert "removed a card number" in _said(env)[0]
    assert db.prompts[mine]["status"] == "open"


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


class _RedactConn:
    def __init__(self, owns=False, fail=False):
        self.owns, self.fail, self.calls = owns, fail, 0

    async def fetchval(self, query, *args):
        self.calls += 1
        if self.fail:
            raise RuntimeError("relation does not exist")
        assert "owner_user_id = $2" in query and "'purchase', 'pick_card'" in query
        return self.owns


@pytest.mark.asyncio
async def test_redaction_applies_only_to_replies_and_to_the_purchase_owner():
    pan, cid, uid = "pay with 4242 4242 4242 4242", uuid4(), uuid4()
    removed = ("pay with [card number removed]", True)
    quiet = _RedactConn(owns=False)
    assert await chat_flow.redact_card_numbers(quiet, channel_id=cid, user_id=uid, replied_prompt_id=None,
                                               content="meeting 2026-10-01 room 4412") == ("meeting 2026-10-01 room 4412", False)
    assert quiet.calls == 0  # no card-shaped number: no query at all
    assert await chat_flow.redact_card_numbers(quiet, channel_id=cid, user_id=uid, replied_prompt_id=None,
                                               content=pan) == (pan, False)
    owner = _RedactConn(owns=True)
    assert await chat_flow.redact_card_numbers(owner, channel_id=cid, user_id=uid, replied_prompt_id=None,
                                               content=pan) == removed
    threaded = _RedactConn()
    assert await chat_flow.redact_card_numbers(threaded, channel_id=cid, user_id=uid, replied_prompt_id=uuid4(),
                                               content=pan) == removed
    assert threaded.calls == 0
    broken = _RedactConn(fail=True)  # fails closed
    assert await chat_flow.redact_card_numbers(broken, channel_id=cid, user_id=uid, replied_prompt_id=None,
                                               content=pan) == removed
    assert await chat_flow.redact_card_numbers(quiet, channel_id=cid, user_id=uid, replied_prompt_id=None,
                                               content=None) == (None, False)


# ── project access: the REST rule ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_answers_use_the_rest_apis_project_access_rule(monkeypatch):
    from app.matcha import dependencies
    from app.matcha.services.matcha_work import project_service

    seen = {}

    async def resolve(project_id, user, *, company_id):
        seen.update(project_id=project_id, user=user, company_id=company_id)
        return None if user.role == "employee" else ({}, "owner")

    company = uuid4()
    monkeypatch.setattr(project_service, "resolve_project_access", resolve)
    monkeypatch.setattr(dependencies, "get_client_company_id", AsyncMock(return_value=company))
    prompt = {"project_id": uuid4()}

    assert await chat_flow._can_access_project(prompt, SimpleNamespace(id=uuid4(), role="client", email="a@example.com"))
    assert isinstance(seen["user"], CurrentUser) and seen["company_id"] == company
    assert not await chat_flow._can_access_project(prompt, SimpleNamespace(id=uuid4(), role="employee", email=""))
    assert await chat_flow._can_access_project(prompt, SimpleNamespace(id=uuid4(), role="admin", email="b@example.com"))
    assert seen["company_id"] is None  # admins reach projects only as collaborators


# ── the worker's offer ────────────────────────────────────────────────────────

class _OfferConn:
    def __init__(self, row, inserted=True, newer_run=False, older_open=()):
        self.row, self.inserted, self.newer_run = row, inserted, newer_run
        self.older_open = list(older_open)
        self.executed = []
        self.fetched = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *args):
        if "INSERT INTO mw_agent_card_prompts" in query:
            assert "ON CONFLICT (run_id) WHERE kind = 'show_result' DO NOTHING" in query
            assert args[5] == chat_flow.OFFER_TTL
            return {"id": uuid4(), "expires_at": datetime(2031, 1, 1, tzinfo=timezone.utc)} if self.inserted else None
        assert "FROM mw_project_agent_runs r" in query
        return self.row

    async def fetchval(self, query, *args):
        assert query == chat_flow._NEWER_RUN_SQL
        return self.newer_run

    async def fetch(self, query, *args):
        self.fetched.append((query, args))
        assert "SET status = 'superseded'" in query and "RETURNING id, channel_id, kind" in query
        return self.older_open

    async def execute(self, query, *args):
        self.executed.append((query, args))


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
    holder["updates"] = AsyncMock()
    monkeypatch.setattr(chat_flow, "broadcast_espresso_message", holder["broadcast"])
    monkeypatch.setattr(chat_flow, "_publish_prompt_update", holder["updates"])
    return holder


@pytest.mark.asyncio
async def test_offer_asks_once_under_the_card_lock_and_supersedes_older_questions(offer_env):
    row = _offer_row()
    older = {"id": uuid4(), "channel_id": row["channel_id"], "kind": "purchase"}
    offer_env["conn"] = conn = _OfferConn(row, older_open=[older])
    assert await chat_flow.offer_result(uuid4())
    content, metadata = offer_env["said"][0]
    assert "I finished \"Find a balm\". Want to see what I found? Reply yes or no." in content
    assert metadata["kind"] == "agent_card_prompt" and metadata["prompt_kind"] == "show_result"
    # The heading is fixed server text, never cut out of the (user-titled) content.
    assert metadata["view"]["question"] == "I finished it. Want to see what I found?"
    assert metadata["expires_at"] == "2031-01-01T00:00:00+00:00" and "owner_user_id" not in metadata
    assert [b["reply"] for b in metadata["view"]["buttons"]] == ["Show me", "Not now"]
    assert [parse_answer(b["reply"]).kind for b in metadata["view"]["buttons"]] == ["yes", "no"]
    queries = [q for q, _ in conn.executed]
    assert conn.executed[0][1] == (f"{row['task_id']}:card_agent",)  # same lock as enqueue
    assert len(conn.fetched) == 1 and conn.fetched[0][1][0] == row["task_id"]
    assert any("SET message_id" in q for q in queries)
    offer_env["broadcast"].assert_awaited_once()
    # Open chats hear that the older question closed.
    offer_env["updates"].assert_awaited_once_with({
        "type": "agent_card_prompt_updated", "channel_id": row["channel_id"], "prompt_id": str(older["id"]),
        "status": "superseded", "answer": None, "answer_text": None,
    })


@pytest.mark.asyncio
async def test_no_offer_once_the_card_has_been_sent_back(offer_env):
    offer_env["conn"] = _OfferConn(_offer_row(), newer_run=True)
    assert await chat_flow.offer_result(uuid4()) is False
    assert offer_env["said"] == []


@pytest.mark.asyncio
async def test_offer_for_a_revision_says_reworked(offer_env):
    offer_env["conn"] = _OfferConn(_offer_row(round=2))
    await chat_flow.offer_result(uuid4())
    assert "I reworked" in offer_env["said"][0][0]
    assert offer_env["said"][0][1]["view"]["question"] == "I reworked it. Want to see the new result?"


@pytest.mark.asyncio
async def test_offer_is_idempotent_per_run(offer_env):
    offer_env["conn"] = conn = _OfferConn(_offer_row(), inserted=False)
    assert await chat_flow.offer_result(uuid4())
    assert offer_env["said"] == []
    assert conn.fetched == []


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [None, _offer_row(status="failed"), _offer_row(channel_id=None), _offer_row(channel_id="junk")])
async def test_no_offer_without_a_finished_run_and_a_project_chat(offer_env, row):
    offer_env["conn"] = _OfferConn(row)
    assert await chat_flow.offer_result(uuid4()) is False
    assert offer_env["said"] == []


def test_newer_run_rule_ignores_failed_runs():
    # A failed (or never dispatched) newer run must not make the current
    # result's questions stale.
    assert "n.status IN ('queued', 'running', 'done')" in chat_flow._NEWER_RUN_SQL


@pytest.mark.asyncio
async def test_close_open_prompts_returns_the_events_to_broadcast():
    channel, pid = uuid4(), uuid4()

    class C:
        q = []

        async def fetch(self, query, *args):
            self.q.append(query)
            return [{"id": pid, "channel_id": channel, "kind": "show_result"}]

    conn = C()
    events = await chat_flow.close_open_prompts(conn, uuid4())
    assert "superseded" in conn.q[0]
    assert events == [{"type": "agent_card_prompt_updated", "channel_id": str(channel), "prompt_id": str(pid),
                       "status": "superseded", "answer": None, "answer_text": None}]


@pytest.mark.asyncio
async def test_prompt_update_broadcast_is_best_effort(monkeypatch):
    calls = []

    async def boom(update):
        calls.append(update)
        raise RuntimeError("redis down")

    monkeypatch.setattr(chat_flow, "_publish_prompt_update", boom)
    await chat_flow.broadcast_prompt_updates([{"channel_id": str(uuid4())}, {"channel_id": str(uuid4())}])
    assert len(calls) == 2  # one failure doesn't stop the rest


@pytest.mark.asyncio
async def test_prompt_updates_ride_the_channel_bridge(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications

    sent = []

    async def bridge(channel_id, event):
        sent.append((channel_id, event))

    monkeypatch.setattr(project_task_notifications, "broadcast_channel_event", bridge)
    channel = uuid4()
    update = {"type": "agent_card_prompt_updated", "channel_id": str(channel), "prompt_id": "p"}
    await chat_flow._publish_prompt_update(update)
    assert sent == [(channel, update)]


@pytest.mark.parametrize("kind, answer, text", [
    ("show_result", "yes", "Showed the result"), ("show_result", "no", "Skipped for now"),
    ("purchase", "yes", "Going ahead with the purchase"), ("purchase", "no", "Not buying it"),
    ("pick_card", "card:4242", "Used the card ending 4242"), ("pick_card", "no", "Cancelled"),
    ("pick_card", "odd", "Answered"), ("show_result", None, None),
])
def test_answer_text(kind, answer, text):
    assert chat_flow.answer_text(kind, answer) == text


def test_ttls_are_sane():
    assert chat_flow.PICK_CARD_TTL < chat_flow.PURCHASE_TTL < chat_flow.OFFER_TTL <= timedelta(days=7)


# ── Stripe test-mode charge ───────────────────────────────────────────────────

async def _approve(env, user, payload=OFFER):
    db = env["db"]
    card = _card(user)
    db.cards = [card]
    pid = db.add_prompt("pick_card", owner=user.id, payload={
        **payload, "options": [{"n": 1, "card_id": str(card["id"]), "last4": "4242", "brand": "visa", "label": ""}],
    })
    assert await _answer(env, user, "1", prompt_id=pid)
    return card


@pytest.mark.asyncio
async def test_approved_purchase_is_charged_in_stripe_test_mode(env, monkeypatch):
    seen = {}

    async def charge(key, **kwargs):
        seen.update(kwargs, key=key)
        return {"status": "test_charged", "payment_intent_id": "pi_test_123", "error": None}

    monkeypatch.setattr(chat_flow.test_charge, "test_key", lambda: "sk_test_x")
    monkeypatch.setattr(chat_flow.test_charge, "charge", charge)
    user = _user()
    await _approve(env, user)
    assert seen["key"] == "sk_test_x" and seen["amount"] == 4.49 and seen["currency"] == "USD"
    assert seen["brand"] == "visa"
    update = env["db"].charge_updates[0]
    assert update[1:] == ("test_charged", "pi_test_123", None)
    receipt = _said(env)[-1]
    assert receipt.startswith("All done. Here's your receipt.")
    for line in ("Receipt (Stripe TEST mode, no real money moved)", "Item: Organic Lip Balm (Dr. Bronner's)",
                 "Store: Shop", "Total: $4.49 USD", "Paid with: Visa ending 4242 (Mercury test)",
                 "Payment: pi_test_123 (succeeded)"):
        assert line in receipt
    assert "4242 4242" not in receipt and "http" not in receipt
    card = env["said"][-1]["metadata"]
    assert card["kind"] == "agent_card_receipt"
    r = card["receipt"]
    assert r["status"] == "paid_test" and r["total_text"] == "$4.49" and r["currency"] == "USD"
    assert r["payment_intent_id"] == "pi_test_123" and r["card_text"] == "Visa ending 4242 (Mercury test)"
    assert r["product_url"] == "https://shop.example.com/p" and len(r["order_ref"]) == 8


@pytest.mark.asyncio
async def test_a_failed_test_charge_is_recorded_and_reported(env, monkeypatch):
    monkeypatch.setattr(chat_flow.test_charge, "test_key", lambda: "sk_test_x")
    monkeypatch.setattr(chat_flow.test_charge, "charge", AsyncMock(
        return_value={"status": "test_failed", "payment_intent_id": None, "error": "Your card was declined."}))
    await _approve(env, _user())
    assert env["db"].charge_updates[0][1] == "test_failed"
    assert "The Stripe test charge failed: Your card was declined." in _said(env)[-1]
    receipt = env["said"][-1]["metadata"]["receipt"]
    assert receipt["status"] == "failed" and receipt["error"] == "Your card was declined."


@pytest.mark.asyncio
async def test_no_verified_price_means_no_test_charge(env, monkeypatch):
    charge = AsyncMock()
    monkeypatch.setattr(chat_flow.test_charge, "test_key", lambda: "sk_test_x")
    monkeypatch.setattr(chat_flow.test_charge, "charge", charge)
    await _approve(env, _user(), payload={**OFFER, "amount": None, "currency": None})
    charge.assert_not_awaited()
    assert "No verified price, so I didn't make a test charge." in _said(env)[-1]
    assert "Finish checkout here: https://shop.example.com/p" in _said(env)[-1]
    assert env["said"][-1]["metadata"]["receipt"]["status"] == "no_price"
    assert len(env["db"].purchases) == 1


@pytest.mark.asyncio
async def test_handoff_mode_charges_nothing(env, monkeypatch):
    charge = AsyncMock()
    monkeypatch.setattr(chat_flow.test_charge, "charge", charge)
    await _approve(env, _user())
    charge.assert_not_awaited()
    # Plain text is what notifications and older apps show: the link is in it.
    assert "I haven't charged anything. Finish checkout here: https://shop.example.com/p" in _said(env)[-1]
    assert env["said"][-1]["metadata"]["receipt"]["status"] == "approved"


# ── history overlay ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_overlay_stamps_question_state():
    answered, expired, other = uuid4(), uuid4(), uuid4()

    class C:
        async def fetch(self, query, *args):
            assert "mw_agent_card_prompts" in query and set(args[0]) == {answered, expired}
            return [{"id": answered, "kind": "show_result", "status": "answered", "answer": "yes", "expired": False},
                    {"id": expired, "kind": "purchase", "status": "open", "answer": None, "expired": True}]

    def msg(pid):
        return {"id": uuid4(), "metadata": json.dumps({"kind": "agent_card_prompt", "prompt_id": str(pid)})}

    plain = {"id": uuid4(), "metadata": "{}"}
    out = await chat_flow.overlay_prompt_statuses(C(), [msg(answered), msg(expired), plain], channel_id=uuid4())
    assert out[0]["metadata"]["prompt_status"] == "answered" and out[0]["metadata"]["answer"] == "yes"
    assert out[0]["metadata"]["answer_text"] == "Showed the result"
    assert out[1]["metadata"]["prompt_status"] == "expired"
    assert out[2] is plain

    class Never:
        async def fetch(self, *a):
            raise AssertionError("no question messages: no query")

    assert await chat_flow.overlay_prompt_statuses(Never(), [plain], channel_id=uuid4()) == [plain]
    del other


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "find me a rain jacket to buy that is waterproof", "I want to buy a desk, is it worth it",
])
async def test_a_new_shopping_sentence_never_completes_an_open_card_question(env, text):
    # One saved card + an open "use this card?" question: a plain "yes" would
    # buy. An ordinary sentence with a buy word and a stray "that"/"it" must not.
    db, user = env["db"], _user()
    card = _card(user)
    db.cards = [card]
    pid = db.add_prompt("pick_card", owner=user.id, payload={
        **OFFER, "options": [{"n": 1, "card_id": str(card["id"]), "last4": "4242", "brand": "visa", "label": ""}],
    })
    assert chat_flow.might_answer_plain(text) is False
    assert await _answer(env, user, text) is False
    assert db.purchases == [] and db.prompts[pid]["status"] == "open" and env["said"] == []
