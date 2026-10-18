"""The two commercial Matcha products, managed in admin and mirrored to Stripe.

Pricing/entitlements remain in their existing tables. Only account- and mode-
scoped catalog IDs and reconciliation state live in platform_settings (no new
schema). Advisory transaction locks serialize sync/reconciliation across app
processes. Deterministic product IDs and price lookup/idempotency keys recover
Stripe success followed by a timeout or database rollback without duplicates.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone

from app.config import get_settings
from app.database import get_connection
from app.core.services.matcha_lite_pricing import get_matcha_lite_pricing
from app.core.services.product_definitions import get_product_by_slug
from app.core.services.stripe_service import StripeServiceError, stripe

logger = logging.getLogger(__name__)
PRODUCTS = {"incidents": "Matcha Incidents", "scheduler": "Matcha Scheduler"}
SCHEDULER_SLUG = "schedule-comm"
INCIDENT_PLANS = ("matcha_lite", "matcha_lite_essentials")
CATALOG_EVENTS = frozenset({
    "product.created", "product.updated", "product.deleted",
    "price.created", "price.updated", "price.deleted",
})


class CatalogError(StripeServiceError):
    pass


def _dict(value) -> dict:
    return value.to_dict() if hasattr(value, "to_dict") else dict(value)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:24]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CatalogContext:
    account_id: str
    livemode: bool
    api_key: str

    @property
    def scope(self) -> str:
        return _digest([self.account_id, self.livemode])

    def state_key(self, product_key: str) -> str:
        return f"stripe_catalog:{self.scope}:{product_key}"

    def product_id(self, product_key: str) -> str:
        return f"matcha_{product_key}_{self.scope}"


@dataclass(frozen=True)
class CatalogPrice:
    key: str
    label: str
    amount_cents: int
    pricing_model: str
    block_size: int = 1
    min_headcount: int = 1
    max_headcount: int = 300

    def quantity(self, headcount: int, locations: int | None) -> int:
        if not self.min_headcount <= headcount <= self.max_headcount:
            raise CatalogError("Company headcount is outside this product's limits")
        if self.pricing_model == "per_location":
            if not locations or locations < 1:
                raise CatalogError("Company location count is required")
            return locations
        if self.pricing_model == "per_seat":
            return headcount
        if self.pricing_model == "block":
            return math.ceil(headcount / self.block_size)
        return 1


@dataclass(frozen=True)
class CatalogProduct:
    key: str
    name: str
    description: str
    active: bool
    prices: tuple[CatalogPrice, ...]

    @property
    def fingerprint(self) -> str:
        return _digest(asdict(self))


async def catalog_context() -> CatalogContext:
    key = get_settings().stripe_secret_key
    if stripe is None or not key:
        raise CatalogError("Configure the server's Stripe secret key first")
    if not key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
        raise CatalogError("Stripe secret key must identify test or live mode")
    account = _dict(await asyncio.to_thread(stripe.Account.retrieve, api_key=key))
    return CatalogContext(account["id"], key.startswith(("sk_live_", "rk_live_")), key)


async def load_product(conn, product_key: str) -> CatalogProduct:
    if product_key not in PRODUCTS:
        raise CatalogError("Only Matcha Incidents and Matcha Scheduler are commercial products")
    if product_key == "incidents":
        plans = []
        for code in INCIDENT_PLANS:
            pricing = await get_matcha_lite_pricing(conn, code)
            plans.append(CatalogPrice(
                code, "Standard" if code == "matcha_lite" else "Essentials",
                pricing.effective_price_per_block_cents, "block", pricing.block_size,
                pricing.min_headcount, pricing.max_headcount,
            ))
        return CatalogProduct(product_key, PRODUCTS[product_key], "Incident reporting and HR resources", True, tuple(plans))
    product = await get_product_by_slug(conn, SCHEDULER_SLUG, published_only=False)
    if product is None or not product.is_paid:
        raise CatalogError("Set up the paid schedule-comm product in Products first")
    return CatalogProduct(
        product_key, product.name, product.description,
        # Archiving stops new signups, but existing pending tenants can finish
        # paying, as the custom-product checkout contract already promises.
        product.status in ("published", "archived"),
        (CatalogPrice("scheduler", "Monthly", int(product.price_cents or 0), product.pricing_model,
                      product.block_size or 1, product.min_headcount, product.max_headcount),),
    )


async def _read_state(conn, context: CatalogContext, product_key: str) -> dict:
    raw = await conn.fetchval("SELECT value FROM platform_settings WHERE key = $1", context.state_key(product_key))
    state = json.loads(raw) if isinstance(raw, str) else (raw or {})
    if state and (state.get("account_id") != context.account_id or state.get("livemode") != context.livemode):
        raise CatalogError("Stripe catalog account/mode mismatch")
    return state


async def _write_state(conn, context: CatalogContext, product_key: str, state: dict) -> None:
    await conn.execute(
        """INSERT INTO platform_settings (key, value, updated_at) VALUES ($1, $2::jsonb, NOW())
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
        context.state_key(product_key), json.dumps(state),
    )


