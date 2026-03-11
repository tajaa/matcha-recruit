"""Matcha Work — chat-driven AI workspace for HR document elements."""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, status
from fastapi.responses import StreamingResponse

from ...core.models.auth import CurrentUser
from ...core.services.compliance_service import get_location_requirements, get_locations
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id, require_feature
from ..services.model_pricing import calculate_call_cost
from ..models.matcha_work import (
    CreateThreadRequest,
    CreateThreadResponse,
    DocumentVersionResponse,
    ElementListItem,
    FinalizeResponse,
    HandbookDocument,
    MWMessageOut,
    OnboardingDocument,
    PolicyDocument,
    PresentationDocument,
    ReviewDocument,
    RevertRequest,
    SaveDraftResponse,
    SendMessageRequest,
    SendMessageResponse,
    PinThreadRequest,
    ThreadDetailResponse,
    ThreadListItem,
    OfferLetterDocument,
    UsageSummaryResponse,
    UpdateTitleRequest,
    SendReviewRequestsRequest,
    SendReviewRequestsResponse,
    ReviewRequestStatus,
    PublicReviewRequestResponse,
    PublicReviewSubmitRequest,
    PublicReviewSubmitResponse,
    SendHandbookSignaturesRequest,
    SendHandbookSignaturesResponse,
    GeneratePresentationResponse,
    WorkbookDocument,
)
from ..services import matcha_work_document as doc_svc
from ..services import billing_service
from ..services.er_document_parser import ERDocumentParser
from ..services.matcha_work_handbook_upload import AuditedLocation, audit_uploaded_handbook, check_handbook_relevance
from ..services.matcha_work_ai import get_ai_provider, _infer_skill_from_state, _build_company_context, compact_conversation
from ..services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)
from ...core.services.email import get_email_service
from ...core.services.handbook_service import HandbookService

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_feature("matcha_work"))])
public_router = APIRouter()

VALID_OFFER_LETTER_FIELDS = set(OfferLetterDocument.model_fields.keys()) - {"company_logo_url"}
VALID_REVIEW_FIELDS = set(ReviewDocument.model_fields.keys())
VALID_WORKBOOK_FIELDS = set(WorkbookDocument.model_fields.keys()) - {"images"}
VALID_ONBOARDING_FIELDS = set(OnboardingDocument.model_fields.keys())
VALID_PRESENTATION_FIELDS = set(PresentationDocument.model_fields.keys()) - {"cover_image_url"}
HANDBOOK_UPLOAD_MANAGED_FIELDS = {
    "handbook_source_type",
    "handbook_upload_status",
    "handbook_uploaded_file_url",
    "handbook_uploaded_filename",
    "handbook_blocking_error",
    "handbook_review_locations",
    "handbook_red_flags",
    "handbook_green_flags",
    "handbook_jurisdiction_summaries",
    "handbook_analysis_generated_at",
}
VALID_HANDBOOK_FIELDS = set(HandbookDocument.model_fields.keys()) - HANDBOOK_UPLOAD_MANAGED_FIELDS
VALID_POLICY_FIELDS = set(PolicyDocument.model_fields.keys())

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
HANDBOOK_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx"}
HANDBOOK_UPLOAD_MAX_BYTES = 10 * 1024 * 1024


def _validate_updates_for_skill(skill: str, updates: dict) -> dict:
    """Filter AI updates to known fields for the inferred skill."""
    if skill == "offer_letter":
        valid_fields = VALID_OFFER_LETTER_FIELDS
    elif skill == "review":
        valid_fields = VALID_REVIEW_FIELDS
    elif skill == "onboarding":
        valid_fields = VALID_ONBOARDING_FIELDS
    elif skill == "workbook":
        valid_fields = VALID_WORKBOOK_FIELDS
    elif skill == "presentation":
        valid_fields = VALID_PRESENTATION_FIELDS
    elif skill == "handbook":
        valid_fields = VALID_HANDBOOK_FIELDS
    elif skill == "policy":
        valid_fields = VALID_POLICY_FIELDS
    else:
        return {}
    return {k: v for k, v in updates.items() if k in valid_fields}


def _row_to_message(row: dict) -> MWMessageOut:
    return MWMessageOut(
        id=row["id"],
        thread_id=row["thread_id"],
        role=row["role"],
        content=row["content"],
        version_created=row.get("version_created"),
        created_at=row["created_at"],
    )


def _location_label(location: dict) -> str:
    city = str(location.get("city") or "").strip()
    state = str(location.get("state") or "").strip().upper()
    return f"{city}, {state}" if city else state


def _thread_accepts_handbook_upload(thread: dict) -> bool:
    current_state = thread.get("current_state") or {}
    current_skill = _infer_skill_from_state(current_state)
    if current_skill == "chat":
        return True
    if current_skill != "handbook":
        return False
    source_type = current_state.get("handbook_source_type")
    # Allow upload if already in upload mode OR if source type hasn't been
    # committed yet (user started chatting about a handbook but can still
    # switch to upload mode via the paperclip button).
    if source_type in ("upload", None):
        return True
    return False


def _build_handbook_block_message(location_labels: list[str]) -> str:
    if not location_labels:
        return (
            "Handbook upload audit is blocked because no active Compliance Locations were found. "
            "Add or sync company locations in /compliance first."
        )
    if len(location_labels) == 1:
        scoped = location_labels[0]
    else:
        scoped = ", ".join(location_labels[:6])
        if len(location_labels) > 6:
            scoped += f", and {len(location_labels) - 6} more"
    return (
        "Handbook upload audit is blocked because these active Compliance Locations are not fully synced: "
        f"{scoped}. Fix /compliance coverage first, then retry the upload."
    )


def _build_handbook_upload_summary(
    *,
    file_name: str,
    reviewed_locations: list[str],
    red_flags: list[dict],
    green_flags: list[dict] | None = None,
    jurisdiction_summaries: list[dict] | None = None,
    blocked_message: Optional[str] = None,
) -> str:
    if blocked_message:
        return blocked_message

    passing_count = len(green_flags or [])
    gap_count = len(red_flags)

    if not red_flags:
        return (
            f"Uploaded {file_name} and reviewed it against {len(reviewed_locations)} active Compliance Location(s). "
            f"{passing_count} requirement(s) covered, no jurisdiction coverage gaps detected."
        )

    counts = {"high": 0, "medium": 0, "low": 0}
    for row in red_flags:
        severity = str(row.get("severity") or "medium").lower()
        if severity in counts:
            counts[severity] += 1

    severity_bits = []
    for severity in ("high", "medium", "low"):
        count = counts[severity]
        if count:
            severity_bits.append(f"{count} {severity}")

    severity_summary = ", ".join(severity_bits) if severity_bits else f"{gap_count} issue(s)"

    # Per-jurisdiction coverage snippet
    jurisdiction_bits: list[str] = []
    for js in (jurisdiction_summaries or []):
        jurisdiction_bits.append(f"{js['location_label']} {js['covered_count']}/{js['total_count']}")
    jurisdiction_snippet = (" | ".join(jurisdiction_bits) + ".") if jurisdiction_bits else ""

    return (
        f"Uploaded {file_name} and reviewed it against {len(reviewed_locations)} active Compliance Location(s). "
        f"{passing_count} passing, {severity_summary} red flag(s). "
        + (f"Coverage: {jurisdiction_snippet} " if jurisdiction_snippet else "")
        + "Review the Preview panel for details."
    )


