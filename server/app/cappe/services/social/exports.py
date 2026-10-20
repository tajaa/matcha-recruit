"""Exports: a dropped video cut for each platform, for the owner to download.

One row per video per request (the chat's "prepare this for all platforms",
or the Exports tab). The worker (`workers/tasks/cappe_social_media.py:
prepare_cappe_social_export`) does one step per run — probe, listen for the
words, cut one file, write the captions file — and records each as it lands,
so the minute publisher gets the worker between steps and a restart resumes.
`next_step` says what is left; `rollup` says how it ended.

Files live next to the video's own cuts in the public bucket. A cut reused
from the video's posting render is `shared` and stays when the export goes.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from app.core.services.storage import get_storage

from ..common import loads, loads_list
from . import assets as asset_store
from . import presets

logger = logging.getLogger(__name__)

COLUMNS = ("id, site_id, account_id, asset_id, status, platforms, captions, facts, targets, outputs, srt, texts, "
           "warnings, step, provenance, error, attempts, started_at, expires_at, created_at, updated_at")
OPEN = ("queued", "working")
# One step per run; a healthy export of two cuts with captions takes five.
MAX_RUNS = 12


def _row(row) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    d["platforms"] = list(d.get("platforms") or [])
    for key in ("targets", "outputs", "texts", "provenance"):
        d[key] = loads(d.get(key)) or {}
    for key in ("facts", "srt", "step"):
        d[key] = loads(d.get(key))
    d["warnings"] = loads_list(d.get("warnings")) or []
    return d


# ── what's left ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Step:
    kind: str                  # probe | transcribe | encode | srt | done
    recipe: Optional[str] = None

    def as_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "recipe": self.recipe}


def _words(asset: dict[str, Any]) -> list:
    return list(((asset.get("transcript") or {}).get("words")) or [])


def next_step(export: dict[str, Any], asset: dict[str, Any]) -> Step:
    """The one thing the next run does."""
    if not export.get("facts") or not export.get("targets"):
        return Step("probe")
    if export.get("captions") and asset.get("transcript") is None:
        return Step("transcribe")
    outputs = export.get("outputs") or {}
    for key in dict.fromkeys(export["targets"].values()):
        if key not in outputs:
            return Step("encode", key)
    if export.get("captions") and _words(asset) and not export.get("srt"):
        return Step("srt")
    return Step("done")


def rollup(export: dict[str, Any]) -> str:
    """ready when every platform has its file, failed when none does."""
    outputs = export.get("outputs") or {}
    keys = list(dict.fromkeys((export.get("targets") or {}).values()))
    good = [k for k in keys if (outputs.get(k) or {}).get("url")]
    if keys and len(good) == len(keys):
        return "ready"
    return "partial" if good else "failed"


# ── rows ────────────────────────────────────────────────────────────────────

async def create(conn, *, site_id: UUID, account_id: UUID, asset_id: UUID, platforms: list[str], captions: bool,
                 texts: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    """A queued export. The video's own files are kept at least as long."""
    row = await conn.fetchrow(
        f"""INSERT INTO cappe_social_exports (site_id, account_id, asset_id, platforms, captions, texts, provenance)
            VALUES ($1, $2, $3, $4::text[], $5, $6::jsonb, $7::jsonb)
            RETURNING {COLUMNS}""",
        site_id, account_id, asset_id, [p for p in presets.EXPORT_PLATFORMS if p in platforms], captions,
        json.dumps(texts), json.dumps(provenance),
    )
    await conn.execute(
        "UPDATE cappe_social_assets SET expires_at = GREATEST(expires_at, NOW() + INTERVAL '30 days') WHERE id = $1",
        asset_id,
    )
    return _row(row)


async def get(conn, site_id: UUID, export_id: UUID) -> Optional[dict[str, Any]]:
    return _row(await conn.fetchrow(
        f"SELECT {COLUMNS} FROM cappe_social_exports WHERE id = $1 AND site_id = $2 AND status <> 'deleted'",
        export_id, site_id,
    ))


