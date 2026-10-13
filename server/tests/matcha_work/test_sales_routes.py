from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.core.models.auth import CurrentUser
from app.matcha.routes.matcha_work import sales as routes
from app.matcha.models.matcha_work.sales import (
    CampaignCreate,
    ProspectImport,
    ProspectPatch,
    Template,
    SendBatch,
    CampaignAction,
)
from app.matcha.dependencies import require_admin_or_client

USER = CurrentUser(id=uuid4(), email="owner@example.test", role="client")
PID, CID, ITEM = uuid4(), uuid4(), uuid4()


@pytest.mark.asyncio
async def test_routes_use_validated_bodies_and_current_owner(monkeypatch):
    for name in [
        "list_campaigns",
        "create_campaign",
        "read_campaign",
        "import_prospects",
        "patch_prospect",
        "draft_template",
        "approve_batch",
        "campaign_action",
    ]:
        mock = AsyncMock(return_value={"ok": True})
        monkeypatch.setattr(routes.sales, name, mock)
    await routes.campaigns(PID, USER)
    await routes.create(PID, CampaignCreate(request_id=uuid4(), title="Dental"), USER)
    await routes.read(CID, USER)
    await routes.add(CID, ProspectImport(prospects=[{"email": "a@example.test"}]), USER)
    await routes.update(CID, ITEM, ProspectPatch(stage="qualified"), USER)
    await routes.template(CID, Template(subject="Hi", body="Offer"), USER)
    await routes.send(
        CID,
        SendBatch(
            request_id=uuid4(),
            sender="owner@example.test",
            drafts=[{"id": ITEM, "review_token": "a" * 64}],
        ),
        USER,
    )
    await routes.action(CID, CampaignAction(action="pause"), USER)
    assert routes.sales.patch_prospect.call_args.args[:3] == (CID, ITEM, USER.id)
    assert routes.sales.approve_batch.call_args.args[1] == USER.id
    assert routes.sales.campaign_action.call_args.args == (CID, USER.id, "pause")
    assert all(
        any(d.dependency is require_admin_or_client for d in route.dependencies)
        for route in routes.router.routes
    )


@pytest.mark.asyncio
async def test_errors_preserve_actionable_status():
    async def refused():
        raise routes.sales.SalesError("Draft changed", 409)

    with pytest.raises(HTTPException) as exc:
        await routes._call(refused())
    assert exc.value.status_code == 409 and exc.value.detail == "Draft changed"
