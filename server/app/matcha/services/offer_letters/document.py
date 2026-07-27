"""Offer letter document generation + the candidate salary-range email.

Moved from routes/employee_lifecycle/offer_letters.py (refactor round 2,
stage 3). `_safe` / `_generate_benefits_text` / `_generate_contingencies_text`
had no other consumer in the route file, so they moved along with
`_generate_offer_letter_html` rather than being left behind as orphans.
"""
import html
import logging
from urllib.parse import quote

from app.config import get_settings
from app.core.services.email import EmailService

logger = logging.getLogger(__name__)


def _safe(value: str | None, default: str = "") -> str:
    """HTML-escape a string value for safe embedding in templates."""
    return html.escape(str(value)) if value else default


def _generate_benefits_text(offer: dict) -> str:
    """Generate plain English benefits text from structured data."""
    parts = []

    if offer.get("benefits_medical"):
        medical = "medical insurance"
        if offer.get("benefits_medical_coverage"):
            medical += f" (employer covers {offer['benefits_medical_coverage']}% of premiums)"
        if offer.get("benefits_medical_waiting_days") and offer["benefits_medical_waiting_days"] > 0:
            medical += f" after a {offer['benefits_medical_waiting_days']}-day waiting period"
        parts.append(medical)

    if offer.get("benefits_dental"):
        parts.append("dental insurance")

    if offer.get("benefits_vision"):
        parts.append("vision insurance")

    if offer.get("benefits_401k"):
        k401 = "401(k) retirement plan"
        if offer.get("benefits_401k_match"):
            k401 += f" with {offer['benefits_401k_match']}"
        parts.append(k401)

    if offer.get("benefits_wellness"):
        parts.append(f"wellness benefits ({offer['benefits_wellness']})")

    if offer.get("benefits_pto_vacation") or offer.get("benefits_pto_sick"):
        pto_parts = []
        if offer.get("benefits_pto_vacation"):
            pto_parts.append("vacation")
        if offer.get("benefits_pto_sick"):
            pto_parts.append("sick leave")
        parts.append(f"paid time off ({' and '.join(pto_parts)})")

    if offer.get("benefits_holidays"):
        parts.append("paid holidays")

    if offer.get("benefits_other"):
        parts.append(offer["benefits_other"])

    if not parts:
        return ""

    # Join with proper grammar
    if len(parts) == 1:
        return f"You will be eligible for {parts[0]}."
    elif len(parts) == 2:
        return f"You will be eligible for {parts[0]} and {parts[1]}."
    else:
        return f"You will be eligible for {', '.join(parts[:-1])}, and {parts[-1]}."


def _generate_contingencies_text(offer: dict) -> str:
    """Generate contingencies text for the offer letter."""
    contingencies = []
    if offer.get("contingency_background_check"):
        contingencies.append("background check")
    if offer.get("contingency_credit_check"):
        contingencies.append("credit check")
    if offer.get("contingency_drug_screening"):
        contingencies.append("drug screening")

    base = "This offer of employment is contingent upon your authorization to work in the United States, as required by federal law."

    if contingencies:
        if len(contingencies) == 1:
            contingency_list = contingencies[0]
        elif len(contingencies) == 2:
            contingency_list = f"{contingencies[0]} and {contingencies[1]}"
        else:
            contingency_list = f"{', '.join(contingencies[:-1])}, and {contingencies[-1]}"
        return f"{base} This offer is also contingent upon the successful completion of the following: {contingency_list}."

    return base