async def _configured_product(conn, product_key: str, state: dict) -> CatalogProduct:
    source = await load_product(conn, product_key)
    return replace(source, name=state.get("name_override", source.name),
                   description=state.get("description_override", source.description))


async def _lock(conn, context: CatalogContext, product_key: str) -> None:
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", context.state_key(product_key))


def _price_matches(remote: dict, price: CatalogPrice, product_id: str, *, active: bool = True) -> bool:
    recurring = remote.get("recurring") or {}
    return (
        remote.get("product") == product_id and remote.get("currency") == "usd"
        and remote.get("unit_amount") == price.amount_cents
        and recurring.get("interval") == "month" and recurring.get("interval_count") == 1
        and recurring.get("usage_type") == "licensed"
        and remote.get("billing_scheme") == "per_unit"
        and remote.get("active") is active
    )


def _sync_remote(context: CatalogContext, product: CatalogProduct) -> dict:
    product_id = context.product_id(product.key)
    options = {"api_key": context.api_key}
    try:
        remote_product = _dict(stripe.Product.retrieve(product_id, **options))
    except Exception as exc:
        if getattr(exc, "code", None) != "resource_missing":
            raise
        remote_product = _dict(stripe.Product.create(
            id=product_id, name=product.name, description=product.description, active=product.active,
            metadata={"matcha_catalog": product.key},
            idempotency_key=f"matcha-product:{context.scope}:{product.key}:{product.fingerprint}", **options,
        ))
    if remote_product.get("metadata", {}).get("matcha_catalog") != product.key:
        raise CatalogError("The Stripe product ID is already owned by another integration")
    prices = {}
    for price in product.prices:
        if price.amount_cents <= 0 or price.block_size < 1:
            raise CatalogError("A commercial product needs a positive price and block size")
        lookup = f"matcha:{context.scope}:{price.key}:{_digest(asdict(price))}"
        found = _dict(stripe.Price.list(lookup_keys=[lookup], limit=1, **options))["data"]
        if found:
            remote = _dict(found[0])
            if not _price_matches(remote, price, product_id, active=bool(remote.get("active"))):
                raise CatalogError("A Stripe price no longer matches the admin pricing configuration")
            if not remote["active"]:
                remote = _dict(stripe.Price.modify(remote["id"], active=True, **options))
        else:
            remote = _dict(stripe.Price.create(
                product=product_id, currency="usd", unit_amount=price.amount_cents,
                recurring={"interval": "month"}, lookup_key=lookup,
                nickname=price.label, metadata={"matcha_catalog": product.key, "source": price.key},
                idempotency_key=lookup, **options,
            ))
        if not _price_matches(remote, price, product_id):
            raise CatalogError("Stripe did not return the requested monthly price")
        prices[price.key] = {**asdict(price), "stripe_price_id": remote["id"]}
    stripe.Product.modify(
        product_id, name=product.name, description=product.description, active=product.active,
        default_price=prices[product.prices[0].key]["stripe_price_id"], **options,
    )
    return {"stripe_product_id": product_id, "prices": prices}


