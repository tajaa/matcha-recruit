"""Cappe shipping zones — destinations beyond the store's home country — and
every destination's delivery options.

The home country's flat rate is the store's own shipping settings
(`PUT /sites/{id}`); zones are replaced as a set, like discounts and rate
rules, and the delivery options (`cappe_shipping_rates`) with them. Nothing
points at a zone or rate row (an order stores the country, the option's name
and the amounts it was charged), so replacing them can't orphan anything.

Plan-gated (`shipping_zones`). Clearing everything is always allowed, so a
downgraded store can tidy up.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount, CappeShippingRateInput, CappeShippingZones, CappeShippingZonesReplace,
)
from ..services.entitlements import resolve_entitlements
from ..services.shipping import (
    SHIP_COUNTRIES, home_country, load_rate_rows, load_zones, site_currency, validate_rates, validate_zones,
)
from ._shared import get_owned_site

router = APIRouter()

_SORTED_COUNTRIES = sorted(SHIP_COUNTRIES)


def _view(site, ent, zones, rates) -> dict:
    by_zone: dict = {}
    for r in rates:
        by_zone.setdefault(r["zone_id"], []).append(r)
    return {
        "enabled": ent.has("shipping_zones"),
        "home_country": home_country(site),
        "currency": site_currency(site),
        "countries": _SORTED_COUNTRIES,
        "zones": [{**z, "countries": list(z.get("countries") or []), "rates": by_zone.get(z["id"], [])}
                  for z in zones],
        "home_rates": by_zone.get(None, []),
    }


def _kept(rows) -> list[CappeShippingRateInput]:
    return [CappeShippingRateInput.model_validate(dict(r)) for r in rows]


async def _insert_rates(conn, site_id, zone_id, rates) -> None:
    if not rates:
        return
    # One round trip per destination, not per option: this runs under the
    # store's FOR UPDATE lock.
    await conn.executemany(
        """INSERT INTO cappe_shipping_rates
               (site_id, zone_id, name, method, amount_cents, per_item_cents, min_subtotal_cents,
                max_subtotal_cents, min_weight_g, max_weight_g, free_over_cents, delivery_min_days,
                delivery_max_days, postal_codes, instructions, sort_order)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::text[], $15, $16)""",
        [(site_id, zone_id, rate.name, rate.method, rate.amount_cents, rate.per_item_cents,
          rate.min_subtotal_cents, rate.max_subtotal_cents, rate.min_weight_g, rate.max_weight_g,
          rate.free_over_cents, rate.delivery_min_days, rate.delivery_max_days, rate.postal_codes,
          rate.instructions, i) for i, rate in enumerate(rates)],
    )


@router.get("/sites/{site_id}/shipping-zones", response_model=CappeShippingZones)
async def get_shipping_zones(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        # Every saved zone and option, even on a plan that no longer applies
        # them, so the owner sees what is paused rather than finding it gone.
        zones = await load_zones(conn, site_id, None)
        rates = await load_rate_rows(conn, site_id)
    return _view(site, ent, zones, rates)


@router.put("/sites/{site_id}/shipping-zones", response_model=CappeShippingZones)
async def replace_shipping_zones(
    site_id: UUID, body: CappeShippingZonesReplace,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        if not ent.has("shipping_zones") and (body.zones or body.home_rates):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Shipping zones and delivery options aren't included in your plan.",
            )
        validate_zones(body.zones, home=home_country(site))
        for zone in body.zones:
            validate_rates(zone.rates or [], where=zone.name)
        validate_rates(body.home_rates or [], where="Home")
        async with conn.transaction():
            # One save at a time per store: two interleaved replaces would
            # otherwise each delete the other's rows and keep both inserts.
            await conn.execute("SELECT 1 FROM cappe_sites WHERE id = $1 FOR UPDATE", site_id)
            # Options a save leaves out (None) are kept: the home ones as they
            # are, a zone's by the zone's name (its id changes with the set).
            old = await conn.fetch(
                """SELECT r.*, z.name AS zone_name FROM cappe_shipping_rates r
                     LEFT JOIN cappe_shipping_zones z ON z.id = r.zone_id
                    WHERE r.site_id = $1 ORDER BY r.sort_order, r.created_at""",
                site_id,
            )
            home_rates = body.home_rates if body.home_rates is not None else _kept(
                r for r in old if r["zone_id"] is None
            )
            # A zone's kept options by its old name, each set handed out once:
            # two zones sharing a name must not both inherit (and double) them.
            kept_by_name: dict = {}
            for r in old:
                if r["zone_id"] is not None:
                    kept_by_name.setdefault(r["zone_name"], []).append(r)
            # Zone rates go with their zones (ON DELETE CASCADE).
            await conn.execute("DELETE FROM cappe_shipping_rates WHERE site_id = $1", site_id)
            await conn.execute("DELETE FROM cappe_shipping_zones WHERE site_id = $1", site_id)
            for i, zone in enumerate(body.zones):
                zone_id = await conn.fetchval(
                    """INSERT INTO cappe_shipping_zones
                           (site_id, name, countries, rest_of_world, flat_cents,
                            free_threshold_cents, charge_tax, sort_order)
                       VALUES ($1, $2, $3::varchar[], $4, $5, $6, $7, $8) RETURNING id""",
                    site_id, zone.name, zone.countries, zone.rest_of_world, zone.flat_cents,
                    zone.free_threshold_cents, zone.charge_tax, i,
                )
                rates = zone.rates if zone.rates is not None else _kept(kept_by_name.pop(zone.name, []))
                await _insert_rates(conn, site_id, zone_id, rates)
            await _insert_rates(conn, site_id, None, home_rates)
            zones = await load_zones(conn, site_id, None)
            rates = await load_rate_rows(conn, site_id)
    return _view(site, ent, zones, rates)