async def _build_thread_detail_response(thread_id: UUID, company_id: UUID) -> ThreadDetailResponse:
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread["current_state"] = await doc_svc.ensure_matcha_work_thread_storage_scope(
        thread_id,
        company_id,
        thread["current_state"],
    )
    messages = await doc_svc.get_thread_messages(thread_id)
    return ThreadDetailResponse(
        id=thread["id"],
        title=thread["title"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
        task_type=_infer_skill_from_state(thread["current_state"]),
        is_pinned=thread.get("is_pinned", False),
        linked_offer_letter_id=thread.get("linked_offer_letter_id"),
        created_at=thread["created_at"],
        updated_at=thread["updated_at"],
        messages=[_row_to_message(row) for row in messages],
    )


def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _append_action_note(reply: str, note: Optional[str]) -> str:
    clean_note = (note or "").strip()
    if not clean_note:
        return reply
    clean_reply = (reply or "").strip()
    if not clean_reply:
        return clean_note
    return f"{clean_reply}\n\n{clean_note}"


def _extract_emails_from_text(text: str) -> list[str]:
    if not text:
        return []
    return doc_svc.normalize_recipient_emails(EMAIL_REGEX.findall(text))


def _looks_like_send_draft_command(content: str) -> bool:
    text = (content or "").lower()
    if not text:
        return False
    has_send = bool(re.search(r"\b(send|email)\b", text))
    has_draft_context = bool(re.search(r"\b(draft|offer(?:\s+letter)?)\b", text))
    has_email = bool(_extract_emails_from_text(content))
    return has_send and has_draft_context and has_email


def _collect_offer_draft_recipients(
    *,
    structured_update: Optional[dict],
    current_state: dict,
    user_message: str,
) -> list[str]:
    collected: list[str] = []

    if isinstance(structured_update, dict):
        raw_recipients = structured_update.get("recipient_emails")
        if isinstance(raw_recipients, list):
            collected.extend(str(v) for v in raw_recipients if str(v).strip())
        elif isinstance(raw_recipients, str) and raw_recipients.strip():
            collected.append(raw_recipients)

        for key in ("candidate_email", "review_recipient_email"):
            raw_email = structured_update.get(key)
            if isinstance(raw_email, str) and raw_email.strip():
                collected.append(raw_email)

    state_recipients = current_state.get("recipient_emails")
    if isinstance(state_recipients, list):
        collected.extend(str(v) for v in state_recipients if str(v).strip())

    candidate_email = current_state.get("candidate_email")
    if isinstance(candidate_email, str) and candidate_email.strip():
        collected.append(candidate_email)

    collected.extend(_extract_emails_from_text(user_message))
    return doc_svc.normalize_recipient_emails(collected)


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _coerce_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


async def _send_mw_provisioning_email(
    *,
    company_id: UUID,
    personal_email: str,
    employee_name: str,
    work_email: str,
    google_result: dict | None,
    slack_result: dict | None,
) -> None:
    """Send a welcome email with provisioning credentials for Matcha Work onboarding."""
    temp_password: str | None = None
    if google_result:
        temp_password = google_result.get("initial_password")

    slack_invite_link: str | None = None
    slack_workspace_name: str | None = None
    if slack_result:
        for step in slack_result.get("steps") or []:
            resp = step.get("last_response") or {}
            if resp.get("invite_link"):
                slack_invite_link = resp["invite_link"]
                break

    google_succeeded = google_result and google_result.get("status") == "completed"
    slack_succeeded = slack_result and slack_result.get("status") == "completed"

    if not google_succeeded and not slack_succeeded:
        return

    async with get_connection() as conn:
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1", company_id,
        ) or "Your Company"
        if slack_succeeded:
            slack_config_row = await conn.fetchval(
                "SELECT config FROM integration_connections WHERE company_id = $1 AND provider = $2",
                company_id, PROVIDER_SLACK,
            )
            if slack_config_row:
                slack_cfg = json.loads(slack_config_row) if isinstance(slack_config_row, str) else slack_config_row
                slack_workspace_name = slack_cfg.get("slack_team_name")

    email_svc = get_email_service()
    await email_svc.send_provisioning_welcome_email(
        to_email=personal_email,
        to_name=employee_name,
        company_name=company_name,
        work_email=work_email if google_succeeded else None,
        temp_password=temp_password,
        slack_workspace_name=slack_workspace_name,
        slack_invite_link=slack_invite_link,
    )


async def _create_onboarding_employees(
    *,
    company_id: UUID,
    triggered_by: UUID,
    employees: list[dict],
) -> list[dict]:
    """Create employee records and trigger provisioning for each. Returns updated employee dicts."""
    results: list[dict] = []

    async with get_connection() as conn:
        # Pre-fetch integration config once for the company
        google_workspace_auto = False
        slack_auto = False
        try:
            integration_rows = await conn.fetch(
                """
                SELECT provider, config
                FROM integration_connections
                WHERE company_id = $1 AND status = 'connected'
                """,
                company_id,
            )
            for irow in integration_rows:
                cfg = _json_object(irow["config"])
                if irow["provider"] == PROVIDER_GOOGLE_WORKSPACE:
                    google_workspace_auto = _coerce_bool(cfg.get("auto_provision_on_employee_create"), True)
                elif irow["provider"] == PROVIDER_SLACK:
                    slack_auto = _coerce_bool(cfg.get("auto_invite_on_employee_create"), True)
        except Exception:
            logger.exception("Unable to query integration connections for company %s", company_id)

        for emp in employees:
            emp_status = (emp.get("status") or "").strip().lower()
            if emp_status in ("created", "done", "error"):
                results.append(emp)
                continue

            first_name = (emp.get("first_name") or "").strip()
            last_name = (emp.get("last_name") or "").strip()
            work_email = (emp.get("work_email") or "").strip().lower()

            if not first_name or not last_name or not work_email:
                emp["status"] = "error"
                emp["error"] = "Missing required fields: first_name, last_name, work_email"
                results.append(emp)
                continue

            try:
                existing = await conn.fetchval(
                    "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                    company_id, work_email,
                )
                if existing:
                    emp["status"] = "error"
                    emp["error"] = f"Employee with email {work_email} already exists"
                    results.append(emp)
                    continue

                start_date = None
                raw_start = (emp.get("start_date") or "").strip()
                if raw_start:
                    try:
                        start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                    except ValueError:
                        pass  # leave as None

                personal_email = (emp.get("personal_email") or "").strip().lower() or None
                address = (emp.get("address") or "").strip() or None

                row = await conn.fetchrow(
                    """
                    INSERT INTO employees (org_id, email, personal_email, first_name, last_name,
                                           work_state, employment_type, start_date, address)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                    """,
                    company_id,
                    work_email,
                    personal_email,
                    first_name,
                    last_name,
                    (emp.get("work_state") or "").strip() or None,
                    (emp.get("employment_type") or "").strip() or None,
                    start_date,
                    address,
                )

                emp["status"] = "created"
                emp["employee_id"] = str(row["id"])
                emp["error"] = None

                # Trigger provisioning
                prov = {}
                google_result: dict | None = None
                slack_result: dict | None = None

                if google_workspace_auto:
                    try:
                        google_result = await start_google_workspace_onboarding(
                            company_id=company_id,
                            employee_id=row["id"],
                            triggered_by=triggered_by,
                            trigger_source="matcha_work_onboarding",
                        )
                        prov["google_workspace"] = "triggered"
                    except Exception as gex:
                        logger.exception("Google Workspace provisioning failed for %s", work_email)
                        prov["google_workspace"] = f"error: {gex}"

                if slack_auto:
                    try:
                        slack_result = await start_slack_onboarding(
                            company_id=company_id,
                            employee_id=row["id"],
                            triggered_by=triggered_by,
                            trigger_source="matcha_work_onboarding",
                        )
                        prov["slack"] = "triggered"
                    except Exception as sex:
                        logger.exception("Slack provisioning failed for %s", work_email)
                        prov["slack"] = f"error: {sex}"

                if prov:
                    emp["provisioning_results"] = prov

                # Send provisioning welcome email
                if personal_email and (google_result or slack_result):
                    try:
                        await _send_mw_provisioning_email(
                            company_id=company_id,
                            personal_email=personal_email,
                            employee_name=f"{first_name} {last_name}".strip(),
                            work_email=work_email,
                            google_result=google_result,
                            slack_result=slack_result,
                        )
                    except Exception:
                        logger.exception("Failed to send provisioning email for %s", work_email)

            except Exception as e:
                logger.exception("Failed to create employee %s %s: %s", first_name, last_name, e)
                emp["status"] = "error"
                emp["error"] = str(e)

            results.append(emp)

    return results


