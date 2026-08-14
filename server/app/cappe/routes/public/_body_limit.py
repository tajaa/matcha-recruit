"""Bound anonymous Cappe JSON bodies before FastAPI parses them."""
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

MAX_PUBLIC_JSON_BODY_BYTES = 8 * 1024


class CappePublicJsonBodyLimitRoute(APIRoute):
    """Reject declared and chunked bodies over the public JSON limit."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > MAX_PUBLIC_JSON_BODY_BYTES:
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
                    if received_bytes > MAX_PUBLIC_JSON_BODY_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="Request is too large",
                        )
                return message

            return await original_route_handler(Request(request.scope, limited_receive))

        return custom_route_handler


def limited_public_router() -> APIRouter:
    """Create a router for public JSON writes with the shared body limit."""
    return APIRouter(route_class=CappePublicJsonBodyLimitRoute)


__all__ = ["MAX_PUBLIC_JSON_BODY_BYTES", "CappePublicJsonBodyLimitRoute", "limited_public_router"]
