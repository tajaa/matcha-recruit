"""Cappe locations — owner CRUD for a site's physical locations (LA, San Diego…).

Booking config rows (types, availability, staff, rate rules, discounts) carry a
NULLABLE location_id; a site with no locations behaves as a single-location site.
A location's own address / hours / timezone drive its booking widget + map/hours.
"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ...core.services.geo import geocode_address
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeLocation, CappeLocationCreate, CappeLocationUpdate
from ..services.directory import refresh_site_search
from ._shared import get_owned_site, loads_list
from .render import invalidate_render_cache

logger = logging.getLogger(__name__)

router = APIRouter()

_LOC_COLS = (
    "id, site_id, name, address, lat, lng, city, region, timezone, hours, contact_phone, "
    "contact_email, is_default, active, sort_order, created_at, updated_at"
)


async def _geocode_location(site_id: UUID, location_id: UUID) -> None:
    """Background: resolve a location's free-text address to coordinates + city.

    `lat`/`lng` have always been OPTIONAL HAND-TYPED fields on the location
    form, used only to draw a map embed — so they are null for nearly every
    site. Discover's "near me" reads them, which means without this the radius
    filter would match almost nothing.

    Runs after the response (external HTTP, US Census), owns its connection, and
    swallows everything: a failed geocode costs the site its distance sort, not
    its location. Never overwrites coordinates the owner typed themselves.
    """
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT address, lat, lng FROM cappe_locations WHERE id = $1 AND site_id = $2",
                location_id, site_id,
            )
            if row is None or not (row["address"] or "").strip():
                return
            result = await geocode_address(row["address"])
            if result is None:
                return
            # COALESCE on lat/lng: an owner-supplied coordinate is authoritative,
            # but city/region are ours to fill either way.
            await conn.execute(
                """UPDATE cappe_locations
                      SET lat = COALESCE(lat, $3), lng = COALESCE(lng, $4),
                          city = $5, region = $6, geocoded_at = NOW(), updated_at = NOW()
                    WHERE id = $1 AND site_id = $2""",
                location_id, site_id,
                result["lat"], result["lng"], result["city"], result["region"],
            )
            # City/region are indexed at weight D, so "coffee portland" works.
            await refresh_site_search(conn, site_id)
    except Exception:  # noqa: BLE001 - best-effort, post-response
        logger.warning("cappe: geocode failed for location %s", location_id, exc_info=True)


def _row(r) -> dict:
    d = dict(r)
    d["hours"] = loads_list(d.get("hours"))
    return d


async def _clear_other_defaults(conn, site_id: UUID, keep_id) -> None:
    await conn.execute(
        "UPDATE cappe_locations SET is_default = false, updated_at = NOW() "
        "WHERE site_id = $1 AND is_default = true AND ($2::uuid IS NULL OR id <> $2)",
        site_id, keep_id,
    )


@router.get("/sites/{site_id}/locations", response_model=list[CappeLocation])
async def list_locations(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_LOC_COLS} FROM cappe_locations WHERE site_id = $1 "
            "ORDER BY is_default DESC, sort_order, created_at",
            site_id,
        )
    return [_row(r) for r in rows]


@router.post("/sites/{site_id}/locations", response_model=CappeLocation, status_code=status.HTTP_201_CREATED)
async def create_location(
    site_id: UUID,
    body: CappeLocationCreate,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            # The first location on a site is implicitly the default.
            has_any = await conn.fetchval("SELECT 1 FROM cappe_locations WHERE site_id = $1 LIMIT 1", site_id)
            is_default = body.is_default or not has_any
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_locations
                    (site_id, name, address, lat, lng, timezone, hours, contact_phone,
                     contact_email, is_default, active, sort_order)
                    VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12) RETURNING {_LOC_COLS}""",
                site_id, body.name, body.address, body.lat, body.lng, body.timezone,
                json.dumps([h.model_dump() for h in body.hours]), body.contact_phone,
                body.contact_email, is_default, body.active, body.sort_order,
            )
            if is_default:
                await _clear_other_defaults(conn, site_id, row["id"])
    await invalidate_render_cache(site_id)
    background.add_task(_geocode_location, site_id, row["id"])
    return _row(row)


@router.put("/sites/{site_id}/locations/{location_id}", response_model=CappeLocation)
async def update_location(
    site_id: UUID, location_id: UUID, body: CappeLocationUpdate,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        sets, args = [], []
        for col in ("name", "address", "lat", "lng", "timezone", "contact_phone",
                    "contact_email", "is_default", "active", "sort_order"):
            val = getattr(body, col)
            if val is not None:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if body.hours is not None:
            args.append(json.dumps([h.model_dump() for h in body.hours]))
            sets.append(f"hours = ${len(args)}::jsonb")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_LOC_COLS} FROM cappe_locations WHERE id = $1 AND site_id = $2", location_id, site_id
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
            return _row(row)
        sets.append("updated_at = NOW()")
        args.extend([location_id, site_id])
        async with conn.transaction():
            row = await conn.fetchrow(
                f"UPDATE cappe_locations SET {', '.join(sets)} "
                f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_LOC_COLS}",
                *args,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
            if body.is_default:
                await _clear_other_defaults(conn, site_id, location_id)
    await invalidate_render_cache(site_id)
    # Only a changed address needs re-resolving; every other edit leaves the
    # coordinates (and the city we derived from them) correct.
    if body.address is not None:
        background.add_task(_geocode_location, site_id, location_id)
    return _row(row)


@router.delete("/sites/{site_id}/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    site_id: UUID, location_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Soft-delete (active=false) to preserve booking history. If it was the
    default, promote the next active location."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE cappe_locations SET active = false, is_default = false, updated_at = NOW() "
                "WHERE id = $1 AND site_id = $2 RETURNING is_default",
                location_id, site_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
            # Ensure a default still exists among active locations.
            still = await conn.fetchval(
                "SELECT 1 FROM cappe_locations WHERE site_id = $1 AND active = true AND is_default = true LIMIT 1",
                site_id,
            )
            if not still:
                await conn.execute(
                    "UPDATE cappe_locations SET is_default = true, updated_at = NOW() WHERE id = ("
                    "  SELECT id FROM cappe_locations WHERE site_id = $1 AND active = true "
                    "  ORDER BY sort_order, created_at LIMIT 1)",
                    site_id,
                )
    await invalidate_render_cache(site_id)
