"""Importing archive pictures (services/magazine/imports.py, routes/library.py,
workers/tasks/cappe_media_import.py, routes/public/stock.py; cappemag03).

What each block pins:

  * queueing: a picture already in (or on its way) comes back as it stands, a
    failed one is queued again, a refused one stays refused;
  * the worker re-checks the license at the archive before downloading — a
    picture no longer offered under a license we can publish is refused, never
    stored; a download that fails is retried, then failed; the Met's web-large
    copy stands in when the original is too big; a stored picture is written
    with its credit, and marked ready, in one transaction;
  * the routes: search hides archive errors behind a 502, marks pictures
    already in the library, signs thumbnails; the daily allowance comes from
    the plan (zero included) and a full day is a 429 that says how many are
    left; polling re-dispatches a stuck import; "stock a topic" skips what is
    already in the library;
  * the thumbnail route serves only links we signed, re-encoded, cached by
    picture.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_stock_imports.py -q
"""
import asyncio
import io
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.routes import library  # noqa: E402
from app.cappe.routes.public import stock as public_stock  # noqa: E402
from app.cappe.services import media  # noqa: E402
from app.cappe.services.magazine import imports, sources  # noqa: E402
from app.cappe.services.magazine.sources import thumbs  # noqa: E402
from app.cappe.services.magazine.sources.base import StockResult  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402

ACCOUNT = SimpleNamespace(id=uuid4(), plan="business", account_type="business")
SITE_ID, POST_ID, ASSET_ID = uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def _import(source="openverse", source_id="abc", status="pending", attempts=0, **over):
    return {"id": uuid4(), "site_id": SITE_ID, "account_id": ACCOUNT.id, "source": source, "source_id": source_id,
            "status": status, "attempts": attempts, "error": None, "asset_id": None, "post_id": None,
            "created_at": NOW, "updated_at": NOW, **over}


def _result(**over):
    base = dict(source="openverse", source_id="abc", title="Harbour at dusk", creator="Ana", license="by",
                license_version="2.0", license_url="https://creativecommons.org/licenses/by/2.0/",
                provider_label="Flickr", landing_url="https://www.flickr.com/photos/x/1",
                image_url="https://live.staticflickr.com/1.jpg", thumb_url="https://api.openverse.org/t/",
                credit_line="“Harbour at dusk” by Ana / CC BY 2.0 via Flickr")
    return StockResult(**{**base, **over})


