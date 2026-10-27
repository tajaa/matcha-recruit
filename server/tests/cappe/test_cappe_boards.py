"""Mood boards (`services/boards/`, `routes/boards.py`, migration cappeboard01).

What each block pins:

  * a pin's files are private: stored with `upload_private_file`, answered as
    signed links, never as a storage path or a public CDN address;
  * a signed link is the permission: forged or expired tokens are 404, a
    picture streams from our origin, a document redirects to S3 under its own
    name;
  * a photo or screenshot loses its metadata before it is stored;
  * a pasted link becomes a card with its page's title and picture, a link
    straight to a picture becomes a photo pin, and a failed fetch is still a
    card named by its host;
  * boards and pins are the site owner's alone (another site is a 404), and
    the board/pin/storage limits are refused with the files cleaned up;
  * a pinned picture reaches the library only with the owner's "I may use this";
  * the bounds are mirrored by the client (`client/src/cappe/boards/limits.ts`).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_boards.py -q
"""
import io
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models import boards as models  # noqa: E402
from app.cappe.routes import boards as routes  # noqa: E402
from app.cappe.routes.public import board_files as public_files  # noqa: E402
from app.cappe.services import media  # noqa: E402
from app.cappe.services.boards import files, limits, links, store  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402

ACCOUNT = SimpleNamespace(id=uuid4(), plan="writer", account_type="writer")
SITE_ID, BOARD_ID, PIN_ID, ASSET_ID = uuid4(), uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
GPS_IFD = 0x8825
ROOT = Path(__file__).resolve().parents[3]


def _photo(size=(1200, 800), fmt="JPEG") -> bytes:
    exif = Image.Exif()
    exif.get_ifd(GPS_IFD)[2] = (37.0, 46.0, 30.0)
    out = io.BytesIO()
    Image.new("RGB", size, (40, 90, 160)).save(out, fmt, exif=exif.tobytes())
    return out.getvalue()


def _pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((40, 60), "Spring issue mood")
    data = doc.tobytes()
    doc.close()
    return data


class Storage:
    """The private bucket, in memory."""

    def __init__(self):
        self.files: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.public: list[str] = []
        self.presigned: list[tuple[str, str]] = []

    async def upload_private_file(self, file_bytes, filename, prefix="documents", content_type=None, bucket=None):
        path = f"s3://private-bucket/{prefix}/{len(self.files)}-{filename}"
        self.files[path] = (file_bytes, content_type)
        return path

    async def upload_file(self, *, file_bytes, filename, prefix, content_type):
        url = f"https://cdn.example.test/{prefix}/{len(self.public)}-{filename}"
        self.public.append(url)
        return url

    async def download_file(self, path):
        if path not in self.files:
            raise RuntimeError("Failed to download from S3")
        return self.files[path][0]

    async def delete_private_file(self, path):
        self.deleted.append(path)
        return self.files.pop(path, None) is not None

    def get_presigned_download_url(self, path, expires_in=900, *, disposition=None):
        self.presigned.append((path, disposition))
        return f"https://private-bucket.s3.example.test/{path[5:]}?sig=1" if path in self.files else None


