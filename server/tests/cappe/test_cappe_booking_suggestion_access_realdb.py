"""Opt-in localhost integration tests for Cappe booking access.

Run manually only after cappeaiaccess01 is applied:

    RUN_CAPPE_ACCESS_REALDB_TESTS=1 \
    CAPPE_ACCESS_TEST_DATABASE_URL=postgresql://... \
    ./venv/bin/python -m pytest tests/cappe/test_cappe_booking_suggestion_access_realdb.py -q

The test uses reserved domains and cleans its rows. It never creates schema.
"""
import asyncio
import os
from datetime import datetime, timezone

import asyncpg
import pytest

from app.cappe.services.booking_suggestion_access import (
    issue_suggestion_link,
    redeem_suggestion_link,
)


RUN = os.getenv("RUN_CAPPE_ACCESS_REALDB_TESTS") == "1"
DATABASE_URL = os.getenv("CAPPE_ACCESS_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not RUN or not DATABASE_URL,
    reason="set RUN_CAPPE_ACCESS_REALDB_TESTS=1 and CAPPE_ACCESS_TEST_DATABASE_URL",
)


def _assert_local_database(url: str) -> None:
    host = url.split("@", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Cappe access integration tests are localhost-only")


@pytest.mark.asyncio
async def test_realdb_issue_and_redeem_are_single_current_capabilities():
    _assert_local_database(DATABASE_URL)
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    email = "integration-client@cappe.test"
    site_id = None
    try:
        async with pool.acquire() as conn:
            site_id = await conn.fetchval(
                "SELECT id FROM cappe_sites WHERE slug = 'lumiere-spa' AND status = 'published'"
            )
            if site_id is None:
                pytest.skip("seed Lumiere before running the integration test")
            await conn.execute(
                "INSERT INTO cappe_clients (site_id, email, name, source) "
                "VALUES ($1, $2, 'Integration Client', 'manual') "
                "ON CONFLICT (site_id, email) DO UPDATE SET name = EXCLUDED.name",
                site_id,
                email,
            )

        now = datetime.now(timezone.utc)

        async def issue():
            async with pool.acquire() as conn:
                async with conn.transaction():
                    return await issue_suggestion_link(
                        conn, site_id=site_id, email=email, now=now
                    )

        issued = await asyncio.gather(issue(), issue())
        assert all(item is not None for item in issued)
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM cappe_booking_suggestion_links "
                "WHERE site_id = $1 AND client_email = $2",
                site_id,
                email,
            ) == 1

        # The newest issued token is the only redeemable one.
        token = issued[-1][0]

        async def redeem():
            async with pool.acquire() as conn:
                async with conn.transaction():
                    return await redeem_suggestion_link(
                        conn, site_id=site_id, token=token, now=now
                    )

        redeemed = await asyncio.gather(redeem(), redeem())
        assert sum(result is not None for result in redeemed) == 1
    finally:
        async with pool.acquire() as conn:
            if site_id is not None:
                await conn.execute(
                    "DELETE FROM cappe_booking_suggestion_sessions WHERE site_id = $1 AND client_email = $2",
                    site_id,
                    email,
                )
                await conn.execute(
                    "DELETE FROM cappe_booking_suggestion_links WHERE site_id = $1 AND client_email = $2",
                    site_id,
                    email,
                )
                await conn.execute(
                    "DELETE FROM cappe_clients WHERE site_id = $1 AND email = $2",
                    site_id,
                    email,
                )
        await pool.close()
