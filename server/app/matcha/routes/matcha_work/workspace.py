"""Cross-project workspace surface: open-tasks + recent-activity feeds for
Home, the per-user Gmail email agent, entitlements/usage summary.

The global (non-project) manual task board moved to
routes/dashboard/tasks.py (2026-07-28) -- it no longer holds the third
order-sensitive route pair this module used to carry.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import asyncio
import logging
import re
import secrets
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.core.services.redis_cache import get_redis_cache
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.matcha_work.matcha_work import UsageSummaryResponse
from app.matcha.services.matcha_work import matcha_work_document as doc_svc

logger = logging.getLogger(__name__)
router = APIRouter()
oauth_callback_router = APIRouter()

GMAIL_OAUTH_STATE_TTL_SECONDS = 30 * 60
_GMAIL_OAUTH_STATE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_GMAIL_OAUTH_STATE_KEY_PREFIX = "gmail_oauth_state:"


class _GmailOAuthStateStoreUnavailable(RuntimeError):
    """Raised when a secure, one-time OAuth state cannot be issued or consumed."""


def _gmail_oauth_state_key(state: str) -> str:
    return f"{_GMAIL_OAUTH_STATE_KEY_PREFIX}{state}"


def _validate_gmail_oauth_state_format(state: str) -> None:
    if not _GMAIL_OAUTH_STATE_PATTERN.fullmatch(state):
        raise ValueError("Invalid or expired OAuth state")


async def _issue_gmail_oauth_state(user_id: UUID) -> str:
    """Persist an opaque user binding that can be consumed exactly once."""
    redis = get_redis_cache()
    if redis is None:
        raise _GmailOAuthStateStoreUnavailable("OAuth state store is unavailable")

    # SET NX handles the practically impossible random collision without ever
    # replacing a still-live state.
    for _attempt in range(3):
        state = secrets.token_urlsafe(32)
        try:
            stored = await redis.set(
                _gmail_oauth_state_key(state),
                str(user_id),
                ex=GMAIL_OAUTH_STATE_TTL_SECONDS,
                nx=True,
            )
        except Exception as exc:
            raise _GmailOAuthStateStoreUnavailable(
                "OAuth state store is unavailable"
            ) from exc
        if stored:
            return state
    raise _GmailOAuthStateStoreUnavailable("Failed to allocate OAuth state")


async def _consume_gmail_oauth_state(state: str) -> UUID:
    """Atomically consume an opaque state and return its initiating user."""
    _validate_gmail_oauth_state_format(state)
    redis = get_redis_cache()
    if redis is None:
        raise _GmailOAuthStateStoreUnavailable("OAuth state store is unavailable")
    try:
        user_id = await redis.getdel(_gmail_oauth_state_key(state))
    except Exception as exc:
        raise _GmailOAuthStateStoreUnavailable(
            "OAuth state store is unavailable"
        ) from exc
    if user_id is None:
        raise ValueError("Invalid or expired OAuth state")
    try:
        return UUID(user_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Invalid or expired OAuth state") from exc


async def _connected_gmail(current_user: CurrentUser):
    """The caller's own GmailService with its token loaded, or 400. Mail is
    always read and sent as the signed-in user — there is no shared mailbox."""
    from app.matcha.services.matcha_work.gmail_service import GmailService

    gmail = GmailService(current_user.id)
    await gmail.load_token()
    if not gmail.is_configured:
        raise HTTPException(status_code=400, detail="Gmail not connected")
    return gmail


async def _require_email_ai(current_user: CurrentUser) -> None:
    """Email fetch/read/send stay free (non-AI); every AI action is Lite+."""
    from app.matcha.services.billing import entitlements_service

    await entitlements_service.require_plan(
        current_user.id, entitlements_service.PLAN_LITE, "email_ai"
    )


_GMAIL_MESSAGE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")


def _is_message_id(value) -> bool:
    """Gmail message ids are opaque url-safe tokens. Anything else (a slash,
    `..`, a query string) would splice into the Gmail API path and reach a
    different endpoint of the caller's mailbox, so it is refused up front."""
    return isinstance(value, str) and bool(_GMAIL_MESSAGE_ID_RE.fullmatch(value))


def _require_message_id(value) -> str:
    if not _is_message_id(value):
        raise HTTPException(status_code=400, detail="email_id must be a Gmail message id")
    return value


