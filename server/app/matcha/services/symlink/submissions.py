"""Staged submissions: stage on recipient submit, apply/reject on sender review.

Confirm-first is the whole point: `stage` only writes `symlink_submissions`;
`apply` is the sole path into a domain table and re-asserts role + feature on
every call (mirrors `huume/actions.py:evaluate_huume_action`). Per kind:

  credential_upload  → copies each attachment into the employee's credential
                       prefix + inserts `credential_documents` rows
                       (uploaded_via='symlink'), then queues the same Gemini
                       extraction the portal upload runs. Needs `employee_id`.
  info_update        → PATCHes a whitelisted set of `employees` columns
                       (phone / address / emergency_contact) when `employee_id`
                       is linked; record-only otherwise.
  manager_review     → record-only (status 'applied', nothing else written).
  custom             → record-only.

Apply is two-phase so no S3 round-trip ever runs inside the write transaction
(the same rule `attachments.py` follows for uploads):

  1. `prepare_apply`  — gate + read the attachment rows (short, no locks).
  2. `copy_credential_objects` — S3 GET/PUT per attachment with NO connection
     held. Discards what it copied if any copy fails.
  3. `apply`          — the locked transaction: insert domain rows, flip the
     submission + link. The route discards the copies if this raises, so a
     rollback never strands objects under `employee-credentials/`.
  4. `run_credential_extraction` — post-commit, re-reads the object by path
     (the bytes are not carried across the response boundary).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.matcha.services.symlink import attachments as att
from app.matcha.services.symlink import links
from app.matcha.services.symlink.chat import coerce_submitted, is_complete, missing_items

logger = logging.getLogger(__name__)

APPLY_ROLES = {"client", "admin"}


class ApplyError(HTTPException):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(status_code=status_code, detail=detail)


def evaluate_apply(current_user, features: dict) -> None:
    """Deterministic gate, re-run per apply call (never trust the mount gate alone)."""
    if getattr(current_user, "role", None) not in APPLY_ROLES:
        raise ApplyError("Only company admins can apply a submission", 403)
    if current_user.role != "admin" and not bool((features or {}).get("symlink")):
        raise ApplyError("Sym-link is not enabled for this company", 403)


def serialize(row: Any) -> Optional[dict]:
    if not row:
        return None
    fields = row["fields"]
    if isinstance(fields, str):
        fields = json.loads(fields)
    applied_ref = row["applied_ref"]
    if isinstance(applied_ref, str):
        applied_ref = json.loads(applied_ref)
    return {
        "id": str(row["id"]),
        "symlink_id": str(row["symlink_id"]),
        "status": row["status"],
        "fields": fields or {},
        "attachment_ids": [str(a) for a in (row["attachment_ids"] or [])],
        "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        "reviewed_by": str(row["reviewed_by"]) if row["reviewed_by"] else None,
        "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        "review_note": row["review_note"],
        "applied_ref": applied_ref,
    }


def _fields_of(submission: Any) -> dict:
    fields = submission["fields"]
    return fields if isinstance(fields, dict) else json.loads(fields or "{}")


# ── stage ──────────────────────────────────────────────────────────────────


async def stage(conn, link_row: Any, submitted_fields: dict) -> Any:
    """Recipient submit. Caller holds FOR UPDATE on the link row and has
    already confirmed it is open. The review form is authoritative — a cleared
    input clears the field — and the deterministic completion check is re-run
    against the spec so a client can't skip a required item by editing the form."""
    spec = links.spec_of(link_row)
    fields = coerce_submitted(submitted_fields or {}, spec)
    present = await links.present_slots(conn, link_row["id"])
    if not is_complete(fields, present, spec):
        missing = ", ".join(m["label"] for m in missing_items(fields, present, spec))
        raise HTTPException(status_code=422, detail=f"Still missing: {missing}")
    attachment_rows = await links.list_attachments(conn, link_row["id"])
    row = await conn.fetchrow(
        """INSERT INTO symlink_submissions (symlink_id, company_id, fields, attachment_ids)
           VALUES ($1, $2, $3::jsonb, $4::uuid[])
           ON CONFLICT (symlink_id) DO NOTHING
           RETURNING id, symlink_id, company_id, fields, attachment_ids, submitted_at, status,
                     reviewed_by, reviewed_at, review_note, applied_ref""",
        link_row["id"], link_row["company_id"], json.dumps(fields),
        [r["id"] for r in attachment_rows],
    )
    if not row:
        raise HTTPException(status_code=409, detail="This request was already submitted")
    await links.save_turn(
        conn, link_row["id"], transcript=links.transcript_of(link_row),
        known_fields=fields, turn_count=int(link_row["turn_count"] or 0),
    )
    await links.set_status(conn, link_row["id"], link_row["company_id"], "submitted", completed=True)
    await links.revoke_unlocks(conn, link_row["id"])
    return row


