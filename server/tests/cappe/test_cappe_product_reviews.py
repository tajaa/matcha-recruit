"""Per-product reviews — the 2026-10 commerce readiness review, PR 9.

Reviews were site-wide and anonymous, and "submissions off" only hid the form.
What each block pins:

  * who may post is enforced by the server (anyone / buyers / off);
  * a review from a paid order's page is a verified purchase, once per
    product per order, and only for something in that order;
  * bots that fill the hidden field are told yes and stored nowhere; a
    per-store cap keeps a flood out of the moderation queue;
  * a product's own reviews, its rating on the listing, and the owner's
    public reply;
  * the order page offers a form per product once paid.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_product_reviews.py -q
"""
import asyncio
import os
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.cappe.models.cappe import CappeReviewCreate, CappeReviewReply, CappeReviewSettings  # noqa: E402
from app.cappe.routes import reviews as owner_reviews  # noqa: E402
from app.cappe.routes.public import reviews as public_reviews  # noqa: E402
from app.cappe.services.render import order_page  # noqa: E402

SITE, PRODUCT, ORDER = uuid4(), uuid4(), uuid4()
TOKEN = "ab" * 16
ASSETS = pathlib.Path(order_page.__file__).parent / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe47_product_reviews.py"


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Conn:
    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, sql, args):
        self.calls.append((sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer(sql, args)

    async def fetchval(self, sql, *args):
        return self._answer(sql, args)

    async def fetch(self, sql, *args):
        return self._answer(sql, args) or []

    async def execute(self, sql, *args):
        self._answer(sql, args)

    def sql(self, needle):
        return [c for c in self.calls if needle in c[0]]


def _request():
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})


