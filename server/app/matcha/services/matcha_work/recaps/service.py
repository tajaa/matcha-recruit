"""Owner-scoped reads and reversible user controls; no agent execution."""
from __future__ import annotations

import time
import base64
import binascii
import re

from fastapi import HTTPException

from app.config import get_settings
from app.database import connection_or_direct, decode_jsonb

from . import settings
from app.matcha.models.matcha_work.recaps import Asset, Cursor, Manifest

# Every read and every asynchronous publication re-checks source retention.
VALID = """EXISTS (SELECT 1 FROM companies c WHERE c.id=r.company_id AND c.is_personal)
    AND EXISTS (SELECT 1 FROM users u WHERE u.id=r.owner_user_id AND u.is_active AND NOT COALESCE(u.is_suspended,FALSE))
    AND EXISTS (SELECT 1 FROM mw_agent_recap_sources s WHERE s.recap_id=r.id)
    AND NOT EXISTS (
        SELECT 1 FROM mw_agent_recap_sources s
        LEFT JOIN mw_project_agent_runs a ON a.id=s.run_id
        LEFT JOIN mw_agent_task_rounds q ON q.id=s.task_round_id
        LEFT JOIN mw_agent_tasks t ON t.id=q.task_id
        LEFT JOIN mw_job_searches j ON j.id=s.job_search_id
        WHERE s.recap_id=r.id AND (
            (s.kind='run' AND (a.id IS NULL OR a.requested_by<>r.owner_user_id OR a.company_id<>r.company_id)) OR
            (s.kind='research' AND (t.id IS NULL OR t.deleted_at IS NOT NULL OR t.user_id<>r.owner_user_id OR t.company_id<>r.company_id)) OR
            (s.kind='jobs' AND (j.id IS NULL OR j.deleted_at IS NOT NULL OR j.user_id<>r.owner_user_id OR j.company_id<>r.company_id))))"""


async def owned(conn, recap_id, user_id, company_id, *, lock=False):
    if not settings.enabled() and not await conn.fetchval("SELECT to_regclass('mw_agent_recaps')"):
        raise HTTPException(404, "Recap not found.")
    row = await conn.fetchrow(
        f"""SELECT r.* FROM mw_agent_recaps r WHERE r.id=$1 AND r.owner_user_id=$2 AND r.company_id=$3
            AND r.state<>'deleted' AND {VALID} {'FOR UPDATE OF r' if lock else ''}""",
        recap_id, user_id, company_id,
    )
    if row is None:
        raise HTTPException(404, "Recap not found.")
    return row


def view(row, *, detail=False):
    output = decode_jsonb(row.get("output_manifest"), {}) or {}
    result = {k: row[k] for k in ("id", "title", "state", "outcome", "created_at", "ready_at", "expires_at", "last_error_code")}
    result.update(schema_version=1, duration_ms=output.get("duration_ms"), can_retry=(
        row["state"] == "failed" and row["manual_retry_request_id"] is None and row["render_attempts"] < 4
        and row["created_at"].timestamp() > time.time() - 7 * 86400
    ))
    if detail:
        manifest = decode_jsonb(row.get("manifest"), {}) or {}
        result["chapters"] = output.get("chapters", [])
        result["transcript"] = manifest.get("transcript") or [s["event"] for s in manifest.get("scenes", [])]
        result["source_completed_at"] = row["source_completed_at"]
    return result


async def preferences(user_id, company_id):
    available = settings.available(user_id)
    if not settings.enabled():
        return {"enabled": False, "email_enabled": False, "available": False}
    async with connection_or_direct() as conn:
        row = await conn.fetchrow("SELECT enabled,email_enabled FROM mw_agent_recap_preferences WHERE user_id=$1 AND company_id=$2", user_id, company_id)
    return {"enabled": bool(row and row["enabled"]), "email_enabled": bool(row and row["email_enabled"]), "available": available}


async def set_preferences(user_id, company_id, body):
    if not settings.available(user_id):
        raise HTTPException(503, "Task recaps aren't available for this account yet.")
    async with connection_or_direct() as conn, conn.transaction():
        await conn.execute(
            """INSERT INTO mw_agent_recap_preferences(company_id,user_id,enabled,email_enabled) VALUES($1,$2,$3,$4)
               ON CONFLICT(company_id,user_id) DO UPDATE SET enabled=$3,email_enabled=$4,updated_at=NOW()""",
            company_id, user_id, body.enabled, body.email_enabled,
        )
        if not body.enabled:
            await conn.execute(
                """UPDATE mw_agent_recaps SET state='skipped',render_token=NULL,last_error_code='opt_out'
                   WHERE company_id=$1 AND owner_user_id=$2 AND state IN ('collecting','waiting','queued','rendering')""", company_id, user_id,
            )
    return await preferences(user_id, company_id)


