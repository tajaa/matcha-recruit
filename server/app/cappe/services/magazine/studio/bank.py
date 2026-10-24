"""The Gummfit-curated bank in Gummfit Studio's side panel
(`cappe_studio_bank`, cappemag11).

Photos and graphics a Matcha admin picks for every site
(`routes/studio_bank_admin.py`, hey-matcha.com/admin/cappe → Studio bank). The
Studio shows them first: photos under Photos → Gummfit
(`routes/library.py`), graphics under Elements → From Gummfit
(`routes/public/graphics.py`).

  * A photo is stored once, with its responsive sizes. Placing it gives the
    site a library row (`cappe_assets`, kind `stock`, source `gummfit`,
    source_id the bank row) that points at the same files and prints the
    photo's credit, so nothing is downloaded or copied, and placing it again
    finds that row. A bank photo can be deleted: the rows made from it, and
    the files, stay (library rows never delete their files).
  * A graphic is an SVG cleaned like the built-in bank's
    (`graphics.clean_svg`) and stored beside them by its sha256
    (`cappe/graphics/<sha>.svg`), so the same route serves it and both
    renderers draw it. Pages name it by sha, so a graphic is hidden, never
    deleted, and the graphics a page names that the manifest doesn't are
    looked up here when it is saved (`doc_graphics`).
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Optional
from uuid import UUID

from ...cappe_assets import COLUMNS as ASSET_COLUMNS, row as asset_row
from . import graphics, limits

KINDS = ("photo", "graphic")
STATUSES = ("live", "hidden")
LICENSES = ("gummfit", "cc0", "pdm", "by", "by-sa")
SOURCE = "gummfit"
PROVIDER = "Gummfit"
MAX_NAME = 120
MAX_COLLECTION = 60
MAX_CREATOR = 200
MAX_TAGS = 12
MAX_TAG = 40
MAX_CREDIT = 500
PAGE_MAX = 60
PICKS_MAX = 500

COLUMNS = (
    "id, kind, name, tags, collection, status, sort_order, url, variants, width, height, bytes, mime, creator, "
    "credit_line, license, source_url, sha, mono, fit, graphic_group, w, h, created_by_email, created_at, updated_at"
)


class Exists(ValueError):
    """That graphic is already in the bank (or built into the Studio)."""


def row(r) -> dict[str, Any]:
    d = dict(r)
    if isinstance(d.get("variants"), str):
        d["variants"] = json.loads(d["variants"])
    d["tags"] = list(d.get("tags") or [])
    return d


# ── cleaning what an admin types ─────────────────────────────────────────────

def clean_name(value: Any) -> str:
    return " ".join(str(value or "").split())[:MAX_NAME]


def clean_collection(value: Any) -> Optional[str]:
    return " ".join(str(value or "").split())[:MAX_COLLECTION] or None


def clean_tags(value: Any) -> list[str]:
    """Tags from a list or a comma-separated string: lower-case, each once."""
    parts: Iterable[Any] = value.split(",") if isinstance(value, str) else (value or [])
    seen: dict[str, None] = {}
    for part in parts:
        tag = " ".join(str(part).lower().split())[:MAX_TAG]
        if tag:
            seen.setdefault(tag, None)
    return list(seen)[:MAX_TAGS]


def credit(creator: Optional[str], credit_line: Optional[str]) -> str:
    """What a placed photo prints under it: the admin's words, else its
    creator and Gummfit, else Gummfit."""
    if credit_line and credit_line.strip():
        return " ".join(credit_line.split())[:MAX_CREDIT]
    return f"{' '.join(creator.split())} / {PROVIDER}"[:MAX_CREDIT] if creator and creator.strip() else PROVIDER


_GRADIENT = re.compile(rb"<(?:linearGradient|radialGradient|pattern|image)\b", re.I)
# What draws paint, and what never shows its own (a clip path or mask only cuts).
_DRAWN = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "textPath"}
_UNSEEN = {"clipPath", "mask", "title", "desc", "metadata"}
_NAMED = {"black": "#000000", "white": "#ffffff"}


def _paint(value: str, colour: str) -> Optional[str]:
    """A fill or stroke as one comparable string: None for no paint, `url(`
    for a paint server, the element's `color` for currentColor."""
    v = value.strip().lower()
    if v in ("none", "transparent"):
        return None
    if v == "currentcolor":
        return colour
    if v.startswith("url("):
        return "url("
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        v = "#" + "".join(c * 2 for c in v[1:])
    return _NAMED.get(v, v)


def _declared(el) -> dict[str, str]:
    """An element's fill, stroke and color, from its attributes and its style
    attribute (which wins, as in CSS)."""
    out = {k: el.get(k) for k in ("fill", "stroke", "color") if el.get(k) is not None}
    for part in (el.get("style") or "").split(";"):
        name, _, value = part.partition(":")
        if name.strip().lower() in ("fill", "stroke", "color") and value.strip():
            out[name.strip().lower()] = value
    return {k: v for k, v in out.items() if v.strip().lower() != "inherit"}


