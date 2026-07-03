"""Cross-project workspace surface: open-tasks + recent-activity feeds for
Home, the per-user Gmail email agent, entitlements/usage summary, and the
global (non-project) manual task board.

Holds the third order-sensitive route pair: DELETE /tasks/{task_id} must
stay registered before DELETE /tasks/dismiss (Starlette matches in
registration order; task_id uses a plain path param so /tasks/dismiss is
already shadowed today -- pre-existing, not fixed by this split).

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.matcha_work import UsageSummaryResponse
from app.matcha.services import matcha_work_document as doc_svc
from app.matcha.services.matcha_work_ai import get_ai_provider

logger = logging.getLogger(__name__)
router = APIRouter()

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
    from app.matcha.services.gmail_service import GmailService
    gmail = GmailService(current_user.id)
    return await gmail.get_status()

@router.post("/agent/email/connect")
async def agent_email_connect(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Start Google OAuth flow. Returns an auth_url to open in a popup."""
    from app.matcha.services.gmail_service import get_oauth_credentials, GMAIL_SCOPES
    import urllib.parse

    creds = get_oauth_credentials()
    if not creds:
        raise HTTPException(status_code=500, detail="Google OAuth credentials not configured on the server")

    settings = get_settings()
    redirect_uri = f"{settings.app_base_url}/api/matcha-work/agent/email/callback"

    # Encode user ID in state so callback knows who to store the token for
    from app.core.services.secret_crypto import encrypt_secret
    state = encrypt_secret(str(current_user.id))

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

