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
# A building's homes a model is shown: the ones that fit, else the cheapest few.
HOMES_FOR_MODEL = 6
HOMES_NOT_FITTING = 3


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


async def known_names(conn, task_id: UUID) -> set[tuple[str, str]]:
    """The (name, seller or place) of every finding the task has: `insert_items`
    skips another with the same, so there is no point looking one up."""
    rows = await conn.fetch("SELECT title, subtitle FROM mw_agent_task_items WHERE task_id = $1", task_id)
    return {(title_key(row["title"]), title_key(row["subtitle"])) for row in rows}


async def insert_items(conn, task: dict, token: UUID, round_n: int, records: list[dict], *, room: int) -> int:
    """Add new findings (at most `room`) if this chain still owns the task; a
    finding already there (same page, or same name) is skipped. Returns how
    many were added, and counts them on the round."""
    if room <= 0 or not records:
        return 0
    existing = await conn.fetch(
        "SELECT dedupe_key, title, subtitle FROM mw_agent_task_items WHERE task_id = $1", task["id"],
    )
    keys = {row["dedupe_key"] for row in existing}
    titles = {title_key(row["title"]) for row in existing if title_key(row["title"])}
    # Same name and same seller or place: the same thing, whatever its link.
    pairs = {(title_key(row["title"]), title_key(row.get("subtitle"))) for row in existing}
    rows, seen = [], set()
    for record in records:
        key = dedupe_key(record)
        name = title_key(record.get("title"))
        pair = (name, title_key(record.get("subtitle")))
        if (key in keys or key in seen or (name and pair in pairs)
                or (name and name in titles and record.get("origin") != "provider")):
            continue
        seen.add(key)
        pairs.add(pair)
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


def _units(row: dict) -> list[dict]:
    return [u for u in decode_jsonb(row.get("units"), []) or [] if isinstance(u, dict)]


def _fitting(row: dict) -> set[str] | None:
    """The homes the last ranking found meet every per-home limit, or None
    before a ranking has looked at them."""
    explain = decode_jsonb(row.get("rank_explain"), {}) or {}
    fits = explain.get("units_fit")
    return {str(f) for f in fits} if isinstance(fits, list) else None


def homes_view(row) -> dict | None:
    """How many homes a building lists, how many fit, and the cheapest that fits."""
    from .research.units import lowest_rent  # research imports this module

    row = dict(row)
    units = _units(row)
    if not units:
        return None
    fits = _fitting(row)
    fitting = [u for u in units if fits is None or str(u.get("id")) in fits]
    cheapest = min((lowest_rent(u) for u in fitting), default=None)
    return {"count": len(units), "fit": len(fitting) if fits is not None else None, "from": cheapest}


def units_view(row) -> list[dict]:
    """A building's homes for the app, each marked `fits` (None before
    ranking). A floor plan's source is never shown, only our copy."""
    row = dict(row)
    fits = _fitting(row)
    return [{**{k: v for k, v in u.items() if k != "plan_source"},
             "fits": None if fits is None else str(u.get("id")) in fits} for u in _units(row)]


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
        # Its page as the browser drew it: never a photo.
        "screenshots": decode_jsonb(row.get("screenshots"), []) or [],
        "status": row.get("status") or "candidate",
        "fit_score": row.get("fit_score"),
        "rank": row.get("rank"),
        "rank_band": row.get("rank_band"),
        "flags": list(explain.get("flags") or []),
        "user_state": row.get("user_state") or "new",
        "round": row.get("round_n"),
        "homes": homes_view(row),
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
        "units": units_view(row),
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
        "units": _units(row),
    }


def view_for_model(row) -> dict[str, Any]:
    row = dict(row)
    out = {
        "id": str(row["id"]),
        "title": row.get("title") or "",
        "subtitle": row.get("subtitle") or "",
        "url": row.get("url"),
        "fields": decode_jsonb(row.get("fields"), {}) or {},
        "fit_score": row.get("fit_score"),
        "fit_reasons": decode_jsonb(row.get("fit_reasons"), []) or [],
        # The homes below say which fit; their ids would only be noise.
        "rank_explain": {k: v for k, v in (decode_jsonb(row.get("rank_explain"), {}) or {}).items()
                         if k != "units_fit"},
    }
    units = _units(row)
    if units:
        from .research.units import unit_line  # research imports this module

        fits = _fitting(row)
        if fits is None:  # not ranked yet: the cheapest, none judged
            out["homes"] = {"listed": len(units), "examples": [unit_line(u) for u in units[:HOMES_FOR_MODEL]]}
        else:
            fitting = [u for u in units if str(u.get("id")) in fits]
            out["homes"] = {"listed": len(units), "meet_every_limit": len(fitting),
                            "homes_that_fit": [unit_line(u) for u in fitting[:HOMES_FOR_MODEL]]}
            if not fitting:
                out["homes"]["cheapest_not_fitting"] = [unit_line(u) for u in units[:HOMES_NOT_FITTING]]
    return out