def _generate_offer_letter_html(
    offer: dict, logo_src: str | None = None, signature: dict | None = None,
) -> str:
    """Generate HTML for the offer letter PDF.

    `signature`, when provided (typed-name acceptance via /offer/:token),
    renders the candidate block as an electronic-signature record instead
    of a blank line — {"name": str, "signed_at": datetime, "ip": str}.
    """
    # Format dates
    created_date = offer["created_at"].strftime("%B %d, %Y") if offer.get("created_at") else ""
    start_date = offer["start_date"].strftime("%B %d, %Y") if offer.get("start_date") else "TBD"
    expiration_date = offer["expiration_date"].strftime("%B %d, %Y") if offer.get("expiration_date") else None

    # Generate benefits and contingencies text (already plain text, escape for HTML)
    benefits_text = _safe(_generate_benefits_text(offer))
    contingencies_text = _safe(_generate_contingencies_text(offer))

    # Escape all user-provided fields
    company_name = _safe(offer.get("company_name"))
    candidate_name = _safe(offer.get("candidate_name"))
    position_title = _safe(offer.get("position_title"))
    manager_name = _safe(offer.get("manager_name"), "the Hiring Manager")
    manager_title = _safe(offer.get("manager_title"))
    salary = _safe(offer.get("salary"), "TBD")
    bonus = _safe(offer.get("bonus"), "N/A")
    stock_options = _safe(offer.get("stock_options"), "N/A")
    employment_type = _safe(offer.get("employment_type"), "Full-Time Exempt")
    location = _safe(offer.get("location"), "Remote")

    # Accept-by clause
    accept_by_clause = ""
    if expiration_date:
        accept_by_clause = f"""
        <p style="margin-top: 20px;">
            Please sign and return this offer by <strong>{expiration_date}</strong>.
            If the offer is not accepted by this date, it may be withdrawn.
        </p>
        """

    # Logo section — sanitize URL
    logo_html = ""
    if logo_src:
        safe_url = quote(logo_src, safe=":/?#[]@!$&'()*+,;=,%")
        logo_html = f'<img src="{safe_url}" alt="Company Logo" style="max-height: 60px; max-width: 200px;" />'

    # Candidate signature block — blank line pre-signing, electronic record after
    if signature and signature.get("name"):
        signed_name = _safe(signature.get("name"))
        signed_at_val = signature.get("signed_at")
        signed_at_str = signed_at_val.strftime("%B %d, %Y %I:%M %p UTC") if signed_at_val else ""
        signer_ip = _safe(signature.get("ip"))
        candidate_signature_html = f"""
                <div class="signature-name" style="font-style: italic; border-bottom: 1px solid #333; padding-bottom: 8px;">{signed_name}</div>
                <div class="signature-title">Candidate Acceptance (Electronic Signature)</div>
        """
        signature_disclosure_html = f"""
        <p style="margin-top: 40px; font-size: 8pt; color: #999;">
            Electronically signed by {signed_name} on {signed_at_str}{f" from IP {signer_ip}" if signer_ip else ""}.
            This constitutes acceptance of the offer above.
        </p>
        """
    else:
        candidate_signature_html = f"""
                <div class="signature-line"></div>
                <div class="signature-name">{candidate_name}</div>
                <div class="signature-title">Candidate Acceptance</div>
        """
        signature_disclosure_html = ""

    html_out = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 12pt;
                line-height: 1.6;
                color: #1a1a1a;
                max-width: 700px;
                margin: 40px auto;
                padding: 40px;
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                border-bottom: 1px solid #e5e5e5;
                padding-bottom: 20px;
                margin-bottom: 30px;
            }}
            .company-name {{
                font-size: 18pt;
                font-weight: bold;
                margin-bottom: 5px;
            }}
            .subtitle {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 2px;
                color: #666;
            }}
            .date-block {{
                text-align: right;
            }}
            .date-label {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #666;
            }}
            .section-title {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 2px;
                color: #666;
                border-bottom: 1px solid #e5e5e5;
                padding-bottom: 8px;
                margin-bottom: 15px;
                margin-top: 30px;
            }}
            .terms-grid {{
                background: #f9f9f9;
                padding: 20px;
                border: 1px solid #e5e5e5;
                margin: 20px 0;
            }}
            .terms-row {{
                display: flex;
                margin-bottom: 15px;
            }}
            .terms-item {{
                flex: 1;
            }}
            .terms-label {{
                font-size: 9pt;
                text-transform: uppercase;
                color: #666;
                margin-bottom: 3px;
            }}
            .terms-value {{
                font-weight: bold;
            }}
            .signature-section {{
                margin-top: 60px;
                padding-top: 30px;
                border-top: 1px solid #e5e5e5;
                display: flex;
                justify-content: space-between;
            }}
            .signature-block {{
                width: 45%;
            }}
            .signature-line {{
                border-bottom: 1px solid #333;
                height: 40px;
                margin-bottom: 8px;
            }}
            .signature-name {{
                font-weight: bold;
            }}
            .signature-title {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #666;
            }}
            .at-will-section {{
                margin-top: 30px;
            }}
            .at-will-title {{
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .at-will-text {{
                font-size: 11pt;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                {logo_html}
                <div class="company-name">{company_name}</div>
                <div class="subtitle">Official Offer of Employment</div>
            </div>
            <div class="date-block">
                <div class="date-label">Date</div>
                <div><strong>{created_date}</strong></div>
            </div>
        </div>

        <p>Dear <strong>{candidate_name}</strong>,</p>

        <p>
            We are pleased to offer you the position of <strong>{position_title}</strong>
            at <strong>{company_name}</strong>. We were very impressed with your background
            and believe your skills and experience will be a valuable addition to our team.
        </p>

        <p>
            Should you accept this offer, you will report to <strong>{manager_name}</strong>{f", {manager_title}" if offer.get('manager_title') else ""}.
        </p>

        <div class="terms-grid">
            <div class="section-title" style="margin-top: 0;">Compensation & Terms</div>
            <div class="terms-row">
                <div class="terms-item">
                    <div class="terms-label">Annual Salary</div>
                    <div class="terms-value">{salary}</div>
                </div>
                <div class="terms-item">
                    <div class="terms-label">Start Date</div>
                    <div class="terms-value">{start_date}</div>
                </div>
            </div>
            <div class="terms-row">
                <div class="terms-item">
                    <div class="terms-label">Bonus Potential</div>
                    <div class="terms-value">{bonus}</div>
                </div>
                <div class="terms-item">
                    <div class="terms-label">Equity / Options</div>
                    <div class="terms-value">{stock_options}</div>
                </div>
            </div>
            <div class="terms-row">
                <div class="terms-item">
                    <div class="terms-label">Employment Type</div>
                    <div class="terms-value">{employment_type}</div>
                </div>
                <div class="terms-item">
                    <div class="terms-label">Location</div>
                    <div class="terms-value">{location}</div>
                </div>
            </div>
        </div>

        <div class="section-title">Benefits</div>
        <p>{benefits_text if benefits_text else 'Standard company benefits package.'}</p>

        <div class="section-title">Contingencies</div>
        <p>{contingencies_text}</p>

        <div class="at-will-section">
            <div class="at-will-title">At-Will Employment</div>
            <p class="at-will-text">
                Your employment with the Company will be on an at-will basis. This means that either you or
                the Company may terminate the employment relationship at any time, with or without cause
                or notice, subject to applicable law. Nothing in this offer letter or in any other Company
                document or policy should be interpreted as creating a contract of employment for any
                definite period of time.
            </p>
        </div>

        {accept_by_clause}

        <div class="signature-section">
            <div class="signature-block">
                <div class="signature-line"></div>
                <div class="signature-name">{manager_name}</div>
                <div class="signature-title">Authorized Signature</div>
            </div>
            <div class="signature-block">
                {candidate_signature_html}
            </div>
        </div>
        {signature_disclosure_html}
    </body>
    </html>
    """
    return html_out


async def _send_candidate_range_email(
    candidate_email: str,
    company_name: str,
    position_title: str,
    token: str,
    negotiation_round: int,
) -> None:
    """Send magic link email to candidate for salary range submission."""
    settings = get_settings()
    email_svc = EmailService()
    if not email_svc.is_configured():
        logger.warning("[OfferLetters] Email not configured, skipping candidate range email")
        return
    frontend_url = getattr(settings, 'app_base_url', 'http://localhost:5174')
    offer_url = f"{frontend_url}/offer/{token}"
    round_text = f" (Round {negotiation_round})" if negotiation_round > 1 else ""
    subject = f"Salary Range Offer from {company_name}{round_text}"
    html_body = f"""
<html><body style="font-family: sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
<h2 style="color: #16a34a;">You have a salary range offer from {company_name}</h2>
<p>You have been invited to submit your salary range for the <strong>{position_title}</strong> position at <strong>{company_name}</strong>.</p>
<p>The offer uses a blind range matching system — neither party sees the other's exact numbers. The system finds the overlap automatically.</p>
<p style="margin: 24px 0;">
  <a href="{offer_url}" style="background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
    View Offer &amp; Submit Your Range
  </a>
</p>
<p style="color: #666; font-size: 0.9em;">This link expires in 7 days. If you did not expect this email, you can ignore it.</p>
</body></html>"""
    await email_svc.send_email(
        to_email=candidate_email,
        to_name=None,
        subject=subject,
        html_content=html_body,
    )
