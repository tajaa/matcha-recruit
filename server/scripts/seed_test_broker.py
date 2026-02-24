#!/usr/bin/env python3
"""Seed a test broker account for local/staging validation."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_pool, get_connection, close_pool
from app.core.services.auth import hash_password
from app.config import load_settings

EMAIL = "broker@test.com"
PASSWORD = "broker123!"
BROKER_NAME = "Test Brokerage Partners"
BROKER_SLUG = "test-broker"


async def seed():
    settings = load_settings()
    await init_pool(settings.database_url)

    async with get_connection() as conn:
        async with conn.transaction():
            # Upsert user
            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role, is_active)
                VALUES ($1, $2, 'broker', true)
                ON CONFLICT (email) DO UPDATE
                    SET password_hash = EXCLUDED.password_hash,
                        role = 'broker',
                        is_active = true
                RETURNING id
                """,
                EMAIL,
                hash_password(PASSWORD),
            )
            user_id = user["id"]

            # Upsert broker
            broker = await conn.fetchrow(
                """
                INSERT INTO brokers (name, slug, status, support_routing, billing_mode, invoice_owner, terms_required_version)
                VALUES ($1, $2, 'active', 'shared', 'direct', 'matcha', 'v1')
                ON CONFLICT (slug) DO UPDATE
                    SET name = EXCLUDED.name, status = 'active'
                RETURNING id
                """,
                BROKER_NAME,
                BROKER_SLUG,
            )
            broker_id = broker["id"]

            # Upsert broker_member
            await conn.execute(
                """
                INSERT INTO broker_members (broker_id, user_id, role, is_active)
                VALUES ($1, $2, 'admin', true)
                ON CONFLICT (broker_id, user_id) DO UPDATE
                    SET role = 'admin', is_active = true
                """,
                broker_id,
                user_id,
            )

    print("=== Test Broker Created ===")
    print(f"  Email:         {EMAIL}")
    print(f"  Password:      {PASSWORD}")
    print(f"  Broker name:   {BROKER_NAME}")
    print(f"  Broker slug:   {BROKER_SLUG}")
    print(f"  Referral link: <APP_URL>/register?via={BROKER_SLUG}")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(seed())
