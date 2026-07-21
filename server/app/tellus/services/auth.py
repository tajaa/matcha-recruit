"""Tell-Us token helpers.

Tell-Us-scoped JWTs: the subject is a `tellus_accounts.id` and every token
carries `"scope": "tellus"`. `decode_tellus_token` enforces that scope, so
neither a matcha nor a cappe token can satisfy a Tell-Us endpoint (and
vice-versa) even though all are signed with the same `settings.jwt_secret_key`.

The implementation lives in `core.services.scoped_auth` and is shared with
Cappe — these were byte-identical twins apart from the scope string, and two
copies of a scope check is a security-drift hazard: a fix to one leaves the
other product exposed.

Password hashing/verification is reused verbatim from core — there is exactly
one bcrypt implementation in the codebase.
"""
from app.core.services.scoped_auth import is_token_revoked, make_token_helpers

# Re-export the single bcrypt implementation so Tell-Us imports from one place.
from ...core.services.auth import hash_password, verify_password_async  # noqa: F401

TELLUS_SCOPE = "tellus"

_helpers = make_token_helpers(TELLUS_SCOPE)

create_tellus_access_token = _helpers.create_access_token
create_tellus_refresh_token = _helpers.create_refresh_token
decode_tellus_token = _helpers.decode_token
is_tellus_token_revoked = is_token_revoked
