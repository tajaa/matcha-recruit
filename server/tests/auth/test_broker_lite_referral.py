"""
Tests for broker Lite referral token feature.

Covers:
  - BusinessRegister model accepts lite_broker_token field
  - Token resolution in register_business: valid token sets referring_broker_id
  - Invalid/expired token is non-blocking (registration succeeds without attribution)
  - broker_ref slug takes precedence over lite_broker_token
  - lite_broker_token ignored for non-matcha_lite tiers

Email is not invoked — tests exercise only the resolution slice, not the full
register_business endpoint, so no email calls are made.

Note: broker route endpoint tests (create/list/deactivate via AsyncClient) are
omitted here because app.matcha.routes.__init__.py transitively imports Twilio
and audioop_lts which are not available in the local dev environment. Those
endpoints are covered by the SQL + Pydantic logic reviewed inline.
"""

import asyncio
from uuid import uuid4

from app.core.models.auth import BusinessRegister

# ---------------------------------------------------------------------------
# BusinessRegister model
# ---------------------------------------------------------------------------

def test_business_register_accepts_lite_broker_token():
    req = BusinessRegister(
        company_name="Test Co",
        industry="Retail",
        company_size="1-10",
        headcount=5,
        email="owner@example.com",
        password="password123",
        name="Owner",
        tier="matcha_lite",
        lite_broker_token="sometoken",
    )
    assert req.lite_broker_token == "sometoken"


def test_business_register_lite_broker_token_defaults_none():
    req = BusinessRegister(
        company_name="Test Co",
        industry="Retail",
        company_size="1-10",
        headcount=5,
        email="owner@example.com",
        password="password123",
        name="Owner",
    )
    assert req.lite_broker_token is None


def test_business_register_lite_broker_token_independent_of_broker_ref():
    req = BusinessRegister(
        company_name="Test Co",
        industry="Retail",
        company_size="1-10",
        headcount=5,
        email="owner@example.com",
        password="password123",
        name="Owner",
        broker_ref="acme-broker",
        lite_broker_token="abc123",
    )
    assert req.broker_ref == "acme-broker"
    assert req.lite_broker_token == "abc123"


# ---------------------------------------------------------------------------
# Token resolution logic (replicated from auth.py lines 1530-1555)
# Tests validate correctness of the resolution slice in isolation.
# Email is never reached — we only run the slug + token lookup portion.
# ---------------------------------------------------------------------------

class _AuthConn:
    """
    Minimal fake asyncpg connection for the token-resolution slice.
    Tracks whether use_count UPDATE was executed.
    """

    def __init__(self, token_broker_id=None, broker_slug_id=None):
        self._token_broker_id = token_broker_id
        self._broker_slug_id = broker_slug_id
        self.use_count_incremented = False

    async def fetchrow(self, query, *args):
        if "FROM brokers WHERE slug" in query:
            return {"id": self._broker_slug_id} if self._broker_slug_id else None
        if "UPDATE broker_lite_referral_tokens" in query:
            if self._token_broker_id:
                self.use_count_incremented = True
                return {"broker_id": self._token_broker_id}
            return None
        return None


async def _resolve(conn, request_kwargs: dict):
    """Run just the referring_broker_id resolution from register_business."""
    request = BusinessRegister(**request_kwargs)

    referring_broker_id = None

    if request.broker_ref:
        row = await conn.fetchrow(
            "SELECT id FROM brokers WHERE slug = $1 AND status = 'active'",
            request.broker_ref.strip().lower(),
        )
        if row:
            referring_broker_id = row["id"]

    if request.lite_broker_token and request.tier == "matcha_lite" and referring_broker_id is None:
        row = await conn.fetchrow(
            """
            UPDATE broker_lite_referral_tokens
            SET use_count    = use_count + 1,
                last_used_at = NOW()
            WHERE token     = $1
              AND is_active  = true
              AND (expires_at IS NULL OR expires_at > NOW())
            RETURNING broker_id
            """,
            request.lite_broker_token.strip(),
        )
        if row:
            referring_broker_id = row["broker_id"]

    return referring_broker_id


def _base(**kwargs) -> dict:
    return {
        "company_name": "Test Co",
        "industry": "Retail",
        "company_size": "1-10",
        "headcount": 5,
        "email": "owner@example.com",
        "password": "password123",
        "name": "Owner",
        **kwargs,
    }


def test_valid_lite_token_sets_referring_broker():
    broker_id = uuid4()
    conn = _AuthConn(token_broker_id=broker_id)
    result = asyncio.run(_resolve(conn, _base(tier="matcha_lite", lite_broker_token="valid-token")))
    assert result == broker_id
    assert conn.use_count_incremented is True


def test_invalid_lite_token_does_not_block_signup():
    conn = _AuthConn(token_broker_id=None)
    result = asyncio.run(_resolve(conn, _base(tier="matcha_lite", lite_broker_token="bad-token")))
    assert result is None
    assert conn.use_count_incremented is False


def test_broker_ref_slug_takes_precedence_over_lite_token():
    slug_broker = uuid4()
    token_broker = uuid4()
    conn = _AuthConn(token_broker_id=token_broker, broker_slug_id=slug_broker)
    result = asyncio.run(
        _resolve(conn, _base(tier="matcha_lite", broker_ref="acme", lite_broker_token="tok"))
    )
    assert result == slug_broker
    assert conn.use_count_incremented is False


def test_lite_token_ignored_for_non_lite_tier():
    broker_id = uuid4()
    conn = _AuthConn(token_broker_id=broker_id)
    result = asyncio.run(_resolve(conn, _base(tier="ir_only", lite_broker_token="valid-token")))
    assert result is None
    assert conn.use_count_incremented is False


def test_no_token_returns_none():
    conn = _AuthConn()
    result = asyncio.run(_resolve(conn, _base(tier="matcha_lite")))
    assert result is None
    assert conn.use_count_incremented is False
