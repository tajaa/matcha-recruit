"""Buy: take the person to the store's checkout with the product in the cart.

Espresso never pays or places the order: the person reviews and pays at the
store. What it does is the walk there.

* A Shopify store (most brand stores): the product's own data
  (`/products/<handle>.js`) gives the variant, its price now and whether it
  is in stock; a cart permalink (`/cart/<variant>:<qty>`) opens checkout with
  it in the cart, and with the person's saved shipping address and email
  filled in when they have one (Settings → Shipping addresses). The preview
  shows exactly what is filled in before they go.
* Any other store: the product's page, to add it to the cart there.

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

from ..playbook import IntakeField
from ..research import providers
from .base import ActionContext, ActionError, ItemAction, Line, Proposal, outcome

logger = logging.getLogger(__name__)

PRODUCT_BYTES = 1_000_000
PRODUCT_SECONDS = 15.0
MAX_QUANTITY = 10
_HANDLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~%-]{0,200}$")

QUANTITY = IntakeField(key="quantity", label="Quantity", type="number", help=f"1 to {MAX_QUANTITY}")


def store_page(item: dict) -> str | None:
    """The finding's store page: an http(s) link that isn't one of Google's."""
    return providers.store_link(item.get("url"))


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


async def shopify_product(url: str, *, fetch=fetch_public) -> dict | None:
    """The store's own product data when it is a Shopify store, else None."""
    handle = product_handle(url)
    if handle is None:
        return None
    host = urlsplit(url).hostname
    try:
        fetched = await fetch(f"https://{host}/products/{handle}.js", max_bytes=PRODUCT_BYTES,
                              accept="application/json", total_timeout=PRODUCT_SECONDS)
    except (UnsafeURL, TimeoutError, OSError):
        return None
    except Exception:
        logger.info("buy: product data fetch failed", exc_info=True)
        return None
    if fetched.status != 200 or fetched.truncated:
        return None
    try:
        data = json.loads(fetched.body)
    except (ValueError, UnicodeDecodeError):
        return None
    variants = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(variants, list) or not any(isinstance(v, dict) and isinstance(v.get("id"), int) for v in variants):
        return None
    return data


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
    store = host.removeprefix("www.")
    found, currency = _found_price(ctx.item)
    quantity = int(params.get("quantity") or 1)
    if not 1 <= quantity <= MAX_QUANTITY:
        raise ActionError(f"Quantity must be 1 to {MAX_QUANTITY}.", 422)

    product = await shopify_product(url, fetch=fetch)
    variant = pick_variant(product, wanted_variant(url)) if product else None
    if variant is None:
        lines = [Line("Item", title), Line("Store", store)]
        if found is not None:
            lines.append(Line("Price when found", format_money(found, currency) or ""))
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

    price = variant["price"] / 100 if isinstance(variant.get("price"), int) else None
    address = await _saved_address(ctx.user.id)
    email = (getattr(ctx.user, "email", "") or "").strip()
    link = checkout_link(host, variant["id"], quantity, address=address, email=email)
    option = variant.get("title") if variant.get("title") not in (None, "", "Default Title") else None
    lines = [Line("Item", f"{title} ({option})" if option else title), Line("Store", store),
             Line("Quantity", str(quantity))]
    if price is not None:
        lines.append(Line("Price now", format_money(price, currency) or ""))
    if address:
        lines.append(Line("Ship to", shipping_addresses.one_line(address)))
    if email:
        lines.append(Line("Email", email))
    note = f"Opens checkout at {store} with this in the cart"
    note += ", your address and email filled in. " if address else (", your email filled in. " if email else ". ")
    note += "You review and pay there; Espresso doesn't pay or place the order."
    if price is not None and found is not None and abs(price - found) >= 0.01:
        note += f" It was {format_money(found, currency)} when found."
    return Proposal(
        frozen={"kind": "checkout", "url": link, "store": store, "title": title,
                "variant_id": variant["id"], "quantity": quantity, "price": price, "currency": currency},
        title=f"Buy {title}",
        lines=tuple(lines),
        note=note,
    )


async def perform(ctx: ActionContext, frozen: dict) -> dict:
    """Nothing to do on the server: the link is the hand-off."""
    store = frozen.get("store") or "the store"
    if frozen.get("kind") == "checkout":
        return outcome(f"Checkout opened at {store}", (Line("Item", frozen.get("title") or ""),
                                                        Line("Quantity", str(frozen.get("quantity") or 1))),
                       url=frozen.get("url"))
    return outcome(f"Opened the product at {store}", (Line("Item", frozen.get("title") or ""),), url=frozen.get("url"))


ACTION = ItemAction(
    key="buy",
    label="Buy",
    icon="cart",
    description="Opens the store's checkout with this in the cart (or its page, for stores that can't). "
                "You pay at the store; Espresso never pays or orders.",
    item_kinds=("product",),
    params=(QUANTITY,),
    confirm_label="Go to checkout",
    available=available,
    prepare=prepare,
    perform=perform,
    per_day=30,
)
