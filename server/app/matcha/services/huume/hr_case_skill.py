"""Huume HR-case skill: write-ups and Matcha Drive from a Huume thread.

Read tools (`list_write_ups`, `search_drive`, `read_drive_file`) and four
staged actions:

  - `hr_case_draft`     (submit_write_up)         — manager or HR
  - `hr_case_decision`  (decide_write_up)         — HR only
  - `hr_case_delivered` (mark_write_up_delivered) — the case's manager or HR
  - `hr_case_signed`    (file_signed_write_up)    — the case's manager or HR

Everything funnels into `services/hr_cases/workflow.py`, the same code the
REST routes use, so authorization (HR vs the case's own manager) and the
leave-law check are identical on both paths.

The staged draft carries a REFERENCE to its source (a thread attachment's
stored URL, a Drive file id, or a Google file id) — never the bytes, which
can't ride the thread's JSON state. The confirm turn fetches the bytes again
and submits exactly what was named. A manager is only ever shown
`workflow.manager_view`; the leave findings behind a hold stay with HR.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

READ_TEXT_CAP = 20_000


async def _actor(conn, user_id: UUID):
    role = await conn.fetchval("SELECT role FROM users WHERE id = $1", user_id)
    return SimpleNamespace(id=user_id, role=role or "client")


async def _is_hr(conn, *, company_id: UUID, user_id: UUID) -> bool:
    from app.matcha.services.hr_cases.access import has_hr_access

    return await has_hr_access(conn, user=await _actor(conn, user_id), company_id=company_id)


def _module_off(features: dict[str, Any], flag: str, label: str) -> Optional[dict[str, Any]]:
    if not (features or {}).get(flag):
        return {"status": "module_off", "message": f"{label} isn't enabled for this company."}
    return None


# ── Read tools ─────────────────────────────────────────────────────────


async def list_write_ups(*, company_id: UUID, user_id: UUID, features: dict[str, Any]) -> dict[str, Any]:
    off = _module_off(features, "hr_cases", "HR cases")
    if off:
        return off
    from app.database import get_connection
    from app.matcha.services.hr_cases import case_service, workflow

    async with get_connection() as conn:
        if await _is_hr(conn, company_id=company_id, user_id=user_id):
            cases = await case_service.list_cases(conn, company_id=company_id)
            return {"status": "ok", "view": "hr", "cases": [
                {
                    "case_id": str(c["id"]), "case_number": c["case_number"], "stage": c["stage_label"],
                    "incident_number": c.get("incident_number"), "employee": c.get("employee_name"),
                    "action_type": c.get("action_type"), "manager": c.get("gm_name"),
                    "allowed_events": c.get("allowed_events"),
                }
                for c in cases[:40]
            ]}
        mine = await workflow.list_for_manager(conn, company_id=company_id, user_id=user_id)
    return {"status": "ok", "view": "manager", "cases": [
        {
            "case_id": str(c["id"]), "case_number": c["case_number"], "stage": c["stage_label"],
            "incident_number": c.get("incident_number"), "employee": c.get("employee_name"),
            "held_for_hr": bool((c.get("review") or {}).get("held_for_hr")),
            "hr_asked": c.get("decision_reason"),
            "can_submit_draft": c["can_submit_draft"], "can_mark_delivered": c["can_mark_delivered"],
        }
        for c in mine
    ]}


async def search_drive(*, company_id: UUID, user_id: UUID, features: dict[str, Any], query: str) -> dict[str, Any]:
    off = _module_off(features, "matcha_drive", "Matcha Drive")
    if off:
        return off
    from app.database import get_connection
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    async with get_connection() as conn:
        actor = await drive_service.load_actor(conn, user=await _actor(conn, user_id), company_id=company_id)
        try:
            results = await drive_service.search(conn, company_id=company_id, q=query, actor=actor, limit=15)
        except DriveError as exc:
            return {"status": "error", "message": exc.detail}
    return {"status": "ok", "files": [
        {"drive_file_id": str(r["id"]), "filename": r["filename"], "folder": r.get("folder_name"),
         "space": r.get("space"), "readable_text": r["text_status"] == "ok"}
        for r in results
    ]}


async def read_drive_file(*, company_id: UUID, user_id: UUID, features: dict[str, Any], file_id: str) -> dict[str, Any]:
    off = _module_off(features, "matcha_drive", "Matcha Drive")
    if off:
        return off
    from app.database import get_connection
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    try:
        fid = UUID(str(file_id))
    except (TypeError, ValueError):
        return {"status": "error", "message": "That doesn't look like a Drive file id."}
    async with get_connection() as conn:
        actor = await drive_service.load_actor(conn, user=await _actor(conn, user_id), company_id=company_id)
        try:
            out = await drive_service.read_file_text(conn, company_id=company_id, file_id=fid, actor=actor,
                                                     max_chars=READ_TEXT_CAP)
        except DriveError as exc:
            return {"status": "error", "message": exc.detail}
    if out["text_status"] != "ok":
        return {"status": "no_text", "filename": out["filename"],
                "message": "There's no readable text in that file (it may be a scan or an image)."}
    return {"status": "ok", "drive_file_id": str(out["id"]), "filename": out["filename"],
            "text": out["text"], "truncated": out["truncated"]}


# ── Stage-time resolution (submit_write_up) ─────────────────────────────


async def resolve_draft_args(
    *, company_id: UUID, args: dict[str, Any], attachment_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Turn the model's args into a stageable dict: resolve the employee by
    name, and pin the draft's source to a concrete reference. Returns
    {"status": "ok", ...fields} or {"status": "refused", "message": ...}."""
    from app.database import get_connection
    from app.matcha.services.drive.google_drive_service import parse_file_id

    out: dict[str, Any] = {}
    sources = [k for k in ("attachment_index", "drive_file_id", "google_url") if args.get(k) not in (None, "")]
    if len(sources) != 1:
        return {"status": "refused", "message": "Tell me which one file is the write-up: an attachment in this chat, a Drive file, or a Google Doc link."}
    source = sources[0]
    if source == "attachment_index":
        try:
            idx = int(args["attachment_index"])
        except (TypeError, ValueError):
            return {"status": "refused", "message": "Which attachment is the write-up?"}
        newest_first = list(reversed(attachment_refs or []))
        if not 0 <= idx < len(newest_first):
            return {"status": "refused", "message": "I don't see that attachment in this chat. Attach the write-up and try again."}
        ref = newest_first[idx]
        out.update(source="attachment", attachment_url=ref["url"], filename=ref.get("filename"))
    elif source == "drive_file_id":
        out.update(source="drive", drive_file_id=str(args["drive_file_id"]))
    else:
        gid = parse_file_id(str(args["google_url"]))
        if not gid:
            return {"status": "refused", "message": "That isn't a Google Doc or Drive file link."}
        out.update(source="google", google_file_id=gid)

    employee_id = args.get("employee_id")
    name = str(args.get("employee_name") or "").strip()
    async with get_connection() as conn:
        if employee_id:
            row = await conn.fetchrow(
                "SELECT id, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS name "
                "FROM employees WHERE id::text = $1 AND org_id = $2", str(employee_id), company_id,
            )
            rows = [row] if row else []
        elif name:
            rows = await conn.fetch(
                "SELECT id, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS name "
                "FROM employees WHERE org_id = $1 AND termination_date IS NULL "
                "AND (COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) ILIKE $2 ESCAPE '\\' "
                "ORDER BY last_name, first_name LIMIT 5",
                company_id, "%" + name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
            )
        else:
            rows = []
    if not rows:
        return {"status": "refused", "message": "Who is the write-up for? I couldn't find that employee on the roster."}
    if len(rows) > 1:
        return {"status": "refused", "message": "More than one employee matches: "
                + ", ".join(r["name"] for r in rows) + ". Which one?"}
    out.update(employee_id=str(rows[0]["id"]), employee_name=rows[0]["name"])
    return {"status": "ok", **out}