@router.get("/agent/email/callback")
async def agent_email_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """OAuth callback — exchange code for tokens, store encrypted in DB, close popup."""
    from app.matcha.services.gmail_service import GmailService, get_oauth_credentials, GMAIL_SCOPES
    from app.core.services.secret_crypto import decrypt_secret as _decrypt

    # Recover user ID from state
    try:
        user_id_str = _decrypt(state)
        from uuid import UUID as _UUID
        user_id = _UUID(user_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

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
    from app.matcha.services.gmail_service import GmailService
    gmail = GmailService(current_user.id)
    await gmail.load_token()
    if not gmail.is_configured:
        raise HTTPException(status_code=400, detail="Gmail not connected")
    emails = await gmail.fetch_unread(max_results=25)
    return {"emails": emails}

@router.post("/agent/email/draft")
async def agent_email_draft(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Draft a reply to an email using AI."""
    from app.matcha.services import entitlements_service
    from app.matcha.services.gmail_service import GmailService

    # Email fetch/send stay free (non-AI); AI drafting is Lite+.
    await entitlements_service.require_plan(current_user.id, entitlements_service.PLAN_LITE, "email_ai")

    gmail = GmailService(current_user.id)
    await gmail.load_token()
    if not gmail.is_configured:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    email_id = body.get("email_id")
    instructions = body.get("instructions", "Write a helpful, concise reply.")
    if not email_id:
        raise HTTPException(status_code=400, detail="email_id is required")

    email = await gmail.get_message(email_id)

    ai_provider = get_ai_provider()
    prompt = (
        f"Draft a professional reply to this email. Return ONLY the reply body text, no subject line.\n"
        f"Instructions: {instructions}\n\n"
        f"Original email:\nFrom: {email['from']}\nSubject: {email['subject']}\nBody:\n{email['body'][:3000]}"
    )
    ai_resp = await ai_provider.generate(
        [{"role": "user", "content": prompt}], {}, company_context=""
    )
    draft_body = ai_resp.assistant_reply

    result = await gmail.create_draft(
        to=email["from"],
        subject=f"Re: {email['subject']}" if not email["subject"].startswith("Re:") else email["subject"],
        body=draft_body,
        reply_to_id=email_id,
    )

    return {
        "draft_id": result.get("id"),
        "to": email["from"],
        "subject": email["subject"],
        "body": draft_body,
    }

@router.post("/agent/email/send")
async def agent_email_send(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send an email via Gmail."""
    from app.matcha.services.gmail_service import GmailService
    gmail = GmailService(current_user.id)
    await gmail.load_token()
    if not gmail.is_configured:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    to = body.get("to")
    subject = body.get("subject")
    email_body = body.get("body")
    reply_to_id = body.get("reply_to_id")

    if not all([to, subject, email_body]):
        raise HTTPException(status_code=400, detail="to, subject, and body are required")

    result = await gmail.send_email(to=to, subject=subject, body=email_body, reply_to_id=reply_to_id)
    return {"message_id": result.get("id"), "to": to, "subject": subject}

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
    from app.matcha.services import entitlements_service

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

@router.get("/tasks")
async def list_tasks(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Combined task board: auto-populated items + manual tasks + dismissals."""
    from app.matcha.routes.dashboard import _UPCOMING_SOURCES, _apply_company_filter, _severity_from_days, UpcomingItem
    from datetime import date as _date, timedelta as _td

    company_id = await get_client_company_id(current_user)
    today = _date.today()
    lookahead = today + _td(days=90)

    # 1. Auto-populated items from upcoming sources
    auto_items = []
    async with get_connection() as conn:
        import asyncpg as _asyncpg
        for source in _UPCOMING_SOURCES:
            try:
                sql = _apply_company_filter(source["sql"], company_id)
                uses_p1 = "$1" in sql
                uses_p2 = "$2" in sql
                if uses_p1 and uses_p2:
                    rows = await conn.fetch(sql, company_id, lookahead)
                elif uses_p1:
                    rows = await conn.fetch(sql, company_id)
                elif uses_p2:
                    rows = await conn.fetch(sql, lookahead)
                else:
                    rows = await conn.fetch(sql)
            except (_asyncpg.UndefinedTableError, _asyncpg.UndefinedColumnError):
                continue
            except Exception:
                continue
            for row in rows:
                deadline = row["deadline"]
                if deadline is None:
                    continue
                days_until = (deadline - today).days
                link = source["link"]
                row_id = row.get("id")
                if row_id and "{id}" in link:
                    link = link.replace("{id}", row_id)
                auto_items.append({
                    "category": source["category"],
                    "source_id": row.get("id") or "",
                    "title": row["title"] or source["category"].title(),
                    "subtitle": row.get("subtitle"),
                    "date": str(deadline),
                    "days_until": days_until,
                    "severity": _severity_from_days(days_until),
                    "link": link,
                })

    auto_items.sort(key=lambda x: x["days_until"])

    # 2. Manual tasks
    manual_items = []
    async with get_connection() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT id, title, description, due_date, horizon, priority, status,
                       completed_at, link, category, created_at, updated_at
                FROM mw_tasks
                WHERE company_id = $1 AND status != 'cancelled' AND project_id IS NULL
                ORDER BY
                    CASE WHEN status = 'completed' THEN 1 ELSE 0 END,
                    due_date ASC NULLS LAST,
                    created_at DESC
                """,
                company_id,
            )
            for r in rows:
                d = dict(r)
                d["id"] = str(d["id"])
                d["source"] = "manual"
                if d["due_date"]:
                    d["days_until"] = (d["due_date"] - today).days
                    d["date"] = str(d["due_date"])
                else:
                    d["days_until"] = None
                    d["date"] = None
                manual_items.append(d)
        except Exception:
            pass  # table may not exist yet

    # 3. Dismissed IDs
    dismissed_ids = []
    async with get_connection() as conn:
        try:
            rows = await conn.fetch(
                "SELECT source_category, source_id FROM mw_task_dismissals WHERE user_id = $1",
                current_user.id,
            )
            dismissed_ids = [f"{r['source_category']}:{r['source_id']}" for r in rows]
        except Exception:
            pass

    return {
        "auto_items": auto_items,
        "manual_items": manual_items,
        "dismissed_ids": dismissed_ids,
        "total": len(auto_items) + len(manual_items),
    }

@router.post("/tasks", status_code=201)
async def create_task(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a manual task."""
    from datetime import date as _date

    company_id = await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")

    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    due_date = body.get("due_date")
    if due_date and isinstance(due_date, str):
        due_date = _date.fromisoformat(due_date)

    horizon = body.get("horizon")
    priority = body.get("priority", "medium")
    if priority not in ("critical", "high", "medium", "low"):
        priority = "medium"

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_tasks (company_id, created_by, title, description, due_date, horizon, priority, link)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            company_id, current_user.id, title,
            body.get("description"), due_date, horizon, priority, body.get("link"),
        )
    d = dict(row)
    d["id"] = str(d["id"])
    d["company_id"] = str(d["company_id"])
    d["created_by"] = str(d["created_by"])
    d["source"] = "manual"
    if d.get("due_date"):
        d["days_until"] = (d["due_date"] - _date.today()).days
        d["date"] = str(d["due_date"])
    else:
        d["days_until"] = None
        d["date"] = None
    return d

@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a manual task."""
    company_id = await get_client_company_id(current_user)

    allowed = {"title", "description", "due_date", "horizon", "priority", "status", "link"}
    sets = []
    vals = []
    idx = 1
    for k, v in body.items():
        if k in allowed:
            if k == "due_date" and isinstance(v, str):
                from datetime import date as _date
                v = _date.fromisoformat(v)
            sets.append(f"{k} = ${idx}")
            vals.append(v)
            idx += 1

    if not sets:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Auto-fill completed_at
    if body.get("status") == "completed":
        sets.append(f"completed_at = ${idx}")
        vals.append(datetime.now(timezone.utc))
        idx += 1
    elif body.get("status") == "pending":
        sets.append(f"completed_at = ${idx}")
        vals.append(None)
        idx += 1

    sets.append(f"updated_at = NOW()")
    vals.extend([task_id, company_id])

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE mw_tasks SET {', '.join(sets)} WHERE id = ${idx} AND company_id = ${idx + 1} RETURNING *",
            *vals,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    d = dict(row)
    d["id"] = str(d["id"])
    d["source"] = "manual"
    return d

@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Cancel a manual task."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_tasks SET status = 'cancelled', updated_at = NOW() WHERE id = $1 AND company_id = $2",
            task_id, company_id,
        )
    return {"status": "cancelled"}

@router.post("/tasks/dismiss")
async def dismiss_auto_task(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Dismiss an auto-populated task item."""
    cat = body.get("source_category", "")
    sid = body.get("source_id", "")
    if not cat or not sid:
        raise HTTPException(status_code=400, detail="source_category and source_id required")
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO mw_task_dismissals (user_id, source_category, source_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, source_category, source_id) DO NOTHING
            """,
            current_user.id, cat, sid,
        )
    return {"status": "dismissed"}

@router.delete("/tasks/dismiss")
async def undismiss_auto_task(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Un-dismiss a previously dismissed auto-populated task."""
    cat = body.get("source_category", "")
    sid = body.get("source_id", "")
    if not cat or not sid:
        raise HTTPException(status_code=400, detail="source_category and source_id required")
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM mw_task_dismissals WHERE user_id = $1 AND source_category = $2 AND source_id = $3",
            current_user.id, cat, sid,
        )
    return {"status": "restored"}
