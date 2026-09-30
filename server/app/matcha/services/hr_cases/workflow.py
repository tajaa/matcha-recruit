"""Write-up workflow on an HR case: manager submits a draft → review → HR
approves or sends back → manager delivers.

Authorization lives here, not in the routes, so REST and Huume enforce the
same thing:
  - HR (Work admin, or READ on Drive's HR / Discipline folder) may act on
    any case.
  - The case's manager (`gm_user_id`) may submit drafts and mark delivery on
    their own case, and sees only `manager_view`.
  - Any business user may start a case by submitting a draft; they become
    that case's manager.
  - Approve / request changes are HR-only.

Draft files are always stored in Drive's `HR / Discipline / Drafts` folder
through the system path, whatever the manager's own Drive access — the
manager can submit into HR without being able to browse it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Optional
from uuid import UUID

from . import case_service, draft_review, notifications
from .case_service import ACTION_TYPES, CaseError

logger = logging.getLogger(__name__)

DRAFTABLE_STAGES = ("flagged", "drafting", "changes_requested")
MIN_CHANGE_REASON = 20
MAX_OCCURRENCE_DATES = 30


def parse_occurrence_dates(values: Iterable[Any]) -> list[date]:
    out: list[date] = []
    for v in values or []:
        if isinstance(v, date):
            out.append(v)
            continue
        text = str(v or "").strip()
        if not text:
            continue
        try:
            out.append(date.fromisoformat(text))
        except ValueError:
            raise CaseError(400, f"'{text}' isn't a date (use YYYY-MM-DD).") from None
    if len(out) > MAX_OCCURRENCE_DATES:
        raise CaseError(400, "That's a lot of dates for one write-up — list the specific occurrences.")
    if any(d > date.today() for d in out):
        raise CaseError(400, "Occurrence dates can't be in the future.")
    return sorted(set(out))


def manager_view(case: dict[str, Any]) -> dict[str, Any]:
    """What the manager on a case sees: progress and their own draft's notes,
    never the leave-law findings, triage matches or HR's internal history."""
    stage = case["stage"]
    return {
        "id": case["id"],
        "case_number": case["case_number"],
        "stage": stage,
        "stage_label": case.get("stage_label"),
        "checklist": case.get("checklist"),
        "incident_id": case.get("source_incident_id"),
        "incident_number": case.get("incident_number"),
        "incident_title": case.get("incident_title"),
        "employee_id": case.get("employee_id"),
        "employee_name": case.get("employee_name"),
        "action_type": case.get("action_type"),
        "review": draft_review.for_manager(case.get("review")),
        "decision": case.get("decision"),
        "decision_reason": case.get("decision_reason") if case.get("decision") == "changes_requested" else None,
        "delivered_at": case.get("delivered_at"),
        "has_draft": bool(case.get("draft_file_id")),
        "can_submit_draft": stage in DRAFTABLE_STAGES,
        "can_mark_delivered": stage == "approved",
        "can_upload_signed": stage in ("delivered", "needs_attention"),
        "signed_check": manager_signed_check(case),
        "updated_at": case.get("updated_at"),
    }


def _authorize(case: dict[str, Any], *, actor_user_id: UUID, actor_is_hr: bool) -> None:
    if actor_is_hr or (case.get("gm_user_id") and case["gm_user_id"] == actor_user_id):
        return
    raise CaseError(404, "That case doesn't exist.")


async def load_for_actor(conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID, actor_is_hr: bool) -> dict[str, Any]:
    case = await case_service.get_case(conn, company_id=company_id, case_id=case_id)
    _authorize(case, actor_user_id=actor_user_id, actor_is_hr=actor_is_hr)
    return case


async def list_for_manager(conn, *, company_id: UUID, user_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        case_service._CASE_SELECT
        + " WHERE c.company_id = $1 AND c.gm_user_id = $2"
        " AND (c.stage NOT IN ('closed', 'dismissed') OR c.closed_at > NOW() - INTERVAL '30 days')"
        " ORDER BY c.updated_at DESC LIMIT 100",
        company_id, user_id,
    )
    return [manager_view(case_service.serialize(r)) for r in rows]


async def store_draft_file(conn, *, company_id: UUID, case_number: str, prepared, uploaded_by: UUID,
                           source: str = "upload", source_ref: Optional[str] = None) -> dict[str, Any]:
    from app.matcha.services.drive import drive_service

    folders = await drive_service.ensure_system_folders(conn, company_id)
    return await drive_service.store_file(
        conn, company_id=company_id, folder_id=folders["hr_discipline_drafts"], prepared=prepared,
        uploaded_by=uploaded_by, actor=None, source=source, source_ref=source_ref,
        filename=f"{case_number} - draft - {prepared.filename}",
    )


