"""Shared field validators for Cappe request models.

One place for the rules that more than one model needs, so a new model can't
quietly skip them.

`https_url` is the extraction of `CreatorSocialUpsert._https` — which used to be
the *only* model that checked a URL scheme. Every other user-supplied URL
(portfolio, avatar/cover, collab submission + proof, order deliverable) reached
an `<a href>` / `background-image: url(...)` sink in the client unvalidated,
which is a stored `javascript:` vector (audit F3).
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..services.common import MAX_SNAPSHOT_BYTES

# Custom URL scheme a white-label storefront app registers for checkout returns.
# `render.app_return` 302s to `<scheme>://order/<token>`, so the scheme must be
# an app hand-off, never something a browser navigates or executes itself.
# The regex mirrors RFC 3986 scheme syntax; the denylist removes the schemes a
# browser treats as web / script / data / local navigation (CodeQL #205).
APP_URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]{1,30}$")
BLOCKED_APP_URL_SCHEMES = frozenset({
    "http", "https", "ws", "wss", "ftp", "file", "javascript", "vbscript",
    "data", "blob", "about", "mailto", "tel", "sms",
})


def is_app_url_scheme(v: str | None) -> bool:
    """True when `v` is a syntactically valid, non-web custom app scheme."""
    return bool(v) and bool(APP_URL_SCHEME_RE.fullmatch(v)) and v not in BLOCKED_APP_URL_SCHEMES


def app_url_scheme(v: str | None) -> str | None:
    """Field validator: `None` clears the scheme; anything else must pass
    `is_app_url_scheme`."""
    if v is None:
        return None
    if not is_app_url_scheme(v):
        raise ValueError(
            "app_url_scheme must be a custom app scheme (e.g. \"ahnimal\"), not a web or script scheme"
        )
    return v


def https_url(v: str | None) -> str | None:
    """Require an absolute `https://` URL.

    `None` passes through, and so does the empty string: several of these fields
    are cleared by sending `""`, and the length constraints on the field itself
    are what reject an empty value where one is required.
    """
    if v is None:
        return None
    s = v.strip()
    if not s:
        return s
    if not s.lower().startswith("https://"):
        raise ValueError("URL must start with https://")
    return s


def assert_json_size(field_name: str, value: Any, limit: int = MAX_SNAPSHOT_BYTES) -> None:
    """Reject an opaque JSON blob whose serialized form exceeds `limit` bytes.

    `content` / `theme_config` / `meta_config` are `dict[str, Any]` by design —
    the block editor stores whatever the canvas produced — so nothing else bounds
    them before they are persisted, re-rendered, and inlined into prompts.
    """
    if value is None:
        return
    try:
        size = len(json.dumps(value, default=str))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not serializable") from exc
    if size > limit:
        raise ValueError(
            f"{field_name} is too large ({size} bytes; the limit is {limit})"
        )


__all__ = [
    "https_url", "assert_json_size", "MAX_SNAPSHOT_BYTES",
    "APP_URL_SCHEME_RE", "BLOCKED_APP_URL_SCHEMES", "is_app_url_scheme", "app_url_scheme",
]
