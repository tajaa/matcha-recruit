"""A magazine's own fonts: reading an upload, the site's font list, the routes
and the public file route. Fonts are made here with fontTools; persistence
uses a fake connection, storage a mock. No database is touched."""
import asyncio
import hashlib
import pathlib
import re
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

from app.cappe.routes import studio_fonts as routes
from app.cappe.routes.public import fonts as public_fonts
from app.cappe.services.magazine.studio import custom_fonts as C
from app.cappe.services.magazine.studio import fonts as faces
from tests._helpers.routes import QueryConn, route_client
from tests.cappe.test_cappe_magazine_routes import ACCOUNT, SITE, SITE_ROW, Conn, Ctx

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
LETTERS = [chr(c) for c in range(0x41, 0x5B)]
FAMILY = "u-0123456789abcdef"


# ── fonts made for the tests ─────────────────────────────────────────────────

def _builder(*, weight=400, italic=False, name="Test Sans", typo=True):
    fb = FontBuilder(1000, isTTF=True)
    order = [".notdef", "space"] + LETTERS
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x20: "space", **{ord(c): c for c in LETTERS}})
    glyphs = {}
    for g in order:
        pen = TTGlyphPen(None)
        if g != "space":
            pen.moveTo((50, 0)); pen.lineTo((50, 700)); pen.lineTo((450, 700)); pen.lineTo((450, 0)); pen.closePath()
        glyphs[g] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({g: (500, 50) for g in order})
    fb.setupHorizontalHeader(ascent=900, descent=-250)
    fb.setupNameTable({"familyName": name, "styleName": "Italic" if italic else "Regular"})
    fb.setupOS2(sTypoAscender=800 if typo else 0, sTypoDescender=-200 if typo else 0, sTypoLineGap=90,
                usWinAscent=950, usWinDescent=300, usWeightClass=weight, fsSelection=1 if italic else 0x40,
                sCapHeight=700, sxHeight=500)
    fb.setupPost()
    return fb


def _bytes(font) -> bytes:
    buf = BytesIO()
    font.save(buf)
    return buf.getvalue()


def ttf(**kw) -> bytes:
    return _bytes(_builder(**kw))


def ttf_with_features() -> bytes:
    font = TTFont(BytesIO(ttf()))
    addOpenTypeFeaturesFromString(font, "languagesystem DFLT dflt; feature smcp { sub A by B; } smcp; "
                                        "feature kern { pos A B -50; } kern;")
    return _bytes(font)


def otf() -> bytes:
    fb = FontBuilder(1000, isTTF=False)
    order = [".notdef", "space"] + LETTERS
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x20: "space", **{ord(c): c for c in LETTERS}})
    strings = {}
    for g in order:
        pen = T2CharStringPen(500, None)
        if g != "space":
            pen.moveTo((50, 0)); pen.curveTo((50, 400), (100, 700), (250, 700)); pen.lineTo((450, 0)); pen.closePath()
        strings[g] = pen.getCharString()
    fb.setupCFF("TestSerif", {"FullName": "Test Serif"}, strings, {})
    fb.setupHorizontalMetrics({g: (500, 50) for g in order})
    fb.setupHorizontalHeader(ascent=880, descent=-220)
    fb.setupNameTable({"familyName": "Test Serif", "styleName": "Bold"})
    fb.setupOS2(sTypoAscender=780, sTypoDescender=-220, usWeightClass=700, sCapHeight=690, sxHeight=480)
    fb.setupPost()
    return _bytes(fb)


def woff2() -> bytes:
    font = TTFont(BytesIO(ttf()))
    font.flavor = "woff2"
    return _bytes(font)


def variable() -> bytes:
    fb = _builder(name="Test Var")
    fb.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    fb.setupGvar({})
    return _bytes(fb)


def ttc() -> bytes:
    coll = TTCollection()
    coll.fonts = [TTFont(BytesIO(ttf())), TTFont(BytesIO(ttf(weight=700)))]
    return _bytes(coll)


def _read(data: bytes) -> TTFont:
    return TTFont(BytesIO(data))


# ── reading an upload ────────────────────────────────────────────────────────