def _wire(monkeypatch, *answers, who="anyone"):
    conn = Conn([("review_submissions", who), *answers])
    monkeypatch.setattr(public_reviews, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_reviews, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(public_reviews, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_reviews, "_published_site", AsyncMock(return_value={"id": SITE}))
    return conn


def _post(**kw):
    body = CappeReviewCreate(author_name="Ana", rating=5, body="Lovely mug", **kw)
    return asyncio.run(public_reviews.public_submit_review("shop", body, _request()))


# ── who may post ─────────────────────────────────────────────────────────────

def test_anyone_may_post_about_the_store_and_it_waits_for_approval(monkeypatch):
    conn = _wire(monkeypatch, ("COUNT(*)", 0), ("INSERT INTO cappe_reviews", uuid4()))
    assert _post() == {"ok": True}
    ((sql, args),) = conn.sql("INSERT INTO cappe_reviews")
    assert "'pending'" in sql and args[4:] == (None, None, False)     # no product, no order, not verified


def test_a_visitor_review_of_a_product_must_name_one_this_store_sells(monkeypatch):
    conn = _wire(monkeypatch, ("FROM cappe_products", None))
    with pytest.raises(HTTPException) as exc:
        _post(product_id=PRODUCT)
    assert exc.value.status_code == 422 and not conn.sql("INSERT")


def test_submissions_off_are_refused_by_the_server(monkeypatch):
    conn = _wire(monkeypatch, who="off")
    with pytest.raises(HTTPException) as exc:
        _post()
    assert exc.value.status_code == 403 and not conn.sql("INSERT")


def test_buyers_only_refuses_a_review_without_an_order(monkeypatch):
    conn = _wire(monkeypatch, who="buyers")
    with pytest.raises(HTTPException) as exc:
        _post(product_id=PRODUCT)
    assert exc.value.status_code == 403 and "order pages" in exc.value.detail and not conn.sql("INSERT")


def test_a_bot_that_fills_the_hidden_field_is_told_yes_and_kept_nowhere(monkeypatch):
    conn = _wire(monkeypatch)
    assert _post(website="http://spam.example.com") == {"ok": True}
    assert conn.calls == []


def test_a_flooded_queue_takes_no_more(monkeypatch):
    conn = _wire(monkeypatch, ("COUNT(*)", public_reviews.MAX_PENDING))
    with pytest.raises(HTTPException) as exc:
        _post()
    assert exc.value.status_code == 429 and not conn.sql("INSERT")


# ── verified purchases ───────────────────────────────────────────────────────

def test_a_review_from_a_paid_order_is_a_verified_purchase(monkeypatch):
    conn = _wire(monkeypatch, ("FROM cappe_orders", {"id": ORDER, "status": "paid"}),
                 ("FROM cappe_order_items", 1), ("COUNT(*)", 0), ("INSERT INTO cappe_reviews", uuid4()),
                 who="buyers")
    _post(product_id=PRODUCT, order_token=TOKEN)
    assert conn.sql("FROM cappe_orders")[0][1] == (TOKEN, SITE)       # this store's order only
    ((sql, args),) = conn.sql("INSERT INTO cappe_reviews")
    assert args[4:] == (PRODUCT, ORDER, True)
    assert "ON CONFLICT (order_id, product_id)" in sql


@pytest.mark.parametrize("order,in_order,code", [
    (None, 1, 403),                                     # not this store's order
    ({"id": ORDER, "status": "pending"}, 1, 403),       # not paid yet
    ({"id": ORDER, "status": "fulfilled"}, None, 422),  # not something in the order
])
def test_an_order_review_must_come_from_a_paid_order_for_what_it_bought(monkeypatch, order, in_order, code):
    conn = _wire(monkeypatch, ("FROM cappe_orders", order), ("FROM cappe_order_items", in_order))
    with pytest.raises(HTTPException) as exc:
        _post(product_id=PRODUCT, order_token=TOKEN)
    assert exc.value.status_code == code and not conn.sql("INSERT")


def test_one_review_per_product_per_order(monkeypatch):
    _wire(monkeypatch, ("FROM cappe_orders", {"id": ORDER, "status": "paid"}),
          ("FROM cappe_order_items", 1), ("COUNT(*)", 0), ("INSERT INTO cappe_reviews", None))
    with pytest.raises(HTTPException) as exc:
        _post(product_id=PRODUCT, order_token=TOKEN)
    assert exc.value.status_code == 409


def test_a_review_names_a_real_author_and_rating():
    with pytest.raises(ValidationError):
        CappeReviewCreate(author_name="", rating=5, body="x")
    with pytest.raises(ValidationError):
        CappeReviewCreate(author_name="A", rating=6, body="x")


# ── reading reviews ──────────────────────────────────────────────────────────

def test_a_products_reviews_put_verified_purchases_first(monkeypatch):
    conn = _wire(monkeypatch, ("FROM cappe_reviews", [{"author_name": "Ana", "rating": 5, "body": "x",
                                                       "created_at": None, "verified": True}]))
    out = asyncio.run(public_reviews.public_reviews("shop", _request(), product_id=PRODUCT))
    assert out[0]["verified"] is True
    sql, args = conn.sql("FROM cappe_reviews")[0]
    assert "product_id = $2" in sql and "ORDER BY verified DESC" in sql and args == (SITE, PRODUCT)
    asyncio.run(public_reviews.public_reviews("shop", _request(), product_id=None))
    assert "product_id" not in conn.sql("FROM cappe_reviews")[1][0].split("WHERE")[1]


def test_the_widget_can_ask_who_may_post(monkeypatch):
    _wire(monkeypatch, who="buyers")
    assert asyncio.run(public_reviews.public_review_settings("shop", _request())) == {"submissions": "buyers"}


# ── the owner ────────────────────────────────────────────────────────────────

def _owner(monkeypatch, conn):
    monkeypatch.setattr(owner_reviews, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(owner_reviews, "get_owned_site", AsyncMock(return_value={"id": SITE, "review_submissions": "buyers"}))
    return SimpleNamespace(id=uuid4())


ROW = {"id": uuid4(), "site_id": SITE, "author_name": "Ana", "rating": 5, "body": "x", "status": "approved",
       "created_at": None, "product_id": PRODUCT, "product_name": "Mug", "verified": True,
       "owner_reply": "Thank you!", "owner_replied_at": None}


def test_the_owner_replies_publicly_and_can_take_it_back(monkeypatch):
    conn = Conn([("UPDATE cappe_reviews SET owner_reply", ROW["id"]), ("FROM cappe_reviews r", ROW)])
    account = _owner(monkeypatch, conn)
    out = asyncio.run(owner_reviews.reply_to_review(SITE, ROW["id"], CappeReviewReply(reply="  Thank you! "), account))
    assert out["owner_reply"] == "Thank you!" and out["product_name"] == "Mug"
    sql, args = conn.sql("SET owner_reply")[0]
    assert args[0] == "Thank you!" and "CASE WHEN $1::text IS NULL THEN NULL ELSE NOW() END" in sql
    asyncio.run(owner_reviews.reply_to_review(SITE, ROW["id"], CappeReviewReply(reply="   "), account))
    assert conn.sql("SET owner_reply")[1][1][0] is None


def test_replying_to_a_strangers_review_is_404(monkeypatch):
    account = _owner(monkeypatch, Conn([]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_reviews.reply_to_review(SITE, uuid4(), CappeReviewReply(reply="hi"), account))
    assert exc.value.status_code == 404


def test_the_owner_sees_which_product_and_whether_verified(monkeypatch):
    conn = Conn([("FROM cappe_reviews r", [ROW])])
    account = _owner(monkeypatch, conn)
    (out,) = asyncio.run(owner_reviews.list_reviews(SITE, account))
    assert out["product_name"] == "Mug" and out["verified"] is True
    assert "LEFT JOIN cappe_products p" in conn.sql("FROM cappe_reviews r")[0][0]


def test_the_owner_sets_who_may_post(monkeypatch):
    conn = Conn([])
    account = _owner(monkeypatch, conn)
    assert asyncio.run(owner_reviews.get_review_settings(SITE, account)) == {"submissions": "buyers"}
    asyncio.run(owner_reviews.set_review_settings(SITE, CappeReviewSettings(submissions="off"), account))
    assert conn.sql("SET review_submissions")[0][1] == ("off", SITE)
    with pytest.raises(ValidationError):
        CappeReviewSettings(submissions="everyone")


def test_moderating_returns_the_full_review(monkeypatch):
    from app.cappe.models.cappe import CappeReviewModerate
    conn = Conn([("UPDATE cappe_reviews SET status", ROW["id"]), ("FROM cappe_reviews r", ROW)])
    account = _owner(monkeypatch, conn)
    out = asyncio.run(owner_reviews.moderate_review(SITE, ROW["id"], CappeReviewModerate(status="approved"), account))
    assert out["product_name"] == "Mug"


# ── the order page ───────────────────────────────────────────────────────────

ITEMS = [
    {"title": "Mug", "product_id": PRODUCT, "reviewable": True, "reviewed": False},
    {"title": "Mug", "product_id": PRODUCT, "reviewable": True, "reviewed": False},      # same product twice
    {"title": "Old print", "product_id": uuid4(), "reviewable": False, "reviewed": False},  # no longer sold
    {"title": "Zine", "product_id": uuid4(), "reviewable": True, "reviewed": True},     # already reviewed
    {"title": "Custom", "product_id": None, "reviewable": False, "reviewed": False},
]


def test_a_paid_order_offers_one_form_per_product_still_to_review():
    html = order_page._reviews_html(ITEMS)
    assert html.count("data-czreview") == 1 and f'data-product="{PRODUCT}"' in html
    assert "verified purchase" in html
    assert order_page._reviews_html(ITEMS[2:]) == ""


def test_the_order_page_shows_review_forms_only_once_paid_and_when_open():
    order = {"id": ORDER, "status": "paid", "subtotal_cents": 1000, "currency": "USD"}
    site = {"id": SITE, "name": "Store", "theme_config": {}, "meta_config": {}}
    kw = dict(token=TOKEN, takes_cards=True, now=None, clear_cart=False)
    from datetime import datetime, timezone
    kw["now"] = datetime(2026, 10, 6, tzinfo=timezone.utc)
    assert "<form class=\"cz-order__review\"" in order_page.render_order_page(site, [], order, ITEMS[:1], reviews_open=True, **kw)
    assert "<form class=\"cz-order__review\"" not in order_page.render_order_page(site, [], order, ITEMS[:1], reviews_open=False, **kw)
    pending = {**order, "status": "pending"}
    assert "<form class=\"cz-order__review\"" not in order_page.render_order_page(site, [], pending, ITEMS[:1], reviews_open=True, **kw)


# ── the scripts ──────────────────────────────────────────────────────────────

def test_the_scripts_send_the_order_token_honour_the_setting_and_trap_bots():
    order_js = (ASSETS / "order.js").read_text()
    assert "order_token:token" in order_js and "data-czreview" in order_js
    widget = (ASSETS / "reviews.js").read_text()
    assert "RT.get('/review-settings')" in widget and "who==='off'" in widget and "data-website" in widget
    store = (ASSETS / "store.js").read_text()
    assert "RT.get('/reviews?product_id='" in store and "Verified purchase" in store
    # Product structured data, with `<` escaped so a product name can't close the script.
    assert "'@type':'Product'" in store and "aggregateRating" in store and "replace(/</g,'\\\\u003c')" in store


def test_the_migration_chains():
    src = MIGRATION.read_text()
    assert 'down_revision = "zzzzcappe46"' in src and 'revision = "zzzzcappe47"' in src
    assert "uq_cappe_reviews_order_product ON cappe_reviews (order_id, product_id)" in src
    assert "CHECK (review_submissions IN ('anyone', 'buyers', 'off'))" in src


def test_the_product_list_carries_each_products_rating(monkeypatch):
    from app.cappe.routes.public import shop as public_shop
    a, b = uuid4(), uuid4()
    rows = [{"id": a, "subscription_intervals": [], "price_cents": 1000, "intake_fields": "[]"},
            {"id": b, "subscription_intervals": [], "price_cents": 500, "intake_fields": "[]"}]

    async def _fetch(sql, *args):
        if "FROM cappe_reviews" in sql:
            assert "status = 'approved'" in sql and "GROUP BY product_id" in sql
            return [{"product_id": a, "n": 3, "avg": 4.7}]
        return rows

    conn = Conn([("SELECT NOW()", None)])
    conn.fetch = _fetch
    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "site_today", lambda *_a: None)
    rated, unrated = asyncio.run(public_shop.public_products("shop", _request()))
    assert (rated["rating_count"], rated["rating_avg"]) == (3, 4.7)
    assert (unrated["rating_count"], unrated["rating_avg"]) == (0, None)
