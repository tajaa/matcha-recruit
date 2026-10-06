"""Plan site caps are checked and consumed under one per-account row lock."""
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.routes import sites  # noqa: E402


class _Transaction:
    def __init__(self, conn):
        self.conn = conn

    # Depth 1 is the account-lock transaction; depth 2 is the per-attempt
    # savepoint around the site INSERT, which must never outlive the lock.
    async def __aenter__(self):
        assert self.conn.depth < 2
        self.conn.depth += 1
        self.conn.in_transaction = True
        self.conn.events.append("begin" if self.conn.depth == 1 else "savepoint")

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.depth -= 1
        if self.conn.depth == 0:
            self.conn.events.append("rollback" if exc_type else "commit")
            self.conn.in_transaction = False
        elif exc_type:
            self.conn.events.append("savepoint-rollback")


class _Conn:
    def __init__(self, account_id, *, template=False, collisions=0):
        self.account_id = account_id
        self.template = template
        # How many site INSERTs lose the race for their subdomain.
        self.collisions = collisions
        self.taken: set[str] = set()
        self.inserted_args = None
        self.depth = 0
        self.in_transaction = False
        self.events: list[str] = []
        self.site_id = uuid4()

    def transaction(self):
        return _Transaction(self)

    async def fetchval(self, sql, *args):
        if "FROM cappe_accounts" in sql:
            assert self.in_transaction
            self.events.append("lock")
            return self.account_id
        if "COUNT(*) FROM cappe_sites" in sql:
            assert self.in_transaction
            self.events.append("count")
            return 0
        if "SELECT 1 FROM cappe_sites" in sql:
            assert self.in_transaction
            self.events.append("slug")
            return 1 if args[0] in self.taken else None
        if "INSERT INTO cappe_pages" in sql:
            # The template path inserts its real pages with RETURNING id.
            assert self.in_transaction
            self.events.append("page")
            return uuid4()
        raise AssertionError(sql)

    async def fetchrow(self, sql, *args):
        if "INSERT INTO cappe_sites" in sql:
            assert self.depth == 2, "site INSERT must run inside its savepoint"
            if self.collisions:
                self.collisions -= 1
                self.taken.add(args[2])
                raise asyncpg.UniqueViolationError("cappe_sites_slug_key")
            self.inserted_args = args
            self.events.append("site")
            return self._site_row(
                name=args[1], slug=args[2],
                source_type="template" if self.template else args[3],
                template_slug=args[3] if self.template else None,
            )
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        assert self.in_transaction
        if "INSERT INTO cappe_pages" not in sql:
            raise AssertionError(sql)
        self.events.append("page")
        return "INSERT 0 1"

    def _site_row(self, *, name, slug, source_type, template_slug):
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        return {
            "id": self.site_id, "account_id": self.account_id,
            "name": name, "slug": slug, "subdomain": slug,
            "custom_domain": None, "source_type": source_type,
            "template_id": None, "template_slug": template_slug, "status": "draft",
            "theme_config": "{}", "meta_config": "{}", "timezone": "UTC",
            "is_multi_location": False, "tax_rate_bps": 0, "tax_label": "Tax",
            "shipping_flat_cents": 0, "shipping_free_threshold_cents": None,
            "shipping_label": "Shipping", "receipt_prefix": "ORDER",
            "listed": False, "directory_category": None, "directory_tags": "[]",
            "directory_blurb": None, "directory_confirmed_at": None,
            "published_at": None, "created_at": now, "updated_at": now,
        }


class _ConnCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


def _patch_dependencies(monkeypatch, conn):
    monkeypatch.setattr(sites, "get_connection", lambda: _ConnCtx(conn))

    async def _entitlements(_plan, *, conn=None):
        assert conn is not None and conn.in_transaction
        conn.events.append("entitlements")
        return SimpleNamespace(site_limit=1)

    monkeypatch.setattr(sites, "resolve_entitlements", _entitlements)


