"""Shared cart arithmetic for quotes, one-off orders and subscriptions."""
from collections import Counter

from fastapi import HTTPException

from .discounts import apply_discount_cents
from .options import validate_and_price_options


def unit_price(product, groups, selected_ids, discount_percent=0):
    delta, snapshot = validate_and_price_options(groups, selected_ids)
    return apply_discount_cents(max(0, product["price_cents"] + delta), discount_percent), snapshot


def cart_totals(lines, site):
    from .commerce import compute_shipping_cents

    subtotal = sum(line["unit_price_cents"] * line["quantity"] for line in lines)
    physical = [line for line in lines if line["fulfillment"] == "physical"]
    taxable = sum(line["unit_price_cents"] * line["quantity"] for line in physical)
    tax = taxable * int(site.get("tax_rate_bps") or 0) // 10000
    shipping = compute_shipping_cents(
        has_physical=bool(physical), goods_subtotal_cents=taxable,
        flat_cents=int(site.get("shipping_flat_cents") or 0),
        free_threshold_cents=site.get("shipping_free_threshold_cents"),
    )
    if subtotal + tax + shipping > 99_999_999:
        raise HTTPException(422, "Cart total exceeds the checkout limit")
    return {"subtotal_cents": subtotal, "tax_cents": tax, "shipping_cents": shipping,
            "total_cents": subtotal + tax + shipping}


def price_cart(products_by_id, items, site):
    """Read-only quote; unavailable lines remain visible for cart repair."""
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
    return {"lines": lines, **cart_totals(lines, site), "currency": next(iter(currencies), "USD")}
