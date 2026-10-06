"""Cappe shipping zones — destinations beyond the store's home country.

The home country's rates are the store's own shipping settings
(`PUT /sites/{id}`); zones are replaced as a set, like discounts and rate
rules. Nothing points at a zone row (an order stores the country and the
amounts it was charged), so replacing them can't orphan anything.

Plan-gated (`shipping_zones`). Clearing the zones is always allowed, so a
downgraded store can tidy up.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeShippingZones, CappeShippingZonesReplace
from ..services.entitlements import resolve_entitlements
from ..services.shipping import SHIP_COUNTRIES, home_country, load_zones, site_currency, validate_zones
from ._shared import get_owned_site

router = APIRouter()

_SORTED_COUNTRIES = sorted(SHIP_COUNTRIES)


def _view(site, ent, zones) -> dict:
    return {
        "enabled": ent.has("shipping_zones"),
        "home_country": home_country(site),
        "currency": site_currency(site),
        "countries": _SORTED_COUNTRIES,
        "zones": [{**z, "countries": list(z.get("countries") or [])} for z in zones],
    }


@router.get("/sites/{site_id}/shipping-zones", response_model=CappeShippingZones)
async def get_shipping_zones(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        # Every saved zone, even on a plan that no longer applies them, so the
        # owner sees what is paused rather than finding it gone.
        zones = await load_zones(conn, site_id, None)
    return _view(site, ent, zones)


@router.put("/sites/{site_id}/shipping-zones", response_model=CappeShippingZones)
async def replace_shipping_zones(
    site_id: UUID, body: CappeShippingZonesReplace,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        if body.zones and not ent.has("shipping_zones"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Shipping to other countries isn't included in your plan.",
            )
        validate_zones(body.zones, home=home_country(site))
        async with conn.transaction():
            # One save at a time per store: two interleaved replaces would
            # otherwise each delete the other's rows and keep both inserts.
            await conn.execute("SELECT 1 FROM cappe_sites WHERE id = $1 FOR UPDATE", site_id)
            await conn.execute("DELETE FROM cappe_shipping_zones WHERE site_id = $1", site_id)
            for i, zone in enumerate(body.zones):
                await conn.execute(
                    """INSERT INTO cappe_shipping_zones
                           (site_id, name, countries, rest_of_world, flat_cents,
                            free_threshold_cents, charge_tax, sort_order)
                       VALUES ($1, $2, $3::varchar[], $4, $5, $6, $7, $8)""",
                    site_id, zone.name, zone.countries, zone.rest_of_world, zone.flat_cents,
                    zone.free_threshold_cents, zone.charge_tax, i,
                )
            zones = await load_zones(conn, site_id, None)
    return _view(site, ent, zones)