def _inject_slide_context(msg_dicts: list[dict], current_state: dict, slide_index: Optional[int]) -> None:
    """Prepend selected slide content to the last user message so the AI sees what it's editing.

    Modifies msg_dicts in-place. Only the AI-facing message list is changed — the saved
    database message remains the user's original text.
    """
    if slide_index is None or not msg_dicts:
        return

    # Find slides in top-level or under presentation (workbook)
    slides = current_state.get("slides") or []
    if not slides:
        pres = current_state.get("presentation")
        if isinstance(pres, dict):
            slides = pres.get("slides") or []

    if not slides or not (0 <= slide_index < len(slides)):
        return

    slide = slides[slide_index]
    if not isinstance(slide, dict):
        return

    total = len(slides)
    title = slide.get("title", "Untitled")
    bullets = slide.get("bullets") or []
    speaker_notes = slide.get("speaker_notes", "")

    context_lines = [
        f"[Editing Slide {slide_index + 1}/{total}: \"{title}\"]",
        "Current content:",
        f"- Title: {title}",
        f"- Bullets: {json.dumps(bullets)}",
    ]
    if speaker_notes:
        context_lines.append(f"- Speaker Notes: {speaker_notes}")

    context_block = "\n".join(context_lines)

    # Find last user message and prepend context
    for i in range(len(msg_dicts) - 1, -1, -1):
        if msg_dicts[i]["role"] == "user":
            original = msg_dicts[i]["content"]
            msg_dicts[i] = {
                "role": "user",
                "content": f"{context_block}\n\nUser request: {original}",
            }
            break


def _scope_slide_update(ai_resp, current_state: dict, slide_index: Optional[int]) -> None:
    """When a specific slide was targeted, restrict the AI's update to only that slide.

    The AI is instructed to return the full slides array, but it may inadvertently modify
    other slides or presentation-level fields. This function:
    1) Strips non-slide keys (title, subtitle, theme, etc.) from the update
    2) Merges only the targeted slide from the AI response into the existing slides array
    3) Handles workbook presentations where slides live under presentation.slides
    """
    if slide_index is None:
        return
    if not isinstance(ai_resp.structured_update, dict):
        return

    # Strip non-slide presentation fields — only slide content should change
    for key in ("presentation_title", "subtitle", "theme", "cover_image_url", "generated_at"):
        ai_resp.structured_update.pop(key, None)

    ai_slides = ai_resp.structured_update.get("slides")

    # Determine where current slides live
    current_slides = list(current_state.get("slides") or [])

    # Fallback: workbook presentations store slides under presentation.slides
    if not current_slides:
        pres = current_state.get("presentation")
        if isinstance(pres, dict):
            current_slides = list(pres.get("slides") or [])

    if not isinstance(ai_slides, list) or not current_slides:
        return
    if not (0 <= slide_index < len(ai_slides) and 0 <= slide_index < len(current_slides)):
        return

    merged = list(current_slides)
    merged[slide_index] = ai_slides[slide_index]
    ai_resp.structured_update["slides"] = merged


