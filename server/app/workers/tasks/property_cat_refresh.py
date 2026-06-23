"""Celery task: geocode property buildings + refresh catastrophe perils.

Two modes:
  - ``refresh_property_cat(building_id=...)`` — enrich one building (dispatched
    after a building is created/updated).
  - ``refresh_property_cat()`` — periodic sweep of un-geocoded / stale buildings,
    capped per cycle. Re-dispatched on worker startup, gated by
    ``scheduler_settings('property_cat_refresh')`` (default off).

All hazard fetching is best-effort inside ``property_cat`` (never raises per
building); this task only owns scheduling + the per-cycle cap.
"""

import asyncio
from uuid import UUID

from ..celery_app import celery_app
from ..utils import get_db_connection

_STALE_DAYS = 90
_DEFAULT_CAP = 20


async def _refresh(building_id=None, cap: int = _DEFAULT_CAP) -> dict:
    from app.matcha.services import property_cat

    conn = await get_db_connection()
    try:
        if building_id is not None:
            bid = building_id if isinstance(building_id, UUID) else UUID(str(building_id))
            return await property_cat.enrich_building(conn, bid)

        rows = await conn.fetch(
            """
            SELECT id FROM company_property_buildings
            WHERE lat IS NULL
               OR cat_refreshed_at IS NULL
               OR cat_refreshed_at < NOW() - make_interval(days => $1)
            ORDER BY cat_refreshed_at NULLS FIRST
            LIMIT $2
            """,
            _STALE_DAYS, cap,
        )
        ok = 0
        for r in rows:
            try:
                await property_cat.enrich_building(conn, r["id"])
                ok += 1
            except Exception as exc:  # noqa: BLE001 - one building must not abort the sweep
                print(f"[Property Cat] building {r['id']} failed: {exc}")
        return {"processed": ok, "selected": len(rows)}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=2)
def refresh_property_cat(self, building_id=None) -> dict:
    """Geocode + refresh catastrophe hazard for one building or a periodic batch."""
    try:
        result = asyncio.run(_refresh(building_id))
        print(f"[Property Cat] Refresh complete: {result}")
        return {"status": "success", **result}
    except Exception as e:  # noqa: BLE001
        print(f"[Property Cat] Refresh failed: {e}")
        raise self.retry(exc=e, countdown=300)