@pytest.fixture
def storage(monkeypatch):
    fake = Storage()
    for module in (files, routes, public_files, media):
        monkeypatch.setattr(module, "get_storage", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def no_limits(monkeypatch):
    async def _no_limit(*_a, **_k):
        return None

    monkeypatch.setattr(routes, "check_rate_limit", _no_limit)
    monkeypatch.setattr(public_files, "check_rate_limit", _no_limit)


def _board(**over):
    return {"id": BOARD_ID, "title": "Spring issue", "created_at": NOW, "updated_at": NOW, **over}


def _pin_row(**over):
    base = {
        "id": PIN_ID, "board_id": BOARD_ID, "kind": "note", "x": 10.0, "y": 20.0, "w": 220.0, "h": 180.0,
        "rotation": 0.0, "z": 1, "asset_id": None, "file_path": None, "thumb_path": None, "filename": None,
        "mime": None, "size_bytes": 0, "width": None, "height": None, "note": "Warm light", "color": "yellow",
        "url": None, "title": None, "description": None, "site_name": None, "created_at": NOW, "updated_at": NOW,
        "asset_url": None, "asset_variants": None, "asset_width": None, "asset_height": None, "asset_alt": None,
    }
    return {**base, **over}


class Conn(QueryConn):
    def transaction(self):
        return self


def _site_conn(**tables) -> Conn:
    fetchrow = {"FROM cappe_sites": {"id": SITE_ID, "account_id": ACCOUNT.id}}
    fetchrow.update(tables.pop("fetchrow", {}))
    return Conn(fetchrow=fetchrow, **tables)


def _client(monkeypatch, conn):
    monkeypatch.setattr(routes, "get_connection", lambda *a, **k: conn)
    return route_client(routes.router, overrides={routes.require_cappe_account: ACCOUNT})


class FakeStore:
    """The route's view of `store`, recording what it was asked to write."""

    def __init__(self, monkeypatch, *, board=True, pins=(), row=None):
        self.inserted, self.updated, self.layout = [], [], []
        self.board, self.pins, self.row = (_board() if board else None), list(pins), row
        self.limit: Exception | None = None
        for name in ("get_board", "insert_pin", "update_pin", "update_layout", "list_pins", "get_pin",
                     "check_room", "delete_pin", "attach_asset", "library_assets"):
            monkeypatch.setattr(store, name, getattr(self, name))

    async def get_board(self, conn, site_id, board_id):
        return self.board if board_id == BOARD_ID else None

    async def check_room(self, conn, site_id, board_id, new_bytes):
        if self.limit:
            raise self.limit

    async def insert_pin(self, conn, site_id, board_id, fields):
        if self.limit:
            raise self.limit
        self.inserted.append(fields)
        return store.pin_out(_pin_row(**{k: v for k, v in fields.items()}))

    async def update_pin(self, conn, site_id, board_id, pin_id, changes):
        self.updated.append(changes)
        return store.pin_out(_pin_row(**{**(self.row or {}), **changes}))

    async def update_layout(self, conn, site_id, board_id, items):
        self.layout.append(items)
        return len(items)

    async def list_pins(self, conn, board_id):
        return [store.pin_out(p) for p in self.pins]

    async def library_assets(self, conn, site_id, pins):
        return [{"id": p["asset_id"], "kind": "upload", "url": "https://cdn.example.test/a.jpg", "prompt": None,
                 "aspect": None, "image_size": None, "created_at": NOW, "variants": {}, "ai_generated": False,
                 "moderation": "unchecked"} for p in pins if p.get("asset_id")]

    async def get_pin(self, conn, board_id, pin_id):
        return _pin_row(**self.row) if self.row is not None and pin_id == PIN_ID else None

    async def delete_pin(self, conn, site_id, board_id, pin_id):
        return [p for p in (self.row.get("file_path"), self.row.get("thumb_path")) if p] if self.row else None

    async def attach_asset(self, conn, site_id, board_id, pin_id, asset_id, file_path):
        return store.pin_out(_pin_row(**{**self.row, "asset_id": asset_id, "file_path": None, "thumb_path": None,
                                         "asset_url": "https://cdn.example.test/cappe/library/0-a.jpg"}))


# ── the client mirrors the bounds ───────────────────────────────────────────

def test_the_client_mirrors_every_bound():
    ts = (ROOT / "client/src/cappe/boards/limits.ts").read_text()
    for name in ("MAX_BOARDS_PER_SITE", "MAX_PINS_PER_BOARD", "MAX_SITE_BYTES", "MAX_FILE_BYTES", "TITLE_MAX",
                 "NOTE_MAX", "URL_MAX", "COORD_MAX", "SIZE_MIN", "SIZE_MAX", "ROTATION_MAX", "Z_MAX"):
        found = re.search(rf"export const {name} = ([^\n]+)", ts)
        assert found, f"{name} missing from limits.ts"
        assert eval(found.group(1).rstrip(";").replace("_", "")) == getattr(limits, name), name  # noqa: S307
    colors = re.search(r"NOTE_COLORS = \[([^\]]+)\]", ts).group(1)
    assert tuple(re.findall(r"'(\w+)'", colors)) == limits.NOTE_COLORS
    assert get_args(models.NoteColor) == limits.NOTE_COLORS


# ── signed links ────────────────────────────────────────────────────────────

def test_a_signed_link_verifies_and_keeps_its_claim():
    token = files.sign("s3://private-bucket/cappe/boards/1-a.webp", mode="image", mime="image/webp", now=1000.0)
    claim = files.verify(token, now=1000.0)
    assert claim["p"] == "s3://private-bucket/cappe/boards/1-a.webp" and claim["m"] == "image"


def test_a_forged_mangled_or_expired_link_is_refused():
    token = files.sign("s3://private-bucket/cappe/boards/1-a.webp", mode="image", mime="image/webp", now=1000.0)
    payload, mac = token.split(".")
    other = files.sign("s3://private-bucket/cappe/boards/2-b.webp", mode="image", mime="image/webp", now=1000.0)
    assert files.verify(f"{other.split('.')[0]}.{mac}", now=1000.0) is None
    assert files.verify(payload, now=1000.0) is None
    assert files.verify(token, now=1000.0 + 3 * files.TTL_SECONDS) is None


def test_the_same_file_keeps_the_same_link_within_a_window():
    """So the browser's cache works across board loads."""
    start = 10 * files.TTL_SECONDS
    a = files.sign("s3://b/k", mode="image", mime="image/webp", now=start + 5)
    b = files.sign("s3://b/k", mode="image", mime="image/webp", now=start + files.TTL_SECONDS - 5)
    assert a == b
    assert files.verify(a, now=start + files.TTL_SECONDS - 5) is not None


def test_only_private_paths_are_ever_signed_for():
    token = files.sign("https://elsewhere.example.test/x.png", mode="image", mime="image/png")
    assert files.verify(token) is None


# ── files ───────────────────────────────────────────────────────────────────

def test_a_filename_is_safe_to_show_and_send():
    assert files.clean_filename("../../etc/passwd") == "passwd"
    assert files.clean_filename("C:\\Users\\me\\Mood board.pdf") == "Mood board.pdf"
    assert files.clean_filename("bad\x00name\n.txt") == "badname.txt"
    long = "a" * 300 + ".pdf"
    assert len(files.clean_filename(long)) == limits.FILENAME_MAX and files.clean_filename(long).endswith(".pdf")
    assert files.clean_filename("") == "file"


def test_a_vague_type_goes_by_the_extension():
    assert files.declared_type("application/octet-stream", "brief.PDF") == files.PDF
    assert files.declared_type("", "shot.png") == "image/png"
    assert files.declared_type("application/vnd.ms-excel", "list.csv") == "text/csv"
    assert files.declared_type("image/jpeg; charset=binary", "a.jpg") == "image/jpeg"
    assert files.declared_type(None, "song.mp3") is None


def test_a_document_downloads_under_its_own_name():
    assert files.disposition("Look book.pdf", files.PDF).startswith("inline;")
    sheet = files.disposition("Prices é.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert sheet.startswith("attachment;") and "filename*=UTF-8''Prices%20%C3%A9.xlsx" in sheet


def test_a_thumbnail_is_small_and_carries_no_metadata():
    thumb = files.thumbnail(_photo((3000, 2000)))
    with Image.open(io.BytesIO(thumb)) as img:
        assert img.format == "WEBP" and max(img.size) == files.THUMB_SIDE
        assert not img.getexif().get_ifd(GPS_IFD)


def test_a_pdf_gets_its_first_page_and_a_broken_one_gets_none():
    thumb = files.pdf_thumbnail(_pdf())
    with Image.open(io.BytesIO(thumb)) as img:
        assert img.format == "WEBP"
    assert files.pdf_thumbnail(b"%PDF-1.4 not really") is None


def test_storing_a_photo_strips_its_location_and_keeps_it_private(storage):
    import asyncio

    kept = asyncio.run(files.store_image(_photo(), "image/jpeg", "IMG_0001.jpg"))
    assert kept.file_path.startswith("s3://private-bucket/cappe/boards/")
    assert kept.thumb_path.startswith("s3://private-bucket/cappe/boards/")
    assert not storage.public
    with Image.open(io.BytesIO(storage.files[kept.file_path][0])) as img:
        assert not img.getexif().get_ifd(GPS_IFD)
    assert (kept.width, kept.height) == (1200, 800)


def test_without_a_private_bucket_storing_says_so(monkeypatch):
    import asyncio

    class NoBucket:
        async def upload_private_file(self, *a, **k):
            raise RuntimeError("S3 not configured for private uploads")

    monkeypatch.setattr(files, "get_storage", lambda: NoBucket())
    with pytest.raises(files.StorageUnavailable):
        asyncio.run(files.store_document(b"notes", "text/plain", "a.txt"))


# ── links ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("example.com/look", "https://example.com/look"),
    ("  https://www.example.org/a?b=1 ", "https://www.example.org/a?b=1"),
    ("http://example.net", "http://example.net"),
])
def test_a_pasted_address_becomes_a_web_address(raw, expected):
    assert links.normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "javascript:alert(1)", "ftp://example.com/a", "not a link",
                                 "https://user:pw@example.com/", "localhost/admin", "x" * 3000])