def _reply_subject(subject: str | None) -> str:
    subject = re.sub(r"[\r\n]+", " ", subject or "").strip()
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


_BARE_ADDRESS_RE = re.compile(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[^@\s,;<>\"]+")


def _reply_recipient(from_header: str | None) -> str | None:
    """The one bare address a reply goes to, parsed out of the original's
    From header, or None when it has no usable one. The header is written by
    the sender: a folded CR/LF would make `_build_raw` refuse the draft (a
    sender-chosen 500), and `Alice <a@x.test>, b@y.test` would become a
    two-recipient To: line on the saved draft."""
    from email.utils import getaddresses

    for _name, addr in getaddresses([from_header or ""]):
        addr = addr.strip()
        if _BARE_ADDRESS_RE.fullmatch(addr):
            return addr
    return None


def _clean_message_id_header(value) -> str | None:
    """The original's Message-ID when it is one (`<…>`, no whitespace). A
    malformed value is dropped, not refused: Gmail's threadId still keeps the
    reply in its conversation."""
    if isinstance(value, str) and re.fullmatch(r"<[^<>\s]{1,995}>", value.strip()):
        return value.strip()
    return None


def _optional_str(body: dict, key: str) -> str | None:
    value = body.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{key} must be a string")
    return value


async def _get_message_or_404(gmail, email_id: str, *, include_html: bool = False) -> dict:
    """Gmail answers a stale id (a message deleted since the list loaded) with
    400/404. That is "not found" for the caller, not a server error."""
    try:
        return await gmail.get_message(email_id, include_html=include_html)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 404):
            raise HTTPException(status_code=404, detail="Message not found") from exc
        raise


