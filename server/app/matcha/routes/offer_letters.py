import html
import logging
from io import BytesIO
from typing import List
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from ...database import get_connection
from ..models.offer_letter import OfferLetter, OfferLetterCreate, OfferLetterUpdate
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser
from ...core.services.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter()

# Explicit allowlist of columns that can be updated via PATCH
ALLOWED_UPDATE_COLUMNS = {
    "candidate_name", "position_title", "company_name", "status",
    "salary", "bonus", "stock_options", "start_date", "employment_type",
    "location", "benefits", "manager_name", "manager_title", "expiration_date",
    "benefits_medical", "benefits_medical_coverage", "benefits_medical_waiting_days",
    "benefits_dental", "benefits_vision", "benefits_401k", "benefits_401k_match",
    "benefits_wellness", "benefits_pto_vacation", "benefits_pto_sick",
    "benefits_holidays", "benefits_other",
    "contingency_background_check", "contingency_credit_check", "contingency_drug_screening",
    "company_logo_url",
}


@router.get("", response_model=List[OfferLetter])
async def list_offer_letters(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List offer letters scoped to the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            rows = await conn.fetch(
                """
                SELECT * FROM offer_letters
                WHERE (company_id = $1 OR company_id IS NULL)
                ORDER BY created_at DESC
                """,
                company_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM offer_letters
                WHERE company_id = $1
                ORDER BY created_at DESC
                """,
                company_id,
            )
        return [OfferLetter(**dict(row)) for row in rows]


@router.post("", response_model=OfferLetter)
async def create_offer_letter(
    offer: OfferLetterCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new offer letter draft."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    async with get_connection() as conn:
        # Look up company name from companies table (authoritative source)
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1", company_id
        )
        row = await conn.fetchrow(
            """
            INSERT INTO offer_letters (
                candidate_name, position_title, company_name, company_id,
                salary, bonus,
                stock_options, start_date, employment_type, location, benefits,
                manager_name, manager_title, expiration_date,
                benefits_medical, benefits_medical_coverage, benefits_medical_waiting_days,
                benefits_dental, benefits_vision, benefits_401k, benefits_401k_match,
                benefits_wellness, benefits_pto_vacation, benefits_pto_sick,
                benefits_holidays, benefits_other,
                contingency_background_check, contingency_credit_check, contingency_drug_screening,
                company_logo_url
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26,
                    $27, $28, $29, $30)
            RETURNING *
            """,
            offer.candidate_name,
            offer.position_title,
            company_name,
            company_id,
            offer.salary,
            offer.bonus,
            offer.stock_options,
            offer.start_date,
            offer.employment_type,
            offer.location,
            offer.benefits,
            offer.manager_name,
            offer.manager_title,
            offer.expiration_date,
            offer.benefits_medical,
            offer.benefits_medical_coverage,
            offer.benefits_medical_waiting_days,
            offer.benefits_dental,
            offer.benefits_vision,
            offer.benefits_401k,
            offer.benefits_401k_match,
            offer.benefits_wellness,
            offer.benefits_pto_vacation,
            offer.benefits_pto_sick,
            offer.benefits_holidays,
            offer.benefits_other,
            offer.contingency_background_check,
            offer.contingency_credit_check,
            offer.contingency_drug_screening,
            offer.company_logo_url,
        )
        return OfferLetter(**dict(row))


@router.get("/{offer_id}", response_model=OfferLetter)
async def get_offer_letter(
    offer_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get details of a specific offer letter."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND (company_id = $2 OR company_id IS NULL)",
                offer_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND company_id = $2",
                offer_id,
                company_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="Offer letter not found")
        return OfferLetter(**dict(row))


@router.patch("/{offer_id}", response_model=OfferLetter)
async def update_offer_letter(
    offer_id: UUID,
    update: OfferLetterUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update an offer letter."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"

    async with get_connection() as conn:
        # Check if exists and belongs to company
        exists = await conn.fetchval(
            f"SELECT 1 FROM offer_letters WHERE id = $1 AND {company_filter}",
            offer_id,
            company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Offer letter not found")

        # Build query dynamically (only allow whitelisted columns)
        update_data = {
            k: v for k, v in update.dict(exclude_unset=True).items()
            if k in ALLOWED_UPDATE_COLUMNS
        }
        if not update_data:
            row = await conn.fetchrow(
                f"SELECT * FROM offer_letters WHERE id = $1 AND {company_filter}",
                offer_id,
                company_id,
            )
            return OfferLetter(**dict(row))

        set_clauses = []
        values = []
        idx = 1
        for key, value in update_data.items():
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
            idx += 1

        values.append(offer_id)
        values.append(company_id)
        where_filter = f"(company_id = ${idx + 1} OR company_id IS NULL)" if is_admin else f"company_id = ${idx + 1}"
        query = f"""
            UPDATE offer_letters
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${idx} AND {where_filter}
            RETURNING *
        """

        row = await conn.fetchrow(query, *values)
        return OfferLetter(**dict(row))


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


def _safe(value: str | None, default: str = "") -> str:
    """HTML-escape a string value for safe embedding in templates."""
    return html.escape(str(value)) if value else default


def _generate_offer_letter_html(offer: dict) -> str:
    """Generate HTML for the offer letter PDF."""
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
    if offer.get("company_logo_url"):
        safe_url = quote(offer["company_logo_url"], safe=":/?#[]@!$&'()*+,;=")
        logo_html = f'<img src="{safe_url}" alt="Company Logo" style="max-height: 60px; max-width: 200px;" />'

    html = f"""
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
                <div class="signature-line"></div>
                <div class="signature-name">{candidate_name}</div>
                <div class="signature-title">Candidate Acceptance</div>
            </div>
        </div>
    </body>
    </html>
    """
    return html


@router.get("/{offer_id}/pdf")
async def download_offer_letter_pdf(
    offer_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate and download offer letter as PDF."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND (company_id = $2 OR company_id IS NULL)",
                offer_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND company_id = $2",
                offer_id,
                company_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="Offer letter not found")

        offer = dict(row)

    # Generate HTML
    html_content = _generate_offer_letter_html(offer)

    # Try to use weasyprint for PDF generation
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="offer-letter-{(offer.get("candidate_name") or "draft").replace(" ", "-")}.pdf"'
            }
        )
    except ImportError as e:
        # WeasyPrint not installed - cannot generate PDF
        logger.error(f"WeasyPrint not installed - cannot generate PDF: {e}")
        raise HTTPException(
            status_code=500,
            detail="PDF generation not available. WeasyPrint library is not installed."
        )
    except Exception as e:
        logger.error(f"Failed to generate PDF for offer {offer_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate PDF. Please try again or contact support."
        )


@router.post("/{offer_id}/logo")
async def upload_offer_logo(
    offer_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a company logo for an offer letter."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")

    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"

    async with get_connection() as conn:
        # Check if offer exists and belongs to company
        exists = await conn.fetchval(
            f"SELECT 1 FROM offer_letters WHERE id = $1 AND {company_filter}",
            offer_id,
            company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Offer letter not found")

        # Upload to storage
        storage = get_storage()
        file_bytes = await file.read()

        try:
            url = await storage.upload_file(
                file_bytes,
                file.filename or "logo.png",
                prefix="offer-logos",
                content_type=file.content_type
            )
        except Exception as e:
            logger.error(f"Failed to upload logo for offer {offer_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload logo. Please try again.")

        # Update offer letter with logo URL
        logo_filter = "(company_id = $3 OR company_id IS NULL)" if is_admin else "company_id = $3"
        await conn.execute(
            f"UPDATE offer_letters SET company_logo_url = $1, updated_at = NOW() WHERE id = $2 AND {logo_filter}",
            url,
            offer_id,
            company_id,
        )

        return {"url": url}
