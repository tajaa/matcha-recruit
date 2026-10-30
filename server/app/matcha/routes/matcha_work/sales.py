"""User-owned sales campaigns; only the human review surface enqueues sends."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.core.models.auth import CurrentUser
from app.matcha.dependencies import require_admin_or_client
from app.matcha.models.matcha_work.sales import (
    CampaignCreate,
    CampaignPatch,
    ProspectImport,
    ProspectPatch,
    Template,
    SendBatch,
    CampaignAction,
    ResolveUnknown,
)
from app.matcha.services.matcha_work import sales_service as sales

router = APIRouter(dependencies=[Depends(require_admin_or_client)])


async def _call(operation):
    try:
        return await operation
    except sales.SalesError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc)) from exc


@router.get("/projects/{project_id}/sales")
async def campaigns(
    project_id: UUID, user: CurrentUser = Depends(require_admin_or_client)
):
    return {
        "campaigns": await _call(sales.list_campaigns(project_id, user.id)),
        # Other editors' campaigns here: summaries only, no contact data.
        "workspace_campaigns": await _call(
            sales.workspace_campaigns(project_id, user.id)
        ),
    }


@router.post("/projects/{project_id}/sales")
async def create(
    project_id: UUID,
    body: CampaignCreate,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.create_campaign(project_id, user.id, body))


# Declared before /sales/{campaign_id} so these are never read as an id.
@router.get("/sales/workspaces")
async def workspaces(user: CurrentUser = Depends(require_admin_or_client)):
    """The collab workspaces a campaign can live in (the web Sales page's picker)."""
    return {"workspaces": await _call(sales.list_projects(user.id))}


@router.get("/sales/playbooks")
async def playbooks(user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(sales.playbook_options(user.id))


@router.get("/sales/{campaign_id}")
async def read(campaign_id: UUID, user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(sales.read_campaign(campaign_id, user.id))


@router.patch("/sales/{campaign_id}")
async def edit(
    campaign_id: UUID,
    body: CampaignPatch,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.update_campaign(campaign_id, user.id, body))


@router.delete("/sales/{campaign_id}")
async def delete(
    campaign_id: UUID, user: CurrentUser = Depends(require_admin_or_client)
):
    return await _call(sales.delete_campaign(campaign_id, user.id))


@router.get("/sales/{campaign_id}/status")
async def status(
    campaign_id: UUID, user: CurrentUser = Depends(require_admin_or_client)
):
    return await _call(sales.campaign_status(campaign_id, user.id))


@router.post("/sales/{campaign_id}/prospects")
async def add(
    campaign_id: UUID,
    body: ProspectImport,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.import_prospects(campaign_id, user.id, body))


@router.patch("/sales/{campaign_id}/prospects/{item_id}")
async def update(
    campaign_id: UUID,
    item_id: UUID,
    body: ProspectPatch,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.patch_prospect(campaign_id, item_id, user.id, body))


@router.delete("/sales/{campaign_id}/prospects/{item_id}")
async def remove(
    campaign_id: UUID,
    item_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.delete_prospect(campaign_id, item_id, user.id))


@router.post("/sales/{campaign_id}/prospects/{item_id}/opt-out")
async def opt_out(
    campaign_id: UUID,
    item_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.opt_out(campaign_id, item_id, user.id))


@router.post("/sales/{campaign_id}/prospects/{item_id}/resolve")
async def resolve(
    campaign_id: UUID,
    item_id: UUID,
    body: ResolveUnknown,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(
        sales.resolve_unknown(campaign_id, item_id, user.id, body.outcome)
    )


@router.post("/sales/{campaign_id}/template")
async def template(
    campaign_id: UUID,
    body: Template,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.draft_template(campaign_id, user.id, body))


@router.post("/sales/{campaign_id}/send")
async def send(
    campaign_id: UUID,
    body: SendBatch,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.approve_batch(campaign_id, user.id, body))


@router.post("/sales/{campaign_id}/action")
async def action(
    campaign_id: UUID,
    body: CampaignAction,
    user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(sales.campaign_action(campaign_id, user.id, body.action))
