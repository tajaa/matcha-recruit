"""Buy: take the person to the store's checkout with the product in the cart.

Espresso never pays or places the order: the person reviews and pays at the
store. What it does is the walk there.

* A Shopify store (most brand stores), confirmed by Shopify itself: the
  store's `/meta.json` names its `*.myshopify.com` shop, and that shop's
  product (`https://<shop>/products/<handle>.js`) must come back from the
  finding's own host (Shopify redirects a shop to its own domain only). A
  site that merely looks like Shopify fails that, and gets the product page.
  The product data gives the variant, its price now (in the shop's currency,
  from `/meta.json`) and whether it is in stock; a cart permalink
  (`/cart/<variant>:<qty>`) opens checkout with it in the cart.
* With "Fill in my email and saved address" on (the default), the checkout
  link also carries the person's email and default saved shipping address
  (Shopify's `checkout[...]` parameters), so they reach that confirmed shop
  in the link. The preview lists exactly what is filled in. The link kept
  in the action's result afterwards carries none of it (`stored_url`); the
  frozen proposal and its preview keep it, as the person's own record of
  what they agreed to (like their saved addresses).
* Any other store: the product's page.

The link is built here from the finding's store page (provenance-gated when
it was found) and the store's own data, never from a model.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work import shipping_addresses
from app.matcha.services.matcha_work.agent_card.chat_flow import format_money
from app.matcha.services.matcha_work.agent_card.page_extract import site_of

from ..playbook import IntakeField
from ..research.links import store_link
from .base import ActionContext, ActionError, ItemAction, Line, Proposal, outcome

logger = logging.getLogger(__name__)

PRODUCT_BYTES = 1_000_000
PRODUCT_SECONDS = 15.0
MAX_QUANTITY = 10
_HANDLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~%-]{0,200}$")
_SHOP = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.myshopify\.com$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
BAD_QUANTITY = f"Quantity must be 1 to {MAX_QUANTITY}."

QUANTITY = IntakeField(key="quantity", label="Quantity", type="number", help=f"1 to {MAX_QUANTITY}")
FILL_IN = IntakeField(key="fill_in", label="Fill in my email and saved address", type="boolean", default="yes",
                      help="Shopify stores only: they go to the store in the checkout link.")


def store_page(item: dict) -> str | None:
    """The finding's store page: an http(s) link that isn't one of Google's."""
    return store_link(item.get("url"))


def available(ctx: ActionContext) -> str | None:
    if ctx.item.get("kind") != "product":
        return "Only products can be bought."
    if store_page(ctx.item) is None:
        return "Espresso only has Google's page for this one, not a store's."
    if ctx.item.get("status") == "unavailable":
        return "It looked unavailable when Espresso checked."
    return None


def product_handle(url: str) -> str | None:
    """`/products/<handle>` (also under a collection) from a store link."""
    parts = [p for p in urlsplit(url).path.split("/") if p]
    for n, part in enumerate(parts[:-1]):
        if part == "products" and _HANDLE.match(parts[n + 1]):
            return parts[n + 1].removesuffix(".js").removesuffix(".json")
    return None


def wanted_variant(url: str) -> int | None:
    value = dict(parse_qsl(urlsplit(url).query)).get("variant") or ""
    return int(value) if value.isdigit() else None


async def _json(url: str, fetch) -> tuple[dict | None, str]:
    """A small JSON document from a public page, and the URL it came from."""
    try:
        fetched = await fetch(url, max_bytes=PRODUCT_BYTES, accept="application/json",
                              total_timeout=PRODUCT_SECONDS)
    except (UnsafeURL, TimeoutError, OSError):
        return None, ""
    except Exception:
        logger.info("buy: store data fetch failed", exc_info=True)
        return None, ""
    if fetched.status != 200 or fetched.truncated:
        return None, ""
    try:
        data = json.loads(fetched.body)
    except (ValueError, UnicodeDecodeError):
        return None, ""
    return (data if isinstance(data, dict) else None), fetched.final_url or url


async def shopify_store(url: str, *, fetch=fetch_public) -> dict | None:
    """`{"product", "currency", "shop"}` when Shopify confirms the finding's
    host is a Shopify shop's own, else None."""
    handle = product_handle(url)
    host = urlsplit(url).hostname
    if handle is None or not host:
        return None
    meta, _ = await _json(f"https://{host}/meta.json", fetch)
    shop = str((meta or {}).get("myshopify_domain") or "").lower()
    if not _SHOP.match(shop):
        return None
    product, came_from = await _json(f"https://{shop}/products/{handle}.js", fetch)
    # Shopify sends a shop to its own domain: this host, or the shop itself.
    if product is None or site_of(urlsplit(came_from).hostname) not in (site_of(host), shop):
        return None
    variants = product.get("variants")
    if not isinstance(variants, list) or not any(isinstance(v, dict) and isinstance(v.get("id"), int) for v in variants):
        return None
    currency = str(meta.get("currency") or "").upper()
    return {"product": product, "currency": currency if _CURRENCY.match(currency) else None, "shop": shop}


def pick_variant(product: dict, wanted: int | None) -> dict | None:
    """The variant the link named, else the first in stock, else the first."""
    variants = [v for v in product.get("variants") or [] if isinstance(v, dict) and isinstance(v.get("id"), int)]
    named = next((v for v in variants if v["id"] == wanted), None)
    return named or next((v for v in variants if v.get("available")), None) or (variants[0] if variants else None)


