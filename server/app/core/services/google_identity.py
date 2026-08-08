"""Shared Google ID-token verification — used by matcha core and Tell-Us auth.

Single implementation so both `/api/auth/google` and `/api/tellus/auth/google`
share the same audience allowlist and fail-closed behavior, instead of each
route hand-rolling its own `verify_oauth2_token` call (which is how the core
endpoint ended up skipping audience validation entirely).
"""
import asyncio
from dataclasses import dataclass

from ...config import get_settings


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None


class GoogleTokenError(ValueError):
    pass


async def verify_google_id_token(raw_token: str) -> GoogleIdentity:
    """Verify a Google ID token and return the identity it asserts.

    Raises GoogleTokenError on anything untrustworthy — including an empty
    audience allowlist, so a deploy that forgets to configure a client ID
    rejects every token rather than accepting every token.
    """
    settings = get_settings()
    allowed_audiences = settings.google_allowed_audiences
    if not allowed_audiences:
        raise GoogleTokenError("Google sign-in is not configured")

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    try:
        idinfo = await asyncio.to_thread(
            google_id_token.verify_oauth2_token, raw_token, google_requests.Request()
        )
    except Exception as exc:
        raise GoogleTokenError("Invalid Google ID token") from exc

    if idinfo.get("aud") not in allowed_audiences:
        raise GoogleTokenError("Token was not issued for this app")
    if idinfo.get("email_verified") is not True:
        raise GoogleTokenError("Google email is not verified")

    email = idinfo.get("email")
    sub = idinfo.get("sub")
    if not email or not sub:
        raise GoogleTokenError("Token is missing required claims")

    return GoogleIdentity(sub=sub, email=email, name=idinfo.get("name"))