class TxConn(QueryConn):
    """QueryConn plus `transaction()`, recording which writes ran inside one."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.in_tx = False
        self.tx_writes: list[str] = []

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                conn.in_tx = True

            async def __aexit__(self, *exc):
                conn.in_tx = False
                return False

        return _Tx()

    def _dispatch(self, kind, sql, args):
        if self.in_tx:
            self.tx_writes.append(sql)
        return super()._dispatch(kind, sql, args)


def _jpeg(size=(1600, 1000)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (30, 60, 90)).save(out, "JPEG")
    return out.getvalue()


def _fetched(body=b"", status=200, content_type="image/jpeg", truncated=False):
    return SimpleNamespace(body=body, status=status, content_type=content_type, truncated=truncated)


# ── queueing ─────────────────────────────────────────────────────────────────

def test_enqueue_returns_rows_in_the_order_asked_and_keeps_refusals():
    new = _import(source_id="new")
    refused = _import(source_id="old", status="refused")
    conn = QueryConn(fetch={"INSERT INTO cappe_asset_imports": [new],
                            "FROM cappe_asset_imports WHERE site_id": [refused]})
    rows = run(imports.enqueue(conn, site_id=SITE_ID, account_id=ACCOUNT.id,
                               keys=[("openverse", "old"), ("openverse", "new")]))
    assert [r["source_id"] for r in rows] == ["old", "new"]
    assert rows[0]["status"] == "refused"
    insert = conn.sql_for("fetch")[0]
    assert "WHERE cappe_asset_imports.status = 'failed'" in insert  # a failure is re-queued,
    assert "status = 'ready' AND cappe_asset_imports.asset_id IS NULL" in insert  # and so is a deleted picture
    assert conn.args_for("FROM cappe_asset_imports WHERE site_id")[1:] == (["openverse"], ["old"])


def test_existing_and_statuses():
    assert run(imports.existing(QueryConn(), SITE_ID, [])) == {}
    ready = _import(status="ready", asset_id=ASSET_ID)
    waiting = _import(source_id="zzz")
    conn = QueryConn(fetch={"FROM cappe_asset_imports": [ready, waiting],
                            "FROM cappe_assets": [{"id": ASSET_ID, "variants": '{"960": "x"}'}]})
    out = run(imports.statuses(conn, SITE_ID, [ready["id"], waiting["id"]]))
    assert out[0]["asset"] == {"id": ASSET_ID, "variants": {"960": "x"}} and out[1]["asset"] is None
    assert run(imports.statuses(QueryConn(fetch={"FROM cappe_asset_imports": [waiting]}), SITE_ID,
                                [waiting["id"]]))[0]["asset"] is None


def test_daily_use_and_stuck_and_claim():
    conn = QueryConn(fetchval={"count(*)": 7, "SELECT 1 FROM cappe_asset_imports": 1},
                     fetchrow={"UPDATE cappe_asset_imports SET status = 'working'": None})
    assert run(imports.daily_used(conn, ACCOUNT.id)) == 7
    assert run(imports.stuck(conn, SITE_ID)) is True
    assert run(imports.claim_next(conn, SITE_ID)) is None
    claim = conn.sql_for("fetchrow")[0]
    assert "FOR UPDATE SKIP LOCKED" in claim and "attempts = attempts + 1" in claim
    # A retry waits RETRY_SECONDS: a throttled archive isn't asked three times in a second.
    assert f"updated_at < NOW() - INTERVAL '{imports.RETRY_SECONDS} seconds'" in claim
    assert run(imports.import_next(conn, SITE_ID)) is None


# ── the worker's side ────────────────────────────────────────────────────────

@pytest.fixture
def worker(monkeypatch):
    """Fakes for the archive, the download and storage; returns their logs."""
    state = SimpleNamespace(result=_result(), fetches=[], fetch_plan=None, stored=[], store_error=None)

    async def resolve(source, source_id, *, fresh=False):
        assert fresh, "the worker must re-check the license at the archive"
        if isinstance(state.result, Exception):
            raise state.result
        return state.result

    async def fetch_public(url, **kw):
        state.fetches.append(url)
        plan = state.fetch_plan or [_fetched(_jpeg())]
        step = plan[min(len(state.fetches), len(plan)) - 1]
        if isinstance(step, Exception):
            raise step
        return step

    async def store_processed(image, *, prefix, filename=None):
        if state.store_error:
            raise state.store_error
        state.stored.append((prefix, filename, image.width))
        return media.StoredImage(url="https://cdn.example.test/lib/a.jpg", mime="image/jpeg", width=image.width,
                                 height=image.height, bytes=len(image.data), variants={"960": "x"})

    monkeypatch.setattr(imports.sources, "resolve", resolve)
    monkeypatch.setattr(imports, "fetch_public", fetch_public)
    monkeypatch.setattr(imports.media, "store_processed", store_processed)
    return state


def _worker_conn():
    return TxConn(fetchval={"INSERT INTO cappe_assets": ASSET_ID}, strict_execute=True,
                  execute={"UPDATE cappe_asset_imports": "UPDATE 1"})


def _finished(conn):
    sql = [s for s in conn.sql_for("execute") if "UPDATE cappe_asset_imports" in s][-1]
    return sql, conn.args_for(sql)


def test_a_picture_is_stored_with_its_credit_and_marked_ready_together(worker):
    conn, row = _worker_conn(), _import(attempts=1)
    assert run(imports.import_one(conn, row)) == "ready"
    insert = conn.args_for("INSERT INTO cappe_assets")
    assert "'stock'" in conn.sql_for("fetchval")[0]
    assert insert[3:5] == ("openverse", "abc") and insert[9] == "by"
    assert insert[13] == "“Harbour at dusk” by Ana / CC BY 2.0 via Flickr"
    assert conn.tx_writes and all("cappe_asset" in s for s in conn.tx_writes)
    assert any("status = 'ready'" in s for s in conn.tx_writes)  # in the same transaction as the asset
    assert worker.stored == [("cappe/library", "openverse.jpg", 1600)]
    assert worker.fetches == ["https://live.staticflickr.com/1.jpg"]


@pytest.mark.parametrize("outcome, source", [(None, "openverse"), (_result(), "unsplash")])
def test_a_picture_no_longer_offered_is_refused_and_never_downloaded(worker, outcome, source):
    worker.result = outcome
    conn = _worker_conn()
    assert run(imports.import_one(conn, _import(source=source, attempts=1))) == "refused"
    sql, args = _finished(conn)
    assert args[1:] == ("refused", imports.REFUSED) and worker.fetches == [] and worker.stored == []


@pytest.mark.parametrize("attempts, expected", [(1, "pending"), (imports.MAX_ATTEMPTS, "failed")])
def test_an_archive_that_is_down_is_retried_then_failed(worker, attempts, expected):
    worker.result = sources.SourceError("HTTP 503")
    conn = _worker_conn()
    assert run(imports.import_one(conn, _import(attempts=attempts))) == expected
    assert _finished(conn)[1][1:] == (expected, imports.UNREACHABLE)


@pytest.mark.parametrize("plan", [
    [TimeoutError()],
    [_fetched(status=500)],
    [_fetched(b"<html>", content_type="text/html")],
    [_fetched(b"x", truncated=True)],
])
def test_a_download_that_fails_goes_back_to_the_queue(worker, plan):
    worker.fetch_plan = plan
    conn = _worker_conn()
    assert run(imports.import_one(conn, _import(attempts=1))) == "pending"
    assert worker.stored == []


def test_the_mets_web_large_copy_stands_in_for_an_oversized_original(worker):
    worker.result = _result(source="met", source_id="363984", image_url="https://images.metmuseum.org/orig.jpg",
                            thumb_url="https://images.metmuseum.org/web-large.jpg", license="cc0")
    worker.fetch_plan = [_fetched(b"x" * 10, truncated=True), _fetched(_jpeg((900, 600)), content_type="image/jpg")]
    assert run(imports.import_one(_worker_conn(), _import(source="met", source_id="363984", attempts=1))) == "ready"
    assert worker.fetches == ["https://images.metmuseum.org/orig.jpg", "https://images.metmuseum.org/web-large.jpg"]
    assert worker.stored[0][1:] == ("met.jpg", 900)


def test_a_file_we_cant_read_fails_without_retrying(worker):
    worker.fetch_plan = [_fetched(b"II*\x00", content_type="image/tiff")]
    conn = _worker_conn()
    assert run(imports.import_one(conn, _import(attempts=1))) == "failed"
    assert _finished(conn)[1][1:] == ("failed", imports.UNREADABLE)
    worker.fetch_plan = [_fetched(b"not really a jpeg")]
    conn = _worker_conn()
    assert run(imports.import_one(conn, _import(attempts=1))) == "failed"


def test_a_last_attempt_left_working_by_a_dead_worker_is_failed_not_stranded():
    conn = QueryConn(fetchrow={"UPDATE cappe_asset_imports SET status = 'working'": None})
    run(imports.claim_next(conn, SITE_ID))
    sweep = conn.sql_for("execute")[0]
    assert "SET status = 'failed'" in sweep and "status = 'working' AND attempts >= $2" in sweep
    assert conn.args_for(sweep) == (SITE_ID, imports.MAX_ATTEMPTS, imports.UNREACHABLE)
    assert imports.requeueable(_import(status="failed"))  # so asking again starts it afresh


def test_an_adapters_surprise_fails_that_import_only(worker, monkeypatch):
    # A KeyError from a payload the adapter didn't expect is not "refused"
    # (a refusal is final); it is retried like any other failure.
    worker.result = KeyError("nested")
    row = _import(attempts=1)
    monkeypatch.setattr(imports, "claim_next", AsyncMock(return_value=row))
    conn = _worker_conn()
    assert run(imports.import_next(conn, SITE_ID)) == "pending"
    assert _finished(conn)[1][1:] == ("pending", imports.UNREACHABLE)


def test_the_mets_web_large_copy_stands_in_when_the_original_times_out(worker):
    worker.result = _result(source="met", source_id="1", image_url="https://images.metmuseum.org/orig.jpg",
                            thumb_url="https://images.metmuseum.org/web-large.jpg", license="cc0")
    worker.fetch_plan = [TimeoutError(), _fetched(_jpeg((900, 600)))]
    assert run(imports.import_one(_worker_conn(), _import(source="met", source_id="1", attempts=1))) == "ready"
    assert worker.fetches == ["https://images.metmuseum.org/orig.jpg", "https://images.metmuseum.org/web-large.jpg"]


def test_a_requeued_import_counts_as_a_new_request():
    conn = QueryConn(fetch={"INSERT INTO cappe_asset_imports": [], "FROM cappe_asset_imports WHERE site_id": []})
    run(imports.enqueue(conn, site_id=SITE_ID, account_id=ACCOUNT.id, keys=[("openverse", "a")]))
    upsert = conn.sql_for("fetch")[0]
    assert "created_at = NOW()" in upsert.split("DO UPDATE", 1)[1]  # daily_used counts by created_at


def test_a_storage_hiccup_is_retried(worker):
    worker.store_error = RuntimeError("s3")
    conn = _worker_conn()
    assert run(imports.import_one(conn, _import(attempts=1))) == "pending"
    assert conn.tx_writes == []


def test_the_worker_works_the_queue_until_empty_and_closes_its_connection(monkeypatch):
    from app.workers.celery_app import celery_app
    from app.workers.tasks import cappe_media_import as task

    assert "app.workers.tasks.cappe_media_import" in celery_app.conf.include
    conn = SimpleNamespace(close=AsyncMock())
    outcomes = iter(["ready", "ready", "refused", None])

    async def get_db_connection():
        return conn

    async def import_next(c, site_id):
        assert c is conn and site_id == "site-1"
        return next(outcomes)

    monkeypatch.setattr(task, "get_db_connection", get_db_connection)
    monkeypatch.setattr(task.imports, "import_next", import_next)
    assert task.run_cappe_media_import("site-1") == {"status": "success", "ready": 2, "refused": 1}
    conn.close.assert_awaited_once()

    async def boom(c, site_id):
        raise RuntimeError("db gone")

    monkeypatch.setattr(task.imports, "import_next", boom)
    with pytest.raises(RuntimeError):
        task.run_cappe_media_import("site-1")
    assert conn.close.await_count == 2


# ── the routes ───────────────────────────────────────────────────────────────

@pytest.fixture
def routes(monkeypatch):
    state = SimpleNamespace(dispatched=[], features={"stock_imports_per_day": 300}, conn=None)

    async def no_limit(*a, **k):
        return None

    async def entitlements(plan, *, conn=None):
        return SimpleNamespace(features=state.features)

    monkeypatch.setattr(library, "check_rate_limit", no_limit)
    monkeypatch.setattr(library, "resolve_entitlements", entitlements)
    monkeypatch.setattr(library, "_dispatch", lambda site_id: state.dispatched.append(site_id))
    monkeypatch.setattr(library, "get_connection", lambda *a, **k: state.conn)
    return state


def _client():
    return route_client(library.router, overrides={library.require_cappe_account: ACCOUNT})


def _site_conn(**tables):
    fetchrow = {"FROM cappe_sites": {"id": SITE_ID, "account_id": ACCOUNT.id}}
    fetchrow.update(tables.pop("fetchrow", {}))
    return TxConn(fetchrow=fetchrow, **tables)


def test_search_marks_what_is_already_in_and_signs_thumbnails(monkeypatch, routes):
    async def search(source, q, page):
        assert (source, q, page) == ("openverse", "harbor", 2)
        return [_result(), _result(source_id="def")], True

    monkeypatch.setattr(library.sources, "search_page", search)
    routes.conn = _site_conn(fetch={"FROM cappe_assets": [{"source": "openverse", "source_id": "def"}]})
    with _client() as client:
        res = client.get(f"/sites/{SITE_ID}/library/search", params={"source": "openverse", "q": "harbor", "page": 2})
    assert res.status_code == 200, res.text
    body = res.json()
    assert [r["imported"] for r in body["results"]] == [False, True] and body["has_more"] is True
    token = body["results"][0]["thumb"].rsplit("/", 1)[1]
    assert thumbs.verify(token) == "https://api.openverse.org/t/"
    assert "image_url" not in body["results"][0]  # the archive's file address stays server-side


def test_a_page_with_nothing_publishable_isnt_the_last(monkeypatch, routes):
    async def search(source, q, page):
        return [], True  # The Met: every hit on this page is copyrighted

    monkeypatch.setattr(library.sources, "search_page", search)
    routes.conn = _site_conn(fetch={"FROM cappe_assets": []})
    with _client() as client:
        body = client.get(f"/sites/{SITE_ID}/library/search", params={"source": "met", "q": "harbor"}).json()
    assert body["results"] == [] and body["has_more"] is True


def test_the_allowance_is_counted_under_a_per_account_lock(routes):
    routes.conn = _import_conn(used=10, queued=[_import(source_id="a")])
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/import", json={"items": [{"source": "openverse",
                                                                               "source_id": "a"}]})
    assert res.status_code == 202, res.text
    tx = routes.conn.tx_writes
    assert "pg_advisory_xact_lock" in tx[0] and routes.conn.args_for(tx[0]) == (f"cappe_stock_import:{ACCOUNT.id}",)
    assert any("count(*)" in q for q in tx) and any("INSERT INTO cappe_asset_imports" in q for q in tx)


def test_search_errors(monkeypatch, routes):
    async def down(source, q, page):
        raise sources.SourceError("HTTP 503")

    monkeypatch.setattr(library.sources, "search_page", down)
    routes.conn = _site_conn()
    with _client() as client:
        assert client.get(f"/sites/{SITE_ID}/library/search",
                          params={"source": "met", "q": "x"}).status_code == 502
        assert client.get(f"/sites/{SITE_ID}/library/search",
                          params={"source": "unsplash", "q": "x"}).status_code == 422
    routes.conn = QueryConn(fetchrow={"FROM cappe_sites": None})
    with _client() as client:
        assert client.get(f"/sites/{SITE_ID}/library/search",
                          params={"source": "met", "q": "x"}).status_code == 404


def _import_conn(used=0, existing=(), queued=None, post_ok=True):
    return _site_conn(
        fetchval={"count(*)": used, "FROM cappe_posts": 1 if post_ok else None},
        fetch={"INSERT INTO cappe_asset_imports": queued if queued is not None else [],
               "FROM cappe_asset_imports WHERE site_id": list(existing)},
    )


def test_import_queues_and_dispatches(routes):
    rows = [_import(source_id="a"), _import(source_id="b")]
    routes.conn = _import_conn(used=10, queued=rows)
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/import", json={
            "items": [{"source": "openverse", "source_id": "a"}, {"source": "openverse", "source_id": "b"},
                      {"source": "openverse", "source_id": "a"}], "post_id": str(POST_ID)})
    assert res.status_code == 202, res.text
    assert [i["status"] for i in res.json()["imports"]] == ["pending", "pending"]
    assert res.json()["remaining_today"] == 288
    assert routes.dispatched == [SITE_ID]
    assert routes.conn.args_for("INSERT INTO cappe_asset_imports")[2:] == (["openverse", "openverse"], ["a", "b"],
                                                                          POST_ID)


def test_pictures_already_in_dont_count_against_the_day_and_dont_dispatch(routes):
    ready = _import(source_id="a", status="ready", asset_id=ASSET_ID)
    routes.features = {"stock_imports_per_day": 1}
    routes.conn = _import_conn(used=1, existing=[ready])
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/import", json={"items": [{"source": "openverse",
                                                                               "source_id": "a"}]})
    assert res.status_code == 202 and res.json()["imports"][0]["status"] == "ready"
    assert routes.dispatched == []


def test_a_picture_deleted_from_the_library_can_be_imported_again():
    assert imports.requeueable(_import(status="ready", asset_id=None))
    assert imports.requeueable(_import(status="failed"))
    assert not imports.requeueable(_import(status="ready", asset_id=ASSET_ID))
    assert not imports.requeueable(_import(status="refused"))
    assert not imports.requeueable(_import(status="working"))


def test_a_deleted_picture_counts_against_the_day_when_imported_again(routes):
    deleted = _import(source_id="a", status="ready", asset_id=None)
    routes.features = {"stock_imports_per_day": 1}
    routes.conn = _import_conn(used=1, existing=[deleted])
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/import", json={"items": [{"source": "openverse",
                                                                               "source_id": "a"}]})
    assert res.status_code == 429


@pytest.mark.parametrize("features, used, left", [
    ({"stock_imports_per_day": 25}, 24, "1 more picture today"),
    ({"stock_imports_per_day": 0}, 0, "0 more pictures today"),
    ({}, 25, "0 more pictures today (your plan allows 25 a day)"),
])
def test_a_full_day_is_a_429_that_says_whats_left(routes, features, used, left):
    routes.features = features
    failed = _import(source_id="b", status="failed")
    routes.conn = _import_conn(used=used, existing=[failed])
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/import", json={"items": [
            {"source": "nasa", "source_id": "a"}, {"source": "openverse", "source_id": "b"}]})
    assert res.status_code == 429 and left in res.json()["detail"]
    assert routes.dispatched == []


def test_import_into_another_sites_story_is_refused(routes):
    routes.conn = _import_conn(post_ok=False)
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/import", json={
            "items": [{"source": "openverse", "source_id": "a"}], "post_id": str(POST_ID)})
    assert res.status_code == 422


def test_polling_reports_status_and_re_dispatches_a_stuck_import(routes):
    waiting = _import(status="working")
    routes.conn = _site_conn(fetch={"FROM cappe_asset_imports": [waiting]},
                             fetchval={"SELECT 1 FROM cappe_asset_imports": 1})
    with _client() as client:
        res = client.get(f"/sites/{SITE_ID}/library/imports", params={"ids": f"{waiting['id']},"})
        assert res.status_code == 200 and res.json()["imports"][0]["status"] == "working"
        assert routes.dispatched == [SITE_ID]
        assert client.get(f"/sites/{SITE_ID}/library/imports", params={"ids": "nope"}).status_code == 422
    done = _import(status="ready")
    routes.dispatched.clear()
    routes.conn = _site_conn(fetch={"FROM cappe_asset_imports": [done]})
    with _client() as client:
        assert client.get(f"/sites/{SITE_ID}/library/imports", params={"ids": str(done["id"])}).status_code == 200
    assert routes.dispatched == []  # nothing waiting: no stuck check, no dispatch


def test_stocking_a_topic_skips_whats_in_and_falls_through_sources(monkeypatch, routes):
    asked = []

    async def search(source, q, page):
        asked.append(source)
        if source == "smithsonian":
            raise sources.SourceError("down")
        return [_result(source=source, source_id=f"{source}-{i}") for i in range(3)]

    monkeypatch.setattr(library.sources, "search", search)
    monkeypatch.setattr(library, "TOPIC_QUERIES", {"travel": [("smithsonian", "x"), ("openverse", "y"),
                                                              ("nasa", "z")]})
    queued = [_import(source_id="openverse-1"), _import(source_id="openverse-2")]
    routes.conn = _import_conn(queued=queued)
    routes.conn.set("fetch", "FROM cappe_assets", [{"source": "openverse", "source_id": "openverse-0"}])
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/stock-topic", json={"topic": "travel", "count": 2})
        assert res.status_code == 202, res.text
        assert asked == ["smithsonian", "openverse", "nasa"]  # 3 found < 2×2, so it kept going
        assert routes.conn.args_for("INSERT INTO cappe_asset_imports")[3] == ["openverse-1", "openverse-2"]
        assert client.post(f"/sites/{SITE_ID}/library/stock-topic", json={"topic": "astrology"}).status_code == 422


def test_stocking_a_topic_when_every_archive_is_down(monkeypatch, routes):
    async def down(source, q, page):
        raise sources.SourceError("down")

    monkeypatch.setattr(library.sources, "search", down)
    routes.conn = _site_conn(fetch={"FROM cappe_assets": []})
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/stock-topic", json={"topic": "science"})
    assert res.status_code == 502


def test_stocking_a_topic_already_stocked_says_so_not_that_archives_are_down(monkeypatch, routes):
    async def search(source, q, page):
        return [_result(source=source, source_id="x")]

    monkeypatch.setattr(library.sources, "search", search)
    routes.conn = _site_conn(fetch={"FROM cappe_assets": [{"source": s, "source_id": "x"}
                                                          for s in ("openverse", "smithsonian", "met", "nasa")]})
    with _client() as client:
        res = client.post(f"/sites/{SITE_ID}/library/stock-topic", json={"topic": "science"})
    assert res.status_code == 409 and "already in your library" in res.json()["detail"]


def test_every_topic_has_set_searches():
    from app.cappe.services.magazine.topics import TOPIC_QUERIES, TOPICS

    assert set(TOPIC_QUERIES) == set(TOPICS)
    for queries in TOPIC_QUERIES.values():
        assert queries and all(src in sources.SOURCES and q for src, q in queries)


def test_dispatch_never_fails_the_request(monkeypatch):
    from app.workers.tasks import cappe_media_import as task

    calls = []
    monkeypatch.setattr(task.run_cappe_media_import, "delay", lambda site_id: calls.append(site_id))
    library._dispatch(SITE_ID)
    assert calls == [str(SITE_ID)]

    def broker_down(site_id):
        raise ConnectionError

    monkeypatch.setattr(task.run_cappe_media_import, "delay", broker_down)
    library._dispatch(SITE_ID)  # logged, not raised


# ── the public thumbnail ─────────────────────────────────────────────────────

@pytest.fixture
def thumb_route(monkeypatch):
    state = SimpleNamespace(fetches=[], cache={}, fetched=_fetched(_jpeg()))

    async def no_limit(*a, **k):
        return None

    async def fetch_public(url, **kw):
        state.fetches.append(url)
        if isinstance(state.fetched, Exception):
            raise state.fetched
        return state.fetched

    async def cache_get(_r, key):
        return state.cache.get(key)

    async def cache_set(_r, key, value, ttl):
        state.cache[key] = value

    monkeypatch.setattr(public_stock, "check_rate_limit", no_limit)
    monkeypatch.setattr(public_stock, "fetch_public", fetch_public)
    monkeypatch.setattr(public_stock, "get_redis_cache", lambda: object())
    monkeypatch.setattr(public_stock, "cache_get", cache_get)
    monkeypatch.setattr(public_stock, "cache_set", cache_set)
    return state


def test_a_signed_thumbnail_is_served_small_and_cached_by_picture(thumb_route):
    url = "https://images-assets.nasa.gov/image/a/a~small.jpg"
    with route_client(public_stock.router) as client:
        first = client.get(f"/public/stock-thumbs/{thumbs.sign(url)}")
        assert first.status_code == 200 and first.headers["content-type"] == "image/webp"
        with Image.open(io.BytesIO(first.content)) as img:
            assert max(img.size) == thumbs.THUMB_SIDE
        again = client.get(f"/public/stock-thumbs/{thumbs.sign(url, now=time.time() - 60)}")  # another token
        assert again.status_code == 200 and again.content == first.content
    assert thumb_route.fetches == [url]


@pytest.mark.parametrize("fetched", [TimeoutError(), _fetched(status=404), _fetched(b"<html>", content_type="text/html"),
                                     _fetched(b"not an image")])
def test_a_thumbnail_the_archive_wont_give_is_a_502(thumb_route, fetched):
    thumb_route.fetched = fetched
    with route_client(public_stock.router) as client:
        assert client.get(f"/public/stock-thumbs/{thumbs.sign('https://x.test/a.jpg')}").status_code == 502


def test_only_our_links_are_fetched(thumb_route):
    with route_client(public_stock.router) as client:
        assert client.get("/public/stock-thumbs/aHR0cHM6Ly9ldmlsLnRlc3Q.forged").status_code == 404
    assert thumb_route.fetches == []
