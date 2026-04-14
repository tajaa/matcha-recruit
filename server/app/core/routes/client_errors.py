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
from typing import Any, Optional

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from ..services.auth import decode_token
from ...database import get_connection

logger = logging.getLogger("matcha.client_errors")

router = APIRouter()


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
    try:
        user_id, user_email = await _resolve_user(authorization)

        # Log it so it's immediately visible in container logs
        logger.error(
            "[CLIENT-%s] %s | user=%s | url=%s | api=%s(%s) | stack=%s",
            body.kind.upper(),
            body.message[:500],
            user_email or user_id or "anon",
            (body.url or "")[:200],
            body.api_endpoint or "",
            body.api_status_code or "",
            (body.stack or "").replace("\n", " | ")[:1000],
        )

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
                user_agent,
                body.api_endpoint,
                body.api_status_code,
                json.dumps(body.context) if body.context else None,
            )
    except Exception as exc:
        logger.warning("Failed to persist client error report: %s", exc)
    return None
