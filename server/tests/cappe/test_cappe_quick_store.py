"""An online store in one step: `POST /sites/quick-store` (services/quick_store.py)."""
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models.cappe import CappeQuickStoreCreate  # noqa: E402
from app.cappe.routes import sites  # noqa: E402
from app.cappe.services import quick_store, readiness  # noqa: E402
from app.cappe.services.entitlements import Entitlements  # noqa: E402
from app.cappe.services.policies import REQUIRED_FOR_PHYSICAL, starter  # noqa: E402


class _Tx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.depth += 1
        self.conn.events.append("begin" if self.conn.depth == 1 else "savepoint")

    async def __aexit__(self, exc_type, *_):
        self.conn.depth -= 1
        if self.conn.depth == 0:
            self.conn.events.append("rollback" if exc_type else "commit")


class _Conn:
    def __init__(self, account_id):
        self.account_id = account_id
        self.site_id = uuid4()
        self.depth = 0
        self.events: list[str] = []
        self.site_args = None
        self.page = None
        self.policies: dict[str, str] = {}

    def transaction(self):
        return _Tx(self)

    async def fetchval(self, sql, *args):
        if "FROM cappe_accounts" in sql:
            assert self.depth
            self.events.append("lock")
            return self.account_id
        if "COUNT(*) FROM cappe_sites" in sql:
            return 0
        if "SELECT 1 FROM cappe_sites" in sql:
            return None
        raise AssertionError(sql)

    async def fetchrow(self, sql, *args):
        assert "INSERT INTO cappe_sites" in sql, sql
        self.site_args = args
        self.events.append("site")
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        return {
            "id": self.site_id, "account_id": self.account_id, "name": args[1], "slug": args[2],
            "subdomain": args[2], "custom_domain": None, "source_type": "blank", "template_id": None,
            "template_slug": None, "status": "draft", "theme_config": "{}", "meta_config": "{}",
            "timezone": args[4] or "UTC", "is_multi_location": False, "tax_rate_bps": 0,
            "tax_label": "Tax", "shipping_flat_cents": 0, "shipping_free_threshold_cents": None,
            "shipping_label": "Shipping", "receipt_prefix": "ORDER", "listed": False,
            "directory_category": args[3], "directory_tags": "[]", "directory_blurb": None,
            "directory_confirmed_at": None, "published_at": None, "created_at": now, "updated_at": now,
        }

    async def execute(self, sql, *args):
        assert self.depth, "every write is inside the store's transaction"
        if "INSERT INTO cappe_pages" in sql:
            self.page = json.loads(args[1])
            self.events.append("page")
        elif "INSERT INTO cappe_site_policies" in sql:
            self.policies[args[1]] = args[2]
            self.events.append("policy")
        else:
            raise AssertionError(sql)
        return "INSERT 0 1"


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_):
        return False


def _ent(*kinds):
    return Entitlements(
        plan_code="x", plan_name="Free", can_sell=True, platform_fee_bps=200,
        allowed_fulfillment=frozenset(kinds), features={}, site_limit=None, mailbox_quota_included=0,
    )


@pytest.fixture
def setup(monkeypatch):
    account = SimpleNamespace(id=uuid4(), plan="business", account_type="business")
    conn = _Conn(account.id)
    made: list = []
    state = {"ent": _ent("physical", "digital", "service", "booking")}

    async def _entitlements(_plan, *, conn=None):
        return state["ent"]

    async def _insert_product(c, site_id, body):
        assert c.depth, "the product is written in the store's transaction"
        c.events.append("product")
        made.append(body)
        return {"id": uuid4()}

    async def _product_out(_c, row):
        return {"id": row["id"]}

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(sites, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(sites, "resolve_entitlements", _entitlements)
    monkeypatch.setattr(sites, "insert_product", _insert_product)
    monkeypatch.setattr(sites, "_product_out", _product_out)
    monkeypatch.setattr(sites, "refresh_site_search", _noop)
    monkeypatch.setattr(sites, "invalidate_render_cache", _noop)
    return SimpleNamespace(account=account, conn=conn, made=made, state=state)


def _body(**over):
    data = {"name": " Karajan Goods ", "tagline": "Small-batch ceramics.", "timezone": "America/New_York",
            "product": {"name": "Moon mug", "price_cents": 2400, "inventory": 12}}
    data.update(over)
    return CappeQuickStoreCreate(**data)


def test_home_page_is_the_name_the_line_and_the_shop():
    hero, store = quick_store.home_blocks("Karajan Goods", "  Small-batch ceramics. ")
    assert hero == {"type": "hero", "style": "centered", "heading": "Karajan Goods",
                    "subheading": "Small-batch ceramics.", "cta": "Shop now", "ctaHref": "#shop"}
    assert store["type"] == "store"
    # No line given: no line printed, never placeholder copy.
    assert "subheading" not in quick_store.home_blocks("Karajan Goods", " ")[0]


def test_the_home_page_and_policies_meet_the_publish_checklist():
    hero, store = quick_store.home_blocks("Karajan Goods", None)
    assert hero["type"] in readiness._CONTENT_BLOCKS
    assert readiness._block_has_text({k: v for k, v in hero.items() if k != "type"})
    assert store["type"] in readiness._SELL_BLOCKS
    assert {k for k, _ in quick_store.starter_policies()} == set(REQUIRED_FOR_PHYSICAL)


@pytest.mark.asyncio
async def test_makes_the_whole_store_in_one_transaction(setup):
    out = await sites.create_quick_store(_body(), setup.account)

    ev = setup.conn.events
    assert ev[0] == "begin" and ev[-1] == "commit" and ev.count("begin") == 1
    assert ev.index("lock") < ev.index("site") < ev.index("page") < ev.index("product")
    # Name trimmed, listed under Retail, the owner's timezone.
    assert setup.conn.site_args[1] == "Karajan Goods"
    assert setup.conn.site_args[3] == "retail"
    assert setup.conn.site_args[4] == "America/New_York"
    assert setup.conn.page == {"blocks": quick_store.home_blocks("Karajan Goods", "Small-batch ceramics.")}
    assert setup.conn.policies == {k: starter(k) for k in REQUIRED_FOR_PHYSICAL}
    (product,) = setup.made
    assert (product.name, product.price_cents, product.inventory) == ("Moon mug", 2400, 12)
    assert product.fulfillment == "physical" and product.status == "active"
    assert out["product"] is not None and out["site"]["name"] == "Karajan Goods"


@pytest.mark.asyncio
async def test_a_plan_that_cant_sell_goods_is_refused_before_anything_is_written(setup):
    setup.state["ent"] = _ent("digital", "service", "booking")
    with pytest.raises(HTTPException) as exc:
        await sites.create_quick_store(_body(), setup.account)
    assert exc.value.status_code == 403
    assert setup.conn.events == []


@pytest.mark.asyncio
async def test_the_store_can_be_made_without_its_product(setup):
    setup.state["ent"] = _ent("digital", "service", "booking")
    out = await sites.create_quick_store(_body(product=None, tagline=None), setup.account)
    assert out["product"] is None and setup.made == []
    assert "subheading" not in setup.conn.page["blocks"][0]
    assert set(setup.conn.policies) == set(REQUIRED_FOR_PHYSICAL)


@pytest.mark.asyncio
async def test_a_blank_name_is_refused(setup):
    with pytest.raises(HTTPException) as exc:
        await sites.create_quick_store(_body(name="   "), setup.account)
    assert exc.value.status_code == 422
    assert setup.conn.events == []