@router.get("/tasks/open")
async def list_open_tasks_endpoint(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Open work assigned to the current user, for the Home "Assigned to me" card.

    Strictly the current user's own work, scoped to their company:
    - top-level tasks (`mw_tasks`) where `assigned_to = me` and the task is
      still open (status not completed/cancelled), and
    - checklist subtasks (`mw_subtasks`) where `assigned_to = me`, not yet done,
      and whose parent task is still open.

    Returns one merged list. Subtask rows carry `is_subtask=True` plus
    `parent_task_id`/`parent_title`; they reuse `title`/`project_title` and
    fill the task-only fields (priority/status/due_date/progress_note) with
    neutral defaults so the shared `MWOpenTask` shape still decodes. Tasks come
    first (priority then due date), subtasks after (most-recent first) — they're
    lower-signal checklist items.
    """
    # Scope is `assigned_to = me`, NOT company_id. matcha-work supports
    # cross-tenant project collaborators (a task assigned to me can live in
    # another company's project), admins/multi-company users resolve to a
    # single default company, and personal users have no company at all — all
    # three lose their assigned work if we gate on a resolved company_id.
    # `assigned_to = current_user.id` is the correct (and sufficient) boundary
    # for this personal Home view.
    async with get_connection() as conn:
        task_rows = await conn.fetch(
            """
            SELECT t.id, t.project_id, t.title, t.priority, t.status,
                   t.due_date, t.progress_note, t.assigned_to, t.created_by,
                   t.updated_at,
                   p.title AS project_title, p.project_type
            FROM mw_tasks t
            LEFT JOIN mw_projects p ON p.id = t.project_id
            WHERE t.assigned_to = $1
              AND t.status NOT IN ('completed', 'cancelled')
              AND t.project_id IS NOT NULL
            ORDER BY
                CASE t.priority
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
                END,
                t.due_date NULLS LAST,
                t.updated_at DESC
            LIMIT 50
            """,
            current_user.id,
        )
        subtask_rows = await conn.fetch(
            """
            SELECT s.id, s.project_id, s.title, s.assigned_to, s.created_by,
                   s.updated_at,
                   s.task_id AS parent_task_id, pt.title AS parent_title,
                   p.title AS project_title, p.project_type
            FROM mw_subtasks s
            JOIN mw_tasks pt ON pt.id = s.task_id
            LEFT JOIN mw_projects p ON p.id = s.project_id
            WHERE s.assigned_to = $1
              AND s.is_done = false
              AND pt.status NOT IN ('completed', 'cancelled')
            ORDER BY s.updated_at DESC
            LIMIT 50
            """,
            current_user.id,
        )

    out = []
    for r in task_rows:
        d = dict(r)
        for k in ("id", "project_id", "assigned_to", "created_by"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        if d.get("due_date") is not None:
            d["due_date"] = d["due_date"].isoformat()
        if d.get("updated_at") is not None:
            d["updated_at"] = d["updated_at"].isoformat()
        d["is_subtask"] = False
        out.append(d)
    for r in subtask_rows:
        d = dict(r)
        for k in ("id", "project_id", "assigned_to", "created_by", "parent_task_id"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        if d.get("updated_at") is not None:
            d["updated_at"] = d["updated_at"].isoformat()
        # Fill the task-only fields the shared MWOpenTask shape expects.
        d["priority"] = ""
        d["status"] = "pending"
        d["due_date"] = None
        d["progress_note"] = None
        d["is_subtask"] = True
        out.append(d)
    return out

@router.get("/activity/recent")
async def list_recent_activity_endpoint(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Recent activity feed across projects, tasks, threads in this company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            WITH recent AS (
                SELECT 'project'::text AS kind,
                       p.id::text AS ref_id,
                       p.id::text AS project_id,
                       p.title,
                       p.project_type,
                       p.updated_at
                FROM mw_projects p
                WHERE p.company_id = $1
                  AND p.updated_at > NOW() - INTERVAL '14 days'
                ORDER BY p.updated_at DESC
                LIMIT 30
            ), recent_tasks AS (
                SELECT 'task'::text AS kind,
                       t.id::text AS ref_id,
                       t.project_id::text AS project_id,
                       t.title,
                       NULL::text AS project_type,
                       t.updated_at
                FROM mw_tasks t
                WHERE t.company_id = $1
                  AND t.project_id IS NOT NULL
                  AND t.updated_at > NOW() - INTERVAL '14 days'
                ORDER BY t.updated_at DESC
                LIMIT 30
            ), recent_threads AS (
                SELECT 'thread'::text AS kind,
                       th.id::text AS ref_id,
                       NULL::text AS project_id,
                       th.title,
                       NULL::text AS project_type,
                       th.updated_at
                FROM mw_threads th
                WHERE th.company_id = $1
                  AND th.surface <> 'schedule_assistant'
                  AND th.updated_at > NOW() - INTERVAL '14 days'
                ORDER BY th.updated_at DESC
                LIMIT 30
            ), recent_journals AS (
                -- Surface the parent journal for any entry written or edited
                -- in the last 14 days. Title comes from the journal so the
                -- dashboard row links somewhere navigable; the entry timestamp
                -- drives ordering so silent journals don't crowd the list.
                SELECT 'journal'::text AS kind,
                       j.id::text AS ref_id,
                       NULL::text AS project_id,
                       j.title,
                       NULL::text AS project_type,
                       MAX(GREATEST(j.updated_at, e.updated_at)) AS updated_at
                FROM mw_journals j
                LEFT JOIN mw_journal_entries e ON e.journal_id = j.id
                WHERE j.company_id = $1
                  AND j.status = 'active'
                  -- Journals are PERSONAL (unlike projects/tasks/threads which
                  -- are company-shared). Scope to the caller's own journals +
                  -- ones explicitly shared with them, or coworker notes leak
                  -- into the dashboard feed.
                  AND (
                    j.created_by = $2
                    OR EXISTS(
                        SELECT 1 FROM mw_journal_collaborators jc
                        WHERE jc.journal_id = j.id AND jc.user_id = $2
                          AND jc.status = 'active'
                    )
                  )
                  AND (
                    j.updated_at > NOW() - INTERVAL '14 days'
                    OR e.updated_at > NOW() - INTERVAL '14 days'
                  )
                GROUP BY j.id, j.title
                ORDER BY updated_at DESC
                LIMIT 30
            )
            SELECT * FROM recent
            UNION ALL SELECT * FROM recent_tasks
            UNION ALL SELECT * FROM recent_threads
            UNION ALL SELECT * FROM recent_journals
            ORDER BY updated_at DESC
            LIMIT 25
            """,
            company_id,
            current_user.id,
        )
    out = []
    for r in rows:
        d = dict(r)
        if d.get("updated_at") is not None:
            d["updated_at"] = d["updated_at"].isoformat()
        out.append(d)
    return out

