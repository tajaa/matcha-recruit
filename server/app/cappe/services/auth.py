"""Cappe token helpers.

Cappe-scoped JWTs: the subject is a `cappe_accounts.id` and every token carries
`"scope": "cappe"`. `decode_cappe_token` enforces that scope, so a matcha access
token can never satisfy a Cappe endpoint (and vice-versa) even though both are
signed with the same `settings.jwt_secret_key`.

The implementation lives in `core.services.scoped_auth` and is shared with
Tell-Us — these were byte-identical twins apart from the scope string, and two
copies of a scope check is a security-drift hazard: a fix to one leaves the
other product exposed.

Password hashing/verification is reused verbatim from core — there is exactly
one bcrypt implementation in the codebase.
"""
from app.core.services.scoped_auth import is_token_revoked, make_token_helpers

# Re-export the single bcrypt implementation so Cappe code imports from one place.
from ...core.services.auth import hash_password, verify_password_async  # noqa: F401

CAPPE_SCOPE = "cappe"

_helpers = make_token_helpers(CAPPE_SCOPE)

create_cappe_access_token = _helpers.create_access_token
create_cappe_refresh_token = _helpers.create_refresh_token
decode_cappe_token = _helpers.decode_token
is_cappe_token_revoked = is_token_revoked
