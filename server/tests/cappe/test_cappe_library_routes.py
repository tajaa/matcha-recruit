"""The image library over HTTP (routes/uploads.py, migration cappemag01).

What each block pins:

  * the editor's quick upload and the creator upload store a re-encoded image
    — a phone photo's GPS position never reaches the CDN;
  * the library upload needs the owner's "I took this or may use it", stores
    the responsive sizes, and credits an AI-made picture as AI;
  * alt text and captions are editable on any picture, the credit only on the
    owner's own uploads; another site's picture is a 404;
  * the list searches and filters by kind, stock included.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_library_routes.py -q
"""
import io
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from app.cappe.routes import creators, uploads  # noqa: E402
from app.cappe.services import media  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402

ACCOUNT = SimpleNamespace(id=uuid4(), plan="business", account_type="business")
SITE_ID, ASSET_ID = uuid4(), uuid4()
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
GPS_IFD = 0x8825


def _photo(size=(1200, 800)) -> bytes:
    exif = Image.Exif()
    exif.get_ifd(GPS_IFD)[2] = (37.0, 46.0, 30.0)
    out = io.BytesIO()
    Image.new("RGB", size, (40, 90, 160)).save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


def _asset(**overrides):
    base = {
        "id": ASSET_ID, "kind": "upload", "url": "https://cdn.example.test/a.jpg", "prompt": None,
        "aspect": None, "image_size": None, "created_at": NOW, "variants": "{}", "ai_generated": False,
        "moderation": "unchecked",
    }
    return {**base, **overrides}


class Storage:
    def __init__(self):
        self.files = []

    async def upload_file(self, *, file_bytes, filename, prefix, content_type):
        self.files.append({"bytes": file_bytes, "filename": filename, "prefix": prefix, "type": content_type})
        return f"https://cdn.example.test/{prefix}/{len(self.files)}-{filename}"


@pytest.fixture
def storage(monkeypatch):
    store = Storage()
    monkeypatch.setattr(uploads, "get_storage", lambda: store)
    monkeypatch.setattr(media, "get_storage", lambda: store)
    return store


def _client(monkeypatch, conn):
    monkeypatch.setattr(uploads, "get_connection", lambda *a, **k: conn)
    return route_client(uploads.router, overrides={uploads.require_cappe_account: ACCOUNT})


def _site_conn(**tables) -> QueryConn:
    fetchrow = {"FROM cappe_sites": {"id": SITE_ID, "account_id": ACCOUNT.id}}
    fetchrow.update(tables.pop("fetchrow", {}))
    return QueryConn(fetchrow=fetchrow, **tables)


def _has_gps(data: bytes) -> bool:
    with Image.open(io.BytesIO(data)) as img:
        return bool(img.getexif().get_ifd(GPS_IFD))


def test_the_editor_upload_stores_the_photo_without_its_position(monkeypatch, storage):
    conn = _site_conn()
    with _client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE_ID}/upload", files={"file": ("IMG_0001.jpg", _photo(), "image/jpeg")})
    assert res.status_code == 200, res.text
    stored = storage.files[0]
    assert stored["filename"] == "IMG_0001.jpg" and stored["type"] == "image/jpeg"
    assert not _has_gps(stored["bytes"])
    # the catalog row knows the stored size
    args = conn.args_for("INSERT INTO cappe_assets")
    assert args[-4:] == (1200, 800, len(stored["bytes"]), "image/jpeg")


def test_a_broken_catalog_insert_never_fails_the_editor_upload(monkeypatch, storage):
    async def broken(*_a, **_k):
        raise RuntimeError("catalog down")

    monkeypatch.setattr(uploads.cappe_assets, "record", broken)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/upload", files={"file": ("a.jpg", _photo((40, 40)), "image/jpeg")})
    assert res.status_code == 200
    assert res.json()["url"].startswith("https://cdn.example.test/cappe/")


def test_the_editor_upload_refuses_bytes_that_only_look_like_an_image(monkeypatch, storage):
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/upload",
                          files={"file": ("x.jpg", b"\xff\xd8\xff not a jpeg", "image/jpeg")})
    assert res.status_code == 400
    assert storage.files == []


def test_a_library_upload_needs_the_owners_permission(monkeypatch, storage):
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(
            f"/sites/{SITE_ID}/assets/upload",
            files={"file": ("a.jpg", _photo(), "image/jpeg")}, data={"rights_attested": "false"},
        )
    assert res.status_code == 422
    assert "permission" in res.json()["detail"]
    assert storage.files == []


def test_a_library_upload_stores_the_sizes_and_what_is_printed_beside_it(monkeypatch, storage):
    conn = _site_conn(fetchrow={"INSERT INTO cappe_assets": _asset(credit_line="Photo: Ana Ruiz", alt="Boats")})
    with _client(monkeypatch, conn) as client:
        res = client.post(
            f"/sites/{SITE_ID}/assets/upload",
            files={"file": ("harbour.jpg", _photo(), "image/jpeg")},
            data={"rights_attested": "true", "alt": " Boats ", "credit_line": "Photo: Ana Ruiz", "caption": ""},
        )
    assert res.status_code == 201, res.text
    assert res.json()["credit_line"] == "Photo: Ana Ruiz"
    assert [f["prefix"] for f in storage.files] == ["cappe/library"] * len(storage.files)
    assert [f["type"] for f in storage.files].count("image/webp") == 3  # 480, 960, 1200
    assert not any(_has_gps(f["bytes"]) for f in storage.files if f["type"] == "image/jpeg")
    args = conn.args_for("INSERT INTO cappe_assets")
    assert args[3:9] == ("own", False, "Photo: Ana Ruiz", "Boats", None, 1200)
    assert '"webp"' in args[-1] and '"share"' in args[-1]