@pytest.mark.asyncio
async def test_blank_site_limit_check_and_insert_share_account_lock(monkeypatch):
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id)
    _patch_dependencies(monkeypatch, conn)

    await sites.create_site(
        SimpleNamespace(name="Demo", source_type="blank", is_multi_location=False, directory_category=None),
        account,
    )

    assert conn.events == [
        "begin", "lock", "entitlements", "count", "slug", "savepoint", "site", "page", "commit",
    ]


@pytest.mark.asyncio
async def test_template_site_limit_check_and_insert_share_account_lock(monkeypatch):
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id, template=True)
    _patch_dependencies(monkeypatch, conn)

    site = await sites.create_site_from_template(
        SimpleNamespace(
            template_slug="saveur-bistro", name="Demo", is_multi_location=True,
            directory_category="food-drink",
        ),
        account,
    )

    # No catalog read: the registry is in-process, so the first DB touch is
    # the account lock. One page INSERT per template page.
    assert conn.events[:7] == ["begin", "lock", "entitlements", "count", "slug", "savepoint", "site"]
    assert conn.events[-1] == "commit"
    assert conn.events.count("page") == len(sites.get_template("saveur-bistro").pages)
    assert site["page_count"] == conn.events.count("page")
    # The wizard's answers survive the template path: several locations, and
    # the Discover category it picked.
    (_acct, _name, _slug, template_slug, theme_json, multi, category) = conn.inserted_args
    assert template_slug == "saveur-bistro"
    assert multi is True
    assert category == "food-drink"
    # A free account's clone is gated exactly like the editor's save path.
    assert "premium" not in json.loads(theme_json)
    assert json.loads(theme_json)["template"] == "saveur-bistro"


@pytest.mark.asyncio
async def test_losing_the_subdomain_race_retries_on_the_next_free_name(monkeypatch):
    """Another account took "bakery" between the check and the INSERT. That was
    a 500; now the attempt is rolled back to its savepoint (the account lock
    is kept) and the site lands on the next candidate."""
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id, collisions=1)
    _patch_dependencies(monkeypatch, conn)

    site = await sites.create_site(
        SimpleNamespace(name="Bakery", source_type="blank", is_multi_location=False, directory_category=None), account,
    )

    assert site["slug"] == "bakery-2"
    assert conn.events == [
        "begin", "lock", "entitlements", "count",
        "slug", "savepoint", "savepoint-rollback",
        "slug", "slug", "savepoint", "site", "page", "commit",
    ]


@pytest.mark.asyncio
async def test_repeated_subdomain_collisions_end_in_a_409_not_a_500(monkeypatch):
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id, collisions=99)
    _patch_dependencies(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        await sites.create_site(
            SimpleNamespace(name="Demo", source_type="blank", is_multi_location=False, directory_category=None), account,
        )

    assert exc.value.status_code == 409
    assert conn.events[-1] == "rollback"
    assert "site" not in conn.events


@pytest.mark.asyncio
async def test_hitting_the_site_cap_carries_a_code_the_dashboard_can_act_on(monkeypatch):
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id)
    _patch_dependencies(monkeypatch, conn)

    async def _full(sql, *args):
        if "COUNT(*) FROM cappe_sites" in sql:
            return 1
        return account.id

    conn.fetchval = _full
    with pytest.raises(HTTPException) as exc:
        await sites.create_site(
            SimpleNamespace(name="Second", source_type="blank", is_multi_location=False, directory_category=None), account,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "site_limit_reached"
    assert "Upgrade to create more" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_blank_site_keeps_the_category_the_wizard_asked_for(monkeypatch):
    """The category question comes BEFORE blank-vs-template, so the blank
    path must not drop the answer."""
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id)
    _patch_dependencies(monkeypatch, conn)

    await sites.create_site(
        SimpleNamespace(name="Demo", source_type="blank", is_multi_location=False, directory_category="pets"),
        account,
    )
    assert conn.inserted_args[-1] == "pets"

    conn = _Conn(account.id)
    _patch_dependencies(monkeypatch, conn)
    await sites.create_site(
        SimpleNamespace(name="Demo", source_type="blank", is_multi_location=False, directory_category="made-up"),
        account,
    )
    assert conn.inserted_args[-1] is None  # unknown slug dropped, not stored


