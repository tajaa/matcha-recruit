"""A job's first message into the person's Gmail drafts, and what the job
remembers about it."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.matcha.routes.matcha_work import job_search as routes
from app.matcha.services.matcha_work import gmail_service
from app.matcha.services.matcha_work.job_search import service
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import LEAD, NOW, SEARCH, USER, lead_row, search_row

OUTREACH = {"to_email": "ceo@backpack.example.com", "subject": "COFO role", "body": "Hi Jane,\n\nI saw the role."}


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn().on("FROM mw_job_searches s", search_row())
    monkeypatch.setattr(service, "connection_or_direct", connection(conn))
    return conn


@pytest.fixture
def gmail(monkeypatch):
    fake = SimpleNamespace(
        load_token=AsyncMock(), is_configured=True,
        get_draft=AsyncMock(return_value={"id": "r-1", "to": "x@example.com", "subject": "Old"}),
        create_draft=AsyncMock(return_value={"id": "r-2"}),
    )
    monkeypatch.setattr(gmail_service, "GmailService", lambda user_id: fake)
    return fake


def _lead(**over):
    return lead_row(**{"approach": json.dumps({"outreach": OUTREACH}), "email_draft_id": None,
                       "email_drafted_at": None, "email_sent_at": None, **over})


def _missing(status=404):
    request = httpx.Request("GET", "https://gmail.googleapis.com/x")
    return httpx.HTTPStatusError("x", request=request, response=httpx.Response(status, request=request))


@pytest.mark.asyncio
async def test_a_jobs_first_message_becomes_a_gmail_draft(conn, gmail):
    conn.on("FROM mw_job_leads WHERE id = $1", _lead())
    conn.on("UPDATE mw_job_leads", _lead(email_draft_id="r-2", email_drafted_at=NOW))
    out = await service.draft_email(SEARCH, LEAD, USER)
    assert out["created"] is True and out["draft_id"] == "r-2"
    assert gmail.create_draft.await_args.kwargs == {
        "to": "ceo@backpack.example.com", "subject": "COFO role", "body": OUTREACH["body"]}
    [update] = conn.ran("UPDATE mw_job_leads")
    assert update[2] == (LEAD, SEARCH, "r-2") and "email_sent_at = NULL" in update[1]
    assert out["lead"]["email_draft_id"] == "r-2" and out["lead"]["email_drafted_at"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_asking_again_returns_the_draft_while_it_is_in_gmail(conn, gmail):
    conn.on("FROM mw_job_leads WHERE id = $1", _lead(email_draft_id="r-1", email_drafted_at=NOW))
    out = await service.draft_email(SEARCH, LEAD, USER)
    assert out["created"] is False and out["draft_id"] == "r-1" and not gmail.create_draft.await_count
    # Sent or deleted in Gmail itself: a new one.
    gmail.get_draft.side_effect = _missing()
    conn.on("UPDATE mw_job_leads", _lead(email_draft_id="r-2"))
    assert (await service.draft_email(SEARCH, LEAD, USER))["created"] is True
    # A stored id Gmail would refuse outright: a new one too.
    gmail.get_draft.side_effect = ValueError("Invalid draft id")
    assert (await service.draft_email(SEARCH, LEAD, USER))["created"] is True
    # Any other Gmail failure is not a reason to duplicate the draft.
    gmail.get_draft.side_effect = _missing(500)
    with pytest.raises(httpx.HTTPStatusError):
        await service.draft_email(SEARCH, LEAD, USER)
    # Once sent, asking again starts a new draft.
    gmail.get_draft.reset_mock()
    gmail.get_draft.side_effect = None
    conn.on("FROM mw_job_leads WHERE id = $1", _lead(email_draft_id="r-1", email_sent_at=NOW))
    assert (await service.draft_email(SEARCH, LEAD, USER))["created"] is True and not gmail.get_draft.await_count


@pytest.mark.asyncio
async def test_edit_draft_never_makes_one(conn, gmail):
    waiting = _lead(email_draft_id="r-1", email_drafted_at=NOW)
    conn.on("FROM mw_job_leads WHERE id = $1", waiting)
    out = await service.draft_email(SEARCH, LEAD, USER, existing_only=True)
    assert out["created"] is False and out["draft_id"] == "r-1"
    # Sent or deleted in Gmail itself: forgotten on the job and refused, so a
    # new draft is the person's own click. Nothing is made or sent.
    gmail.get_draft.side_effect = _missing()
    conn.on("UPDATE mw_job_leads", _lead())
    with pytest.raises(service.JobSearchError) as exc:
        await service.draft_email(SEARCH, LEAD, USER, existing_only=True)
    assert exc.value.code == 409 and exc.value.detail["code"] == "email_draft_missing"
    assert exc.value.detail["lead"]["email_draft_id"] is None
    [update] = conn.ran("UPDATE mw_job_leads")
    assert update[2] == (LEAD, SEARCH, "r-1") and "SET email_draft_id = NULL" in update[1]
    assert "AND email_draft_id = $3" in update[1]
    # A new draft made meanwhile isn't forgotten: the job comes back as it is.
    conn.on("UPDATE mw_job_leads", None)
    conn.on("SELECT * FROM mw_job_leads WHERE id = $1", _lead(email_draft_id="r-9"))
    with pytest.raises(service.JobSearchError) as exc:
        await service.draft_email(SEARCH, LEAD, USER, existing_only=True)
    assert exc.value.detail["lead"]["email_draft_id"] == "r-9"
    # Already sent, or never drafted: refused as it is, with Gmail not asked.
    gmail.get_draft.reset_mock()
    for row in (_lead(email_draft_id="r-1", email_sent_at=NOW), _lead()):
        conn.on("FROM mw_job_leads WHERE id = $1", row)
        with pytest.raises(service.JobSearchError) as exc:
            await service.draft_email(SEARCH, LEAD, USER, existing_only=True)
        assert exc.value.detail["code"] == "email_draft_missing"
    assert not gmail.get_draft.await_count and not gmail.create_draft.await_count
    assert len(conn.ran("UPDATE mw_job_leads")) == 2


@pytest.mark.asyncio
async def test_no_message_no_gmail_or_no_job_is_said_plainly(conn, gmail):
    conn.on("FROM mw_job_leads WHERE id = $1", None)
    with pytest.raises(service.JobSearchError) as exc:
        await service.draft_email(SEARCH, LEAD, USER)
    assert exc.value.code == 404
    conn.on("FROM mw_job_leads WHERE id = $1", lead_row(approach="{}"))
    with pytest.raises(service.JobSearchError, match="Draft its approach first") as exc:
        await service.draft_email(SEARCH, LEAD, USER)
    assert exc.value.code == 409
    conn.on("FROM mw_job_leads WHERE id = $1", _lead())
    gmail.is_configured = False
    with pytest.raises(service.JobSearchError) as exc:
        await service.draft_email(SEARCH, LEAD, USER)
    assert exc.value.code == 409 and exc.value.detail["code"] == "email_not_connected"


@pytest.mark.asyncio
async def test_a_bad_address_is_left_out_and_a_missing_subject_is_made(conn, gmail):
    approach = {"outreach": {"to_email": "the CEO (LinkedIn)", "subject": "", "body": "Hello"}}
    conn.on("FROM mw_job_leads WHERE id = $1", lead_row(approach=json.dumps(approach), email_draft_id=None,
                                                         email_sent_at=None))
    conn.on("UPDATE mw_job_leads", _lead(email_draft_id="r-2"))
    out = await service.draft_email(SEARCH, LEAD, USER)
    assert out["to"] == "" and out["subject"] == "COO at Acme"
    assert gmail.create_draft.await_args.kwargs["to"] == ""


@pytest.mark.asyncio
async def test_email_notes_a_sent_or_deleted_draft_on_its_job(conn):
    await service.note_email_draft(USER, "r-1", sent=True)
    [sent] = conn.ran("UPDATE mw_job_leads")
    assert sent[2] == (USER, "r-1", True) and "WHERE user_id = $1 AND email_draft_id = $2" in sent[1]
    await service.note_email_draft(USER, "r-1", sent=False)
    assert conn.ran("UPDATE mw_job_leads")[1][2][2] is False
    conn.on("UPDATE mw_job_leads", RuntimeError("db down"))
    await service.note_email_draft(USER, "r-1", sent=True)  # never raises


def test_a_lead_carries_its_email_state():
    view = service.lead_summary(lead_row(email_draft_id="r-1", email_drafted_at=NOW, email_sent_at=None))
    assert view["email_draft_id"] == "r-1" and view["email_drafted_at"] == NOW.isoformat()
    assert view["email_sent_at"] is None
    assert service.lead_summary(lead_row())["email_draft_id"] is None


@pytest.mark.asyncio
async def test_the_route_passes_the_caller(monkeypatch):
    drafted = AsyncMock(return_value={"draft_id": "r-1"})
    monkeypatch.setattr(routes.service, "draft_email", drafted)
    caller = SimpleNamespace(id=uuid4())
    assert await routes.draft_job_email(SEARCH, LEAD, None, caller) == {"draft_id": "r-1"}
    assert drafted.await_args.args == (SEARCH, LEAD, caller.id)
    assert drafted.await_args.kwargs == {"existing_only": False}
    await routes.draft_job_email(SEARCH, LEAD, routes.EmailDraftRequest(existing_only=True), caller)
    assert drafted.await_args.kwargs == {"existing_only": True}