async def _apply_ai_updates_and_operations(
    *,
    thread_id: UUID,
    company_id: UUID,
    ai_resp,
    current_state: dict,
    current_version: int,
    user_message: str,
    current_user_id: Optional[UUID] = None,
) -> tuple[dict, int, Optional[str], bool, str]:
    """Apply structured updates, execute supported operations, and return updated response state."""
    skill = ai_resp.skill or _infer_skill_from_state(current_state)
    # If skill is not a known document type (e.g. "none" or "chat"), fall back to
    # inferring from the update keys themselves so workbook/review/etc. updates
    # created on a fresh thread aren't silently dropped.
    if skill not in ("offer_letter", "review", "workbook", "onboarding", "presentation", "handbook", "policy") and isinstance(ai_resp.structured_update, dict) and ai_resp.structured_update:
        skill_from_updates = _infer_skill_from_state(ai_resp.structured_update)
        if skill_from_updates != "chat":
            skill = skill_from_updates
    initial_version = int(current_version)
    pdf_url: Optional[str] = None
    assistant_reply = ai_resp.assistant_reply
    changed = False

    should_execute_skill = bool(
        ai_resp.mode == "skill"
        and (ai_resp.confidence >= 0.65 or not ai_resp.missing_fields)
    )
    logger.info(
        "[MW] ai mode=%s skill=%s op=%s conf=%.2f missing=%s update_keys=%s should_exec=%s",
        ai_resp.mode, skill, ai_resp.operation, ai_resp.confidence,
        ai_resp.missing_fields,
        list(ai_resp.structured_update.keys()) if isinstance(ai_resp.structured_update, dict) else None,
        should_execute_skill,
    )
    force_send_draft = (
        skill == "offer_letter"
        and _looks_like_send_draft_command(user_message)
    )
    can_execute_operation = should_execute_skill or force_send_draft

    if should_execute_skill and ai_resp.structured_update:
        safe_updates = _validate_updates_for_skill(skill, ai_resp.structured_update)
        if skill == "handbook" and current_state.get("handbook_source_type") == "upload":
            safe_updates = {}
        if safe_updates:
            result = await doc_svc.apply_update(thread_id, safe_updates)
            current_version = result["version"]
            current_state = result["current_state"]
            changed = changed or current_version != initial_version

            inferred = _infer_skill_from_state(current_state)
            if inferred == "offer_letter":
                pdf_url = await doc_svc.generate_pdf(
                    current_state,
                    thread_id,
                    current_version,
                    is_draft=True,
                    company_id=company_id,
                )
            elif inferred == "presentation" and not current_state.get("cover_image_url"):
                # Generate a cover image the first time slides are created
                cover_url = await doc_svc.generate_cover_image(
                    presentation_title=str(current_state.get("presentation_title") or "Presentation"),
                    subtitle=current_state.get("subtitle"),
                    company_id=company_id,
                    thread_id=thread_id,
                )
                if cover_url:
                    cover_result = await doc_svc.apply_update(thread_id, {"cover_image_url": cover_url})
                    current_version = cover_result["version"]
                    current_state = cover_result["current_state"]

    operation = str(ai_resp.operation or "none").strip().lower()
    if force_send_draft and operation in {"none", "create", "update", "track"}:
        operation = "send_draft"

    if can_execute_operation and operation not in {"none", "create", "update", "track"}:
        action_note: Optional[str] = None
        try:
            if operation == "save_draft":
                if skill != "offer_letter":
                    action_note = "Save draft is only available for offer letters."
                else:
                    saved = await doc_svc.save_offer_letter_draft(thread_id, company_id)
                    action_note = f"Saved draft successfully ({saved['offer_status']})."
            elif operation == "send_draft":
                if skill != "offer_letter":
                    action_note = "Draft sending is only available for offer letters."
                else:
                    recipients = _collect_offer_draft_recipients(
                        structured_update=ai_resp.structured_update
                        if isinstance(ai_resp.structured_update, dict)
                        else None,
                        current_state=current_state,
                        user_message=user_message,
                    )
                    send_result = await doc_svc.send_offer_letter_draft(
                        thread_id=thread_id,
                        company_id=company_id,
                        recipient_emails=recipients,
                    )
                    if send_result.get("pdf_url"):
                        pdf_url = send_result["pdf_url"]
                    action_note = (
                        f"Draft email send complete: {send_result['sent_count']} sent, "
                        f"{send_result['failed_count']} failed."
                    )
                    if send_result["failed_count"] > 0:
                        failed_recipients = [
                            str(row.get("email"))
                            for row in send_result.get("recipients", [])
                            if row.get("status") != "sent" and row.get("email")
                        ]
                        if failed_recipients:
                            action_note += f" Failed recipient(s): {', '.join(failed_recipients[:3])}."
            elif operation == "send_requests":
                if skill != "review":
                    action_note = "Sending review requests is only available in review threads."
                else:
                    recipient_emails: list[str] = []
                    if isinstance(ai_resp.structured_update, dict):
                        raw_emails = ai_resp.structured_update.get("recipient_emails")
                        if isinstance(raw_emails, list):
                            recipient_emails = [str(v) for v in raw_emails if str(v).strip()]

                    send_result = await doc_svc.send_review_requests(
                        thread_id=thread_id,
                        company_id=company_id,
                        recipient_emails=recipient_emails,
                    )
                    refreshed = await doc_svc.get_thread(thread_id, company_id)
                    if refreshed:
                        current_state = refreshed["current_state"]
                        current_version = refreshed["version"]
                        changed = changed or current_version != initial_version
                    action_note = (
                        f"Sent {send_result['sent_count']} request(s), "
                        f"{send_result['failed_count']} failed. "
                        f"Received {send_result['received_responses']}/{send_result['expected_responses']}."
                    )
            elif operation == "finalize":
                finalized = await doc_svc.finalize_thread(thread_id, company_id)
                refreshed = await doc_svc.get_thread(thread_id, company_id)
                if refreshed:
                    current_state = refreshed["current_state"]
                    current_version = refreshed["version"]
                if finalized.get("pdf_url"):
                    pdf_url = finalized["pdf_url"]
                action_note = "Thread finalized."
            elif operation == "create_employees":
                if skill != "onboarding":
                    action_note = "Employee creation is only available in onboarding threads."
                else:
                    raw_employees = current_state.get("employees")
                    if not isinstance(raw_employees, list) or not raw_employees:
                        action_note = "No employees found to create. Please add employee details first."
                    else:
                        results = await _create_onboarding_employees(
                            company_id=company_id,
                            triggered_by=current_user_id,
                            employees=[dict(e) for e in raw_employees],
                        )
                        current_state["employees"] = results
                        current_state["batch_status"] = "complete"
                        created = sum(1 for e in results if e.get("status") == "created")
                        errors = sum(1 for e in results if e.get("status") == "error")
                        result = await doc_svc.apply_update(
                            thread_id,
                            current_state,
                            diff_summary=f"Created {created} employee(s), {errors} error(s)",
                        )
                        current_version = result["version"]
                        current_state = result["current_state"]
                        changed = True
                        action_note = f"Created {created} employee(s)"
                        if errors:
                            error_names = [
                                f"{e.get('first_name', '?')} {e.get('last_name', '?')}: {e.get('error', 'unknown')}"
                                for e in results if e.get("status") == "error"
                            ]
                            action_note += f", {errors} failed: " + "; ".join(error_names[:5])
                        action_note += "."
            elif operation == "generate_presentation":
                if skill != "workbook":
                    action_note = "Presentation generation is only available in workbook threads."
                else:
                    generated = await doc_svc.generate_workbook_presentation(
                        thread_id=thread_id,
                        company_id=company_id,
                    )
                    current_state = generated["current_state"]
                    current_version = generated["version"]
                    changed = True
                    action_note = (
                        f"Generated a presentation with {generated['slide_count']} slides. "
                        "Open Preview to review and download."
                    )
            elif operation == "generate_handbook":
                if skill != "handbook":
                    action_note = "Handbook generation is only available in handbook threads."
                elif current_state.get("handbook_source_type") == "upload":
                    action_note = "Handbook generation is unavailable in upload review mode. Start a new template handbook thread instead."
                else:
                    title = current_state.get("handbook_title")
                    states = current_state.get("handbook_states") or []
                    legal_name = current_state.get("handbook_legal_name")
                    ceo = current_state.get("handbook_ceo")

                    if not title or not states or not legal_name or not ceo:
                        missing = []
                        if not title: missing.append("handbook_title")
                        if not states: missing.append("handbook_states")
                        if not legal_name: missing.append("handbook_legal_name")
                        if not ceo: missing.append("handbook_ceo")
                        action_note = f"Cannot generate — missing required fields: {', '.join(missing)}"
                    else:
                        await doc_svc.apply_update(thread_id, {"handbook_status": "generating"})

                        from ...core.models.handbook import (
                            HandbookCreateRequest, HandbookScopeInput,
                            CompanyHandbookProfileInput, HandbookSectionInput,
                        )
                        profile_data = current_state.get("handbook_profile") or {}
                        raw = profile_data if isinstance(profile_data, dict) else {}

                        scopes = [HandbookScopeInput(state=s.upper()) for s in states]
                        mode = "single_state" if len(scopes) == 1 else "multi_state"

                        profile = CompanyHandbookProfileInput(
                            legal_name=legal_name,
                            dba=current_state.get("handbook_dba"),
                            ceo_or_president=ceo,
                            headcount=current_state.get("handbook_headcount"),
                            remote_workers=raw.get("remote_workers", False),
                            minors=raw.get("minors", False),
                            tipped_employees=raw.get("tipped_employees", False),
                            tip_pooling=raw.get("tip_pooling", False),
                            union_employees=raw.get("union_employees", False),
                            federal_contracts=raw.get("federal_contracts", False),
                            group_health_insurance=raw.get("group_health_insurance", False),
                            background_checks=raw.get("background_checks", False),
                            hourly_employees=raw.get("hourly_employees", True),
                            salaried_employees=raw.get("salaried_employees", False),
                            commissioned_employees=raw.get("commissioned_employees", False),
                        )

                        custom_sections_raw = current_state.get("handbook_custom_sections") or []
                        custom_sections = [
                            HandbookSectionInput(
                                section_key=f"custom_{i}",
                                title=s.get("title", ""),
                                content=s.get("content", ""),
                                section_order=900 + i,
                                section_type="custom",
                            )
                            for i, s in enumerate(custom_sections_raw)
                            if isinstance(s, dict) and s.get("title")
                        ]

                        req = HandbookCreateRequest(
                            title=title,
                            mode=mode,
                            source_type="template",
                            industry=current_state.get("handbook_industry"),
                            scopes=scopes,
                            profile=profile,
                            custom_sections=custom_sections,
                            guided_answers=current_state.get("handbook_guided_answers") or {},
                            create_from_template=True,
                        )

                        handbook = await HandbookService.create_handbook(
                            company_id=str(company_id),
                            data=req,
                            created_by=str(current_user_id) if current_user_id else None,
                        )

                        section_previews = [
                            {"section_key": s.section_key, "title": s.title,
                             "content": (s.content or "")[:500], "section_type": s.section_type}
                            for s in (handbook.sections or [])
                        ]

                        coverage_updates = {}
                        try:
                            async with get_connection() as cov_conn:
                                industry_key = await cov_conn.fetchval(
                                    "SELECT industry FROM companies WHERE id = $1", str(company_id)
                                )
                            coverage = HandbookService.compute_coverage(handbook, industry_key or "")
                            coverage_updates = {
                                "handbook_strength_score": coverage.strength_score,
                                "handbook_strength_label": coverage.strength_label,
                            }
                        except Exception as cov_err:
                            logger.warning("Coverage computation failed: %s", cov_err)

                        result = await doc_svc.apply_update(thread_id, {
                            "handbook_status": "created",
                            "handbook_id": str(handbook.id),
                            "handbook_mode": mode,
                            "handbook_sections": section_previews,
                            **coverage_updates,
                        })
                        current_version = result["version"]
                        current_state = result["current_state"]
                        changed = True

                        section_count = len(handbook.sections or [])
                        score_note = ""
                        if coverage_updates.get("handbook_strength_score") is not None:
                            score_note = f" Coverage score: {coverage_updates['handbook_strength_score']}/100 ({coverage_updates['handbook_strength_label']})."
                        action_note = f"Handbook created with {section_count} sections.{score_note}"
            elif operation == "generate_policy":
                if skill != "policy":
                    action_note = "Policy generation is only available in policy threads."
                else:
                    policy_type = current_state.get("policy_type")
                    location_names = current_state.get("policy_location_names") or []

                    if not policy_type:
                        action_note = "Cannot generate — missing required field: policy_type"
                    elif not location_names:
                        action_note = "Cannot generate — please specify at least one location (city, state)."
                    else:
                        await doc_svc.apply_update(thread_id, {"policy_status": "generating"})

                        # Resolve location names to location IDs from business_locations
                        location_ids: list[str] = []
                        async with get_connection() as conn:
                            for loc_name in location_names:
                                parts = [p.strip() for p in loc_name.split(",")]
                                if len(parts) == 2:
                                    city, state = parts[0], parts[1]
                                    row = await conn.fetchrow(
                                        "SELECT id FROM business_locations WHERE company_id = $1 AND city ILIKE $2 AND state ILIKE $3",
                                        str(company_id), city, state,
                                    )
                                    if row:
                                        location_ids.append(str(row["id"]))

                        from ...core.services.policy_draft_service import generate_policy_draft_stream, PolicyDraftRequest

                        draft_request = PolicyDraftRequest(
                            policy_type=policy_type,
                            location_ids=location_ids if location_ids else None,
                            additional_context=current_state.get("policy_additional_context"),
                        )

                        # Collect the full generated content
                        policy_content = ""
                        async for event in generate_policy_draft_stream(str(company_id), draft_request):
                            if event.get("type") == "content":
                                policy_content += event.get("text", "")
                            elif event.get("type") == "error":
                                raise ValueError(event.get("message", "Policy generation failed"))

                        result = await doc_svc.apply_update(thread_id, {
                            "policy_status": "created",
                            "policy_content": policy_content,
                        })
                        current_version = result["version"]
                        current_state = result["current_state"]
                        changed = True
                        action_note = "Policy draft generated. Review in the Preview panel, then edit or save."
            else:
                action_note = f"The action '{operation}' is not supported yet."
        except ValueError as e:
            action_note = str(e)
        except Exception as e:
            logger.error(
                "Failed Matcha Work operation '%s' for thread %s: %s",
                operation,
                thread_id,
                e,
                exc_info=True,
            )
            action_note = "I understood the command, but couldn't complete it right now."

        assistant_reply = _append_action_note(assistant_reply, action_note)

    return current_state, current_version, pdf_url, changed, assistant_reply


