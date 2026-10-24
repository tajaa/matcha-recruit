"""An owner's own licensed fonts, for one magazine (site).

An upload (TTF, OTF, WOFF or WOFF2, up to `MAX_UPLOAD_BYTES`) is read by
fontTools and written again from what it parsed, never stored as it came:

  * a variable font is fixed at its default instance;
  * PostScript (CFF/CFF2) outlines become TrueType ones (cu2qu), so every
    stored face is a `.ttf` served and loaded like the catalog's
    (`format('truetype')`, HarfBuzz in the Studio);
  * only the tables the subsetter knows are kept (every glyph and every
    OpenType layout feature, hinting dropped), so nothing unknown rides along;
  * the vertical metrics are made one as the catalog's are
    (`font_build.normalize_metrics`), so a baseline lands where the Studio
    measured it.

A face is a row of `cappe_studio_fonts` and its file `cappe/fonts/<sha>.ttf`.
Pages name it by family key (`u-<16 hex>`), never by its real name, and a
saved document carries the records of the faces it sets (`doc_faces` →
`doc.faces`), so the reader and the renderers need nothing else. Faces are
hidden, never deleted: a page that names one keeps working.
"""
from __future__ import annotations

import json
import math
import re
import secrets
import unicodedata
from io import BytesIO
from typing import Any, Optional
from uuid import UUID

from asyncpg.exceptions import UniqueViolationError

FAMILY_RE = re.compile(r"^u-[0-9a-f]{16}$")
_FAMILY_ANY = re.compile(r"u-[0-9a-f]{16}")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_FONTS_PER_SITE = 60
MAX_NAME = 60
_UNREADABLE = "This file isn't a font the Studio can read."
_REQUIRED = ("cmap", "head", "hhea", "OS/2", "hmtx")
# Bitmap and SVG glyphs: not text faces, and more parser surface for nothing.
_DROP = ["DSIG", "STAT", "SVG ", "sbix", "CBDT", "CBLC", "EBDT", "EBLC", "EBSC"]

_COLS = ('id, family, name, weight, italic, sha, bytes, upm, "asc", "desc", cap, x, features, filename, '
         "created_at, hidden_at")


class FontError(ValueError):
    """The upload can't be used; the message is for the owner."""


class FontConflict(Exception):
    """The upload clashes with the site's fonts (`code` for the client)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_custom(name: Any) -> bool:
    return isinstance(name, str) and bool(FAMILY_RE.match(name))


def clean_name(value: Any) -> str:
    """A family's display name: printable, single-spaced, at most 60 characters."""
    if not isinstance(value, str):
        return ""
    text = "".join(c for c in value if unicodedata.category(c)[0] != "C")
    return " ".join(text.split())[:MAX_NAME].strip()


def round_weight(value: Any, default: int = 400) -> int:
    """A weight to the nearest hundred (half up), 100–900."""
    try:
        w = math.floor(float(value) / 100.0 + 0.5) * 100
    except (TypeError, ValueError, OverflowError):
        return default
    return max(100, min(900, w))


# ── reading an upload ────────────────────────────────────────────────────────

def _kind(data: bytes) -> str:
    head = data[:4]
    if head == b"ttcf":
        raise FontError("Font collections (.ttc) aren't supported. Upload each face on its own.")
    if head in (b"\x00\x01\x00\x00", b"true"):
        return "ttf"
    if head == b"OTTO":
        return "otf"
    if head == b"wOFF":
        return "woff"
    if head == b"wOF2":
        return "woff2"
    raise FontError("Upload a TTF, OTF, WOFF or WOFF2 font file.")


def _to_quadratic(font) -> None:
    """PostScript outlines as TrueType ones (fontTools' otf2ttf snippet)."""
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import newTable

    order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
        glyphs[name] = pen.glyph()
    font["loca"] = newTable("loca")
    font["glyf"] = glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = glyphs
    for tag in ("CFF ", "CFF2", "VORG"):
        if tag in font:
            del font[tag]
    glyf.compile(font)
    hmtx = font["hmtx"]
    for name, glyph in glyf.glyphs.items():
        if hasattr(glyph, "xMin"):
            hmtx[name] = (hmtx[name][0], glyph.xMin)
    font["maxp"] = maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    maxp.maxZones, maxp.maxTwilightPoints, maxp.maxStorage = 1, 0, 0
    maxp.maxFunctionDefs = maxp.maxInstructionDefs = maxp.maxStackElements = maxp.maxSizeOfInstructions = 0
    maxp.maxComponentElements = max((len(getattr(g, "components", None) or []) for g in glyphs.values()), default=0)
    maxp.compile(font)
    post = font["post"]
    post.formatType = 3.0
    post.extraNames, post.mapping = [], {}
    post.glyphOrder = order
    font.sfntVersion = "\x00\x01\x00\x00"


