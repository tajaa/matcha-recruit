"""Shared helpers for the `routes/public/` package — the Cappe public surface
(anonymous, by site slug). See `__init__.py` for the package-level docstring.
"""
from fastapi import HTTPException, Request, status

from ....core.services.email._shared import _is_reserved_test_domain
from ....core.services.redis_cache import check_rate_limit, client_ip
from ...services.commerce import validate_intake as _validate_intake  # noqa: F401  (test_cappe_offerings imports this)


async def _published_site(conn, slug: str):
    """Resolve a published site by slug, or 404. Returns the row (incl. id, timezone)."""
    row = await conn.fetchrow(
        "SELECT id, name, slug, subdomain, custom_domain, theme_config, meta_config, timezone, status "
        "FROM cappe_sites WHERE slug = $1",
        slug,
    )
    if row is None or row["status"] != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return row


def _reject_reserved(email: str | None):
    if email and _is_reserved_test_domain(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reserved/test email domains are not accepted",
        )


async def _read_rate_limit(request: Request) -> None:
    """Shared per-IP budget for anonymous read endpoints. Generous — a page
    load fires 2-3 widget fetches — but stops scripted scraping/enumeration."""
    await check_rate_limit(client_ip(request), "cappe_pub_read", 120, 60)


async def _location_ctx(conn, site, location_id):
    """Validate `location_id` belongs to the published site (and is active) and
    return (location_id, tz). None → site timezone. Raises 400 on a bad id."""
    if location_id is None:
        return None, site["timezone"]
    row = await conn.fetchrow(
        "SELECT timezone FROM cappe_locations WHERE id = $1 AND site_id = $2 AND active = true",
        location_id, site["id"],
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown location")
    return location_id, (row["timezone"] or site["timezone"])
