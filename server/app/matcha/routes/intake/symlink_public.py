"""Sym-link — public recipient endpoints (`/sym/{token}`).

No auth, no feature gate at the mount: the per-task token is the credential,
and the company's raw stored `enabled_features["symlink"]` must be True (the
flag defaults False, so — unlike `ir_magic_links` — a missing key means OFF).

Hardening mirrors `/request-info`: per-IP caps before any DB lookup, per-link
+ per-company Redis budgets charged only once the link is known live, a
64 KiB raw-body ceiling ahead of Pydantic, a honeypot on the unlock + submit
bodies, and the single-use burn (submit) done under FOR UPDATE.

Unlock state: `POST /unlock` verifies the company passcode and returns a
random opaque token whose sha256 is stored in `symlink_unlocks`; the browser
sends it back as `X-Symlink-Unlock`. Rotating the passcode never touches
those rows (decided grace rule); revoking/expiring the link does.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.services.redis_cache import check_rate_limit, client_ip
from app.database import get_connection
from app.matcha.models.symlink import (
    MAX_PUBLIC_CHAT_BODY_BYTES,
    UNLOCK_HEADER,
    PublicSubmitRequest,
    PublicTurnRequest,
    PublicUnlockRequest,
)
from app.matcha.services._shared.public_links import build_public_link as _build_public_link
from app.matcha.services._shared.jsonio import safe_json_loads
from app.matcha.services.symlink import attachments as att
from app.matcha.services.symlink import chat, kinds, links, notify, passcode, submissions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["symlink-public"])


def _features_dict(raw) -> dict:
    return safe_json_loads(raw, {}) or {}


def _symlink_allowed(features: dict) -> bool:
    return bool(features.get("symlink", False))


async def _read_json_capped(request: Request, model):
    raw = await request.body()
    if len(raw) > MAX_PUBLIC_CHAT_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request is too large")
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Malformed request")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors())


async def _resolve(token: str) -> Any:
    """RLS-free token → row (with company name + raw features), 404 if the
    link doesn't exist or the company has the feature off."""
    async with get_connection() as conn:
        row = await links.fetch_by_token(conn, token)
    if not row or not _symlink_allowed(_features_dict(row["enabled_features"])):
        raise HTTPException(status_code=404, detail="Invalid link")
    return row


def _check_open(row: Any) -> None:
    status = links.effective_status(row)
    if status not in links.OPEN_STATUSES:
        raise HTTPException(status_code=410, detail=links.CLOSED_MESSAGES.get(status, "This link is closed."))


async def _require_unlock(conn, row: Any, request: Request) -> None:
    token = request.headers.get(UNLOCK_HEADER)
    if not await links.verify_unlock(conn, row["id"], token):
        raise HTTPException(status_code=401, detail="Enter the passcode to continue")


async def _budget(token: str, company_id: str, kind: str, per_link: int, per_company: int) -> None:
    await check_rate_limit(token, f"symlink_{kind}_link", per_link, 3600)
    await check_rate_limit(company_id, f"symlink_{kind}_co", per_company, 3600)


async def _state(conn, row: Any) -> dict:
    spec = links.spec_of(row)
    known = links.known_fields_of(row)
    attachments = await links.list_attachments(conn, row["id"])
    present = {a["slot"] for a in attachments}
    return {
        "spec": kinds.public_spec(spec),
        "transcript": links.transcript_of(row),
        "known_fields": chat.coerce_fields({}, known, spec),
        "attachments": [att.serialize(a) for a in attachments],
        "complete": chat.is_complete(known, present, spec),
        "missing": chat.missing_items(known, present, spec),
        "turn_count": int(row["turn_count"] or 0),
    }


def _public_summary(row: Any) -> dict:
    return {
        "valid": True,
        "company_name": row["company_name"],
        "title": row["title"],
        "kind": row["kind"],
        "instructions": row["instructions"],
        "recipient_name": row["recipient_name"],
        "status": links.effective_status(row),
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
    }


# ── validate ───────────────────────────────────────────────────────────────


@router.get("/sym/{token}")
async def validate_symlink(token: str, request: Request):
    """Link summary; plus the resumable conversation when the unlock header is valid."""
    await check_rate_limit(client_ip(request), "symlink_validate", 60, 3600)
    row = await _resolve(token)
    out = _public_summary(row)
    status = out["status"]
    if status not in links.OPEN_STATUSES:
        out["valid"] = False
        out["closed_message"] = links.CLOSED_MESSAGES.get(status, "This link is closed.")
        return out
    unlock = request.headers.get(UNLOCK_HEADER)
    out["unlocked"] = False
    if unlock:
        async with get_connection(tenant_id=str(row["company_id"])) as conn:
            if await links.verify_unlock(conn, row["id"], unlock):
                out["unlocked"] = True
                out.update(await _state(conn, row))
    return out


