"""compliance_service._settings — auto-check settings, check log, pinning, split of _checks.py."""
from contextlib import asynccontextmanager
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

from app.core.services.compliance_service._shared import (
    MAX_VERIFICATIONS_PER_CHECK,
    _heartbeat_while,
    _parse_jsonb_list,
)
from app.core.services.compliance_service._normalize import (
    _missing_required_categories,
    _normalize_category,
    _normalize_requirement_categories,
)
from app.core.services.compliance_service._industry import (
    _get_industry_profile,
    _requirement_applicable_industries,
)
from app.core.services.compliance_service._verification import (
    format_corrections_for_prompt,
    get_recent_corrections,
    score_verification_confidence,
)
from app.core.services.compliance_service._jurisdictions import (
    _authority_label,
    _basis_from_metadata,
    _drop_no_rule_placeholders,
    _fill_missing_categories_from_parents,
    _get_or_create_jurisdiction,
    _is_jurisdiction_fresh,
    _jurisdiction_row_to_dict,
    _load_jurisdiction_requirements,
    _lookup_has_local_ordinance,
    _try_load_county_requirements,
    _try_load_state_requirements,
)
from app.core.services.compliance_service._hierarchy import (
    _compute_triggered_by,
    _filter_city_level_requirements,
    _filter_requirements_for_company,
    _filter_with_preemption,
    _project_chain_to_location,
    codified_gate_sql,
    determine_governing_requirement,
    is_codified_row,
    resolve_jurisdiction_stack,
)
from app.core.services.compliance_service._catalog_writes import (
    _compute_requirement_key,
    _upsert_jurisdiction_legislation,
    _upsert_jurisdiction_requirements_routed,
    _upsert_requirements_additive,
)
from app.core.services.compliance_service._alerts import (
    _complete_check_log,
    _create_alert,
    _create_check_log,
    _log_verification_outcome,
    _notify_company_admins_of_compliance_changes,
    _record_change_notification_item,
    _send_bulk_alert_email,
    escalate_upcoming_deadlines,
    process_upcoming_legislation,
)
from app.core.services.compliance_service._research import (
    _fill_from_state_fallback,
    _refresh_repository_missing_categories,
)
from app.core.services.compliance_service._locations import (
    _sync_requirements_to_location,
    get_location,
)




async def update_auto_check_settings(
    location_id: UUID, company_id: UUID, settings: AutoCheckSettings
) -> Optional[BusinessLocation]:
    """Update auto-check settings for a location."""
    from app.database import get_connection

    async with get_connection() as conn:
        updates = []
        params = []
        param_idx = 3

        if settings.auto_check_enabled is not None:
            updates.append(f"auto_check_enabled = ${param_idx}")
            params.append(settings.auto_check_enabled)
            param_idx += 1
        if settings.auto_check_interval_days is not None:
            updates.append(f"auto_check_interval_days = ${param_idx}")
            params.append(settings.auto_check_interval_days)
            param_idx += 1

        if not updates:
            return await get_location(location_id, company_id)

        # Recompute next_auto_check
        if settings.auto_check_enabled is not None and not settings.auto_check_enabled:
            updates.append("next_auto_check = NULL")
        else:
            if settings.auto_check_interval_days is not None:
                interval = settings.auto_check_interval_days
            else:
                # Use the persisted interval so re-enabling doesn't reset to 7
                updates.append(
                    f"next_auto_check = NOW() + INTERVAL '1 day' * auto_check_interval_days"
                )
                interval = None
            if interval is not None:
                updates.append(
                    f"next_auto_check = NOW() + INTERVAL '1 day' * ${param_idx}"
                )
                params.append(interval)
                param_idx += 1

        updates.append("updated_at = NOW()")
        params.insert(0, location_id)
        params.insert(1, company_id)

        await conn.execute(
            f"UPDATE business_locations SET {', '.join(updates)} WHERE id = $1 AND company_id = $2",
            *params,
        )
        return await get_location(location_id, company_id)




async def get_check_log(
    location_id: UUID, company_id: UUID, limit: int = 20
) -> List[CheckLogEntry]:
    """Get compliance check history for a location."""
    from app.database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM compliance_check_log
            WHERE location_id = $1 AND company_id = $2
            ORDER BY started_at DESC
            LIMIT $3
            """,
            location_id,
            company_id,
            limit,
        )
        return [
            CheckLogEntry(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                company_id=str(row["company_id"]),
                check_type=row["check_type"],
                status=row["status"],
                started_at=row["started_at"].isoformat(),
                completed_at=row["completed_at"].isoformat()
                if row["completed_at"]
                else None,
                new_count=row["new_count"] or 0,
                updated_count=row["updated_count"] or 0,
                alert_count=row["alert_count"] or 0,
                error_message=row["error_message"],
            )
            for row in rows
        ]






async def set_requirement_pinned(
    requirement_id: UUID, company_id: UUID, is_pinned: bool
) -> dict | None:
    from app.database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE compliance_requirements cr
            SET is_pinned = $1
            FROM business_locations bl
            WHERE cr.id = $2
              AND cr.location_id = bl.id
              AND bl.company_id = $3
            RETURNING cr.id, cr.title, cr.is_pinned
            """,
            is_pinned,
            requirement_id,
            company_id,
        )
    if not row:
        return None
    return {"id": str(row["id"]), "title": row["title"], "is_pinned": row["is_pinned"]}




async def get_pinned_requirements(company_id: UUID) -> list[dict]:
    from app.database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT cr.id, cr.category, cr.jurisdiction_level, cr.jurisdiction_name,
                   cr.title, cr.description, cr.current_value, cr.effective_date,
                   cr.source_url, cr.is_pinned,
                   bl.name AS location_name, bl.city, bl.state
            FROM compliance_requirements cr
            JOIN business_locations bl ON cr.location_id = bl.id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = cr.jurisdiction_requirement_id
            WHERE bl.company_id = $1
              AND cr.is_pinned = true
              AND bl.is_active = true
            """
            # A pin is a bookmark into the tab. If the row isn't listed there
            # any more, a pin pointing at it is a dead link.
            + await codified_gate_sql("cat", conn=conn)
            + " ORDER BY cr.category, cr.jurisdiction_level",
            company_id,
        )
    return [
        {
            "id": str(row["id"]),
            "category": row["category"],
            "jurisdiction_level": row["jurisdiction_level"],
            "jurisdiction_name": row["jurisdiction_name"],
            "title": row["title"],
            "description": row["description"],
            "current_value": row["current_value"],
            "effective_date": row["effective_date"].isoformat()
            if row["effective_date"]
            else None,
            "source_url": row["source_url"],
            "is_pinned": row["is_pinned"],
            "location_name": row["location_name"],
            "city": row["city"],
            "state": row["state"],
        }
        for row in rows
    ]




