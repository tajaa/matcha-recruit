"""A task's findings: how they are keyed, stored and shown. Pool-free.

Every write a phase makes goes through the task's dispatch token, so a
cancelled task, or a chain a reconcile replaced, stops adding findings at the
next write.
"""
from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from app.database import decode_jsonb
from app.matcha.services.matcha_work.agent_card.schema import normalize_url

_WORDS = re.compile(r"[a-z0-9]+")


def _iso(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def title_key(title: str) -> str:
    return " ".join(_WORDS.findall(str(title or "").casefold()))[:160]


def dedupe_key(record: dict) -> str:
    """One finding per page; a finding with no page is keyed by its name."""
    url = normalize_url(record.get("url"))
    if url:
        return f"u:{url}"[:500]
    return f"t:{title_key(record.get('title'))}|{title_key(record.get('subtitle'))[:60]}"


async def insert_items(conn, task: dict, token: UUID, round_n: int, records: list[dict], *, room: int) -> int:
    """Add new findings (at most `room`) if this chain still owns the task; a
    finding already there (same page, or same name) is skipped. Returns how
    many were added, and counts them on the round."""
    if room <= 0 or not records:
        return 0
    existing = await conn.fetch(
        "SELECT dedupe_key, title FROM mw_agent_task_items WHERE task_id = $1", task["id"],
    )
    keys = {row["dedupe_key"] for row in existing}
    titles = {title_key(row["title"]) for row in existing if title_key(row["title"])}
    rows, seen = [], set()
    for record in records:
        key = dedupe_key(record)
        name = title_key(record.get("title"))
        if key in keys or key in seen or (name and name in titles and record.get("origin") != "provider"):
            continue
        seen.add(key)
        rows.append({
            "dedupe_key": key,
            "kind": record.get("kind") or "other",
            "title": str(record.get("title") or "")[:200],
            "subtitle": str(record.get("subtitle") or "")[:200],
            "url": record.get("url"),
            "origin": record.get("origin") or "web",
            "provider": record.get("provider"),
            "fields": record.get("fields") or {},
            "image_candidates": record.get("image_candidates") or [],
        })
        if len(rows) >= room:
            break
    if not rows:
        return 0
    inserted = int(await conn.fetchval(
        """WITH ins AS (
               INSERT INTO mw_agent_task_items
                   (task_id, round_n, dedupe_key, kind, title, subtitle, url, origin, provider,
                    fields, image_candidates)
               SELECT $1, $2, r.dedupe_key, r.kind, r.title, r.subtitle, r.url, r.origin, r.provider,
                      r.fields, r.image_candidates
               FROM jsonb_to_recordset($3::jsonb) AS r(
                   dedupe_key text, kind text, title text, subtitle text, url text, origin text,
                   provider text, fields jsonb, image_candidates jsonb)
               WHERE EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $1 AND dispatch_token = $4)
               ON CONFLICT (task_id, dedupe_key) DO NOTHING
               RETURNING 1)
           SELECT COUNT(*) FROM ins""",
        task["id"], round_n, json.dumps(rows, default=str), token,
    ) or 0)
    if inserted:
        await conn.execute(
            """UPDATE mw_agent_task_rounds SET items_added = items_added + $3
               WHERE task_id = $1 AND n = $2""",
            task["id"], round_n, inserted,
        )
    return inserted


def _fields_view(fields: dict, *, evidence: bool) -> dict:
    out = {}
    for key, value in (fields or {}).items():
        if not isinstance(value, dict):
            continue
        shown = {"display": value.get("display"), "value": value.get("value"), "status": value.get("status")}
        if value.get("unit"):
            shown["unit"] = value["unit"]
        if value.get("currency"):
            shown["currency"] = value["currency"]
        if evidence:
            shown["evidence"] = value.get("evidence") or {}
        out[key] = shown
    return out


def item_summary(row) -> dict:
    row = dict(row)
    explain = decode_jsonb(row.get("rank_explain"), {}) or {}
    return {
        "id": str(row["id"]),
        "kind": row.get("kind") or "other",
        "title": row.get("title") or "",
        "subtitle": row.get("subtitle") or "",
        "url": row.get("url"),
        "origin": row.get("origin"),
        "provider": row.get("provider"),
        "fields": _fields_view(decode_jsonb(row.get("fields"), {}) or {}, evidence=False),
        "images": decode_jsonb(row.get("images"), []) or [],
        "status": row.get("status") or "candidate",
        "fit_score": row.get("fit_score"),
        "rank": row.get("rank"),
        "rank_band": row.get("rank_band"),
        "flags": list(explain.get("flags") or []),
        "user_state": row.get("user_state") or "new",
        "round": row.get("round_n"),
    }


def item_detail(row) -> dict:
    row = dict(row)
    return {
        **item_summary(row),
        "fields": _fields_view(decode_jsonb(row.get("fields"), {}) or {}, evidence=True),
        "violations": decode_jsonb(row.get("violations"), []) or [],
        "fit_reasons": decode_jsonb(row.get("fit_reasons"), []) or [],
        "rank_explain": decode_jsonb(row.get("rank_explain"), {}) or {},
        "notes": row.get("notes") or "",
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def as_rank_input(row) -> dict:
    row = dict(row)
    return {
        "id": row["id"],
        "fields": decode_jsonb(row.get("fields"), {}) or {},
        "status": row.get("status"),
        "fit_score": row.get("fit_score"),
        "user_state": row.get("user_state"),
    }


def view_for_model(row) -> dict[str, Any]:
    row = dict(row)
    return {
        "id": str(row["id"]),
        "title": row.get("title") or "",
        "subtitle": row.get("subtitle") or "",
        "url": row.get("url"),
        "fields": decode_jsonb(row.get("fields"), {}) or {},
        "fit_score": row.get("fit_score"),
        "fit_reasons": decode_jsonb(row.get("fit_reasons"), []) or [],
        "rank_explain": decode_jsonb(row.get("rank_explain"), {}) or {},
    }
