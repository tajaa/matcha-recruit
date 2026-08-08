"""Pure-function + source-guard tests for Google sign-in (no DB, no network).

verify_google_id_token is the shared gate for both matcha core's
/api/auth/google and Tell-Us's /api/tellus/auth/google — these tests are the
regression pin for the audience-validation hole the core endpoint originally
shipped with (no `audience=` passed to verify_oauth2_token).

TestGoogleAuthRouteSourceGuards uses inspect.getsource — repo pattern (see
test_likes.py), never spec_from_file_location.
"""
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.services.google_identity import GoogleTokenError, verify_google_id_token
from app.tellus.routes import auth as auth_routes

_VALID_CLAIMS = {
    "aud": "ios-client-id",
    "sub": "112233445566",
    "email": "person@example.com",
    "email_verified": True,
    "name": "Person One",
}


def _settings(ios="ios-client-id", web=None):
    return SimpleNamespace(google_allowed_audiences=[c for c in (ios, web) if c])


class TestVerifyGoogleIdToken:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        with patch(
            "app.core.services.google_identity.get_settings", return_value=_settings()
        ), patch(
            "google.oauth2.id_token.verify_oauth2_token", return_value=dict(_VALID_CLAIMS)
        ):
            identity = await verify_google_id_token("raw-token")
        assert identity.sub == "112233445566"
        assert identity.email == "person@example.com"
        assert identity.name == "Person One"

    @pytest.mark.asyncio
    async def test_wrong_audience_rejected(self):
        """The regression test for the original core bug: a token minted for
        a DIFFERENT Google OAuth client must not be accepted."""
        claims = {**_VALID_CLAIMS, "aud": "some-other-app-client-id"}
        with patch(
            "app.core.services.google_identity.get_settings", return_value=_settings()
        ), patch("google.oauth2.id_token.verify_oauth2_token", return_value=claims):
            with pytest.raises(GoogleTokenError):
                await verify_google_id_token("raw-token")

    @pytest.mark.asyncio
    async def test_empty_allowlist_fails_closed(self):
        """An unconfigured deploy (no GOOGLE_IOS_CLIENT_ID/GOOGLE_WEB_CLIENT_ID)
        must reject every token, not accept every token."""
        with patch(
            "app.core.services.google_identity.get_settings", return_value=_settings(ios=None)
        ):
            with pytest.raises(GoogleTokenError):
                await verify_google_id_token("raw-token")

    @pytest.mark.asyncio
    async def test_unverified_email_rejected(self):
        claims = {**_VALID_CLAIMS, "email_verified": False}
        with patch(
            "app.core.services.google_identity.get_settings", return_value=_settings()
        ), patch("google.oauth2.id_token.verify_oauth2_token", return_value=claims):
            with pytest.raises(GoogleTokenError):
                await verify_google_id_token("raw-token")

    @pytest.mark.asyncio
    async def test_invalid_token_wrapped(self):
        with patch(
            "app.core.services.google_identity.get_settings", return_value=_settings()
        ), patch(
            "google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("bad token")
        ):
            with pytest.raises(GoogleTokenError):
                await verify_google_id_token("raw-token")


class TestGoogleAuthRouteSourceGuards:
    """DB-touching paths are integration-level — run manually per
    server/app/tellus/CLAUDE.md. These pin the two SQL-shape invariants a
    live test can't cheaply cover without a real double-tap race / a real
    unverified account."""

    def test_new_account_insert_is_a_savepoint(self):
        """A concurrent double-tap's INSERT can raise UniqueViolationError —
        it must be caught OUTSIDE the transaction() block it's nested in, or
        the recovery SELECT below runs on an aborted transaction and 500s
        (the exact bug signup()'s brand-slug branch documents avoiding)."""
        src = inspect.getsource(auth_routes.google_auth)
        # One for the outer per-request transaction, one SAVEPOINT around
        # just the new-account INSERT.
        assert src.count("async with conn.transaction():") == 2

    def test_link_nulls_password_only_when_never_verified(self):
        """Linking Google onto an account matched by email must not silently
        keep a password nobody proved belongs to that address — see the
        pre-hijack note in tellus/CLAUDE.md's Google sign-in section."""
        src = inspect.getsource(auth_routes.google_auth)
        assert "password_hash = CASE WHEN email_verified_at IS NULL" in src
        assert "THEN NULL ELSE password_hash END" in src
        assert "tokens_valid_after = CASE WHEN email_verified_at IS NULL" in src
