#!/usr/bin/env python3
"""Mint the Stripe Products/Prices behind the Cappe billing catalog.

The migration seeds catalog ROWS but deliberately makes no Stripe API calls —
`migrate-prod.sh` rehearses the whole upgrade against live rows and rolls it
back, and a rehearsal that created real Stripe objects could not undo them, so
the real run would duplicate them. This script does that half, separately.

Nothing in the catalog is purchasable until this has run: every seeded price row
has `stripe_price_id IS NULL`, and `/billing/checkout` refuses (503) rather than
guessing.

Safe to re-run. It only touches rows whose Stripe id is still NULL, and every
Price carries a unique `lookup_key`, which is Stripe's own idempotency handle —
a duplicate errors rather than silently minting a second Price.

    cd server
    ./venv/bin/python scripts/seed_cappe_plans.py --dry-run
    ./venv/bin/python scripts/seed_cappe_plans.py

Point it at an environment with DATABASE_URL + STRIPE_SECRET_KEY in the env (or
server/.env). Verify which Stripe account those keys belong to before running
against prod — Cappe and Matcha share one platform account.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402


async def main(dry_run: bool) -> int:
    settings = load_settings()

    from app.cappe.services.stripe_connect import CappeStripeError, get_cappe_stripe  # noqa: E402
    from app.database import init_pool, close_pool, get_connection  # noqa: E402

    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    cs = get_cappe_stripe()
    created_products = created_prices = 0

    try:
        async with get_connection() as conn:
            products = await conn.fetch(
                "SELECT code, name, description, stripe_product_id "
                "FROM cappe_billing_products WHERE status <> 'archived' ORDER BY sort_order, code"
            )

            for p in products:
                product_id = p["stripe_product_id"]
                if not product_id:
                    print(f"  product {p['code']}: CREATE")
                    if not dry_run:
                        product_id = await cs.ensure_product(
                            code=p["code"], name=p["name"], description=p["description"]
                        )
                        await conn.execute(
                            "UPDATE cappe_billing_products SET stripe_product_id = $1, "
                            "updated_at = NOW() WHERE code = $2",
                            product_id, p["code"],
                        )
                    created_products += 1
                else:
                    print(f"  product {p['code']}: ok ({product_id})")

                prices = await conn.fetch(
                    "SELECT id, role, interval, unit_amount_cents, currency, lookup_key "
                    "FROM cappe_billing_prices "
                    "WHERE product_code = $1 AND stripe_price_id IS NULL AND is_current "
                    "ORDER BY role, interval",
                    p["code"],
                )
                for pr in prices:
                    label = f"{p['code']}/{pr['role']}/{pr['interval']} " \
                            f"{pr['unit_amount_cents']}c"
                    print(f"    price {label}: CREATE")
                    if dry_run or not product_id:
                        created_prices += 1
                        continue
                    try:
                        price_id = await cs.ensure_price(
                            product_id=product_id,
                            unit_amount_cents=pr["unit_amount_cents"],
                            currency=pr["currency"],
                            interval=pr["interval"],
                            lookup_key=pr["lookup_key"],
                        )
                    except CappeStripeError as exc:
                        # A duplicate lookup_key means Stripe already has this
                        # price — report it rather than creating an unkeyed twin.
                        print(f"    !! {label}: {exc}")
                        continue
                    await conn.execute(
                        "UPDATE cappe_billing_prices SET stripe_price_id = $1 WHERE id = $2",
                        price_id, pr["id"],
                    )
                    created_prices += 1
    finally:
        await close_pool()

    verb = "would create" if dry_run else "created"
    print(f"\n{verb}: {created_products} product(s), {created_prices} price(s)")
    if dry_run:
        print("dry run — nothing was written to Stripe or the database")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be created; touch nothing")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.dry_run)))
