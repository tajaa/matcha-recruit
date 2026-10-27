"""The mood-board tables (`cappeboard01`) and the shape a pin is answered in.

Every query names the site, so a board or pin id from another site is simply
not found. Adding a pin takes the site's advisory lock between the counts and
the insert, so two uploads at once can't both fit under a board's pin limit or
the site's storage limit.

Deleting a board or a site takes the same lock before it reads which files to
remove, so a pin can't be added between that read and the cascade (its files
would never be removed). A pin added after the board is gone is `BoardGone`.

A pin is answered without its storage paths: its pictures and file are signed
links naming the pin (`files.link`, looked up again by `file_for`), and a
library picture's are its public CDN sizes.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from .. import cappe_assets
from . import files
from .limits import MAX_BOARDS_PER_SITE, MAX_PINS_PER_BOARD, MAX_SITE_BYTES, Z_MAX


class BoardLimit(Exception):
    """The site has as many boards, or a board as many pins, as it may."""


class SiteFull(Exception):
    """The site's pinned files would pass `MAX_SITE_BYTES`."""


class BoardGone(Exception):
    """The board was deleted before the pin could be added."""


BOARD_COLUMNS = "b.id, b.title, b.created_at, b.updated_at"
PIN_COLUMNS = (
    "p.id, p.board_id, p.kind, p.x, p.y, p.w, p.h, p.rotation, p.z, p.asset_id, p.file_path, p.thumb_path, "
    "p.filename, p.mime, p.size_bytes, p.width, p.height, p.note, p.color, p.url, p.title, p.description, "
    "p.site_name, p.created_at, p.updated_at, a.url AS asset_url, a.variants AS asset_variants, "
    "a.width AS asset_width, a.height AS asset_height, a.alt AS asset_alt"
)
_PIN_FROM = "cappe_board_pins p LEFT JOIN cappe_assets a ON a.id = p.asset_id"
_OUT = ("id", "board_id", "kind", "x", "y", "w", "h", "rotation", "z", "asset_id", "filename", "mime",
        "size_bytes", "width", "height", "note", "color", "url", "title", "description", "site_name",
        "created_at", "updated_at")
INSERT_FIELDS = ("kind", "x", "y", "w", "h", "rotation", "asset_id", "file_path", "thumb_path", "filename",
                 "mime", "size_bytes", "width", "height", "note", "color", "url", "title", "description",
                 "site_name")
PATCHABLE = ("x", "y", "w", "h", "rotation", "z", "note", "color", "title")
COVERS = 4


def _sized(variants: dict, fallback: Optional[str], want: int = 960) -> Optional[str]:
    """The smallest of a library picture's WebP sizes at least `want` wide,
    else its largest, else the picture itself."""
    sizes = sorted((v for v in (variants or {}).get("webp") or [] if isinstance(v, dict) and v.get("url")),
                   key=lambda v: v.get("w") or 0)
    for size in sizes:
        if (size.get("w") or 0) >= want:
            return size["url"]
    return sizes[-1]["url"] if sizes else fallback


def pin_out(r) -> dict[str, Any]:
    d = dict(r)
    out = {k: d.get(k) for k in _OUT}
    out.update(src=None, full=None, file_url=None, alt=None, in_library=d.get("asset_id") is not None)
    if out["in_library"]:
        variants = cappe_assets.row({"variants": d.get("asset_variants")})["variants"]
        out.update(src=_sized(variants, d.get("asset_url")), full=d.get("asset_url"), alt=d.get("asset_alt"),
                   width=d.get("asset_width"), height=d.get("asset_height"))
        return out
    if d.get("thumb_path"):
        out["src"] = files.link(d["id"], "thumb")
    if d.get("file_path"):
        out["full" if d["kind"] == "image" else "file_url"] = files.link(d["id"], "full" if d["kind"] == "image" else "doc")
    return out