# ── Execution ──────────────────────────────────────────────────────────


async def _fetch_bytes(conn, *, company_id: UUID, user_id: UUID, action: dict[str, Any]) -> tuple[str, bytes, str, Optional[str]]:
    """(filename, bytes, source, source_ref) for a staged reference."""
    from app.core.services.storage import get_storage
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.google_drive_service import GoogleDriveService

    source = action.get("source")
    if source == "attachment":
        data = await get_storage().download_file(action["attachment_url"])
        return action.get("filename") or "write-up", data, "huume", None
    if source == "drive":
        actor = await drive_service.load_actor(conn, user=await _actor(conn, user_id), company_id=company_id)
        meta, data = await drive_service.read_file_bytes(
            conn, company_id=company_id, file_id=UUID(action["drive_file_id"]), actor=actor,
        )
        return meta["filename"], data, "huume", f"drive:{action['drive_file_id']}"
    fetched = await GoogleDriveService(user_id).fetch_file(action["google_file_id"])
    return fetched.name, fetched.data, "google_drive", fetched.file_id


async def _fetch_source(conn, *, company_id: UUID, user_id: UUID, action: dict[str, Any]):
    """(prepared, source, source_ref) for the staged reference."""
    from app.matcha.services.drive import drive_service

    name, data, source, ref = await _fetch_bytes(conn, company_id=company_id, user_id=user_id, action=action)
    return await drive_service.prepare_file(name, data), source, ref