def test_an_ai_made_library_upload_is_credited_as_ai(monkeypatch, storage):
    conn = _site_conn(fetchrow={"INSERT INTO cappe_assets": _asset(ai_generated=True, credit_line="AI illustration")})
    with _client(monkeypatch, conn) as client:
        res = client.post(
            f"/sites/{SITE_ID}/assets/upload",
            files={"file": ("art.png", _photo((300, 300)), "image/jpeg")},
            data={"rights_attested": "true", "ai_made": "true", "credit_line": "Photo: me"},
        )
    assert res.status_code == 201, res.text
    assert conn.args_for("INSERT INTO cappe_assets")[3:6] == ("ai", True, "AI illustration")


def test_a_library_upload_of_a_non_image_type_is_refused(monkeypatch, storage):
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(
            f"/sites/{SITE_ID}/assets/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")}, data={"rights_attested": "true"},
        )
    assert res.status_code == 400


def test_another_accounts_site_is_a_404(monkeypatch, storage):
    conn = QueryConn(fetchrow={"FROM cappe_sites": None})
    with _client(monkeypatch, conn) as client:
        assert client.get(f"/sites/{SITE_ID}/assets").status_code == 404
        assert client.patch(f"/sites/{SITE_ID}/assets/{ASSET_ID}", json={"alt": "x"}).status_code == 404


def test_the_list_filters_by_kind_and_searches(monkeypatch):
    conn = _site_conn(fetch={"FROM cappe_assets": [_asset(kind="stock", source="openverse", license="by",
                                                          credit_line="Photo: Ana / CC BY 2.0")]})
    with _client(monkeypatch, conn) as client:
        res = client.get(f"/sites/{SITE_ID}/assets?kind=stock&q=harbour")
        assert client.get(f"/sites/{SITE_ID}/assets?kind=bogus").status_code == 422
    assert res.status_code == 200
    asset = res.json()["assets"][0]
    assert asset["kind"] == "stock" and asset["credit_line"] == "Photo: Ana / CC BY 2.0"
    assert conn.args_for("FROM cappe_assets") == (SITE_ID, "stock", "%harbour%", 200)


def test_alt_text_on_an_archive_picture_is_editable(monkeypatch):
    conn = _site_conn(fetchrow={
        "SELECT id, kind": _asset(kind="stock"),
        "UPDATE cappe_assets": _asset(kind="stock", alt="Fishing boats at dawn"),
    })
    cleared = []

    async def invalidate(site_id):
        cleared.append(site_id)

    monkeypatch.setattr(uploads, "invalidate_site_render_cache", invalidate)
    with _client(monkeypatch, conn) as client:
        res = client.patch(f"/sites/{SITE_ID}/assets/{ASSET_ID}", json={"alt": "Fishing boats at dawn"})
    assert res.status_code == 200, res.text
    assert res.json()["alt"] == "Fishing boats at dawn"
    # Story pages print the alt text and credit: their cached copies go.
    assert cleared == [SITE_ID]


def test_the_credit_of_an_archive_picture_is_not_editable(monkeypatch):
    conn = _site_conn(fetchrow={"SELECT id, kind": _asset(kind="stock")})
    with _client(monkeypatch, conn) as client:
        res = client.patch(f"/sites/{SITE_ID}/assets/{ASSET_ID}", json={"credit_line": "Photo: me"})
    assert res.status_code == 422
    assert not conn.sql_for("execute") and not any("UPDATE" in s for s in conn.sql_for("fetchrow"))


def test_editing_a_missing_picture_is_a_404(monkeypatch):
    conn = _site_conn(fetchrow={"SELECT id, kind": None})
    with _client(monkeypatch, conn) as client:
        assert client.patch(f"/sites/{SITE_ID}/assets/{ASSET_ID}", json={"alt": "x"}).status_code == 404


def test_a_picture_deleted_between_read_and_write_is_a_404(monkeypatch):
    conn = _site_conn(fetchrow={"SELECT id, kind": _asset(), "UPDATE cappe_assets": None})
    with _client(monkeypatch, conn) as client:
        assert client.patch(f"/sites/{SITE_ID}/assets/{ASSET_ID}", json={"alt": "x"}).status_code == 404


def test_a_creator_photo_is_stored_without_its_position(monkeypatch, storage):
    monkeypatch.setattr(creators, "get_storage", lambda: storage)

    async def no_limit(*_a, **_k):
        return None

    monkeypatch.setattr(creators, "check_rate_limit", no_limit)
    creator = SimpleNamespace(id=uuid4(), plan="creator", account_type="creator")
    with route_client(creators.router, overrides={creators.require_cappe_account: creator}) as client:
        res = client.post("/creators/me/upload", files={"file": ("me.jpg", _photo(), "image/jpeg")})
    assert res.status_code == 200, res.text
    assert not _has_gps(storage.files[0]["bytes"])


def test_a_creator_upload_that_is_not_an_image_is_refused(monkeypatch, storage):
    monkeypatch.setattr(creators, "get_storage", lambda: storage)

    async def no_limit(*_a, **_k):
        return None

    monkeypatch.setattr(creators, "check_rate_limit", no_limit)
    creator = SimpleNamespace(id=uuid4(), plan="creator", account_type="creator")
    with route_client(creators.router, overrides={creators.require_cappe_account: creator}) as client:
        res = client.post("/creators/me/upload",
                          files={"file": ("me.jpg", b"\xff\xd8\xff not a jpeg", "image/jpeg")})
    assert res.status_code == 400
    assert storage.files == []
