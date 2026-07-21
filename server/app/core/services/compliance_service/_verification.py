"""compliance_service.verification — J6 split of compliance_service.py."""
from typing import Optional, List, AsyncGenerator, Dict, Any, Callable, Tuple
from uuid import UUID
from datetime import date, datetime, timedelta
import asyncio
import json
import logging
import re

import asyncpg
import httpx
from fastapi import HTTPException

from app.core.services.scope_registry.codify import codified_sql
from app.core.services.company_contacts import get_company_name_and_contacts
from app.core.services.jurisdiction_context import (
    get_known_sources,
    record_source,
    extract_domain,
    build_context_prompt,
    get_source_reputations,
    update_source_accuracy,
)
from app.core.models.compliance import (
    BusinessLocation,
    ComplianceRequirement,
    ComplianceAlert,
    LocationCreate,
    LocationUpdate,
    AutoCheckSettings,
    RequirementResponse,
    AlertResponse,
    CheckLogEntry,
    UpcomingLegislationResponse,
    VerificationResult,
    ComplianceSummary,
)
from app.core.compliance_registry import (
    LABOR_CATEGORIES as REQUIRED_LABOR_CATEGORIES,
    HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES,
    LIFE_SCIENCES_CATEGORIES,
    INDUSTRY_TAGS as MEDICAL_COMPLIANCE_INDUSTRY_TAGS,
)

logger = logging.getLogger(__name__)




def score_verification_confidence(sources: List[dict]) -> float:
    """Score confidence based on source quality. Pure function."""
    if not sources:
        return 0.0
    score = 0.0
    weights = {"official": 0.5, "news": 0.25, "blog": 0.05, "other": 0.05}
    for source in sources:
        source_type = source.get("type", "other")
        score += weights.get(source_type, 0.05)
    return min(score, 1.0)




async def score_verification_confidence_with_reputation(
    sources: List[dict],
    jurisdiction_id: UUID,
    conn,
) -> float:
    """Score confidence blending type-based scoring (70%) with historical accuracy (30%).

    Phase 3.2: Enhanced confidence scoring that incorporates source reputation.

    Args:
        sources: List of source dicts with 'type' and 'url' fields
        jurisdiction_id: UUID of the jurisdiction for reputation lookup
        conn: Database connection

    Returns:
        Float confidence score between 0.0 and 1.0
    """
    if not sources:
        return 0.0

    # Get base type-based score (existing logic)
    type_score = score_verification_confidence(sources)

    # Extract domains from sources
    domains = []
    for source in sources:
        url = source.get("url", "")
        domain = extract_domain(url)
        if domain:
            domains.append(domain)

    if not domains:
        # No domains to look up, return type-based score only
        return type_score

    # Get historical accuracy for these domains
    reputations = await get_source_reputations(conn, jurisdiction_id, domains)

    if not reputations:
        return type_score

    # Compute weighted average reputation (weight by source type)
    type_weights = {"official": 0.5, "news": 0.25, "blog": 0.1, "other": 0.1}
    total_weight = 0.0
    weighted_reputation = 0.0

    for source in sources:
        url = source.get("url", "")
        domain = extract_domain(url)
        if domain and domain in reputations:
            source_type = source.get("type", "other")
            weight = type_weights.get(source_type, 0.1)
            weighted_reputation += reputations[domain] * weight
            total_weight += weight

    if total_weight == 0:
        return type_score

    avg_reputation = weighted_reputation / total_weight

    # Blend: 70% type-based, 30% historical accuracy
    blended_score = (type_score * 0.7) + (avg_reputation * 0.3)

    return min(blended_score, 1.0)




async def update_source_reputation(
    conn,
    jurisdiction_id: UUID,
    sources: List[dict],
    was_accurate: bool,
):
    """Update accuracy counters for sources based on admin review.

    Phase 3.2: Called when admin marks a verification outcome as correct/incorrect.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        sources: List of source dicts with 'url' field
        was_accurate: True if the sources provided accurate information
    """
    if not sources or not jurisdiction_id:
        return

    for source in sources:
        url = source.get("url", "")
        domain = extract_domain(url)
        if domain:
            await update_source_accuracy(conn, jurisdiction_id, domain, was_accurate)




