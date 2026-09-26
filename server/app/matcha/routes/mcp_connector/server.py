"""The Matcha remote MCP server and the OAuth routes in front of it.

Wire layout (all on the one public origin, `mcp_oauth.public_origin()`):

    POST /api/mcp                                      MCP, Streamable HTTP, stateless JSON
    GET  /.well-known/oauth-protected-resource/api/mcp RFC 9728 (+ root alias)
    GET  /.well-known/oauth-authorization-server       RFC 8414 (+ path-inserted alias)
    GET  /api/oauth/authorize                          → SPA consent page
    POST /api/oauth/token | /register | /revoke        SDK handlers over MatchaOAuthProvider

Stateless JSON mode on purpose: every tool here is a quick request/response,
and it keeps each call inside nginx's 90 s / CloudFront's 60 s read timeouts
with no long-lived stream to keep alive.

Tools are thin: they resolve the caller from the verified token and hand off
to `research.py`, which owns every access decision.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Optional
from uuid import UUID

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware, get_access_token
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, Field
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route, Router

from app.core.services import mcp_oauth
from app.database import get_connection

from . import research

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Matcha is the person's workspace. These tools let you work the research cards on "
    "their Espresso kanban boards: list_research_cards to find one, get_research_card to "
    "read it, claim_research_card before you start, and attach_research_report to hand "
    "back the finished report. Do the research yourself with your own web search; the "
    "report must follow the report_contract returned by get_research_card."
)

mcp_server = MCPServer(
    name="matcha",
    title="Matcha",
    instructions=_INSTRUCTIONS,
    website_url="https://hey-matcha.com",
    version="1.0.0",
)

_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
# Visible to teammates on the board (moves the card, posts a note), so it is
# flagged the way a client should treat a change other people will see.
_PUBLISH = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)


# ── caller resolution ────────────────────────────────────────────────────────


async def _client_name(client_id: str) -> str:
    async with get_connection() as conn:
        name = await conn.fetchval("SELECT client_name FROM oauth_clients WHERE client_id = $1", client_id)
    return (name or "an AI assistant").strip()[:80]


async def _caller(*, write: bool = False):
    """(CurrentUser, client name) for the verified token on this request."""
    from app.core.dependencies import load_current_user
    from app.core.services.redis_cache import check_rate_limit
    from app.matcha.dependencies import require_feature
    from fastapi import HTTPException

    token = get_access_token()
    if token is None or not token.subject:
        raise ToolError("Not signed in to Matcha. Reconnect the Matcha connector.")
    if write and mcp_oauth.SCOPE_WRITE not in token.scopes:
        raise ToolError(
            "This connection was granted read-only access. Reconnect Matcha and allow "
            "'update your research cards' to publish reports."
        )
    try:
        await check_rate_limit(token.subject, "mcp_tool", 120, 60)
        user = await load_current_user(UUID(token.subject), check_session_revocation=False)
        # Same gate as the /matcha-work routers: the kanban lives behind it.
        await require_feature("matcha_work")(user)
    except HTTPException as exc:
        if exc.status_code == 429:
            raise ToolError("Too many Matcha tool calls in the last minute; wait a moment and retry.")
        raise ToolError(
            "Your Matcha account cannot use boards right now"
            + (f": {exc.detail}" if isinstance(exc.detail, str) else ".")
        )
    return user, await _client_name(token.client_id)


async def _run(label: str, fn, *, write: bool = False, **kwargs) -> dict[str, Any]:
    user, client_name = await _caller(write=write)
    if write:
        kwargs["client_name"] = client_name
    logger.info("[mcp] tool=%s user=%s client=%s", label, user.id, client_name)
    try:
        return await fn(user, **kwargs)
    except research.ConnectorError as exc:
        raise ToolError(str(exc))


# ── tools ────────────────────────────────────────────────────────────────────


@mcp_server.tool(
    name="list_research_cards",
    title="List research cards",
    description=(
        "List research cards on the person's Espresso kanban boards that are waiting for "
        "research (To do, Changes requested) or already in progress. Returns task_id, board, "
        "title and column for each, newest first."
    ),
    annotations=_READ,
)
async def list_research_cards_tool(
    project_id: Annotated[
        Optional[str], Field(description="Only this board (project UUID). Omit for all boards.")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum cards to return.")] = 20,
) -> dict[str, Any]:
    return await _run("list_research_cards", research.list_research_cards, project_id=project_id, limit=limit)


@mcp_server.tool(
    name="get_research_card",
    title="Read a research card",
    description=(
        "Read one research card: its question (title + description), reviewer feedback from a "
        "previous round, text attachments, the previous report if this is a revision, and the "
        "report_contract the finished report must follow."
    ),
    annotations=_READ,
)
async def get_research_card_tool(
    task_id: Annotated[str, Field(description="The research card's task UUID.")],
) -> dict[str, Any]:
    return await _run("get_research_card", research.get_research_card, task_id=task_id)


@mcp_server.tool(
    name="claim_research_card",
    title="Start a research card",
    description=(
        "Mark the card In Progress before researching it, so teammates and the Matcha "
        "AutoPR bot know it is being worked. Safe to call again on a card already in progress."
    ),
    annotations=_WRITE,
)
async def claim_research_card_tool(
    task_id: Annotated[str, Field(description="The research card's task UUID.")],
) -> dict[str, Any]:
    return await _run("claim_research_card", research.claim_research_card, write=True, task_id=task_id)


@mcp_server.tool(
    name="attach_research_report",
    title="Publish the research report",
    description=(
        "Attach the finished markdown report to the card, post the one-line takeaway as a "
        "note, and move the card to Review for a teammate. The report must contain the "
        "headings ### Summary, ### Findings, ### Recommendation and ### Sources, in that order."
    ),
    annotations=_PUBLISH,
)
async def attach_research_report_tool(
    task_id: Annotated[str, Field(description="The research card's task UUID.")],
    report_markdown: Annotated[
        str, Field(description="The complete report in markdown, following report_contract.")
    ],
    card_note: Annotated[
        str, Field(description="One-line takeaway for the card, at most 240 characters.")
    ],
) -> dict[str, Any]:
    return await _run(
        "attach_research_report",
        research.attach_research_report,
        write=True,
        task_id=task_id,
        report_markdown=report_markdown,
        card_note=card_note,
    )


# ── ASGI assembly ────────────────────────────────────────────────────────────

# Building the SDK app once creates `mcp_server.session_manager`; only its
# session manager is used — the routes are laid out below so the endpoint can
# sit at /api/mcp on the main FastAPI app rather than a Starlette sub-app root.
mcp_server.streamable_http_app(
    stateless_http=True,
    json_response=True,
    # Bearer-token auth, not cookies, so the DNS-rebinding Host/Origin check
    # (meant for servers on localhost) has nothing to protect here.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
session_manager = mcp_server.session_manager

_provider = mcp_oauth.MatchaOAuthProvider()


def _mcp_endpoint():
    app = StreamableHTTPASGIApp(session_manager)
    app = RequireAuthMiddleware(
        app,
        required_scopes=[mcp_oauth.SCOPE_READ],
        resource_metadata_url=AnyHttpUrl(mcp_oauth.protected_resource_metadata_url()),
    )
    app = AuthContextMiddleware(app)
    return AuthenticationMiddleware(
        app,
        backend=BearerAuthBackend(
            mcp_oauth.MatchaTokenVerifier(_provider),
            resource_server_url=AnyHttpUrl(mcp_oauth.mcp_resource_url()),
        ),
    )


async def _as_metadata(_: Request) -> JSONResponse:
    return JSONResponse(
        mcp_oauth.authorization_server_metadata(),
        headers={"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"},
    )


async def _pr_metadata(_: Request) -> JSONResponse:
    return JSONResponse(
        mcp_oauth.protected_resource_metadata(),
        headers={"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"},
    )


# Per-IP ceilings on the two unauthenticated OAuth writes. Registration is
# rare (once per assistant install); token calls are once an hour per grant.
_OAUTH_RATE_LIMITS = {"/register": (20, 3600), "/token": (60, 60)}


class _OAuthRateLimit:
    """ASGI wrapper for /api/oauth: 429 an IP that hammers register/token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            limit = _OAUTH_RATE_LIMITS.get(scope.get("path", "").removeprefix(scope.get("root_path", "")))
            if limit:
                from fastapi import HTTPException

                from app.core.services.redis_cache import check_rate_limit, client_ip

                action = "mcp_oauth_" + scope["path"].rsplit("/", 1)[-1]
                try:
                    await check_rate_limit(client_ip(Request(scope)), action, *limit)
                except HTTPException as exc:
                    response = JSONResponse(
                        {"error": "slow_down", "error_description": "Too many requests"},
                        status_code=exc.status_code,
                        headers=exc.headers,
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def _oauth_routes() -> list[Route]:
    # The SDK's own metadata route would advertise `<issuer>/authorize`; ours
    # lives under /api/oauth, so it is dropped here and served by `_as_metadata`.
    routes = create_auth_routes(
        provider=_provider,
        issuer_url=AnyHttpUrl(mcp_oauth.issuer_url()),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=list(mcp_oauth.SUPPORTED_SCOPES),
            default_scopes=list(mcp_oauth.SUPPORTED_SCOPES),
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    return [r for r in routes if not r.path.startswith("/.well-known")]


def connector_routes() -> list[Route | Mount]:
    """Every route the connector adds to the main app, ready to append."""
    return [
        Route("/api/mcp", endpoint=_mcp_endpoint()),
        Mount("/api/oauth", app=_OAuthRateLimit(Router(routes=_oauth_routes()))),
        Route("/.well-known/oauth-protected-resource/api/mcp", _pr_metadata, methods=["GET", "OPTIONS"]),
        Route("/.well-known/oauth-protected-resource", _pr_metadata, methods=["GET", "OPTIONS"]),
        Route("/.well-known/oauth-authorization-server", _as_metadata, methods=["GET", "OPTIONS"]),
        Route("/.well-known/oauth-authorization-server/api/oauth", _as_metadata, methods=["GET", "OPTIONS"]),
    ]