async def _archive_retired_prices(context: CatalogContext, product_key: str) -> None:
    """Retire only IDs no longer referenced by a committed catalog mapping.

    Reacquire the lock and reread state: another admin may already have changed
    back to an older price while this sync was committing. Failed cleanup stays
    queued, and does not make a valid new checkout price unavailable.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            await _lock(conn, context, product_key)
            state = await _read_state(conn, context, product_key)
            retired = state.get("retired_price_ids", [])
            if not retired:
                return
            current = {p["stripe_price_id"] for p in state.get("prices", {}).values()}
            for price_id in retired:
                if price_id in current:
                    continue
                try:
                    await asyncio.to_thread(stripe.Price.modify, price_id, active=False, api_key=context.api_key)
                except Exception as exc:
                    if getattr(exc, "code", None) != "resource_missing":
                        raise
            state["retired_price_ids"] = []
            await _write_state(conn, context, product_key, state)


async def sync_product(product_key: str, *, force: bool = True, changed_by: str | None = None) -> dict:
    if product_key not in PRODUCTS:
        raise CatalogError("Only Matcha Incidents and Matcha Scheduler can be synced")
    context = await catalog_context()
    error = None
    async with get_connection() as conn:
        async with conn.transaction():
            await _lock(conn, context, product_key)
            state = await _read_state(conn, context, product_key)
            product = await _configured_product(conn, product_key, state)
            if not force and state.get("fingerprint") == product.fingerprint and state.get("status") == "synced":
                return state
            state = {**state, "account_id": context.account_id, "livemode": context.livemode,
                     "product_key": product_key, "changed_by": changed_by}
            try:
                remote = await asyncio.to_thread(_sync_remote, context, product)
                current_ids = {p["stripe_price_id"] for p in remote["prices"].values()}
                old_ids = {p["stripe_price_id"] for p in state.get("prices", {}).values()}
                state["retired_price_ids"] = sorted((set(state.get("retired_price_ids", [])) | old_ids) - current_ids)
                state.update(remote, fingerprint=product.fingerprint, status="synced", error=None,
                             synced_at=_now(), webhook_verified_at=None)
            except Exception as exc:
                error = CatalogError(str(exc).replace(context.api_key, "[redacted]")[:500])
                state.update(status="error", error=str(error))
                logger.warning("Stripe catalog sync failed for %s: %s", product_key, error)
            await _write_state(conn, context, product_key, state)
    if error:
        raise error
    try:
        await _archive_retired_prices(context, product_key)
    except Exception:
        logger.exception("Stripe catalog %s is synced; retired-price cleanup will retry on the next sync", product_key)
    return state


async def sync_after_save(product_key: str, *, changed_by: str | None = None) -> None:
    """A local price save stays committed if Stripe is unavailable; admin can retry."""
    try:
        if not get_settings().stripe_secret_key:
            return
        await sync_product(product_key, changed_by=changed_by)
    except Exception:
        logger.exception("Admin pricing saved; Stripe catalog %s needs retry", product_key)


async def save_catalog_details(product_key: str, *, name: str, description: str, changed_by: str) -> None:
    if product_key not in PRODUCTS:
        raise CatalogError("Only Matcha Incidents and Matcha Scheduler can be edited")
    context = await catalog_context()
    async with get_connection() as conn:
        async with conn.transaction():
            await _lock(conn, context, product_key)
            state = await _read_state(conn, context, product_key)
            state.update(account_id=context.account_id, livemode=context.livemode, product_key=product_key,
                         name_override=name, description_override=description, status="out_of_sync", changed_by=changed_by)
            await _write_state(conn, context, product_key, state)
    await sync_product(product_key, changed_by=changed_by)


async def checkout_line_item(
    product_key: str, price_key: str, *, headcount: int, amount_cents: int, locations: int | None = None,
) -> dict:
    state = await sync_product(product_key, force=False)
    price_data = state.get("prices", {}).get(price_key)
    if not price_data:
        raise CatalogError("This product's Stripe price has not been synced")
    price = CatalogPrice(**{k: v for k, v in price_data.items() if k != "stripe_price_id"})
    quantity = price.quantity(headcount, locations)
    if quantity * price.amount_cents != amount_cents:
        raise CatalogError("Pricing changed while checkout was opening. Reload and try again.")
    # A published product may have been archived while the caller was loading it.
    async with get_connection() as conn:
        context = CatalogContext(state["account_id"], state["livemode"], "")
        current = await _read_state(conn, context, product_key)
        product = await _configured_product(conn, product_key, current)
    if not product.active or product.fingerprint != state.get("fingerprint"):
        raise CatalogError("This product changed. Reload before starting checkout.")
    return {"price": price_data["stripe_price_id"], "quantity": quantity}


async def catalog_status() -> dict:
    configured = bool(get_settings().stripe_secret_key and stripe is not None)
    context = await catalog_context() if configured else None
    products = []
    async with get_connection() as conn:
        webhook = await _read_state(conn, context, "webhook") if context else {}
        for key, name in PRODUCTS.items():
            try:
                state = await _read_state(conn, context, key) if context else {}
                definition = await _configured_product(conn, key, state)
                status = state.get("status", "not_synced") if configured else "not_configured"
                if state.get("fingerprint") and state["fingerprint"] != definition.fingerprint:
                    status = "out_of_sync"
                products.append({"key": key, "name": name, "active": definition.active,
                                 "display_name": definition.name, "description": definition.description,
                                 "status": status, "stripe_product_id": state.get("stripe_product_id"),
                                 "prices": list(state.get("prices", {}).values()), "error": state.get("error"),
                                 "synced_at": state.get("synced_at"),
                                 "webhook_verified_at": state.get("webhook_verified_at")})
            except CatalogError as exc:
                products.append({"key": key, "name": name, "active": False, "status": "not_ready", "error": str(exc),
                                 "display_name": name, "description": "",
                                 "prices": [], "stripe_product_id": None, "synced_at": None, "webhook_verified_at": None})
    return {"configured": configured, "account_id": context.account_id if context else None,
            "livemode": context.livemode if context else None, "products": products, "webhook": webhook}


def _remote_is_current(context: CatalogContext, product: CatalogProduct, state: dict) -> bool:
    options = {"api_key": context.api_key}
    try:
        remote = _dict(stripe.Product.retrieve(context.product_id(product.key), **options))
        if (remote.get("deleted") or remote.get("active") != product.active
                or remote.get("metadata", {}).get("matcha_catalog") != product.key
                or remote.get("name") != product.name or (remote.get("description") or "") != product.description):
            return False
        for price in product.prices:
            saved = state.get("prices", {}).get(price.key)
            if not saved or not _price_matches(_dict(stripe.Price.retrieve(saved["stripe_price_id"], **options)), price, remote["id"]):
                return False
        first = state["prices"][product.prices[0].key]["stripe_price_id"]
        return remote.get("default_price") == first
    except Exception as exc:
        if getattr(exc, "code", None) == "resource_missing":
            return False
        raise


async def reconcile_catalog_event(event_object: dict, *, livemode: bool, account: str | None = None) -> None:
    context = await catalog_context()
    if livemode != context.livemode or (account and account != context.account_id):
        return
    product_id = event_object.get("product") if event_object.get("object") == "price" else event_object.get("id")
    key = next((k for k in PRODUCTS if context.product_id(k) == product_id), None)
    if key is None:
        return
    async with get_connection() as conn:
        async with conn.transaction():
            await _lock(conn, context, key)
            state = await _read_state(conn, context, key)
            if not state:
                return
            product = await _configured_product(conn, key, state)
            # Retrieve current Stripe objects: webhook snapshots can be stale,
            # duplicated, or arrive in the reverse order of admin saves.
            current = await asyncio.to_thread(_remote_is_current, context, product, state)
            state.update(status="synced" if current and state.get("fingerprint") == product.fingerprint else "out_of_sync",
                         webhook_verified_at=_now(), error=None)
            await _write_state(conn, context, key, state)


async def configure_catalog_webhook() -> dict:
    """Extend the existing signed endpoint; preserve all payment event types.

    Never create an endpoint whose signing secret the server does not have.
    """
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise CatalogError("Configure the server's Stripe webhook signing secret first")
    context = await catalog_context()
    url = settings.app_base_url.rstrip("/") + "/api/webhooks/stripe"

    def configure():
        endpoints = stripe.WebhookEndpoint.list(limit=100, api_key=context.api_key)
        matches = [e for e in endpoints.auto_paging_iter() if e.url == url and e.status == "enabled"]
        if len(matches) != 1:
            raise CatalogError(f"Expected one enabled Stripe webhook endpoint for {url}; found {len(matches)}")
        endpoint = matches[0]
        enabled = set(endpoint.enabled_events)
        if "*" not in enabled and not CATALOG_EVENTS.issubset(enabled):
            stripe.WebhookEndpoint.modify(endpoint.id, enabled_events=sorted(enabled | CATALOG_EVENTS), api_key=context.api_key)
        return {"url": url, "endpoint_id": endpoint.id, "catalog_events_enabled": True}

    result = await asyncio.to_thread(configure)
    async with get_connection() as conn:
        await _write_state(conn, context, "webhook", {
            **result, "account_id": context.account_id, "livemode": context.livemode,
        })
    return result