@pytest.mark.parametrize("make", [ttf, otf, woff2, variable])
def test_every_kind_comes_out_a_plain_truetype_face_with_one_set_of_metrics(make):
    out, meta = C.process(make())
    font = _read(out)
    assert font.sfntVersion == "\x00\x01\x00\x00" and font.flavor is None
    assert "glyf" in font and "CFF " not in font and "CFF2" not in font and "fvar" not in font
    os2, hhea = font["OS/2"], font["hhea"]
    assert hhea.ascent == os2.sTypoAscender == os2.usWinAscent == meta["asc"] > 0
    assert hhea.descent == os2.sTypoDescender == -os2.usWinDescent == meta["desc"]
    assert hhea.lineGap == 0 and os2.sTypoLineGap == 0 and os2.fsSelection & (1 << 7)
    assert font.getBestCmap()[ord("A")] and meta["upm"] == 1000


def test_cff_outlines_become_quadratic_and_keep_their_shape():
    out, meta = C.process(otf())
    font = _read(out)
    assert font["glyf"]["A"].numberOfContours == 1 and font["maxp"].tableVersion == 0x00010000
    assert meta == {"weight": 700, "italic": False, "upm": 1000, "asc": 780, "desc": -220, "cap": 690, "x": 480,
                    "features": [], "suggested_name": "Test Serif"}


def test_layout_features_are_kept_and_listed():
    out, meta = C.process(ttf_with_features())
    assert meta["features"] == ["kern", "smcp"]
    assert "GSUB" in _read(out) and "GPOS" in _read(out)


def test_a_face_without_typo_metrics_takes_its_hhea():
    _, meta = C.process(ttf(typo=False))
    assert (meta["asc"], meta["desc"]) == (900, -250)


@pytest.mark.parametrize("weight, italic, expect", [(400, False, (400, False)), (350, True, (400, True)),
                                                    (250, False, (300, False)), (950, False, (900, False))])
def test_weight_and_italic_are_read_from_the_face(weight, italic, expect):
    _, meta = C.process(ttf(weight=weight, italic=italic))
    assert (meta["weight"], meta["italic"]) == expect


@pytest.mark.parametrize("data, message", [
    (ttc(), "collections"),
    (b"\x89PNG\r\n\x1a\n" + b"0" * 64, "TTF, OTF, WOFF or WOFF2"),
    (b"\x00\x01\x00\x00" + b"garbage" * 20, "isn't a font"),
    (b"OTTO" + b"\x00" * 64, "isn't a font"),
    (b"\x00\x01\x00\x00" + b"0" * (C.MAX_UPLOAD_BYTES + 1), "10 MB"),
])
def test_what_isnt_a_usable_face_is_refused(data, message):
    with pytest.raises(C.FontError, match=message):
        C.process(data)


def test_a_face_with_no_latin_letters_is_refused():
    font = TTFont(BytesIO(ttf()))
    for table in font["cmap"].tables:
        table.cmap = {0x20: "space"}
    with pytest.raises(C.FontError, match="no Latin letters"):
        C.process(_bytes(font))


def test_names_and_weights_are_cleaned():
    assert C.clean_name("  Canela\u0000  Deck \n") == "Canela Deck"
    assert len(C.clean_name("x" * 200)) == 60 and C.clean_name(None) == ""
    assert [C.round_weight(v) for v in (49, 150, 449, 1000, "bad")] == [100, 200, 400, 900, 400]
    assert C.is_custom(FAMILY) and not C.is_custom("Inter") and not C.is_custom("u-0123")


# ── records and the site's fonts ─────────────────────────────────────────────

def row(**over):
    base = {"id": uuid4(), "family": FAMILY, "name": "Canela", "weight": 400, "italic": False, "sha": "a" * 64,
            "bytes": 1234, "upm": 1000, "asc": 800, "desc": -200, "cap": 700, "x": 500, "features": ["smcp", "kern"],
            "filename": "Canela.otf", "created_at": NOW, "hidden_at": None}
    return {**base, **over}


def test_a_doc_face_carries_exactly_what_a_page_needs():
    face = C.doc_face(row())
    assert set(face) == {"family", "name", "weight", "italic", "sha", "bytes", "upm", "asc", "desc", "cap", "x", "features"}
    assert face["features"] == ["kern", "smcp"]
    rec = C.record(row(hidden_at=NOW))
    assert rec["hidden"] is True and rec["created_at"] == NOW.isoformat() and rec["filename"] == "Canela.otf"


