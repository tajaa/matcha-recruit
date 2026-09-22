"""Plan site caps are checked and consumed under one per-account row lock."""
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.routes import sites  # noqa: E402


class _Transaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        assert not self.conn.in_transaction
        self.conn.in_transaction = True
        self.conn.events.append("begin")

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.events.append("rollback" if exc_type else "commit")
        self.conn.in_transaction = False


class _Conn:
    def __init__(self, account_id, *, template=False):
        self.account_id = account_id
        self.template = template
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
            return None
        raise AssertionError(sql)

    async def fetchrow(self, sql, *args):
        if "FROM cappe_templates" in sql:
            assert not self.in_transaction
            self.events.append("template")
            return {
                "id": args[0], "name": "Starter", "is_active": True,
                "structure": json.dumps({"theme": {}, "pages": []}),
            }
        if "INSERT INTO cappe_sites" in sql:
            assert self.in_transaction
            self.events.append("site")
            return self._site_row(
                name=args[1], slug=args[2],
                source_type="template" if self.template else args[3],
                template_id=args[3] if self.template else None,
            )
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        assert self.in_transaction
        if "INSERT INTO cappe_pages" not in sql:
            raise AssertionError(sql)
        self.events.append("page")
        return "INSERT 0 1"

    def _site_row(self, *, name, slug, source_type, template_id):
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        return {
            "id": self.site_id, "account_id": self.account_id,
            "name": name, "slug": slug, "subdomain": slug,
            "custom_domain": None, "source_type": source_type,
            "template_id": template_id, "status": "draft",
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
        SimpleNamespace(name="Demo", source_type="blank", is_multi_location=False),
        account,
    )

    assert conn.events == [
        "begin", "lock", "entitlements", "count", "slug", "site", "page", "commit",
    ]


@pytest.mark.asyncio
async def test_template_site_limit_check_and_insert_share_account_lock(monkeypatch):
    account = SimpleNamespace(id=uuid4(), plan="free")
    conn = _Conn(account.id, template=True)
    _patch_dependencies(monkeypatch, conn)

    await sites.create_site_from_template(
        SimpleNamespace(template_id=uuid4(), name="Demo"), account,
    )

    assert conn.events == [
        "template", "begin", "lock", "entitlements", "count", "slug",
        "site", "page", "commit",
    ]
