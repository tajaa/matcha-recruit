from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from app.matcha.services.matcha_work.agent_runtime import catalog, consent
from app.matcha.services.matcha_work.agent_runtime.abilities import sales
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from .helpers import context

PROJECT, CAMPAIGN, ITEM = [str(uuid4()) for _ in range(3)]


def test_sales_is_private_and_requires_its_own_data_sharing_consent():
    ability = sales.build()
    assert ability.consent_version == consent.current_version("sales")
    assert not catalog.availability(ability, catalog.Situation(private=True)).available
    assert catalog.availability(
        ability, catalog.Situation(private=True, grants={"sales": {}})
    ).available
    assert not catalog.availability(
        ability, catalog.Situation(private=False, grants={"sales": {}})
    ).available
    assert all(
        tool.effect in ("draft", "read") and tool.untrusted_output
        for tool in ability.tools
    )
    assert "review" in ability.prompt_block(context()).lower()


@pytest.fixture
def wired(monkeypatch):
    mocks = {}
    for name in [
        "list_projects",
        "list_campaigns",
        "read_campaign",
        "create_campaign",
        "import_prospects",
        "patch_prospect",
        "draft_template",
    ]:
        mocks[name] = AsyncMock()
        monkeypatch.setattr(sales.store, name, mocks[name])
    mocks["list_projects"].return_value = [{"id": PROJECT, "title": "Sales"}]
    mocks["list_campaigns"].return_value = [{"id": CAMPAIGN, "title": "Dental"}]
    mocks["read_campaign"].return_value = {
        "campaign": {"id": CAMPAIGN},
        "prospects": [{"id": ITEM}],
    }
    mocks["create_campaign"].return_value = {"id": CAMPAIGN}
    mocks["import_prospects"].return_value = {"added": 1}
    mocks["patch_prospect"].return_value = {"id": ITEM}
    mocks["draft_template"].return_value = {"drafted": 100}
    return mocks


async def invoke(name, args, state, ctx=None):
    tool = next(t for t in sales.build().tools if t.name == name)
    return await tool.handler(ctx or context(), state, args, 60)


def state():
    return RunState(started=0, sessions={"sales": sales.SalesSession()})


@pytest.mark.asyncio
async def test_tools_save_discovery_research_and_drafts_in_a_reopenable_campaign(wired):
    s = state()
    assert (
        await invoke(
            "create_sales_campaign", {"project_id": PROJECT, "title": "Dental"}, s
        )
    ).status == "error"
    await invoke("list_sales_workspaces", {}, s)
    await invoke(
        "create_sales_campaign",
        {"project_id": PROJECT, "title": "Dental", "target": "SF", "offer": "Video"},
        s,
    )
    await invoke("list_sales_campaigns", {"project_id": PROJECT}, s)
    await invoke("read_sales_campaign", {"campaign_id": CAMPAIGN, "offset": 25}, s)
    assert wired["read_campaign"].call_args.kwargs == {"offset": 25, "limit": 25}
    s.provenance.add("https://example.test")
    await invoke(
        "add_sales_prospects",
        {
            "campaign_id": CAMPAIGN,
            "prospects": [{"name": "Ana", "sources": ["https://example.test"]}],
        },
        s,
    )
    await invoke(
        "update_sales_prospect",
        {
            "campaign_id": CAMPAIGN,
            "prospect_id": ITEM,
            "changes": {
                "research": "Public hours",
                "sources": ["https://example.test"],
            },
        },
        s,
    )
    await invoke(
        "update_sales_prospect",
        {
            "campaign_id": CAMPAIGN,
            "prospect_id": ITEM,
            "changes": {"subject": "Hi Ana", "body": "An offer"},
        },
        s,
    )
    out = await invoke(
        "draft_sales_template",
        {"campaign_id": CAMPAIGN, "subject": "Hi {{name}}", "body": "An offer"},
        s,
    )
    assert out.payload == {"drafted": 100} and wired["patch_prospect"].await_count == 2


@pytest.mark.asyncio
async def test_writes_need_a_read_and_discovery_needs_observed_sources(wired):
    s = state()
    args = {"campaign_id": CAMPAIGN, "prospects": [{"email": "ana@example.test"}]}
    assert (await invoke("add_sales_prospects", args, s)).status == "error"
    await invoke("read_sales_campaign", {"campaign_id": CAMPAIGN}, s)
    assert (await invoke("add_sales_prospects", args, s)).status == "error"
    assert (
        await invoke(
            "add_sales_prospects", args, s, context(ask="Use ana@example.test")
        )
    ).status == "ok"
    args["prospects"] = [{"name": "Discovered", "sources": ["https://never-read.test"]}]
    assert (await invoke("add_sales_prospects", args, s)).status == "error"
    args["prospects"] = [{"email": "a@example.test"}] * 51
    assert (await invoke("add_sales_prospects", args, s)).status == "error"
    update = {
        "campaign_id": CAMPAIGN,
        "prospect_id": str(uuid4()),
        "changes": {"body": "Hi"},
    }
    assert (await invoke("update_sales_prospect", update, s)).status == "error"
    update["prospect_id"] = ITEM
    update["changes"] = {"research": "Unsupported fact"}
    assert (await invoke("update_sales_prospect", update, s)).status == "error"
    update["changes"] = {
        "research": "Unsupported fact",
        "sources": ["https://never-read.test"],
    }
    assert (await invoke("update_sales_prospect", update, s)).status == "error"
    wired["read_campaign"].side_effect = sales.store.SalesError("Access revoked")
    assert (
        await invoke("read_sales_campaign", {"campaign_id": CAMPAIGN}, s)
    ).payload == {"error": "Access revoked"}


@pytest.mark.asyncio
async def test_large_research_pages_stay_valid_and_continue_at_actual_offset(wired):
    import json

    s = state()
    wired["read_campaign"].return_value = {
        "campaign": {"id": CAMPAIGN},
        "offset": 0,
        "prospects": [
            {
                "id": str(uuid4()),
                "notes": "n" * 4000,
                "research": "r" * 6000,
                "body": "b" * 12000,
                "sources": ["https://example.test"],
            }
            for _ in range(25)
        ],
    }
    result = await invoke("read_sales_campaign", {"campaign_id": CAMPAIGN}, s)
    assert len(json.dumps(result.payload)) < 12000
    assert result.payload["next_offset"] == 1
    assert result.payload["prospects"][0]["text_truncated"]
    assert len(s.sessions["sales"].prospects) == 1
