"""Bound anonymous Cappe JSON bodies before FastAPI parses them."""
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

MAX_PUBLIC_JSON_BODY_BYTES = 8 * 1024

# A cart or a form submission is legitimately bigger than a booking request:
# up to 100 line items with per-line intake answers, or a form with long
# free-text fields. Still bounded, just further out.
MAX_PUBLIC_CART_BODY_BYTES = 32 * 1024


class CappePublicJsonBodyLimitRoute(APIRoute):
    """Reject declared and chunked bodies over the public JSON limit.

    `max_body_bytes` is a class attribute so `limited_public_router` can mint a
    subclass per cap; every instance shares the one implementation.
    """

    max_body_bytes: int = MAX_PUBLIC_JSON_BODY_BYTES

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()
        limit = type(self).max_body_bytes

        async def custom_route_handler(request: Request):
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > limit:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": "Request is too large"},
                )

            received_bytes = 0

            async def limited_receive():
                nonlocal received_bytes
                message = await request.receive()
                if message["type"] == "http.request":
                    received_bytes += len(message.get("body") or b"")
                    if received_bytes > limit:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="Request is too large",
                        )
                return message

            return await original_route_handler(Request(request.scope, limited_receive))

        return custom_route_handler


def limited_public_router(max_bytes: int = MAX_PUBLIC_JSON_BODY_BYTES) -> APIRouter:
    """Create a router for public JSON writes with a pre-parse body limit.

    Every anonymous write router uses one: without it, FastAPI parses whatever
    an unauthenticated caller sends before any validator sees it. GET routes on
    the same router are unaffected — they carry no body.
    """
    route_class = CappePublicJsonBodyLimitRoute
    if max_bytes != MAX_PUBLIC_JSON_BODY_BYTES:
        route_class = type(
            f"CappePublicJsonBodyLimitRoute{max_bytes}",
            (CappePublicJsonBodyLimitRoute,),
            {"max_body_bytes": max_bytes},
        )
    return APIRouter(route_class=route_class)


__all__ = [
    "MAX_PUBLIC_JSON_BODY_BYTES",
    "MAX_PUBLIC_CART_BODY_BYTES",
    "CappePublicJsonBodyLimitRoute",
    "limited_public_router",
]
