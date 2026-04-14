"""Client error reporting — captures JS errors + failed API responses from the browser.

Used in place of a paid service like Sentry. The frontend installs global handlers
(window.onerror, unhandledrejection, fetch interceptor, React ErrorBoundary) that
POST error reports here. We persist them to `client_error_reports` and also log
each one so they show up in `docker logs matcha-backend` in near real time.

Unauthenticated — we want errors from logged-out sessions too (e.g. broken login
page). We still try to resolve the current user from the bearer token if present.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..dependencies import require_admin
from ..services.auth import decode_token
from ...database import get_connection

logger = logging.getLogger("matcha.client_errors")

router = APIRouter()

# --- simple in-process rate limit per IP ---
# Cheap, no Redis needed. Resets on backend restart. Stops a rogue client from
# hammering the unauth endpoint.
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_PER_WINDOW = 60
_rate_limit_state: dict[str, list[float]] = {}


def _rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    timestamps = _rate_limit_state.get(client_ip, [])
    # Drop expired entries
    timestamps = [t for t in timestamps if t >= cutoff]
    if len(timestamps) >= _RATE_LIMIT_MAX_PER_WINDOW:
        _rate_limit_state[client_ip] = timestamps
        return True
    timestamps.append(now)
    _rate_limit_state[client_ip] = timestamps
    # Opportunistic cleanup if the dict grows
    if len(_rate_limit_state) > 1000:
        for ip in list(_rate_limit_state.keys()):
            if not _rate_limit_state[ip] or _rate_limit_state[ip][-1] < cutoff:
                _rate_limit_state.pop(ip, None)
    return False


# Redact any context keys that look sensitive before persisting.
_REDACT_KEYS = {
    "password", "passwd", "secret", "token", "access_token", "refresh_token",
    "api_key", "apikey", "authorization", "cookie", "session", "ssn", "credit_card",
    "card_number", "cvv",
}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("[REDACTED]" if k.lower() in _REDACT_KEYS else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class ClientErrorReport(BaseModel):
    kind: str = Field(..., pattern="^(js_error|promise_rejection|api_error|react_error)$")
    message: str = Field(..., max_length=4000)
    stack: Optional[str] = Field(None, max_length=20000)
    url: Optional[str] = Field(None, max_length=2000)
    api_endpoint: Optional[str] = Field(None, max_length=1000)
    api_status_code: Optional[int] = None
    context: Optional[dict[str, Any]] = None


async def _resolve_user(authorization: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Best-effort user lookup from bearer token; None if missing/invalid."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None, None
    token = authorization[7:].strip()
    try:
        payload = decode_token(token, expected_type="access")
        if not payload:
            return None, None
        return payload.sub, getattr(payload, "email", None)
    except Exception:
        return None, None


@router.post("/client-errors", status_code=204)
async def report_client_error(
    body: ClientErrorReport,
    request: Request,
    authorization: Optional[str] = Header(None),
    user_agent: Optional[str] = Header(None),
):
    """Accept an error report from the browser. Always returns 204 even on lookup
    failure — we never want error reporting itself to throw."""
    # Per-IP rate limit (60/min). Returns 429, client reporter will silently
    # drop on non-2xx so this doesn't cascade.
    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many error reports")

    try:
        user_id, user_email = await _resolve_user(authorization)

        # Normalize newlines in logged message so a single error is one log line
        log_message = (body.message or "").replace("\n", " ").replace("\r", " ")[:500]
        log_stack = (body.stack or "").replace("\n", " | ")[:1000]

        # Log it so it's immediately visible in container logs
        logger.error(
            "[CLIENT-%s] %s | user=%s | url=%s | api=%s(%s) | stack=%s",
            body.kind.upper(),
            log_message,
            user_email or user_id or "anon",
            (body.url or "")[:200],
            body.api_endpoint or "",
            body.api_status_code or "",
            log_stack,
        )

        # Redact + cap the context JSON so a malicious client can't push
        # arbitrary blobs into the DB
        context_json = None
        if body.context:
            redacted = _redact(body.context)
            serialized = json.dumps(redacted)
            if len(serialized) > 10_000:
                serialized = json.dumps({"_truncated": True, "_bytes": len(serialized)})
            context_json = serialized

        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO client_error_reports (
                    user_id, user_email, kind, message, stack, url,
                    user_agent, api_endpoint, api_status_code, context
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                """,
                user_id,
                user_email,
                body.kind,
                body.message[:4000],
                (body.stack or None),
                (body.url or None),
                (user_agent or "")[:500] if user_agent else None,
                body.api_endpoint,
                body.api_status_code,
                context_json,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Failed to persist client error report: %s", exc)
    return None


