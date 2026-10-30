"""Scripted sales tests: no database, provider calls or real email."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock
from uuid import uuid4
import httpx
import pytest
from pydantic import ValidationError
from app.matcha.models.matcha_work.sales import (
    FOOTER_PLACEHOLDER,
    CampaignCreate,
    CampaignPatch,
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
FOOTER = "Reply unsubscribe and I won't email you again.\nAcme Video, 1 Main St, Springfield"


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
            footer=FOOTER,
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


def token(row=None):
    return sales.review_token(row or prospect(), FOOTER)


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
    # A person can read a batch of 50; 51 is refused before any check runs.
    with pytest.raises(ValidationError):
        SendBatch(
            request_id=uuid4(),
            sender="owner@example.test",
            drafts=[{"id": uuid4(), "review_token": "a" * 64} for _ in range(51)],
        )
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


def test_footer_is_part_of_the_review_and_of_the_sent_body():
    assert token() != sales.review_token(prospect(), "Another footer")
    assert sales.view(prospect(), FOOTER)["review_token"] == token()
    assert sales.compose_body("Hi Ana\n", FOOTER) == f"Hi Ana\n\n{FOOTER}"
    assert sales.compose_body("Hi Ana", " ") == "Hi Ana"
    assert sales.footer_problem(FOOTER) is None
    assert sales.footer_problem("")
    assert sales.footer_problem(f"Reply stop.\n{FOOTER_PLACEHOLDER}")


@pytest.mark.asyncio
async def test_access_rechecks_account_and_collaborator_permissions(wired):
    await sales.project_access(wired, PROJECT, USER, edit=True)
    query = wired.ran("FROM mw_projects p JOIN users")[0][1]
    assert (
        "u.is_active" in query
        and "is_suspended" in query
        and "status = 'active'" in query
        and "p.project_type = 'collab'" in query
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
async def test_workspace_list_uses_the_same_access_and_feature_rule(wired):
    wired.on(
        "SELECT DISTINCT",
        [
            access_row() | {"id": PROJECT, "title": "Work"},
            access_row(home_features={}) | {"id": uuid4(), "title": "Disabled"},
        ],
    )
    assert await sales.list_projects(USER) == [{"id": str(PROJECT), "title": "Work"}]
    access_query = wired.ran("SELECT DISTINCT")[0][1]
    assert "p.project_type = 'collab'" in access_query and "is_suspended" in access_query


@pytest.mark.asyncio
async def test_campaign_reads_creation_and_pages_are_owner_scoped(wired):
    wired.on("ORDER BY updated_at DESC", [campaign()])
    assert (await sales.list_campaigns(PROJECT, USER))[0]["title"] == "Dental"
    wired.on("INSERT INTO mw_sales_campaigns", campaign())
    assert (
        await sales.create_campaign(
            PROJECT,
            USER,
            CampaignCreate(request_id=uuid4(), title="Dental", footer=FOOTER),
        )
    )["id"] == str(CAMPAIGN)
    # project, user, request, title, target, offer, footer, playbook, cta_url
    assert wired.ran("INSERT INTO mw_sales_campaigns")[0][2][6] == FOOTER
    wired.on("ORDER BY created_at,id OFFSET", [prospect()]).on(
        "GROUP BY status", [{"status": "draft", "count": 1}]
    )
    data = await sales.read_campaign(CAMPAIGN, USER, offset=25, limit=25)
    assert data["counts"] == {"draft": 1} and data["offset"] == 25
    assert data["prospects"][0]["review_token"] == token()
    # Reads (polled every 15 s) never take the campaign row lock.
    assert not wired.ran("FOR UPDATE")
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
async def test_status_poll_carries_tokens_but_no_message_text(wired):
    wired.on("SELECT id, email, subject, body, status, error", [prospect()]).on(
        "GROUP BY status", [{"status": "draft", "count": 1}]
    )
    data = await sales.campaign_status(CAMPAIGN, USER)
    assert data["prospects"] == [
        {"id": str(ITEM), "status": "draft", "error": None, "review_token": token()}
    ]
    assert data["counts"] == {"draft": 1} and not wired.ran("FOR UPDATE")


@pytest.mark.asyncio
async def test_other_editors_see_campaign_summaries_without_contacts(wired):
    summary = {"id": uuid4(), "title": "Clinics", "status": "sending", "creator": "b@example.test", "prospects": 3, "sent": 1, "problems": 0}
    wired.on("COUNT(p.id) FILTER", [summary])
    rows = await sales.workspace_campaigns(PROJECT, USER)
    assert rows[0]["creator"] == "b@example.test" and "email" not in rows[0]
    assert "c.user_id <> $2" in wired.ran("COUNT(p.id) FILTER")[0][1]
    wired.on("FROM mw_projects p JOIN users", access_row("viewer"))
    assert await sales.workspace_campaigns(PROJECT, USER) == []


@pytest.mark.asyncio
async def test_campaign_edits_freeze_the_footer_while_messages_are_pending(wired):
    wired.on("UPDATE mw_sales_campaigns SET title", campaign(title="Clinics"))
    assert (
        await sales.update_campaign(CAMPAIGN, USER, CampaignPatch(title="Clinics"))
    )["title"] == "Clinics"
    wired.on("UPDATE mw_sales_campaigns SET footer", campaign(footer="New"))
    wired.on("SELECT COUNT(*)", 0)
    await sales.update_campaign(CAMPAIGN, USER, CampaignPatch(footer="New"))
    wired.on("SELECT COUNT(*)", 2)
    with pytest.raises(sales.SalesError, match="footer"):
        await sales.update_campaign(CAMPAIGN, USER, CampaignPatch(footer="New"))
    # The same footer is not a change, and an empty patch writes nothing.
    await sales.update_campaign(CAMPAIGN, USER, CampaignPatch(footer=FOOTER))
    wired.calls.clear()
    await sales.update_campaign(CAMPAIGN, USER, CampaignPatch())
    assert not wired.ran("UPDATE mw_sales_campaigns SET")


@pytest.mark.asyncio
async def test_deletes_wait_for_in_flight_messages(wired):
    wired.on("status = 'claimed'", 0)
    assert await sales.delete_campaign(CAMPAIGN, USER) == {"deleted": True}
    assert wired.ran("DELETE FROM mw_sales_campaigns")
    wired.on("status = 'claimed'", 1)
    with pytest.raises(sales.SalesError, match="in-progress"):
        await sales.delete_campaign(CAMPAIGN, USER)
    wired.on("status = 'claimed'", 0).on(
        "FROM mw_sales_campaigns", campaign(status="sending")
    )
    with pytest.raises(sales.SalesError, match="Pause"):
        await sales.delete_campaign(CAMPAIGN, USER)
    wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect())
    assert await sales.delete_prospect(CAMPAIGN, ITEM, USER) == {"deleted": True}
    for status in ("approved", "claimed"):
        wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect(status=status))
        with pytest.raises(sales.SalesError, match="Release"):
            await sales.delete_prospect(CAMPAIGN, ITEM, USER)


@pytest.mark.asyncio
async def test_opt_out_suppresses_the_address_in_every_campaign(wired):
    wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect(status="sent")).on(
        "SET status = 'opted_out', error = NULL WHERE id", prospect(status="opted_out")
    )
    out = await sales.opt_out(CAMPAIGN, ITEM, USER)
    assert out["status"] == "opted_out"
    assert wired.ran("INSERT INTO mw_sales_suppressions")[0][2] == (USER, "a@example.test")
    everywhere = wired.ran("FROM mw_sales_campaigns c WHERE p.campaign_id")[0]
    assert everywhere[2] == (USER, "a@example.test") and "<> 'claimed'" in everywhere[1]
    wired.calls.clear()
    wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect(email="", status="prospect"))
    await sales.opt_out(CAMPAIGN, ITEM, USER)
    assert not wired.ran("INSERT INTO mw_sales_suppressions")
    wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect(status="claimed"))
    with pytest.raises(sales.SalesError, match="being sent"):
        await sales.opt_out(CAMPAIGN, ITEM, USER)


@pytest.mark.asyncio
async def test_resolving_an_unconfirmed_message(wired):
    wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect())
    with pytest.raises(sales.SalesError, match="unconfirmed"):
        await sales.resolve_unknown(CAMPAIGN, ITEM, USER, "sent")
    wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect(status="unknown"))
    wired.on("SET status = 'sent'", prospect(status="sent")).on(
        "SET error = NULL, claimed_at = NULL", prospect(status="draft")
    )
    assert (await sales.resolve_unknown(CAMPAIGN, ITEM, USER, "sent"))["status"] == "sent"
    assert (await sales.resolve_unknown(CAMPAIGN, ITEM, USER, "not_sent"))["status"] == "draft"
    assert "THEN 'draft' ELSE 'prospect'" in wired.ran("claimed_at = NULL")[0][1]


@pytest.mark.asyncio
async def test_import_dedupes_skips_opted_out_people_and_enforces_campaign_total(wired):
    wired.on("array_agg(dedupe_key)", ["email:existing@example.test"]).on(
        "FROM mw_sales_suppressions", [{"email": "stop@example.test"}]
    )
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
                    "stop@example.test",
                ]
            ]
        ),
    )
    assert out == {"added": 1, "duplicates": 2, "suppressed": 1}
    inserted = json.loads(wired.ran("INSERT INTO mw_sales_prospects")[0][2][1])
    assert [p["email"] for p in inserted] == ["new@example.test"]
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
            ProspectPatch(body="edited", review_token=token(row)),
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
    wired.on("FROM mw_sales_suppressions", [{"email": "stop@example.test"}])
    with pytest.raises(sales.SalesError, match="asked not to be contacted"):
        await sales.patch_prospect(
            CAMPAIGN, ITEM, USER, ProspectPatch(email="stop@example.test")
        )
    # Re-saving the address it already has is not a new contact.
    await sales.patch_prospect(
        CAMPAIGN, ITEM, USER, ProspectPatch(email="a@example.test")
    )
    await sales.patch_prospect(CAMPAIGN, ITEM, USER, ProspectPatch())
    for status in ("approved", "opted_out"):
        wired.on("FROM mw_sales_prospects WHERE campaign_id", prospect(status=status))
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
    select = wired.ran("status IN ('prospect','draft','failed')")[0]
    assert select[2] == (CAMPAIGN, True)
    calls = wired.ran("UPDATE mw_sales_prospects SET subject")
    rendered = json.loads(calls[0][2][-1])
    assert rendered[0]["status"] == "draft" and rendered[1]["status"] == "prospect"
    wired.calls.clear()
    # The agent's path only fills prospects that have no draft yet.
    await sales.draft_template(
        CAMPAIGN, USER, Template(subject="Hi", body="Hi"), overwrite=False
    )
    select = wired.ran("status IN ('prospect','draft','failed')")[0]
    assert select[2] == (CAMPAIGN, False) and "subject = ''" in select[1]
    wired.calls.clear()
    wired.on(
        "status IN ('prospect','draft','failed')",
        [prospect(), prospect(name="Bea\nBcc: b")],
    )
    with pytest.raises(sales.SalesError, match="message for Bea"):
        await sales.draft_template(
            CAMPAIGN, USER, Template(subject="Hi {{name}}", body="Hi")
        )
    assert not wired.ran("UPDATE mw_sales_prospects SET subject")


def batch():
    return SendBatch(
        request_id=uuid4(),
        sender="owner@example.test",
        drafts=[{"id": ITEM, "review_token": token()}],
    )


@pytest.fixture
def approvals(wired, monkeypatch):
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
    # Fixtures use example.test; the reserved-domain refusal is tested on its own.
    monkeypatch.setattr(sales, "_is_reserved_test_domain", lambda _email: False)
    wired.on("id = ANY", [prospect()]).on("SELECT COUNT(*)", 0)
    return gmail, dispatch


@pytest.mark.asyncio
async def test_approval_is_exact_idempotent_and_sender_scoped(wired, approvals):
    gmail, dispatch = approvals
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
async def test_approval_needs_a_footer_and_contactable_real_recipients(
    wired, approvals, monkeypatch
):
    gmail, dispatch = approvals
    for footer in ("", f"Reply stop.\n{FOOTER_PLACEHOLDER}"):
        wired.on("FROM mw_sales_campaigns", campaign(footer=footer))
        with pytest.raises(sales.SalesError, match="footer"):
            await sales.approve_batch(CAMPAIGN, USER, batch(), gmail)
    wired.on("FROM mw_sales_campaigns", campaign())
    # A token computed before the footer existed no longer matches.
    stale = SendBatch(
        request_id=uuid4(),
        sender="owner@example.test",
        drafts=[{"id": ITEM, "review_token": sales.review_token(prospect())}],
    )
    with pytest.raises(sales.SalesError, match="changed"):
        await sales.approve_batch(CAMPAIGN, USER, stale, gmail)
    monkeypatch.setattr(sales, "_is_reserved_test_domain", lambda _email: True)
    with pytest.raises(sales.SalesError, match="Reserved"):
        await sales.approve_batch(CAMPAIGN, USER, batch(), gmail)
    monkeypatch.setattr(sales, "_is_reserved_test_domain", lambda _email: False)
    wired.on("FROM mw_sales_suppressions", [{"email": "a@example.test"}])
    with pytest.raises(sales.SalesError, match="asked not to be contacted"):
        await sales.approve_batch(CAMPAIGN, USER, batch(), gmail)
    assert not dispatch.called and not wired.ran("SET status = 'approved'")


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
async def test_stale_claims_report_how_many_expired(wired):
    wired.on("SET status = 'unknown'", "UPDATE 2")
    assert await sales._stale(wired, CAMPAIGN) == 2
    wired.on("SET status = 'unknown'", "UPDATE 0")
    assert await sales._stale(wired, CAMPAIGN) == 0


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
    monkeypatch.setattr(worker, "_campaign_wait", AsyncMock(return_value=0))
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


def refused(code, reason=None):
    body = {"error": {"errors": [{"reason": reason}]}} if reason else {}
    response = httpx.Response(
        code, json=body, request=httpx.Request("POST", "https://example.test/send")
    )
    return httpx.HTTPStatusError("refused", request=response.request, response=response)


# (Gmail behaviour, recipient outcome, campaign paused?, next countdown)
OUTCOMES = [
    ("none", "sent", False, 15),
    ("quota", "approved", False, worker.MAX_COUNTDOWN),
    ("minute", "approved", False, 60),
    ("429", "approved", False, worker.MAX_COUNTDOWN),
    ("403-daily", "approved", False, worker.MAX_COUNTDOWN),
    ("403", "approved", True, None),
    ("401", "approved", True, None),
    ("400", "failed", False, 15),
    ("invalid", "failed", False, 15),
    ("transport", "unknown", True, None),
    ("500", "unknown", True, None),
    ("no_id", "unknown", True, None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,outcome,paused,countdown", OUTCOMES)
async def test_delivery_classifies_every_outcome_and_pauses_when_uncertain(
    wired, delivery, failure, outcome, paused, countdown
):
    gmail, dispatch = delivery
    effects = {
        "quota": GmailSendRateLimited("Send rate limit: max 50 emails per hour"),
        "minute": GmailSendRateLimited("Send rate limit: max 5 emails per minute"),
        "429": refused(429),
        "403-daily": refused(403, "dailyLimitExceeded"),
        "403": refused(403, "insufficientPermissions"),
        "401": refused(401),
        "400": refused(400, "invalidArgument"),
        "invalid": ValueError("invalid"),
        "transport": httpx.ReadTimeout("lost ack"),
        "500": refused(500),
    }
    if failure in effects:
        gmail.send_email.side_effect = effects[failure]
    if failure == "no_id":
        gmail.send_email.return_value = {}
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert wired.ran("SET status = 'claimed'")
    assert wired.ran("SET status = $2::text")[0][2][1] == outcome
    # The reviewed footer goes out with the reviewed body.
    assert gmail.send_email.call_args.kwargs == {
        "to": "a@example.test",
        "subject": "Hello Ana",
        "body": f"Hi Ana\n\n{FOOTER}",
    }
    assert bool(wired.ran("SET status = 'paused'")) == paused
    if paused:
        assert not dispatch.called
    else:
        assert dispatch.call_args.kwargs["countdown"] == countdown


def test_refusals_are_classified_by_reason():
    assert worker._refusal(refused(429).response) == "quota"
    assert worker._refusal(refused(403, "userRateLimitExceeded").response) == "quota"
    assert worker._refusal(refused(403).response) == "account"
    assert worker._refusal(refused(401).response) == "account"
    assert worker._refusal(refused(400).response) == "message"
    broken = httpx.Response(403, content=b"<html>", request=httpx.Request("POST", "https://example.test"))
    assert worker._refusal(broken) == "account"


@pytest.mark.asyncio
async def test_worker_stale_token_revoked_access_and_mailbox_switch(wired, delivery):
    gmail, dispatch = delivery
    await worker.deliver_one(CAMPAIGN, uuid4(), gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and not dispatch.called
    wired.on("FROM mw_projects p JOIN users", None)
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert "Workspace access changed" in wired.ran("SET status = 'paused'")[0][2][1]
    assert not gmail.send_email.called
    wired.calls.clear()
    wired.on("FROM mw_projects p JOIN users", access_row())
    gmail.get_status.return_value = {"connected": True, "email": "other@example.test"}
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert (
        wired.ran("SET status = 'approved', claimed_at = NULL")
        and not gmail.send_email.called
    )
    wired.calls.clear()
    gmail.get_status.side_effect = RuntimeError("network")
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert "Gmail is unavailable" in wired.ran("SET status = 'paused'")[0][2][1]


@pytest.mark.asyncio
async def test_an_interrupted_claim_pauses_the_queue(wired, delivery):
    gmail, dispatch = delivery
    wired.on("SET status = 'unknown'", "UPDATE 1")
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert wired.ran("SET status = 'paused'") and not gmail.send_email.called
    assert not wired.ran("SET status = 'claimed'") and not dispatch.called


@pytest.mark.asyncio
async def test_opted_out_recipients_are_dropped_before_any_claim(wired, delivery):
    gmail, _ = delivery
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    drop = wired.ran("FROM mw_sales_suppressions s")[0]
    assert drop[2] == (CAMPAIGN, USER) and "SET status = 'opted_out'" in drop[1]
    calls = [c[1] for c in wired.calls]
    assert calls.index(drop[1]) < calls.index(wired.ran("SET status = 'claimed'")[0][1])


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
    # A long wait is split into countdowns below the broker's visibility timeout.
    wired.on(
        "FROM mw_sales_campaigns",
        campaign(
            status="sending",
            next_attempt_at=datetime.now(timezone.utc) + timedelta(hours=2),
        ),
    )
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert dispatch.call_args.kwargs["countdown"] == worker.MAX_COUNTDOWN
    wired.on("FROM mw_sales_campaigns", campaign(status="sending")).on(
        "SELECT EXISTS", True
    )
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and dispatch.call_args.kwargs["countdown"] == 60
    wired.on("SELECT EXISTS", False).on("status = 'approved' ORDER", None)
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert wired.ran("status = 'complete'")


@pytest.mark.asyncio
async def test_campaigns_leave_gmail_room_for_the_persons_own_email(
    wired, delivery, monkeypatch
):
    gmail, dispatch = delivery
    monkeypatch.setattr(worker, "_campaign_wait", AsyncMock(return_value=900))
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and not wired.ran("SET status = 'claimed'")
    waiting = wired.ran("make_interval")[0]
    assert waiting[2] == (CAMPAIGN, 900.0, worker.WAITING_FOR_CAPACITY)
    assert dispatch.call_args.kwargs["countdown"] == 901


@pytest.mark.asyncio
async def test_campaign_share_reads_the_shared_counters(monkeypatch):
    from app.core.services import redis_cache

    states = {
        "gmail_send_3600s": {"used": 35, "resets_in_seconds": 600},
        "gmail_recipients_86400s": {"used": 10, "resets_in_seconds": 80000},
    }

    async def state(_key, action, _limit, _window):
        return states[action]

    monkeypatch.setattr(redis_cache, "get_rate_limit_state", state)
    assert await worker._campaign_wait(USER) == 600
    states["gmail_send_3600s"]["used"] = 34
    assert await worker._campaign_wait(USER) == 0
    states["gmail_recipients_86400s"] = {"used": 150, "resets_in_seconds": 0}
    assert await worker._campaign_wait(USER) == 86400

    async def unavailable(*_args):
        raise RuntimeError("redis")

    monkeypatch.setattr(redis_cache, "get_rate_limit_state", unavailable)
    assert await worker._campaign_wait(USER) == 0


@pytest.mark.asyncio
async def test_a_reserved_recipient_fails_alone_and_the_batch_continues(
    wired, delivery, monkeypatch
):
    gmail, dispatch = delivery
    monkeypatch.setattr(worker, "_is_reserved_test_domain", lambda _email: True)
    await worker.deliver_one(CAMPAIGN, TOKEN, gmail_factory=lambda _id: gmail)
    assert not gmail.send_email.called and wired.ran("Reserved test address")
    assert not wired.ran("status = 'paused'") and not wired.ran("SET status = 'claimed'")
    assert dispatch.call_args.kwargs["countdown"] == 1


@pytest.mark.asyncio
async def test_worker_start_restarts_sending_queues_under_a_new_token(
    wired, monkeypatch
):
    dispatch = AsyncMock()
    monkeypatch.setattr(sales, "dispatch", dispatch)
    other = uuid4()
    wired.on("WHERE status = 'sending'", [{"id": CAMPAIGN}, {"id": other}]).on(
        "SELECT status FROM mw_sales_campaigns", {"status": "sending"}
    )
    await worker.reconcile()
    rotated = wired.ran("SET dispatch_token = $2")
    assert [c[2][0] for c in rotated] == [CAMPAIGN, other]
    assert [c.args[1] for c in dispatch.await_args_list] == [c[2][1] for c in rotated]
    # An interrupted claim pauses instead of restarting.
    wired.calls.clear()
    dispatch.reset_mock()
    wired.on("SET status = 'unknown'", "UPDATE 1")
    await worker.reconcile()
    assert len(wired.ran("SET status = 'paused'")) == 2 and not dispatch.called
    # Campaigns that stopped sending meanwhile, and a dead broker, are skipped.
    wired.on("SET status = 'unknown'", "UPDATE 0").on(
        "SELECT status FROM mw_sales_campaigns", {"status": "paused"}
    )
    await worker.reconcile()
    assert not dispatch.called
    wired.on("SELECT status FROM mw_sales_campaigns", {"status": "sending"})
    dispatch.side_effect = sales.SalesError("queue down", 503)
    await worker.reconcile()
    assert dispatch.await_count == 2


def test_worker_start_queues_the_sales_reconcile():
    import inspect
    from app.workers import celery_app as app_module

    assert "reconcile_sales_campaigns.delay()" in inspect.getsource(
        app_module.on_worker_ready
    )
    assert (
        worker.reconcile_sales_campaigns.name
        == "app.workers.tasks.sales_campaign.reconcile_sales_campaigns"
    )
