"""Public token URL builder — the one place that knows how to turn a token
into a browser-facing link behind the prod nginx proxy.

Lifted out of `routes/ir_incidents/_shared.py` (which keeps its
`_build_public_link` name as an alias) so a non-IR feature can mint a public
URL without importing the IR router package — that import runs the whole IR
`__init__.py` (~2,300 modules / ~2s cold) and drags WeasyPrint in.
"""
from __future__ import annotations

from typing import Any


def build_public_link(request: Any, token: str, segment: str) -> str:
    """``https://host/<segment>/<token>`` honoring the X-Forwarded-Proto / Host
    pair set by nginx, falling back to the request's own scheme/host."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/{segment}/{token}"


def public_link_from_settings(token: str, segment: str) -> str:
    """Request-free counterpart of `build_public_link` for links that leave the
    process in an email or a worker — composes off `settings.app_base_url`
    (the setting every other emailed link uses) so an unauthenticated caller's
    `X-Forwarded-Host` can never steer where a recipient or admin is sent.
    Use the header-aware builder only for URLs echoed back to the same
    authenticated request."""
    from app.config import get_settings

    base = (get_settings().app_base_url or "").rstrip("/")
    return f"{base}/{segment}/{token}"
