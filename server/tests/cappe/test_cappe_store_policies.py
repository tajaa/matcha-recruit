"""Store policies, the seller on the receipt, checkout's terms line, the
commerce checklist and Merlin's stock — physical sellers PR 5/7 (`zzzzcappe54`).

What each block pins:

  * policies: the four kinds, our starting text, the owner's text rendered
    escaped, the owner API (an empty body takes the page down);
  * the store: `/policies/<kind>`, footer links, the bag's list, the sitemap;
  * checkout: the payment page says what paying agrees to and can ask for a
    phone; Stripe's billing details land on the order;
  * the receipt names the seller (legal name, address, tax number) and the
    buyer's billing address;
  * the checklist: a store selling physical goods can't publish without its
    refund and shipping policies; the rest are nudges;
  * Merlin sets stock, SKU and weight, and a physical product nobody gave a
    stock count is a draft;
  * clients carry the store's currency; the migration and dev scrub.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_store_policies.py -q
"""
import asyncio
import inspect
import os
import pathlib
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.cappe.models.shop import CappeCartItem, CappeCheckoutRequest, CappePolicyUpdate  # noqa: E402
from app.cappe.models.sites import CappeSiteUpdate  # noqa: E402
from app.cappe.routes import clients as clients_routes  # noqa: E402
from app.cappe.routes import policies as policy_routes  # noqa: E402
from app.cappe.routes import render as render_mod  # noqa: E402
from app.cappe.routes import sites as site_routes  # noqa: E402
from app.cappe.routes.payments import extract_billing_details  # noqa: E402
from app.cappe.services import commerce, policies, stripe_connect  # noqa: E402
from app.cappe.services.entitlements import ALL_FULFILLMENT  # noqa: E402
from app.cappe.services.merlin import setup_actions as sa  # noqa: E402
from app.cappe.services.readiness import compute_readiness  # noqa: E402
from app.cappe.services.receipt import build_receipt_html  # noqa: E402
from app.cappe.services.render.page import render_site_html  # noqa: E402
from app.cappe.services.render.policy_page import render_policy_page  # noqa: E402

