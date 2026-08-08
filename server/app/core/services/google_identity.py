"""Shared Google ID-token verification — used by matcha core and Tell-Us auth.

Single implementation so both `/api/auth/google` and `/api/tellus/auth/google`
share the same audience allowlist and fail-closed behavior, instead of each
route hand-rolling its own `verify_oauth2_token` call (which is how the core
endpoint ended up skipping audience validation entirely).
"""
import asyncio
import threading
from dataclasses import dataclass

from ...config import get_settings


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None


class GoogleTokenError(ValueError):
    pass


# asyncio.to_thread runs on a small pooled executor, not one thread per call —
# a thread-local reusable google.auth.transport.requests.Request (wraps a
# requests.Session) keeps its connection to googleapis.com warm across
# verifications that land on the same pool thread, instead of paying a fresh
# TLS handshake on every single sign-in. requests.Session isn't documented
# thread-safe, hence thread-local rather than one shared instance — see
# _verify_on_worker_thread for why the lookup must happen on the worker
# thread itself.
_local = threading.local()


def _verify_on_worker_thread(raw_token: str):
    # Runs inside the to_thread executor — the thread-local lookup must
    # happen HERE, on the actual pool thread, not on the event-loop thread
    # that schedules it. Looking it up before scheduling would hand the same
    # Session to whichever pool thread runs next, defeating the point (and
    # risking concurrent use of one Session from multiple pool threads).
    from google.oauth2 import id_token as google_id_token

    req = getattr(_local, "request", None)
    if req is None:
        from google.auth.transport import requests as google_requests
        req = _local.request = google_requests.Request()
    return google_id_token.verify_oauth2_token(raw_token, req)


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

    try:
        idinfo = await asyncio.to_thread(_verify_on_worker_thread, raw_token)
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
