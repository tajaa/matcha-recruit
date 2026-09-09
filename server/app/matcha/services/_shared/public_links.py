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