def test_anything_else_is_refused(raw):
    with pytest.raises(links.BadLink):
        links.normalize_url(raw)


def test_a_page_head_gives_its_title_line_and_picture():
    html = """<html><head><title>Fallback</title>
      <meta property="og:title" content="Linen &amp; light">
      <meta name="description" content="A   quiet studio.">
      <meta property="og:site_name" content="Studio Journal">
      <meta property="og:image" content="/img/cover.jpg"></head><body><meta property="og:title" content="Late"></body>"""
    head = links.parse_head(html, "https://journal.example.test/posts/1")
    assert head == {"title": "Linen & light", "description": "A quiet studio.", "site_name": "Studio Journal",
                    "image_url": "https://journal.example.test/img/cover.jpg"}


def test_a_page_without_metadata_uses_its_title_and_no_unsafe_picture():
    head = links.parse_head("<title> Just a page </title><meta property='og:image' content='javascript:x'>",
                            "https://a.example.test/")
    assert head["title"] == "Just a page" and head["image_url"] is None


def _fetched(body: bytes, content_type: str, status: int = 200, truncated=False, url="https://a.example.test/"):
    return SimpleNamespace(url=url, final_url=url, status=status, content_type=content_type, body=body,
                           truncated=truncated)


def test_a_link_preview_fetches_the_page_then_its_picture(monkeypatch):
    import asyncio

    calls = []

    async def fetch(url, **kw):
        calls.append(url)
        if url.endswith("/cover.jpg"):
            return _fetched(_photo(), "image/jpeg", url=url)
        return _fetched(b'<head><meta property="og:title" content="Moodboard"><meta property="og:image" '
                        b'content="https://cdn.a.example.test/cover.jpg"></head>', "text/html", url=url)

    monkeypatch.setattr(links, "fetch_public", fetch)
    preview = asyncio.run(links.fetch_preview("https://a.example.test/p"))
    assert preview.title == "Moodboard" and preview.site_name == "a.example.test" and not preview.direct
    assert preview.image_mime == "image/webp" and preview.image_bytes
    assert calls == ["https://a.example.test/p", "https://cdn.a.example.test/cover.jpg"]


