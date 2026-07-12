"""Usage analytics — client beacon (write) + admin dashboard (read).

The beacon is unauthenticated on purpose: public/marketing pages and logged-out
auth flows are exactly the traffic we can't see otherwise. It resolves the user
from the bearer token when one is present, and falls back to an anonymous
first-party `visitor_id` the client keeps in localStorage. Same shape as
`client_errors.py` — 204, per-IP rate limit, never throws.

Server-side API calls are NOT accepted here (`api_call` is rejected by the event
pattern); those are recorded by the `track_api_usage` middleware in main.py,
where the status and duration are actually known. Both write through
`services/usage_tracker.record_event`.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..dependencies import require_admin
from ..services.usage_tracker import record_event, resolve_token
from ...database import get_connection

logger = logging.getLogger("matcha.usage")

router = APIRouter()

# --- in-process per-IP rate limit (mirrors client_errors.py) ---
# Higher ceiling than client-errors: page views batch, and a busy tab flushing
# every 10s plus a keepalive on close is normal traffic.
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_PER_WINDOW = 120
_rate_limit_state: dict[str, list[float]] = {}


def _rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    timestamps = [t for t in _rate_limit_state.get(client_ip, []) if t >= cutoff]
    if len(timestamps) >= _RATE_LIMIT_MAX_PER_WINDOW:
        _rate_limit_state[client_ip] = timestamps
        return True
    timestamps.append(now)
    _rate_limit_state[client_ip] = timestamps
    if len(_rate_limit_state) > 1000:
        for ip in list(_rate_limit_state.keys()):
            if not _rate_limit_state[ip] or _rate_limit_state[ip][-1] < cutoff:
                _rate_limit_state.pop(ip, None)
    return False


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
# The digit lookahead keeps long route slugs ("workforce-compliance") intact:
# generated tokens (hex/base64url) essentially always contain a digit.
_TOKENISH_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9_\-]{20,}$")


def normalize_path(path: str) -> str:
    """Collapse identifying path segments to placeholders.

    The client already does this, but we redo it server-side because the raw
    value is attacker-controlled and some public routes carry a live secret in
    the URL (`/report/<token>`, `/s/<token>`). A leaked token in the analytics
    table would be a real credential leak, so this is a hard invariant, not a
    tidiness pass. Also bounds cardinality of the top-pages rollup.
    """
    path = (path or "/").split("?")[0].split("#")[0]
    out = []
    for seg in path.split("/"):
        if not seg:
            out.append(seg)
        elif _UUID_RE.match(seg):
            out.append(":id")
        elif seg.isdigit():
            out.append(":id")
        elif _TOKENISH_RE.match(seg):
            out.append(":token")
        else:
            out.append(seg)
    return ("/".join(out) or "/")[:300]


class UsageBeaconEvent(BaseModel):
    event: str = Field(..., pattern="^(page_view|session_start|heartbeat)$")
    path: str = Field(..., max_length=300)
    surface: str = Field(..., pattern="^(web|public|werk_desktop)$")
    ts: Optional[datetime] = None


class UsageBeaconBody(BaseModel):
    visitor_id: Optional[str] = Field(None, max_length=64)
    events: list[UsageBeaconEvent] = Field(..., max_length=50)


@router.post("/usage/beacon", status_code=204)
async def usage_beacon(
    body: UsageBeaconBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Accept a batch of client usage events. Always 204 — analytics must never
    surface an error to the user."""
    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many usage events")

    try:
        user_id, role = resolve_token(authorization)

        visitor_id = body.visitor_id
        if visitor_id and not _UUID_RE.match(visitor_id):
            visitor_id = None  # only accept our own generated ids

        now = datetime.now(timezone.utc)
        for ev in body.events:
            occurred_at = now
            if ev.ts:
                ts = ev.ts if ev.ts.tzinfo else ev.ts.replace(tzinfo=timezone.utc)
                # Clamp client clocks — a skewed device must not write rows into
                # next year and skew every "last N days" rollup.
                if abs((ts - now).total_seconds()) <= 3600:
                    occurred_at = ts
            record_event(
                surface=ev.surface,
                event=ev.event,
                path=normalize_path(ev.path),
                user_id=user_id,
                role=role,
                visitor_id=visitor_id,
                occurred_at=occurred_at,
            )
    except Exception:
        logger.warning("usage beacon failed", exc_info=True)
    return None