def _keep_all(font) -> None:
    """Every glyph and layout feature through the subsetter: what it doesn't
    know is dropped (`passthrough_tables` off), and so is hinting."""
    from fontTools import subset

    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.layout_scripts = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.name_legacy = True
    opts.notdef_outline = True
    opts.notdef_glyph = True
    opts.hinting = False
    opts.glyph_names = False
    opts.legacy_kern = True
    opts.drop_tables += _DROP
    sub = subset.Subsetter(opts)
    sub.populate(glyphs=font.getGlyphOrder())
    sub.subset(font)


def _suggested_name(font) -> str:
    names = font["name"] if "name" in font else None
    if names is None:
        return ""
    for nid in (16, 1):
        value = names.getDebugName(nid)
        if value and clean_name(value):
            return clean_name(value)
    return ""


def process(data: bytes) -> tuple[bytes, dict]:
    """The upload as a TrueType face the Studio can set, and what it knows
    about it. Raises `FontError` for anything it can't use."""
    from fontTools.ttLib import TTFont, TTLibError

    from .font_build import features, instance, metrics, normalize_metrics

    if len(data) > MAX_UPLOAD_BYTES:
        raise FontError("A font file can be at most 10 MB.")
    _kind(data)
    try:
        font = TTFont(BytesIO(data), lazy=False, recalcTimestamp=False)
        if any(tag not in font for tag in _REQUIRED):
            raise FontError(_UNREADABLE)
        cmap = font.getBestCmap() or {}
        if not any(cp in cmap for cp in (*range(0x41, 0x5B), *range(0x61, 0x7B))):
            raise FontError("This font has no Latin letters to set.")
        os2, head = font["OS/2"], font["head"]
        weight = round_weight(os2.usWeightClass)
        italic = bool(os2.fsSelection & 1) or bool(head.macStyle & 2)
        suggested = _suggested_name(font)
        font = instance(font)
        if "CFF " in font or "CFF2" in font:
            _to_quadratic(font)
        font.flavor = None
        _keep_all(font)
        normalize_metrics(font)
        font.recalcTimestamp = False
        buf = BytesIO()
        font.save(buf)
        out = buf.getvalue()
        meta = {"weight": weight, "italic": italic, **metrics(font), "features": features(font),
                "suggested_name": suggested}
    except FontError:
        raise
    except (TTLibError, Exception) as exc:  # fontTools raises many kinds on a bad file
        raise FontError(_UNREADABLE) from exc
    if len(out) > MAX_OUTPUT_BYTES:
        raise FontError("This font is too big once prepared. Upload a smaller file.")
    if meta["upm"] <= 0 or meta["asc"] <= 0:
        raise FontError(_UNREADABLE)
    return out, meta


# ── records ──────────────────────────────────────────────────────────────────

def doc_face(row: Any) -> dict:
    """A face as a document carries it (`doc.faces`)."""
    return {
        "family": row["family"], "name": row["name"], "weight": int(row["weight"]), "italic": bool(row["italic"]),
        "sha": row["sha"], "bytes": int(row["bytes"] or 0), "upm": int(row["upm"] or 1000),
        "asc": int(row["asc"] or 0), "desc": int(row["desc"] or 0), "cap": int(row["cap"] or 0),
        "x": int(row["x"] or 0), "features": sorted(row["features"] or []),
    }


def record(row: Any) -> dict:
    """A face as the owner's font list shows it."""
    created = row["created_at"]
    return {**doc_face(row), "id": str(row["id"]), "filename": row["filename"],
            "hidden": row["hidden_at"] is not None,
            "created_at": created.isoformat() if hasattr(created, "isoformat") else created}


# ── the site's fonts ─────────────────────────────────────────────────────────

async def list_fonts(conn, site_id: UUID, *, include_hidden: bool = False) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM cappe_studio_fonts WHERE site_id = $1"
        + ("" if include_hidden else " AND hidden_at IS NULL")
        + " ORDER BY lower(name), name, weight, italic, created_at, id",
        site_id,
    )
    return [record(r) for r in rows]