def test_a_link_to_a_picture_is_that_picture(monkeypatch):
    import asyncio

    async def fetch(url, **kw):
        return _fetched(_photo(), "image/jpeg", url=url)

    monkeypatch.setattr(links, "fetch_public", fetch)
    preview = asyncio.run(links.fetch_preview("https://a.example.test/shot.jpg"))
    assert preview.direct and preview.image_mime == "image/jpeg"


def test_a_link_that_cant_be_fetched_is_a_card_named_by_its_host(monkeypatch):
    import asyncio

    async def fetch(url, **kw):
        raise links.BadLink("unsafe")

    monkeypatch.setattr(links, "fetch_public", fetch)
    preview = asyncio.run(links.fetch_preview("https://www.example.org/x"))
    assert preview.title == "example.org" and preview.image_bytes is None


# ── the answer never carries a storage path ─────────────────────────────────

def test_a_private_pin_is_answered_with_signed_links_only():
    out = store.pin_out(_pin_row(kind="image", file_path="s3://private-bucket/cappe/boards/0-a.jpg",
                                 thumb_path="s3://private-bucket/cappe/boards/1-thumb.webp", mime="image/jpeg"))
    assert out["src"].startswith(files.PATH) and out["full"].startswith(files.PATH)
    assert "file_path" not in out and "thumb_path" not in out and not out["in_library"]
    assert "s3://" not in str(models.PinOut(**out).model_dump(mode="json"))


def test_a_library_pin_shows_the_librarys_sizes():
    variants = '{"webp": [{"w": 480, "url": "https://cdn.example.test/w480.webp"}, ' \
               '{"w": 960, "url": "https://cdn.example.test/w960.webp"}]}'
    out = store.pin_out(_pin_row(kind="image", asset_id=ASSET_ID, asset_url="https://cdn.example.test/a.jpg",
                                 asset_variants=variants, asset_width=2000, asset_height=1000, asset_alt="Dunes"))
    assert out["src"] == "https://cdn.example.test/w960.webp" and out["full"] == "https://cdn.example.test/a.jpg"
    assert out["in_library"] and (out["width"], out["height"], out["alt"]) == (2000, 1000, "Dunes")


def test_a_document_pin_links_to_its_file_under_its_name():
    out = store.pin_out(_pin_row(kind="file", file_path="s3://private-bucket/cappe/boards/0-brief.pdf",
                                 filename="brief.pdf", mime=files.PDF))
    claim = files.verify(out["file_url"][len(files.PATH):])
    assert claim["m"] == "doc" and claim["n"] == "brief.pdf"


# ── store: scoping and limits ───────────────────────────────────────────────

def test_adding_a_pin_locks_the_site_and_checks_room_first():
    import asyncio

    conn = Conn(
        fetchval={"COUNT(*) FROM cappe_board_pins": 3, "SUM(size_bytes)": 10, "INSERT INTO cappe_board_pins": PIN_ID},
        fetchrow={"FROM cappe_board_pins p LEFT JOIN cappe_assets": _pin_row()},
    )
    asyncio.run(store.insert_pin(conn, SITE_ID, BOARD_ID, {"kind": "note", "x": 0, "y": 0, "w": 220, "h": 180,
                                                           "note": "Warm light", "color": "yellow"}))
    order = [sql for _, sql, _ in conn.calls]
    lock = next(i for i, sql in enumerate(order) if "pg_advisory_xact_lock" in sql)
    insert = next(i for i, sql in enumerate(order) if "INSERT INTO cappe_board_pins" in sql)
    assert lock < insert
    assert conn.args_for("pg_advisory_xact_lock") == (f"cappe_boards:{SITE_ID}",)
    assert "site_id = $2" not in order[insert] and conn.args_for("INSERT INTO cappe_board_pins")[:2] == (BOARD_ID, SITE_ID)