SITE, ORDER = uuid4(), uuid4()
NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
ROOT = pathlib.Path(__file__).resolve().parents[3]
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"
MIGRATION = ROOT / "server" / "alembic" / "versions" / "zzzzcappe54_store_policies.py"


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class SqlConn:
    """Answers by the first matching SQL fragment; records every call."""

    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, sql, args):
        self.calls.append((sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value(sql, args) if callable(value) else value
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


# ── the policies ─────────────────────────────────────────────────────────────

def test_four_kinds_each_with_a_starting_text():
    assert policies.KINDS == ("refund", "shipping", "terms", "privacy")
    for kind in policies.KINDS:
        assert len(policies.starter(kind)) > 100 and policies.policy_path(kind) == f"/policies/{kind}"
    assert [p["kind"] for p in policies.links(["privacy", "refund"])] == ["refund", "privacy"]
    assert policies.links(None) == []


def test_the_owners_text_is_escaped_into_paragraphs_with_headings():
    html = policies.body_html("Returns\nWithin 30 days.\n\nPlain <script>alert(1)</script> line.\nSecond line.")
    assert html == ("<h2>Returns</h2><p>Within 30 days.</p>"
                    "<p>Plain &lt;script&gt;alert(1)&lt;/script&gt; line.<br>Second line.</p>")
    assert policies.body_html("") == ""


def test_the_payment_page_line_names_terms_and_refunds_with_their_addresses():
    note = policies.checkout_note("Lumen", "https://lumen.example.com/", ["refund", "terms", "privacy"])
    assert note == ("By paying you agree to Lumen's terms (https://lumen.example.com/policies/terms) "
                    "and refund policy (https://lumen.example.com/policies/refund).")
    assert policies.checkout_note("Lumen", "https://x.test", ["privacy"]) is None
    assert policies.checkout_note("Lumen", None, ["terms"]) is None
    assert len(policies.checkout_note("x" * 2000, "https://x.test", ["terms"])) == 1200


def test_the_owner_api_publishes_and_takes_down(monkeypatch):
    conn = SqlConn([("SELECT kind, body, updated_at", [{"kind": "refund", "body": "Returns", "updated_at": NOW}])])
    monkeypatch.setattr(policy_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(policy_routes, "get_owned_site", AsyncMock(return_value={"id": SITE}))
    invalidate = AsyncMock()
    monkeypatch.setattr(policy_routes, "invalidate_site_render_cache", invalidate)
    account = SimpleNamespace(id=uuid4())
    view = asyncio.run(policy_routes.get_policies(SITE, account))
    assert [(p["kind"], p["body"]) for p in view["policies"]] == [
        ("refund", "Returns"), ("shipping", None), ("terms", None), ("privacy", None)]
    assert view["policies"][1]["starter"] == policies.starter("shipping")
    asyncio.run(policy_routes.put_policy(SITE, "shipping", CappePolicyUpdate(body="  We ship weekly.\r\n "), account))
    (_sql, args), = conn.sql("INSERT INTO cappe_site_policies")
    assert args == (SITE, "shipping", "We ship weekly.")
    asyncio.run(policy_routes.put_policy(SITE, "refund", CappePolicyUpdate(body="   "), account))
    assert conn.sql("DELETE FROM cappe_site_policies") and invalidate.await_count == 2
    with pytest.raises(HTTPException) as exc:
        asyncio.run(policy_routes.put_policy(SITE, "cookies", CappePolicyUpdate(body="x"), account))
    assert exc.value.status_code == 404
    with pytest.raises(ValidationError):
        CappePolicyUpdate(body="x" * 20001)


# ── on the store ─────────────────────────────────────────────────────────────

SITE_ROW = {"id": SITE, "name": "Bloom", "slug": "bloom", "subdomain": "bloom", "custom_domain": None,
            "theme_config": "{}", "meta_config": "{}", "timezone": "UTC", "account_id": uuid4()}


def _request(path, host="bloom.gummfit.com"):
    return Request({"type": "http", "method": "GET", "path": path, "client": ("127.0.0.1", 1),
                    "headers": [(b"host", host.encode())]})


def _wire(monkeypatch, *, policy=None, kinds=("refund", "terms")):
    conn = SqlConn([
        ("FROM cappe_sites WHERE subdomain", SITE_ROW),
        ("SELECT title, slug, content FROM cappe_pages", {"title": "Home", "slug": "home", "content": '{"blocks": []}'}),
        ("FROM cappe_pages", [{"slug": "home", "title": "Home", "updated_at": NOW}]),
        # The policy page reads every row once: its own body and the footer's list.
        ("SELECT kind, body, updated_at FROM cappe_site_policies",
         [{"kind": "refund", **policy}] + [{"kind": k, "body": "x", "updated_at": NOW} for k in kinds if k != "refund"]
         if policy else []),
        ("SELECT kind, updated_at FROM cappe_site_policies", [{"kind": k, "updated_at": NOW} for k in kinds]),
        ("SELECT kind FROM cappe_site_policies", [{"kind": k} for k in kinds]),
    ])
    monkeypatch.setattr(render_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(render_mod, "get_redis_cache", lambda: None)
    monkeypatch.setattr(render_mod, "subdomain_from_host", lambda host: "bloom" if host and "gummfit" in host else None)
    monkeypatch.setattr(render_mod, "_custom_domain_candidates", lambda host: [])
    monkeypatch.setattr(render_mod, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(allowed_fulfillment=frozenset())))
    monkeypatch.setattr(render_mod, "site_public_origin", lambda site: "https://bloom.gummfit.com")
    return conn


def test_a_policy_has_its_own_page(monkeypatch):
    _wire(monkeypatch, policy={"body": "Returns\nWithin <b>30</b> days.", "updated_at": NOW})
    response = asyncio.run(render_mod.policy_page("refund", _request("/policies/refund")))
    body = response.body.decode()
    assert response.status_code == 200 and "<h1>Refund policy</h1>" in body
    assert "Within &lt;b&gt;30&lt;/b&gt; days." in body and "Last updated 20 October 2026" in body
    assert 'rel="canonical" href="https://bloom.gummfit.com/policies/refund"' in body
    assert response.headers["content-security-policy"] == render_mod.TENANT_CSP
    # The footer lists the store's other published policies from the same read.
    assert 'href="/policies/terms"' in body


def test_an_unpublished_or_unknown_policy_has_no_page(monkeypatch):
    _wire(monkeypatch, policy=None)
    assert asyncio.run(render_mod.policy_page("refund", _request("/policies/refund"))).status_code == 404
    assert asyncio.run(render_mod.policy_page("cookies", _request("/policies/cookies"))).status_code == 404
    with pytest.raises(HTTPException):
        asyncio.run(render_mod.policy_page("refund", _request("/policies/refund", host="hey-matcha.com")))


def test_the_footer_and_the_bag_list_the_stores_policies():
    site = {"name": "Bloom", "slug": "bloom", "theme_config": {}, "meta_config": {},
            "policies": policies.links(["terms", "refund"])}
    html = render_site_html(site, {"title": "Home", "slug": "home", "content": {"blocks": []}}, [])
    assert ('<div class="cz-foot-policies"><a href="/policies/refund">Refund policy</a>'
            '<a href="/policies/terms">Terms of service</a></div>') in html
    ctx = re.search(r"window\.__CAPPE__=(\{.*?\});</script>", html).group(1)
    assert '"policies": [{"kind": "refund", "title": "Refund policy", "url": "/policies/refund"}' in ctx
    bare = render_site_html({**site, "policies": []}, {"title": "Home", "slug": "home", "content": {"blocks": []}}, [])
    assert '<div class="cz-foot-policies">' not in bare


def test_the_stores_pages_carry_its_policies(monkeypatch):
    _wire(monkeypatch)
    body = asyncio.run(render_mod.render_home(_request("/"))).body.decode()
    assert 'href="/policies/terms"' in body


def test_the_sitemap_lists_the_policies(monkeypatch):
    _wire(monkeypatch, kinds=("privacy", "refund"))
    xml = asyncio.run(render_mod.tenant_seo(_request("/sitemap.xml"), "sitemap")).body.decode()
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert locs[-2:] == ["https://bloom.gummfit.com/policies/refund", "https://bloom.gummfit.com/policies/privacy"]


def test_the_page_renderer_is_the_sites_shell():
    html = render_policy_page({"name": "Bloom", "slug": "bloom", "theme_config": {}, "meta_config": {}}, [], "terms",
                              "Hello", updated_at=None, origin="https://bloom.test")
    assert "<title>Terms of service — Bloom</title>" in html and "Last updated" not in html


def test_the_bag_says_what_ordering_agrees_to():
    js = (ASSETS / "cart.js").read_text()
    assert "(window.__CAPPE__||{}).policies" in js and "RT.esc(RT.url(p.url))" in js
    assert "By placing your order you agree to the store’s " in js and "+terms()+" in js
    assert ".cz-bag__terms{" in (ASSETS / "base.css").read_text()


# ── checkout ─────────────────────────────────────────────────────────────────

class OrderConn:
    def __init__(self, site_cfg):
        self.site_cfg, self.order = site_cfg, None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return self

    async def fetch(self, sql, *args):
        return []

    async def fetchrow(self, sql, *args):
        if "FROM cappe_products" in sql:
            return self.product
        if "FROM cappe_sites" in sql:
            return self.site_cfg
        if "INSERT INTO cappe_orders" in sql:
            self.order = {"id": ORDER, "status": "pending", "access_token": "ab" * 16, "subtotal_cents": args[3],
                          "tax_cents": args[4], "shipping_cents": args[5], "total_cents": args[6],
                          "currency": args[7], "requires_approval": args[9], "shipping_address": None,
                          "ship_country": args[11], "shipping_method": "ship", "shipping_rate_label": "Shipping"}
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        return NOW

    async def execute(self, sql, *args):
        pass


def _checkout(monkeypatch, site_cfg):
    conn = OrderConn({"tax_label": None, "shipping_label": None, **site_cfg})
    conn.product = {"id": uuid4(), "name": "Candle", "price_cents": 2000, "currency": "USD", "inventory": None,
                    "low_stock_threshold": None, "status": "active", "fulfillment": "physical",
                    "booking_type_id": None, "requires_approval": False, "intake_fields": "[]", "sku": None,
                    "weight_g": None, "ships_free": False, "shipping_surcharge_cents": 0}
    owner = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
             "stripe_account_id": "acct_1", "stripe_charges_enabled": True}
    stripe = SimpleNamespace(create_checkout_session=AsyncMock(return_value={"id": "cs_1", "url": "https://pay"}))
    ent = SimpleNamespace(platform_fee_bps=200, allowed_fulfillment=ALL_FULFILLMENT, has=lambda f: True)
    for name, value in (("get_connection", lambda: conn), ("fetch_active_discounts", AsyncMock(return_value=[])),
                        ("fetch_option_groups", AsyncMock(return_value={})), ("fetch_variants", AsyncMock(return_value={})),
                        ("lock_stock_rows", AsyncMock()), ("fetch_site_owner", AsyncMock(return_value=owner)),
                        ("resolve_entitlements", AsyncMock(return_value=ent)), ("require_can_sell", lambda _: None),
                        ("check_recipient_send_ok", AsyncMock(return_value=True)), ("get_cappe_stripe", lambda: stripe)):
        monkeypatch.setattr(commerce, name, value)
    site = {"id": SITE, "name": "Lumen", "timezone": "UTC", "subdomain": "lumen", "custom_domain": "lumen.example.com"}
    body = CappeCheckoutRequest(customer_email="buyer@example.com",
                                items=[CappeCartItem(product_id=conn.product["id"], quantity=1)],
                                success_url="https://lumen.example.com/", cancel_url="https://lumen.example.com/")
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    return stripe.create_checkout_session.await_args.kwargs


def test_the_payment_page_says_what_paying_agrees_to_and_asks_for_a_phone(monkeypatch):
    kw = _checkout(monkeypatch, {"collect_phone": True, "policy_kinds": ["terms", "shipping"]})
    assert kw["collect_phone"] is True
    assert kw["submit_note"] == "By paying you agree to Lumen's terms (https://lumen.example.com/policies/terms)."


def test_without_terms_or_a_refund_policy_the_page_says_nothing(monkeypatch):
    kw = _checkout(monkeypatch, {"policy_kinds": ["privacy"]})
    assert kw["submit_note"] is None and kw["collect_phone"] is False


def test_pay_now_reads_the_same_two_things():
    src = inspect.getsource(commerce.pay_for_order)
    assert "s.collect_phone" in src and "ARRAY(SELECT kind FROM cappe_site_policies WHERE site_id = s.id) AS policy_kinds" in src
    assert 'checkout_note(row["site_name"], site_public_origin(site), row.get("policy_kinds"))' in src


class _FakeStripe:
    def __init__(self):
        self.created = []
        self.checkout = SimpleNamespace(Session=SimpleNamespace(create=lambda **kw: self.created.append(kw) or {"id": "cs"}))


def test_stripe_gets_the_phone_and_the_line(monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setattr(stripe_connect, "stripe", fake)
    svc = object.__new__(stripe_connect.CappeStripe)  # no settings needed: the key check is skipped
    svc._ensure_key = lambda: None

    def create(**extra):
        return asyncio.run(svc.create_checkout_session(
            account_id="acct_1", currency="usd", line_items=[], application_fee_cents=0,
            success_url="https://x.test", cancel_url="https://x.test", metadata={}, **extra))

    create(collect_phone=True, submit_note="By paying you agree to X's terms.")
    create()
    assert fake.created[0]["phone_number_collection"] == {"enabled": True}
    assert fake.created[0]["custom_text"] == {"submit": {"message": "By paying you agree to X's terms."}}
    assert "phone_number_collection" not in fake.created[1] and "custom_text" not in fake.created[1]


def test_stripes_billing_details_land_on_the_order():
    session = {"customer_details": {"name": "Ann", "phone": "+44 7700", "email": "a@example.com",
                                    "address": {"line1": "1 High St", "line2": None, "city": "Bath",
                                                "postal_code": "BA1", "country": "GB", "state": None}}}
    assert extract_billing_details(session) == {
        "name": "Ann", "phone": "+44 7700",
        "address": {"line1": "1 High St", "city": "Bath", "postal_code": "BA1", "country": "GB"}}
    assert extract_billing_details({"customer_details": {"address": {"country": None}}}) is None
    assert extract_billing_details({}) is None
    from app.cappe.routes import payments
    assert "billing_address = COALESCE($7::jsonb, o.billing_address)" in inspect.getsource(payments._mark_order_paid)


# ── the receipt ──────────────────────────────────────────────────────────────

_ORDER = {"currency": "GBP", "business_name": "Lumen", "receipt_number": "LUM-1", "customer_name": "Ann",
          "customer_email": "ann@example.com", "subtotal_cents": 2000, "tax_cents": 0, "total_cents": 2000,
          "created_at": NOW, "tax_label": "VAT"}


def test_the_receipt_names_the_seller_and_the_billing_address():
    html = build_receipt_html({
        **_ORDER, "legal_name": "Lumen Candles Ltd", "business_address": "12 Market St\nBristol <BS1>",
        "tax_id": "GB123", "billing_address": '{"name": "Ann", "address": {"line1": "1 High St", "city": "Bath", "country": "GB"}}',
    }, [])
    assert "Lumen Candles Ltd<br>12 Market St<br>Bristol &lt;BS1&gt;<br>VAT ID: GB123" in html
    assert "<div>1 High St</div><div>Bath</div><div>GB</div>" in html


def test_a_receipt_without_them_is_as_before():
    html = build_receipt_html({**_ORDER, "legal_name": "Lumen"}, [])
    assert "VAT ID" not in html and "<br>" not in html.split("Receipt</div>")[0].split("Lumen</div>")[-1]


def test_the_receipt_query_reads_them():
    from app.cappe.services import receipt
    src = inspect.getsource(receipt.render_order_receipt_pdf)
    # A numbered receipt shows the seller as it was frozen; one not numbered
    # yet shows the store as it is now.
    for col in ("legal_name", "business_address", "tax_id"):
        assert re.search(rf"CASE WHEN o\.receipt_number IS NULL THEN s\.{col}\s+ELSE o\.seller_{col} END AS {col}", src)
    assert "o.billing_address" in src


class _NumberingConn:
    """Just enough connection for `assign_receipt_number`."""

    def __init__(self, existing=None, site=None):
        self.existing, self.site, self.writes = existing, site, []

    def transaction(self):
        class _Tx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *exc):
                return False
        return _Tx()

    async def fetchval(self, sql, *args):
        return self.existing

    async def fetchrow(self, sql, *args):
        assert "RETURNING receipt_seq, receipt_prefix, legal_name, business_address, tax_id" in sql
        return self.site

    async def execute(self, sql, *args):
        self.writes.append((sql, args))


def test_numbering_a_receipt_freezes_the_seller_on_the_order():
    from app.cappe.services.receipt import assign_receipt_number
    order_id, site_id = uuid4(), uuid4()
    conn = _NumberingConn(site={"receipt_seq": 7, "receipt_prefix": "LUM", "legal_name": "Lumen Ltd",
                                "business_address": "12 Market St", "tax_id": "GB123"})
    assert asyncio.run(assign_receipt_number(conn, order_id, site_id)) == "LUM-00007"
    (sql, args), = conn.writes
    assert "seller_legal_name = $3" in sql and "seller_business_address = $4" in sql and "seller_tax_id = $5" in sql
    assert args == ("LUM-00007", order_id, "Lumen Ltd", "12 Market St", "GB123")
    # Already numbered: nothing is re-frozen, so a later change can't reach it.
    conn = _NumberingConn(existing="LUM-00007")
    assert asyncio.run(assign_receipt_number(conn, order_id, site_id)) == "LUM-00007"
    assert conn.writes == []


def test_the_store_takes_who_it_is():
    body = CappeSiteUpdate(legal_name="Lumen Ltd", business_address="12 Market St", tax_id="GB1", collect_phone=True)
    assert body.collect_phone is True
    with pytest.raises(ValidationError):
        CappeSiteUpdate(tax_id="x" * 65)
    assert "legal_name, business_address, tax_id, collect_phone" in site_routes._SITE_COLS
    assert 'add(key, (getattr(body, key) or "").strip() or None)' in inspect.getsource(site_routes)


# ── the checklist ────────────────────────────────────────────────────────────

class ReadyConn:
    def __init__(self, commerce_facts):
        self.facts = commerce_facts

    async def fetch(self, _sql, _site_id):
        return [{"content": '{"blocks": [{"type": "hero", "heading": "Lumen"}]}'}]

    async def fetchval(self, _sql, _site_id):
        return 1

    async def fetchrow(self, _sql, _site_id):
        return self.facts


def _ready(facts, **site):
    return asyncio.run(compute_readiness(ReadyConn(facts), SITE, {"meta_config": None, **site}))


def _items(result):
    return {i["key"]: (i["required"], i["done"]) for i in result["items"]}


def test_a_store_selling_physical_goods_needs_its_refund_and_shipping_policies():
    facts = {"physical": 2, "physical_without_picture": 1, "sells_paid": True, "has_rates": False,
             "policy_kinds": ["refund"], "takes_cards": False}
    result = _ready(facts)
    assert result["ready"] is False
    items = _items(result)
    assert items["policies"] == (True, False)
    assert items["payments"] == (False, False) and items["shipping"] == (False, False)
    assert items["tax"] == (False, False) and items["identity"] == (False, False)
    assert items["product_pictures"] == (False, False)
    done = _ready({**facts, "policy_kinds": ["refund", "shipping"], "takes_cards": True, "physical_without_picture": 0},
                  shipping_free_threshold_cents=0, tax_rate_bps=2000, legal_name="Lumen Ltd", business_address="12 Market St")
    commerce_keys = ("payments", "policies", "shipping", "tax", "identity", "product_pictures")
    assert done["ready"] is True and all(_items(done)[k][1] for k in commerce_keys)


def test_delivery_options_count_as_shipping_set():
    facts = {"physical": 1, "physical_without_picture": 0, "sells_paid": True, "has_rates": True,
             "policy_kinds": ["refund", "shipping"], "takes_cards": True}
    assert _items(_ready(facts))["shipping"] == (False, True)


def test_a_store_without_physical_goods_gets_no_commerce_section():
    items = _items(_ready({"physical": 0, "sells_paid": True, "takes_cards": False}))
    assert "policies" not in items and "shipping" not in items and items["payments"] == (False, False)
    assert "payments" not in _items(_ready({"physical": 0, "sells_paid": False}))


# ── Merlin ───────────────────────────────────────────────────────────────────

def test_merlin_takes_stock_sku_and_weight_for_physical_goods():
    payload, err = sa._validate_create_product(
        {"name": "Candle", "fulfillment": "physical", "price_cents": 2000, "inventory": 12, "sku": " CND-1 ", "weight_g": 400})
    assert err is None and (payload["inventory"], payload["sku"], payload["weight_g"]) == (12, "CND-1", 400)
    unlimited, _ = sa._validate_create_product({"name": "Print", "fulfillment": "physical", "inventory": None})
    assert unlimited["inventory"] is None and "inventory" in unlimited
    untold, _ = sa._validate_create_product({"name": "Mug", "fulfillment": "physical"})
    assert "inventory" not in untold
    digital, _ = sa._validate_create_product({"name": "PDF", "fulfillment": "digital", "inventory": 3})
    assert "inventory" not in digital
    for bad in ({"inventory": -1}, {"inventory": True}, {"weight_g": 1.5}, {"sku": "x" * 121}):
        _p, err = sa._validate_create_product({"name": "x", "fulfillment": "physical", **bad})
        assert err


def test_merlin_says_what_the_stock_will_be():
    base = {"name": "Mug", "fulfillment": "physical", "price_cents": 1200}
    assert sa._summary_create_product(base).endswith("saved as a draft until you set the stock)")
    assert sa._summary_create_product({**base, "inventory": None}).endswith("unlimited stock)")
    assert sa._summary_create_product({**base, "inventory": 5}).endswith("5 in stock)")
    assert "'inventory'" in " ".join(sa.SETUP_ACTIONS_BY_NAME["create_product"].prompt_rules)


class MerlinConn:
    def __init__(self):
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return {"id": uuid4(), "name": args[1], "status": args[4], "fulfillment": args[5]}

    async def execute(self, sql, *args):
        self.calls.append((sql, args))


@pytest.mark.parametrize("extra,status,logged", [
    ({}, "draft", False),                       # nobody said the stock: finish it in Shop
    ({"inventory": None}, "active", False),     # made to order
    ({"inventory": 7}, "active", True),         # opening stock, in the stock history
])
def test_merlin_makes_a_physical_product_with_its_stock(monkeypatch, extra, status, logged):
    monkeypatch.setattr(sa, "assign_slug", AsyncMock())
    monkeypatch.setattr(sa, "refresh_site_search", AsyncMock())
    conn = MerlinConn()
    payload = {"name": "Candle", "fulfillment": "physical", "price_cents": 2000, "description": None,
               "digital_file_url": None, "category": None, "sku": "CND", "weight_g": 400, **extra}
    out = asyncio.run(sa._execute_create_product(conn, {"id": SITE}, object(), payload))
    insert = conn.calls[0]
    assert out["status"] == status and insert[1][8:11] == (extra.get("inventory"), "CND", 400)
    assert any("cappe_inventory_adjustments" in sql for sql, _a in conn.calls) is logged


# ── clients, migration, dev scrub ────────────────────────────────────────────

def test_clients_carry_the_stores_currency():
    row = {"email": "a@example.com", "name": "A", "phone": None, "orders_count": 1, "bookings_count": 0,
           "is_subscriber": False, "has_thread": False, "is_imported": False, "total_spent_cents": 4200,
           "last_activity": NOW, "location_id": None, "location_name": None}
    assert clients_routes._client_from_row(row, "EUR").currency == "EUR"
    src = inspect.getsource(clients_routes)
    assert src.count("site_currency(site)") == 3
    # Orders from before a currency change don't add to a total labelled in the new one.
    assert "CASE WHEN upper(currency) = (SELECT upper(currency) FROM cappe_sites WHERE id = $1)" in clients_routes._CLIENTS_SQL


def test_the_migration_chains_and_adds_everything_it_says():
    src = MIGRATION.read_text()
    assert 'revision = "zzzzcappe54"' in src and 'down_revision = "zzzzcappe53"' in src
    assert "CREATE TABLE IF NOT EXISTS cappe_site_policies" in src and "PRIMARY KEY (site_id, kind)" in src
    assert "CHECK (kind IN ('refund', 'shipping', 'terms', 'privacy'))" in src
    for col in ("legal_name", "business_address", "tax_id", "collect_phone", "billing_address",
                "seller_legal_name", "seller_business_address", "seller_tax_id"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src and f"DROP COLUMN IF EXISTS {col}" in src


def test_dev_refreshes_scrub_billing_addresses():
    sql = (ROOT / "scripts" / "sql" / "anonymize_dev.sql").read_text()
    assert "UPDATE cappe_orders SET billing_address = NULL WHERE billing_address IS NOT NULL" in sql
    assert "column_name = 'billing_address'" in sql
    assert "UPDATE cappe_sites SET" in sql and "tax_id           = CASE WHEN tax_id IS NOT NULL" in sql
    # ...and the copy each numbered receipt froze.
    assert "column_name = 'seller_tax_id'" in sql
    assert "seller_tax_id           = CASE WHEN seller_tax_id IS NOT NULL" in sql
