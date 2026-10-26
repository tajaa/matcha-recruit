"""Writer setup is atomic, private and safe to replay. No real DB access."""
import asyncio
import copy
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4, uuid5

import pytest
from fastapi import HTTPException

from app.cappe.models.magazine import CappeMagazineStart
from app.cappe.routes import magazine
from app.cappe.services.magazine.studio.schema import starter_doc
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_writers import BODY, BUSINESS, WRITER, _site_row


class SetupConn:
    def __init__(self):
        self.site = None
        self.post = None
        self.events = []
        self.fail = False
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self):
        # Model the account row lock's lifetime, including rollback after a
        # failing post insert. Concurrent calls share this fake database.
        async with self.lock:
            snapshot = copy.deepcopy((self.site, self.post))
            self.events.append("begin")
            try:
                yield
            except Exception:
                self.site, self.post = snapshot
                self.events.append("rollback")
                raise
            else:
                self.events.append("commit")

    async def fetchrow(self, sql, *args):
        if "SELECT" in sql and "FROM cappe_sites" in sql:
            assert "account_id = $2" in sql
            return self.site if self.site and (self.site["id"], self.site["account_id"]) == args else None
        if "INSERT INTO cappe_sites" in sql:
            self.events.append("site")
            self.site = _site_row(id=args[4], account_id=args[0], name=args[1], slug=args[2], subdomain=args[2])
            return self.site
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if "FROM cappe_sites" in sql:
            return self.site is not None
        if "FROM cappe_posts" in sql:
            assert "id = $1 AND site_id = $2" in sql
            return self.post[0] if self.post and self.post[:2] == args else None
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "INSERT INTO cappe_pages" in sql:
            assert "'draft'" in sql
            self.events.append("about")
        elif "INSERT INTO cappe_posts" in sql:
            assert "'draft', 'pages'" in sql and "'free'" in sql
            self.events.append("post")
            if self.fail:
                raise RuntimeError("post insert interrupted")
            self.post = args
        else:
            raise AssertionError(sql)


@pytest.fixture
def setup(monkeypatch):
    conn = SetupConn()

    async def lock(conn, account_id):
        assert conn.lock.locked()
        conn.events.append("lock")

    async def limit(conn, account):
        conn.events.append("limit")
        if conn.site:
            raise HTTPException(status_code=402, detail="Site limit")

    async def save(conn, site_id, fields, **kw):
        assert conn.lock.locked() and fields["front_at_root"] is True
        conn.events.append("magazine")

    monkeypatch.setattr(magazine, "get_connection", lambda: conn_context(conn))
    monkeypatch.setattr(magazine, "_lock_account_for_site_creation", lock)
    monkeypatch.setattr(magazine, "_enforce_site_limit", limit)
    monkeypatch.setattr(magazine, "save_magazine", save)
    return conn


@asynccontextmanager
async def conn_context(conn):
    yield conn


def payload(**over):
    return {**BODY, "request_id": str(uuid4()), "doc": starter_doc(), **over}


def client(account=WRITER):
    return route_client(magazine.router, overrides={magazine.require_cappe_account: account})


def test_creates_private_site_and_editable_draft_without_photos_or_a_plan(setup):
    body = payload(name="  The Harbour Review  ")
    doc = body["doc"]
    doc["items"].append({"id": "photo", "kind": "image", "page": "p1", "x": 0, "y": 0, "w": 100, "h": 100,
                         "asset_id": str(uuid4()), "caption": "Private sample", "cutout": {"asset_id": str(uuid4())}})
    doc["paywall_page"] = 2
    free_writer = SimpleNamespace(**{**vars(WRITER), "plan": "free"})
    with client(free_writer) as api:
        result = api.post("/magazine/quick-start", json=body)
    assert result.status_code == 201, result.text
    data = result.json()
    site_id = uuid5(WRITER.id, f"writer-start:{body['request_id']}")
    assert data["site"]["id"] == str(site_id)
    assert data["post_id"] == str(uuid5(site_id, "first-draft"))
    assert data["site"]["status"] == "draft" and data["site"]["published_at"] is None
    assert setup.events == ["begin", "lock", "limit", "site", "magazine", "about", "post", "commit"]
    assert setup.post[2] == "The Harbour Review — First edition"
    saved = json.loads(setup.post[3])
    assert saved["doc"]["items"][-1]["asset_id"] is None
    assert saved["doc"]["items"][-1]["caption"] == ""
    assert "cutout" not in saved["doc"]["items"][-1]
    assert saved["doc"]["paywall_page"] is None


def test_lost_response_replay_does_not_hit_site_limit_or_overwrite_edits(setup):
    body = payload()
    with client() as api:
        first = api.post("/magazine/quick-start", json=body)
        setup.post = (*setup.post[:2], "Owner-edited title", *setup.post[3:])
        again = api.post("/magazine/quick-start", json=body)
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    assert setup.events[-3:] == ["begin", "lock", "commit"]
    assert setup.events.count("limit") == 1 and setup.events.count("post") == 1
    assert setup.post[2] == "Owner-edited title"


def test_concurrent_duplicate_start_returns_one_draft(setup):
    body = CappeMagazineStart(**payload())

    async def duplicate():
        return await asyncio.gather(magazine.quick_start_magazine(body, WRITER),
                                    magazine.quick_start_magazine(body, WRITER))

    a, b = asyncio.run(duplicate())
    assert a == b
    assert setup.events.count("post") == setup.events.count("site") == 1


def test_failure_rolls_back_the_magazine_and_retry_can_finish(setup):
    body = CappeMagazineStart(**payload())
    setup.fail = True
    with pytest.raises(RuntimeError, match="post insert interrupted"):
        asyncio.run(magazine.quick_start_magazine(body, WRITER))
    assert setup.site is None and setup.post is None and setup.events[-1] == "rollback"
    setup.fail = False
    result = asyncio.run(magazine.quick_start_magazine(body, WRITER))
    assert result["post_id"] == setup.post[0]


@pytest.mark.parametrize("over", [
    {"name": "   "}, {"name": "a" * 121}, {"handle": "www"}, {"topics": ["made-up"]},
    {"doc": {"pages": []}}, {"doc": {"pages": [{"id": f"p{i}"} for i in range(33)]}},
    {"doc": {"extra": "x" * 1_000_001}}, {"request_id": "bad"},
])
def test_refuses_invalid_input_before_writing(setup, over):
    with client() as api:
        result = api.post("/magazine/quick-start", json=payload(**over))
    assert result.status_code == 422, result.text
    assert setup.events == []


def test_business_cannot_create_a_writer_magazine(setup):
    with client(BUSINESS) as api:
        assert api.post("/magazine/quick-start", json=payload()).status_code == 403
    assert setup.events == []


def test_same_request_key_from_another_account_cannot_replay_the_first_magazine(setup):
    body = payload()
    with client() as api:
        assert api.post("/magazine/quick-start", json=body).status_code == 201
    other = SimpleNamespace(**{**vars(WRITER), "id": uuid4()})
    with client(other) as api:
        assert api.post("/magazine/quick-start", json=body).status_code == 402
    assert setup.events.count("post") == 1


def test_new_request_still_enforces_limit_and_deleted_draft_is_not_recreated(setup):
    body = payload()
    with client() as api:
        assert api.post("/magazine/quick-start", json=body).status_code == 201
        assert api.post("/magazine/quick-start", json=payload()).status_code == 402
        setup.post = None
        assert api.post("/magazine/quick-start", json=body).status_code == 409
    assert setup.events.count("post") == 1
