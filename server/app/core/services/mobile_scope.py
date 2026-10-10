"""What a business admin's Matcha Schedule phone token may reach.

A client-role session minted for the phone (`cl=ios_schedule`) carries the
same role as the web session, and the client role reaches billing, the whole
roster, ER and IR. The phone is the device most likely to be lost, and the app
only needs the schedule, so its token is held to the routes below and refused
everywhere else.

Employee phone tokens are not touched: the employee role already bounds them.
WebSockets never accept a phone token at all (`decode_token` refuses one
without `allow_mobile_access`), so only HTTP is checked.
"""

from __future__ import annotations

import re
from typing import Optional

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import decode_token

_UUID = r"[0-9a-fA-F-]{36}"

# (allowed methods, path pattern). Anchored; paths include the /api prefix.
_ALLOWED: tuple[tuple[frozenset[str], re.Pattern[str]], ...] = tuple(
    (frozenset(methods), re.compile(pattern))
    for methods, pattern in (
        ({"GET"}, r"^/api/auth/me$"),
        ({"POST"}, r"^/api/push/(register|unregister)$"),
        ({"GET"}, r"^/api/locations$"),
        ({"GET", "POST", "PUT", "PATCH", "DELETE"}, r"^/api/employee-schedule/.+$"),
        ({"GET", "POST", "PUT", "PATCH", "DELETE"}, r"^/api/inbox(/.*)?$"),
        ({"GET", "POST", "PUT", "PATCH", "DELETE"}, r"^/api/matcha-work/notifications(/.*)?$"),
        # The schedule assistant's turns. The route itself refuses a phone
        # session on any thread that is not a schedule thread.
        ({"POST"}, rf"^/api/matcha-work/threads/{_UUID}/messages/stream$"),
        # Paid time off approvals for business admins.
        ({"GET"}, r"^/api/employees/pto/requests$"),
        ({"PATCH"}, rf"^/api/employees/pto/requests/{_UUID}$"),
    )
)

REFUSAL = "Matcha Schedule can't open this. Use Matcha on the web."


def manager_phone_path_allowed(method: str, path: str) -> bool:
    return any(method in methods and pattern.match(path) for methods, pattern in _ALLOWED)


def is_business_phone_token(authorization: Optional[str]) -> bool:
    """A valid access token from a Matcha Schedule session for a non-employee."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    payload = decode_token(authorization[7:].strip(), expected_type="access", allow_mobile_access=True)
    return bool(payload and payload.cl == "ios_schedule" and payload.role != "employee")


class ManagerPhoneScopeMiddleware:
    """Pure ASGI, so SSE responses stream through untouched."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] != "OPTIONS":
            authorization = None
            for name, value in scope.get("headers") or ():
                if name == b"authorization":
                    authorization = value.decode("latin-1")
                    break
            if is_business_phone_token(authorization) and not manager_phone_path_allowed(
                scope["method"], scope["path"],
            ):
                await JSONResponse({"detail": REFUSAL}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