@pytest.mark.asyncio
async def test_a_pre_registry_tab_can_still_clone_by_the_old_row_id(monkeypatch):
    """A tab that loaded the gallery before the deploy posts `template_id`.
    The retired row's slug is mapped onto its registry replacement."""
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id, template=True)
    _patch_dependencies(monkeypatch, conn)
    base_fetchval = conn.fetchval

    async def _fetchval(sql, *args):
        if "FROM cappe_templates" in sql:
            assert not conn.in_transaction
            return "restaurant"
        return await base_fetchval(sql, *args)

    conn.fetchval = _fetchval
    await sites.create_site_from_template(
        SimpleNamespace(template_slug=None, template_id=uuid4(), name="Demo",
                        is_multi_location=False, directory_category=None),
        account,
    )
    assert conn.inserted_args[3] == "saveur-bistro"


@pytest.mark.asyncio
async def test_an_unknown_template_is_a_404_before_any_lock(monkeypatch):
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id, template=True)
    _patch_dependencies(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        await sites.create_site_from_template(
            SimpleNamespace(template_slug="nope", name="Demo", is_multi_location=False, directory_category=None),
            account,
        )
    assert exc.value.status_code == 404
    assert conn.events == []


# --- reset-to-template ---------------------------------------------------------

class _ResetConn:
    def __init__(self, site, *, vanish=False):
        self.site = site
        self.vanish = vanish
        self.written = None

    async def fetchrow(self, sql, *args):
        if sql.startswith("SELECT * FROM cappe_sites"):
            return self.site
        if "UPDATE cappe_sites SET theme_config" in sql:
            if self.vanish:
                return None
            self.written = json.loads(args[0])
            return {**self.site, "theme_config": args[0]}
        raise AssertionError(sql)


def _patch_reset(monkeypatch, conn):
    invalidated = []
    monkeypatch.setattr(sites, "get_connection", lambda: _ConnCtx(conn))

    async def _invalidate(site_id):
        invalidated.append(site_id)

    monkeypatch.setattr(sites, "invalidate_render_cache", _invalidate)
    return invalidated


def _reset_site(template_slug):
    return {"id": uuid4(), "template_slug": template_slug,
            "theme_config": json.dumps({"preset": "noir"}), "meta_config": "{}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("plan, keeps_premium", [("free", False), ("business", True)])
async def test_reset_restores_the_template_theme_gated_to_the_plan(monkeypatch, plan, keeps_premium):
    site = _reset_site("saveur-bistro")
    conn = _ResetConn(site)
    invalidated = _patch_reset(monkeypatch, conn)

    out = await sites.reset_theme_to_template(site["id"], SimpleNamespace(id=uuid4(), plan=plan))

    template = sites.get_template("saveur-bistro")
    assert conn.written["colors"] == template.theme["colors"]
    assert conn.written["template"] == "saveur-bistro"
    assert "preset" not in conn.written
    assert ("premium" in conn.written) is keeps_premium
    assert out["theme_config"] == conn.written
    assert invalidated == [site["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("template_slug", [None, "retired-template"])
async def test_reset_404s_when_the_site_has_no_template_in_the_catalog(monkeypatch, template_slug):
    site = _reset_site(template_slug)
    conn = _ResetConn(site)
    invalidated = _patch_reset(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        await sites.reset_theme_to_template(site["id"], SimpleNamespace(id=uuid4(), plan="free"))
    assert exc.value.status_code == 404
    assert conn.written is None and invalidated == []


@pytest.mark.asyncio
async def test_reset_404s_instead_of_500_when_the_site_vanishes_mid_request(monkeypatch):
    site = _reset_site("saveur-bistro")
    conn = _ResetConn(site, vanish=True)
    invalidated = _patch_reset(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        await sites.reset_theme_to_template(site["id"], SimpleNamespace(id=uuid4(), plan="free"))
    assert exc.value.status_code == 404
    assert invalidated == []

