"""Shared helpers for the Cappe routers."""
import json
import re
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status

# asyncpg returns JSONB columns as text (no global codec is registered), so
# every JSONB read goes through _loads and every write through json.dumps.

_SLUG_RE = re.compile(r"[^a-z0-9]+")

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


async def unique_slug(conn, base: str, table: str, column: str = "slug") -> str:
    """Return `base`, or `base-2`, `base-3`, … until it's free in table.column.

    Table/column are caller-controlled literals (never user input), so the
    f-string is safe; the value is always parameterized.
    """
    candidate = base
    n = 1
    while True:
        exists = await conn.fetchval(
            f"SELECT 1 FROM {table} WHERE {column} = $1", candidate
        )
        if not exists:
            return candidate
        n += 1
        candidate = f"{base}-{n}"


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


async def unique_site_slug(conn, table: str, site_id, base: str, column: str = "slug") -> str:
    """Per-site slug uniqueness for tables with UNIQUE(site_id, slug). `table`
    and `column` are caller literals (never user input)."""
    candidate = base
    n = 1
    while await conn.fetchval(
        f"SELECT 1 FROM {table} WHERE site_id = $1 AND {column} = $2", site_id, candidate
    ):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def get_owned_site(conn, site_id: UUID, account_id: UUID):
    """Fetch a site row, 404ing if it doesn't exist or isn't this account's.

    Same id is returned for missing-vs-forbidden so we never leak which site
    ids exist across accounts.
    """
    row = await conn.fetchrow(
        "SELECT * FROM cappe_sites WHERE id = $1 AND account_id = $2",
        site_id,
        account_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return row


def site_row_to_dict(row, page_count: Optional[int] = None) -> dict:
    """Map a cappe_sites row to the CappeSite response shape."""
    d = dict(row)
    d["theme_config"] = loads(row["theme_config"])
    d["meta_config"] = loads(row["meta_config"])
    if page_count is not None:
        d["page_count"] = page_count
    return d


def page_row_to_dict(row) -> dict:
    """Map a cappe_pages row to the CappePage response shape."""
    d = dict(row)
    d["content"] = loads(row["content"])
    return d