# ── unlock ─────────────────────────────────────────────────────────────────


@router.post("/sym/{token}/unlock")
async def unlock_symlink(token: str, request: Request):
    body = await _read_json_capped(request, PublicUnlockRequest)
    if body.internal_ref:
        return {"unlock_token": "ok"}  # honeypot — look successful, do nothing

    ip = client_ip(request)
    await check_rate_limit(ip, "symlink_unlock_ip", 8, 600)
    row = await _resolve(token)
    _check_open(row)
    # Charged after the link is known live so a dead token can't drain the bucket.
    await check_rate_limit(token, "symlink_unlock_link", 12, 3600)

    company_id = str(row["company_id"])
    async with get_connection(tenant_id=company_id) as conn:
        code_row = await passcode.fetch_passcode(conn, row["company_id"])
        stored = code_row["code"] if code_row else None
        if not passcode.verify(body.passcode, stored):
            await links.log_audit(conn, row["id"], row["company_id"], None, "symlink_unlock_failed", ip_address=ip)
            raise HTTPException(status_code=401, detail="That passcode isn't right. Check with the person who sent this link.")
        async with conn.transaction():
            unlock_token = await links.record_unlock(conn, row["id"], row["company_id"], ip=ip)
            await links.log_audit(conn, row["id"], row["company_id"], None, "symlink_unlocked", ip_address=ip)
        fresh = await links.fetch_by_id(conn, row["id"], row["company_id"])
        state = await _state(conn, fresh)
    out = _public_summary(row)
    out["status"] = links.effective_status(fresh)
    out["unlocked"] = True
    out["unlock_token"] = unlock_token
    out.update(state)
    return out


# ── chat turn ──────────────────────────────────────────────────────────────


@router.post("/sym/{token}/chat/turn")
async def symlink_chat_turn(token: str, request: Request):
    body = await _read_json_capped(request, PublicTurnRequest)
    ip = client_ip(request)
    await check_rate_limit(ip, "symlink_turn_ip", 10, 60)
    await check_rate_limit(ip, "symlink_turn_ip_hr", 60, 3600)
    row = await _resolve(token)
    _check_open(row)
    company_id = str(row["company_id"])

    async with get_connection(tenant_id=company_id) as conn:
        await _require_unlock(conn, row, request)
        await _budget(token, company_id, "turn", 40, 240)
        fresh = await links.fetch_by_id(conn, row["id"], row["company_id"])
        spec = links.spec_of(fresh)
        transcript = links.transcript_of(fresh)
        known = links.known_fields_of(fresh)
        present = await links.present_slots(conn, row["id"])
        turn_count = int(fresh["turn_count"] or 0)
        if turn_count >= chat.MAX_TURNS:
            state = await _state(conn, fresh)
            return {
                "assistant_message": "Let's move to the review step — you can fill in anything that's left there.",
                "fields": state["known_fields"],
                "complete": state["complete"],
                "turn_count": turn_count,
                "error": False,
                "limit_reached": True,
            }
        company_name = row["company_name"]
        instructions = fresh["instructions"]

    # No pooled connection across the model call.
    transcript = transcript + [{"role": "user", "content": body.message.strip()}]
    result = await chat.next_turn(
        transcript, known, spec, present, company_name=company_name, instructions=instructions,
    )
    transcript = transcript + [{"role": "assistant", "content": result["assistant_message"]}]
    turn_count += 1

    async with get_connection(tenant_id=company_id) as conn:
        await links.save_turn(
            conn, row["id"], transcript=transcript[-200:], known_fields=result["fields"], turn_count=turn_count,
        )
    return {
        "assistant_message": result["assistant_message"],
        "fields": result["fields"],
        "complete": result["complete"],
        "turn_count": turn_count,
        "error": result["error"],
    }


# ── attachments ────────────────────────────────────────────────────────────


