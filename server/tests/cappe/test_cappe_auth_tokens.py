"""Cappe token + helper unit tests — no DB, no app boot.

Verifies the cross-product scope isolation: a Cappe-scoped token decodes under
Cappe but NOT under matcha, and a matcha token is rejected by Cappe. Run from
server/ so `app` is importable.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# Minimal env so app.config.load_settings() succeeds (no DB connection happens).
os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.auth import (  # noqa: E402
    create_cappe_access_token,
    create_cappe_refresh_token,
    decode_cappe_token,
    is_cappe_token_revoked,
)
from app.cappe.routes._shared import loads, slugify  # noqa: E402
from app.core.services.auth import create_access_token, decode_token  # noqa: E402


def test_access_token_roundtrip():
    aid = uuid4()
    tok = create_cappe_access_token(aid, "user@example.com")
    payload = decode_cappe_token(tok, expected_type="access")
    assert payload is not None
    assert payload["sub"] == str(aid)
    assert payload["email"] == "user@example.com"
    assert payload["scope"] == "cappe"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    aid = uuid4()
    tok = create_cappe_refresh_token(aid, "user@example.com")
    payload = decode_cappe_token(tok, expected_type="refresh")
    assert payload is not None
    assert payload["type"] == "refresh"
    assert payload["scope"] == "cappe"


def test_refresh_token_not_accepted_as_access():
    tok = create_cappe_refresh_token(uuid4(), "user@example.com")
    assert decode_cappe_token(tok, expected_type="access") is None


def test_matcha_token_rejected_by_cappe():
    # A real matcha access token has no scope='cappe' claim → must be rejected.
    tok = create_access_token(uuid4(), "user@example.com", "client")
    assert decode_cappe_token(tok, expected_type="access") is None


def test_cappe_token_rejected_by_matcha():
    # Symmetric: a Cappe token lacks the 'role' claim matcha's decoder requires.
    tok = create_cappe_access_token(uuid4(), "user@example.com")
    assert decode_token(tok, expected_type="access") is None


def test_garbage_token_rejected():
    assert decode_cappe_token("not-a-real-jwt", expected_type="access") is None
    assert decode_cappe_token("", expected_type="access") is None


def test_expired_token_rejected():
    tok = create_cappe_access_token(uuid4(), "user@example.com", expires_delta=timedelta(seconds=-10))
    assert decode_cappe_token(tok, expected_type="access") is None


# --- helper unit tests ------------------------------------------------------

def test_slugify():
    assert slugify("My Cool Site!") == "my-cool-site"
    assert slugify("  Trim  Me  ") == "trim-me"
    assert slugify("") == "site"
    assert slugify("---") == "site"
    assert slugify("Café & Co") == "caf-co"


def test_token_revocation_watermark():
    now = datetime.now(timezone.utc)
    watermark = now
    # iat 60s before the watermark → revoked.
    assert is_cappe_token_revoked(int((now - timedelta(seconds=60)).timestamp()), watermark) is True
    # iat 60s after the watermark → still valid.
    assert is_cappe_token_revoked(int((now + timedelta(seconds=60)).timestamp()), watermark) is False
    # No watermark (never logged out) → never revoked.
    assert is_cappe_token_revoked(int(now.timestamp()), None) is False
    # No iat on the token → not revoked.
    assert is_cappe_token_revoked(None, watermark) is False
    # Garbage iat → safe (not revoked, no crash).
    assert is_cappe_token_revoked("nope", watermark) is False


def test_loads_normalizes_jsonb_reads():
    assert loads(None) == {}
    assert loads('{"a": 1}') == {"a": 1}
    assert loads({"b": 2}) == {"b": 2}
    assert loads("not json") == {}
    assert loads("[1,2,3]") == {}  # non-object JSON collapses to {}
