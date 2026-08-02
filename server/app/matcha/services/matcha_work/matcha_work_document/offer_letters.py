"""Offer letter draft save/send."""
import base64
import logging
from typing import Optional
from uuid import UUID

from app.database import get_connection
from app.core.services.email import EmailService
from app.core.services.storage import get_storage

from ._coerce import _parse_jsonb, normalize_recipient_emails, _coerce_offer_draft_recipient_emails
from ._email_html import _build_offer_letter_payload, _render_offer_letter_draft_email_html
from .pdf import generate_pdf
from .messages import add_message
from .elements import _sync_element_for_thread

logger = logging.getLogger(__name__)


async def save_offer_letter_draft(thread_id: UUID, company_id: UUID) -> dict:
    """Persist current thread state into offer_letters as a draft and link the thread."""
    async with get_connection() as conn:
        async with conn.transaction():
            thread_row = await conn.fetchrow(
                """
                SELECT t.current_state, t.status, t.linked_offer_letter_id, c.name AS fallback_company_name
                FROM mw_threads t
                JOIN companies c ON c.id = t.company_id
                WHERE t.id = $1 AND t.company_id = $2
                FOR UPDATE
                """,
                thread_id,
                company_id,
            )
            if thread_row is None:
                raise ValueError("Thread not found")
            if thread_row["status"] == "archived":
                raise ValueError("Cannot save draft for an archived thread")

            state = _parse_jsonb(thread_row["current_state"])
            payload = _build_offer_letter_payload(state, thread_row["fallback_company_name"] or "")

            if not payload["candidate_name"] or not payload["position_title"]:
                raise ValueError("Candidate name and position title are required to save a draft")

            existing_offer_id = thread_row["linked_offer_letter_id"]
            saved = None
            if existing_offer_id is not None:
                saved = await conn.fetchrow(
                    """
                    UPDATE offer_letters
                    SET candidate_name = $1,
                        position_title = $2,
                        company_name = $3,
                        salary = $4,
                        bonus = $5,
                        stock_options = $6,
                        start_date = $7,
                        employment_type = $8,
                        location = $9,
                        benefits = $10,
                        manager_name = $11,
                        manager_title = $12,
                        expiration_date = $13,
                        benefits_medical = $14,
                        benefits_medical_coverage = $15,
                        benefits_medical_waiting_days = $16,
                        benefits_dental = $17,
                        benefits_vision = $18,
                        benefits_401k = $19,
                        benefits_401k_match = $20,
                        benefits_wellness = $21,
                        benefits_pto_vacation = $22,
                        benefits_pto_sick = $23,
                        benefits_holidays = $24,
                        benefits_other = $25,
                        contingency_background_check = $26,
                        contingency_credit_check = $27,
                        contingency_drug_screening = $28,
                        company_logo_url = $29,
                        salary_range_min = $30,
                        salary_range_max = $31,
                        candidate_email = $32,
                        source_thread_id = COALESCE(source_thread_id, $33),
                        status = 'draft',
                        updated_at = NOW()
                    WHERE id = $34 AND company_id = $35
                    RETURNING id, status, updated_at
                    """,
                    payload["candidate_name"],
                    payload["position_title"],
                    payload["company_name"],
                    payload["salary"],
                    payload["bonus"],
                    payload["stock_options"],
                    payload["start_date"],
                    payload["employment_type"],
                    payload["location"],
                    payload["benefits"],
                    payload["manager_name"],
                    payload["manager_title"],
                    payload["expiration_date"],
                    payload["benefits_medical"],
                    payload["benefits_medical_coverage"],
                    payload["benefits_medical_waiting_days"],
                    payload["benefits_dental"],
                    payload["benefits_vision"],
                    payload["benefits_401k"],
                    payload["benefits_401k_match"],
                    payload["benefits_wellness"],
                    payload["benefits_pto_vacation"],
                    payload["benefits_pto_sick"],
                    payload["benefits_holidays"],
                    payload["benefits_other"],
                    payload["contingency_background_check"],
                    payload["contingency_credit_check"],
                    payload["contingency_drug_screening"],
                    payload["company_logo_url"],
                    payload["salary_range_min"],
                    payload["salary_range_max"],
                    payload["candidate_email"],
                    thread_id,
                    existing_offer_id,
                    company_id,
                )

            if saved is None:
                saved = await conn.fetchrow(
                    """
                    INSERT INTO offer_letters (
                        candidate_name, position_title, company_name, company_id, status,
                        salary, bonus, stock_options, start_date, employment_type, location, benefits,
                        manager_name, manager_title, expiration_date,
                        benefits_medical, benefits_medical_coverage, benefits_medical_waiting_days,
                        benefits_dental, benefits_vision, benefits_401k, benefits_401k_match,
                        benefits_wellness, benefits_pto_vacation, benefits_pto_sick,
                        benefits_holidays, benefits_other,
                        contingency_background_check, contingency_credit_check, contingency_drug_screening,
                        company_logo_url, salary_range_min, salary_range_max, candidate_email,
                        source_thread_id
                    )
                    VALUES (
                        $1, $2, $3, $4, 'draft',
                        $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14,
                        $15, $16, $17,
                        $18, $19, $20, $21,
                        $22, $23, $24,
                        $25, $26,
                        $27, $28, $29,
                        $30, $31, $32, $33,
                        $34
                    )
                    RETURNING id, status, updated_at
                    """,
                    payload["candidate_name"],
                    payload["position_title"],
                    payload["company_name"],
                    company_id,
                    payload["salary"],
                    payload["bonus"],
                    payload["stock_options"],
                    payload["start_date"],
                    payload["employment_type"],
                    payload["location"],
                    payload["benefits"],
                    payload["manager_name"],
                    payload["manager_title"],
                    payload["expiration_date"],
                    payload["benefits_medical"],
                    payload["benefits_medical_coverage"],
                    payload["benefits_medical_waiting_days"],
                    payload["benefits_dental"],
                    payload["benefits_vision"],
                    payload["benefits_401k"],
                    payload["benefits_401k_match"],
                    payload["benefits_wellness"],
                    payload["benefits_pto_vacation"],
                    payload["benefits_pto_sick"],
                    payload["benefits_holidays"],
                    payload["benefits_other"],
                    payload["contingency_background_check"],
                    payload["contingency_credit_check"],
                    payload["contingency_drug_screening"],
                    payload["company_logo_url"],
                    payload["salary_range_min"],
                    payload["salary_range_max"],
                    payload["candidate_email"],
                    thread_id,
                )

            await conn.execute(
                """
                UPDATE mw_threads
                SET linked_offer_letter_id = $1, updated_at = NOW()
                WHERE id = $2 AND company_id = $3
                """,
                saved["id"],
                thread_id,
                company_id,
            )
            await _sync_element_for_thread(conn, thread_id)

            return {
                "thread_id": thread_id,
                "linked_offer_letter_id": saved["id"],
                "offer_status": saved["status"],
                "saved_at": saved["updated_at"],
            }