@router.get("/agent/email/status")
async def agent_email_status(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Check if the current user has Gmail connected."""
    from app.matcha.services.matcha_work.gmail_service import GmailService
    gmail = GmailService(current_user.id)
    # The client caps a card's email picker from this, so the limit lives in
    # one place (the snapshot route enforces it).
    return {**(await gmail.get_status()), "snapshot_max_emails": SNAPSHOT_MAX_EMAILS}


@router.post("/agent/email/connect")
async def agent_email_connect(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Start Google OAuth flow. Returns an auth_url to open in a popup."""
    from app.matcha.services.matcha_work.gmail_service import get_oauth_credentials, GMAIL_SCOPES
    import urllib.parse

    creds = get_oauth_credentials()
    if not creds:
        raise HTTPException(status_code=500, detail="Google OAuth credentials not configured on the server")

    settings = get_settings()
    redirect_uri = f"{settings.app_base_url}/api/matcha-work/agent/email/callback"

    # The system-browser callback has no Matcha bearer token. Carry only an
    # opaque random handle; Redis holds the user binding and consumes it once.
    try:
        state = await _issue_gmail_oauth_state(current_user.id)
    except _GmailOAuthStateStoreUnavailable as exc:
        logger.error("Cannot issue Gmail OAuth state: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Gmail connection is temporarily unavailable. Please try again.",
        ) from exc

    params = {
        "client_id": creds["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url}


@oauth_callback_router.get("/agent/email/callback", include_in_schema=False)
async def agent_email_callback(
    state: str = Query(...),
    code: str | None = Query(None),
    error: str | None = Query(None),
):
    """OAuth callback — exchange code for tokens, store encrypted in DB, close popup."""
    from app.matcha.services.matcha_work.gmail_service import GmailService, get_oauth_credentials, GMAIL_SCOPES

    # Recover the initiating user without requiring a bearer token: Google
    # redirects the system browser here directly and cannot attach one.
    try:
        user_id = await _consume_gmail_oauth_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except _GmailOAuthStateStoreUnavailable as exc:
        logger.error("Cannot consume Gmail OAuth state: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Gmail connection is temporarily unavailable. Please try again.",
        ) from exc

    if error == "access_denied":
        return Response(
            content="""<!DOCTYPE html><html><body>
<script>window.opener && window.opener.postMessage('gmail-cancelled', '*'); window.close();</script>
<p>Gmail connection canceled. You can close this window.</p>
</body></html>""",
            media_type="text/html",
        )
    if error or not code:
        return Response(
            content="""<!DOCTYPE html><html><body>
<script>window.opener && window.opener.postMessage('gmail-error', '*'); window.close();</script>
<p>Google could not complete the Gmail connection. Close this window and try again.</p>
</body></html>""",
            media_type="text/html",
            status_code=400,
        )

    creds = get_oauth_credentials()
    if not creds:
        raise HTTPException(status_code=500, detail="Google OAuth credentials not configured")

    settings = get_settings()
    redirect_uri = f"{settings.app_base_url}/api/matcha-work/agent/email/callback"

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15.0,
        )
        if resp.status_code != 200:
            logger.error("Gmail OAuth token exchange failed: %s", resp.text)
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
        tokens = resp.json()

    # Store encrypted token in DB
    gmail = GmailService(user_id)
    await gmail.save_token({
        "token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "scopes": GMAIL_SCOPES,
    })

    # Return HTML that closes the popup
    return Response(
        content="""<!DOCTYPE html><html><body>
<script>window.opener && window.opener.postMessage('gmail-connected', '*'); window.close();</script>
<p>Gmail connected. You can close this window.</p>
</body></html>""",
        media_type="text/html",
    )


@router.delete("/agent/email/disconnect")
async def agent_email_disconnect(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove the current user's Gmail connection."""
    async with get_connection() as conn:
        await conn.execute("UPDATE users SET gmail_token=NULL WHERE id=$1", current_user.id)
    return {"status": "disconnected"}

@router.post("/agent/email/fetch")
async def agent_email_fetch(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Fetch unread emails for the current user."""
    gmail = await _connected_gmail(current_user)
    emails = await gmail.fetch_unread(max_results=25)
    return {"emails": emails}


@router.get("/agent/email/messages/{email_id}")
async def agent_email_get_message(
    email_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """One message by Gmail id, with its HTML part (`body_html`) for the
    reader. Also re-opens a message that has dropped out of the unread list
    (read elsewhere, or after a relaunch)."""
    _require_message_id(email_id)
    gmail = await _connected_gmail(current_user)
    return await _get_message_or_404(gmail, email_id, include_html=True)


@router.post("/agent/email/summarize")
async def agent_email_summarize(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Flash Lite catch-up summary of one message. An empty `summary` means
    the model was unavailable — the client shows retry copy, never a 500."""
    from app.matcha.services.matcha_work import email_ai_service as email_ai

    await _require_email_ai(current_user)
    email_id = _require_message_id(body.get("email_id"))

    gmail = await _connected_gmail(current_user)
    msg = await _get_message_or_404(gmail, email_id)
    return {"email_id": email_id, "summary": await email_ai.summarize_email(msg)}


@router.post("/agent/email/triage")
async def agent_email_triage(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Bucket messages into needs_reply / action / fyi / newsletter for the
    sidebar. In-app only: nothing is labelled, archived or marked read in
    Gmail. With no `email_ids`, triages the current unread list; an empty
    list is an empty selection and triages nothing."""
    from app.matcha.services.matcha_work import email_ai_service as email_ai

    await _require_email_ai(current_user)
    ids = body.get("email_ids")
    if ids is not None and (not isinstance(ids, list) or not all(_is_message_id(i) for i in ids)):
        raise HTTPException(status_code=400, detail="email_ids must be a list of message ids")
    if ids == []:
        return {"buckets": []}

    gmail = await _connected_gmail(current_user)
    if ids is not None:
        unique_ids = list(dict.fromkeys(ids))[: email_ai.TRIAGE_MAX_EMAILS]
        fetched = await asyncio.gather(
            *[gmail.get_message(i) for i in unique_ids], return_exceptions=True
        )
        msgs = [m for m in fetched if isinstance(m, dict)]
    else:
        msgs = await gmail.fetch_unread(max_results=email_ai.TRIAGE_MAX_EMAILS)
    return {"buckets": await email_ai.triage_emails(msgs)}


@router.post("/agent/email/draft")
async def agent_email_draft(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Draft a reply with Flash Lite and save it as a Gmail draft in the
    original thread. Returns the text so the client can review and send."""
    from app.matcha.services.matcha_work import email_ai_service as email_ai

    await _require_email_ai(current_user)
    email_id = _require_message_id(body.get("email_id"))
    instructions = body.get("instructions")
    if instructions is not None and not isinstance(instructions, str):
        raise HTTPException(status_code=400, detail="instructions must be a string")

    gmail = await _connected_gmail(current_user)
    email = await _get_message_or_404(gmail, email_id)
    # Before the model call: no point drafting a reply that can't be addressed.
    to = _reply_recipient(email.get("from"))
    if to is None:
        raise HTTPException(
            status_code=422, detail="The original sender has no address a reply can go to"
        )

    draft_body = await email_ai.draft_reply(email, instructions)
    if not draft_body:
        raise HTTPException(
            status_code=502, detail="AI drafting is temporarily unavailable — try again"
        )

    subject = _reply_subject(email.get("subject"))
    thread_id = email.get("thread_id")
    in_reply_to = _clean_message_id_header(email.get("message_id_header"))
    try:
        result = await gmail.create_draft(
            to=to,
            subject=subject,
            body=draft_body,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
        )
    except ValueError as exc:  # a header that still can't be written
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # `subject` is the one saved on the draft, so the client never re-derives
    # the Re: rule.
    return {
        "draft_id": result.get("id"),
        "to": to,
        "subject": subject,
        "body": draft_body,
        "thread_id": thread_id,
        "in_reply_to": in_reply_to,
    }


@router.post("/agent/email/send")
async def agent_email_send(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send an email via the caller's Gmail. `thread_id` + `in_reply_to`
    (the original's Message-ID header) keep a reply in its conversation;
    `reply_to_id` is the legacy form and still threads."""
    from app.matcha.services.matcha_work.gmail_service import GmailSendRateLimited

    to = body.get("to")
    subject = body.get("subject")
    email_body = body.get("body")
    if not all(isinstance(v, str) and v.strip() for v in (to, subject, email_body)):
        raise HTTPException(status_code=400, detail="to, subject, and body are required")
    reply_to_id = _optional_str(body, "reply_to_id")
    thread_id = _optional_str(body, "thread_id")
    in_reply_to = _optional_str(body, "in_reply_to")
    draft_id = _optional_str(body, "draft_id")
    for key, value in (("reply_to_id", reply_to_id), ("thread_id", thread_id)):
        if value is not None and not _is_message_id(value):
            raise HTTPException(status_code=400, detail=f"{key} must be a Gmail id")

    gmail = await _connected_gmail(current_user)
    try:
        result = await gmail.send_email(
            to=to,
            subject=subject,
            body=email_body,
            reply_to_id=reply_to_id,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
        )
    except GmailSendRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:  # a header carrying CR/LF
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if draft_id:
        # The AI draft this reply started from is now redundant. Best-effort:
        # the mail already went out, so a failed cleanup must not fail the send.
        try:
            await gmail.delete_draft(draft_id)
        except Exception:  # noqa: BLE001
            logger.warning("Gmail draft cleanup failed after send", exc_info=True)
    return {"message_id": result.get("id"), "to": to, "subject": subject}

SNAPSHOT_MAX_EMAILS = 10


@router.post("/agent/email/snapshot")
async def agent_email_snapshot(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Attach `email-<message id>.md` snapshots of the caller's own Gmail
    messages to a kanban task, so an `email` card carries its corpus into the
    AutoPR sandbox (which never touches Gmail itself). Rendered server-side so
    mail bodies make one hop. Idempotent on filename; no AI, so no `email_ai`
    gate. Project access + task ownership are checked exactly like the
    task-file upload route, and the bytes go through the same project-file
    upload policy."""
    from app.matcha.routes.matcha_work._shared import (
        _resolve_file_urls,
        _verify_project_access,
        _verify_task_belongs_to_project,
    )
    from app.matcha.services.matcha_work import email_ai_service as email_ai
    from app.matcha.services.matcha_work import project_file_service

    ids = body.get("email_ids")
    if not isinstance(ids, list) or not ids or not all(_is_message_id(i) for i in ids):
        raise HTTPException(status_code=400, detail="email_ids must be a non-empty list of message ids")
    unique_ids = list(dict.fromkeys(ids))
    if len(unique_ids) > SNAPSHOT_MAX_EMAILS:
        raise HTTPException(
            status_code=400, detail=f"At most {SNAPSHOT_MAX_EMAILS} emails per snapshot"
        )
    try:
        project_id = UUID(str(body.get("project_id")))
        task_id = UUID(str(body.get("task_id")))
    except ValueError:
        raise HTTPException(status_code=400, detail="project_id and task_id must be UUIDs")

    project, _role = await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)
    company_id = project.get("company_id") or await get_client_company_id(current_user)
    gmail = await _connected_gmail(current_user)

    existing = {f.get("filename") for f in await project_file_service.list_task_files(project_id, task_id)}
    prefix = f"matcha-work/{company_id}/{project_id}/tasks/{task_id}/files"
    skipped: list[dict] = []
    to_fetch: list[str] = []
    for email_id in unique_ids:
        # The filename is the id, so an attached message is skipped unread.
        if email_ai.snapshot_filename(email_id) in existing:
            skipped.append({"email_id": email_id, "reason": "already_attached"})
        else:
            to_fetch.append(email_id)

    # Concurrent reads, as in triage: one Gmail round-trip at a time held the
    # Send-to-board sheet open for seconds.
    fetched = await asyncio.gather(
        *[gmail.get_message(i) for i in to_fetch], return_exceptions=True
    )
    files: list[dict] = []
    for email_id, msg in zip(to_fetch, fetched):
        if not isinstance(msg, dict):  # one unreadable message must not sink the rest
            logger.warning(
                "email snapshot: fetch failed for one message",
                exc_info=msg if isinstance(msg, BaseException) else False,
            )
            skipped.append({"email_id": email_id, "reason": "fetch_failed"})
            continue
        record = await project_file_service.store_project_file_bytes(
            email_ai.snapshot_markdown(msg).encode("utf-8"),
            filename=email_ai.snapshot_filename(email_id),
            content_type="text/markdown",
            project_id=project_id,
            uploaded_by=current_user.id,
            prefix=prefix,
            task_id=task_id,
        )
        files.append(record)

    return {"files": _resolve_file_urls(files), "skipped": skipped}


@router.get("/entitlements")
async def get_entitlements(
    response: Response,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Werk plan entitlements — the client's single tier read.

    Returns {plan, features, quotas}; plan resolved from role + company +
    mw_subscriptions + beta flags (see entitlements_service). Replaces the
    client's separate isPlusActive / beta-flag reads.
    """
    from app.matcha.services.billing import entitlements_service

    response.headers["Cache-Control"] = "private, max-age=60"
    company_id = await get_client_company_id(current_user)
    return await entitlements_service.resolve_entitlements(current_user.id, company_id)

@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    response: Response,
    period_days: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get Matcha Work token usage totals for the current user, grouped by model."""
    response.headers["Cache-Control"] = "private, max-age=300"
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return UsageSummaryResponse(
            period_days=period_days,
            generated_at=datetime.now(timezone.utc),
            totals={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "operation_count": 0,
                "estimated_operations": 0,
            },
            by_model=[],
        )

    summary = await doc_svc.get_token_usage_summary(company_id, current_user.id, period_days)
    return UsageSummaryResponse(**summary)


async def _build_usage_meter(user_id, company_id, role: str) -> dict:
    """Compose the three walls a tenant can hit into one meter payload, for
    the Work shell's TokenIndicator — 'anywhere Huume/Gemini is used'.

    Each block degrades to None INDEPENDENTLY on its own read failure (or,
    for company_budget/huume_turns, when the caller has no company) — a
    redis outage must not take down the quota half of the meter, and vice
    versa. Never raises.

    Admins skip company_budget/huume_turns entirely — mirrors the old
    `/billing/balance` admin sentinel bypass and `_run_quota_gate`'s
    `check_token_budget` role skip. Without this, `get_client_company_id`'s
    `resolve_accessible_company_scope` hands an admin an arbitrary tenant's
    company_id (first match), so the meter would show that tenant's budget
    and an Upgrade button that starts checkout for the wrong company. The
    per-user quota (the 429 wall) still applies to admins, so user_quota is
    still resolved."""
    from app.matcha.services.billing import entitlements_service, token_budget_service

    user_quota = None
    try:
        plan = await entitlements_service.resolve_plan_for_user(user_id)
        q = await doc_svc.check_token_quota(user_id, company_id)
        user_quota = {
            "plan": plan, "used": q["used"], "limit": q["limit"],
            "remaining": q["remaining"], "window_hours": q["window_hours"],
            "resets_at": q["resets_at"],
        }
    except Exception:
        logger.warning("usage meter: quota read failed", exc_info=True)

    company_budget = None
    huume_turns = None
    if company_id is not None and role != "admin":
        try:
            b = await token_budget_service.get_token_budget(company_id)
            company_budget = {
                "free_tokens_remaining": b["free_tokens_remaining"],
                "subscription_tokens_remaining": b["subscription_tokens_remaining"],
                "total_tokens_remaining": b["total_tokens_remaining"],
                "free_token_limit": b["free_token_limit"],
                "subscription_token_limit": b["subscription_token_limit"],
                "has_active_subscription": b["has_active_subscription"],
            }
        except Exception:
            logger.warning("usage meter: budget read failed", exc_info=True)

        from app.core.services.redis_cache import get_rate_limit_state
        from app.matcha.services.matcha_work.turn_pipeline import (
            HUUME_TURN_LIMIT, HUUME_TURN_WINDOW_SECONDS,
        )
        huume_turns = await get_rate_limit_state(
            str(company_id), "huume_turn", HUUME_TURN_LIMIT, HUUME_TURN_WINDOW_SECONDS,
        )

    return {"user_quota": user_quota, "company_budget": company_budget, "huume_turns": huume_turns}


@router.get("/usage/meter")
async def get_usage_meter(
    response: Response,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Live position against the three AI-usage walls a turn can hit: the
    per-user plan token quota (the 429 `_run_quota_gate` raises), the
    company token budget (the 402 the same gate raises), and the
    per-company `huume_turn` rate limit (turn_pipeline.HUUME_TURN_LIMIT).
    One read for the Work shell's TokenIndicator, mounted once in
    WorkLayout so it covers every turn-initiating surface.

    no-store: this is fetched event-driven (on turn-complete/error, see
    notifyUsageChanged) specifically to snap the meter to red right after a
    429/402 — a browser-cached response would silently serve pre-turn
    numbers for the cache window and defeat that."""
    response.headers["Cache-Control"] = "no-store"
    company_id = await get_client_company_id(current_user)
    return await _build_usage_meter(current_user.id, company_id, current_user.role)

# The global (non-project) manual task board + auto-populated deadline feed
# moved to routes/dashboard/tasks.py (2026-07-28) — GET/POST/PATCH/DELETE
# /dashboard/tasks[...]. It was core HR-ops data (credentials, incidents,
# training, compliance deadlines) stranded behind the matcha_work gate.
