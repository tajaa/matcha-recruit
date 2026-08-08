"""Pure-function tests for Google ID-token verification (no DB, no network).

verify_google_id_token is the shared gate for both matcha core's
/api/auth/google and Tell-Us's /api/tellus/auth/google — these tests are the
regression pin for the audience-validation hole the core endpoint originally
shipped with (no `audience=` passed to verify_oauth2_token).
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.services.google_identity import GoogleTokenError, verify_google_id_token

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
