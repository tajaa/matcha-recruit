"""Shared cart arithmetic for quotes, one-off orders and subscriptions."""
from collections import Counter

from fastapi import HTTPException

from .discounts import apply_discount_cents, best_discount_percent
from .options import validate_and_price_options


def unit_price(product, groups, selected_ids, discount_percent=0):
    delta, snapshot = validate_and_price_options(groups, selected_ids)
    return apply_discount_cents(max(0, product["price_cents"] + delta), discount_percent), snapshot


def cart_totals(lines, site, destination=None):
    """Subtotal, tax, shipping and total for priced lines.

    `destination` (services/shipping.Destination) is where the physical lines
    ship; None means the store's home country, the only place it shipped to
    before zones. Tax is the store's rate on physical goods, charged at home
    and in a zone only when that zone says so.
    """
    from .commerce import compute_shipping_cents
    from .promos import line_total
    from .shipping import home_destination

    # A promo code's share of a line comes off before tax and shipping.
    dest = destination or home_destination(site)
    subtotal = sum(line_total(line) for line in lines)
    physical = [line for line in lines if line["fulfillment"] == "physical"]
    taxable = sum(line_total(line) for line in physical)
    tax = taxable * int(site.get("tax_rate_bps") or 0) // 10000 if dest.charge_tax else 0
    shipping = compute_shipping_cents(
        has_physical=bool(physical), goods_subtotal_cents=taxable,
        flat_cents=dest.flat_cents, free_threshold_cents=dest.free_threshold_cents,
    )
    if subtotal + tax + shipping > 99_999_999:
        raise HTTPException(422, "Cart total exceeds the checkout limit")
    return {"subtotal_cents": subtotal, "tax_cents": tax, "shipping_cents": shipping,
            "total_cents": subtotal + tax + shipping}


def priceable_products(rows, option_groups, discounts, on_date):
    """Attach live option groups and the active promotion used by cart pricing.

    Quotes and checkout must feed ``price_cart`` the same product shape. Keeping
    that decoration here prevents a recurring quote from advertising a
    promotion that the eventual Stripe subscription silently drops.
    """
    return {
        row["id"]: {
            **dict(row),
            "option_groups": option_groups.get(row["id"], []),
            "discount_percent": best_discount_percent(
                discounts,
                kind="product",
                target_id=str(row["id"]),
                on_date=on_date,
            ),
        }
        for row in rows
    }


def price_cart(products_by_id, items, site, destination=None, promo=None, on_date=None):
    """Read-only quote; unavailable lines remain visible for cart repair.

    `promo` (a code row, or None) is applied to the available lines that carry
    no automatic discount; the result says whether it applied and why not."""
    quantities = Counter()
    option_quantities = Counter()
    for item in items:
        quantities[item.product_id] += item.quantity
        for option_id in set(item.selected_option_ids):
            option_quantities[option_id] += item.quantity
    lines = []
    currencies = set()
    for item in items:
        product = products_by_id.get(item.product_id)
        line = {"product_id": str(item.product_id), "quantity": item.quantity,
                "unit_price_cents": 0, "available": False, "fulfillment": "physical"}
        if product:
            groups = product.get("option_groups", [])
            try:
                unit, snapshot = unit_price(product, groups, item.selected_option_ids, product.get("discount_percent", 0))
                available = product["status"] == "active"
                if product["fulfillment"] == "physical":
                    stock = product.get("inventory")
                    available &= stock is None or stock >= quantities[item.product_id]
                    for group in groups:
                        for option in group.get("options", []):
                            stock = option.get("inventory")
                            if stock is not None and stock < option_quantities[option["id"]]:
                                available = False
                line.update(unit_price_cents=unit, selected_options=snapshot, available=available,
                            fulfillment=product["fulfillment"], title=product["name"])
                currencies.add(product["currency"])
            except ValueError as exc:
                line["reason"] = str(exc)
        lines.append(line)
    if len(currencies) > 1:
        raise HTTPException(422, "Mixed currencies not supported")
    currency = next(iter(currencies), "USD")
    extra = {}
    if promo is not None:
        extra["promo"] = apply_promo(lines, promo, products_by_id, items, on_date, currency)
    return {"lines": lines, **cart_totals(lines, site, destination), "currency": currency, **extra}


def promo_eligible(product, line) -> bool:
    """A line a code can discount: priced, available, not already on sale."""
    return bool(
        product and line.get("available", True) and line["unit_price_cents"] > 0
        and not int(product.get("discount_percent") or 0)
    )


def apply_promo(lines, promo, products_by_id, items, on_date, currency) -> dict:
    """Write each line's share of a code's discount onto it. Returns what the
    bag shows: {code, valid, discount_cents, message}."""
    from .promos import allocate, evaluate

    eligible = [promo_eligible(products_by_id.get(item.product_id), line) for item, line in zip(items, lines)]
    totals = [line["unit_price_cents"] * line["quantity"] for line in lines]
    discount, reason = evaluate(
        promo.get("row"), eligible_cents=sum(t for t, ok in zip(totals, eligible) if ok),
        on_date=on_date, currency=currency,
    ) if not promo.get("reason") else (0, promo["reason"])
    for line, share in zip(lines, allocate(discount, totals, eligible)):
        if share:
            line["promo_discount_cents"] = share
    return {"code": promo["code"], "valid": reason is None, "discount_cents": discount, "message": reason}