async def submit_draft(
    conn,
    *,
    company_id: UUID,
    actor_user_id: UUID,
    actor_is_hr: bool,
    prepared,
    employee_id: UUID,
    action_type: str,
    infraction_type: str,
    occurrence_dates: list[date],
    case_id: Optional[UUID] = None,
    incident_id: Optional[UUID] = None,
    source: str = "upload",
    source_ref: Optional[str] = None,
    origin: str = "gm_draft",
) -> dict[str, Any]:
    """Store the draft in HR / Discipline / Drafts, review it, and either send
    it to HR (`submitted`) or hold it (`held`) when the leave check blocks.
    Returns {status, case, manager_view}."""
    if action_type not in ACTION_TYPES:
        raise CaseError(400, "Pick the kind of action (verbal, written, final warning, suspension, PIP or other).")
    if infraction_type not in draft_review.INFRACTION_TYPES:
        raise CaseError(400, "Pick what the write-up is about (attendance, performance, conduct, safety or policy).")
    if prepared.text_status != "ok" or not prepared.extracted_text:
        raise CaseError(400, "I can't read the text in that file. Send a PDF with selectable text, a Word document, or a Google Doc.")

    employee = await conn.fetchrow(
        "SELECT id, NULLIF(TRIM(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')), '') AS name "
        "FROM employees WHERE id = $1 AND org_id = $2",
        employee_id, company_id,
    )
    if not employee:
        raise CaseError(404, "That employee isn't on this company's roster.")

    # Resolve (or open) the case.
    if case_id:
        case = await load_for_actor(conn, company_id=company_id, case_id=case_id,
                                    actor_user_id=actor_user_id, actor_is_hr=actor_is_hr)
    else:
        case = None
        if incident_id:
            exists = await conn.fetchval(
                "SELECT 1 FROM ir_incidents WHERE id = $1 AND company_id = $2", incident_id, company_id,
            )
            if not exists:
                raise CaseError(404, "That incident doesn't exist.")
            case = await case_service.find_open_case_for_incident(conn, company_id=company_id, incident_id=incident_id)
        if case is None:
            case, _ = await case_service.open_case(
                conn, company_id=company_id, origin=origin, incident_id=incident_id,
                gm_user_id=actor_user_id, opened_by=actor_user_id, employee_id=employee_id,
            )
        elif not case.get("gm_user_id"):
            await case_service.set_fields(conn, company_id=company_id, case_id=case["id"],
                                          sets={"gm_user_id": actor_user_id})
            case = await case_service.get_case(conn, company_id=company_id, case_id=case["id"])
        else:
            _authorize(case, actor_user_id=actor_user_id, actor_is_hr=actor_is_hr)

    if case["stage"] not in DRAFTABLE_STAGES:
        raise CaseError(409, f"This case is {case['stage_label'].lower()} — a new draft can't be sent now.")

    stored = await store_draft_file(conn, company_id=company_id, case_number=case["case_number"],
                                    prepared=prepared, uploaded_by=actor_user_id,
                                    source=source, source_ref=source_ref)
    await conn.execute(
        "UPDATE drive_files SET linked_type = 'hr_case', linked_id = $2 WHERE id = $1",
        stored["id"], case["id"],
    )

    incident_account = None
    if case.get("source_incident_id"):
        incident_account = await conn.fetchval(
            "SELECT description FROM ir_incidents WHERE id = $1", case["source_incident_id"],
        )
    policy_titles = [v.get("policy_title") for v in ((case.get("triage") or {}).get("violations") or [])]
    review = await draft_review.review_draft(
        conn, company_id=company_id, employee_id=employee_id, employee_name=employee["name"],
        text=prepared.extracted_text, action_type=action_type, infraction_type=infraction_type,
        occurrence_dates=occurrence_dates, case_id=case["id"],
        incident_account=incident_account, policy_titles=[t for t in policy_titles if t],
    )
    review["input"] = {
        "infraction_type": infraction_type, "action_type": action_type,
        "occurrence_dates": [d.isoformat() for d in occurrence_dates], "file_id": str(stored["id"]),
    }
    sets = {
        "draft_file_id": stored["id"], "review": review, "employee_id": employee_id,
        "action_type": action_type, "occurrence_dates": occurrence_dates,
    }
    if review["blocks"]:
        await case_service.set_fields(
            conn, company_id=company_id, case_id=case["id"], sets=sets, event="draft_held",
            actor_user_id=actor_user_id, details={"file_id": str(stored["id"]), "block_codes": [b["code"] for b in review["blocks"]]},
        )
        case = await case_service.get_case(conn, company_id=company_id, case_id=case["id"])
        await notifications.notify_step(conn, case=case, step="draft_held", actor_user_id=actor_user_id)
        status = "held"
    else:
        case = await case_service.apply_event(
            conn, company_id=company_id, case_id=case["id"], event="draft_submitted",
            actor_user_id=actor_user_id, sets=sets,
            details={"file_id": str(stored["id"]), "advisory_count": len(review["advisories"])},
        )
        await notifications.notify_step(conn, case=case, step="draft_submitted", actor_user_id=actor_user_id)
        status = "submitted"
    return {"status": status, "case": case, "manager_view": manager_view(case)}