async def send_offer_letter_draft(
    thread_id: UUID,
    company_id: UUID,
    recipient_emails: list[str],
    custom_message: Optional[str] = None,
) -> dict:
    async with get_connection() as conn:
        thread_row = await conn.fetchrow(
            """
            SELECT t.title, t.status, t.current_state, t.version, c.name AS company_name
            FROM mw_threads t
            JOIN companies c ON c.id = t.company_id
            WHERE t.id=$1 AND t.company_id=$2
            """,
            thread_id,
            company_id,
        )
    if thread_row is None:
        raise ValueError("Thread not found")
    if thread_row["status"] == "archived":
        raise ValueError("Cannot send draft from an archived thread")
    if thread_row["status"] == "finalized":
        raise ValueError("Thread is finalized. Draft sending is only available before finalize")

    state = _parse_jsonb(thread_row["current_state"])
    normalized_recipients = normalize_recipient_emails(recipient_emails)
    if not normalized_recipients:
        normalized_recipients = _coerce_offer_draft_recipient_emails(state)
    if not normalized_recipients:
        raise ValueError("At least one valid recipient email is required")
    if len(normalized_recipients) > 20:
        raise ValueError("A maximum of 20 recipients is supported per draft send")

    # Reuse existing draft-save validations and persist the latest state first.
    draft_result = await save_offer_letter_draft(thread_id, company_id)

    version = int(thread_row["version"] or 0)
    pdf_url = await generate_pdf(
        state,
        thread_id,
        version,
        is_draft=True,
        company_id=company_id,
    )
    if not pdf_url:
        raise ValueError("Unable to generate draft PDF")

    try:
        pdf_bytes = await get_storage().download_file(pdf_url)
    except Exception as exc:
        logger.warning("Failed to download Matcha Work draft PDF for thread %s: %s", thread_id, exc)
        raise ValueError("Unable to load draft PDF for email attachment") from exc

    attachment_filename = f"offer-letter-draft-v{version}.pdf"
    attachment = {
        "filename": attachment_filename,
        "content": base64.b64encode(pdf_bytes).decode("ascii"),
        "disposition": "attachment",
    }

    candidate_name = str(state.get("candidate_name") or "").strip()
    position_title = str(state.get("position_title") or "").strip()
    company_name = str(thread_row["company_name"] or "").strip() or "Your HR Team"

    subject = (
        f"Offer letter draft for review — {candidate_name} ({position_title})"
        if candidate_name and position_title
        else "Offer letter draft for review"
    )
    html_content = _render_offer_letter_draft_email_html(
        company_name=company_name,
        candidate_name=candidate_name,
        position_title=position_title,
        custom_message=custom_message,
    )
    text_content = (
        f"{company_name} shared an offer letter draft for {candidate_name or 'a candidate'} "
        f"({position_title or 'position attached'}). The draft PDF is attached for review."
    )

    email_service = EmailService()
    sent_count = 0
    failed_count = 0
    recipients: list[dict] = []

    for recipient_email in normalized_recipients:
        status_value = "failed"
        last_error = None
        if not email_service.is_configured():
            last_error = "email_service_not_configured"
        else:
            try:
                sent = await email_service.send_email(
                    to_email=recipient_email,
                    to_name=None,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    attachments=[attachment],
                )
                if sent:
                    status_value = "sent"
                else:
                    last_error = "send_failed"
            except Exception as exc:
                logger.warning(
                    "Failed to send Matcha Work offer draft email to %s: %s",
                    recipient_email,
                    exc,
                )
                last_error = "send_exception"

        if status_value == "sent":
            sent_count += 1
        else:
            failed_count += 1
        recipients.append(
            {
                "email": recipient_email,
                "status": status_value,
                "last_error": last_error,
            }
        )

    await add_message(
        thread_id,
        "system",
        (
            f"Offer letter draft email send attempted: {sent_count} sent, "
            f"{failed_count} failed ({len(normalized_recipients)} recipient(s))."
        ),
        version_created=None,
    )

    return {
        "thread_id": thread_id,
        "version": version,
        "pdf_url": pdf_url,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "recipients": recipients,
        "linked_offer_letter_id": draft_result["linked_offer_letter_id"],
        "offer_status": draft_result["offer_status"],
        "saved_at": draft_result["saved_at"],
    }