# ── Admin: list + query error reports ─────────────────────────────────────


@router.get("/admin/client-errors", dependencies=[Depends(require_admin)])
async def list_client_errors(
    kind: Optional[str] = None,
    user_email: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 100,
    offset: int = 0,
):
    """Admin-only — list recent client error reports with filters."""
    if since_hours < 1 or since_hours > 720:
        since_hours = 24
    if limit < 1 or limit > 500:
        limit = 100
    if offset < 0:
        offset = 0

    filters = ["occurred_at > NOW() - ($1 || ' hours')::interval"]
    args: list[Any] = [str(since_hours)]
    if kind:
        if kind not in ("js_error", "promise_rejection", "api_error", "react_error"):
            raise HTTPException(status_code=400, detail="invalid kind")
        args.append(kind)
        filters.append(f"kind = ${len(args)}")
    if user_email:
        args.append(f"%{user_email.lower()}%")
        filters.append(f"LOWER(user_email) LIKE ${len(args)}")
    args.append(limit)
    args.append(offset)

    async with get_connection() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM client_error_reports WHERE {' AND '.join(filters)}",
            *args[:-2],
        )
        rows = await conn.fetch(
            f"""
            SELECT id, user_id, user_email, kind, message, stack, url,
                   user_agent, api_endpoint, api_status_code, context,
                   occurred_at, created_at
            FROM client_error_reports
            WHERE {' AND '.join(filters)}
            ORDER BY occurred_at DESC
            LIMIT ${len(args) - 1} OFFSET ${len(args)}
            """,
            *args,
        )

    return {
        "total": int(total or 0),
        "items": [
            {
                "id": str(r["id"]),
                "user_id": str(r["user_id"]) if r["user_id"] else None,
                "user_email": r["user_email"],
                "kind": r["kind"],
                "message": r["message"],
                "stack": r["stack"],
                "url": r["url"],
                "user_agent": r["user_agent"],
                "api_endpoint": r["api_endpoint"],
                "api_status_code": r["api_status_code"],
                "context": (
                    json.loads(r["context"]) if isinstance(r["context"], str)
                    else r["context"]
                ),
                "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
            }
            for r in rows
        ],
    }


@router.get("/admin/client-errors/stats", dependencies=[Depends(require_admin)])
async def client_errors_stats(since_hours: int = 24):
    """Admin-only — aggregate counts by kind and top error messages."""
    if since_hours < 1 or since_hours > 720:
        since_hours = 24

    async with get_connection() as conn:
        by_kind = await conn.fetch(
            """
            SELECT kind, COUNT(*) as count
            FROM client_error_reports
            WHERE occurred_at > NOW() - ($1 || ' hours')::interval
            GROUP BY kind
            ORDER BY count DESC
            """,
            str(since_hours),
        )
        top_messages = await conn.fetch(
            """
            SELECT message, kind, COUNT(*) as count, MAX(occurred_at) as last_seen
            FROM client_error_reports
            WHERE occurred_at > NOW() - ($1 || ' hours')::interval
            GROUP BY message, kind
            ORDER BY count DESC
            LIMIT 20
            """,
            str(since_hours),
        )

    return {
        "by_kind": [{"kind": r["kind"], "count": int(r["count"])} for r in by_kind],
        "top_messages": [
            {
                "message": r["message"],
                "kind": r["kind"],
                "count": int(r["count"]),
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            }
            for r in top_messages
        ],
    }
