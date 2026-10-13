"""Scripted sales tests: no database, provider calls or real email."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock
from uuid import uuid4
import httpx
import pytest
from pydantic import ValidationError
from app.matcha.models.matcha_work.sales import (
    CampaignCreate,
    Prospect,
    ProspectImport,
    ProspectPatch,
    SendBatch,
    Template,
)
from app.matcha.services.matcha_work import sales_service as sales
from app.workers.tasks import sales_campaign as worker
from app.matcha.services.matcha_work.gmail_service import GmailSendRateLimited
from tests.agent_runtime.helpers import FakeConn, connection

USER, PROJECT, CAMPAIGN, ITEM, TOKEN = (uuid4() for _ in range(5))


def access_row(role="owner", **over):
    return (
        dict(
            collaborator_role=role,
            user_role="client",
            home_features={"matcha_work": True},
            signup_source=None,
            visible_features='["matcha_work"]',
        )
        | over
    )


def campaign(**over):
    return (
        dict(
            id=CAMPAIGN,
            project_id=PROJECT,
            user_id=USER,
            title="Dental",
            target="SF",
            offer="Video",
            status="idle",
            sender="owner@example.test",
            dispatch_token=TOKEN,
            last_approval_id=None,
            next_attempt_at=None,
            error=None,
        )
        | over
    )


def prospect(**over):
    return (
        dict(
            id=ITEM,
            campaign_id=CAMPAIGN,
            email="a@example.test",
            name="Ana",
            company="Dental",
            website="https://example.test",
            notes="",
            research="Public hours",
            sources='["https://example.test"]',
            subject="Hello Ana",
            body="Hi Ana",
            stage="lead",
            status="draft",
            error=None,
        )
        | over
    )


@pytest.fixture
def wired(monkeypatch):
    conn = (
        FakeConn()
        .on("FROM mw_sales_campaigns", campaign())
        .on("FROM mw_projects p JOIN users", access_row())
    )
    monkeypatch.setattr(sales, "connection_or_direct", connection(conn))
    monkeypatch.setattr(worker, "connection_or_direct", connection(conn))
    return conn


def test_validation_templates_and_review_fingerprints():
    assert Prospect(email=" ANA@Example.test ").email == "ana@example.test"
    assert Prospect(sources=["https://example.test"] * 2).sources == [
        "https://example.test"
    ]
    for fields in [
        dict(email="a@example.test,b@example.test"),
        dict(email="Ana <a@example.test>"),
        dict(email="a@example.test\nBcc: x"),
        dict(sources=["file:///tmp/private"]),
        dict(website="https://user:secret@example.test"),
    ]:
        with pytest.raises(ValidationError):
            Prospect(**fields)
    for fields in [dict(subject="x\nBcc: y"), dict(stage="bad")]:
        with pytest.raises(ValidationError):
            ProspectPatch(**fields)
    for values in [[], [Prospect(email="a@example.test")] * 1001]:
        with pytest.raises(ValidationError):
            ProspectImport(prospects=values)
    assert (
        sales.render_template("Hi {{name}} at {{company}}", prospect(name="Zoë 👋"))
        == "Hi Zoë 👋 at Dental"
    )
    for template in ["{{secret}}", "{{name", "{{name}} }}"]:
        with pytest.raises(sales.SalesError):
            sales.render_template(template, prospect())
    assert sales.dedupe_key(Prospect(email="A@example.test")) == "email:a@example.test"
    assert sales.dedupe_key(Prospect(company="Dental")) == sales.dedupe_key(
        Prospect(company="dental")
    )
    with pytest.raises(sales.SalesError):
        sales.dedupe_key(Prospect(notes="Missing contact"))
    assert sales.review_token(prospect()) != sales.review_token(prospect(body="new"))
    assert sales.view(prospect())["sources"] == ["https://example.test"]
    assert "dispatch_token" not in sales.view(campaign())


@pytest.mark.asyncio
async def test_access_rechecks_account_and_collaborator_permissions(wired):
    await sales.project_access(wired, PROJECT, USER, edit=True)
    query = wired.ran("FROM mw_projects p JOIN users")[0][1]
    assert (
        "u.is_active" in query
        and "is_suspended" in query
        and "status = 'active'" in query
    )
    assert "u.role IN ('client','individual') AND cl.company_id = p.company_id" in query
    wired.on("FROM mw_projects p JOIN users", access_row("viewer"))
    with pytest.raises(sales.SalesError, match="read-only"):
        await sales.project_access(wired, PROJECT, USER, edit=True)
    await sales.project_access(wired, PROJECT, USER)
    wired.on("FROM mw_projects p JOIN users", None)
    with pytest.raises(sales.SalesError) as exc:
        await sales.project_access(wired, PROJECT, USER)
    assert exc.value.code == 404


@pytest.mark.asyncio
async def test_revoked_feature_and_platform_visibility_pause_delivery_access(wired):
    for row in [access_row(home_features={}), access_row(visible_features="[]")]:
        wired.on("FROM mw_projects p JOIN users", row)
        with pytest.raises(sales.SalesError, match="no longer enabled"):
            await sales.project_access(wired, PROJECT, USER, edit=True)
    wired.on(
        "FROM mw_projects p JOIN users", access_row(user_role="admin", home_features={})
    )
    await sales.project_access(wired, PROJECT, USER, edit=True)


@pytest.mark.asyncio
async def test_campaign_reads_creation_and_pages_are_owner_scoped(wired):
    wired.on("SELECT DISTINCT p.id", [{"id": PROJECT, "title": "Work"}])
    assert (await sales.list_projects(USER))[0]["id"] == str(PROJECT)
    wired.on("ORDER BY updated_at DESC", [campaign()])
    assert (await sales.list_campaigns(PROJECT, USER))[0]["title"] == "Dental"
    wired.on("INSERT INTO mw_sales_campaigns", campaign())
    assert (
        await sales.create_campaign(
            PROJECT, USER, CampaignCreate(request_id=uuid4(), title="Dental")
        )
    )["id"] == str(CAMPAIGN)
    wired.on("ORDER BY created_at,id OFFSET", [prospect()]).on(
        "GROUP BY status", [{"status": "draft", "count": 1}]
    )
    data = await sales.read_campaign(CAMPAIGN, USER, offset=25, limit=25)
    assert data["counts"] == {"draft": 1} and data["offset"] == 25
    assert wired.ran("FOR UPDATE")[0][2] == (CAMPAIGN, USER)
    for offset, limit in [(-1, 25), (0, 0), (1001, 25), (0, 1001)]:
        with pytest.raises(sales.SalesError):
            await sales.read_campaign(CAMPAIGN, USER, offset=offset, limit=limit)
    wired.on("INSERT INTO mw_sales_campaigns", campaign(project_id=uuid4()))
    with pytest.raises(sales.SalesError, match="another workspace"):
        await sales.create_campaign(
            PROJECT, USER, CampaignCreate(request_id=uuid4(), title="Dental")
        )
    wired.on("FROM mw_sales_campaigns", None)
    with pytest.raises(sales.SalesError, match="not found"):
        await sales.read_campaign(CAMPAIGN, USER)


@pytest.mark.asyncio
async def test_import_dedupes_and_enforces_campaign_total(wired):
    wired.on("array_agg(dedupe_key)", ["email:existing@example.test"])
    out = await sales.import_prospects(
        CAMPAIGN,
        USER,
        ProspectImport(
            prospects=[
                Prospect(email=e)
                for e in [
                    "new@example.test",
                    "NEW@example.test",
                    "existing@example.test",
                ]
            ]
        ),
    )
    assert (
        out == {"added": 1, "duplicates": 2}
        and len(wired.ran("INSERT INTO mw_sales_prospects")) == 1
    )
    wired.on("array_agg(dedupe_key)", [f"email:{i}@example.test" for i in range(1000)])
    with pytest.raises(sales.SalesError, match="1,000"):
        await sales.import_prospects(
            CAMPAIGN,
            USER,
            ProspectImport(prospects=[Prospect(email="new@example.test")]),
        )


@pytest.mark.asyncio
async def test_edits_compare_review_token_and_preserve_frozen_messages(wired):
    row = prospect()
    wired.on("FROM mw_sales_prospects WHERE campaign_id", row).on(
        "UPDATE mw_sales_prospects SET", row | {"body": "edited"}
    )
    assert (
        await sales.patch_prospect(
            CAMPAIGN,
            ITEM,
            USER,
            ProspectPatch(body="edited", review_token=sales.review_token(row)),
        )
    )["body"] == "edited"
    with pytest.raises(sales.SalesError, match="draft changed"):
        await sales.patch_prospect(
            CAMPAIGN, ITEM, USER, ProspectPatch(body="x", review_token="x" * 64)
        )
    wired.on("SELECT EXISTS", True)
    with pytest.raises(sales.SalesError, match="already"):
        await sales.patch_prospect(
            CAMPAIGN, ITEM, USER, ProspectPatch(email="other@example.test")
        )
    wired.on("SELECT EXISTS", False)
    await sales.patch_prospect(
        CAMPAIGN,
        ITEM,
        USER,
        ProspectPatch(email="other@example.test", sources=["https://example.test"]),
    )
    await sales.patch_prospect(CAMPAIGN, ITEM, USER, ProspectPatch())
    wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect(status="approved"))
    with pytest.raises(sales.SalesError, match="frozen"):
        await sales.patch_prospect(
            CAMPAIGN, ITEM, USER, ProspectPatch(body="late edit")
        )
    await sales.patch_prospect(CAMPAIGN, ITEM, USER, ProspectPatch(stage="qualified"))
    wired.on("FROM mw_sales_prospects WHERE campaign_id", None)
    with pytest.raises(sales.SalesError, match="not found"):
        await sales.patch_prospect(
            CAMPAIGN, ITEM, USER, ProspectPatch(stage="qualified")
        )


@pytest.mark.asyncio
async def test_template_validates_all_rows_before_writing(wired):
    wired.on(
        "status IN ('prospect','draft','failed')",
        [prospect(), prospect(id=uuid4(), email="")],
    )
    assert (
        await sales.draft_template(
            CAMPAIGN, USER, Template(subject="Hi {{name}}", body="About {{company}}")
        )
    )["drafted"] == 2
    calls = wired.ran("UPDATE mw_sales_prospects SET subject")
    rendered = json.loads(calls[0][2][-1])
    assert rendered[0]["status"] == "draft" and rendered[1]["status"] == "prospect"
    wired.calls.clear()
    wired.on(
        "status IN ('prospect','draft','failed')",
        [prospect(), prospect(name="a\nBcc: b")],
    )
    with pytest.raises(sales.SalesError, match="multiline"):
        await sales.draft_template(
            CAMPAIGN, USER, Template(subject="Hi {{name}}", body="Hi")
        )
    assert not wired.ran("UPDATE mw_sales_prospects SET subject")


def batch():
    return SendBatch(
        request_id=uuid4(),
        sender="owner@example.test",
        drafts=[{"id": ITEM, "review_token": sales.review_token(prospect())}],
    )


@pytest.mark.asyncio
async def test_approval_is_exact_idempotent_and_sender_scoped(wired, monkeypatch):
    gmail = type(
        "Gmail",
        (),
        {
            "get_status": AsyncMock(
                return_value={"connected": True, "email": "owner@example.test"}
            )
        },
    )()
    dispatch = AsyncMock()
    monkeypatch.setattr(sales, "dispatch", dispatch)
    wired.on("id = ANY", [prospect()]).on("SELECT COUNT(*)", 0)
    data = batch()
    await sales.approve_batch(CAMPAIGN, USER, data, gmail)
    assert wired.ran("SET status = 'approved'") and dispatch.await_count == 1
    wired.on(
        "FROM mw_sales_campaigns",
        campaign(last_approval_id=data.request_id, status="sending"),
    )
    assert await sales.approve_batch(CAMPAIGN, USER, data, gmail) == {
        "status": "sending"
    }
    assert dispatch.await_count == 1
    wired.on("FROM mw_sales_campaigns", campaign(status="sending"))
    with pytest.raises(sales.SalesError, match="Pause"):
        await sales.approve_batch(CAMPAIGN, USER, batch(), gmail)
    wired.on("FROM mw_sales_campaigns", campaign()).on(
        "id = ANY", [prospect(body="changed")]
    )
    with pytest.raises(sales.SalesError, match="changed"):
        await sales.approve_batch(CAMPAIGN, USER, batch(), gmail)
    wired.on("id = ANY", [prospect()]).on("SELECT COUNT(*)", 1)
    with pytest.raises(sales.SalesError, match="pending"):
        await sales.approve_batch(CAMPAIGN, USER, batch(), gmail)
    data = batch()
    data.drafts *= 2
    with pytest.raises(sales.SalesError, match="only once"):
        await sales.approve_batch(CAMPAIGN, USER, data, gmail)
    gmail.get_status.return_value = {"connected": True, "email": "other@example.test"}
    with pytest.raises(sales.SalesError, match="Connect"):
        await sales.approve_batch(CAMPAIGN, USER, batch(), gmail)


@pytest.mark.asyncio
async def test_actions_recover_pending_and_only_retry_definite_failures(
    wired, monkeypatch
):
    dispatch = AsyncMock()
    monkeypatch.setattr(sales, "dispatch", dispatch)
    for action in ["pause", "release_pending", "retry_failed"]:
        await sales.campaign_action(CAMPAIGN, USER, action)
    assert "status = 'approved'" in wired.ran("SET status = 'draft'")[0][1]
    assert "status = 'failed'" in wired.ran("SET status = 'draft', error")[0][1]
    assert "status = 'claimed'" in wired.ran("SET status = 'unknown'")[0][1]
    assert not dispatch.called
    wired.on("SELECT COUNT(*)", 2)
    await sales.campaign_action(CAMPAIGN, USER, "resume")
    dispatch.assert_awaited_once()
    wired.on("SELECT COUNT(*)", 0)
    with pytest.raises(sales.SalesError, match="No approved"):
        await sales.campaign_action(CAMPAIGN, USER, "resume")
    with pytest.raises(sales.SalesError, match="Unknown"):
        await sales.campaign_action(CAMPAIGN, USER, "bad")


@pytest.mark.asyncio
async def test_broker_failure_pauses_without_losing_approval(wired, monkeypatch):
    monkeypatch.setattr(
        worker.send_sales_campaign,
        "apply_async",
        lambda **_kw: (_ for _ in ()).throw(RuntimeError("broker")),
    )
    with pytest.raises(sales.SalesError) as exc:
        await sales.dispatch(CAMPAIGN, TOKEN)
    assert exc.value.code == 503 and wired.ran("status = 'paused'")
    assert not wired.ran("UPDATE mw_sales_prospects")


@pytest.fixture
def delivery(wired, monkeypatch):
    wired.on("FROM mw_sales_campaigns", campaign(status="sending")).on(
        "SELECT EXISTS", False
    ).on("status = 'approved' ORDER", prospect(status="approved"))
    monkeypatch.setattr(worker, "_is_reserved_test_domain", lambda _email: False)
    dispatch = AsyncMock()
    monkeypatch.setattr(sales, "dispatch", dispatch)
    gmail = type(
        "Gmail",
        (),
        {
            "get_status": AsyncMock(
                return_value={"connected": True, "email": "owner@example.test"}
            ),
            "send_email": AsyncMock(return_value={"id": "message-1"}),
        },
    )()
    return gmail, dispatch


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,outcome",
    [
        ("none", "sent"),
        ("quota", "approved"),
        ("transport", "unknown"),
        ("500", "unknown"),
        ("400", "failed"),
        ("invalid", "failed"),
        ("no_id", "unknown"),
    ],
)
async def test_delivery_claims_before_send_and_keeps_uncertain_outcomes(
    wired, delivery, failure, outcome
):
    gmail, dispatch = delivery
    if failure == "quota":
        gmail.send_email.side_effect = GmailSendRateLimited("50 emails per hour")
    if failure == "transport":
        gmail.send_email.side_effect = httpx.ReadTimeout("lost ack")
    if failure in ("500", "400"):
        response = httpx.Response(
            int(failure), request=httpx.Request("POST", "https://example.test/send")
        )
        gmail.send_email.side_effect = httpx.HTTPStatusError(
            "refused", request=response.request, response=response
        )
    if failure == "invalid":
        gmail.send_email.side_effect = ValueError("invalid")
    if failure == "no_id":
        gmail.send_email.return_value = {}
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert (
        wired.ran("SET status = 'claimed'")
        and wired.ran("SET status = $2")[0][2][1] == outcome
    )
    assert gmail.send_email.call_args.kwargs == {
        "to": "a@example.test",
        "subject": "Hello Ana",
        "body": "Hi Ana",
    }
    assert dispatch.call_args.kwargs["countdown"] == (
        3600 if failure == "quota" else 15
    )


@pytest.mark.asyncio
async def test_worker_stale_token_revoked_access_and_mailbox_switch(wired, delivery):
    gmail, dispatch = delivery
    await worker.deliver_one(CAMPAIGN, uuid4(), gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and not dispatch.called
    wired.on("FROM mw_projects p JOIN users", None)
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert wired.ran("Workspace access changed") and not gmail.send_email.called
    wired.on("FROM mw_projects p JOIN users", access_row())
    gmail.get_status.return_value = {"connected": True, "email": "other@example.test"}
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert (
        wired.ran("SET status = 'approved', claimed_at = NULL")
        and not gmail.send_email.called
    )


@pytest.mark.asyncio
async def test_duplicate_jobs_wait_for_pacing_and_claims_then_finish(wired, delivery):
    gmail, dispatch = delivery
    wired.on(
        "FROM mw_sales_campaigns",
        campaign(
            status="sending",
            next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        ),
    )
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and dispatch.call_args.kwargs["countdown"] >= 59
    wired.on("FROM mw_sales_campaigns", campaign(status="sending")).on(
        "SELECT EXISTS", True
    )
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and dispatch.call_args.kwargs["countdown"] == 60
    wired.on("SELECT EXISTS", False).on("status = 'approved' ORDER", None)
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert wired.ran("status = 'complete'")


@pytest.mark.asyncio
async def test_reserved_test_addresses_are_never_delivered(
    wired, delivery, monkeypatch
):
    gmail, _ = delivery
    monkeypatch.setattr(worker, "_is_reserved_test_domain", lambda _email: True)
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and wired.ran("status = 'paused'")
