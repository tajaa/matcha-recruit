"""Discipline projects -- seeding plus the meeting/signature/refusal state
recorders.

This is a discipline concern living in matcha_work because the workflow is
modelled as a project; the authoritative discipline product is
services/discipline/ and routes/employee_lifecycle/discipline.py.
"""
import logging
from typing import Optional
from uuid import UUID
from app.database import get_connection

from ._config import _ALLOWED_DISCIPLINE_CATEGORIES, _ALLOWED_DISCIPLINE_LEVELS, _ALLOWED_DISCIPLINE_SEVERITIES, _now_iso
from ._data import _load_and_lock_data, _persist_data

logger = logging.getLogger(__name__)


def _seed_discipline_data(extra_data: Optional[dict]) -> dict:
    """Initial project_data shape for a Discipline project.

    Document-first flow: no synced employee DB, no escalation engine,
    no look-back math. The user fills in the employee details + the
    situation, picks a level, and the AI drafts the document into
    mw_projects.sections like blog projects do.
    """
    e = extra_data or {}
    employee_in = e.get("employee") or {}
    infraction_in = e.get("infraction") or {}
    level = e.get("level") if e.get("level") in _ALLOWED_DISCIPLINE_LEVELS else None
    category = (
        infraction_in.get("category")
        if infraction_in.get("category") in _ALLOWED_DISCIPLINE_CATEGORIES
        else None
    )
    severity = (
        infraction_in.get("severity")
        if infraction_in.get("severity") in _ALLOWED_DISCIPLINE_SEVERITIES
        else None
    )
    return {
        "employee": {
            "name": employee_in.get("name"),
            "title": employee_in.get("title"),
            "department": employee_in.get("department"),
            "manager_name": employee_in.get("manager_name"),
            "manager_email": employee_in.get("manager_email"),
            "employee_email": employee_in.get("employee_email"),
        },
        "infraction": {
            "category": category,
            "category_label": infraction_in.get("category_label"),
            "occurred_on": infraction_in.get("occurred_on"),
            "summary": infraction_in.get("summary"),
            "severity": severity,
            "evidence_urls": [],
        },
        "level": level,
        "draft_status": "drafting",
        "meeting_held_at": None,
        "signature": {
            "method": None,
            "envelope_id": None,
            "requested_at": None,
            "signed_at": None,
            "refused_at": None,
            "refusal_notes": None,
            "signed_pdf_storage_path": None,
        },
        "delivered_status": "draft",
    }


async def patch_discipline(project_id: UUID, patch: dict) -> dict:
    """Deep-merge employee + infraction; replace level when provided.

    Used by the Quick Setup tab and by AI directives that emit discipline_setup updates.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            if "employee" in patch and isinstance(patch["employee"], dict):
                emp = dict(data.get("employee") or {})
                emp.update(patch["employee"])
                data["employee"] = emp
            if "infraction" in patch and isinstance(patch["infraction"], dict):
                infr = dict(data.get("infraction") or {})
                category = patch["infraction"].get("category")
                severity = patch["infraction"].get("severity")
                if category is not None and category not in _ALLOWED_DISCIPLINE_CATEGORIES:
                    raise ValueError(f"Unknown infraction category '{category}'")
                if severity is not None and severity not in _ALLOWED_DISCIPLINE_SEVERITIES:
                    raise ValueError(f"Unknown infraction severity '{severity}'")
                infr.update(patch["infraction"])
                data["infraction"] = infr
            if "level" in patch:
                if patch["level"] not in _ALLOWED_DISCIPLINE_LEVELS:
                    raise ValueError(f"Unknown discipline level '{patch['level']}'")
                data["level"] = patch["level"]
            return await _persist_data(conn, project_id, data)


async def mark_discipline_meeting_held(project_id: UUID) -> dict:
    """Stamp meeting_held_at. Required gate before signature can be requested."""
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            if not data.get("meeting_held_at"):
                data["meeting_held_at"] = _now_iso()
            return await _persist_data(conn, project_id, data)


async def record_discipline_signature_request(
    project_id: UUID,
    *,
    envelope_id: str,
    method: str,
    recipient_email: str,
) -> dict:
    """Record that a signature request was sent (digital path).

    Sets the signature blob and flips draft_status to pending_signature
    so the UI shows the awaiting-signature state.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            sig = dict(data.get("signature") or {})
            sig.update({
                "method": method,
                "envelope_id": envelope_id,
                "requested_at": _now_iso(),
                "recipient_email": recipient_email,
            })
            data["signature"] = sig
            data["draft_status"] = "pending_signature"
            data["delivered_status"] = "active"
            return await _persist_data(conn, project_id, data)


async def record_discipline_signed(
    project_id: UUID,
    *,
    signed_pdf_storage_path: Optional[str] = None,
    method: Optional[str] = None,
) -> dict:
    """Mark a discipline project as signed (digital webhook OR physical upload)."""
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            sig = dict(data.get("signature") or {})
            sig["signed_at"] = _now_iso()
            if signed_pdf_storage_path:
                sig["signed_pdf_storage_path"] = signed_pdf_storage_path
            if method:
                sig["method"] = method
            data["signature"] = sig
            data["draft_status"] = "physically_signed" if method == "physical" else "signed"
            data["delivered_status"] = "closed"
            return await _persist_data(conn, project_id, data)


async def record_discipline_refused(project_id: UUID, *, notes: str) -> dict:
    """Mark a discipline project as refused-to-sign. Closes the workflow."""
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            sig = dict(data.get("signature") or {})
            sig["refused_at"] = _now_iso()
            sig["refusal_notes"] = notes
            data["signature"] = sig
            data["draft_status"] = "refused"
            data["delivered_status"] = "closed"
            return await _persist_data(conn, project_id, data)