# ── apply: phase 1 + 2 (outside the write transaction) ─────────────────────


async def prepare_apply(conn, link_row: Any, submission: Any, *, current_user, features: dict) -> list:
    """Gate + collect the attachment rows a credential apply will copy. Runs
    on a plain (unlocked) connection; `apply` re-checks status under the lock."""
    evaluate_apply(current_user, features)
    if submission["status"] != "pending":
        raise ApplyError("This submission was already reviewed", 409)
    if link_row["kind"] != "credential_upload":
        return []
    if not link_row["employee_id"]:
        raise ApplyError("Link this sym-link to an employee before applying a credential upload")
    return await links.list_attachments(conn, link_row["id"])


async def copy_credential_objects(link_row: Any, attachment_rows: list) -> list[dict]:
    """S3 only — no DB connection held. Copies each staged object into the
    employee's credential prefix; on any failure discards the copies made so
    far and raises. Returns [{"attachment": row, "file_path": ..., "mime": ...}]."""
    if not attachment_rows:
        return []
    from app.core.services.storage import get_storage

    storage = get_storage()
    company_id = link_row["company_id"]
    employee_id = link_row["employee_id"]
    copied: list[dict] = []
    try:
        for arow in attachment_rows:
            content = await att.read_bytes(arow["storage_path"])
            if content is None:
                raise ApplyError("Could not read the uploaded document from storage", 502)
            mime = arow["content_type"] or "application/octet-stream"
            file_path = await storage.upload_private_file(
                content, arow["file_name"],
                prefix=f"employee-credentials/{company_id}/{employee_id}", content_type=mime,
            )
            del content
            copied.append({"attachment": arow, "file_path": file_path, "mime": mime})
    except Exception:
        await discard_copies(copied)
        raise
    return copied


async def discard_copies(copied: list[dict]) -> None:
    """Best-effort cleanup of objects written by `copy_credential_objects`."""
    for item in copied:
        await att.discard(item["file_path"])


# ── apply: phase 3 (inside the locked transaction) ─────────────────────────


async def _apply_credential_upload(conn, link_row: Any, submission: Any, actor_id, copied: list[dict]) -> dict:
    employee_id = link_row["employee_id"]
    if not employee_id:
        raise ApplyError("Link this sym-link to an employee before applying a credential upload")
    spec = links.spec_of(link_row)
    document_type = spec.get("document_type") or "other"
    company_id = link_row["company_id"]
    fields = _fields_of(submission)

    # The link closed to uploads at submit time, so the attachment set can't
    # have moved between phase 1 and now — but verify rather than assume.
    live_ids = {r["id"] for r in await links.list_attachments(conn, link_row["id"])}
    if live_ids != {c["attachment"]["id"] for c in copied}:
        raise ApplyError("The attachments changed while applying; try again", 409)

    from app.core.services.credential_template_service import (
        materialize_uploaded_schedule_blocking_requirement,
    )

    created: list[str] = []
    extraction_jobs: list[tuple[Any, str, str]] = []
    for item in copied:
        arow = item["attachment"]
        await materialize_uploaded_schedule_blocking_requirement(
            conn, company_id=company_id, employee_id=employee_id, credential_type_key=document_type,
        )
        doc = await conn.fetchrow(
            """INSERT INTO credential_documents
                   (company_id, employee_id, document_type, filename, file_path, mime_type, file_size,
                    uploaded_by, uploaded_via)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'symlink')
               RETURNING id""",
            company_id, employee_id, document_type, arow["file_name"], item["file_path"], item["mime"],
            int(arow["size_bytes"] or 0), actor_id,
        )
        created.append(str(doc["id"]))
        extraction_jobs.append((doc["id"], item["file_path"], item["mime"]))

    ref = {
        "credential_document_ids": created,
        "document_type": document_type,
        "employee_id": str(employee_id),
        "fields": {k: fields.get(k) for k in ("credential_name", "credential_number", "issuing_authority", "issued_on", "expires_on")},
    }
    # The extraction runs after the transaction commits (caller schedules it).
    ref["_extraction_jobs"] = extraction_jobs
    return ref


_INFO_UPDATE_COLUMNS = ("phone", "address")


