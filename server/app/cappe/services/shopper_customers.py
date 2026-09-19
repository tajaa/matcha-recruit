"""Connected-account customers; Stripe I/O never holds a pooled connection."""
from app.database import get_connection
from .stripe_connect import get_cappe_stripe


async def connected_customer(shopper, account_id):
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM cappe_shoppers WHERE id=$1 AND site_id=$2", shopper["id"], shopper["site_id"])
        address = await conn.fetchrow("SELECT * FROM cappe_shopper_addresses WHERE shopper_id=$1 AND site_id=$2 AND is_default",
                                      shopper["id"], shopper["site_id"])
    if not row:
        from fastapi import HTTPException
        raise HTTPException(401, "Shopper no longer exists")
    shipping = None
    if address:
        shipping = {"name": address["name"], "phone": address["phone"], "address": {
            "line1": address["line1"], "line2": address["line2"], "city": address["city"],
            "state": address["region"], "postal_code": address["postal_code"], "country": address["country"],
        }}
    customer = await get_cappe_stripe().ensure_connected_customer(
        account_id=account_id, email=row["email"], name=row["name"], shipping=shipping,
        customer_id=row["stripe_customer_id"], idempotency_key=f"shopper:{row['id']}:{account_id}",
    )
    async with get_connection() as conn:
        claimed = await conn.fetchval(
            "UPDATE cappe_shoppers SET stripe_customer_id=COALESCE(stripe_customer_id,$1) "
            "WHERE id=$2 AND site_id=$3 RETURNING stripe_customer_id", customer, shopper["id"], shopper["site_id"],
        )
    return claimed or customer