def test_a_full_board_or_site_is_refused():
    import asyncio

    full_board = Conn(fetchval={"COUNT(*) FROM cappe_board_pins": limits.MAX_PINS_PER_BOARD})
    with pytest.raises(store.BoardLimit):
        asyncio.run(store.check_room(full_board, SITE_ID, BOARD_ID, 0))
    full_site = Conn(fetchval={"COUNT(*) FROM cappe_board_pins": 1, "SUM(size_bytes)": limits.MAX_SITE_BYTES - 5})
    with pytest.raises(store.SiteFull):
        asyncio.run(store.check_room(full_site, SITE_ID, BOARD_ID, 10))
    asyncio.run(store.check_room(full_site, SITE_ID, BOARD_ID, 5))


def test_every_board_and_pin_query_names_the_site():
    import asyncio

    conn = Conn(fetchrow={"FROM cappe_boards": None, "DELETE FROM cappe_board_pins": None,
                          "UPDATE cappe_boards": None},
                fetchval={"DELETE FROM cappe_boards": None, "UPDATE cappe_board_pins": None}, fetch={})
    conn.set("fetch", "FROM cappe_board_pins", [])
    assert asyncio.run(store.get_board(conn, SITE_ID, BOARD_ID)) is None
    assert asyncio.run(store.delete_board(conn, SITE_ID, BOARD_ID)) is None
    assert asyncio.run(store.delete_pin(conn, SITE_ID, BOARD_ID, PIN_ID)) is None
    assert asyncio.run(store.rename_board(conn, SITE_ID, BOARD_ID, "New")) is None
    assert asyncio.run(store.update_pin(conn, SITE_ID, BOARD_ID, PIN_ID, {"x": 5})) is None
    for kind, sql, args in conn.calls:
        if "cappe_board" in sql and "pg_advisory" not in sql:
            assert "site_id" in sql and SITE_ID in args, sql


def test_too_many_boards_is_refused():
    import asyncio

    conn = Conn(fetchval={"COUNT(*) FROM cappe_boards": limits.MAX_BOARDS_PER_SITE})
    with pytest.raises(store.BoardLimit):
        asyncio.run(store.create_board(conn, SITE_ID, "One more"))


def test_a_layout_counts_what_moved():
    import asyncio

    conn = Conn(execute={"UPDATE cappe_board_pins p": "UPDATE 2"}, strict_execute=False)
    items = [{"id": uuid4(), "x": 1, "y": 2, "w": 30, "h": 40, "rotation": 0, "z": 1} for _ in range(2)]
    assert asyncio.run(store.update_layout(conn, SITE_ID, BOARD_ID, items)) == 2
    assert asyncio.run(store.update_layout(conn, SITE_ID, BOARD_ID, [])) == 0


# ── routes ──────────────────────────────────────────────────────────────────

def test_another_accounts_site_is_not_found(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_sites": None})
    with _client(monkeypatch, conn) as client:
        assert client.get(f"/sites/{SITE_ID}/boards").status_code == 404
        assert client.post(f"/sites/{SITE_ID}/boards", json={"title": "Mine"}).status_code == 404


def test_a_board_on_another_site_is_not_found(monkeypatch):
    FakeStore(monkeypatch)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.get(f"/sites/{SITE_ID}/boards/{uuid4()}")
    assert res.status_code == 404


def test_a_board_comes_with_its_pins_privately(monkeypatch):
    FakeStore(monkeypatch, pins=[_pin_row(), _pin_row(id=uuid4(), kind="link", url="https://a.example.test/",
                                                      title="A", z=2),
                                 _pin_row(id=uuid4(), kind="image", asset_id=ASSET_ID, z=3,
                                          asset_url="https://cdn.example.test/a.jpg")])
    with _client(monkeypatch, _site_conn()) as client:
        res = client.get(f"/sites/{SITE_ID}/boards/{BOARD_ID}")
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store, private"
    body = res.json()
    assert body["board"]["pin_count"] == 3 and [p["kind"] for p in body["pins"]] == ["note", "link", "image"]
    assert [a["id"] for a in body["assets"]] == [str(ASSET_ID)]


def test_a_note_is_pinned_yellow_unless_coloured(monkeypatch):
    fake = FakeStore(monkeypatch)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins",
                          json={"kind": "note", "x": 40, "y": 60, "note": "  Warm, grainy, 70s  "})
        empty = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins", json={"kind": "note", "x": 0, "y": 0,
                                                                                 "note": "   "})
        odd = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins", json={"kind": "note", "x": 0, "y": 0,
                                                                               "note": "a", "color": "red"})
    assert res.status_code == 201
    assert fake.inserted[0] | {} == {"kind": "note", "x": 40, "y": 60, "w": 220.0, "h": 180.0, "rotation": 0,
                                     "note": "Warm, grainy, 70s", "color": "yellow"}
    assert empty.status_code == 422 and odd.status_code == 422


