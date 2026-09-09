"""Sym-link — sender-side (admin) routes.

Mounted at `/symlink` with `require_feature("symlink")` (see routes/__init__.py).
The public recipient endpoints live in `routes/intake/symlink_public.py`.

Every write logs to `symlink_audit_log` inside the transaction. Applying a
submission is the only path into a domain table and re-asserts role + feature
per call in `services/symlink/submissions.apply`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from app.core.feature_flags import merge_company_features
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.symlink import (
    DEFAULT_EXPIRY_DAYS,
    PasscodeSettings,
    SubmissionReview,
    SymlinkCreate,
    iso,
)
from app.matcha.services._shared.public_links import build_public_link as _build_public_link
from app.matcha.services._shared.jsonio import safe_json_loads
from app.matcha.services.symlink import attachments as att
from app.matcha.services.symlink import kinds, links, notify, passcode, submissions

logger = logging.getLogger(__name__)

router = APIRouter()

PUBLIC_SEGMENT = "sym"


def _serialize_link(request: Request, row: Any, *, email_sent: Optional[bool] = None) -> dict:
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "title": row["title"],
        "instructions": row["instructions"],
        "spec": links.spec_of(row),
        "recipient_name": row["recipient_name"],
        "recipient_email": row["recipient_email"],
        "employee_id": str(row["employee_id"]) if row["employee_id"] else None,
        "status": links.effective_status(row),
        "link": _build_public_link(request, row["token"], PUBLIC_SEGMENT),
        "expires_at": iso(row["expires_at"]),
        "created_at": iso(row["created_at"]),
        "sent_at": iso(row["sent_at"]),
        "last_sent_at": iso(row["last_sent_at"]),
        "first_unlocked_at": iso(row["first_unlocked_at"]),
        "completed_at": iso(row["completed_at"]),
        "turn_count": int(row["turn_count"] or 0),
        "email_sent": email_sent,
    }


def _serialize_passcode(row: Any) -> dict:
    return {
        "code": passcode.format_code(row["code"]),
        "rotated_at": iso(row["rotated_at"]),
        "next_rotation_at": iso(row["next_rotation_at"]),
        "rotation_weekday": int(row["rotation_weekday"] if row["rotation_weekday"] is not None else 0),
        "announce_channel_id": str(row["announce_channel_id"]) if row["announce_channel_id"] else None,
    }


async def _company(conn, company_id):
    row = await conn.fetchrow(
        "SELECT id, name, enabled_features, signup_source FROM companies WHERE id = $1", company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return row


def _merged_features(company_row) -> dict:
    raw = safe_json_loads(company_row["enabled_features"], {}) or {}
    try:
        return merge_company_features(raw, company_row["signup_source"])
    except TypeError:
        return merge_company_features(raw)


async def _get_link_or_404(conn, link_id, company_id, *, for_update: bool = False):
    row = await links.fetch_by_id(conn, link_id, company_id, for_update=for_update)
    if not row:
        raise HTTPException(status_code=404, detail="Sym-link not found")
    return row


# ── catalog ────────────────────────────────────────────────────────────────


@router.get("/kinds")
async def list_kinds(current_user=Depends(require_admin_or_client)):
    return {"kinds": kinds.kind_catalog()}


# ── links ──────────────────────────────────────────────────────────────────


@router.get("/links")
async def list_links(
    request: Request,
    status: Optional[str] = Query(None),
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        rows = await links.list_links(conn, company_id, status=status)
    return {"links": [_serialize_link(request, r) for r in rows]}


@router.post("/links")
async def create_link(
    body: SymlinkCreate,
    request: Request,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Mint a link and (by default) email it. The send is awaited so the
    response's `email_sent` is truthful; the connection is released first."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    try:
        spec = kinds.materialize_spec(body.kind, body.spec_overrides)
    except kinds.SpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    async with get_connection() as conn:
        company = await _company(conn, company_id)
        if body.employee_id:
            owned = await conn.fetchval(
                "SELECT id FROM employees WHERE id = $1 AND org_id = $2", body.employee_id, company_id,
            )
            if not owned:
                raise HTTPException(status_code=404, detail="Employee not found")
        if body.kind == "credential_upload" and not body.employee_id:
            raise HTTPException(
                status_code=422,
                detail="A credential upload must be linked to an employee so the document has a home",
            )
        # Make sure the company has a passcode before the first link goes out.
        await passcode.ensure_passcode(conn, company_id)
        async with conn.transaction():
            row = await links.create_link(
                conn, company_id=company_id, kind=body.kind, title=body.title.strip(),
                instructions=(body.instructions or "").strip() or None, spec=spec,
                recipient_name=body.recipient_name.strip(), recipient_email=body.recipient_email.strip().lower(),
                employee_id=body.employee_id, expires_in_days=body.expires_in_days,
                created_by=current_user.id,
            )
            await links.log_audit(
                conn, row["id"], company_id, current_user.id, "symlink_created",
                details={"kind": body.kind, "recipient_email": row["recipient_email"]},
            )
        requested_by = await notify.requester_display_name(conn, current_user)

    email_sent: Optional[bool] = None
    if body.send_email:
        email_sent = await notify.send_invite(
            row, url=_build_public_link(request, row["token"], PUBLIC_SEGMENT),
            company_name=company["name"] or "Your company", requested_by_name=requested_by,
        )
        if email_sent:
            async with get_connection() as conn:
                row = await links.mark_sent(conn, row["id"], company_id) or row
                await links.log_audit(conn, row["id"], company_id, current_user.id, "symlink_sent")
    return _serialize_link(request, row, email_sent=email_sent)


@router.get("/links/{link_id}")
async def get_link(
    link_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        row = await _get_link_or_404(conn, link_id, company_id)
        attachments = await links.list_attachments(conn, link_id)
        submission = await links.fetch_submission(conn, link_id)
    out = _serialize_link(request, row)
    out.update({
        "transcript": links.transcript_of(row),
        "known_fields": links.known_fields_of(row),
        "attachments": [att.serialize(a) for a in attachments],
        "submission": submissions.serialize(submission),
    })
    return out


@router.post("/links/{link_id}/resend")
async def resend_link(
    link_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Fresh token + expiry, persisted only after the email succeeded so a
    failed resend never burns the live link (info_requests.py pattern). The
    connection is released before the send — an email round-trip must not pin
    a pool slot."""
    async with get_connection() as conn:
        row = await _get_link_or_404(conn, link_id, company_id)
        if links.effective_status(row) not in ("pending", "in_progress", "expired"):
            raise HTTPException(status_code=400, detail="This sym-link is closed")
        company = await _company(conn, company_id)
        requested_by = await notify.requester_display_name(conn, current_user)

    new_token = links.new_token()
    preview = dict(row)
    preview["token"] = new_token
    sent = await notify.send_invite(
        preview, url=_build_public_link(request, new_token, PUBLIC_SEGMENT),
        company_name=company["name"] or "Your company", requested_by_name=requested_by,
        reminder=True,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="Failed to send the email; the previous link still works")

    async with get_connection() as conn:
        async with conn.transaction():
            updated = await links.rotate_token(
                conn, link_id, company_id, token=new_token, expires_in_days=DEFAULT_EXPIRY_DAYS,
            )
            if not updated:
                raise HTTPException(status_code=409, detail="This sym-link was closed before the resend completed")
            await links.log_audit(conn, link_id, company_id, current_user.id, "symlink_resent")
    return _serialize_link(request, updated, email_sent=True)