def one_colour(svg: bytes) -> bool:
    """Whether a cleaned SVG is drawn in one colour: the Studio then shows it
    as a silhouette in any colour. Every drawn shape's paint counts as SVG
    paints it: a fill nobody set is black, fills, strokes and color are
    inherited from the groups around it, and currentColor is that color
    (black in a picture). A gradient, a pattern, a picture or two paints make
    it colourful, kept as drawn; so does anything that isn't readable XML."""
    if _GRADIENT.search(svg):
        return False
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return False
    paints: set[str] = set()

    def walk(el, fill: str, stroke: str, colour: str) -> None:
        tag = el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""
        if tag in _UNSEEN:
            return
        own = _declared(el)
        if "color" in own:
            colour = _paint(own["color"], colour) or colour
        fill, stroke = own.get("fill", fill), own.get("stroke", stroke)
        if tag in _DRAWN:
            for value in ((stroke,) if tag == "line" else (fill, stroke)):
                p = _paint(value, colour)
                if p:
                    paints.add(p)
        for child in el:
            walk(child, fill, stroke, colour)

    walk(root, "black", "none", "#000000")
    return "url(" not in paints and len(paints) <= 1


def default_fit(group: str) -> str:
    """How a graphic fills its box when placed: dividers and shapes stretch,
    patterns repeat, the rest keep their shape (as `graphics_own` does)."""
    return {"lines": "stretch", "shapes": "stretch", "patterns": "tile"}.get(group, "contain")


# ── the Studio's side ────────────────────────────────────────────────────────

async def doc_graphics(conn, raw_doc: Any) -> dict[str, dict]:
    """The bank's graphics a document names that the built-in manifest
    doesn't, as `schema.normalize_doc` reads them. Hidden ones count: a page
    keeps a graphic it already has."""
    items = raw_doc.get("items") if isinstance(raw_doc, dict) else None
    items = list(items) if isinstance(items, list) else []
    identity = raw_doc.get("identity") if isinstance(raw_doc, dict) else None
    if isinstance(identity, dict) and isinstance(identity.get("parents"), list):
        for parent in identity["parents"][:8]:
            if isinstance(parent, dict) and isinstance(parent.get("items"), list):
                items.extend(parent["items"][:80])
    srcs = sorted({
        i["src"] for i in items
        if isinstance(i, dict) and i.get("kind") == "graphic" and graphics.is_sha(i.get("src"))
        and graphics.by_sha(i["src"]) is None
    })[:limits.MAX_ITEMS]  # no more than a document can hold, so a valid one is never cut short
    if not srcs:
        return {}
    rows = await conn.fetch(
        "SELECT sha, mono, fit FROM cappe_studio_bank WHERE kind = 'graphic' AND sha = ANY($1::text[])", srcs,
    )
    return {r["sha"]: {"sha": r["sha"], "mono": r["mono"], "fit": r["fit"]} for r in rows}


async def has_graphic(conn, sha: str) -> bool:
    return bool(await conn.fetchval("SELECT 1 FROM cappe_studio_bank WHERE kind = 'graphic' AND sha = $1", sha))


async def graphic_picks(conn) -> list[dict]:
    """The live graphics, as the side panel's cards, in the admin's order."""
    rows = await conn.fetch(
        "SELECT sha, name, graphic_group, mono, fit, w, h, tags, collection FROM cappe_studio_bank "
        f"WHERE kind = 'graphic' AND status = 'live' ORDER BY sort_order, created_at DESC LIMIT {PICKS_MAX}"
    )
    return [{"sha": r["sha"], "name": r["name"], "group": r["graphic_group"], "mono": r["mono"], "fit": r["fit"],
             "w": r["w"], "h": r["h"], "tags": list(r["tags"] or []), "collection": r["collection"]} for r in rows]


def _like(word: str) -> str:
    return "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def photos(conn, q: str = "", collection: Optional[str] = None, offset: int = 0,
                 limit: int = PAGE_MAX) -> dict:
    """Live photos matching every word of `q` (in the name, a tag or the
    collection), newest of the admin's order first, and the collections."""
    where, args = ["kind = 'photo'", "status = 'live'"], []
    if collection:
        args.append(collection)
        where.append(f"collection = ${len(args)}")
    for word in q.lower().split()[:8]:
        args.append(_like(word))
        n = len(args)
        where.append(f"(lower(name) LIKE ${n} OR lower(coalesce(collection, '')) LIKE ${n} "
                     f"OR EXISTS (SELECT 1 FROM unnest(tags) t WHERE t LIKE ${n}))")
    sql_where = " AND ".join(where)
    total = await conn.fetchval(f"SELECT count(*) FROM cappe_studio_bank WHERE {sql_where}", *args)
    rows = await conn.fetch(
        f"SELECT id, name, url, variants, width, height, credit_line, collection FROM cappe_studio_bank "
        f"WHERE {sql_where} ORDER BY sort_order, created_at DESC "
        f"OFFSET {max(0, int(offset))} LIMIT {max(1, min(int(limit), PAGE_MAX))}",
        *args,
    )
    collections = await conn.fetch(
        "SELECT DISTINCT collection FROM cappe_studio_bank "
        "WHERE kind = 'photo' AND status = 'live' AND collection IS NOT NULL ORDER BY collection"
    )
    return {"total": total, "items": [row(r) for r in rows], "collections": [r["collection"] for r in collections]}