def test_a_library_picture_must_be_this_sites(monkeypatch):
    FakeStore(monkeypatch)
    conn = _site_conn(fetchrow={"FROM cappe_assets": None})
    with _client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins",
                          json={"kind": "image", "x": 0, "y": 0, "asset_id": str(ASSET_ID)})
    assert res.status_code == 422


def test_a_library_picture_keeps_its_shape(monkeypatch):
    fake = FakeStore(monkeypatch)
    asset = {"id": ASSET_ID, "width": 1000, "height": 1500, "variants": "{}"}
    with _client(monkeypatch, _site_conn(fetchrow={"FROM cappe_assets": asset})) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins",
                          json={"kind": "image", "x": 0, "y": 0, "asset_id": str(ASSET_ID)})
    assert res.status_code == 201
    assert (fake.inserted[0]["w"], fake.inserted[0]["h"]) == (280.0, 420.0)
    assert fake.inserted[0]["asset_id"] == ASSET_ID


def test_a_link_is_pinned_with_its_preview_kept_private(monkeypatch, storage):
    fake = FakeStore(monkeypatch)

    async def preview(url):
        return links.LinkPreview(url=url, title="Moodboard", site_name="a.example.test",
                                 image_bytes=files.thumbnail(_photo()), image_mime="image/webp")

    monkeypatch.setattr(links, "fetch_preview", preview)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins",
                          json={"kind": "link", "x": 0, "y": 0, "url": "a.example.test/p"})
        bad = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins",
                          json={"kind": "link", "x": 0, "y": 0, "url": "javascript:alert(1)"})
    assert res.status_code == 201 and bad.status_code == 422
    pinned = fake.inserted[0]
    assert pinned["kind"] == "link" and pinned["url"] == "https://a.example.test/p" and pinned["h"] == 260.0
    assert pinned["thumb_path"] in storage.files and not storage.public
    assert res.json()["src"].startswith(files.PATH)


def test_a_link_to_a_picture_is_pinned_as_a_photo(monkeypatch, storage):
    fake = FakeStore(monkeypatch)

    async def preview(url):
        return links.LinkPreview(url=url, title="a.example.test", image_bytes=_photo((600, 900)),
                                 image_mime="image/jpeg", direct=True)

    monkeypatch.setattr(links, "fetch_preview", preview)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins",
                          json={"kind": "link", "x": 0, "y": 0, "url": "https://a.example.test/shot.jpg"})
    assert res.status_code == 201
    assert fake.inserted[0]["kind"] == "image" and fake.inserted[0]["url"] == "https://a.example.test/shot.jpg"
    assert fake.inserted[0]["h"] == 420.0


def test_a_screenshot_upload_is_a_private_photo_pin(monkeypatch, storage):
    fake = FakeStore(monkeypatch)
    png = io.BytesIO()
    Image.new("RGB", (1440, 900), (200, 200, 200)).save(png, "PNG")
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/upload", data={"x": "12", "y": "34"},
                          files={"file": ("Screenshot 2026-10-27.png", png.getvalue(), "image/png")})
    assert res.status_code == 201, res.text
    pinned = fake.inserted[0]
    assert pinned["kind"] == "image" and (pinned["x"], pinned["y"]) == (12.0, 34.0)
    assert pinned["file_path"] in storage.files and pinned["thumb_path"] in storage.files
    assert pinned["size_bytes"] == sum(len(storage.files[p][0]) for p in (pinned["file_path"], pinned["thumb_path"]))
    assert not storage.public and "s3://" not in res.text


def test_a_pdf_upload_is_a_file_pin_with_its_first_page(monkeypatch, storage):
    fake = FakeStore(monkeypatch)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/upload", data={"x": "0", "y": "0"},
                          files={"file": ("brief.pdf", _pdf(), "application/octet-stream")})
    assert res.status_code == 201, res.text
    pinned = fake.inserted[0]
    assert pinned["kind"] == "file" and pinned["mime"] == files.PDF and pinned["thumb_path"]
    assert pinned["filename"] == "brief.pdf" and pinned["h"] == 290.0


