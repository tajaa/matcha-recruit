"""Cross-scope token isolation for the side products.

Cappe, Tell-Us and matcha all sign with the same `jwt_secret_key`, so the ONLY
thing stopping a token minted for one product from authenticating against
another is the `scope` claim check in the decode path. That check used to be
duplicated per product; these tests pin the behaviour now that there is one
implementation behind `make_token_helpers`.
"""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.cappe.services.auth import (
    create_cappe_access_token,
    create_cappe_refresh_token,
    decode_cappe_token,
)
from app.core.services.scoped_auth import is_token_revoked, make_token_helpers
from app.tellus.services.auth import (
    create_tellus_access_token,
    create_tellus_refresh_token,
    decode_tellus_token,
)

ACCOUNT = uuid4()
EMAIL = "someone@example.com"


@pytest.fixture(autouse=True, scope="module")
def _settings():
    """These helpers read jwt_secret_key/algorithm from settings, which are
    normally initialized by the app lifespan. Load them once for the module —
    this reads the local .env, so it needs no network or database."""
    from app.config import load_settings

    load_settings()



class TestScopeIsolation:
    def test_cappe_token_decodes_for_cappe(self):
        payload = decode_cappe_token(create_cappe_access_token(ACCOUNT, EMAIL))
        assert payload is not None
        assert payload["sub"] == str(ACCOUNT)
        assert payload["scope"] == "cappe"

    def test_tellus_token_decodes_for_tellus(self):
        payload = decode_tellus_token(create_tellus_access_token(ACCOUNT, EMAIL))
        assert payload is not None
        assert payload["scope"] == "tellus"

    def test_cappe_token_is_rejected_by_tellus(self):
        # Same signing key — the scope claim is the whole boundary.
        assert decode_tellus_token(create_cappe_access_token(ACCOUNT, EMAIL)) is None

    def test_tellus_token_is_rejected_by_cappe(self):
        assert decode_cappe_token(create_tellus_access_token(ACCOUNT, EMAIL)) is None

    def test_unscoped_token_is_rejected_by_both(self):
        # A matcha token carries no `scope` claim at all.
        unscoped = make_token_helpers("").create_access_token(ACCOUNT, EMAIL)
        assert decode_cappe_token(unscoped) is None
        assert decode_tellus_token(unscoped) is None


class TestTokenType:
    def test_refresh_token_rejected_where_access_expected(self):
        refresh = create_cappe_refresh_token(ACCOUNT, EMAIL)
        assert decode_cappe_token(refresh, expected_type="access") is None
        assert decode_cappe_token(refresh, expected_type="refresh") is not None

    def test_access_token_rejected_where_refresh_expected(self):
        access = create_tellus_access_token(ACCOUNT, EMAIL)
        assert decode_tellus_token(access, expected_type="refresh") is None

    def test_type_unchecked_when_not_specified(self):
        assert decode_cappe_token(create_cappe_refresh_token(ACCOUNT, EMAIL)) is not None


class TestMalformed:
    @pytest.mark.parametrize("bad", ["", "not.a.token", "a.b.c", None])
    def test_garbage_returns_none_rather_than_raising(self, bad):
        assert decode_cappe_token(bad) is None
        assert decode_tellus_token(bad) is None

    def test_expired_token_is_rejected(self):
        expired = create_cappe_access_token(
            ACCOUNT, EMAIL, expires_delta=timedelta(seconds=-10)
        )
        assert decode_cappe_token(expired) is None


class TestRevocation:
    def test_never_revoked_when_watermark_is_null(self):
        assert is_token_revoked(1_700_000_000, None) is False

    def test_never_revoked_when_iat_missing(self):
        # Tokens minted before the feature shipped carry no iat.
        from datetime import datetime, timezone

        assert is_token_revoked(None, datetime.now(timezone.utc)) is False

    def test_token_older_than_watermark_is_revoked(self):
        from datetime import datetime, timezone

        watermark = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_token_revoked(watermark.timestamp() - 60, watermark) is True

    def test_token_newer_than_watermark_survives(self):
        from datetime import datetime, timezone

        watermark = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_token_revoked(watermark.timestamp() + 60, watermark) is False

    def test_unparseable_iat_is_not_treated_as_revoked(self):
        from datetime import datetime, timezone

        assert is_token_revoked("garbage", datetime.now(timezone.utc)) is False