async def _apply_info_update(conn, link_row: Any, submission: Any) -> dict:
    fields = _fields_of(submission)
    employee_id = link_row["employee_id"]
    if not employee_id:
        return {"record_only": True, "reason": "no linked employee"}
    updates: dict[str, Any] = {}
    for col in _INFO_UPDATE_COLUMNS:
        value = fields.get(col)
        if isinstance(value, str) and value.strip():
            updates[col] = value.strip()[:255 if col == "phone" else 1000]
    contact = {
        k: fields.get(f"emergency_contact_{k}")
        for k in ("name", "phone", "relationship")
        if isinstance(fields.get(f"emergency_contact_{k}"), str) and fields.get(f"emergency_contact_{k}").strip()
    }
    if contact:
        updates["emergency_contact"] = json.dumps(contact)
    if not updates:
        return {"record_only": True, "reason": "nothing to change"}
    sets = []
    params: list[Any] = [employee_id, link_row["company_id"]]
    for col, value in updates.items():
        params.append(value)
        if col == "emergency_contact":
            # Merge, never replace: a submission that skipped the optional
            # relationship must not erase the one already on file.
            sets.append(f"emergency_contact = COALESCE(emergency_contact, '{{}}'::jsonb) || ${len(params)}::jsonb")
        else:
            sets.append(f"{col} = ${len(params)}")
    updated = await conn.fetchval(
        f"UPDATE employees SET {', '.join(sets)}, updated_at = NOW() WHERE id = $1 AND org_id = $2 RETURNING id",
        *params,
    )
    if not updated:
        raise ApplyError("The linked employee no longer exists in this company", 404)
    return {"employee_id": str(employee_id), "updated_columns": sorted(updates)}


async def apply(
    conn, link_row: Any, submission: Any, *, current_user, features: dict, copied: Optional[list[dict]] = None,
) -> tuple[Any, list]:
    """Apply one pending submission inside the caller's locked transaction.
    `copied` is the output of `copy_credential_objects` (credential kind only).
    Returns (updated submission row, post-commit jobs)."""
    evaluate_apply(current_user, features)
    if submission["status"] != "pending":
        raise ApplyError("This submission was already reviewed", 409)

    kind = link_row["kind"]
    post_commit: list = []
    if kind == "credential_upload":
        ref = await _apply_credential_upload(conn, link_row, submission, current_user.id, copied or [])
        post_commit = ref.pop("_extraction_jobs", [])
    elif kind == "info_update":
        ref = await _apply_info_update(conn, link_row, submission)
    else:
        ref = {"record_only": True}

    row = await conn.fetchrow(
        """UPDATE symlink_submissions
              SET status = 'applied', reviewed_by = $2, reviewed_at = NOW(), applied_ref = $3::jsonb
            WHERE id = $1 AND status = 'pending'
        RETURNING id, symlink_id, company_id, fields, attachment_ids, submitted_at, status,
                  reviewed_by, reviewed_at, review_note, applied_ref""",
        submission["id"], current_user.id, json.dumps(ref),
    )
    if not row:
        raise ApplyError("This submission was reviewed concurrently", 409)
    await links.set_status(conn, link_row["id"], link_row["company_id"], "applied")
    return row, post_commit


async def reject(conn, link_row: Any, submission: Any, *, current_user, note: Optional[str]) -> Any:
    if submission["status"] != "pending":
        raise ApplyError("This submission was already reviewed", 409)
    row = await conn.fetchrow(
        """UPDATE symlink_submissions
              SET status = 'rejected', reviewed_by = $2, reviewed_at = NOW(), review_note = $3
            WHERE id = $1 AND status = 'pending'
        RETURNING id, symlink_id, company_id, fields, attachment_ids, submitted_at, status,
                  reviewed_by, reviewed_at, review_note, applied_ref""",
        submission["id"], current_user.id, (note or "").strip()[:2000] or None,
    )
    if not row:
        raise ApplyError("This submission was reviewed concurrently", 409)
    await links.set_status(conn, link_row["id"], link_row["company_id"], "rejected")
    return row


# ── post-commit ────────────────────────────────────────────────────────────


async def _mark_extraction(doc_id, status: str, result: Optional[dict] = None) -> None:
    from app.database import get_connection

    async with get_connection() as conn:
        await conn.execute(
            """UPDATE credential_documents
                  SET extracted_data = COALESCE($1::jsonb, extracted_data), extraction_status = $2, updated_at = NOW()
                WHERE id = $3""",
            json.dumps(result) if result is not None else None, status, doc_id,
        )


async def run_credential_extraction(doc_id, file_path: str, mime: str, document_type: str) -> None:
    """Post-commit: same Gemini extraction the portal upload triggers. Takes the
    object *path*, not the bytes — the document is already durable in S3, and
    holding up to 10 MB per file across the response boundary is what the
    memory-constrained backend container can't afford. A throw lands the row
    on 'failed', never leaves it 'pending' forever."""
    from app.core.services.credential_extraction import extract_credential_info

    try:
        content = await att.read_bytes(file_path)
        if content is None:
            raise RuntimeError(f"could not read {file_path}")
        result = await extract_credential_info(content, mime or "application/octet-stream", document_type)
        del content
        extraction_status = "extracted" if result.get("fields") else "failed"
        await _mark_extraction(doc_id, extraction_status, result)
    except Exception as exc:
        logger.warning("[symlink] credential extraction failed for %s: %s", doc_id, exc)
        try:
            await _mark_extraction(doc_id, "failed")
        except Exception:
            logger.exception("[symlink] could not mark extraction failed for %s", doc_id)