@pytest.mark.parametrize("name,data,ctype,code", [
    ("song.mp3", b"ID3\x03\x00", "audio/mpeg", 415),
    ("fake.png", b"%PDF-1.4 not a png", "image/png", 400),
    ("photo.heic", b"\x00\x00\x00\x18ftypheic", "image/heic", 415),
])
def test_what_cant_be_pinned_is_refused(monkeypatch, storage, name, data, ctype, code):
    FakeStore(monkeypatch)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/upload", data={"x": "0", "y": "0"},
                          files={"file": (name, data, ctype)})
    assert res.status_code == code
    assert not storage.files


def test_a_refused_insert_removes_what_was_stored(monkeypatch, storage):
    fake = FakeStore(monkeypatch)
    fake.limit = None

    async def room(conn, site_id, board_id, new_bytes):
        return None

    async def full(conn, site_id, board_id, fields):
        raise store.SiteFull("Your boards hold 1 GB of files at most.")

    monkeypatch.setattr(store, "check_room", room)
    monkeypatch.setattr(store, "insert_pin", full)
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/upload", data={"x": "0", "y": "0"},
                          files={"file": ("a.jpg", _photo(), "image/jpeg")})
    assert res.status_code == 413
    assert len(storage.deleted) == 2 and not storage.files


def test_a_full_board_refuses_before_storing_anything(monkeypatch, storage):
    fake = FakeStore(monkeypatch)
    fake.limit = store.BoardLimit("A board holds 300 pins.")
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/upload", data={"x": "0", "y": "0"},
                          files={"file": ("a.jpg", _photo(), "image/jpeg")})
    assert res.status_code == 409 and not storage.files