async def decide(
    conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID, decision: str, reason: Optional[str],
) -> dict[str, Any]:
    """HR-only (the caller has already checked HR access). Approval re-runs
    the deterministic leave check: leave records can change between review
    and approval."""
    reason = (reason or "").strip() or None
    case = await case_service.get_case(conn, company_id=company_id, case_id=case_id)
    if decision == "request_changes":
        if not reason or len(reason) < MIN_CHANGE_REASON:
            raise CaseError(400, f"Tell the manager what to change (at least {MIN_CHANGE_REASON} characters).")
        case = await case_service.apply_event(
            conn, company_id=company_id, case_id=case_id, event="request_changes", actor_user_id=actor_user_id,
            sets={"decision": "changes_requested", "decision_reason": reason[:2000],
                  "decided_by": actor_user_id, "decided_at": datetime.now(timezone.utc)},
        )
        await notifications.notify_step(conn, case=case, step="changes_requested",
                                        actor_user_id=actor_user_id, reason=reason[:500])
        return case
    if decision != "approve":
        raise CaseError(400, "Decision must be approve or request_changes.")

    inputs = (case.get("review") or {}).get("input") or {}
    if case["stage"] == "hr_review" and case.get("employee_id") and inputs:
        from app.matcha.services.discipline.discipline_compliance import check_discipline_compliance

        verdict = await check_discipline_compliance(
            conn, company_id=company_id, employee_id=case["employee_id"],
            infraction_type=inputs.get("infraction_type") or "policy_violation",
            occurrence_dates=[date.fromisoformat(d) for d in inputs.get("occurrence_dates") or []],
        )
        if verdict.get("blocks"):
            raise CaseError(409, "Leave records changed since this draft was reviewed and it now conflicts with a "
                                 "protected-leave rule. It can't be approved as written.")
    case = await case_service.apply_event(
        conn, company_id=company_id, case_id=case_id, event="approve", actor_user_id=actor_user_id,
        sets={"decision": "approved", "decision_reason": reason[:2000] if reason else None,
              "decided_by": actor_user_id, "decided_at": datetime.now(timezone.utc)},
    )
    await notifications.notify_step(conn, case=case, step="approved", actor_user_id=actor_user_id)
    return case


async def mark_delivered(
    conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID, actor_is_hr: bool,
    delivered_on: Optional[date] = None,
) -> dict[str, Any]:
    case = await load_for_actor(conn, company_id=company_id, case_id=case_id,
                                actor_user_id=actor_user_id, actor_is_hr=actor_is_hr)
    today = date.today()
    delivered_on = delivered_on or today
    if delivered_on > today:
        raise CaseError(400, "The delivery date can't be in the future.")
    decided = case.get("decided_at")
    if decided and delivered_on < decided.date():
        raise CaseError(400, "The delivery date is before HR approved the write-up.")
    when = (datetime.now(timezone.utc) if delivered_on == today
            else datetime.combine(delivered_on, time(12, 0), tzinfo=timezone.utc))
    case = await case_service.apply_event(
        conn, company_id=company_id, case_id=case_id, event="delivered", actor_user_id=actor_user_id,
        sets={"delivered_at": when, "delivered_by": actor_user_id},
    )
    await notifications.notify_step(conn, case=case, step="delivered", actor_user_id=actor_user_id)
    return case


# ── Signed copy (6/6) ───────────────────────────────────────────────────

# Reasons the manager can fix by uploading again. Comments and a noted refusal
# are HR's to handle, so they don't go back to the manager.
MANAGER_FIXABLE_REASONS = (
    "unreadable_pdf", "encrypted_pdf", "empty_pdf", "illegible_scan",
    "employee_signature_missing", "signature_name_mismatch", "letter_mismatch", "pages_missing",
)


