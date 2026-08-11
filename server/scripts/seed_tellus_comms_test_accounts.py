"""Create the two local-only TellUs accounts used to exercise Comms.

Run from ``server/``:

    ./venv/bin/python scripts/seed_tellus_comms_test_accounts.py

The script refuses non-local database URLs. Both accounts are email-verified
and can sign in through Google; a random password hash exists only to satisfy
the credential invariant and is deliberately not a usable shared password.
"""
import asyncio
import os
import secrets
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402
from app.core.services.auth import hash_password  # noqa: E402
from app.database import close_pool, get_connection, init_pool  # noqa: E402

BRAND_EMAIL = "tessu2022+brand@gmail.com"
GUEST_EMAIL = "tessu2022+guest@gmail.com"
BRAND_NAME = "TellUs Comms Test Business"
BRAND_SLUG = "tellus-comms-test-business"


def _require_local_database(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError(f"Refusing to seed non-local database host: {host or '<missing>'}")


def _random_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


async def _ensure_brand_account(conn) -> tuple[str, str]:
    account = await conn.fetchrow(
        "SELECT id FROM tellus_accounts WHERE lower(email) = $1", BRAND_EMAIL
    )
    if account is None:
        account_id = await conn.fetchval(
            """INSERT INTO tellus_accounts
                   (email, password_hash, display_name, account_type, status, email_verified_at)
               VALUES ($1, $2, $3, 'brand', 'active', NOW()) RETURNING id""",
            BRAND_EMAIL, _random_password_hash(), "TellUs Test Brand",
        )
    else:
        account_id = account["id"]
        await conn.execute(
            """UPDATE tellus_accounts
                  SET account_type = 'brand', status = 'active',
                      email_verified_at = COALESCE(email_verified_at, NOW()), updated_at = NOW()
                WHERE id = $1""",
            account_id,
        )

    brand = await conn.fetchrow(
        "SELECT id, slug FROM tellus_brands WHERE owner_account_id = $1", account_id
    )
    if brand is None:
        slug = BRAND_SLUG
        slug_owner = await conn.fetchval(
            "SELECT owner_account_id FROM tellus_brands WHERE slug = $1", slug
        )
        if slug_owner is not None and slug_owner != account_id:
            slug = f"{BRAND_SLUG}-{secrets.token_hex(3)}"
        brand = await conn.fetchrow(
            """INSERT INTO tellus_brands
                   (owner_account_id, name, slug, location_count, plan_status, activated_at, messaging_enabled)
               VALUES ($1, $2, $3, 1, 'active', NOW(), TRUE)
               RETURNING id, slug""",
            account_id, BRAND_NAME, slug,
        )
    else:
        await conn.execute(
            """UPDATE tellus_brands
                  SET plan_status = 'active', activated_at = COALESCE(activated_at, NOW()),
                      messaging_enabled = TRUE, updated_at = NOW()
                WHERE id = $1""",
            brand["id"],
        )

    await conn.execute(
        """INSERT INTO tellus_brand_members (brand_id, account_id, role, can_manage_inbox)
           VALUES ($1, $2, 'owner', TRUE)
           ON CONFLICT (brand_id, account_id) DO UPDATE
               SET role = 'owner', can_manage_inbox = TRUE""",
        brand["id"], account_id,
    )

    store_id = await conn.fetchval(
        "SELECT id FROM tellus_stores WHERE brand_id = $1 ORDER BY created_at LIMIT 1", brand["id"]
    )
    if store_id is None:
        await conn.execute(
            """INSERT INTO tellus_stores (brand_id, name, city, state)
               VALUES ($1, 'Main location', 'San Francisco', 'CA')""",
            brand["id"],
        )
    return str(account_id), brand["slug"]


async def _ensure_guest_account(conn) -> str:
    account = await conn.fetchrow(
        "SELECT id, account_type FROM tellus_accounts WHERE lower(email) = $1", GUEST_EMAIL
    )
    if account is not None and account["account_type"] == "brand":
        raise RuntimeError(f"{GUEST_EMAIL} already owns a brand; refusing to change its role.")
    if account is None:
        account_id = await conn.fetchval(
            """INSERT INTO tellus_accounts
                   (email, password_hash, display_name, account_type, status, email_verified_at)
               VALUES ($1, $2, $3, 'consumer', 'active', NOW()) RETURNING id""",
            GUEST_EMAIL, _random_password_hash(), "TellUs Test Guest",
        )
    else:
        account_id = account["id"]
        await conn.execute(
            """UPDATE tellus_accounts
                  SET status = 'active', email_verified_at = COALESCE(email_verified_at, NOW()),
                      updated_at = NOW()
                WHERE id = $1""",
            account_id,
        )
    await conn.execute(
        "INSERT INTO tellus_points_balances (account_id) VALUES ($1) ON CONFLICT DO NOTHING",
        account_id,
    )
    return str(account_id)


async def main() -> None:
    settings = load_settings()
    _require_local_database(settings.database_url)
    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    try:
        async with get_connection() as conn:
            async with conn.transaction():
                brand_id, slug = await _ensure_brand_account(conn)
                guest_id = await _ensure_guest_account(conn)
        print(f"TellUs brand test account ready: {BRAND_EMAIL} ({brand_id}, /b/{slug})")
        print(f"TellUs guest test account ready: {GUEST_EMAIL} ({guest_id})")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