@router.post("/links/{link_id}/revoke")
async def revoke_link(
    link_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await links.revoke(conn, link_id, company_id)
            if not row:
                existing = await _get_link_or_404(conn, link_id, company_id)
                raise HTTPException(status_code=400, detail=f"Cannot revoke a link that is {existing['status']}")
            await links.log_audit(conn, link_id, company_id, current_user.id, "symlink_revoked")
    return _serialize_link(request, row)


@router.get("/links/{link_id}/attachments/{attachment_id}/download")
async def download_attachment(
    link_id: UUID,
    attachment_id: UUID,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        await _get_link_or_404(conn, link_id, company_id)
        row = await conn.fetchrow(
            """SELECT storage_path, file_name FROM symlink_attachments
                WHERE id = $1 AND symlink_id = $2 AND company_id = $3 AND discarded_at IS NULL""",
            attachment_id, link_id, company_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    url = att.presigned_url(row["storage_path"])
    if not url:
        raise HTTPException(status_code=503, detail="Storage is not configured for downloads")
    return {"url": url, "file_name": row["file_name"]}


# ── submissions ────────────────────────────────────────────────────────────


@router.get("/submissions")
async def list_submissions(
    request: Request,
    status: str = Query("pending"),
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT sub.id, sub.symlink_id, sub.company_id, sub.fields, sub.attachment_ids,
                       sub.submitted_at, sub.status, sub.reviewed_by, sub.reviewed_at,
                       sub.review_note, sub.applied_ref,
                       {", ".join("s." + c.strip() + " AS link_" + c.strip() for c in links.LINK_COLS.split(","))}
                  FROM symlink_submissions sub
                  JOIN symlinks s ON s.id = sub.symlink_id
                 WHERE sub.company_id = $1 AND sub.status = $2
                 ORDER BY sub.submitted_at DESC
                 LIMIT 200""",
            company_id, status,
        )
    out = []
    for r in rows:
        link_view = {k[5:]: v for k, v in dict(r).items() if k.startswith("link_")}
        item = submissions.serialize(r)
        item["link"] = _serialize_link(request, link_view)
        out.append(item)
    return {"submissions": out}


@router.post("/submissions/{submission_id}/apply")
async def apply_submission(
    submission_id: UUID,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        company = await _company(conn, company_id)
        features = _merged_features(company)
        async with conn.transaction():
            submission = await conn.fetchrow(
                """SELECT id, symlink_id, company_id, fields, attachment_ids, submitted_at, status,
                          reviewed_by, reviewed_at, review_note, applied_ref
                     FROM symlink_submissions WHERE id = $1 AND company_id = $2 FOR UPDATE""",
                submission_id, company_id,
            )
            if not submission:
                raise HTTPException(status_code=404, detail="Submission not found")
            link_row = await _get_link_or_404(conn, submission["symlink_id"], company_id, for_update=True)
            row, post_commit = await submissions.apply(
                conn, link_row, submission, current_user=current_user, features=features,
            )
            await links.log_audit(
                conn, link_row["id"], company_id, current_user.id, "symlink_applied",
                entity_type="symlink_submission", entity_id=str(submission_id),
                details={"kind": link_row["kind"]},
            )
    document_type = links.spec_of(link_row).get("document_type") or "other"
    for doc_id, content, mime in post_commit:
        background_tasks.add_task(submissions.run_credential_extraction, doc_id, content, mime, document_type)
    return submissions.serialize(row)


@router.post("/submissions/{submission_id}/reject")
async def reject_submission(
    submission_id: UUID,
    body: SubmissionReview,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        async with conn.transaction():
            submission = await conn.fetchrow(
                """SELECT id, symlink_id, company_id, fields, attachment_ids, submitted_at, status,
                          reviewed_by, reviewed_at, review_note, applied_ref
                     FROM symlink_submissions WHERE id = $1 AND company_id = $2 FOR UPDATE""",
                submission_id, company_id,
            )
            if not submission:
                raise HTTPException(status_code=404, detail="Submission not found")
            link_row = await _get_link_or_404(conn, submission["symlink_id"], company_id, for_update=True)
            row = await submissions.reject(conn, link_row, submission, current_user=current_user, note=body.note)
            await links.log_audit(
                conn, link_row["id"], company_id, current_user.id, "symlink_rejected",
                entity_type="symlink_submission", entity_id=str(submission_id),
                details={"note": body.note} if body.note else None,
            )
    return submissions.serialize(row)


# ── passcode ───────────────────────────────────────────────────────────────


@router.get("/passcode")
async def get_passcode(
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        row = await passcode.ensure_passcode(conn, company_id)
    return _serialize_passcode(row)


@router.post("/passcode/rotate")
async def rotate_passcode_now(
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await passcode.rotate_passcode(conn, company_id)
            company = await _company(conn, company_id)
            announced = False
            if row["announce_channel_id"] and _merged_features(company).get("matcha_ops"):
                announced = await notify.announce_rotation(
                    conn, company_id=company_id, channel_id=row["announce_channel_id"], code=row["code"],
                )
    out = _serialize_passcode(row)
    out["announced"] = announced
    return out


@router.put("/passcode/settings")
async def update_passcode_settings(
    body: PasscodeSettings,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        row = await passcode.ensure_passcode(conn, company_id)
        weekday = body.rotation_weekday if body.rotation_weekday is not None else int(row["rotation_weekday"] or 0)
        channel_id = row["announce_channel_id"]
        if body.clear_announce_channel:
            channel_id = None
        elif body.announce_channel_id is not None:
            owned = await conn.fetchval(
                "SELECT id FROM channels WHERE id = $1 AND company_id = $2", body.announce_channel_id, company_id,
            )
            if not owned:
                raise HTTPException(status_code=404, detail="Channel not found")
            channel_id = body.announce_channel_id
        # Changing the weekday re-anchors the next rotation from the last one.
        next_at = passcode.next_rotation(row["rotated_at"], weekday) if body.rotation_weekday is not None else row["next_rotation_at"]
        updated = await conn.fetchrow(
            f"""UPDATE symlink_passcodes
                   SET rotation_weekday = $2, announce_channel_id = $3, next_rotation_at = $4, updated_at = NOW()
                 WHERE company_id = $1
             RETURNING {passcode._COLS}""",
            company_id, weekday, channel_id, next_at,
        )
    return _serialize_passcode(updated)


@router.get("/channels")
async def list_announce_channels(
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Company channels the rotation can be announced in (matcha_ops tenants)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, name, channel_scope FROM channels
                WHERE company_id = $1 AND COALESCE(is_archived, false) = false
                ORDER BY name""",
            company_id,
        )
    return {"channels": [{"id": str(r["id"]), "name": r["name"], "scope": r["channel_scope"]} for r in rows]}


@router.get("/employees")
async def search_employees(
    q: str = Query("", max_length=100),
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Small roster lookup for the create form's employee picker."""
    like = f"%{q.strip()}%" if q.strip() else "%"
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, first_name, last_name, email
                 FROM employees
                WHERE org_id = $1
                  AND (first_name ILIKE $2 OR last_name ILIKE $2 OR email ILIKE $2)
                ORDER BY last_name, first_name
                LIMIT 25""",
            company_id, like,
        )
    return {
        "employees": [
            {"id": str(r["id"]), "name": f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(), "email": r["email"]}
            for r in rows
        ]
    }
