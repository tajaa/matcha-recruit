"""Manual friends DB checks.

Disabled unless explicitly opted in. These checks must never mutate a live
database from CI; use reserved-domain accounts against local Postgres only.
"""
import os
from urllib.parse import urlparse

import pytest

asyncpg = pytest.importorskip("asyncpg")

from app.tellus.services.friends_service import (  # noqa: E402
    block_account,
    create_friendship,
    pair_key,
    remove_friendship,
)


pytestmark = pytest.mark.skipif(
    os.getenv("TELLUS_FRIENDS_DB_TEST") != "1",
    reason="manual DB test; set TELLUS_FRIENDS_DB_TEST=1 explicitly",
)


def test_manual_suite_requires_reserved_test_accounts():
    account_a = os.getenv("TELLUS_FRIENDS_ACCOUNT_A", "")
    account_b = os.getenv("TELLUS_FRIENDS_ACCOUNT_B", "")
    assert account_a.endswith(("@example.com", ".test"))
    assert account_b.endswith(("@example.com", ".test"))


class _Rollback:
    pass


@pytest.mark.asyncio
async def test_manual_friendship_symmetry_block_cascade_and_ledger_idempotency():
    """Run the social-graph smoke flow inside a transaction that is rolled back."""
    database_url = os.getenv("TELLUS_FRIENDS_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    parsed = urlparse(database_url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("Manual friends DB tests only permit localhost Postgres")

    conn = await asyncpg.connect(database_url)
    try:
        account_a = await conn.fetchval(
            "SELECT id FROM tellus_accounts WHERE email = $1", os.environ["TELLUS_FRIENDS_ACCOUNT_A"]
        )
        account_b = await conn.fetchval(
            "SELECT id FROM tellus_accounts WHERE email = $1", os.environ["TELLUS_FRIENDS_ACCOUNT_B"]
        )
        assert account_a and account_b and account_a != account_b
        pair = pair_key(account_a, account_b)
        baseline_ledger = await conn.fetchval(
            """SELECT COUNT(*) FROM tellus_points_ledger
                WHERE reason = 'earn_engagement' AND reference_id = $1
                  AND account_id = ANY($2::uuid[])""",
            pair, [account_a, account_b],
        )
        existing_state = await conn.fetchval(
            """SELECT COUNT(*) FROM tellus_friendships
                WHERE (account_id = $1 AND friend_account_id = $2)
                   OR (account_id = $2 AND friend_account_id = $1)""",
            account_a, account_b,
        )
        assert existing_state == 0, "reserved test accounts must start without friendship rows"

        try:
            async with conn.transaction():
                await create_friendship(conn, account_a, account_b, "request")
                assert await conn.fetchval(
                    """SELECT COUNT(*) FROM tellus_friendships
                        WHERE (account_id = $1 AND friend_account_id = $2)
                           OR (account_id = $2 AND friend_account_id = $1)""",
                    account_a, account_b,
                ) == 2

                after_first = await conn.fetchval(
                    """SELECT COUNT(*) FROM tellus_points_ledger
                        WHERE reason = 'earn_engagement' AND reference_id = $1
                          AND account_id = ANY($2::uuid[])""",
                    pair, [account_a, account_b],
                )
                assert after_first <= baseline_ledger + 2
                await remove_friendship(conn, account_a, account_b)
                await create_friendship(conn, account_a, account_b, "request")
                after_readd = await conn.fetchval(
                    """SELECT COUNT(*) FROM tellus_points_ledger
                        WHERE reason = 'earn_engagement' AND reference_id = $1
                          AND account_id = ANY($2::uuid[])""",
                    pair, [account_a, account_b],
                )
                assert after_readd == after_first

                await conn.execute(
                    """INSERT INTO tellus_friend_requests
                        (requester_account_id, addressee_account_id, source)
                        VALUES ($1, $2, 'search')""",
                    account_a, account_b,
                )
                await block_account(conn, account_a, account_b)
                assert await conn.fetchval(
                    """SELECT COUNT(*) FROM tellus_friendships
                        WHERE account_id = $1 AND friend_account_id = $2""",
                    account_a, account_b,
                ) == 0
                assert await conn.fetchval(
                    """SELECT COUNT(*) FROM tellus_friend_requests
                        WHERE status = 'pending'
                          AND ((requester_account_id = $1 AND addressee_account_id = $2)
                            OR (requester_account_id = $2 AND addressee_account_id = $1))""",
                    account_a, account_b,
                ) == 0
                raise _Rollback
        except _Rollback:
            pass
    finally:
        await conn.close()