async def upload_signed(
    conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID, actor_is_hr: bool,
    filename: str, data: bytes,
) -> dict[str, Any]:
    """File the signed copy under the company's filename template in
    `HR / Discipline / Signed / <Last, First>` and move the case to
    `verifying`. Returns {case, mime_type}; the caller then runs the check."""
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    from . import verification

    case = await load_for_actor(conn, company_id=company_id, case_id=case_id,
                                actor_user_id=actor_user_id, actor_is_hr=actor_is_hr)
    if "signed_uploaded" not in (case.get("allowed_events") or []):
        raise CaseError(409, f"This case is {case['stage_label'].lower()} — a signed copy can't be added now.")
    try:
        ext, mime = verification.validate_signed_upload(filename, data)
    except ValueError as exc:
        raise CaseError(400, str(exc)) from None
    employee = await conn.fetchrow(
        "SELECT first_name, last_name FROM employees WHERE id = $1 AND org_id = $2",
        case.get("employee_id"), company_id,
    ) if case.get("employee_id") else None
    employee = dict(employee) if employee else {}
    settings = await case_service.get_settings(conn, company_id)
    name = verification.render_filename(
        settings.get("filename_template") or verification.DEFAULT_TEMPLATE,
        values=verification.filename_values(case, employee), extension=ext,
    )
    folder_id = await verification.ensure_employee_folder(conn, company_id=company_id, employee=employee)
    try:
        prepared = await drive_service.prepare_file(name, data)
        stored = await drive_service.store_file(
            conn, company_id=company_id, folder_id=folder_id, prepared=prepared, uploaded_by=actor_user_id,
            actor=None, source="upload", linked_type="hr_case", linked_id=case_id, filename=name,
        )
    except DriveError as exc:
        raise CaseError(exc.status, exc.detail) from None
    case = await case_service.apply_event(
        conn, company_id=company_id, case_id=case_id, event="signed_uploaded", actor_user_id=actor_user_id,
        sets={"signed_file_id": stored["id"]}, details={"file_id": str(stored["id"]), "filename": name},
    )
    return {"case": case, "mime_type": mime}


async def check_signed_and_notify(
    *, company_id: UUID, case_id: UUID, data: bytes, mime_type: str, actor_user_id: Optional[UUID],
) -> None:
    """Background step after `upload_signed`. Never raises."""
    from app.database import get_connection

    from . import verification

    try:
        async with get_connection() as conn:
            case = await verification.run_check(
                conn, company_id=company_id, case_id=case_id, data=data, mime_type=mime_type,
                actor_user_id=actor_user_id,
            )
            await notifications.notify_signed(conn, case=case, actor_user_id=actor_user_id)
    except Exception:
        logger.exception("[hr_cases] signed-copy check failed for case %s", case_id)


async def recheck_signed(conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID) -> dict[str, Any]:
    """HR: run the check again on the filed copy (e.g. after check_unavailable)."""
    from app.core.services.storage import get_storage

    from . import verification

    case = await case_service.get_case(conn, company_id=company_id, case_id=case_id)
    if case["stage"] != "needs_attention" or not case.get("signed_file_id"):
        raise CaseError(409, "There's no signed copy waiting on a re-check.")
    row = await conn.fetchrow(
        "SELECT filename, storage_path, content_type FROM drive_files WHERE id = $1 AND company_id = $2",
        case["signed_file_id"], company_id,
    )
    if not row:
        raise CaseError(404, "The signed copy is no longer in Drive.")
    data = await get_storage().download_file(row["storage_path"])
    await case_service.apply_event(conn, company_id=company_id, case_id=case_id, event="signed_uploaded",
                                   actor_user_id=actor_user_id, details={"recheck": True})
    case = await verification.run_check(conn, company_id=company_id, case_id=case_id, data=data,
                                        mime_type=row["content_type"] or "application/pdf", actor_user_id=actor_user_id)
    await notifications.notify_signed(conn, case=case, actor_user_id=actor_user_id)
    return case


async def acknowledge(conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID) -> dict[str, Any]:
    """HR has dealt with what the check flagged; close the case."""
    return await case_service.apply_event(
        conn, company_id=company_id, case_id=case_id, event="acknowledge", actor_user_id=actor_user_id,
        sets={"attention_acknowledged_by": actor_user_id, "attention_acknowledged_at": datetime.now(timezone.utc)},
    )


def manager_signed_check(case: dict[str, Any]) -> Optional[dict[str, Any]]:
    """What the manager hears about the signed-copy check: only the problems
    a new upload can fix."""
    from . import verification

    v = case.get("verification")
    if not v:
        return None
    fixable = [r for r in v.get("reasons") or [] if r in MANAGER_FIXABLE_REASONS]
    return {
        "outcome": "verified" if v.get("outcome") == "verified" else ("fix_needed" if fixable else "with_hr"),
        "problems": [verification.REASON_TEXT[r] for r in fixable],
    }
