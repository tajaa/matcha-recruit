"""Private sales campaigns. Pool-free so the API, agent and Celery share one contract.

The campaign row serializes imports, draft edits and queue transitions. A recipient
is claimed durably before Gmail. Unknown outcomes are never automatically replayed.
"""

from __future__ import annotations
import hashlib
import json
import re
from uuid import UUID, uuid4
from types import SimpleNamespace

from app.database import connection_or_direct, decode_jsonb
from app.core.feature_flags import merge_company_features
from app.matcha.models.matcha_work.sales import (
    CampaignCreate,
    ProspectImport,
    ProspectPatch,
    Template,
    SendBatch,
)

MAX_PROSPECTS = 1000


class SalesError(ValueError):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def review_token(row):
    return hashlib.sha256(
        json.dumps(
            [str(row["id"]), row["email"], row["subject"], row["body"]],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def view(row):
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
    if "sources" in result:
        result["sources"] = decode_jsonb(result["sources"]) or []
        result["review_token"] = review_token(row)
    result.pop("dispatch_token", None)
    return result


async def project_access(conn, project_id, user_id, *, edit=False):
    # Same access rule as project_service.access, with fresh account/role checks.
    row = await conn.fetchrow(
        """
        SELECT p.id, p.title, p.company_id, u.role AS user_role,
               home.enabled_features AS home_features, home.signup_source, visible.value AS visible_features,
               c.role AS collaborator_role,
               (u.role IN ('client','individual') AND cl.company_id = p.company_id) AS same_company
        FROM mw_projects p JOIN users u ON u.id = $2
        LEFT JOIN clients cl ON cl.user_id = u.id
        LEFT JOIN companies home ON home.id = cl.company_id
        LEFT JOIN companies project_company ON project_company.id = p.company_id
        LEFT JOIN platform_settings visible ON visible.key = 'visible_features'
        LEFT JOIN mw_project_collaborators c ON c.project_id = p.id AND c.user_id = u.id AND c.status = 'active'
        WHERE p.id = $1 AND u.is_active AND NOT COALESCE(u.is_suspended, FALSE)
          AND u.role IN ('admin','client','individual')
          AND home.deleted_at IS NULL AND project_company.deleted_at IS NULL
          AND (u.role = 'admin' OR COALESCE(home.status,'approved') NOT IN ('pending','rejected'))
          AND (c.user_id IS NOT NULL OR (u.role IN ('client','individual') AND cl.company_id = p.company_id))
    """,
        project_id,
        user_id,
    )
    if not row:
        raise SalesError("This workspace is no longer accessible.", 404)
    if row["user_role"] == "client" and (
        "matcha_work" not in (decode_jsonb(row["visible_features"]) or [])
        or not merge_company_features(row["home_features"], row["signup_source"]).get(
            "matcha_work"
        )
    ):
        raise SalesError("Matcha Work is no longer enabled for this account.", 403)
    if edit and row["collaborator_role"] in ("viewer", "commenter"):
        raise SalesError("You have read-only access to this workspace.", 403)
    return row


async def _campaign(conn, campaign_id, user_id, *, edit=False):
    row = await conn.fetchrow(
        "SELECT * FROM mw_sales_campaigns WHERE id = $1 AND user_id = $2 FOR UPDATE",
        campaign_id,
        user_id,
    )
    if not row:
        raise SalesError("Campaign not found.", 404)
    await project_access(conn, row["project_id"], user_id, edit=edit)
    return row


async def list_projects(user_id):
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT p.id, p.title FROM mw_projects p
            JOIN users u ON u.id = $1 LEFT JOIN clients cl ON cl.user_id = u.id
        LEFT JOIN companies home ON home.id = cl.company_id
        LEFT JOIN companies project_company ON project_company.id = p.company_id
        LEFT JOIN platform_settings visible ON visible.key = 'visible_features'
            LEFT JOIN mw_project_collaborators c ON c.project_id = p.id AND c.user_id = u.id AND c.status = 'active'
            WHERE u.is_active AND NOT COALESCE(u.is_suspended,FALSE) AND u.role IN ('admin','client','individual')
          AND home.deleted_at IS NULL AND project_company.deleted_at IS NULL
          AND (u.role = 'admin' OR COALESCE(home.status,'approved') NOT IN ('pending','rejected'))
            AND (c.user_id IS NOT NULL OR (u.role IN ('client','individual') AND cl.company_id = p.company_id))
            ORDER BY p.title LIMIT 100""",
            user_id,
        )
    return [view(row) for row in rows]


async def list_campaigns(project_id, user_id):
    async with connection_or_direct() as conn:
        await project_access(conn, project_id, user_id)
        rows = await conn.fetch(
            "SELECT * FROM mw_sales_campaigns WHERE project_id = $1 AND user_id = $2 ORDER BY updated_at DESC LIMIT 100",
            project_id,
            user_id,
        )
    return [view(row) for row in rows]


async def create_campaign(project_id, user_id, data: CampaignCreate):
    async with connection_or_direct() as conn, conn.transaction():
        await project_access(conn, project_id, user_id, edit=True)
        row = await conn.fetchrow(
            """INSERT INTO mw_sales_campaigns(project_id,user_id,request_id,title,target,offer)
            VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(user_id,request_id) DO UPDATE SET request_id = EXCLUDED.request_id RETURNING *""",
            project_id,
            user_id,
            data.request_id,
            data.title,
            data.target,
            data.offer,
        )
        if row["project_id"] != project_id:
            raise SalesError(
                "This request was already used for another workspace.", 409
            )
    return view(row)


async def read_campaign(campaign_id, user_id, *, offset=0, limit=1000):
    if not 0 <= offset <= MAX_PROSPECTS or not 1 <= limit <= MAX_PROSPECTS:
        raise SalesError("Invalid prospect page.")
    async with connection_or_direct() as conn, conn.transaction():
        row = await _campaign(conn, campaign_id, user_id)
        items = await conn.fetch(
            "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 ORDER BY created_at,id OFFSET $2 LIMIT $3",
            campaign_id,
            offset,
            limit,
        )
        counts = await conn.fetch(
            "SELECT status,COUNT(*) AS count FROM mw_sales_prospects WHERE campaign_id = $1 GROUP BY status",
            campaign_id,
        )
    return {
        "campaign": view(row),
        "prospects": [view(item) for item in items],
        "counts": {r["status"]: r["count"] for r in counts},
        "offset": offset,
    }


def dedupe_key(item):
    if item.email:
        return "email:" + item.email
    if not (item.website or item.company or item.name):
        raise SalesError("Each prospect needs an email, name, company or website.")
    return (
        "lead:"
        + hashlib.sha256(
            json.dumps(
                [item.name.casefold(), item.company.casefold(), item.website.casefold()]
            ).encode()
        ).hexdigest()
    )


async def import_prospects(campaign_id, user_id, data: ProspectImport):
    keyed = {dedupe_key(item): item for item in data.prospects}
    async with connection_or_direct() as conn, conn.transaction():
        await _campaign(conn, campaign_id, user_id, edit=True)
        existing = set(
            await conn.fetchval(
                "SELECT COALESCE(array_agg(dedupe_key), ARRAY[]::text[]) FROM mw_sales_prospects WHERE campaign_id = $1",
                campaign_id,
            )
        )
        new = [(key, item) for key, item in keyed.items() if key not in existing]
        if len(existing) + len(new) > MAX_PROSPECTS:
            raise SalesError("A campaign supports up to 1,000 prospects.")
        if new:
            await conn.execute(
                """INSERT INTO mw_sales_prospects(campaign_id,dedupe_key,email,name,company,website,notes,sources)
                SELECT $1, r.dedupe_key,r.email,r.name,r.company,r.website,r.notes,r.sources
                FROM jsonb_to_recordset($2::jsonb) AS r(dedupe_key text,email text,name text,company text,website text,notes text,sources jsonb)""",
                campaign_id,
                json.dumps(
                    [item.model_dump() | {"dedupe_key": key} for key, item in new]
                ),
            )
        await _touch(conn, campaign_id)
    return {"added": len(new), "duplicates": len(data.prospects) - len(new)}


async def _touch(conn, campaign_id):
    await conn.execute(
        "UPDATE mw_sales_campaigns SET updated_at = NOW() WHERE id = $1", campaign_id
    )


async def patch_prospect(campaign_id, item_id, user_id, data: ProspectPatch):
    changes = data.model_dump(exclude_none=True, exclude={"review_token"})
    async with connection_or_direct() as conn, conn.transaction():
        await _campaign(conn, campaign_id, user_id, edit=True)
        row = await conn.fetchrow(
            "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 AND id = $2 FOR UPDATE",
            campaign_id,
            item_id,
        )
        if not row:
            raise SalesError("Prospect not found.", 404)
        if data.review_token and data.review_token != review_token(row):
            raise SalesError(
                "The draft changed. Reload and review the current version.", 409
            )
        if set(changes) - {"stage"} and row["status"] not in (
            "prospect",
            "draft",
            "failed",
        ):
            raise SalesError(
                "This message is frozen for delivery. Release pending messages before editing.",
                409,
            )
        merged = dict(row) | changes
        if "email" in changes:
            key = dedupe_key(SimpleNamespace(**merged))
            duplicate = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM mw_sales_prospects WHERE campaign_id = $1 AND dedupe_key = $2 AND id <> $3)",
                campaign_id,
                key,
                item_id,
            )
            if duplicate:
                raise SalesError("That recipient is already in this campaign.", 409)
            changes["dedupe_key"] = key
        if set(changes) - {"stage"}:
            changes["status"] = (
                "draft"
                if merged["email"] and merged["subject"] and merged["body"]
                else "prospect"
            )
            changes["error"] = None
        if changes:
            fields, values = [], [campaign_id, item_id]
            for key, value in changes.items():
                values.append(json.dumps(value) if key == "sources" else value)
                fields.append(
                    f"{key} = ${len(values)}" + ("::jsonb" if key == "sources" else "")
                )
            row = await conn.fetchrow(
                f"UPDATE mw_sales_prospects SET {', '.join(fields)} WHERE campaign_id = $1 AND id = $2 RETURNING *",
                *values,
            )
            await _touch(conn, campaign_id)
    return view(row)


TOKENS = {"name", "company", "research", "website"}


def render_template(template, row):
    tokens = re.findall(r"\{\{(.*?)\}\}", template)
    if any(token not in TOKENS for token in tokens):
        raise SalesError(
            "Template fields: {{name}}, {{company}}, {{research}}, {{website}}."
        )
    rendered = re.sub(r"\{\{(.*?)\}\}", lambda match: row[match[1]] or "", template)
    if "{{" in rendered or "}}" in rendered:
        raise SalesError("Unclosed or nested template field.")
    return rendered.strip()


async def draft_template(campaign_id, user_id, data: Template):
    async with connection_or_direct() as conn, conn.transaction():
        await _campaign(conn, campaign_id, user_id, edit=True)
        rows = await conn.fetch(
            "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 AND status IN ('prospect','draft','failed') ORDER BY created_at,id",
            campaign_id,
        )
        rendered = []
        for row in rows:
            subject, body = (
                render_template(data.subject, row),
                render_template(data.body, row),
            )
            if (
                not subject
                or not body
                or len(subject) > 300
                or len(body) > 12000
                or "\n" in subject
                or "\r" in subject
            ):
                raise SalesError(
                    "A rendered message is empty, too long, or has a multiline subject."
                )
            rendered.append((row, subject, body))
        if rendered:
            await conn.execute(
                """UPDATE mw_sales_prospects SET subject = r.subject, body = r.body, status = r.status, error = NULL
                FROM jsonb_to_recordset($2::jsonb) AS r(id uuid,subject text,body text,status text)
                WHERE mw_sales_prospects.campaign_id = $1 AND mw_sales_prospects.id = r.id""",
                campaign_id,
                json.dumps(
                    [
                        {
                            "id": str(row["id"]),
                            "subject": subject,
                            "body": body,
                            "status": "draft" if row["email"] else "prospect",
                        }
                        for row, subject, body in rendered
                    ]
                ),
            )
        await _touch(conn, campaign_id)
    return {"drafted": len(rendered)}


async def approve_batch(campaign_id, user_id, data: SendBatch, gmail=None):
    from .gmail_service import GmailService

    gmail = gmail or GmailService(user_id)
    status = await gmail.get_status()
    if (
        not status.get("connected")
        or not status.get("email")
        or status["email"].lower() != data.sender.lower()
    ):
        raise SalesError(
            "Connect the Gmail account shown in this review before sending.", 409
        )
    ids = [draft.id for draft in data.drafts]
    if len(set(ids)) != len(ids):
        raise SalesError("Select each draft only once.")
    async with connection_or_direct() as conn, conn.transaction():
        campaign = await _campaign(conn, campaign_id, user_id, edit=True)
        if campaign["last_approval_id"] == data.request_id:
            return {"status": campaign["status"]}
        if campaign["status"] == "sending":
            raise SalesError("Pause the current batch before adding another.", 409)
        rows = await conn.fetch(
            "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 AND id = ANY($2::uuid[]) FOR UPDATE",
            campaign_id,
            ids,
        )
        tokens = {draft.id: draft.review_token for draft in data.drafts}
        if len(rows) != len(ids) or any(
            r["status"] != "draft"
            or not r["email"]
            or not r["subject"]
            or not r["body"]
            or tokens[r["id"]] != review_token(r)
            for r in rows
        ):
            raise SalesError(
                "Some drafts changed or are not ready. Reload and review them again.",
                409,
            )
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM mw_sales_prospects WHERE campaign_id = $1 AND status IN ('approved','claimed')",
            campaign_id,
        )
        if pending:
            raise SalesError("Resume or release the pending batch first.", 409)
        token = uuid4()
        await conn.execute(
            "UPDATE mw_sales_prospects SET status = 'approved', error = NULL WHERE campaign_id = $1 AND id = ANY($2::uuid[])",
            campaign_id,
            ids,
        )
        await conn.execute(
            """UPDATE mw_sales_campaigns SET status = 'sending', sender = $2, dispatch_token = $3,
            last_approval_id = $4, error = NULL, next_attempt_at = NOW(), updated_at = NOW() WHERE id = $1""",
            campaign_id,
            data.sender.lower(),
            token,
            data.request_id,
        )
    await dispatch(campaign_id, token)
    return {"status": "sending"}


async def _stale(conn, campaign_id):
    await conn.execute(
        """UPDATE mw_sales_prospects SET status = 'unknown', error = 'Delivery interrupted. Check Gmail Sent before contacting this recipient again.'
        WHERE campaign_id = $1 AND status = 'claimed' AND claimed_at < NOW() - INTERVAL '10 minutes'""",
        campaign_id,
    )


async def campaign_action(campaign_id, user_id, action):
    token = None
    async with connection_or_direct() as conn, conn.transaction():
        row = await _campaign(conn, campaign_id, user_id, edit=True)
        await _stale(conn, campaign_id)
        if action == "pause":
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', updated_at = NOW() WHERE id = $1",
                campaign_id,
            )
        elif action == "release_pending":
            await conn.execute(
                "UPDATE mw_sales_prospects SET status = 'draft' WHERE campaign_id = $1 AND status = 'approved'",
                campaign_id,
            )
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', dispatch_token = NULL, updated_at = NOW() WHERE id = $1",
                campaign_id,
            )
        elif action == "retry_failed":
            await conn.execute(
                "UPDATE mw_sales_prospects SET status = 'draft', error = NULL WHERE campaign_id = $1 AND status = 'failed'",
                campaign_id,
            )
        elif action == "resume":
            pending = await conn.fetchval(
                "SELECT COUNT(*) FROM mw_sales_prospects WHERE campaign_id = $1 AND status IN ('approved','claimed')",
                campaign_id,
            )
            if not pending or not row["sender"]:
                raise SalesError("No approved messages remain to send.")
            token = uuid4()
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'sending', dispatch_token = $2, error = NULL, updated_at = NOW() WHERE id = $1",
                campaign_id,
                token,
            )
        else:
            raise SalesError("Unknown campaign action.")
    if token:
        await dispatch(campaign_id, token)
    return {"status": "ok"}


async def dispatch(campaign_id, token, *, countdown=0):
    from app.workers.tasks.sales_campaign import send_sales_campaign

    try:
        send_sales_campaign.apply_async(
            args=[str(campaign_id), str(token)], countdown=countdown
        )
    except Exception:
        async with connection_or_direct() as conn:
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', error = 'Queue unavailable. Resume to continue.', updated_at = NOW() WHERE id = $1 AND dispatch_token = $2",
                campaign_id,
                token,
            )
        raise SalesError(
            "The send queue is unavailable. Your approved drafts are saved; use Resume.",
            503,
        )
