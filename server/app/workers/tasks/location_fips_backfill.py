"""Geocode business locations to Census FIPS anchors (migration jurfips01).

Jurisdiction resolution is name-match today, which silently mis-resolves the
hard addresses (unincorporated, annexation edges, shared town names). This worker
adds the deterministic anchor OUT of the request path — geocoding is slow and
flaky, so it must never sit inline in onboarding.

Per location it stamps `place_fips`/`county_fips` + flips `jurisdiction_resolution`
to 'fips' (geocoded) or 'unresolved' (geocode found nothing), stamps the location's
current jurisdiction row with its FIPS, and FLAGS — never silently repoints — a
mismatch where the geocoded county disagrees with the name-matched jurisdiction's
county, for admin review.

Scheduler-gated on `scheduler_settings.task_key = 'location_fips_backfill'`, seeded
DISABLED (makes live Census calls; an admin enables it deliberately). `force=True`
is the manual Trigger — runs even when disabled, same as the other sweeps.
"""
import asyncio
import logging
from typing import Any, Dict

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

# Per-cycle cap — the worker restarts hourly, and we do not want to hammer the
# free Census endpoint. `max_per_cycle` on the scheduler row overrides this.
DEFAULT_BATCH = 100

# Minimum hours between scheduled runs (the atomic last_run_at claim). Stops the
# hourly worker restart from re-geocoding a batch every hour.
MIN_INTERVAL_HOURS = 6


async def _backfill(force: bool = False) -> Dict[str, Any]:
    import httpx
    from app.matcha.services.property_cat import geocode_fips

    conn = await get_db_connection()
    try:
        batch = DEFAULT_BATCH
        if not force:
            sched = await scheduler_settings_row(conn, "location_fips_backfill")
            if not sched or not sched["enabled"]:
                return {"status": "disabled"}
            batch = int(sched["max_per_cycle"] or DEFAULT_BATCH)

            # Atomic interval claim — the worker restarts hourly and re-fires this
            # on startup; without the claim every restart geocodes a fresh batch
            # and two concurrent workers race the same rows. Same pattern as
            # vertical_coverage_sweep. force=True (manual Trigger) bypasses it.
            claimed = await conn.fetchval(
                """
                UPDATE scheduler_settings SET last_run_at = NOW()
                WHERE task_key = 'location_fips_backfill'
                  AND (last_run_at IS NULL
                       OR last_run_at < NOW() - ($1 || ' hours')::interval)
                RETURNING TRUE
                """,
                str(MIN_INTERVAL_HOURS),
            )
            if not claimed:
                return {"status": "skipped", "reason": "a backfill ran recently"}
        else:
            await conn.execute(
                "UPDATE scheduler_settings SET last_run_at = NOW() "
                "WHERE task_key = 'location_fips_backfill'"
            )

        # Candidates: never-anchored locations (still 'name') that have an address
        # to geocode. Oldest first, bounded.
        rows = await conn.fetch(
            """
            SELECT id, address, city, state, zipcode, county, jurisdiction_id
            FROM business_locations
            WHERE jurisdiction_resolution = 'name'
              AND city IS NOT NULL AND state IS NOT NULL
            ORDER BY created_at NULLS LAST
            LIMIT $1
            """,
            batch,
        )
    finally:
        await conn.close()

    if not rows:
        return {"status": "ok", "processed": 0, "anchored": 0, "unresolved": 0, "mismatches": 0}

    anchored = unresolved = mismatches = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for r in rows:
            geo = None
            try:
                geo = await geocode_fips(client, r["address"], r["city"], r["state"], r["zipcode"])
            except Exception as exc:
                logger.warning("fips backfill: geocode failed for %s: %s", r["id"], exc)

            conn = await get_db_connection()
            try:
                if not geo:
                    await conn.execute(
                        "UPDATE business_locations SET jurisdiction_resolution = 'unresolved' WHERE id = $1",
                        r["id"],
                    )
                    unresolved += 1
                    continue

                await conn.execute(
                    """
                    UPDATE business_locations
                    SET place_fips = $2, county_fips = $3, jurisdiction_resolution = 'fips'
                    WHERE id = $1
                    """,
                    r["id"], geo.get("place_fips"), geo.get("county_fips"),
                )
                anchored += 1

                # Stamp the location's current jurisdiction row with its FIPS
                # (best-effort). Two guards, both learned from review:
                #  - place_fips only onto a CITY node — a location name-matched to
                #    a county/state row must not have a place stamped on it (wrong
                #    anchor), and county_fips can still ride onto any level.
                #  - the place_fips index is UNIQUE (partial); a duplicate city row
                #    (which the cleanup-duplicates tooling exists to merge) would
                #    collide, so swallow unique_violation and just skip that stamp
                #    rather than abort the whole batch. county_fips is unconstrained.
                if r["jurisdiction_id"] and geo.get("county_fips"):
                    await conn.execute(
                        "UPDATE jurisdictions SET county_fips = COALESCE(county_fips, $2) WHERE id = $1",
                        r["jurisdiction_id"], geo.get("county_fips"),
                    )
                if r["jurisdiction_id"] and geo.get("place_fips"):
                    try:
                        await conn.execute(
                            """
                            UPDATE jurisdictions
                            SET place_fips = COALESCE(place_fips, $2)
                            WHERE id = $1 AND level::text = 'city'
                            """,
                            r["jurisdiction_id"], geo.get("place_fips"),
                        )
                    except Exception as exc:  # unique_violation on a dup city row, etc.
                        logger.warning(
                            "fips backfill: place_fips stamp skipped for jurisdiction %s (%s): %s",
                            r["jurisdiction_id"], geo.get("place_fips"), exc,
                        )

                # Flag — never repoint — a county disagreement for admin review.
                geo_county = (geo.get("county_name") or "").strip().lower()
                cur_county = (r["county"] or "").strip().lower()
                if geo_county and cur_county and geo_county != cur_county:
                    mismatches += 1
                    logger.warning(
                        "fips backfill MISMATCH: location %s name-matched county '%s' but "
                        "geocode says '%s' (FIPS %s) — review",
                        r["id"], cur_county, geo_county, geo.get("county_fips"),
                    )
            finally:
                await conn.close()

    return {"status": "ok", "processed": len(rows), "anchored": anchored,
            "unresolved": unresolved, "mismatches": mismatches}


@celery_app.task(bind=True, max_retries=2)
def run_location_fips_backfill(self, force: bool = False) -> Dict[str, Any]:
    """Geocode a batch of business locations to FIPS anchors. Re-fires on worker
    startup; gated by the (disabled-by-default) scheduler row."""
    try:
        result = asyncio.run(_backfill(force=force))
        print(f"[FIPS Backfill] {result}")
        return result
    except Exception as e:
        print(f"[FIPS Backfill] Failed: {e}")
        raise self.retry(exc=e, countdown=300)