def resolve_signed_args(*, args: dict[str, Any], attachment_refs: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure. Pin the signed copy to one attachment or Drive file."""
    try:
        UUID(str(args.get("case_id") or ""))
    except (TypeError, ValueError):
        return {"status": "refused", "message": "Which write-up is this the signed copy for? list_write_ups has the case_id."}
    sources = [k for k in ("attachment_index", "drive_file_id") if args.get(k) not in (None, "")]
    if len(sources) != 1:
        return {"status": "refused", "message": "Attach the signed copy here (or name the Drive file) and I'll file it."}
    if sources[0] == "drive_file_id":
        return {"status": "ok", "source": "drive", "drive_file_id": str(args["drive_file_id"])}
    try:
        idx = int(args["attachment_index"])
    except (TypeError, ValueError):
        return {"status": "refused", "message": "Which attachment is the signed copy?"}
    newest_first = list(reversed(attachment_refs or []))
    if not 0 <= idx < len(newest_first):
        return {"status": "refused", "message": "I don't see that attachment in this chat. Attach the signed copy and try again."}
    ref = newest_first[idx]
    return {"status": "ok", "source": "attachment", "attachment_url": ref["url"], "filename": ref.get("filename")}


async def execute(*, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any]) -> dict[str, Any]:
    from datetime import date as _date

    from app.database import get_connection
    from app.matcha.services.drive.drive_service import DriveError
    from app.matcha.services.drive.google_drive_service import GoogleDriveError
    from app.matcha.services.hr_cases import workflow
    from app.matcha.services.hr_cases.case_service import CaseError

    atype = action.get("type")
    try:
        async with get_connection() as conn:
            is_hr = await _is_hr(conn, company_id=company_id, user_id=actor_user_id)
            if atype == "hr_case_draft":
                prepared, source, source_ref = await _fetch_source(
                    conn, company_id=company_id, user_id=actor_user_id, action=action,
                )
                result = await workflow.submit_draft(
                    conn, company_id=company_id, actor_user_id=actor_user_id, actor_is_hr=is_hr,
                    prepared=prepared, employee_id=UUID(action["employee_id"]),
                    action_type=action["action_type"], infraction_type=action["infraction_type"],
                    occurrence_dates=workflow.parse_occurrence_dates(action.get("occurrence_dates") or []),
                    case_id=UUID(action["case_id"]) if action.get("case_id") else None,
                    incident_id=UUID(action["incident_id"]) if action.get("incident_id") else None,
                    source=source, source_ref=source_ref, origin="huume",
                )
                case = result["case"]
                if result["status"] == "held":
                    msg = (f"{case['case_number']}: that write-up can't go forward as written — it conflicts "
                           "with a protected-leave rule. HR has the details and has been told.")
                    if is_hr:
                        msg += " " + " ".join(b["detail"] for b in (case.get("review") or {}).get("blocks") or [])
                else:
                    notes = [n["detail"] for n in (result["manager_view"].get("review") or {}).get("notes") or []]
                    msg = f"{case['case_number']}: sent to HR for review."
                    if notes:
                        msg += " A few things HR will likely ask about: " + " ".join(notes)
                return {"status": "created", "message": msg, "record_id": str(case["id"]),
                        "record_label": case["case_number"], "case_view": result["manager_view"]}
            if atype == "hr_case_decision":
                if not is_hr:
                    return {"status": "refused", "message": "Only HR can approve or send back a write-up."}
                case = await workflow.decide(
                    conn, company_id=company_id, case_id=UUID(action["case_id"]),
                    actor_user_id=actor_user_id, decision=action["decision"], reason=action.get("reason"),
                )
                verb = "Approved to deliver" if action["decision"] == "approve" else "Sent back to the manager"
                return {"status": "created", "message": f"{case['case_number']}: {verb.lower()}.",
                        "record_id": str(case["id"]), "record_label": case["case_number"]}
            if atype == "hr_case_signed":
                name, data, _source, _ref = await _fetch_bytes(
                    conn, company_id=company_id, user_id=actor_user_id, action=action,
                )
                out = await workflow.upload_signed(
                    conn, company_id=company_id, case_id=UUID(action["case_id"]),
                    actor_user_id=actor_user_id, actor_is_hr=is_hr, filename=name, data=data,
                )
                case = out["case"]
                return {
                    "status": "created",
                    "message": f"{case['case_number']}: signed copy filed. I'm checking it now — "
                               "you'll get a notice if anything needs fixing.",
                    "record_id": str(case["id"]), "record_label": case["case_number"],
                    "bg_tasks": [(workflow.check_signed_and_notify, (), {
                        "company_id": company_id, "case_id": case["id"], "data": data,
                        "mime_type": out["mime_type"], "actor_user_id": actor_user_id,
                    })],
                }
            if atype == "hr_case_delivered":
                delivered_on = _date.fromisoformat(action["delivered_on"]) if action.get("delivered_on") else None
                case = await workflow.mark_delivered(
                    conn, company_id=company_id, case_id=UUID(action["case_id"]),
                    actor_user_id=actor_user_id, actor_is_hr=is_hr, delivered_on=delivered_on,
                )
                return {"status": "created",
                        "message": f"{case['case_number']}: marked delivered. Upload the signed copy when you have it.",
                        "record_id": str(case["id"]), "record_label": case["case_number"]}
    except CaseError as exc:
        return {"status": "refused", "message": exc.detail}
    except (DriveError, GoogleDriveError) as exc:
        return {"status": "refused", "message": exc.detail}
    return {"status": "error", "message": "Unsupported action."}