def test_doc_faces_reads_only_the_families_a_document_names():
    conn = QueryConn(fetch={"FROM cappe_studio_fonts": [
        row(), row(sha="b" * 64, hidden_at=NOW), row(weight=700, sha="c" * 64, hidden_at=NOW),
    ]})
    out = asyncio.run(C.doc_faces(conn, SITE, {"threads": [{"paras": [{"runs": [{"t": "x", "font": FAMILY}]}]}]}))
    assert [f["sha"] for f in out[FAMILY]] == ["a" * 64, "c" * 64]  # visible first; a hidden one still counts
    assert conn.args_for("FROM cappe_studio_fonts") == (SITE, [FAMILY])
    assert "site_id = $1" in conn.sql_for("fetch")[0]


def test_doc_faces_asks_nothing_when_no_family_is_named():
    conn = QueryConn()
    assert asyncio.run(C.doc_faces(conn, SITE, {"threads": [{"paras": [{"runs": [{"t": "u-xyz", "font": "Inter"}]}]}]})) == {}
    assert conn.calls == []


# ── the routes ───────────────────────────────────────────────────────────────

def _client(monkeypatch, conn, *, plan_has_magazine=True, account=ACCOUNT, storage=None):
    monkeypatch.setattr(routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(routes, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(routes, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(
        has=lambda f: plan_has_magazine and f == "magazine")))
    storage = storage or AsyncMock()
    monkeypatch.setattr(routes, "get_storage", lambda: storage)
    return route_client(routes.router, overrides={routes.require_cappe_account: account}), storage


def _site_conn(**extra):
    fetchrow = {"FROM cappe_sites WHERE id = $1 AND account_id": SITE_ROW, **extra.pop("fetchrow", {})}
    return Conn(fetchrow=fetchrow, **extra)


def _upload(client, data=None, **form):
    fields = {"name": "Canela", "licence_attested": "true", **form}
    return client.post(f"/sites/{SITE}/studio/fonts", data=fields,
                       files={"file": ("Canela.ttf", data if data is not None else ttf(), "font/ttf")})


def test_an_upload_is_prepared_stored_by_sha_then_recorded(monkeypatch):
    inserted = row(family="u-ffffffffffffffff")
    conn = _site_conn(fetchval={"FROM cappe_sites WHERE id = $1 FOR UPDATE": SITE, "SELECT count(*)": 0,
                                "SELECT family FROM cappe_studio_fonts": None, "SELECT 1 FROM cappe_studio_fonts": None},
                      fetchrow={"WHERE site_id = $1 AND sha = $2": None, "INSERT INTO cappe_studio_fonts": inserted})
    cm, storage = _client(monkeypatch, conn)
    with cm as client:
        res = _upload(client, weight="650", italic="true")
    assert res.status_code == 201, res.text
    assert res.json()["family"] == "u-ffffffffffffffff" and res.json()["id"] == str(inserted["id"])
    key, data, mime = storage.put_key.call_args.args
    sha = hashlib.sha256(data).hexdigest()
    assert key == f"cappe/fonts/{sha}.ttf" and mime == "font/ttf" and _read(data)["glyf"]
    args = conn.args_for("INSERT INTO cappe_studio_fonts")
    assert args[0] == SITE and C.FAMILY_RE.match(args[1]) and args[2:6] == ("Canela", 700, True, sha)
    assert args[-2:] == ("Canela.ttf", ACCOUNT.id)
    queries = [sql for _, sql, _ in conn.calls]
    assert any("FOR UPDATE" in q for q in queries)


def test_an_upload_joins_the_family_of_the_same_name(monkeypatch):
    conn = _site_conn(fetchval={"FOR UPDATE": SITE, "SELECT count(*)": 3, "SELECT family FROM cappe_studio_fonts": FAMILY,
                                "SELECT 1 FROM cappe_studio_fonts": None},
                      fetchrow={"WHERE site_id = $1 AND sha = $2": None, "INSERT INTO cappe_studio_fonts": row()})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        assert _upload(client, name="  canela ").status_code == 201
    assert conn.args_for("INSERT INTO cappe_studio_fonts")[1] == FAMILY
    assert conn.args_for("SELECT family FROM cappe_studio_fonts") == (SITE, "canela")


def test_the_same_file_again_is_the_face_it_already_is(monkeypatch):
    existing = row()
    conn = _site_conn(fetchval={"FOR UPDATE": SITE, "SELECT count(*)": 1},
                      fetchrow={"WHERE site_id = $1 AND sha = $2": existing})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        res = _upload(client)
    assert res.status_code == 200 and res.json()["id"] == str(existing["id"])
    assert not any("INSERT" in sql for _, sql, _ in conn.calls)


def test_the_same_file_hidden_is_shown_again(monkeypatch):
    hidden = row(hidden_at=NOW)
    conn = _site_conn(fetchval={"FOR UPDATE": SITE, "SELECT count(*)": 1, "SELECT 1 FROM cappe_studio_fonts": None},
                      fetchrow={"WHERE site_id = $1 AND sha = $2": hidden, "SET hidden_at = NULL": row()})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        res = _upload(client)
    assert res.status_code == 200 and res.json()["hidden"] is False


@pytest.mark.parametrize("count, taken, code", [(0, True, "duplicate_style"), (C.MAX_FONTS_PER_SITE, None, "too_many_fonts")])
def test_a_clash_is_a_409_with_its_code(monkeypatch, count, taken, code):
    conn = _site_conn(fetchval={"FOR UPDATE": SITE, "SELECT count(*)": count, "SELECT family FROM cappe_studio_fonts": FAMILY,
                                "SELECT 1 FROM cappe_studio_fonts": taken},
                      fetchrow={"WHERE site_id = $1 AND sha = $2": None})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        res = _upload(client)
    assert res.status_code == 409 and res.json()["detail"]["code"] == code


def test_an_upload_needs_the_licence_a_name_and_a_readable_font(monkeypatch):
    cm, storage = _client(monkeypatch, _site_conn())
    with cm as client:
        no_licence = _upload(client, licence_attested="false")
        no_name = _upload(client, name=" \n ")
        junk = _upload(client, data=b"not a font at all")
    assert no_licence.status_code == 422 and no_licence.json()["detail"]["code"] == "licence_required"
    assert no_name.status_code == 422
    assert junk.status_code == 422 and junk.json()["detail"]["code"] == "bad_font"
    storage.put_key.assert_not_called()


def test_an_upload_needs_a_magazine_plan(monkeypatch):
    cm, storage = _client(monkeypatch, _site_conn(), plan_has_magazine=False)
    with cm as client:
        res = _upload(client)
    assert res.status_code == 402 and res.json()["detail"]["code"] == "plan_required"
    storage.put_key.assert_not_called()


def test_a_reader_account_has_no_fonts(monkeypatch):
    reader = SimpleNamespace(id=ACCOUNT.id, plan="free", account_type="reader")
    cm, _ = _client(monkeypatch, _site_conn(), account=reader)
    with cm as client:
        responses = [client.get(f"/sites/{SITE}/studio/fonts"), _upload(client),
                     client.patch(f"/sites/{SITE}/studio/fonts/families/{FAMILY}", json={"name": "X"}),
                     client.delete(f"/sites/{SITE}/studio/fonts/{uuid4()}")]
    assert {r.status_code for r in responses} == {403}
    assert responses[0].json()["detail"]["code"] == "reader_account"


def test_the_list_is_the_sites_visible_faces(monkeypatch):
    conn = _site_conn(fetch={"FROM cappe_studio_fonts": [row()]})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        res = client.get(f"/sites/{SITE}/studio/fonts")
    assert res.status_code == 200 and res.json()["fonts"][0]["family"] == FAMILY
    sql = conn.sql_for("fetch")[0]
    assert "site_id = $1" in sql and "hidden_at IS NULL" in sql


def test_another_accounts_site_is_not_found(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_sites WHERE id = $1 AND account_id": None})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        assert client.get(f"/sites/{SITE}/studio/fonts").status_code == 404
        assert _upload(client).status_code == 404


@pytest.mark.parametrize("renamed, taken, status", [([{"id": uuid4()}], None, 200), ([], None, 404), ([], 1, 409)])
def test_renaming_a_family(monkeypatch, renamed, taken, status):
    conn = _site_conn(fetchval={"FOR UPDATE": SITE, "SELECT 1 FROM cappe_studio_fonts": taken},
                      fetch={"UPDATE cappe_studio_fonts SET name": renamed})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        res = client.patch(f"/sites/{SITE}/studio/fonts/families/{FAMILY}", json={"name": " Canela Deck "})
        bad = client.patch(f"/sites/{SITE}/studio/fonts/families/Inter", json={"name": "X"})
    assert res.status_code == status and bad.status_code == 404
    if status == 200:
        assert res.json() == {"family": FAMILY, "name": "Canela Deck"}
        assert conn.args_for("UPDATE cappe_studio_fonts SET name") == (SITE, FAMILY, "Canela Deck")


@pytest.mark.parametrize("found, status", [(uuid4(), 204), (None, 404)])
def test_hiding_a_face_never_deletes_it(monkeypatch, found, status):
    font_id = uuid4()
    conn = _site_conn(fetchval={"SET hidden_at = COALESCE": found})
    cm, _ = _client(monkeypatch, conn)
    with cm as client:
        res = client.delete(f"/sites/{SITE}/studio/fonts/{font_id}")
    assert res.status_code == status
    assert conn.args_for("SET hidden_at") == (font_id, SITE)
    assert not any("DELETE" in sql for _, sql, _ in conn.calls)


# ── the public file route ────────────────────────────────────────────────────

@pytest.fixture
def custom_face(monkeypatch, tmp_path):
    data, _ = C.process(ttf())
    sha = hashlib.sha256(data).hexdigest()
    (tmp_path / f"{sha}.ttf").write_bytes(data)
    monkeypatch.setenv("CAPPE_FONTS_DIR", str(tmp_path))
    monkeypatch.setattr(faces, "_index", lambda: ({}, {}))
    monkeypatch.setattr(public_fonts, "_cache", public_fonts.OrderedDict())
    monkeypatch.setattr(public_fonts, "_custom", public_fonts.OrderedDict())
    known = {sha}
    monkeypatch.setattr(public_fonts, "known_sha", AsyncMock(side_effect=lambda c, s: s in known))
    monkeypatch.setattr(public_fonts, "get_connection", lambda: QueryConn())
    return sha, data


def test_an_uploaded_face_is_served_like_the_catalogs(custom_face):
    sha, data = custom_face
    with route_client(public_fonts.router) as client:
        res = client.get(f"/public/fonts/{sha}.ttf")
        again = client.get(f"/public/fonts/{sha}.ttf")
        unknown = client.get(f"/public/fonts/{'d' * 64}.ttf")
        odd = client.get("/public/fonts/not-a-sha.ttf")
    assert res.status_code == 200 and res.content == data and res.headers["cache-control"].endswith("immutable")
    assert again.status_code == 200 and sha in public_fonts._custom
    assert public_fonts.known_sha.await_count == 2  # the known one once, the unknown one; never the odd name
    assert unknown.status_code == 404 and odd.status_code == 404


def test_a_big_uploaded_face_is_not_kept_in_memory(monkeypatch):
    data = b"\x00" * (public_fonts._KEEP_MAX_BYTES + 1)
    sha = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(public_fonts, "_cache", public_fonts.OrderedDict())
    monkeypatch.delenv("CAPPE_FONTS_DIR", raising=False)
    storage = AsyncMock()
    storage.get_key.return_value = data
    monkeypatch.setattr(public_fonts, "get_storage", lambda: storage)
    assert asyncio.run(public_fonts.font_bytes(sha)) == data and sha not in public_fonts._cache


# ── the migration and the catalog build ─────────────────────────────────────

def test_the_migration_follows_identity_and_its_downgrade_refuses_while_fonts_exist():
    path = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "cappefont01_studio_fonts.py"
    text = path.read_text()
    assert 'down_revision = "cappeidentity01"' in text
    down = text[text.index("def downgrade"):]
    assert down.index("RAISE EXCEPTION") < down.index("DROP TABLE cappe_studio_fonts")
    assert "WHERE hidden_at IS NULL" in text and "UNIQUE (site_id, sha)" in text


def test_the_catalog_build_uses_the_shared_steps():
    text = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "build_magazine_fonts.py").read_text()
    assert "from app.cappe.services.magazine.studio.font_build import build_face, features, metrics" in text
    assert "def build_face" not in text and "LATIN = " not in text
    compile(text, "build_magazine_fonts.py", "exec")
    from app.cappe.services.magazine.studio import font_build
    face = font_build.build_face(TTFont(BytesIO(variable()), recalcTimestamp=False), 700)
    assert "fvar" not in face and face["hhea"].lineGap == 0 and face.getBestCmap()[ord("A")]



def test_the_columns_named_after_sql_keywords_are_always_quoted():
    # `asc` and `desc` are reserved in Postgres: unquoted, the migration (and any query naming them) is a syntax error.
    root = pathlib.Path(__file__).resolve().parents[2]
    for path in ("alembic/versions/cappefont01_studio_fonts.py", "app/cappe/services/magazine/studio/custom_fonts.py"):
        for line in (root / path).read_text().splitlines():
            if any(word in line for word in ("INTEGER", "SELECT", "INSERT", "_COLS")):
                assert not re.search(r'(?<![\w"])(asc|desc)(?![\w"])', line), f"{path}: {line.strip()}"