async def file_for(conn, pin_id: UUID, part: str) -> Optional[tuple[str, str, str]]:
    """(private path, type, name) of a pin's file for a signed link, or None
    when the pin or that file is gone (deleted, or moved to the library)."""
    row = await conn.fetchrow(
        "SELECT kind, file_path, thumb_path, mime, filename FROM cappe_board_pins WHERE id = $1", pin_id,
    )
    if row is None:
        return None
    if part == "thumb" and row["thumb_path"]:
        return row["thumb_path"], "image/webp", "thumb.webp"
    if row["file_path"] and part == ("full" if row["kind"] == "image" else "doc"):
        return row["file_path"], row["mime"] or "application/octet-stream", row["filename"] or "file"
    return None


async def _lock(conn, site_id: UUID) -> None:
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"cappe_boards:{site_id}")


async def _touch(conn, board_id: UUID) -> None:
    await conn.execute("UPDATE cappe_boards SET updated_at = NOW() WHERE id = $1", board_id)


# ── boards ──────────────────────────────────────────────────────────────────

async def list_boards(conn, site_id: UUID) -> list[dict[str, Any]]:
    """The site's boards, last changed first, each with its pin count and the
    pictures of its topmost few pins."""
    rows = await conn.fetch(
        f"""SELECT {BOARD_COLUMNS}, COUNT(p.id)::int AS pin_count
              FROM cappe_boards b LEFT JOIN cappe_board_pins p ON p.board_id = b.id
             WHERE b.site_id = $1
             GROUP BY b.id
             ORDER BY b.updated_at DESC""",
        site_id,
    )
    covers = await conn.fetch(
        f"""SELECT * FROM (
              SELECT {PIN_COLUMNS}, row_number() OVER (PARTITION BY p.board_id ORDER BY p.z DESC) AS cover_rank
                FROM {_PIN_FROM}
               WHERE p.site_id = $1 AND (p.asset_id IS NOT NULL OR p.thumb_path IS NOT NULL)
            ) ranked WHERE cover_rank <= {COVERS}""",
        site_id,
    )
    by_board: dict[Any, list[str]] = {}
    for cover in covers:
        src = pin_out(cover)["src"]
        if src:
            by_board.setdefault(cover["board_id"], []).append(src)
    return [{**dict(r), "covers": by_board.get(r["id"], [])} for r in rows]


async def get_board(conn, site_id: UUID, board_id: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(f"SELECT {BOARD_COLUMNS} FROM cappe_boards b WHERE b.id = $1 AND b.site_id = $2",
                              board_id, site_id)
    return dict(row) if row else None


async def create_board(conn, site_id: UUID, title: str) -> dict[str, Any]:
    async with conn.transaction():
        await _lock(conn, site_id)
        count = await conn.fetchval("SELECT COUNT(*) FROM cappe_boards WHERE site_id = $1", site_id)
        if (count or 0) >= MAX_BOARDS_PER_SITE:
            raise BoardLimit(f"A site can have {MAX_BOARDS_PER_SITE} boards. Delete one to start another.")
        row = await conn.fetchrow(
            "INSERT INTO cappe_boards (site_id, title) VALUES ($1, $2) RETURNING id, title, created_at, updated_at",
            site_id, title,
        )
    return {**dict(row), "pin_count": 0, "covers": []}


async def rename_board(conn, site_id: UUID, board_id: UUID, title: str) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        "UPDATE cappe_boards SET title = $3, updated_at = NOW() WHERE id = $1 AND site_id = $2 "
        "RETURNING id, title, created_at, updated_at",
        board_id, site_id, title,
    )
    return dict(row) if row else None


async def delete_board(conn, site_id: UUID, board_id: UUID) -> Optional[list[str]]:
    """Delete a board and its pins. Returns the files to remove once the
    delete has committed, or None when there was no such board."""
    async with conn.transaction():
        await _lock(conn, site_id)
        held = await conn.fetch(
            "SELECT file_path, thumb_path FROM cappe_board_pins WHERE board_id = $1 AND site_id = $2",
            board_id, site_id,
        )
        gone = await conn.fetchval("DELETE FROM cappe_boards WHERE id = $1 AND site_id = $2 RETURNING id",
                                   board_id, site_id)
    if gone is None:
        return None
    return [p for r in held for p in (r["file_path"], r["thumb_path"]) if p]