def test_editing_a_pin(monkeypatch):
    fake = FakeStore(monkeypatch, row=_pin_row(kind="link", url="https://a.example.test/"))
    with _client(monkeypatch, _site_conn()) as client:
        ok = client.patch(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/{PIN_ID}",
                          json={"title": "  Look   book ", "color": "pink", "note": "  "})
        null_x = client.patch(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/{PIN_ID}", json={"x": None})
        missing = client.patch(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/{uuid4()}", json={"x": 3})
    assert ok.status_code == 200 and fake.updated[0] == {"title": "Look book", "note": None}
    assert null_x.status_code == 422 and missing.status_code == 404


def test_a_note_cant_be_emptied(monkeypatch):
    FakeStore(monkeypatch, row=_pin_row())
    with _client(monkeypatch, _site_conn()) as client:
        res = client.patch(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/{PIN_ID}", json={"note": " "})
    assert res.status_code == 422


def test_a_layout_moves_many_pins_but_not_one_twice(monkeypatch):
    fake = FakeStore(monkeypatch)
    one = {"id": str(PIN_ID), "x": 5, "y": 6, "w": 100, "h": 80, "rotation": -4, "z": 9}
    with _client(monkeypatch, _site_conn()) as client:
        ok = client.put(f"/sites/{SITE_ID}/boards/{BOARD_ID}/layout", json={"pins": [one]})
        twice = client.put(f"/sites/{SITE_ID}/boards/{BOARD_ID}/layout", json={"pins": [one, one]})
        tiny = client.put(f"/sites/{SITE_ID}/boards/{BOARD_ID}/layout", json={"pins": [{**one, "w": 1}]})
    assert ok.status_code == 200 and ok.json() == {"moved": 1} and fake.layout[0][0]["rotation"] == -4
    assert twice.status_code == 422 and tiny.status_code == 422


def test_deleting_a_pin_removes_its_files_after(monkeypatch, storage):
    FakeStore(monkeypatch, row=_pin_row(kind="image", file_path="s3://private-bucket/a.jpg",
                                        thumb_path="s3://private-bucket/t.webp"))
    with _client(monkeypatch, _site_conn()) as client:
        res = client.delete(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/{PIN_ID}")
    assert res.status_code == 204
    assert storage.deleted == ["s3://private-bucket/a.jpg", "s3://private-bucket/t.webp"]


def test_a_pinned_picture_reaches_the_library_only_when_the_owner_may_use_it(monkeypatch, storage):
    path = "s3://private-bucket/cappe/boards/0-a.jpg"
    storage.files[path] = (_photo(), "image/jpeg")
    storage.files["s3://private-bucket/t.webp"] = (b"x", "image/webp")
    FakeStore(monkeypatch, row=_pin_row(kind="image", file_path=path, thumb_path="s3://private-bucket/t.webp",
                                        mime="image/jpeg", filename="a.jpg"))
    inserted = {}

    async def insert_upload(conn, **kw):
        inserted.update(kw)
        return {"id": ASSET_ID, "kind": "upload", "url": kw["url"], "prompt": None, "aspect": None,
                "image_size": None, "created_at": NOW, "variants": kw["variants"], "ai_generated": False,
                "moderation": "unchecked"}

    monkeypatch.setattr(routes.cappe_assets, "insert_upload", insert_upload)
    url = f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/{PIN_ID}/library"
    with _client(monkeypatch, _site_conn()) as client:
        refused = client.post(url, json={"rights_attested": False})
        assert refused.status_code == 422 and not storage.public and not inserted
        res = client.post(url, json={"rights_attested": True, "alt": " Dunes at dusk "})
    assert res.status_code == 200, res.text
    assert inserted["alt"] == "Dunes at dusk" and all(u.startswith("https://cdn.example.test/cappe/library/")
                                                      for u in storage.public)
    assert res.json()["pin"]["in_library"] and res.json()["asset"]["id"] == str(ASSET_ID)
    assert path in storage.deleted


def test_a_library_pin_cant_be_added_again(monkeypatch, storage):
    FakeStore(monkeypatch, row=_pin_row(kind="image", asset_id=ASSET_ID))
    with _client(monkeypatch, _site_conn()) as client:
        res = client.post(f"/sites/{SITE_ID}/boards/{BOARD_ID}/pins/{PIN_ID}/library",
                          json={"rights_attested": True})
    assert res.status_code == 409


# ── the signed-file route ───────────────────────────────────────────────────

def _public_client():
    return route_client(public_files.router)


def test_a_picture_streams_from_our_origin(storage):
    storage.files["s3://private-bucket/t.webp"] = (b"RIFF....WEBP", "image/webp")
    link = files.image_link("s3://private-bucket/t.webp", "image/webp")
    with _public_client() as client:
        res = client.get(link)
    assert res.status_code == 200 and res.content == b"RIFF....WEBP"
    assert res.headers["content-type"] == "image/webp" and res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["content-security-policy"] == "default-src 'none'"


def test_a_document_redirects_to_s3_under_its_name(storage):
    storage.files["s3://private-bucket/brief.pdf"] = (b"%PDF-1.4", files.PDF)
    link = files.document_link("s3://private-bucket/brief.pdf", files.PDF, "Spring brief.pdf")
    with _public_client() as client:
        res = client.get(link, follow_redirects=False)
    assert res.status_code == 302 and res.headers["location"].startswith("https://private-bucket.s3.example.test/")
    assert storage.presigned[0][1].startswith('inline; filename="Spring brief.pdf"')


def test_a_bad_link_or_a_gone_file_is_not_found(storage):
    with _public_client() as client:
        assert client.get(files.PATH + "nope.nope").status_code == 404
        assert client.get(files.image_link("s3://private-bucket/gone.webp", "image/webp")).status_code == 404
        text = files.PATH + files.sign("s3://private-bucket/a.html", mode="image", mime="text/html")
        assert client.get(text).status_code == 404


# ── the migration ───────────────────────────────────────────────────────────

def test_the_migration_follows_the_reader_annotations():
    src = (ROOT / "server/alembic/versions/cappeboard01_mood_boards.py").read_text()
    assert 'revision = "cappeboard01"' in src and 'down_revision = "cappereader01"' in src
    assert "RAISE EXCEPTION" in src


# ── a deleted site takes its board files with it ────────────────────────────

def test_deleting_a_site_removes_its_board_files_after(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    from app.cappe.routes import sites as sites_mod
    from app.cappe.services import recurring

    conn = Conn(fetch={
        "INSERT INTO cappe_edge_tombstones": [],
        "FROM cappe_board_pins": [{"file_path": "s3://private-bucket/a.jpg", "thumb_path": "s3://private-bucket/t.webp"},
                                  {"file_path": "s3://private-bucket/b.pdf", "thumb_path": None}],
    })
    monkeypatch.setattr(sites_mod, "get_connection", lambda *a, **k: conn)
    monkeypatch.setattr(sites_mod, "get_owned_site", AsyncMock(return_value={"id": SITE_ID}))
    monkeypatch.setattr(sites_mod, "invalidate_render_cache", AsyncMock())
    monkeypatch.setattr(recurring, "cancel_site_subscriptions", AsyncMock(return_value=0))
    tasks = []
    background = SimpleNamespace(add_task=lambda fn, *args: tasks.append((fn, args)))
    asyncio.run(sites_mod.delete_site(SITE_ID, background, account=ACCOUNT))
    order = [sql for _, sql, _ in conn.calls]
    pins = next(i for i, sql in enumerate(order) if "FROM cappe_board_pins" in sql)
    assert pins < next(i for i, sql in enumerate(order) if "DELETE FROM cappe_sites" in sql)
    assert tasks == [(files.remove, (["s3://private-bucket/a.jpg", "s3://private-bucket/t.webp",
                                      "s3://private-bucket/b.pdf"],))]
