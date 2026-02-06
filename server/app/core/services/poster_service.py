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


CATEGORY_DISPLAY = {
    "posting_requirements": {"label": "POSTING REQUIREMENTS", "color": "#1a3a6b"},
    "minimum_wage": {"label": "MINIMUM WAGE", "color": "#1a5c2e"},
    "overtime": {"label": "OVERTIME", "color": "#7c2d12"},
    "sick_leave": {"label": "SICK LEAVE", "color": "#4a1d6b"},
    "workers_comp": {"label": "WORKERS' COMPENSATION", "color": "#8b1a1a"},
}

# Category ordering for consistent layout
_CATEGORY_ORDER = [
    "minimum_wage",
    "overtime",
    "sick_leave",
    "workers_comp",
    "posting_requirements",
]


def _generate_poster_html(
    jurisdiction_name: str,
    state: str,
    requirements: list[dict],
) -> str:
    """Build HTML for a compliance poster modeled after real DOL workplace posters.

    Produces a dense, high-contrast, official-looking document designed to be
    printed on letter-size paper, laminated, and posted in a breakroom.
    """
    # Group requirements by category
    grouped: dict[str, list[dict]] = {}
    for req in requirements:
        cat = req.get("category", "other")
        grouped.setdefault(cat, []).append(req)

    # Build category panels in a stable order
    panels: list[str] = []
    ordered_cats = [c for c in _CATEGORY_ORDER if c in grouped]
    ordered_cats += [c for c in grouped if c not in _CATEGORY_ORDER]

    for cat in ordered_cats:
        reqs = grouped[cat]
        display = CATEGORY_DISPLAY.get(
            cat, {"label": cat.upper().replace("_", " "), "color": "#333"}
        )
        color = display["color"]
        label = display["label"]

        items_html = ""
        for i, req in enumerate(reqs):
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

            separator = '<hr class="item-rule">' if i > 0 else ""

            # Short values (<=20 chars) go big beside the title;
            # longer values get a full-width block below the title
            is_short_value = value and len(value) <= 20
            if is_short_value:
                value_html = f'<div class="item-value">{value}</div>'
                items_html += f"""{separator}<div class="item">
<div class="item-row">
<div class="item-text">
<div class="item-title">{title}</div>
{f'<div class="item-desc">{description}</div>' if description else ''}
{f'<div class="item-effective">Effective {_safe(effective_str)}</div>' if effective_str else ''}
</div>
{value_html}
</div>
</div>"""
            else:
                value_block = f'<div class="item-value-full">{value}</div>' if value else ""
                items_html += f"""{separator}<div class="item">
<div class="item-title">{title}</div>
{value_block}
{f'<div class="item-desc">{description}</div>' if description else ''}
{f'<div class="item-effective">Effective {_safe(effective_str)}</div>' if effective_str else ''}
</div>"""

        panels.append(f"""<div class="panel" style="border-left-color: {color};">
<div class="panel-header" style="background: {color};">{label}</div>
<div class="panel-body">{items_html}</div>
</div>""")

    # Use two-column layout if 3+ panels
    use_columns = len(panels) >= 3
    if use_columns:
        sections_html = '<div class="grid">' + "".join(panels) + "</div>"
    else:
        sections_html = "".join(panels)

    gen_date = datetime.utcnow().strftime("%B %d, %Y")
    req_count = sum(len(v) for v in grouped.values())

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: letter;
    margin: 0;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: Helvetica, Arial, sans-serif;
    font-size: 8.5pt;
    color: #000;
    line-height: 1.3;
    background: #fff;
}}
.page {{
    width: 8.5in;
    min-height: 11in;
    padding: 0;
    position: relative;
}}

/* ── TOP BANNER ── */
.banner {{
    background: #000;
    color: #fff;
    padding: 16px 28px 14px;
    border-bottom: 4px solid #c00;
}}
.banner h1 {{
    font-size: 20pt;
    font-weight: 900;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    margin: 0 0 2px;
}}
.banner-sub {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}}
.banner-jurisdiction {{
    font-size: 11pt;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
.banner-meta {{
    font-size: 7.5pt;
    color: #aaa;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ── BODY ── */
.body {{
    padding: 12px 20px 8px;
}}

/* ── GRID ── */
.grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}}
.grid .panel {{
    width: calc(50% - 5px);
    flex-shrink: 0;
}}

/* ── PANELS ── */
.panel {{
    border: 1.5px solid #000;
    border-left: 5px solid #333;
    margin-bottom: 10px;
    page-break-inside: avoid;
}}
.panel-header {{
    color: #fff;
    font-size: 7.5pt;
    font-weight: 900;
    letter-spacing: 2.5px;
    padding: 4px 10px;
    text-transform: uppercase;
}}
.panel-body {{
    padding: 6px 10px 8px;
}}

/* ── ITEMS ── */
.item-rule {{
    border: none;
    border-top: 1px solid #ccc;
    margin: 5px 0;
}}
.item-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
}}
.item-text {{
    flex: 1;
    min-width: 0;
}}
.item-title {{
    font-size: 8.5pt;
    font-weight: 800;
    color: #000;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 1px;
}}
.item-value {{
    font-size: 16pt;
    font-weight: 900;
    color: #000;
    white-space: nowrap;
    line-height: 1.1;
    letter-spacing: -0.5px;
    flex-shrink: 0;
    padding-top: 0;
}}
.item-value-full {{
    font-size: 13pt;
    font-weight: 900;
    color: #000;
    line-height: 1.15;
    letter-spacing: -0.3px;
    margin: 2px 0 3px;
}}
.item-desc {{
    font-size: 7.5pt;
    color: #222;
    line-height: 1.35;
    margin-top: 1px;
}}
.item-effective {{
    font-size: 6.5pt;
    color: #555;
    margin-top: 2px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}}

/* ── FOOTER ── */
.footer {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: #000;
    color: #fff;
    padding: 8px 20px;
}}
.footer-notice {{
    font-size: 7.5pt;
    font-weight: 900;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    text-align: center;
    margin-bottom: 4px;
}}
.footer-fine {{
    display: flex;
    justify-content: space-between;
    font-size: 6pt;
    color: #999;
    line-height: 1.4;
}}
.footer-fine-left {{
    max-width: 70%;
}}
.footer-fine-right {{
    text-align: right;
    white-space: nowrap;
}}
</style>
</head>
<body>
<div class="page">

<div class="banner">
<h1>Your Rights Under the Law</h1>
<div class="banner-sub">
<div class="banner-jurisdiction">{_safe(jurisdiction_name)}, {_safe(state)}</div>
<div class="banner-meta">{req_count} requirement{"s" if req_count != 1 else ""}</div>
</div>
</div>

<div class="body">
{sections_html}
</div>

<div class="footer">
<div class="footer-notice">This notice must be posted where employees can readily see it</div>
<div class="footer-fine">
<div class="footer-fine-left">
This document is for informational purposes only and does not constitute legal advice.
Employers must verify accuracy with applicable regulatory agencies and maintain current postings.
</div>
<div class="footer-fine-right">Generated {gen_date}</div>
</div>
</div>

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
