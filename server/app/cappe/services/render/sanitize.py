"""Sanitization/escaping primitives for the Cappe renderer — pure string/regex
helpers, no HTML/CSS assembly logic. This is a leaf module: no intra-package
imports."""
import html
import itertools
import json
import re
from typing import Any


_uid_counter = itertools.count(1)


def _uid() -> int:
    return next(_uid_counter)


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _safe_href(href: Any) -> str:
    if not href:
        return "#"
    s = str(href).strip()
    if s.startswith(("/", "#")):
        return s
    if s.lower().startswith(("http://", "https://", "mailto:", "tel:")):
        return s
    return "#"


def _safe_image(url: Any) -> str | None:
    if not url:
        return None
    s = str(url).strip()
    if any(c in s for c in ("'", '"', ")", "(", ";", "<", ">", "\\", "\n", "\r")):
        return None
    return s if s.lower().startswith(("http://", "https://", "/")) else None


def _js_obj(obj: Any) -> str:
    return (json.dumps(obj).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace(chr(0x2028), "\\u2028").replace(chr(0x2029), "\\u2029"))


def _clean_css(v: Any) -> str:
    return str(v if v is not None else "").replace("<", "").replace(">", "").replace("}", "")


_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _hexonly(v: Any) -> str:
    s = str(v or "").strip()
    return s if _HEX_RE.match(s) else ""


def _clampi(v: Any, lo: int, hi: int, default: int = 0) -> int:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


_ANCHOR_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def _anchor_id(v: Any) -> str:
    """Strict slug for a section `id=` attribute. Only [a-z0-9-] with no leading/
    trailing dash — no space/quote/`>` can appear, so no attribute breakout."""
    s = str(v or "").strip().lower()
    return s if _ANCHOR_RE.match(s) else ""


def _safe_url_css(url: Any) -> str:
    """Sanitized URL for a CSS url('...') — reuses the hero re-encode."""
    u = _safe_image(url)
    if not u:
        return ""
    return _esc(u).replace("'", "%27").replace("(", "%28").replace(")", "%29")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_CV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _cv_safe_id(v: Any) -> str:
    s = str(v or "")
    return s if _CV_ID_RE.match(s) else ""