async def record_verification_feedback(
    alert_id: UUID,
    user_id: UUID,
    actual_is_change: bool,
    admin_notes: Optional[str] = None,
    correction_reason: Optional[str] = None,
    company_id: Optional[UUID] = None,
) -> bool:
    """Record admin feedback on a verification outcome for calibration.

    Args:
        alert_id: The alert being reviewed
        user_id: The admin reviewing
        actual_is_change: Whether the change actually occurred
        admin_notes: Optional notes explaining the decision
        correction_reason: Category of error if prediction was wrong (misread_date, wrong_jurisdiction, hallucination, etc.)
        company_id: The company owning the alert (for security verification)

    Returns:
        True if feedback was recorded, False if no matching outcome found or unauthorized
    """
    from app.database import get_connection

    async with get_connection() as conn:
        # Security: Verify the alert belongs to the caller's company
        if company_id is not None:
            alert_company = await conn.fetchval(
                "SELECT company_id FROM compliance_alerts WHERE id = $1",
                alert_id,
            )
            if alert_company is None or alert_company != company_id:
                print(
                    f"[Compliance] Unauthorized feedback attempt: alert {alert_id} not owned by company {company_id}"
                )
                return False

        # First, fetch the outcome data for reputation update (Phase 3.2)
        outcome_row = await conn.fetchrow(
            """
            SELECT jurisdiction_id, predicted_is_change, verification_sources
            FROM verification_outcomes
            WHERE alert_id = $1
            """,
            alert_id,
        )

        # Update the verification outcome
        result = await conn.execute(
            """
            UPDATE verification_outcomes
            SET actual_is_change = $1,
                reviewed_by = $2,
                reviewed_at = NOW(),
                admin_notes = $3,
                correction_reason = $4
            WHERE alert_id = $5
            """,
            actual_is_change,
            user_id,
            admin_notes,
            correction_reason,
            alert_id,
        )

        updated = "UPDATE 1" in result

        # Phase 3.2: Update source reputation based on accuracy
        if updated and outcome_row:
            jurisdiction_id = outcome_row["jurisdiction_id"]
            predicted_is_change = outcome_row["predicted_is_change"]
            verification_sources = outcome_row["verification_sources"]

            if jurisdiction_id and verification_sources:
                # Determine if the sources were accurate
                # Sources are accurate if the prediction matched reality
                was_accurate = predicted_is_change == actual_is_change

                # Parse sources if stored as JSON string
                sources = verification_sources
                if isinstance(sources, str):
                    try:
                        sources = json.loads(sources)
                    except (json.JSONDecodeError, TypeError):
                        sources = []

                if sources:
                    await update_source_reputation(
                        conn, jurisdiction_id, sources, was_accurate
                    )

        return updated




async def get_calibration_stats(
    category: Optional[str] = None,
    days: int = 30,
) -> dict:
    """Get confidence calibration statistics for analysis.

    Returns aggregated stats on prediction accuracy by confidence bucket.
    """
    from app.database import get_connection

    async with get_connection() as conn:
        query = """
            SELECT
                CASE
                    WHEN predicted_confidence >= 0.8 THEN 'high (0.8+)'
                    WHEN predicted_confidence >= 0.6 THEN 'medium (0.6-0.8)'
                    WHEN predicted_confidence >= 0.3 THEN 'low (0.3-0.6)'
                    ELSE 'very_low (<0.3)'
                END as confidence_bucket,
                COUNT(*) as total,
                COUNT(actual_is_change) as reviewed,
                SUM(CASE WHEN predicted_is_change = actual_is_change THEN 1 ELSE 0 END) as correct,
                AVG(predicted_confidence) as avg_confidence
            FROM verification_outcomes
            WHERE created_at > NOW() - INTERVAL '1 day' * $1
        """
        params = [days]
        if category:
            query += " AND category = $2"
            params.append(category)
        query += " GROUP BY confidence_bucket ORDER BY avg_confidence DESC"

        rows = await conn.fetch(query, *params)
        return {
            "buckets": [dict(r) for r in rows],
            "days": days,
            "category_filter": category,
        }




async def get_recent_corrections(
    jurisdiction_id: UUID,
    category: Optional[str] = None,
    limit: int = 5,
    conn=None,
) -> List[Dict]:
    """Get recent false positive corrections for a jurisdiction.

    Used in Phase 3.1 to inject correction context into future research prompts.

    ``conn``: use this connection instead of borrowing the app pool. Required from
    CELERY WORKERS — they are deliberately pool-free (each task runs its own
    asyncio loop; an asyncpg pool bound to another loop cannot be reused), so
    ``get_connection()`` raises there. Without it, every research call made from
    the vertical-coverage sweep died here, BEFORE reaching Gemini, and the ledger
    recorded the cells as failed.

    Returns:
        List of dicts with: requirement_key, category, correction_reason, admin_notes, created_at
    """
    from app.database import get_connection
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _borrowed():
        yield conn

    holder = _borrowed() if conn is not None else get_connection()

    async with holder as conn:
        query = """
            SELECT
                vo.requirement_key,
                vo.category,
                vo.correction_reason,
                vo.admin_notes,
                vo.created_at,
                ca.title as alert_title
            FROM verification_outcomes vo
            LEFT JOIN compliance_alerts ca ON vo.alert_id = ca.id
            WHERE vo.jurisdiction_id = $1
              AND vo.actual_is_change = false
              AND vo.predicted_is_change = true
              AND vo.reviewed_at IS NOT NULL
        """
        params = [jurisdiction_id]
        if category:
            query += " AND vo.category = $2"
            params.append(category)
        query += " ORDER BY vo.created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]




def format_corrections_for_prompt(corrections: List[Dict]) -> str:
    """Format corrections list into a prompt-friendly string."""
    if not corrections:
        return ""

    lines = ["PREVIOUS ERRORS TO AVOID (false positives from past research):"]
    for c in corrections:
        reason = c.get("correction_reason") or "unspecified"
        title = c.get("alert_title") or c.get("requirement_key", "unknown")
        notes = c.get("admin_notes")
        line = f"- {title}: marked as false positive (reason: {reason})"
        if notes:
            line += f" — Admin note: {notes}"
        lines.append(line)

    return "\n".join(lines)
