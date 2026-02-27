"""Matcha Work — chat-driven AI workspace for HR document elements."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse

from ...core.models.auth import CurrentUser
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..models.matcha_work import (
    CreateThreadRequest,
    CreateThreadResponse,
    DocumentVersionResponse,
    ElementListItem,
    FinalizeResponse,
    MWMessageOut,
    OnboardingDocument,
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
    WorkbookDocument,
)
from ..services import matcha_work_document as doc_svc
from ..services import billing_service
from ..services.matcha_work_ai import get_ai_provider
from ..services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)
from ...core.services.email import get_email_service
from ...core.services.handbook_service import HandbookService

logger = logging.getLogger(__name__)

router = APIRouter()
public_router = APIRouter()

VALID_OFFER_LETTER_FIELDS = set(OfferLetterDocument.model_fields.keys())
VALID_REVIEW_FIELDS = set(ReviewDocument.model_fields.keys())
VALID_WORKBOOK_FIELDS = set(WorkbookDocument.model_fields.keys())
VALID_ONBOARDING_FIELDS = set(OnboardingDocument.model_fields.keys())
THREAD_SCOPE_REPLY_TEMPLATE = (
    "This chat is currently focused on {current}. Start a new chat to work on {requested}, "
    "or continue with {current} in this thread."
)

OFFER_INTENT_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\boffer letter\b", 4),
    (r"\bjob offer\b", 4),
    (r"\bemployment offer\b", 4),
    (r"\boffer\b", 1),
    (r"\bsalary\b", 1),
    (r"\bcompensation\b", 1),
    (r"\bbenefits?\b", 1),
    (r"\bstart date\b", 1),
    (r"\bcandidate\b", 1),
)

REVIEW_INTENT_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\bperformance review\b", 4),
    (r"\banonym(?:ous|ized)\s+review\b", 4),
    (r"\breview\b", 1),
    (r"\bfeedback\b", 1),
    (r"\bstrengths?\b", 1),
    (r"\bgrowth areas?\b", 1),
    (r"\brating\b", 1),
    (r"\bevaluation\b", 1),
)

WORKBOOK_INTENT_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\bworkbook\b", 4),
    (r"\bhandbook\b", 4),
    (r"\bmanual\b", 4),
    (r"\bplaybook\b", 4),
    (r"\bguide\b", 1),
    (r"\bpolicy collection\b", 4),
)

ONBOARDING_INTENT_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\bonboard(?:ing)?\b", 4),
    (r"\bnew\s+(?:hire|employee|team\s+member)s?\b", 4),
    (r"\badd\s+employee", 4),
    (r"\bcreate\s+employee", 4),
    (r"\bhire\b", 1),
    (r"\bprovision(?:ing)?\b", 1),
)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


def _normalize_task_type(task_type: Optional[str]) -> str:
    if task_type == "review":
        return "review"
    if task_type == "workbook":
        return "workbook"
    if task_type == "onboarding":
        return "onboarding"
    return "offer_letter"


def _task_type_label(task_type: Optional[str]) -> str:
    normalized = _normalize_task_type(task_type)
    if normalized == "review":
        return "anonymized reviews"
    if normalized == "workbook":
        return "HR workbooks"
    if normalized == "onboarding":
        return "employee onboarding"
    return "offer letters"


def _is_offer_letter_task(task_type: Optional[str]) -> bool:
    return _normalize_task_type(task_type) == "offer_letter"


def _validate_updates(task_type: Optional[str], updates: dict) -> dict:
    """Filter AI updates to known fields for the thread task type."""
    ntype = _normalize_task_type(task_type)
    if ntype == "offer_letter":
        valid_fields = VALID_OFFER_LETTER_FIELDS
    elif ntype == "review":
        valid_fields = VALID_REVIEW_FIELDS
    elif ntype == "onboarding":
        valid_fields = VALID_ONBOARDING_FIELDS
    else:
        valid_fields = VALID_WORKBOOK_FIELDS
    return {k: v for k, v in updates.items() if k in valid_fields}


def _intent_score(text: str, patterns: tuple[tuple[str, int], ...]) -> int:
    score = 0
    for pattern, weight in patterns:
        if re.search(pattern, text):
            score += weight
    return score


def _detect_requested_task_type(content: str) -> Optional[str]:
    text = content.lower().strip()
    if not text:
        return None
    offer_score = _intent_score(text, OFFER_INTENT_PATTERNS)
    review_score = _intent_score(text, REVIEW_INTENT_PATTERNS)
    workbook_score = _intent_score(text, WORKBOOK_INTENT_PATTERNS)
    onboarding_score = _intent_score(text, ONBOARDING_INTENT_PATTERNS)

    if offer_score == 0 and review_score == 0 and workbook_score == 0 and onboarding_score == 0:
        return None

    scores = [
        ("offer_letter", offer_score),
        ("review", review_score),
        ("workbook", workbook_score),
        ("onboarding", onboarding_score),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)

    # Return the winner if it's clear
    if scores[0][1] > scores[1][1]:
        return scores[0][0]

    # Tie-breaking / explicit keywords
    if re.search(r"\bonboard(?:ing)?\b|\bnew\s+(?:hire|employee)s?\b|\badd\s+employee\b|\bcreate\s+employee\b", text):
        return "onboarding"
    if re.search(r"\boffer letter\b|\bjob offer\b|\bemployment offer\b", text):
        return "offer_letter"
    if re.search(r"\bperformance review\b|\banonym(?:ous|ized)\s+review\b", text):
        return "review"
    if re.search(r"\bworkbook\b|\bhandbook\b|\bplaybook\b", text):
        return "workbook"

    return scores[0][0]


def _thread_has_existing_work(thread: dict, prior_message_count: int = 0) -> bool:
    return bool(thread.get("current_state")) or int(thread.get("version", 0)) > 0 or prior_message_count > 0


async def _resolve_task_type_for_message(
    thread: dict,
    company_id: UUID,
    content: str,
    prior_message_count: int = 0,
) -> tuple[Optional[str], dict, Optional[str]]:
    current_task_type = _normalize_task_type(thread.get("task_type"))
    requested_task_type = _detect_requested_task_type(content)
    has_existing_work = _thread_has_existing_work(thread, prior_message_count=prior_message_count)

    if requested_task_type is None:
        return current_task_type, thread, None

    if requested_task_type != current_task_type:
        if has_existing_work:
            return (
                None,
                thread,
                THREAD_SCOPE_REPLY_TEMPLATE.format(
                    current=_task_type_label(current_task_type),
                    requested=_task_type_label(requested_task_type),
                ),
            )
        switched = await doc_svc.set_thread_task_type(thread["id"], company_id, requested_task_type)
        if switched is not None:
            thread = switched
        current_task_type = requested_task_type

    return current_task_type, thread, None


def _row_to_message(row: dict) -> MWMessageOut:
    return MWMessageOut(
        id=row["id"],
        thread_id=row["thread_id"],
        role=row["role"],
        content=row["content"],
        version_created=row.get("version_created"),
        created_at=row["created_at"],
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


async def _apply_ai_updates_and_operations(
    *,
    thread_id: UUID,
    company_id: UUID,
    task_type: str,
    ai_resp,
    current_state: dict,
    current_version: int,
    user_message: str,
    current_user_id: Optional[UUID] = None,
) -> tuple[dict, int, Optional[str], bool, str]:
    """Apply structured updates, execute supported operations, and return updated response state."""
    normalized_task_type = _normalize_task_type(task_type)
    initial_version = int(current_version)
    pdf_url: Optional[str] = None
    assistant_reply = ai_resp.assistant_reply
    changed = False

    should_execute_skill = bool(
        ai_resp.mode == "skill"
        and (ai_resp.confidence >= 0.65 or not ai_resp.missing_fields)
    )
    force_send_draft = (
        _is_offer_letter_task(normalized_task_type)
        and _looks_like_send_draft_command(user_message)
    )
    can_execute_operation = should_execute_skill or force_send_draft

    if should_execute_skill and ai_resp.structured_update:
        safe_updates = _validate_updates(normalized_task_type, ai_resp.structured_update)
        if safe_updates:
            result = await doc_svc.apply_update(thread_id, safe_updates)
            current_version = result["version"]
            current_state = result["current_state"]
            changed = changed or current_version != initial_version

            if _is_offer_letter_task(normalized_task_type):
                pdf_url = await doc_svc.generate_pdf(
                    current_state, thread_id, current_version, is_draft=True
                )

    operation = str(ai_resp.operation or "none").strip().lower()
    if force_send_draft and operation in {"none", "create", "update", "track"}:
        operation = "send_draft"

    if can_execute_operation and operation not in {"none", "create", "update", "track"}:
        action_note: Optional[str] = None
        try:
            if operation == "save_draft":
                if not _is_offer_letter_task(normalized_task_type):
                    action_note = "Save draft is only available for offer letters."
                else:
                    saved = await doc_svc.save_offer_letter_draft(thread_id, company_id)
                    action_note = f"Saved draft successfully ({saved['offer_status']})."
            elif operation == "send_draft":
                if not _is_offer_letter_task(normalized_task_type):
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
                if normalized_task_type != "review":
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
                if normalized_task_type != "onboarding":
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

    task_type = _normalize_task_type(body.task_type)
    if task_type == "review":
        default_title = "Untitled Review"
    elif task_type == "workbook":
        default_title = "Untitled Workbook"
    elif task_type == "onboarding":
        default_title = "New Onboarding"
    else:
        default_title = "Untitled Chat"

    title = body.title or default_title
    thread = await doc_svc.create_thread(company_id, current_user.id, title, task_type=task_type)
    thread_id = thread["id"]

    assistant_reply = None
    pdf_url = None

    if body.initial_message:
        # Save user message
        await doc_svc.add_message(thread_id, "user", body.initial_message)
        resolved_task_type, thread, unsupported_reply = await _resolve_task_type_for_message(
            thread,
            company_id,
            body.initial_message,
            prior_message_count=0,
        )

        if unsupported_reply:
            await doc_svc.add_message(thread_id, "assistant", unsupported_reply)
            assistant_reply = unsupported_reply
        else:
            # Call AI
            ai_provider = get_ai_provider()
            messages = [{"role": "user", "content": body.initial_message}]
            estimated_usage = await ai_provider.estimate_usage(
                messages, thread["current_state"], task_type=resolved_task_type
            )
            ai_resp = await ai_provider.generate(
                messages, thread["current_state"], task_type=resolved_task_type
            )
            final_usage = ai_resp.token_usage or estimated_usage

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
                task_type=resolved_task_type,
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
            thread["task_type"] = resolved_task_type
            assistant_reply = assistant_reply_text

    return CreateThreadResponse(
        id=thread_id,
        title=thread["title"],
        task_type=thread["task_type"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
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

    if thread["task_type"] != "offer_letter":
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

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = await doc_svc.get_thread_messages(thread_id)

    return ThreadDetailResponse(
        id=thread["id"],
        title=thread["title"],
        task_type=thread["task_type"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
        is_pinned=thread.get("is_pinned", False),
        linked_offer_letter_id=thread.get("linked_offer_letter_id"),
        created_at=thread["created_at"],
        updated_at=thread["updated_at"],
        messages=[_row_to_message(m) for m in messages],
    )


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

    # Save user message
    user_msg = await doc_svc.add_message(thread_id, "user", body.content)

    # Fetch message history for context (sliding window handled by AI provider)
    messages = await doc_svc.get_thread_messages(thread_id)
    msg_dicts = [{"role": m["role"], "content": m["content"]} for m in messages]
    prior_message_count = max(0, len(messages) - 1)
    resolved_task_type, thread, unsupported_reply = await _resolve_task_type_for_message(
        thread,
        company_id,
        body.content,
        prior_message_count=prior_message_count,
    )

    if unsupported_reply:
        assistant_msg = await doc_svc.add_message(
            thread_id,
            "assistant",
            unsupported_reply,
            version_created=None,
        )
        return SendMessageResponse(
            user_message=_row_to_message(user_msg),
            assistant_message=_row_to_message(assistant_msg),
            current_state=thread["current_state"],
            version=thread["version"],
            pdf_url=None,
            token_usage=None,
        )

    await billing_service.check_credits(company_id)

    # Call AI
    ai_provider = get_ai_provider()
    estimated_usage = await ai_provider.estimate_usage(
        msg_dicts, thread["current_state"], task_type=resolved_task_type
    )
    ai_resp = await ai_provider.generate(
        msg_dicts, thread["current_state"], task_type=resolved_task_type
    )
    final_usage = ai_resp.token_usage or estimated_usage

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
        task_type=resolved_task_type,
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

    try:
        async with get_connection() as conn:
            async with conn.transaction():
                await billing_service.deduct_credit(
                    conn,
                    company_id=company_id,
                    thread_id=thread_id,
                    user_id=current_user.id,
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

    return SendMessageResponse(
        user_message=_row_to_message(user_msg),
        assistant_message=_row_to_message(assistant_msg),
        current_state=current_state,
        version=current_version,
        pdf_url=pdf_url,
        token_usage=final_usage,
    )


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

    # Save user message before streaming
    user_msg = await doc_svc.add_message(thread_id, "user", body.content)

    # Fetch message history for context (sliding window handled by AI provider)
    messages = await doc_svc.get_thread_messages(thread_id)
    msg_dicts = [{"role": m["role"], "content": m["content"]} for m in messages]
    prior_message_count = max(0, len(messages) - 1)
    resolved_task_type, thread, unsupported_reply = await _resolve_task_type_for_message(
        thread,
        company_id,
        body.content,
        prior_message_count=prior_message_count,
    )

    if unsupported_reply:
        assistant_msg = await doc_svc.add_message(
            thread_id,
            "assistant",
            unsupported_reply,
            version_created=None,
        )
        unsupported_response = SendMessageResponse(
            user_message=_row_to_message(user_msg),
            assistant_message=_row_to_message(assistant_msg),
            current_state=thread["current_state"],
            version=thread["version"],
            pdf_url=None,
            token_usage=None,
        )

        async def unsupported_stream():
            yield _sse_data({"type": "complete", "data": unsupported_response.model_dump(mode="json")})
            yield "data: [DONE]\n\n"

        return StreamingResponse(unsupported_stream(), media_type="text/event-stream")

    await billing_service.check_credits(company_id)

    ai_provider = get_ai_provider()
    estimated_usage = await ai_provider.estimate_usage(
        msg_dicts, thread["current_state"], task_type=resolved_task_type
    )

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
                msg_dicts, thread["current_state"], task_type=resolved_task_type
            )

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
                task_type=resolved_task_type,
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

            try:
                async with get_connection() as conn:
                    async with conn.transaction():
                        await billing_service.deduct_credit(
                            conn,
                            company_id=company_id,
                            thread_id=thread_id,
                            user_id=current_user.id,
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
                pdf_url=pdf_url,
                token_usage=final_usage,
            )

            yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})
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
    period_days: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get Matcha Work token usage totals for the current user, grouped by model."""
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
    if _is_offer_letter_task(thread["task_type"]):
        pdf_url = await doc_svc.generate_pdf(new_state, thread_id, new_version, is_draft=True)

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
    if not _is_offer_letter_task(thread["task_type"]):
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
    if not _is_offer_letter_task(thread["task_type"]):
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
    pdf_url = await doc_svc.generate_pdf(state, thread_id, target_version, is_draft=is_draft)

    if pdf_url is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable")

    return {"pdf_url": pdf_url, "version": target_version}


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
    if _normalize_task_type(thread.get("task_type")) != "workbook":
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
            RETURNING id, title, task_type, status, version, is_pinned, created_at, updated_at
            """,
            body.title,
            thread_id,
            company_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    await doc_svc.sync_element_record(thread_id)

    return ThreadListItem(**dict(row))


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
