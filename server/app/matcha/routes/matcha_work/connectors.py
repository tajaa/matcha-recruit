"""AI connectors: the person's Claude / ChatGPT link to Matcha.

Three concerns, all on the gated `/matcha-work` router:

- **Consent** (`/connectors/consent`) — the SPA page an OAuth authorize request
  lands on. The person is logged in as themselves; approving mints the code
  their AI client exchanges for a connector token. The OAuth protocol endpoints
  themselves are the MCP SDK's, mounted at `/api/oauth/*` by main.py.
- **Grants** (`/connectors`) — which assistants are connected, and disconnect.
- **Launch** (`/projects/{pid}/tasks/{tid}/research-launch`) — the "Research with
  Claude / ChatGPT" button: a deep link that opens a prefilled chat. The model
  then runs on the person's plan and talks back through the connector tools.

Nothing here holds or forwards a Claude / OpenAI credential. See
docs/ops/MCP_CONNECTOR.md.
"""
import logging
import shlex
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.core.services import mcp_oauth
from app.matcha.dependencies import require_company_member
from app.matcha.models.matcha_work.connectors import (
    ConnectorGrant,
    ConnectorsResponse,
    ConsentDecision,
    ConsentDescription,
    ConsentResult,
    ResearchLaunchRequest,
    ResearchLaunchResponse,
)
from app.matcha.routes.mcp_connector import research

logger = logging.getLogger(__name__)
router = APIRouter()

_DEEP_LINKS = {
    "claude": "https://claude.ai/new?q={q}",
    "chatgpt": "https://chatgpt.com/?q={q}",
}


def _claude_code_add_command() -> str:
    return f"claude mcp add --transport http matcha {mcp_oauth.mcp_resource_url()}"


@router.get("/connectors", response_model=ConnectorsResponse)
async def list_connectors_endpoint(
    current_user: CurrentUser = Depends(require_company_member),
):
    grants = [ConnectorGrant(**g) for g in await mcp_oauth.list_user_grants(current_user.id)]
    kinds = {g.kind for g in grants}
    return ConnectorsResponse(
        mcp_url=mcp_oauth.mcp_resource_url(),
        grants=grants,
        connected={k: k in kinds for k in ("claude", "chatgpt", "claude_code")},
        claude_code_command=_claude_code_add_command(),
    )


@router.delete("/connectors/{client_id}")
async def disconnect_connector_endpoint(
    client_id: str,
    current_user: CurrentUser = Depends(require_company_member),
):
    revoked = await mcp_oauth.revoke_client_grants(current_user.id, client_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="No active connection for that assistant")
    logger.info("[mcp-oauth] disconnected client=%s user=%s", client_id, current_user.id)
    return {"disconnected": True}


@router.get("/connectors/consent", response_model=ConsentDescription)
async def describe_consent_endpoint(
    request: str = Query(..., min_length=1, max_length=8000),
    current_user: CurrentUser = Depends(require_company_member),
):
    described = await mcp_oauth.describe_consent(request)
    if not described:
        raise HTTPException(
            status_code=400,
            detail="This connection request has expired. Start connecting again from your assistant.",
        )
    return ConsentDescription(**{k: described[k] for k in ConsentDescription.model_fields})


@router.post("/connectors/consent", response_model=ConsentResult)
async def decide_consent_endpoint(
    body: ConsentDecision,
    current_user: CurrentUser = Depends(require_company_member),
):
    if body.approve:
        redirect_url = await mcp_oauth.approve_authorization(body.request, current_user.id)
    else:
        redirect_url = mcp_oauth.deny_authorization(body.request)
    if not redirect_url:
        raise HTTPException(
            status_code=400,
            detail="This connection request has expired. Start connecting again from your assistant.",
        )
    return ConsentResult(redirect_url=redirect_url)


@router.post(
    "/projects/{project_id}/tasks/{task_id}/research-launch",
    response_model=ResearchLaunchResponse,
)
async def research_launch_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: ResearchLaunchRequest,
    current_user: CurrentUser = Depends(require_company_member),
):
    try:
        card, _project, _role = await research._authorized_card(current_user, task_id)
    except research.ConnectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    if card["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    prompt = research.launch_prompt(card["id"], card["title"])
    if body.client == "claude_code":
        return ResearchLaunchResponse(
            client=body.client, prompt=prompt, command=f"claude {shlex.quote(prompt)}"
        )
    url = _DEEP_LINKS[body.client].format(q=quote(prompt, safe=""))
    return ResearchLaunchResponse(client=body.client, url=url, prompt=prompt)