@router.get("/admin/usage/summary", dependencies=[Depends(require_admin)])
async def usage_summary(since_days: int = Query(7, ge=1, le=90)):
    """Everything the /admin/usage dashboard renders, in one round trip."""
    window = str(since_days)

    async with get_connection() as conn:
        daily = await conn.fetch(
            """
            SELECT date_trunc('day', occurred_at)::date AS day,
                   COUNT(DISTINCT user_id) AS users,
                   COUNT(DISTINCT visitor_id) FILTER (WHERE user_id IS NULL) AS visitors,
                   COUNT(*) FILTER (WHERE event = 'page_view') AS page_views
            FROM usage_events
            WHERE occurred_at > NOW() - ($1 || ' days')::interval
            GROUP BY 1
            ORDER BY 1
            """,
            window,
        )

        totals = await conn.fetchrow(
            """
            SELECT
              COUNT(DISTINCT user_id) FILTER (
                WHERE occurred_at > NOW() - INTERVAL '1 day') AS dau,
              COUNT(DISTINCT user_id) FILTER (
                WHERE occurred_at > NOW() - INTERVAL '7 days') AS wau,
              COUNT(DISTINCT user_id) FILTER (
                WHERE occurred_at > NOW() - INTERVAL '30 days') AS mau,
              COUNT(DISTINCT company_id) FILTER (
                WHERE occurred_at > NOW() - INTERVAL '7 days') AS active_companies_7d,
              COUNT(DISTINCT visitor_id) FILTER (
                WHERE user_id IS NULL
                  AND occurred_at > NOW() - INTERVAL '7 days') AS anon_visitors_7d
            FROM usage_events
            WHERE occurred_at > NOW() - INTERVAL '30 days'
            """
        )

        top_pages = await conn.fetch(
            """
            SELECT surface, path,
                   COUNT(*) AS views,
                   COUNT(DISTINCT COALESCE(user_id::text, visitor_id)) AS uniques
            FROM usage_events
            WHERE event = 'page_view'
              AND occurred_at > NOW() - ($1 || ' days')::interval
            GROUP BY surface, path
            ORDER BY views DESC
            LIMIT 20
            """,
            window,
        )

        companies = await conn.fetch(
            """
            SELECT c.id, c.name,
                   MAX(ue.occurred_at) AS last_seen,
                   COUNT(DISTINCT ue.user_id) AS users,
                   COUNT(*) AS events
            FROM usage_events ue
            JOIN companies c ON c.id = ue.company_id
            WHERE ue.occurred_at > NOW() - ($1 || ' days')::interval
            GROUP BY c.id, c.name
            ORDER BY last_seen DESC
            LIMIT 50
            """,
            window,
        )

        endpoints = await conn.fetch(
            """
            SELECT path, method,
                   COUNT(*) AS calls,
                   AVG(duration_ms)::int AS avg_ms,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)::int AS p95_ms,
                   COUNT(*) FILTER (WHERE status >= 500) AS errors
            FROM usage_events
            WHERE event = 'api_call'
              AND occurred_at > NOW() - ($1 || ' days')::interval
            GROUP BY path, method
            ORDER BY calls DESC
            LIMIT 20
            """,
            window,
        )

    return {
        "since_days": since_days,
        "totals": {
            "dau": int(totals["dau"] or 0),
            "wau": int(totals["wau"] or 0),
            "mau": int(totals["mau"] or 0),
            "active_companies_7d": int(totals["active_companies_7d"] or 0),
            "anon_visitors_7d": int(totals["anon_visitors_7d"] or 0),
        },
        "daily": [
            {
                "day": r["day"].isoformat(),
                "users": int(r["users"] or 0),
                "visitors": int(r["visitors"] or 0),
                "page_views": int(r["page_views"] or 0),
            }
            for r in daily
        ],
        "top_pages": [
            {
                "surface": r["surface"],
                "path": r["path"],
                "views": int(r["views"]),
                "uniques": int(r["uniques"] or 0),
            }
            for r in top_pages
        ],
        "companies": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                "users": int(r["users"] or 0),
                "events": int(r["events"]),
            }
            for r in companies
        ],
        "endpoints": [
            {
                "path": r["path"],
                "method": r["method"],
                "calls": int(r["calls"]),
                "avg_ms": int(r["avg_ms"] or 0),
                "p95_ms": int(r["p95_ms"] or 0),
                "errors": int(r["errors"] or 0),
            }
            for r in endpoints
        ],
    }


@router.delete("/admin/usage", dependencies=[Depends(require_admin)])
async def purge_usage_events(older_than_days: int = Query(90, ge=7, le=3650)):
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM usage_events WHERE occurred_at < NOW() - ($1 || ' days')::interval",
            str(older_than_days),
        )
    deleted = int(result.split()[-1]) if result.startswith("DELETE") else 0
    return {"ok": True, "deleted": deleted}
