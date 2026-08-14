"""Pure helpers shared across Cappe routes and services (no DB access)."""
import json
import re
from typing import Any

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_INVALID_HOST_CHARS = frozenset("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f\x20\x7f,/@\\?#")

# Labels a tenant site may NOT use as its subdomain. Cappe sites live on the
# same apex as the main brand (<sub>.hey-matcha.com), so these protect brand /
# infra / auth hostnames from being claimed for phishing or collisions. The
# renderer refuses to serve any of these as a tenant (see render.py), and site
# creation steers slugs away from them.
RESERVED_SUBDOMAINS = frozenset({
    # apex / web
    "www", "web", "m", "mobile", "cappe",
    # product / app surfaces
    "app", "apps", "api", "admin", "dashboard", "portal", "console", "panel",
    "account", "accounts", "login", "signin", "signup", "register", "auth",
    "sso", "secure", "my", "go", "link", "links", "get", "join",
    # marketing / content
    "blog", "shop", "store", "help", "support", "docs", "doc", "status",
    "about", "contact", "news", "press", "legal", "privacy", "terms",
    "jobs", "careers", "partners", "developers", "developer", "community",
    # mail / infra
    "mail", "email", "smtp", "imap", "pop", "pop3", "webmail", "mx",
    "autodiscover", "autoconfig", "ns", "ns1", "ns2", "dns", "ftp", "sftp",
    "vpn", "proxy", "gateway", "edge", "origin", "lb", "host", "server",
    # ops / internal
    "dev", "staging", "stage", "test", "testing", "qa", "demo", "beta",
    "alpha", "sandbox", "internal", "intranet", "git", "ci", "cd",
    "monitor", "monitoring", "grafana", "metrics", "analytics", "logs",
    # assets / cdn
    "cdn", "assets", "static", "media", "img", "images", "files", "uploads",
    "download", "downloads", "cache", "db", "database", "redis",
    # billing
    "billing", "pay", "payment", "payments", "checkout", "invoice", "invoices",
    # transactional sender labels
    "no-reply", "noreply", "newsletter", "mailer", "notifications", "notify",
    # the reserved root itself
    "root",
})


def normalize_host_header(value: str | None) -> str | None:
    """Return a safe lower-case hostname from an HTTP Host value.

    Host is a request authority, not a URL. Reject ambiguous delimiters rather
    than trying to recover from userinfo, multiple authorities, or malformed
    ports. Forwarded host headers are intentionally not handled here.
    """
    if not value or any(char in _INVALID_HOST_CHARS for char in value):
        return None
    raw = value.strip()
    if raw != value or not raw:
        return None

    if raw.startswith("["):
        close = raw.find("]")
        if close < 0:
            return None
        host = raw[1:close]
        suffix = raw[close + 1:]
        if suffix and (not suffix.startswith(":") or not suffix[1:].isdigit()):
            return None
        return host.lower().rstrip(".") or None

    if raw.count(":") > 1:
        return None
    host = raw
    if ":" in raw:
        host, port = raw.rsplit(":", 1)
        if not port.isdigit():
            return None
    host = host.lower().rstrip(".")
    if not host or any(char in _INVALID_HOST_CHARS for char in host):
        return None
    return host


def slugify(text: str) -> str:
    """Lowercase, hyphenate, strip. Falls back to 'site' when empty."""
    s = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    return s[:140] or "site"


def safe_subdomain_base(text: str) -> str:
    """Slugify, then steer away from a reserved label so the slug can be used
    as a tenant subdomain. A reserved base gets a '-site' suffix (e.g. 'shop'
    → 'shop-site'); uniqueness is still resolved by unique_slug afterward."""
    base = slugify(text)
    if base in RESERVED_SUBDOMAINS:
        base = f"{base}-site"
    return base


def loads(value: Any) -> dict:
    """Normalize a JSONB read (str | dict | None) into a dict."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


def loads_list(value: Any) -> list:
    """Normalize a JSONB array read (str | list | None) into a list."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return value if isinstance(value, list) else []
