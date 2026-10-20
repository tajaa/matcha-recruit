"""Image asset library (`cappe_assets`, migrations zzzzcappe23 + cappemag01).

A per-site catalog over images the account has generated, uploaded, or (from
the magazine's archive search) imported. Since cappemag01 each row also knows
where its picture came from and the credit it is printed with:

  * a generated image is always AI — `record` sets `ai_generated`,
    `license='ai'` and the fixed credit "AI illustration" for every
    `kind='generated'` row, whoever records it (the editor button, Merlin);
  * an upload's credit and creator are the owner's to write; a stock or AI
    image's license fields belong to the server (`update_asset` refuses them).

Recording a row from the editor upload or a generation is best-effort (the
caller wraps `record` in try/except): a broken catalog insert must never turn a
successful upload into a failure. The library's own upload (`insert_upload`)
is not best-effort — the row IS what the owner asked for.
"""
import json
import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

AI_CREDIT = "AI illustration"

COLUMNS = (
    "id, kind, url, prompt, aspect, image_size, created_at, source, source_url, title, creator, "
    "creator_url, license, license_version, license_url, provider_label, credit_line, alt, caption, "
    "width, height, bytes, mime, variants, ai_generated, rights_attested_at, moderation, updated_at"
)

# What the owner may edit on any asset, and what only on their own uploads.
EDITABLE = ("alt", "caption")
UPLOAD_EDITABLE = ("title", "creator", "credit_line")


def row(r) -> dict[str, Any]:
    d = dict(r)
    variants = d.get("variants")
    if isinstance(variants, str):
        try:
            d["variants"] = json.loads(variants)
        except ValueError:
            d["variants"] = {}
    elif variants is None:
        d["variants"] = {}
    return d


async def record(
    conn,
    *,
    account_id: UUID,
    site_id: UUID,
    kind: str,
    url: str,
    prompt: Optional[str] = None,
    aspect: Optional[str] = None,
    image_size: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    size_bytes: Optional[int] = None,
    mime: Optional[str] = None,
) -> None:
    """Insert one catalog row for an editor upload or a generation. Callers
    wrap this in try/except — see the module docstring."""
    generated = kind == "generated"
    await conn.execute(
        """
        INSERT INTO cappe_assets (account_id, site_id, kind, url, prompt, aspect, image_size,
                                  source, ai_generated, license, credit_line, width, height, bytes, mime)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        """,
        account_id, site_id, kind, url, prompt, aspect, image_size,
        "generated" if generated else "upload", generated, "ai" if generated else None,
        AI_CREDIT if generated else None, width, height, size_bytes, mime,
    )


async def insert_upload(
    conn,
    *,
    account_id: UUID,
    site_id: UUID,
    url: str,
    width: int,
    height: int,
    size_bytes: int,
    mime: str,
    variants: dict[str, Any],
    alt: Optional[str],
    caption: Optional[str],
    credit_line: Optional[str],
    ai_made: bool,
) -> dict[str, Any]:
    """The library's own upload: the owner has said they may use the picture
    (`rights_attested_at`), and whether it is AI-made. An AI-made upload is
    credited "AI illustration" whatever the owner typed."""
    created = await conn.fetchrow(
        f"""
        INSERT INTO cappe_assets (account_id, site_id, kind, url, source, license, ai_generated,
                                  credit_line, alt, caption, width, height, bytes, mime, variants,
                                  rights_attested_at)
        VALUES ($1, $2, 'upload', $3, 'upload', $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, NOW())
        RETURNING {COLUMNS}
        """,
        account_id, site_id, url, "ai" if ai_made else "own", ai_made,
        AI_CREDIT if ai_made else credit_line, alt, caption, width, height, size_bytes, mime,
        json.dumps(variants),
    )
    return row(created)


async def list_assets(
    conn, site_id: UUID, *, kind: Optional[str] = None, q: Optional[str] = None, limit: int = 200
) -> list[dict[str, Any]]:
    """A site's assets, newest first. `kind` filters to generated, upload or
    stock; `q` matches the alt text, caption, title, creator or prompt."""
    clauses, args = ["site_id = $1"], [site_id]
    if kind:
        args.append(kind)
        clauses.append(f"kind = ${len(args)}")
    if q:
        args.append(f"%{q.strip()}%")
        n = len(args)
        clauses.append(
            f"(alt ILIKE ${n} OR caption ILIKE ${n} OR title ILIKE ${n} OR creator ILIKE ${n} OR prompt ILIKE ${n})"
        )
    args.append(limit)
    rows = await conn.fetch(
        f"SELECT {COLUMNS} FROM cappe_assets WHERE {' AND '.join(clauses)} "
        f"ORDER BY created_at DESC LIMIT ${len(args)}",
        *args,
    )
    return [row(r) for r in rows]


async def get_asset(conn, site_id: UUID, asset_id: UUID) -> Optional[dict[str, Any]]:
    found = await conn.fetchrow(
        f"SELECT {COLUMNS} FROM cappe_assets WHERE id = $1 AND site_id = $2", asset_id, site_id
    )
    return row(found) if found else None


class NotEditable(ValueError):
    """The owner asked to change a field the server owns on this asset."""


def editable_fields(asset: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """The subset of `changes` the owner may make to `asset`. Alt text and
    captions are always theirs; the credit, title and creator only on their
    own non-AI uploads — an archive image's credit comes from its license, and
    an AI image is always credited as AI. Raises `NotEditable`."""
    allowed = set(EDITABLE)
    if asset["kind"] == "upload" and not asset.get("ai_generated"):
        allowed |= set(UPLOAD_EDITABLE)
    refused = sorted(k for k in changes if k not in allowed)
    if refused:
        raise NotEditable(", ".join(refused))
    return {k: (v.strip() or None) if isinstance(v, str) else v for k, v in changes.items()}


async def update_asset(conn, site_id: UUID, asset_id: UUID, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Write already-checked fields (see `editable_fields`). Site-scoped."""
    unknown = set(fields) - set(EDITABLE + UPLOAD_EDITABLE)
    if unknown:  # names are written into the SQL: never let anything else through
        raise NotEditable(", ".join(sorted(unknown)))
    if not fields:
        return await get_asset(conn, site_id, asset_id)
    names = list(fields)
    sets = ", ".join(f"{name} = ${i + 3}" for i, name in enumerate(names))
    updated = await conn.fetchrow(
        f"UPDATE cappe_assets SET {sets}, updated_at = NOW() WHERE id = $1 AND site_id = $2 "
        f"RETURNING {COLUMNS}",
        asset_id, site_id, *(fields[n] for n in names),
    )
    return row(updated) if updated else None


async def delete_asset(conn, site_id: UUID, asset_id: UUID) -> bool:
    """Delete the catalog row only — never the underlying S3 object, which a
    live page's `_design.bg.image` or a block image field may still
    reference. Returns False if no matching row existed (site-scoped, so a
    foreign asset id 404s rather than deleting cross-tenant)."""
    result = await conn.execute(
        "DELETE FROM cappe_assets WHERE id = $1 AND site_id = $2", asset_id, site_id
    )
    return result != "DELETE 0"
