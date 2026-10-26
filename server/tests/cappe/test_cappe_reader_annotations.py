"""All connections are fakes: no schema or database is touched."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.cappe.models.reader import ReaderAnnotationCreate, ReaderQuote
from app.cappe.routes import reader_annotations as routes
from app.cappe.services.magazine import annotations as service
from tests._helpers.routes import QueryConn, route_client

ACCOUNT, POST, SITE, NOTE = uuid4(), uuid4(), uuid4(), uuid4()
QUOTE = {"exact": "Hello 🌍", "prefix": "", "suffix": "!", "start": 0}
BODY = {"kind": "highlight", "view": "pages", "page": 1, "quote": QUOTE, "text": ""}
ROW = {"id": NOTE, "body": json.dumps(BODY)}
PATH = f"/reader/magazines/salt/stories/tide/annotations/{NOTE}"


class Conn(QueryConn):
    @asynccontextmanager
    async def transaction(self):
        self.calls.append(("transaction", "begin", ()))
        try:
            yield self
        finally:
            self.calls.append(("transaction", "end", ()))


@pytest.mark.parametrize("change", [
    {"kind": "unknown"}, {"page": 0}, {"page": 10001}, {"view": "admin"},
    {"quote": None}, {"text": "x" * 4001}, {"text": "\ud800"}, {"text": "\x00"},
    {"quote": {**QUOTE, "exact": "x" * 2001}}, {"quote": {**QUOTE, "start": -1}},
    {"quote": {**QUOTE, "prefix": "x" * 65}}, {"quote": {**QUOTE, "suffix": "\udfff"}},
    {"kind": "comment", "text": "  "}, {"account_id": str(uuid4())},
])
def test_invalid_shapes(change):
    with pytest.raises(ValidationError):
        ReaderAnnotationCreate(**{**BODY, **change})


def test_unicode_and_page_comments():
    assert ReaderQuote(**QUOTE).exact == "Hello 🌍"
    body = ReaderAnnotationCreate(kind="comment", page=10000, quote=None, text="🌍" * 4000)
    assert len(body.text) == 4000 and body.view == "pages"


@pytest.mark.parametrize("paid,shopper,access,expected", [
    (False, None, False, 200), (True, None, False, 403),
    (True, {"id": uuid4()}, False, 403), (True, {"id": uuid4()}, True, 200),
])
def test_read_access_rechecked(monkeypatch, paid, shopper, access, expected):
    confirmed = AsyncMock(return_value="rae@example.com")
    live = AsyncMock(return_value={"id": POST, "access": "paid" if paid else "free"})
    paid_access = AsyncMock(return_value=access)
    monkeypatch.setattr(service.shelf, "confirmed_email", confirmed)
    monkeypatch.setattr(service.shelf, "published_magazine", AsyncMock(return_value=({"id": SITE}, {})))
    monkeypatch.setattr(service.reader, "live_story", live)
    monkeypatch.setattr(service.shelf, "shopper_for", AsyncMock(return_value=shopper))
    monkeypatch.setattr(service, "has_paid_access", paid_access)
    if expected == 403:
        with pytest.raises(HTTPException) as err:
            asyncio.run(service.readable_post(None, ACCOUNT, "salt", "tide"))
        assert err.value.status_code == 403
    else:
        assert asyncio.run(service.readable_post(None, ACCOUNT, "salt", "tide")) == POST
    confirmed.assert_awaited_once_with(None, ACCOUNT)
    live.assert_awaited_once_with(None, SITE, slug="tide")
    if paid and shopper:
        paid_access.assert_awaited_once_with(None, SITE, shopper["id"])


def test_unpublished_story_is_not_readable(monkeypatch):
    monkeypatch.setattr(service.shelf, "confirmed_email", AsyncMock(return_value="rae@example.com"))
    monkeypatch.setattr(service.shelf, "published_magazine", AsyncMock(return_value=({"id": SITE}, {})))
    monkeypatch.setattr(service.reader, "live_story", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as err:
        asyncio.run(service.readable_post(None, ACCOUNT, "salt", "tide"))
    assert err.value.status_code == 404


def test_retry_returns_original_even_at_cap():
    conn = Conn(fetchval={"FOR UPDATE": ACCOUNT}, fetchrow={"SELECT id, body": ROW})
    assert asyncio.run(service.save(conn, ACCOUNT, POST, NOTE, ReaderAnnotationCreate(**BODY)))["id"] == str(NOTE)
    assert not any("COUNT" in sql or "INSERT" in sql for _, sql, _ in conn.calls)
    assert conn.args_for("SELECT id, body") == (ACCOUNT, POST, NOTE)
    assert conn.calls[0][1] == "begin" and conn.calls[-1][1] == "end"


def test_create_is_bounded_and_transactional():
    conn = Conn(fetchval={"FOR UPDATE": ACCOUNT, "COUNT(*)": 249},
                fetchrow={"SELECT id, body": None, "INSERT INTO": ROW})
    assert asyncio.run(service.save(conn, ACCOUNT, POST, NOTE, ReaderAnnotationCreate(**BODY)))["quote"] == QUOTE
    args = conn.args_for("INSERT INTO")
    assert args[:3] == (ACCOUNT, POST, NOTE) and json.loads(args[3]) == BODY
    assert conn.args_for("COUNT(*)") == (ACCOUNT, POST) and "FOR UPDATE" in conn.calls[1][1]
    conn.set("fetchval", "COUNT(*)", 250)
    with pytest.raises(HTTPException) as err:
        asyncio.run(service.save(conn, ACCOUNT, POST, NOTE, ReaderAnnotationCreate(**BODY)))
    assert err.value.status_code == 409


def test_listing_and_deleting_scope_all_keys():
    conn = Conn(fetch={"SELECT id, body": [ROW]})
    assert asyncio.run(service.listing(conn, ACCOUNT, POST)) == [{**BODY, "id": str(NOTE)}]
    assert conn.args_for("SELECT id, body") == (ACCOUNT, POST, 250)
    asyncio.run(service.remove(conn, ACCOUNT, POST, NOTE))
    assert conn.args_for("DELETE FROM") == (ACCOUNT, POST, NOTE)
    assert "account_id = $1 AND post_id = $2 AND id = $3" in conn.sql_for("execute")[0]
    assert service.annotation({"id": NOTE, "body": BODY})["id"] == str(NOTE)


@pytest.mark.parametrize("verb", ["get", "put", "delete"])
def test_routes_auth_scope_private_and_recheck_access(monkeypatch, verb):
    conn = Conn()
    monkeypatch.setattr(routes, "get_connection", lambda: conn)
    monkeypatch.setattr(routes, "check_rate_limit", AsyncMock())
    readable = AsyncMock(return_value=POST)
    monkeypatch.setattr(service, "readable_post", readable)
    operations = {"get": AsyncMock(return_value=[{**BODY, "id": str(NOTE)}]),
                  "put": AsyncMock(return_value={**BODY, "id": str(NOTE)}), "delete": AsyncMock()}
    for name, verb_ in (("listing", "get"), ("save", "put"), ("remove", "delete")):
        monkeypatch.setattr(service, name, operations[verb_])
    with route_client(routes.router, overrides={routes.require_cappe_account: SimpleNamespace(id=ACCOUNT)}) as client:
        url = PATH.rsplit("/", 1)[0] if verb == "get" else PATH
        response = getattr(client, verb)(url, **({"json": BODY} if verb == "put" else {}))
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store, private"
        readable.assert_awaited_once_with(conn, ACCOUNT, "salt", "tide")
        call = operations[verb].await_args.args
        assert call[:3] == (conn, ACCOUNT, POST)
        if verb != "get":
            assert call[3] == NOTE
        readable.side_effect = HTTPException(403, "No access")
        assert getattr(client, verb)(url, **({"json": BODY} if verb == "put" else {})).status_code == 403
    with route_client(routes.router) as client:
        assert getattr(client, verb)(url, **({"json": BODY} if verb == "put" else {})).status_code in (401, 403)


def test_migration_is_additive_and_refuses_destructive_downgrade(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[2] / "alembic/versions/cappereader01_annotations.py"
    spec = importlib.util.spec_from_file_location("reader_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    sql = []
    monkeypatch.setattr(migration.op, "execute", sql.append)
    migration.upgrade()
    assert "PRIMARY KEY (account_id, post_id, id)" in sql[0]
    assert sql[0].count("ON DELETE CASCADE") == 2 and "octet_length" in sql[0]
    assert "(post_id)" in sql[1]
    migration.downgrade()
    assert "IF EXISTS" in sql[2] and "RAISE EXCEPTION" in sql[2]
    assert sql[3] == "DROP TABLE cappe_reader_annotations"
