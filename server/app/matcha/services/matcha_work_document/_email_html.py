"""matcha_work_document — email_html helpers (L6 split).

Extracted from the monolithic service; re-exported by the package __init__.
"""
from typing import Optional
import html
from app.matcha.services.matcha_work_document._coerce import (
    _coerce_bool,
    _coerce_int,
    _coerce_float,
    _coerce_datetime,
)

import logging
logger = logging.getLogger(__name__)

def _render_review_request_email_html(
    review_title: str,
    company_name: str,
    response_url: str,
    custom_message: Optional[str],
) -> str:
    escaped_title = html.escape(review_title.strip() or "Anonymous Performance Review")
    escaped_company = html.escape(company_name.strip() or "Your HR Team")
    message_block = (
        f"<p>{html.escape(custom_message.strip())}</p>"
        if custom_message and custom_message.strip()
        else ""
    )
    return f"""
<!DOCTYPE html>
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #111827; line-height: 1.5;">
    <div style="max-width: 560px; margin: 0 auto; padding: 20px;">
      <h2 style="margin: 0 0 12px;">Anonymous Review Request</h2>
      <p style="margin: 0 0 12px;">{escaped_company} is requesting your feedback for: <strong>{escaped_title}</strong>.</p>
      {message_block}
      <p style="margin: 0 0 16px;">Use the secure link below to submit your review response:</p>
      <p style="margin: 0 0 18px;">
        <a href="{response_url}" style="display: inline-block; background: #16a34a; color: white; padding: 10px 16px; text-decoration: none; border-radius: 6px;">
          Submit Anonymous Review
        </a>
      </p>
      <p style="margin: 0; color: #6b7280; font-size: 12px;">
        If the button does not work, open this link directly: {response_url}
      </p>
    </div>
  </body>
</html>
"""

def _render_offer_letter_draft_email_html(
    *,
    company_name: str,
    candidate_name: str,
    position_title: str,
    custom_message: Optional[str],
) -> str:
    safe_company_name = html.escape(company_name.strip() or "Your HR Team")
    safe_candidate_name = html.escape(candidate_name.strip() or "Candidate")
    safe_position_title = html.escape(position_title.strip() or "Position")
    message_block = (
        f"<p>{html.escape(custom_message.strip())}</p>"
        if custom_message and custom_message.strip()
        else ""
    )
    return f"""
<!DOCTYPE html>
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #111827; line-height: 1.5;">
    <div style="max-width: 560px; margin: 0 auto; padding: 20px;">
      <h2 style="margin: 0 0 12px;">Offer Letter Draft for Review</h2>
      <p style="margin: 0 0 12px;">{safe_company_name} shared an offer letter draft for <strong>{safe_candidate_name}</strong> (<strong>{safe_position_title}</strong>).</p>
      {message_block}
      <p style="margin: 0 0 12px;">The draft PDF is attached to this email for your review.</p>
      <p style="margin: 0; color: #6b7280; font-size: 12px;">
        Sent from Matcha Work.
      </p>
    </div>
  </body>
</html>
"""

def _build_offer_letter_payload(state: dict, fallback_company_name: str) -> dict:
    company_name = (state.get("company_name") or fallback_company_name or "").strip()
    return {
        "candidate_name": (state.get("candidate_name") or "").strip(),
        "position_title": (state.get("position_title") or "").strip(),
        "company_name": company_name,
        "salary": state.get("salary"),
        "bonus": state.get("bonus"),
        "stock_options": state.get("stock_options"),
        "start_date": _coerce_datetime(state.get("start_date")),
        "employment_type": state.get("employment_type"),
        "location": state.get("location"),
        "benefits": state.get("benefits"),
        "manager_name": state.get("manager_name"),
        "manager_title": state.get("manager_title"),
        "expiration_date": _coerce_datetime(state.get("expiration_date")),
        "benefits_medical": _coerce_bool(state.get("benefits_medical"), False),
        "benefits_medical_coverage": _coerce_int(state.get("benefits_medical_coverage")),
        "benefits_medical_waiting_days": _coerce_int(state.get("benefits_medical_waiting_days")) or 0,
        "benefits_dental": _coerce_bool(state.get("benefits_dental"), False),
        "benefits_vision": _coerce_bool(state.get("benefits_vision"), False),
        "benefits_401k": _coerce_bool(state.get("benefits_401k"), False),
        "benefits_401k_match": state.get("benefits_401k_match"),
        "benefits_wellness": state.get("benefits_wellness"),
        "benefits_pto_vacation": _coerce_bool(state.get("benefits_pto_vacation"), False),
        "benefits_pto_sick": _coerce_bool(state.get("benefits_pto_sick"), False),
        "benefits_holidays": _coerce_bool(state.get("benefits_holidays"), False),
        "benefits_other": state.get("benefits_other"),
        "contingency_background_check": _coerce_bool(state.get("contingency_background_check"), False),
        "contingency_credit_check": _coerce_bool(state.get("contingency_credit_check"), False),
        "contingency_drug_screening": _coerce_bool(state.get("contingency_drug_screening"), False),
        "company_logo_url": state.get("company_logo_url"),
        "salary_range_min": _coerce_float(state.get("salary_range_min")),
        "salary_range_max": _coerce_float(state.get("salary_range_max")),
        "candidate_email": state.get("candidate_email"),
    }