async def get_by_id(conn, export_id: UUID) -> Optional[dict[str, Any]]:
    return _row(await conn.fetchrow(f"SELECT {COLUMNS} FROM cappe_social_exports WHERE id = $1", export_id))


async def list_for_site(conn, site_id: UUID, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""SELECT {COLUMNS} FROM cappe_social_exports WHERE site_id = $1 AND status <> 'deleted'
            ORDER BY created_at DESC LIMIT $2""",
        site_id, limit,
    )
    return [_row(r) for r in rows]


async def load_many(conn, export_ids: list[UUID]) -> list[dict[str, Any]]:
    if not export_ids:
        return []
    rows = await conn.fetch(
        f"SELECT {COLUMNS} FROM cappe_social_exports WHERE id = ANY($1::uuid[]) ORDER BY created_at", list(export_ids),
    )
    return [_row(r) for r in rows]


async def claim(conn, export_id: UUID) -> Optional[dict[str, Any]]:
    """Take an open export for one run; None when it is finished or gone."""
    return _row(await conn.fetchrow(
        f"""UPDATE cappe_social_exports SET status = 'working', attempts = attempts + 1, started_at = NOW(),
                   updated_at = NOW()
            WHERE id = $1 AND status = ANY($2::text[]) RETURNING {COLUMNS}""",
        export_id, list(OPEN),
    ))


async def set_step(conn, export_id: UUID, step: Optional[Step]) -> None:
    await conn.execute(
        "UPDATE cappe_social_exports SET step = $2::jsonb, updated_at = NOW() WHERE id = $1",
        export_id, json.dumps(step.as_json()) if step else None,
    )


async def record_facts(conn, export_id: UUID, facts, targets: dict[str, str]) -> None:
    await conn.execute(
        "UPDATE cappe_social_exports SET facts = $2::jsonb, targets = $3::jsonb, updated_at = NOW() WHERE id = $1",
        export_id,
        json.dumps({"duration_ms": facts.duration_ms, "width": facts.width, "height": facts.height,
                    "has_audio": facts.has_audio}),
        json.dumps(targets),
    )


async def record_output(conn, export_id: UUID, key: str, output: dict[str, Any]) -> None:
    await conn.execute(
        "UPDATE cappe_social_exports SET outputs = outputs || jsonb_build_object($2::text, $3::jsonb), "
        "updated_at = NOW() WHERE id = $1",
        export_id, key, json.dumps(output),
    )


async def record_srt(conn, export_id: UUID, srt: dict[str, Any]) -> None:
    await conn.execute(
        "UPDATE cappe_social_exports SET srt = $2::jsonb, updated_at = NOW() WHERE id = $1", export_id, json.dumps(srt),
    )


async def add_warning(conn, export_id: UUID, warning: str) -> None:
    """A note for the owner, once."""
    await conn.execute(
        """UPDATE cappe_social_exports SET warnings = warnings || jsonb_build_array($2::text), updated_at = NOW()
           WHERE id = $1 AND NOT warnings @> jsonb_build_array($2::text)""",
        export_id, warning,
    )


async def finish(conn, export_id: UUID, status: str, error: Optional[str] = None) -> None:
    await conn.execute(
        """UPDATE cappe_social_exports SET status = $2, error = $3, step = NULL, updated_at = NOW()
           WHERE id = $1 AND status = ANY($4::text[])""",
        export_id, status, (error or None) and error[:500], list(OPEN),
    )


async def requeue(conn, export_id: UUID) -> None:
    """Back in the line for the next run (also starts the stuck clock again)."""
    await conn.execute(
        "UPDATE cappe_social_exports SET status = 'queued', started_at = NOW(), updated_at = NOW() "
        "WHERE id = $1 AND status = ANY($2::text[])",
        export_id, list(OPEN),
    )


async def delete(conn, site_id: UUID, export_id: UUID) -> Optional[dict[str, Any]]:
    """Forget an export; the caller removes its files once the connection is
    released."""
    return _row(await conn.fetchrow(
        f"DELETE FROM cappe_social_exports WHERE id = $1 AND site_id = $2 RETURNING {COLUMNS}", export_id, site_id,
    ))


# ── the sweep's side ───────────────────────────────────────────────────────

async def stuck(conn, *, minutes: int, limit: int) -> list[dict[str, Any]]:
    """Exports nobody is working on: the worker was restarted mid-step, or
    the next step never reached it."""
    rows = await conn.fetch(
        f"""SELECT {COLUMNS} FROM cappe_social_exports
            WHERE status = ANY($3::text[]) AND COALESCE(started_at, updated_at) < NOW() - make_interval(mins => $1)
            ORDER BY updated_at LIMIT $2""",
        minutes, limit, list(OPEN),
    )
    return [_row(r) for r in rows]


async def expired(conn, *, limit: int) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""SELECT {COLUMNS} FROM cappe_social_exports WHERE expires_at < NOW() AND status <> 'deleted'
            ORDER BY expires_at LIMIT $1""",
        limit,
    )
    return [_row(r) for r in rows]


