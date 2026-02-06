"""Service for compliance poster PDF generation and order management."""

import logging
from datetime import datetime
from html import escape
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Categories considered poster-worthy
POSTER_CATEGORIES = [
    "posting_requirements",
    "minimum_wage",
    "overtime",
    "sick_leave",
    "workers_comp",
]


def _safe(val: Optional[str]) -> str:
    """HTML-escape a value, returning empty string for None."""
    return escape(str(val)) if val else ""


def _generate_poster_html(
    jurisdiction_name: str,
    state: str,
    requirements: list[dict],
) -> str:
    """Build HTML for a compliance poster from jurisdiction requirements."""
    sections_html = ""
    for req in requirements:
        title = _safe(req.get("title", ""))
        value = _safe(req.get("current_value", ""))
        description = _safe(req.get("description", ""))
        effective = req.get("effective_date")
        effective_str = ""
        if effective:
            if isinstance(effective, str):
                effective_str = effective
            else:
                effective_str = effective.strftime("%B %d, %Y")

        sections_html += f"""
        <div class="section">
            <div class="section-title">{title}</div>
            {f'<div class="section-value">{value}</div>' if value else ''}
            {f'<div class="section-desc">{description}</div>' if description else ''}
            {f'<div class="section-effective">Effective: {_safe(effective_str)}</div>' if effective_str else ''}
        </div>
        """

    gen_date = datetime.utcnow().strftime("%B %d, %Y")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: letter;
        margin: 0.75in;
    }}
    body {{
        font-family: Arial, Helvetica, sans-serif;
        font-size: 11pt;
        color: #1a1a1a;
        line-height: 1.4;
    }}
    .header {{
        text-align: center;
        border: 3px solid #1a1a1a;
        padding: 16px;
        margin-bottom: 24px;
    }}
    .header h1 {{
        font-size: 22pt;
        margin: 0 0 4px 0;
        letter-spacing: 2px;
    }}
    .header h2 {{
        font-size: 14pt;
        margin: 0;
        font-weight: normal;
        color: #444;
    }}
    .section {{
        border: 1px solid #ccc;
        border-radius: 4px;
        padding: 12px 16px;
        margin-bottom: 12px;
        page-break-inside: avoid;
    }}
    .section-title {{
        font-size: 12pt;
        font-weight: bold;
        color: #1a1a1a;
        margin-bottom: 4px;
        border-bottom: 1px solid #eee;
        padding-bottom: 4px;
    }}
    .section-value {{
        font-size: 14pt;
        font-weight: bold;
        color: #2d6a4f;
        margin: 6px 0;
    }}
    .section-desc {{
        font-size: 10pt;
        color: #444;
        margin: 4px 0;
    }}
    .section-effective {{
        font-size: 9pt;
        color: #666;
        font-style: italic;
        margin-top: 4px;
    }}
    .footer {{
        text-align: center;
        font-size: 8pt;
        color: #888;
        margin-top: 24px;
        border-top: 1px solid #ddd;
        padding-top: 8px;
    }}
</style>
</head>
<body>
    <div class="header">
        <h1>NOTICE TO EMPLOYEES</h1>
        <h2>{_safe(jurisdiction_name)}, {_safe(state)}</h2>
    </div>
    {sections_html}
    <div class="footer">
        This poster was generated on {gen_date} based on current requirements.
        Employers are responsible for verifying accuracy and maintaining up-to-date postings.
    </div>