async def create_font(conn, *, site_id: UUID, account_id: Optional[UUID], name: str, sha: str, size: int,
                      meta: dict, weight: int, italic: bool, filename: Optional[str]) -> tuple[dict, bool]:
    """Add a face to the site (the file is already stored). Returns its
    record and whether it is new; the same file again is the face it already
    is (shown again if it was hidden). Raises `FontConflict`."""
    async with conn.transaction():
        # One upload per site at a time between the checks and the insert.
        await conn.fetchval("SELECT id FROM cappe_sites WHERE id = $1 FOR UPDATE", site_id)
        visible = await conn.fetchval(
            "SELECT count(*) FROM cappe_studio_fonts WHERE site_id = $1 AND hidden_at IS NULL", site_id)
        same = await conn.fetchrow(f"SELECT {_COLS} FROM cappe_studio_fonts WHERE site_id = $1 AND sha = $2",
                                   site_id, sha)
        if same is not None:
            if same["hidden_at"] is None:
                return record(same), False
            if visible >= MAX_FONTS_PER_SITE:
                raise _too_many()
            if await _style_taken(conn, site_id, same["family"], same["weight"], same["italic"]):
                raise _duplicate()
            row = await conn.fetchrow(
                f"UPDATE cappe_studio_fonts SET hidden_at = NULL WHERE id = $1 RETURNING {_COLS}", same["id"])
            return record(row), False
        if visible >= MAX_FONTS_PER_SITE:
            raise _too_many()
        family = await conn.fetchval(
            "SELECT family FROM cappe_studio_fonts WHERE site_id = $1 AND hidden_at IS NULL "
            "AND lower(name) = lower($2) ORDER BY created_at, id LIMIT 1", site_id, name,
        ) or f"u-{secrets.token_hex(8)}"
        if await _style_taken(conn, site_id, family, weight, italic):
            raise _duplicate()
        try:
            row = await conn.fetchrow(
                "INSERT INTO cappe_studio_fonts (site_id, family, name, weight, italic, sha, bytes, upm, \"asc\", \"desc\", "
                "cap, x, features, filename, licence_attested_at, created_by) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), $15) "
                f"RETURNING {_COLS}",
                site_id, family, name, weight, italic, sha, size, meta["upm"], meta["asc"], meta["desc"],
                meta["cap"], meta["x"], list(meta["features"]), (filename or "")[:200] or None, account_id,
            )
        except UniqueViolationError as exc:
            raise _duplicate() from exc
    return record(row), True


async def _style_taken(conn, site_id: UUID, family: str, weight: int, italic: bool) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_studio_fonts WHERE site_id = $1 AND family = $2 AND weight = $3 AND italic = $4 "
        "AND hidden_at IS NULL", site_id, family, weight, italic))


def _duplicate() -> FontConflict:
    return FontConflict("duplicate_style", "This family already has that weight and style. Hide it first to replace it.")


def _too_many() -> FontConflict:
    return FontConflict("too_many_fonts", f"A magazine can have {MAX_FONTS_PER_SITE} fonts. Hide one to add another.")


async def rename_family(conn, site_id: UUID, family: str, name: str) -> int:
    """Rename every face of a family (hidden ones too). Returns how many."""
    async with conn.transaction():
        await conn.fetchval("SELECT id FROM cappe_sites WHERE id = $1 FOR UPDATE", site_id)
        taken = await conn.fetchval(
            "SELECT 1 FROM cappe_studio_fonts WHERE site_id = $1 AND family <> $2 AND hidden_at IS NULL "
            "AND lower(name) = lower($3)", site_id, family, name)
        if taken:
            raise FontConflict("name_taken", "Another of this magazine's fonts has that name.")
        rows = await conn.fetch("UPDATE cappe_studio_fonts SET name = $3 WHERE site_id = $1 AND family = $2 RETURNING id",
                                site_id, family, name)
    return len(rows)


async def hide_font(conn, site_id: UUID, font_id: UUID) -> bool:
    """Hide a face from the picker (pages that set it keep it). False when
    the site has no such face."""
    row = await conn.fetchval(
        "UPDATE cappe_studio_fonts SET hidden_at = COALESCE(hidden_at, NOW()) WHERE id = $1 AND site_id = $2 RETURNING id",
        font_id, site_id)
    return row is not None


async def doc_faces(conn, site_id: UUID, raw_doc: Any) -> dict[str, list[dict]]:
    """The site's faces of every family key the document names, as
    `schema.normalize_doc` takes them: {family: [face, ...]}, one face per
    weight and style (a visible one before a hidden one). Hidden faces count:
    a page that set one keeps it."""
    try:
        text = json.dumps(raw_doc, default=str)
    except (TypeError, ValueError):
        return {}
    keys = sorted(set(_FAMILY_ANY.findall(text)))[:200]
    if not keys:
        return {}
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM cappe_studio_fonts WHERE site_id = $1 AND family = ANY($2::text[]) "
        "ORDER BY family, weight, italic, (hidden_at IS NOT NULL), created_at, id",
        site_id, keys,
    )
    out: dict[str, list[dict]] = {}
    seen: set[tuple] = set()
    for r in rows:
        style = (r["family"], int(r["weight"]), bool(r["italic"]))
        if style in seen:
            continue
        seen.add(style)
        out.setdefault(r["family"], []).append(doc_face(r))
    return out


async def known_sha(conn, sha: str) -> bool:
    """Whether any site has a face with this file (the public font route)."""
    return bool(await conn.fetchval("SELECT 1 FROM cappe_studio_fonts WHERE sha = $1 LIMIT 1", sha))