async def listing(user_id, company_id, *, limit=25, before=None, ids=None, source_id=None):
    cursor = None
    if before is not None:
        try:
            if not isinstance(before, str) or len(before) > 512 or not re.fullmatch(r"[A-Za-z0-9_-]+", before):
                raise ValueError("invalid cursor")
            cursor = Cursor.model_validate_json(base64.urlsafe_b64decode(before + "=" * (-len(before) % 4)))
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(422, "Invalid recap cursor.") from exc
    async with connection_or_direct() as conn:
        if not settings.enabled() and not await conn.fetchval("SELECT to_regclass('mw_agent_recaps')"):
            return {"recaps": [], "next_cursor": None}
        rows = await conn.fetch(
            f"""SELECT r.* FROM mw_agent_recaps r WHERE r.owner_user_id=$1 AND r.company_id=$2 AND r.state<>'deleted'
                AND ($3::timestamptz IS NULL OR (r.created_at,r.id)<($3,$7::uuid)) AND ($4::uuid[] IS NULL OR r.id=ANY($4))
                AND ($5::uuid IS NULL OR EXISTS (SELECT 1 FROM mw_agent_recap_sources s
                    LEFT JOIN mw_agent_task_rounds q ON q.id=s.task_round_id WHERE s.recap_id=r.id
                    AND (s.run_id=$5 OR s.job_search_id=$5 OR q.task_id=$5)))
                AND {VALID} ORDER BY r.created_at DESC,r.id DESC LIMIT $6""",
            user_id, company_id, cursor.at if cursor else None, ids, source_id, limit, cursor.id if cursor else None,
        )
    next_cursor = base64.urlsafe_b64encode(Cursor(at=rows[-1]["created_at"], id=rows[-1]["id"]).model_dump_json().encode()).decode().rstrip("=") if len(rows) == limit else None
    return {"recaps": [view(dict(row)) for row in rows], "next_cursor": next_cursor}


async def detail(user_id, company_id, recap_id):
    async with connection_or_direct() as conn:
        row = await owned(conn, recap_id, user_id, company_id)
        result = view(dict(row), detail=True)
        sources = await conn.fetch(
            """SELECT s.kind,s.run_id,s.job_search_id,q.task_id FROM mw_agent_recap_sources s
               LEFT JOIN mw_agent_task_rounds q ON q.id=s.task_round_id WHERE s.recap_id=$1 AND s.role<>'phase'""", recap_id,
        )
        result["sources"] = [{"kind": s["kind"], "id": s["run_id"] or s["task_id"] or s["job_search_id"]} for s in sources]
        return result


async def playback(user_id, company_id, recap_id):
    from .storage import signed
    async with connection_or_direct() as conn:
        row = await owned(conn, recap_id, user_id, company_id)
    if row["state"] != "ready" or not row["expires_at"] or row["expires_at"].timestamp() <= time.time():
        raise HTTPException(409, "This recap is not available to play.")
    output = decode_jsonb(row["output_manifest"], {})
    return {"video_url": signed(Asset.model_validate(output["video"])), "poster_url": signed(Asset.model_validate(output["poster"])), "expires_in": 300}


async def retry(user_id, company_id, recap_id, request_id):
    if not settings.available(user_id):
        raise HTTPException(503, "Recap rendering is unavailable.")
    async with connection_or_direct() as conn, conn.transaction():
        row = await owned(conn, recap_id, user_id, company_id, lock=True)
        if row["manual_retry_request_id"] == request_id:
            return view(dict(row))
        pref = await conn.fetchval("SELECT enabled FROM mw_agent_recap_preferences WHERE user_id=$1 AND company_id=$2", user_id, company_id)
        if not pref:
            raise HTTPException(409, "Enable task recaps before retrying.")
        if not view(dict(row))["can_retry"] or not row["manifest"]:
            raise HTTPException(409, "A retry is unavailable or has already been requested.")
        Manifest.model_validate(decode_jsonb(row["manifest"], {}))
        row = await conn.fetchrow(
            """UPDATE mw_agent_recaps SET state='queued',manual_retry_request_id=$2,next_attempt_at=NOW(),
               render_token=NULL,last_error_code=NULL,updated_at=NOW() WHERE id=$1 RETURNING *""", recap_id, request_id,
        )
    return view(dict(row))


async def tombstone(conn, recap_id, *, state="deleted"):
    row = await conn.fetchrow(
        """UPDATE mw_agent_recaps SET state=$2,deleted_at=NOW(),render_token=NULL,output_manifest=NULL,
           manifest=NULL,updated_at=NOW() WHERE id=$1 RETURNING company_id,owner_user_id""", recap_id, state,
    )
    if row:
        bucket = get_settings().s3_private_bucket
        if bucket:
            await conn.execute(
                "INSERT INTO mw_agent_recap_cleanup_jobs(bucket,prefix) VALUES($1,$2) ON CONFLICT DO NOTHING",
                bucket, f"espresso-recaps/{row['company_id']}/{row['owner_user_id']}/{recap_id}/",
            )
        await conn.execute("DELETE FROM mw_agent_recap_events WHERE recap_id=$1", recap_id)
        await conn.execute("UPDATE mw_agent_recap_sources SET mail_payload=NULL WHERE recap_id=$1", recap_id)
        await conn.execute("UPDATE mw_agent_recap_deliveries SET state='suppressed',claim_token=NULL WHERE recap_id=$1 AND state IN ('pending','retry_wait')", recap_id)


async def delete(user_id, company_id, recap_id):
    async with connection_or_direct() as conn, conn.transaction():
        if not settings.enabled() and not await conn.fetchval("SELECT to_regclass('mw_agent_recaps')"):
            raise HTTPException(404, "Recap not found.")
        existing = await conn.fetchrow("SELECT state FROM mw_agent_recaps WHERE id=$1 AND owner_user_id=$2 AND company_id=$3", recap_id,user_id,company_id)
        if existing and existing["state"] == "deleted":
            return {"deleted": True}
        await owned(conn, recap_id, user_id, company_id, lock=True)
        await tombstone(conn, recap_id)
    return {"deleted": True}