</body>
</html>"""


async def generate_poster_pdf(conn, jurisdiction_id: UUID) -> dict:
    """Generate a poster PDF for a jurisdiction and upload to storage.

    Returns dict with template info including pdf_url.
    """
    # Get jurisdiction info
    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        raise ValueError(f"Jurisdiction {jurisdiction_id} not found")

    jurisdiction_name = f"{j['city']}, {j['state']}"
    if j["county"]:
        jurisdiction_name = f"{j['city']}, {j['county']} County, {j['state']}"

    # Get poster-worthy requirements
    reqs = await conn.fetch(
        """
        SELECT title, description, current_value, effective_date, category
        FROM jurisdiction_requirements
        WHERE jurisdiction_id = $1
          AND category = ANY($2)
        ORDER BY category, title
        """,
        jurisdiction_id,
        POSTER_CATEGORIES,
    )

    if not reqs:
        # No requirements to poster — mark as failed
        await conn.execute(
            """
            INSERT INTO poster_templates (jurisdiction_id, title, status, description)
            VALUES ($1, $2, 'failed', 'No poster-worthy requirements found')
            ON CONFLICT (jurisdiction_id) DO UPDATE SET
                status = 'failed',
                description = 'No poster-worthy requirements found',
                updated_at = NOW()
            """,
            jurisdiction_id,
            f"Compliance Poster - {jurisdiction_name}",
        )
        return {"status": "failed", "reason": "No poster-worthy requirements"}

    requirements = [dict(r) for r in reqs]
    categories = list(set(r["category"] for r in requirements))

    # Generate HTML and PDF
    html_content = _generate_poster_html(jurisdiction_name, j["state"], requirements)

    try:
        from weasyprint import HTML

        pdf_bytes = HTML(string=html_content).write_pdf()
    except ImportError as e:
        logger.error("WeasyPrint not installed: %s", e)
        await conn.execute(
            """
            INSERT INTO poster_templates (jurisdiction_id, title, status, description)
            VALUES ($1, $2, 'failed', 'PDF generation unavailable')
            ON CONFLICT (jurisdiction_id) DO UPDATE SET
                status = 'failed',
                description = 'PDF generation unavailable',
                updated_at = NOW()
            """,
            jurisdiction_id,
            f"Compliance Poster - {jurisdiction_name}",
        )
        return {"status": "failed", "reason": "WeasyPrint not available"}
    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        await conn.execute(
            """
            INSERT INTO poster_templates (jurisdiction_id, title, status, description)
            VALUES ($1, $2, 'failed', $3)
            ON CONFLICT (jurisdiction_id) DO UPDATE SET
                status = 'failed',
                description = EXCLUDED.description,
                updated_at = NOW()
            """,
            jurisdiction_id,
            f"Compliance Poster - {jurisdiction_name}",
            f"PDF generation error: {str(e)[:200]}",
        )
        return {"status": "failed", "reason": str(e)}

    # Upload to S3
    from .storage import get_storage

    filename = f"poster_{j['state']}_{j['city'].replace(' ', '_')}.pdf"
    pdf_url = await get_storage().upload_file(
        pdf_bytes, filename, prefix="posters", content_type="application/pdf"
    )

    # Upsert template row
    row = await conn.fetchrow(
        """
        INSERT INTO poster_templates (
            jurisdiction_id, title, description, pdf_url, pdf_generated_at,
            categories_included, requirement_count, status, version
        )
        VALUES ($1, $2, $3, $4, NOW(), $5, $6, 'generated', 1)
        ON CONFLICT (jurisdiction_id) DO UPDATE SET
            title = EXCLUDED.title,
            pdf_url = EXCLUDED.pdf_url,
            pdf_generated_at = NOW(),
            categories_included = EXCLUDED.categories_included,
            requirement_count = EXCLUDED.requirement_count,
            status = 'generated',
            version = poster_templates.version + 1,
            updated_at = NOW()
        RETURNING *
        """,
        jurisdiction_id,
        f"Compliance Poster - {jurisdiction_name}",
        f"Labor law posting requirements for {jurisdiction_name}",
        pdf_url,
        categories,
        len(requirements),
    )

    logger.info("Generated poster PDF for %s (v%d, %d requirements)", jurisdiction_name, row["version"], len(requirements))

    return {
        "status": "generated",
        "template_id": str(row["id"]),
        "pdf_url": pdf_url,
        "version": row["version"],
        "requirement_count": len(requirements),
    }


async def check_and_regenerate_poster(conn, jurisdiction_id: UUID) -> Optional[dict]:
    """Check if a poster template needs generation or regeneration.

    Auto-generates a poster if the jurisdiction has poster-worthy requirements
    but no template exists yet. Regenerates if requirements have changed since
    the last generation.

    Returns generation result or None if no action needed.
    """
    # Check if poster-worthy requirements exist for this jurisdiction
    has_reqs = await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1
              AND category = ANY($2)
        )
        """,
        jurisdiction_id,
        POSTER_CATEGORIES,
    )
    if not has_reqs:
        return None

    template = await conn.fetchrow(
        "SELECT id, pdf_generated_at, version FROM poster_templates WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )

    if not template:
        # No template exists but requirements do — auto-generate
        logger.info("Auto-generating poster for jurisdiction %s (has poster-worthy requirements)", jurisdiction_id)
        return await generate_poster_pdf(conn, jurisdiction_id)

    # Template exists — check if requirements have changed since last generation
    if template["pdf_generated_at"]:
        newer = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM jurisdiction_requirements
                WHERE jurisdiction_id = $1
                  AND category = ANY($2)
                  AND last_changed_at > $3
            )
            """,
            jurisdiction_id,
            POSTER_CATEGORIES,
            template["pdf_generated_at"],
        )
        if not newer:
            return None

    logger.info("Poster template for jurisdiction %s is stale, regenerating", jurisdiction_id)
    return await generate_poster_pdf(conn, jurisdiction_id)


async def create_poster_update_alerts(conn, jurisdiction_id: UUID) -> int:
    """Create poster_update alerts for companies with prior orders in this jurisdiction.

    Returns count of alerts created.
    """
    # Find companies that have ordered posters for locations linked to this jurisdiction
    rows = await conn.fetch(
        """
        SELECT DISTINCT po.company_id, bl.id AS location_id
        FROM poster_orders po
        JOIN business_locations bl ON po.location_id = bl.id
        WHERE bl.jurisdiction_id = $1
          AND po.status NOT IN ('cancelled')
        """,
        jurisdiction_id,
    )

    if not rows:
        return 0

    from .compliance_service import _create_alert

    j = await conn.fetchrow(
        "SELECT city, state FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    j_name = f"{j['city']}, {j['state']}" if j else "Unknown"

    count = 0
    for row in rows:
        try:
            await _create_alert(
                conn,
                row["location_id"],
                row["company_id"],
                None,  # requirement_id
                f"Poster Update Available: {j_name}",
                f"Compliance posting requirements have changed for {j_name}. "
                "An updated poster is available. Consider re-ordering to stay compliant.",
                "warning",
                "posting_requirements",
                alert_type="poster_update",
                metadata={"source": "poster_regeneration", "jurisdiction_id": str(jurisdiction_id)},
            )
            count += 1
        except Exception as e:
            logger.error("Failed to create poster alert for company %s: %s", row["company_id"], e)

    if count:
        logger.info("Created %d poster update alerts for jurisdiction %s", count, jurisdiction_id)
    return count


async def generate_all_missing_posters(conn) -> dict:
    """Generate poster templates for all jurisdictions that have poster-worthy
    requirements but no template yet.

    Returns dict with counts: generated, failed, skipped.
    """
    rows = await conn.fetch(
        """
        SELECT DISTINCT jr.jurisdiction_id
        FROM jurisdiction_requirements jr
        LEFT JOIN poster_templates pt ON pt.jurisdiction_id = jr.jurisdiction_id
        WHERE jr.category = ANY($1)
          AND pt.id IS NULL
        """,
        POSTER_CATEGORIES,
    )

    generated = 0
    failed = 0
    for row in rows:
        try:
            result = await generate_poster_pdf(conn, row["jurisdiction_id"])
            if result.get("status") == "generated":
                generated += 1
            else:
                failed += 1
        except Exception as e:
            logger.error("Failed to generate poster for jurisdiction %s: %s", row["jurisdiction_id"], e)
            failed += 1

    logger.info("Bulk poster generation: %d generated, %d failed, %d already existed", generated, failed, len(rows) - generated - failed)
    return {"generated": generated, "failed": failed, "total_missing": len(rows)}