@router.post("/sym/{token}/attachments")
async def upload_symlink_attachment(
    token: str,
    request: Request,
    slot: str = Form(..., max_length=64),
    file: UploadFile = File(...),
):
    ip = client_ip(request)
    await check_rate_limit(ip, "symlink_upload_ip", 20, 3600)
    row = await _resolve(token)
    _check_open(row)
    company_id = str(row["company_id"])
    spec = links.spec_of(row)
    slot_spec = next((a for a in spec.get("attachments", []) if a.get("slot") == slot), None)
    if not slot_spec:
        raise HTTPException(status_code=422, detail="Unknown attachment slot")

    async with get_connection(tenant_id=company_id) as conn:
        await _require_unlock(conn, row, request)
        await _budget(token, company_id, "upload", 24, 200)
        live = await conn.fetchval(
            "SELECT COUNT(*) FROM symlink_attachments WHERE symlink_id = $1 AND discarded_at IS NULL", row["id"],
        )
        if int(live or 0) >= att.MAX_FILES_PER_LINK:
            raise HTTPException(status_code=422, detail="Too many attachments on this link")

    # S3 round-trip happens with no connection held.
    staged = await att.stage_upload(file, company_id=company_id, symlink_id=row["id"], accept=slot_spec.get("accept"))

    try:
        async with get_connection(tenant_id=company_id) as conn:
            async with conn.transaction():
                fresh = await links.fetch_by_id(conn, row["id"], row["company_id"], for_update=True)
                _check_open(fresh)
                arow, replaced = await att.insert_attachment(
                    conn, symlink_id=row["id"], company_id=row["company_id"], slot=slot, staged=staged,
                )
                await links.log_audit(
                    conn, row["id"], row["company_id"], None, "symlink_attachment_uploaded",
                    entity_type="symlink_attachment", entity_id=str(arow["id"]),
                    details={"slot": slot, "file_name": staged["file_name"]}, ip_address=ip,
                )
            present = await links.present_slots(conn, row["id"])
            known = links.known_fields_of(fresh)
    except Exception:
        await att.discard(staged["storage_path"])
        raise
    for old_path in replaced:
        await att.discard(old_path)
    return {
        "attachment": att.serialize(arow),
        "complete": chat.is_complete(known, present, spec),
        "missing": chat.missing_items(known, present, spec),
    }


@router.delete("/sym/{token}/attachments/{attachment_id}")
async def delete_symlink_attachment(token: str, attachment_id: UUID, request: Request):
    row = await _resolve(token)
    _check_open(row)
    company_id = str(row["company_id"])
    async with get_connection(tenant_id=company_id) as conn:
        await _require_unlock(conn, row, request)
        gone = await conn.fetchrow(
            """UPDATE symlink_attachments SET discarded_at = NOW()
                WHERE id = $1 AND symlink_id = $2 AND discarded_at IS NULL
            RETURNING storage_path""",
            attachment_id, row["id"],
        )
        if not gone:
            raise HTTPException(status_code=404, detail="Attachment not found")
        present = await links.present_slots(conn, row["id"])
    await att.discard(gone["storage_path"])
    spec = links.spec_of(row)
    known = links.known_fields_of(row)
    return {"deleted": True, "complete": chat.is_complete(known, present, spec), "missing": chat.missing_items(known, present, spec)}


# ── submit ─────────────────────────────────────────────────────────────────


@router.post("/sym/{token}/submit")
async def submit_symlink(token: str, request: Request, background_tasks: BackgroundTasks):
    body = await _read_json_capped(request, PublicSubmitRequest)
    if body.internal_ref:
        return {"submitted": True}

    ip = client_ip(request)
    await check_rate_limit(ip, "symlink_submit_ip", 10, 3600)
    row = await _resolve(token)
    _check_open(row)
    company_id = str(row["company_id"])

    async with get_connection(tenant_id=company_id) as conn:
        await _require_unlock(conn, row, request)
        async with conn.transaction():
            fresh = await links.fetch_by_id(conn, row["id"], row["company_id"], for_update=True)
            _check_open(fresh)
            await _budget(token, company_id, "submit", 6, 120)
            submission = await submissions.stage(conn, fresh, body.fields)
            await links.log_audit(
                conn, row["id"], row["company_id"], None, "symlink_submitted",
                entity_type="symlink_submission", entity_id=str(submission["id"]), ip_address=ip,
            )
        sender_email, sender_name = await notify.sender_contact(conn, fresh["created_by"], row["company_id"])

    if sender_email:
        review_link = _build_public_link(request, str(row["id"]), "app/symlink")
        background_tasks.add_task(
            notify.send_submitted,
            to_email=sender_email, to_name=sender_name, company_name=row["company_name"] or "Your company",
            recipient_name=row["recipient_name"], title=row["title"], review_link=review_link,
        )
    return {"submitted": True, "submission_id": str(submission["id"])}