async def place_photo(conn, *, account_id: UUID, site_id: UUID, item_id: UUID) -> Optional[dict]:
    """The site's library row for a live bank photo, made the first time it is
    placed. None when the photo isn't in the bank (or is hidden)."""
    p = await conn.fetchrow(
        f"SELECT {COLUMNS} FROM cappe_studio_bank WHERE id = $1 AND kind = 'photo' AND status = 'live'", item_id,
    )
    if p is None:
        return None
    created = await conn.fetchrow(
        f"""
        INSERT INTO cappe_assets (account_id, site_id, kind, url, source, source_id, source_url, title, creator,
                                  license, provider_label, credit_line, alt, width, height, bytes, mime, variants)
        VALUES ($1, $2, 'stock', $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17::jsonb)
        ON CONFLICT (site_id, source, source_id) WHERE source_id IS NOT NULL DO UPDATE SET updated_at = NOW()
        RETURNING {ASSET_COLUMNS}
        """,
        account_id, site_id, p["url"], SOURCE, str(p["id"]), p["source_url"], p["name"], p["creator"], p["license"],
        PROVIDER, p["credit_line"], p["name"], p["width"], p["height"], p["bytes"], p["mime"],
        p["variants"] if isinstance(p["variants"], str) else json.dumps(p["variants"] or {}),
    )
    return asset_row(created)


# ── the admin's side ─────────────────────────────────────────────────────────

async def admin_list(conn, kind: str) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {COLUMNS} FROM cappe_studio_bank WHERE kind = $1 ORDER BY sort_order, created_at DESC", kind,
    )
    return [row(r) for r in rows]


async def get_item(conn, item_id: UUID) -> Optional[dict]:
    found = await conn.fetchrow(f"SELECT {COLUMNS} FROM cappe_studio_bank WHERE id = $1", item_id)
    return row(found) if found else None


async def add_photo(conn, *, url: str, variants: dict, width: int, height: int, size_bytes: int, mime: str,
                    name: str, tags: list[str], collection: Optional[str], creator: Optional[str],
                    credit_line: str, license: str, source_url: Optional[str], email: str,
                    sort_order: int = 0) -> dict:
    created = await conn.fetchrow(
        f"""
        INSERT INTO cappe_studio_bank (kind, name, tags, collection, url, variants, width, height, bytes, mime,
                                       creator, credit_line, license, source_url, created_by_email, sort_order)
        VALUES ('photo', $1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        RETURNING {COLUMNS}
        """,
        name, tags, collection, url, json.dumps(variants), width, height, size_bytes, mime, creator, credit_line,
        license, source_url, email, sort_order,
    )
    return row(created)


async def add_graphic(conn, *, sha: str, w: float, h: float, mono: bool, fit: str, group: str, name: str,
                      tags: list[str], collection: Optional[str], email: str) -> dict:
    created = await conn.fetchrow(
        f"""
        INSERT INTO cappe_studio_bank (kind, name, tags, collection, sha, mono, fit, graphic_group, w, h,
                                       created_by_email)
        VALUES ('graphic', $1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (sha) DO NOTHING
        RETURNING {COLUMNS}
        """,
        name, tags, collection, sha, mono, fit, group, w, h, email,
    )
    if created is None:
        raise Exists("That graphic is already in the bank.")
    return row(created)


EDITABLE = ("name", "tags", "collection", "status", "sort_order", "creator", "credit_line", "license", "source_url")
PHOTO_ONLY = ("creator", "credit_line", "license", "source_url")


async def update_item(conn, item_id: UUID, fields: dict[str, Any]) -> Optional[dict]:
    """Write already-checked fields (names from `EDITABLE` only)."""
    unknown = set(fields) - set(EDITABLE)
    if unknown:  # names are written into the SQL: never let anything else through
        raise ValueError(", ".join(sorted(unknown)))
    if not fields:
        return await get_item(conn, item_id)
    names = list(fields)
    sets = ", ".join(f"{name} = ${i + 2}" for i, name in enumerate(names))
    updated = await conn.fetchrow(
        f"UPDATE cappe_studio_bank SET {sets}, updated_at = NOW() WHERE id = $1 RETURNING {COLUMNS}",
        item_id, *(fields[n] for n in names),
    )
    return row(updated) if updated else None


async def delete_photo(conn, item_id: UUID) -> bool:
    """Take a photo out of the bank. Sites that placed it keep their copy."""
    result = await conn.execute("DELETE FROM cappe_studio_bank WHERE id = $1 AND kind = 'photo'", item_id)
    return result != "DELETE 0"
