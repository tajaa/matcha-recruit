"""Magazine emails ("issues" in cappemag04's tables): a published story
emailed to the magazine's followers. The owner's "Emails" page; an issue in
print — a numbered book with a cover and contents — is `routes/issues.py`.

  * `POST /sites/{id}/posts/{post_id}/issue` — send it. An issue is a
    campaign (`kind='issue'`), so it shares the newsletter's send budget
    (`services/campaigns.py`: three sends and 5,000 people a day per account)
    and its worker (`workers/tasks/cappe_campaign_send.py`). A story goes out
    once.
  * `POST …/issue/test` — the same email to the owner alone, ten a day.
  * `GET /sites/{id}/issues` — what has gone out.

The email is our template (`services/magazine/issue_email.py`), built here
from the published story; a paid story's paid part is never in it.
"""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeIssue, CappeIssueCreate
from ..services.campaigns import SENDS_PER_DAY, send_cap_problem
from ..services.common import site_public_origin
from ..services.magazine import issue_email
from ..services.magazine import reader as mag_reader
from ..services.magazine.magazines import live_magazine
from ._shared import get_owned_site

logger = logging.getLogger(__name__)

router = APIRouter()

TESTS_PER_DAY = 10
_ISSUE_COLS = ("c.id, c.story_id, p.title AS story_title, c.subject, c.status, c.include_body, "
               "c.recipient_count, c.failed_count, c.sent_at, c.created_at")


async def _material(conn, site_id: UUID, post_id: UUID, account: CappeAccount) -> dict[str, Any]:
    site = await get_owned_site(conn, site_id, account.id)
    mag = await live_magazine(conn, site)
    if not mag:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Turn on your magazine, on a plan that includes magazines, to send issues.")
    post = await mag_reader.live_story(conn, site_id, post_id=post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Publish the story first; an issue links to it.")
    origin = site_public_origin(site)
    if not origin:
        # Every link in an issue (the story, unsubscribe) needs the site's own address.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Give your site its address first; an issue links to it.")
    return {"site": site, "mag": mag, "post": post, "assets": await mag_reader.story_assets(conn, site_id, post),
            "origin": origin}


def _build(m: dict[str, Any], body: CappeIssueCreate) -> tuple[str, str, str]:
    return issue_email.build_issue(
        site_name=m["site"]["name"], mag=m["mag"], post=m["post"], assets=m["assets"], origin=m["origin"],
        include_body=body.include_body, subject=(body.subject or "").strip() or None,
    )


_ALREADY_SENT = "This story has already gone to your followers."


async def _already_sent(conn, post_id: UUID) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_campaigns WHERE story_id = $1 AND kind = 'issue' AND status IN ('sending', 'sent')",
        post_id,
    ))


@router.get("/sites/{site_id}/issues", response_model=list[CappeIssue])
async def list_issues(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"""SELECT {_ISSUE_COLS} FROM cappe_campaigns c LEFT JOIN cappe_posts p ON p.id = c.story_id
                 WHERE c.site_id = $1 AND c.kind = 'issue' ORDER BY c.created_at DESC LIMIT 100""",
            site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/posts/{post_id}/issue", response_model=CappeIssue,
             status_code=status.HTTP_202_ACCEPTED)
async def send_issue(site_id: UUID, post_id: UUID, body: CappeIssueCreate,
                     account: CappeAccount = Depends(require_cappe_account)):
    """Email the story to everyone who follows the magazine."""
    async with get_connection() as conn:
        m = await _material(conn, site_id, post_id, account)
        if await _already_sent(conn, post_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_ALREADY_SENT)
        if not await conn.fetchval(
            "SELECT COUNT(*) FROM cappe_subscribers WHERE site_id = $1 AND status = 'subscribed'", site_id,
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="No one follows your magazine yet. Share it, and send the next one.")
        problem = await send_cap_problem(conn, account.id, site_id)
        if problem:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=problem)
    await check_rate_limit(str(account.id), "cappe_campaign_send", SENDS_PER_DAY, 86_400)
    subject, html, text = _build(m, body)
    async with get_connection() as conn, conn.transaction():
        # Checked again under a per-story lock: two Sends at once (two tabs, a
        # retry) can't both insert, so a story goes out once.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"cappe_issue:{post_id}")
        if await _already_sent(conn, post_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_ALREADY_SENT)
        row = await conn.fetchrow(
            """INSERT INTO cappe_campaigns (site_id, subject, body_html, body_text, from_name, status, kind,
                                            story_id, include_body)
               VALUES ($1, $2, $3, $4, $5, 'sending', 'issue', $6, $7)
               RETURNING id, story_id, subject, status, include_body, recipient_count, failed_count,
                         sent_at, created_at""",
            site_id, subject, html, text, m["mag"].get("name") or m["site"]["name"], post_id, body.include_body,
        )
    try:
        from app.workers.tasks.cappe_campaign_send import run_cappe_campaign_send

        run_cappe_campaign_send.delay(str(row["id"]))
    except Exception as exc:  # noqa: BLE001 — broker down: take it back so the writer can send again
        logger.warning("issue dispatch failed for %s: %s", row["id"], type(exc).__name__)
        async with get_connection() as conn:
            await conn.execute("DELETE FROM cappe_campaigns WHERE id = $1 AND status = 'sending'", row["id"])
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Sending is temporarily unavailable — please try again shortly.") from exc
    return {**dict(row), "story_title": m["post"].get("title")}


@router.post("/sites/{site_id}/posts/{post_id}/issue/test")
async def send_test_issue(site_id: UUID, post_id: UUID, body: CappeIssueCreate,
                          account: CappeAccount = Depends(require_cappe_account)):
    """The issue as followers will get it, to the owner's own address only."""
    async with get_connection() as conn:
        m = await _material(conn, site_id, post_id, account)
    await check_rate_limit(str(account.id), "cappe_issue_test", TESTS_PER_DAY, 86_400)
    subject, html, text = _build(m, body)
    from app.core.services.email import EmailService

    ok = await EmailService().send_email_with_fallback(
        to_email=account.email, to_name=account.name, subject=f"[Test] {subject}",
        html_content=issue_email.personalize(html, f"{m['origin']}/unsubscribe/test", html=True),
        text_content=issue_email.personalize(text, f"{m['origin']}/unsubscribe/test", html=False),
        from_name=m["mag"].get("name") or m["site"]["name"],
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The test email didn't go. Try again.")
    return {"ok": True, "to": account.email}