@router.post("/threads", response_model=CreateThreadResponse, status_code=201)
async def create_thread(
    body: CreateThreadRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new chat thread (optionally with an initial message)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    title = body.title or "New Chat"
    thread = await doc_svc.create_thread(company_id, current_user.id, title)
    thread_id = thread["id"]

    assistant_reply = None
    pdf_url = None

    if body.initial_message:
        # Save user message
        await doc_svc.add_message(thread_id, "user", body.initial_message)

        # Call AI with company context (profile already fetched during create_thread)
        ai_provider = get_ai_provider()
        profile = await doc_svc.get_company_profile_for_ai(company_id)
        ctx = _build_company_context(profile)
        messages = [{"role": "user", "content": body.initial_message}]
        ai_resp = await ai_provider.generate(messages, thread["current_state"], company_context=ctx)
        final_usage = ai_resp.token_usage

        new_version = thread["version"]
        (
            updated_state,
            new_version,
            pdf_url,
            changed,
            assistant_reply_text,
        ) = await _apply_ai_updates_and_operations(
            thread_id=thread_id,
            company_id=company_id,
            ai_resp=ai_resp,
            current_state=thread["current_state"],
            current_version=new_version,
            user_message=body.initial_message,
            current_user_id=current_user.id,
        )
        thread["current_state"] = updated_state

        await doc_svc.add_message(
            thread_id,
            "assistant",
            assistant_reply_text,
            version_created=new_version if changed else None,
        )
        try:
            await doc_svc.log_token_usage_event(
                company_id=company_id,
                user_id=current_user.id,
                thread_id=thread_id,
                token_usage=final_usage,
                operation="send_message",
            )
        except Exception as e:
            logger.warning("Failed to log Matcha Work token usage for thread %s: %s", thread_id, e)

        thread["version"] = new_version
        assistant_reply = assistant_reply_text

    return CreateThreadResponse(
        id=thread_id,
        title=thread["title"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
        task_type=_infer_skill_from_state(thread["current_state"]),
        is_pinned=thread.get("is_pinned", False),
        created_at=thread["created_at"],
        assistant_reply=assistant_reply,
        pdf_url=pdf_url,
    )


@router.post("/threads/{thread_id}/logo")
async def upload_thread_logo(
    thread_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a company logo for an offer-letter thread and save it for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="Logo upload is only available for offer letters")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    try:
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:  # 5MB limit
            raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")

        # Upload to storage
        logo_url = await get_storage().upload_file(
            content,
            file.filename or "logo.png",
            prefix=f"company-logos/{company_id}",
            content_type=file.content_type,
        )

        # Update thread state
        await doc_svc.apply_update(
            thread_id,
            {"company_logo_url": logo_url},
            diff_summary="Uploaded company logo",
        )

        # Also update company logo for future use
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE companies SET logo_url = $1 WHERE id = $2",
                logo_url,
                company_id,
            )

        return {"logo_url": logo_url}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload logo for thread %s: %s", thread_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload logo. Please try again.")


@router.post("/threads/{thread_id}/handbook/upload", response_model=ThreadDetailResponse)
async def upload_thread_handbook(
    thread_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload an existing handbook and audit it against synced company jurisdictions."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not _thread_accepts_handbook_upload(thread):
        raise HTTPException(
            status_code=400,
            detail="Handbook upload is only available in a new chat or an upload-mode handbook thread.",
        )

    filename = (file.filename or "handbook.pdf").strip() or "handbook.pdf"
    extension = os.path.splitext(filename)[1].lower()
    if extension not in HANDBOOK_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and DOC handbooks are supported")

    active_locations = [
        loc for loc in await get_locations(company_id)
        if loc.get("is_active", True)
    ]
    active_location_labels = [_location_label(loc) for loc in active_locations if _location_label(loc)]
    unsynced_labels = [
        _location_label(loc)
        for loc in active_locations
        if loc.get("data_status") != "synced" and _location_label(loc)
    ]
    if not active_locations or unsynced_labels:
        blocking_message = _build_handbook_block_message(
            unsynced_labels if unsynced_labels else active_location_labels
        )
        result = await doc_svc.apply_update(
            thread_id,
            {
                "handbook_source_type": "upload",
                "handbook_upload_status": "blocked",
                "handbook_title": thread.get("current_state", {}).get("handbook_title") or "Uploaded Employee Handbook",
                "handbook_status": "error",
                "handbook_uploaded_file_url": None,
                "handbook_uploaded_filename": None,
                "handbook_blocking_error": blocking_message,
                "handbook_review_locations": active_location_labels,
                "handbook_red_flags": [],
                "handbook_sections": [],
                "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                "handbook_error": None,
            },
            diff_summary="Blocked handbook upload audit",
        )
        await doc_svc.add_message(
            thread_id,
            "system",
            f"Handbook upload attempted for {filename}.",
            version_created=result["version"],
        )
        await doc_svc.add_message(
            thread_id,
            "assistant",
            blocking_message,
            version_created=result["version"],
        )
        return await _build_thread_detail_response(thread_id, company_id)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded handbook file is empty")
    if len(content) > HANDBOOK_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Handbook file exceeds the 10 MB limit")

    try:
        extracted_text, _page_count = ERDocumentParser().extract_text_from_bytes(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to extract handbook upload text for thread %s: %s", thread_id, exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to read the uploaded handbook file") from exc

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No readable handbook text was found in the uploaded file")

    # Quick relevance check — reject clearly wrong documents before expensive work.
    is_handbook, rejection_reason = await check_handbook_relevance(extracted_text, get_ai_provider().client)
    if not is_handbook:
        blocking_message = rejection_reason or (
            "This document does not appear to be an employee handbook. "
            "Please upload your company's employee handbook and try again."
        )
        result = await doc_svc.apply_update(
            thread_id,
            {
                "handbook_source_type": "upload",
                "handbook_upload_status": "blocked",
                "handbook_title": thread.get("current_state", {}).get("handbook_title") or "Uploaded Employee Handbook",
                "handbook_status": "error",
                "handbook_uploaded_file_url": None,
                "handbook_uploaded_filename": None,
                "handbook_blocking_error": blocking_message,
                "handbook_review_locations": [],
                "handbook_red_flags": [],
                "handbook_green_flags": [],
                "handbook_jurisdiction_summaries": [],
                "handbook_sections": [],
                "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                "handbook_error": None,
            },
            diff_summary="Rejected non-handbook upload",
        )
        await doc_svc.add_message(
            thread_id,
            "system",
            f"Uploaded file: {filename}.",
            version_created=result["version"],
        )
        await doc_svc.add_message(
            thread_id,
            "assistant",
            blocking_message,
            version_created=result["version"],
        )
        return await _build_thread_detail_response(thread_id, company_id)

    storage = get_storage()
    uploaded_file_url = await storage.upload_file(
        content,
        filename,
        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "handbooks"),
        content_type=file.content_type,
    )
    await storage.upload_file(
        extracted_text.encode("utf-8"),
        f"{os.path.splitext(filename)[0] or 'handbook'}-extracted.txt",
        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "handbook-analysis"),
        content_type="text/plain",
    )

    # Fetch requirements sequentially to avoid connection pool exhaustion.
    # Each get_location_requirements() call acquires a pool connection and
    # internally calls get_employee_impact_for_location() which needs another;
    # running them all in parallel via asyncio.gather can deadlock the pool.
    audited_locations: list[AuditedLocation] = []
    for loc in active_locations:
        if not loc.get("id"):
            continue
        try:
            requirements = await get_location_requirements(UUID(str(loc["id"])), company_id)
        except Exception:
            logger.error(
                "Failed to load location requirements for handbook upload audit thread %s location %s",
                thread_id,
                loc.get("id"),
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail="Failed to load synced compliance requirements")
        audited_locations.append(
            AuditedLocation(
                id=UUID(str(loc["id"])),
                label=_location_label(loc),
                state=str(loc.get("state") or "").strip().upper(),
                city=str(loc.get("city") or "").strip() or None,
                requirements=list(requirements),
            )
        )

    profile = await doc_svc.get_company_profile_for_ai(company_id)
    company_name = str(profile.get("name") or "").strip() or "Company"
    company_industry = str(profile.get("industry") or "").strip() or None

    audit_result = audit_uploaded_handbook(
        thread_id=thread_id,
        company_id=company_id,
        company_name=company_name,
        company_industry=company_industry,
        uploaded_file_url=uploaded_file_url,
        uploaded_filename=filename,
        extracted_text=extracted_text,
        locations=audited_locations,
    )

    result = await doc_svc.apply_update(
        thread_id,
        {
            "handbook_source_type": "upload",
            "handbook_upload_status": "reviewed",
            "handbook_title": audit_result["handbook_title"],
            "handbook_uploaded_file_url": uploaded_file_url,
            "handbook_uploaded_filename": filename,
            "handbook_status": "ready",
            "handbook_blocking_error": None,
            "handbook_error": None,
            **audit_result,
        },
        diff_summary=f"Uploaded handbook audit: {filename}",
    )
    summary_message = _build_handbook_upload_summary(
        file_name=filename,
        reviewed_locations=audit_result["handbook_review_locations"],
        red_flags=audit_result["handbook_red_flags"],
        green_flags=audit_result.get("handbook_green_flags"),
        jurisdiction_summaries=audit_result.get("handbook_jurisdiction_summaries"),
    )
    await doc_svc.add_message(
        thread_id,
        "system",
        f"Uploaded handbook file: {filename}.",
        version_created=result["version"],
    )
    await doc_svc.add_message(
        thread_id,
        "assistant",
        summary_message,
        version_created=result["version"],
    )
    return await _build_thread_detail_response(thread_id, company_id)