def split_name(name: str) -> tuple[str, str]:
    parts = name.split()
    if not parts:
        return "", ""
    return (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (parts[0], "")


def checkout_link(host: str, variant_id: int, quantity: int, *, address: dict | None, email: str) -> str:
    """Shopify's cart permalink: straight to checkout, with what it can fill in."""
    params: list[tuple[str, str]] = []
    if email:
        params.append(("checkout[email]", email))
    if address:
        first, last = split_name(address.get("name") or "")
        for key, value in (("first_name", first), ("last_name", last), ("address1", address.get("line1")),
                           ("address2", address.get("line2")), ("city", address.get("city")),
                           ("province", address.get("region")), ("country", address.get("country")),
                           ("zip", address.get("postal_code"))):
            if value:
                params.append((f"checkout[shipping_address][{key}]", str(value)))
    query = f"?{urlencode(params)}" if params else ""
    return f"https://{host}/cart/{variant_id}:{quantity}{query}"


def quantity_of(params: dict) -> int:
    """A whole number from 1 to MAX_QUANTITY; 1 when not given."""
    raw = params.get("quantity")
    if raw is None:
        return 1
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw != int(raw):
        raise ActionError(BAD_QUANTITY, 422)
    if not 1 <= int(raw) <= MAX_QUANTITY:
        raise ActionError(BAD_QUANTITY, 422)
    return int(raw)


def money(value: float | None, currency: str | None) -> str:
    """With its currency's sign when known; a bare amount when not."""
    if value is None:
        return ""
    return format_money(value, currency) or "" if currency else f"{value:,.2f}"


async def _saved_address(user_id) -> dict | None:
    async with connection_or_direct() as conn:
        addresses = await shipping_addresses.list_addresses(conn, user_id)
    return shipping_addresses.snapshot(addresses[0]) if addresses else None


def _found_price(item: dict) -> tuple[float | None, str | None]:
    price = (decode_jsonb(item.get("fields"), {}) or {}).get("price") or {}
    value = price.get("value") if isinstance(price, dict) else None
    number = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return number, (price.get("currency") if isinstance(price, dict) else None)


async def prepare(ctx: ActionContext, params: dict, *, fetch=fetch_public) -> Proposal:
    url = store_page(ctx.item)
    if url is None:
        raise ActionError(available(ctx) or "There's no store page to buy from.")
    title = ctx.item.get("title") or "this"
    host = urlsplit(url).hostname or ""
    store = site_of(host)
    found, found_currency = _found_price(ctx.item)
    quantity = quantity_of(params)
    fill_in = params.get("fill_in", True) is not False

    shop = await shopify_store(url, fetch=fetch)
    variant = pick_variant(shop["product"], wanted_variant(url)) if shop else None
    if variant is None:
        lines = [Line("Item", title), Line("Store", store)]
        if found is not None:
            lines.append(Line("Price when found", money(found, found_currency)))
        return Proposal(
            frozen={"kind": "product_page", "url": url, "store": store, "title": title},
            title=f"Buy {title}",
            lines=tuple(lines),
            note=f"Opens the product at {store}: add it to your cart and check out there. "
                 "Espresso doesn't pay or place the order.",
            confirm=f"Open {store}",
        )
    if not variant.get("available"):
        raise ActionError(f"{title} is out of stock at {store} right now.")

    currency = shop["currency"]
    price = variant["price"] / 100 if isinstance(variant.get("price"), int) else None
    address = await _saved_address(ctx.user.id) if fill_in else None
    email = (getattr(ctx.user, "email", "") or "").strip() if fill_in else ""
    link = checkout_link(host, variant["id"], quantity, address=address, email=email)
    option = variant.get("title") if variant.get("title") not in (None, "", "Default Title") else None
    lines = [Line("Item", f"{title} ({option})" if option else title), Line("Store", store),
             Line("Quantity", str(quantity))]
    if price is not None:
        lines.append(Line("Price now", money(price, currency)))
    if address:
        lines.append(Line("Ship to", shipping_addresses.one_line(address)))
    if email:
        lines.append(Line("Email", email))
    note = f"Opens checkout at {store} with this in the cart"
    filled = [w for w, on in (("your address", bool(address)), ("email", bool(email))) if on]
    note += f", {' and '.join(filled)} filled in. " if filled else ". "
    note += "You review and pay there; Espresso doesn't pay or place the order."
    # Only the same money compares: a found price in another currency doesn't.
    if (price is not None and found is not None and currency and (found_currency or currency) == currency
            and abs(price - found) >= 0.01):
        note += f" It was {money(found, currency)} when found."
    return Proposal(
        frozen={"kind": "checkout", "url": link, "store": store, "title": title, "variant_id": variant["id"],
                "quantity": quantity, "price": price, "currency": currency,
                "plain_url": checkout_link(host, variant["id"], quantity, address=None, email="")},
        title=f"Buy {title}",
        lines=tuple(lines),
        note=note,
    )


async def perform(ctx: ActionContext, frozen: dict) -> dict:
    """Nothing to do on the server: the link is the hand-off. The link kept
    afterwards (`stored_url`) carries none of the person's details."""
    store = frozen.get("store") or "the store"
    if frozen.get("kind") == "checkout":
        out = outcome(f"Checkout opened at {store}", (Line("Item", frozen.get("title") or ""),
                                                       Line("Quantity", str(frozen.get("quantity") or 1))),
                      url=frozen.get("url"))
        return {**out, "stored_url": frozen.get("plain_url") or frozen.get("url")}
    return outcome(f"Opened the product at {store}", (Line("Item", frozen.get("title") or ""),), url=frozen.get("url"))


ACTION = ItemAction(
    key="buy",
    label="Buy",
    icon="cart",
    description="Opens the store's checkout with this in the cart (or its page, for stores that can't). "
                "You pay at the store; Espresso never pays or orders.",
    item_kinds=("product",),
    params=(QUANTITY, FILL_IN),
    confirm_label="Go to checkout",
    available=available,
    prepare=prepare,
    perform=perform,
    per_day=30,
)
