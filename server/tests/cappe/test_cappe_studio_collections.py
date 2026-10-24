"""Editorial libraries: portable documents, account ownership, bounded saves.

All persistence uses a fake connection; no migration or database is touched.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.cappe.routes import studio
from app.cappe.services.magazine.studio import collections as C
from app.cappe.services.magazine.studio.schema import DocError, starter_doc
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_routes import ACCOUNT, Conn, Ctx

ID = uuid4()
NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)
CARD = {"id": ID, "name": "Quiet mornings", "page_count": 2, "created_at": NOW}


def client_for(monkeypatch, conn):
    monkeypatch.setattr(studio, "get_connection", lambda: Ctx(conn))
    return route_client(studio.router, overrides={studio.require_cappe_account: ACCOUNT})


def test_portable_layout_retains_words_guides_and_geometry_without_photo_or_access_references():
    doc = starter_doc()
    doc["items"].append({"id": "i1", "kind": "image", "page": "p1", "x": 10, "y": 20, "w": 200, "h": 300,
                         "asset_id": str(uuid4()), "caption": "Private photo", "fx": 25, "zoom": 200})
    doc["threads"][0]["paras"] = [{"runs": [{"t": "東京 — a new direction 📷", "font": "Bodoni Moda", "size": 40}]}]
    doc["threads"][0]["comp"] = {"lines": []}
    doc["guides"] = [{"id": "g1", "page": "p1", "axis": "v", "at": 54}]
    doc["paywall_page"] = 2
    out = C.collection_doc(doc)
    assert out["paywall_page"] is None
    assert out["items"][-1]["asset_id"] is None and out["items"][-1]["caption"] == ""
    assert out["items"][-1]["x"] == 10 and out["items"][-1]["zoom"] == 200
    assert out["threads"][0]["paras"][0]["runs"][0]["t"] == "東京 — a new direction 📷"
    assert "comp" not in out["threads"][0]
    assert out["guides"] == doc["guides"]
    assert doc["items"][-1]["asset_id"] and doc["paywall_page"] == 2  # no mutation


@pytest.mark.parametrize("pages", [1, C.MAX_COLLECTION_PAGES])
def test_page_boundaries(pages):
    doc = starter_doc()
    doc["pages"] = [{"id": f"p{k + 1}"} for k in range(pages)]
    doc["items"], doc["threads"] = [], []
    assert len(C.collection_doc(doc)["pages"]) == pages


@pytest.mark.parametrize("change, message", [
    ({"pages": []}, "at least one page"),
    ({"pages": [{"id": "p1"}] * 33}, "at most 32 pages"),
    ({"padding": "é" * 200_000}, "too big to save"),
    ({"items": [{"id": "t3", "kind": "text", "page": "missing"}]}, "isn't in the story"),
    ({"threads": [{"id": "s1", "frames": ["missing"]}]}, "isn't a text frame"),
    ({"items": [{"id": "g1", "kind": "graphic", "page": "p1", "src": "a" * 64}]}, "isn't one the Studio has"),
])
def test_invalid_or_oversized_collections_are_refused(change, message):
    with pytest.raises(DocError, match=message):
        C.collection_doc({**starter_doc(), **change})


def test_a_collection_can_keep_a_hidden_curated_graphic():
    sha = "a" * 64
    doc = starter_doc()
    doc["items"].append({"id": "g1", "kind": "graphic", "page": "p1", "src": sha, "color": "#ff0000"})
    out = C.collection_doc(doc, {sha: {"sha": sha, "mono": True, "fit": "contain"}})
    assert out["items"][-1]["src"] == sha


def test_list_fetches_only_this_accounts_small_cards(monkeypatch):
    conn = Conn(fetch={"FROM cappe_studio_collections": [CARD]})
    with client_for(monkeypatch, conn) as client:
        res = client.get("/studio/collections")
    assert res.status_code == 200 and res.json()[0]["name"] == CARD["name"]
    assert conn.args_for("FROM cappe_studio_collections") == (ACCOUNT.id, C.MAX_COLLECTIONS)
    assert "doc" not in res.json()[0]
    assert "WHERE account_id = $1" in conn.sql_for("fetch")[0]


@pytest.mark.parametrize("found", [True, False])
def test_open_scopes_a_collection_by_owner(monkeypatch, found):
    conn = Conn(fetchrow={"FROM cappe_studio_collections": {**CARD, "doc": json.dumps(starter_doc())} if found else None})
    with client_for(monkeypatch, conn) as client:
        res = client.get(f"/studio/collections/{ID}")
    assert res.status_code == (200 if found else 404)
    assert conn.args_for("FROM cappe_studio_collections") == (ID, ACCOUNT.id)
    assert "AND account_id = $2" in conn.sql_for("fetchrow")[0]
    if found:
        assert isinstance(res.json()["doc"], dict)


def test_save_validates_normalizes_and_locks_the_account_before_inserting(monkeypatch):
    conn = Conn(fetchval={"FROM cappe_accounts": ACCOUNT.id, "SELECT count(*)": 0},
                fetchrow={"INSERT INTO cappe_studio_collections": CARD})
    doc = starter_doc()
    with client_for(monkeypatch, conn) as client:
        res = client.post("/studio/collections", json={"name": " Quiet mornings ", "doc": doc})
    assert res.status_code == 201, res.text
    args = conn.args_for("INSERT INTO cappe_studio_collections")
    assert args[:2] == (ACCOUNT.id, "Quiet mornings")
    assert json.loads(args[2]) == C.collection_doc(doc) and args[3] == 2
    queries = [sql for _, sql, _ in conn.calls]
    assert "FOR UPDATE" in queries[0] and "count(*)" in queries[1] and "INSERT" in queries[2]


def test_save_resolves_custom_bank_graphics(monkeypatch):
    sha = "a" * 64
    doc = starter_doc()
    doc["items"].append({"id": "g1", "kind": "graphic", "page": "p1", "src": sha})
    conn = Conn(fetch={"FROM cappe_studio_bank": [{"sha": sha, "mono": False, "fit": "contain"}]},
                fetchval={"FROM cappe_accounts": ACCOUNT.id, "SELECT count(*)": 0},
                fetchrow={"INSERT INTO cappe_studio_collections": CARD})
    with client_for(monkeypatch, conn) as client:
        res = client.post("/studio/collections", json={"name": "Graphics", "doc": doc})
    assert res.status_code == 201
    assert json.loads(conn.args_for("INSERT INTO cappe_studio_collections")[2])["items"][-1]["color"] is None


def test_full_library_refuses_without_writing(monkeypatch):
    conn = Conn(fetchval={"FROM cappe_accounts": ACCOUNT.id, "SELECT count(*)": C.MAX_COLLECTIONS})
    with client_for(monkeypatch, conn) as client:
        res = client.post("/studio/collections", json={"name": "Another", "doc": starter_doc()})
    assert res.status_code == 409 and "50 collections" in res.text
    assert not any("INSERT" in sql for _, sql, _ in conn.calls)


@pytest.mark.parametrize("name,doc", [("   ", None), ("a" * 81, None), ("bad\nname", None), ("OK", {"pages": []}),
                                      ("OK", {"padding": "x" * 1_000_001})])
def test_bad_save_never_writes(monkeypatch, name, doc):
    conn = Conn()
    with client_for(monkeypatch, conn) as client:
        res = client.post("/studio/collections", json={"name": name, "doc": doc or starter_doc()})
    assert res.status_code == 422
    assert not conn.calls


@pytest.mark.parametrize("found", [True, False])
def test_delete_is_owner_scoped_and_never_touches_story_pages(monkeypatch, found):
    conn = Conn(fetchval={"DELETE FROM cappe_studio_collections": ID if found else None})
    with client_for(monkeypatch, conn) as client:
        res = client.delete(f"/studio/collections/{ID}")
    assert res.status_code == (204 if found else 404)
    assert conn.args_for("DELETE FROM cappe_studio_collections") == (ID, ACCOUNT.id)
    assert len(conn.calls) == 1 and "AND account_id = $2" in conn.calls[0][1]


def test_collection_routes_require_a_cappe_session():
    with route_client(studio.router) as client:
        assert client.get("/studio/collections").status_code == 401