@router.post("/threads/{thread_id}/images")
async def upload_thread_images(
    thread_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload up to 4 images for a workbook thread's presentation (10 MB each)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        thread["current_state"] = await doc_svc.ensure_matcha_work_thread_storage_scope(
            thread_id,
            company_id,
            thread.get("current_state") or {},
        )
        existing: list[str] = (thread.get("current_state") or {}).get("images") or []
        if len(existing) + len(files) > 4:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum 4 images allowed. You already have {len(existing)}.",
            )

        uploaded_urls: list[str] = []
        for file in files:
            if not file.content_type or not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail=f"'{file.filename}' is not an image")
            content = await file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"'{file.filename}' exceeds 10 MB limit")
            url = await get_storage().upload_file(
                content,
                file.filename or "image.jpg",
                prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "images"),
                content_type=file.content_type,
            )
            uploaded_urls.append(url)

        new_images = existing + uploaded_urls
        await doc_svc.apply_update(thread_id, {"images": new_images}, diff_summary="Added presentation images")
        return {"images": new_images, "uploaded_count": len(uploaded_urls)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload images for thread %s: %s", thread_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload images. Please try again.")


@router.delete("/threads/{thread_id}/images")
async def remove_thread_image(
    thread_id: UUID,
    url: str = Query(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a single image from a workbook thread by URL."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    current_images: list[str] = (thread.get("current_state") or {}).get("images") or []
    if url not in current_images:
        raise HTTPException(status_code=404, detail="Image not found in thread")

    updated_images = [u for u in current_images if u != url]
    await doc_svc.apply_update(thread_id, {"images": updated_images}, diff_summary="Removed presentation image")

    # Best-effort S3 deletion — don't fail the request if this errors
    try:
        await get_storage().delete_file(url)
    except Exception:
        pass

    return {"images": updated_images}


@router.get("/threads", response_model=list[ThreadListItem])
async def list_threads(
    status: Optional[str] = Query(None, pattern="^(active|finalized|archived)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List threads for the current company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    threads = await doc_svc.list_threads(company_id, status=status, limit=limit, offset=offset)
    return [ThreadListItem(**t) for t in threads]


@router.get("/elements", response_model=list[ElementListItem])
async def list_elements(
    status: Optional[str] = Query(None, pattern="^(active|finalized|archived)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List Matcha Work elements for the current company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    elements = await doc_svc.list_elements(company_id, status=status, limit=limit, offset=offset)
    return [ElementListItem(**e) for e in elements]


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get thread detail with all messages."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return await _build_thread_detail_response(thread_id, company_id)


@router.post("/threads/{thread_id}/messages", response_model=SendMessageResponse)
async def send_message(
    thread_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send a user message → AI response → state update → PDF."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot send messages to a finalized thread")

    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send messages to an archived thread")

    if current_user.role != "admin":
        await billing_service.check_credits(company_id)

    # Save user message
    user_msg = await doc_svc.add_message(thread_id, "user", body.content)

    # Fetch message history + company profile + context summary in parallel
    messages, profile, (context_summary, summary_at_count) = await asyncio.gather(
        doc_svc.get_thread_messages(thread_id, limit=20),
        doc_svc.get_company_profile_for_ai(company_id),
        doc_svc.get_context_summary(thread_id),
    )
    msg_dicts = [{"role": m["role"], "content": m["content"]} for m in messages]

    # Inject selected slide content into the AI-facing message (not saved to DB)
    _inject_slide_context(msg_dicts, thread["current_state"], body.slide_index)

    # Call AI with company context
    ai_provider = get_ai_provider()
    ctx = _build_company_context(profile)
    ai_resp = await ai_provider.generate(
        msg_dicts, thread["current_state"], company_context=ctx,
        slide_index=body.slide_index, context_summary=context_summary,
    )
    _scope_slide_update(ai_resp, thread["current_state"], body.slide_index)
    final_usage = ai_resp.token_usage

    current_version = thread["version"]
    (
        current_state,
        current_version,
        pdf_url,
        changed,
        assistant_reply_text,
    ) = await _apply_ai_updates_and_operations(
        thread_id=thread_id,
        company_id=company_id,
        ai_resp=ai_resp,
        current_state=thread["current_state"],
        current_version=current_version,
        user_message=body.content,
        current_user_id=current_user.id,
    )

    # Save assistant message
    assistant_msg = await doc_svc.add_message(
        thread_id,
        "assistant",
        assistant_reply_text,
        version_created=current_version if changed else None,
    )

    cost = calculate_call_cost(
        model=str((final_usage or {}).get("model") or "unknown"),
        prompt_tokens=(final_usage or {}).get("prompt_tokens"),
        completion_tokens=(final_usage or {}).get("completion_tokens"),
    )
    if final_usage is not None:
        final_usage["cost_dollars"] = float(cost)

    try:
        await doc_svc.log_token_usage_event(
            company_id=company_id,
            user_id=current_user.id,
            thread_id=thread_id,
            token_usage=final_usage,
            operation="send_message",
            cost_dollars=float(cost),
        )
    except Exception as e:
        logger.warning("Failed to log Matcha Work token usage for thread %s: %s", thread_id, e)

    if current_user.role != "admin":
        try:
            async with get_connection() as conn:
                async with conn.transaction():
                    await billing_service.deduct_credit(
                        conn,
                        company_id=company_id,
                        thread_id=thread_id,
                        user_id=current_user.id,
                        cost=cost,
                        model=str((final_usage or {}).get("model") or "unknown"),
                    )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_402_PAYMENT_REQUIRED:
                logger.warning(
                    "Credits ran out before deduction could be recorded for thread %s",
                    thread_id,
                )
            else:
                logger.warning("Failed to deduct Matcha Work credit for thread %s: %s", thread_id, exc)
        except Exception as exc:
            logger.warning("Failed to deduct Matcha Work credit for thread %s: %s", thread_id, exc)

    # Trigger conversation compaction in the background if needed
    asyncio.create_task(_maybe_compact(thread_id, ai_provider, summary_at_count))

    return SendMessageResponse(
        user_message=_row_to_message(user_msg),
        assistant_message=_row_to_message(assistant_msg),
        current_state=current_state,
        version=current_version,
        task_type=_infer_skill_from_state(current_state),
        pdf_url=pdf_url,
        token_usage=final_usage,
    )


_compacting_threads: set[UUID] = set()  # simple guard against concurrent compaction
_COMPACTION_REFRESH_INTERVAL = 20  # re-compact after this many new messages


async def _maybe_compact(thread_id: UUID, ai_provider, summary_at_count: int | None) -> None:
    """Check message count and run compaction if threshold is exceeded or summary is stale."""
    if thread_id in _compacting_threads:
        return
    try:
        _compacting_threads.add(thread_id)
        msg_count = await doc_svc.get_thread_message_count(thread_id)
        if msg_count < 30:
            return
        # Skip if summary is recent enough
        if summary_at_count is not None and (msg_count - summary_at_count) < _COMPACTION_REFRESH_INTERVAL:
            return
        all_messages = await doc_svc.get_thread_messages(thread_id)
        msg_dicts = [{"role": m["role"], "content": m["content"]} for m in all_messages]
        summary = await compact_conversation(msg_dicts, ai_provider.client)
        if summary:
            await doc_svc.save_context_summary(thread_id, summary, msg_count)
            logger.info("Compacted conversation for thread %s (%d messages)", thread_id, msg_count)
    except Exception:
        logger.warning("Background compaction failed for thread %s", thread_id, exc_info=True)
    finally:
        _compacting_threads.discard(thread_id)


@router.post("/threads/{thread_id}/messages/stream")
async def send_message_stream(
    thread_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send message with SSE progress + token usage events."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot send messages to a finalized thread")

    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send messages to an archived thread")

    if current_user.role != "admin":
        await billing_service.check_credits(company_id)

    # Save user message before streaming
    user_msg = await doc_svc.add_message(thread_id, "user", body.content)

    # Fetch message history + company profile + context summary in parallel
    messages, profile, (context_summary, summary_at_count) = await asyncio.gather(
        doc_svc.get_thread_messages(thread_id, limit=20),
        doc_svc.get_company_profile_for_ai(company_id),
        doc_svc.get_context_summary(thread_id),
    )
    msg_dicts = [{"role": m["role"], "content": m["content"]} for m in messages]

    # Inject selected slide content into the AI-facing message (not saved to DB)
    _inject_slide_context(msg_dicts, thread["current_state"], body.slide_index)

    ai_provider = get_ai_provider()
    ctx = _build_company_context(profile)
    estimated_usage = await ai_provider.estimate_usage(msg_dicts, thread["current_state"], company_context=ctx, slide_index=body.slide_index)

    async def event_stream():
        try:
            yield _sse_data(
                {
                    "type": "usage",
                    "data": {
                        **estimated_usage,
                        "stage": "estimate",
                    },
                }
            )

            ai_resp = await ai_provider.generate(
                msg_dicts, thread["current_state"], company_context=ctx,
                slide_index=body.slide_index, context_summary=context_summary,
            )
            _scope_slide_update(ai_resp, thread["current_state"], body.slide_index)

            current_version = thread["version"]
            (
                current_state,
                current_version,
                pdf_url,
                changed,
                assistant_reply_text,
            ) = await _apply_ai_updates_and_operations(
                thread_id=thread_id,
                company_id=company_id,
                ai_resp=ai_resp,
                current_state=thread["current_state"],
                current_version=current_version,
                user_message=body.content,
                current_user_id=current_user.id,
            )

            # Save assistant message
            assistant_msg = await doc_svc.add_message(
                thread_id,
                "assistant",
                assistant_reply_text,
                version_created=current_version if changed else None,
            )

            final_usage = ai_resp.token_usage or estimated_usage
            stream_cost = calculate_call_cost(
                model=str((final_usage or {}).get("model") or "unknown"),
                prompt_tokens=(final_usage or {}).get("prompt_tokens"),
                completion_tokens=(final_usage or {}).get("completion_tokens"),
            )
            if final_usage is not None:
                final_usage["cost_dollars"] = float(stream_cost)

            try:
                await doc_svc.log_token_usage_event(
                    company_id=company_id,
                    user_id=current_user.id,
                    thread_id=thread_id,
                    token_usage=final_usage,
                    operation="send_message",
                    cost_dollars=float(stream_cost),
                )
            except Exception as e:
                logger.warning("Failed to log Matcha Work token usage for thread %s: %s", thread_id, e)

            if current_user.role != "admin":
                try:
                    async with get_connection() as conn:
                        async with conn.transaction():
                            await billing_service.deduct_credit(
                                conn,
                                company_id=company_id,
                                thread_id=thread_id,
                                user_id=current_user.id,
                                cost=stream_cost,
                                model=str((final_usage or {}).get("model") or "unknown"),
                            )
                except HTTPException as exc:
                    if exc.status_code == status.HTTP_402_PAYMENT_REQUIRED:
                        logger.warning(
                            "Credits ran out before stream deduction could be recorded for thread %s",
                            thread_id,
                        )
                    else:
                        logger.warning("Failed to deduct Matcha Work credit for thread %s: %s", thread_id, exc)
                except Exception as exc:
                    logger.warning("Failed to deduct Matcha Work credit for thread %s: %s", thread_id, exc)

            if final_usage:
                yield _sse_data(
                    {
                        "type": "usage",
                        "data": {
                            **final_usage,
                            "stage": "final",
                        },
                    }
                )

            response = SendMessageResponse(
                user_message=_row_to_message(user_msg),
                assistant_message=_row_to_message(assistant_msg),
                current_state=current_state,
                version=current_version,
                task_type=_infer_skill_from_state(current_state),
                pdf_url=pdf_url,
                token_usage=final_usage,
            )

            yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})

            # Trigger compaction in the background if needed
            asyncio.create_task(_maybe_compact(thread_id, ai_provider, summary_at_count))
        except Exception as e:
            logger.error("Matcha Work stream failed for thread %s: %s", thread_id, e, exc_info=True)
            yield _sse_data(
                {
                    "type": "error",
                    "message": "Failed to process message. Please try again.",
                }
            )
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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


@router.get("/threads/{thread_id}/versions", response_model=list[DocumentVersionResponse])
async def list_versions(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all document versions for a thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    versions = await doc_svc.list_versions(thread_id)
    return [DocumentVersionResponse(**v) for v in versions]


@router.post("/threads/{thread_id}/revert", response_model=SendMessageResponse)
async def revert_thread(
    thread_id: UUID,
    body: RevertRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Revert to a historical version (creates a new version with old state)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot revert a finalized thread")
    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot revert an archived thread")

    try:
        result = await doc_svc.revert_to_version(thread_id, body.version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    new_version = result["version"]
    new_state = result["current_state"]

    system_msg = await doc_svc.add_message(
        thread_id,
        "system",
        f"Document reverted to version {body.version}.",
        version_created=new_version,
    )

    assistant_msg = await doc_svc.add_message(
        thread_id,
        "assistant",
        f"I've reverted the document to version {body.version}. You can continue editing from there.",
        version_created=new_version,
    )

    pdf_url = None
    if _infer_skill_from_state(new_state) == "offer_letter":
        pdf_url = await doc_svc.generate_pdf(
            new_state,
            thread_id,
            new_version,
            is_draft=True,
            company_id=company_id,
        )

    return SendMessageResponse(
        user_message=_row_to_message(system_msg),
        assistant_message=_row_to_message(assistant_msg),
        current_state=new_state,
        version=new_version,
        pdf_url=pdf_url,
    )


@router.post("/threads/{thread_id}/finalize", response_model=FinalizeResponse)
async def finalize_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Finalize the thread — lock status, generate final PDF without watermark."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        result = await doc_svc.finalize_thread(thread_id, company_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FinalizeResponse(**result)


@router.post("/threads/{thread_id}/save-draft", response_model=SaveDraftResponse)
async def save_draft(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Save the current Matcha Work state into offer_letters as a draft."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="Save draft is only available for offer letters")

    try:
        result = await doc_svc.save_offer_letter_draft(thread_id, company_id)
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return SaveDraftResponse(**result)


@router.get("/threads/{thread_id}/pdf")
async def get_pdf(
    thread_id: UUID,
    version: Optional[int] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get or generate the PDF for a thread (optionally a specific version)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="PDF preview is only available for offer letters")

    target_version = version if version is not None else thread["version"]
    state = thread["current_state"]

    # If requesting a historical version, load that state
    if version is not None and version != thread["version"]:
        versions = await doc_svc.list_versions(thread_id)
        ver_map = {v["version"]: v for v in versions}
        if target_version not in ver_map:
            raise HTTPException(status_code=404, detail=f"Version {target_version} not found")
        state = ver_map[target_version]["state_json"]

    is_draft = thread["status"] != "finalized"
    pdf_url = await doc_svc.generate_pdf(
        state,
        thread_id,
        target_version,
        is_draft=is_draft,
        company_id=company_id,
    )

    if pdf_url is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable")

    return {"pdf_url": pdf_url, "version": target_version}


@router.get("/threads/{thread_id}/pdf/proxy")
async def proxy_pdf(
    thread_id: UUID,
    version: Optional[int] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Stream PDF bytes for same-origin iframe embedding (avoids cross-origin iframe blocking)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="PDF preview is only available for offer letters")

    target_version = version if version is not None else thread["version"]
    state = thread["current_state"]

    if version is not None and version != thread["version"]:
        versions = await doc_svc.list_versions(thread_id)
        ver_map = {v["version"]: v for v in versions}
        if target_version not in ver_map:
            raise HTTPException(status_code=404, detail=f"Version {target_version} not found")
        state = ver_map[target_version]["state_json"]

    is_draft = thread["status"] != "finalized"
    pdf_url = await doc_svc.generate_pdf(
        state,
        thread_id,
        target_version,
        is_draft=is_draft,
        company_id=company_id,
    )

    if pdf_url is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable")

    try:
        pdf_bytes = await get_storage().download_file(pdf_url)
    except Exception as e:
        logger.error("Failed to fetch PDF for proxy: %s", e)
        raise HTTPException(status_code=503, detail="Failed to load PDF")

    safe_title = re.sub(r"[^\w\s-]", "", thread.get("title") or "offer-letter").strip().replace(" ", "-") or "offer-letter"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_title}.pdf"'},
    )


@router.delete("/threads/{thread_id}", status_code=204)
async def archive_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Archive (soft-delete) a thread."""
    from ...database import get_connection

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE mw_threads
            SET status='archived', updated_at=NOW()
            WHERE id=$1 AND company_id=$2 AND status != 'archived'
            """,
            thread_id,
            company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Thread not found")
    await doc_svc.sync_element_record(thread_id)


@router.get(
    "/threads/{thread_id}/review-requests",
    response_model=list[ReviewRequestStatus],
)
async def list_review_requests(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List review request status rows for a review thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        rows = await doc_svc.list_review_requests(thread_id, company_id)
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return [ReviewRequestStatus(**row) for row in rows]


@router.post(
    "/threads/{thread_id}/review-requests/send",
    response_model=SendReviewRequestsResponse,
)
async def send_review_requests(
    thread_id: UUID,
    body: SendReviewRequestsRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Send anonymous review request links to recipient emails and track expected responses.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        result = await doc_svc.send_review_requests(
            thread_id=thread_id,
            company_id=company_id,
            recipient_emails=body.recipient_emails,
            custom_message=body.custom_message,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return SendReviewRequestsResponse(**result)


@router.post(
    "/threads/{thread_id}/handbook/send-signatures",
    response_model=SendHandbookSignaturesResponse,
)
async def send_handbook_signatures(
    thread_id: UUID,
    body: SendHandbookSignaturesRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send handbook acknowledgement signatures from a workbook thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send handbook signatures for an archived thread")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "workbook":
        raise HTTPException(status_code=400, detail="Handbook signatures are only available for workbook threads")

    employee_ids = [str(employee_id) for employee_id in body.employee_ids] if body.employee_ids else None

    try:
        distributed = await HandbookService.distribute_to_employees(
            handbook_id=str(body.handbook_id),
            company_id=str(company_id),
            distributed_by=str(current_user.id),
            employee_ids=employee_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if distributed is None:
        raise HTTPException(status_code=404, detail="Handbook not found")

    payload = distributed.model_dump() if hasattr(distributed, "model_dump") else dict(distributed)
    return SendHandbookSignaturesResponse(**payload)


@router.post(
    "/threads/{thread_id}/presentation/generate",
    response_model=GeneratePresentationResponse,
)
async def generate_workbook_presentation(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate slide-ready presentation content from workbook sections."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        result = await doc_svc.generate_workbook_presentation(
            thread_id=thread_id,
            company_id=company_id,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return GeneratePresentationResponse(**result)


@router.get("/threads/{thread_id}/presentation/pdf")
async def get_presentation_pdf(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return the presentation PDF URL, generating it on demand."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    state = await doc_svc.ensure_matcha_work_thread_storage_scope(
        thread_id,
        company_id,
        thread.get("current_state") or {},
    )
    if _infer_skill_from_state(state) not in ("presentation", "workbook"):
        raise HTTPException(status_code=400, detail="Presentation PDF is only available for presentation and workbook threads")

    version = int(thread.get("version") or 0)
    # For workbook threads, use the nested presentation; for standalone presentations, use top-level state
    if _infer_skill_from_state(state) == "workbook":
        pres = state.get("presentation")
        if not pres or not pres.get("slides"):
            raise HTTPException(status_code=400, detail="No presentation slides found. Generate a presentation first.")
        pdf_state = {
            "presentation_title": pres.get("title"),
            "subtitle": pres.get("subtitle"),
            "slides": pres.get("slides", []),
            "cover_image_url": pres.get("cover_image_url"),
        }
    else:
        pdf_state = state

    pdf_url = await doc_svc.generate_presentation_pdf(
        pdf_state,
        thread_id,
        version,
        company_id=company_id,
    )
    if not pdf_url:
        raise HTTPException(status_code=500, detail="Failed to generate presentation PDF")

    return {"pdf_url": pdf_url}


@router.patch("/threads/{thread_id}", response_model=ThreadListItem)
async def update_thread_title(
    thread_id: UUID,
    body: UpdateTitleRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update thread title."""
    from ...database import get_connection

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_threads
            SET title=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, status, version, is_pinned, created_at, updated_at, current_state
            """,
            body.title,
            thread_id,
            company_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    await doc_svc.sync_element_record(thread_id)

    row_dict = dict(row)
    current_state = _json_object(row_dict.pop("current_state", {}))
    return ThreadListItem(
        **{
            **row_dict,
            "task_type": _infer_skill_from_state(current_state),
        }
    )


@router.post("/threads/{thread_id}/pin", response_model=ThreadListItem)
async def set_thread_pin(
    thread_id: UUID,
    body: PinThreadRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Pin or unpin a thread for faster access in chat history."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row = await doc_svc.set_thread_pinned(thread_id, company_id, body.is_pinned)
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ThreadListItem(**row)


@public_router.get("/review-requests/{token}", response_model=PublicReviewRequestResponse)
async def get_public_review_request(token: str):
    """Get a public review-request payload by one-time token."""
    row = await doc_svc.get_public_review_request(token)
    if row is None:
        raise HTTPException(status_code=404, detail="Review request not found")
    return PublicReviewRequestResponse(**row)


@public_router.post(
    "/review-requests/{token}/submit",
    response_model=PublicReviewSubmitResponse,
)
async def submit_public_review_request(
    token: str,
    body: PublicReviewSubmitRequest,
):
    """Submit an anonymous review response via public token link."""
    try:
        result = await doc_svc.submit_public_review_request(
            token=token,
            feedback=body.feedback,
            rating=body.rating,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Review request not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail == "Review response already submitted":
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return PublicReviewSubmitResponse(**result)
