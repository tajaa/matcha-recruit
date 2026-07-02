"""Thin geocoding wrapper for Tell-Us.

Reuses the matcha property-cat US Census geocoder (`geocode(client, ...)`) so
there's one geocoding implementation in the codebase. That function expects an
httpx client argument; this wraps it so callers just pass address parts.
"""
import logging
from typing import Optional

import httpx

from ...matcha.services.property_cat import geocode as _census_geocode

logger = logging.getLogger(__name__)


async def geocode_location(
    city: str,
    state: Optional[str] = None,
    zipcode: Optional[str] = None,
    address: Optional[str] = None,
) -> Optional[dict]:
    """Best-effort geocode → {lat, lng, county, source} or None.

    Swallows network failures (returns None) so a flaky Census API never blocks
    a location update or store save — the row just stores no coordinates.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            return await _census_geocode(client, address, city, state, zipcode)
    except Exception:
        logger.warning("Tell-Us geocode failed for %s, %s %s", city, state, zipcode, exc_info=True)
        return None