async def site_files(conn, site_id: UUID) -> list[str]:
    """Every file a site's pins keep — removed after the site is deleted. Call
    it inside the delete's transaction: it takes the site's lock, so no pin is
    added between this read and the cascade."""
    await _lock(conn, site_id)
    rows = await conn.fetch(
        "SELECT file_path, thumb_path FROM cappe_board_pins "
        "WHERE site_id = $1 AND (file_path IS NOT NULL OR thumb_path IS NOT NULL)",
        site_id,
    )
    return [p for r in rows for p in (r["file_path"], r["thumb_path"]) if p]


# ── pins ────────────────────────────────────────────────────────────────────

async def list_pins(conn, board_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"SELECT {PIN_COLUMNS} FROM {_PIN_FROM} WHERE p.board_id = $1 ORDER BY p.z, p.created_at", board_id,
    )
    return [pin_out(r) for r in rows]


async def get_pin(conn, board_id: UUID, pin_id: UUID):
    """The pin's row as stored (paths included), or None."""
    return await conn.fetchrow(f"SELECT {PIN_COLUMNS} FROM {_PIN_FROM} WHERE p.id = $1 AND p.board_id = $2",
                               pin_id, board_id)


async def library_assets(conn, site_id: UUID, pins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The library pictures a board's pins show, whole: the Studio places a
    picture by its library row."""
    ids = list(dict.fromkeys(p["asset_id"] for p in pins if p.get("asset_id")))
    if not ids:
        return []
    rows = await conn.fetch(
        f"SELECT {cappe_assets.COLUMNS} FROM cappe_assets WHERE site_id = $1 AND id = ANY($2::uuid[])", site_id, ids,
    )
    return [cappe_assets.row(r) for r in rows]


async def check_room(conn, site_id: UUID, board_id: UUID, new_bytes: int) -> None:
    """Raise when one more pin of `new_bytes` wouldn't fit. Checked before an
    upload is stored (to spare the work) and again under the lock."""
    pins = await conn.fetchval("SELECT COUNT(*) FROM cappe_board_pins WHERE board_id = $1", board_id)
    if (pins or 0) >= MAX_PINS_PER_BOARD:
        raise BoardLimit(f"A board holds {MAX_PINS_PER_BOARD} pins. Start another board for more.")
    if new_bytes:
        used = await conn.fetchval("SELECT COALESCE(SUM(size_bytes), 0) FROM cappe_board_pins WHERE site_id = $1",
                                   site_id)
        if (used or 0) + new_bytes > MAX_SITE_BYTES:
            raise SiteFull(f"Your boards hold {MAX_SITE_BYTES // (1024 * 1024 * 1024)} GB of files at most. "
                           "Delete some pinned files to add more.")


async def insert_pin(conn, site_id: UUID, board_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
    """Add a pin on top of the board. Raises `BoardGone`, `BoardLimit` or `SiteFull`."""
    values = {k: fields.get(k) for k in INSERT_FIELDS}
    values["size_bytes"] = values["size_bytes"] or 0
    values["rotation"] = values["rotation"] or 0
    cols = ", ".join(INSERT_FIELDS)
    params = ", ".join(f"${i + 3}" for i in range(len(INSERT_FIELDS)))
    async with conn.transaction():
        await _lock(conn, site_id)
        if not await conn.fetchval("SELECT 1 FROM cappe_boards WHERE id = $1 AND site_id = $2", board_id, site_id):
            raise BoardGone("Board not found")
        await check_room(conn, site_id, board_id, values["size_bytes"])
        pin_id = await conn.fetchval(
            f"""INSERT INTO cappe_board_pins (board_id, site_id, z, {cols})
                VALUES ($1, $2, (SELECT LEAST(COALESCE(MAX(z), 0) + 1, {Z_MAX})
                                   FROM cappe_board_pins WHERE board_id = $1), {params})
                RETURNING id""",
            board_id, site_id, *[values[k] for k in INSERT_FIELDS],
        )
        await _touch(conn, board_id)
        row = await get_pin(conn, board_id, pin_id)
    return pin_out(row)


async def update_pin(conn, site_id: UUID, board_id: UUID, pin_id: UUID,
                     changes: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Apply `changes` (keys from `PATCHABLE`, already checked) and answer the pin."""
    changes = {k: v for k, v in changes.items() if k in PATCHABLE}
    if changes:
        sets = ", ".join(f"{k} = ${i + 4}" for i, k in enumerate(changes))
        found = await conn.fetchval(
            f"UPDATE cappe_board_pins SET {sets}, updated_at = NOW() "
            "WHERE id = $1 AND board_id = $2 AND site_id = $3 RETURNING id",
            pin_id, board_id, site_id, *changes.values(),
        )
        if found is None:
            return None
        await _touch(conn, board_id)
    row = await get_pin(conn, board_id, pin_id)
    return pin_out(row) if row else None


async def update_layout(conn, site_id: UUID, board_id: UUID, items: list[dict[str, Any]]) -> int:
    """Place many pins at once (a drag, a resize, bringing one to the front).
    Pins not on this board are ignored. Returns how many moved."""
    if not items:
        return 0
    status = await conn.execute(
        """UPDATE cappe_board_pins p
              SET x = l.x, y = l.y, w = l.w, h = l.h, rotation = l.rotation, z = l.z, updated_at = NOW()
             FROM unnest($3::uuid[], $4::real[], $5::real[], $6::real[], $7::real[], $8::real[], $9::int[])
                  AS l(id, x, y, w, h, rotation, z)
            WHERE p.id = l.id AND p.board_id = $1 AND p.site_id = $2""",
        board_id, site_id,
        [i["id"] for i in items], [i["x"] for i in items], [i["y"] for i in items], [i["w"] for i in items],
        [i["h"] for i in items], [i["rotation"] for i in items], [i["z"] for i in items],
    )
    tail = str(status).rsplit(" ", 1)[-1]  # asyncpg answers "UPDATE <n>"
    moved = int(tail) if tail.isdigit() else 0
    if moved:
        await _touch(conn, board_id)
    return moved


async def delete_pin(conn, site_id: UUID, board_id: UUID, pin_id: UUID) -> Optional[list[str]]:
    """Delete a pin. Returns its files to remove, or None when there was no such pin."""
    row = await conn.fetchrow(
        "DELETE FROM cappe_board_pins WHERE id = $1 AND board_id = $2 AND site_id = $3 "
        "RETURNING file_path, thumb_path",
        pin_id, board_id, site_id,
    )
    if row is None:
        return None
    await _touch(conn, board_id)
    return [p for p in (row["file_path"], row["thumb_path"]) if p]


async def attach_asset(conn, site_id: UUID, board_id: UUID, pin_id: UUID, asset_id: UUID,
                       file_path: str) -> Optional[dict[str, Any]]:
    """Point a private picture pin at the library picture made from it. Only
    while the pin still holds `file_path` (it wasn't changed meanwhile)."""
    found = await conn.fetchval(
        """UPDATE cappe_board_pins
              SET asset_id = $4, file_path = NULL, thumb_path = NULL, mime = NULL, size_bytes = 0,
                  updated_at = NOW()
            WHERE id = $1 AND board_id = $2 AND site_id = $3 AND kind = 'image' AND file_path = $5
            RETURNING id""",
        pin_id, board_id, site_id, asset_id, file_path,
    )
    if found is None:
        return None
    await _touch(conn, board_id)
    return pin_out(await get_pin(conn, board_id, pin_id))