async def mark_deleted(conn, export_id: UUID) -> None:
    await conn.execute(
        "UPDATE cappe_social_exports SET status = 'deleted', outputs = '{}'::jsonb, srt = NULL, updated_at = NOW() "
        "WHERE id = $1",
        export_id,
    )


# ── files ───────────────────────────────────────────────────────────────────

def _file_keys(export: dict[str, Any]) -> list[str]:
    keys = [o.get("key") for o in (export.get("outputs") or {}).values()
            if isinstance(o, dict) and not o.get("shared")]
    keys.append((export.get("srt") or {}).get("key"))
    return [k for k in keys if k]


def _delete_sync(keys: list[str]) -> None:
    storage = get_storage()
    if not storage.s3_client or not storage.bucket:
        return
    for key in keys:
        try:
            storage.s3_client.delete_object(Bucket=storage.bucket, Key=key)
        except Exception:  # noqa: BLE001 — best effort; the lifecycle rule is the backstop
            logger.warning("cappe social exports: could not delete %s", key)


async def delete_files(export: dict[str, Any]) -> None:
    """Remove the export's own files. Shared cuts belong to the video."""
    keys = _file_keys(export)
    if keys:
        await asyncio.to_thread(_delete_sync, keys)


# ── what the dashboard sees ────────────────────────────────────────────────

def _output_view(output: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(output, dict):
        return None
    return {k: output.get(k) for k in ("url", "width", "height", "duration_ms", "bytes", "trimmed", "error")}


def public_view(export: dict[str, Any], asset: Optional[dict[str, Any]]) -> dict[str, Any]:
    """No storage keys; one row per platform plus the original."""
    outputs = export.get("outputs") or {}
    files = {p: _output_view(outputs.get(key)) for p, key in (export.get("targets") or {}).items()}
    done = sum(1 for k in dict.fromkeys((export.get("targets") or {}).values()) if k in outputs)
    total = len(set((export.get("targets") or {}).values()))
    step = export.get("step") or {}
    return {
        "id": export["id"], "asset_id": export["asset_id"], "status": export["status"],
        "platforms": export["platforms"], "captions": export["captions"], "files": files,
        "progress": {"done": done, "total": total, "step": step.get("kind")},
        "srt": bool((export.get("srt") or {}).get("url")),
        "texts": export.get("texts") or {}, "warnings": export.get("warnings") or [], "error": export.get("error"),
        "filename": (asset or {}).get("filename"), "poster": asset_store.poster(asset),
        "duration_ms": (export.get("facts") or {}).get("duration_ms") or (asset or {}).get("duration_ms"),
        "original": bool(asset and asset.get("status") != "deleted"),
        "created_at": export["created_at"], "updated_at": export["updated_at"],
    }


__all__ = [
    "OPEN", "MAX_RUNS", "Step", "next_step", "rollup", "create", "get", "get_by_id", "list_for_site", "load_many",
    "claim", "set_step", "record_facts", "record_output", "record_srt", "add_warning", "finish", "requeue",
    "delete", "stuck", "expired", "mark_deleted", "delete_files", "public_view",
]
