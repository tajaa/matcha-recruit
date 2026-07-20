"""Admin platform settings routes (J5 split)."""
import asyncio
import difflib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Depends, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.services.credential_crypto import decrypt_credential_fields
from app.core.services.scope_registry.codify import codified_sql
from app.core.feature_flags import merge_company_features
from app.core.services.email import get_email_service
from app.core.models.compliance import AutoCheckSettings, LocationCreate
from app.core.models.compliance_evals import EvalRunRequest, FindingResolveRequest
from app.core.compliance_registry import (
    TRIGGER_PROFILES,
    LABOR_CATEGORIES, HEALTHCARE_CATEGORIES, ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES, SUPPLEMENTARY_CATEGORIES,
)
from app.core.services.compliance_service import (
    _resolve_industry,
    update_auto_check_settings,
    _jurisdiction_row_to_dict,
    run_compliance_check_background,
    run_compliance_check_stream,
    research_jurisdiction_repo_only,
    get_locations,
    get_location_requirements,
    create_location,
    admin_add_requirement_to_location,
)
from app.core.services.redis_cache import (
    get_redis_cache, cache_get, cache_set, cache_delete, cache_delete_pattern,
    admin_jurisdictions_list_key, admin_jurisdiction_detail_key,
    admin_jurisdiction_data_overview_key, admin_jurisdiction_policy_overview_key,
    admin_bookmarked_requirements_key,
)
from app.core.services.rate_limiter import get_rate_limiter
from app.core.services.auth import hash_password
from app.core.services.platform_settings import (
    get_visible_features, prime_visible_features_cache,
    get_matcha_work_model_mode, prime_matcha_work_model_mode_cache,
    get_jurisdiction_research_model_mode, prime_jurisdiction_research_model_mode_cache,
    get_er_similarity_weights, prime_er_similarity_weights_cache,
    get_tenant_codified_only, prime_tenant_codified_only_cache,
    DEFAULT_ER_SIMILARITY_WEIGHTS, EXPECTED_WEIGHT_KEYS,
)
from app.matcha.services import billing_service as mw_billing_service
from app.config import get_settings
from app.core.services.stripe_service import StripeService, StripeServiceError
from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
from app.core.services.deal_pricing import DealInputs
from app.core.services.deal_full import FullDealInputs
from app.core.services.deal_broker import BrokerInputs
from app.core.services.deal_book import BookInputs


from app.core.services.scope_registry.jurisdiction_chain import (  # noqa: E402
    resolve_jurisdiction_chain as _resolve_jurisdiction_chain,
)

from app.core.models.admin import *  # noqa: F401,F403
from app.core.routes.admin._shared import *  # noqa: F401,F403

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/updates", dependencies=[Depends(require_admin)])
async def list_admin_updates():
    """Product changelog shown at /admin/updates, newest first."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT id, date, category, title, summary, whats_new, how_to_use, setup, notes, tag
            FROM admin_updates
            ORDER BY position ASC
        """)
        out = []
        for r in rows:
            d = dict(r)
            d["date"] = d["date"].isoformat()
            for col in ("whats_new", "how_to_use", "setup", "notes"):
                if isinstance(d[col], str):
                    d[col] = json.loads(d[col])
            out.append({
                "id": d["id"],
                "date": d["date"],
                "category": d["category"],
                "title": d["title"],
                "summary": d["summary"],
                "whatsNew": d["whats_new"],
                "howToUse": d["how_to_use"],
                "setup": d["setup"],
                "notes": d["notes"],
                "tag": d["tag"],
            })
        return out


@router.get("/schedulers", dependencies=[Depends(require_admin)])
async def list_schedulers():
    """List all scheduler settings with live stats."""
    async with get_connection() as conn:
        settings = await conn.fetch(
            "SELECT * FROM scheduler_settings ORDER BY created_at"
        )

        result = []
        for row in settings:
            item = {
                "id": str(row["id"]),
                "task_key": row["task_key"],
                "display_name": row["display_name"],
                "description": row["description"],
                "enabled": row["enabled"],
                "max_per_cycle": row["max_per_cycle"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "stats": {},
            }

            if row["task_key"] == "compliance_checks":
                stats = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(*) FROM business_locations WHERE is_active = true) AS total_locations,
                        (SELECT COUNT(*) FROM business_locations WHERE auto_check_enabled = true AND is_active = true) AS auto_check_enabled,
                        (SELECT MIN(next_auto_check) FROM business_locations WHERE auto_check_enabled = true AND is_active = true) AS next_due,
                        (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours') AS checks_24h,
                        (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours' AND status = 'failed') AS failed_24h
                """)
                last_run = await conn.fetchrow(
                    "SELECT started_at, status FROM compliance_check_log ORDER BY started_at DESC LIMIT 1"
                )
                item["stats"] = {
                    "total_locations": stats["total_locations"],
                    "auto_check_enabled": stats["auto_check_enabled"],
                    "next_due": stats["next_due"].isoformat() if stats["next_due"] else None,
                    "checks_24h": stats["checks_24h"],
                    "failed_24h": stats["failed_24h"],
                    "last_run": last_run["started_at"].isoformat() if last_run else None,
                    "last_run_status": last_run["status"] if last_run else None,
                }

            elif row["task_key"] == "deadline_escalation":
                stats = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(*) FROM upcoming_legislation
                         WHERE current_status NOT IN ('effective', 'dismissed')
                           AND expected_effective_date IS NOT NULL) AS active_count
                """)
                item["stats"] = {
                    "active_legislation": stats["active_count"],
                }
            elif row["task_key"] == "onboarding_reminders":
                stats = await conn.fetchrow(
                    """
                    SELECT
                        (
                            SELECT COUNT(*)
                            FROM employee_onboarding_tasks eot
                            WHERE eot.status = 'pending'
                              AND eot.due_date IS NOT NULL
                              AND eot.due_date < CURRENT_DATE
                        ) AS overdue_tasks,
                        (
                            SELECT COUNT(*)
                            FROM employee_onboarding_tasks eot
                            WHERE eot.status = 'pending'
                              AND eot.due_date IS NOT NULL
                              AND eot.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days'
                        ) AS due_soon_tasks
                    """
                )
                item["stats"] = {
                    "overdue_tasks": stats["overdue_tasks"],
                    "due_soon_tasks": stats["due_soon_tasks"],
                }
            elif row["task_key"] == "risk_assessment":
                ra_stats = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(DISTINCT company_id) FROM risk_assessment_history) AS total_assessed,
                        (SELECT COUNT(*) FROM risk_assessment_history WHERE computed_at > NOW() - INTERVAL '7 days') AS assessments_7d,
                        (SELECT COUNT(*) FROM companies WHERE next_risk_assessment IS NOT NULL AND next_risk_assessment <= NOW()) AS due_now
                """)
                last_run = await conn.fetchrow(
                    "SELECT computed_at, source FROM risk_assessment_history ORDER BY computed_at DESC LIMIT 1"
                )
                item["stats"] = {
                    "total_assessed": ra_stats["total_assessed"],
                    "assessments_7d": ra_stats["assessments_7d"],
                    "due_now": ra_stats["due_now"],
                    "last_run": last_run["computed_at"].isoformat() if last_run else None,
                    "last_source": last_run["source"] if last_run else None,
                }

            result.append(item)

        return result


@router.patch("/schedulers/{task_key}", dependencies=[Depends(require_admin)])
async def update_scheduler(task_key: str, request: SchedulerUpdateRequest):
    """Update scheduler settings (enabled, max_per_cycle)."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM scheduler_settings WHERE task_key = $1", task_key
        )
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")

        updates = []
        params = []
        idx = 1

        if request.enabled is not None:
            updates.append(f"enabled = ${idx}")
            params.append(request.enabled)
            idx += 1
        if request.max_per_cycle is not None:
            updates.append(f"max_per_cycle = ${idx}")
            params.append(request.max_per_cycle)
            idx += 1

        if not updates:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

        updates.append(f"updated_at = NOW()")
        params.append(task_key)

        row = await conn.fetchrow(
            f"UPDATE scheduler_settings SET {', '.join(updates)} WHERE task_key = ${idx} RETURNING *",
            *params,
        )
        return {
            "id": str(row["id"]),
            "task_key": row["task_key"],
            "display_name": row["display_name"],
            "description": row["description"],
            "enabled": row["enabled"],
            "max_per_cycle": row["max_per_cycle"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }


@router.post("/schedulers/{task_key}/trigger", dependencies=[Depends(require_admin)])
async def trigger_scheduler(task_key: str):
    """Manually trigger a scheduler task."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM scheduler_settings WHERE task_key = $1", task_key
        )
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")

    from app.workers.tasks.compliance_checks import (
        enqueue_scheduled_compliance_checks,
        run_deadline_escalation,
    )
    from app.workers.tasks.leave_agent_tasks import run_leave_agent_orchestration
    from app.workers.tasks.onboarding_reminders import run_onboarding_reminders

    if task_key == "compliance_checks":
        enqueue_scheduled_compliance_checks.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Compliance checks enqueued"}
    elif task_key == "deadline_escalation":
        run_deadline_escalation.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Deadline escalation enqueued"}
    elif task_key == "leave_agent_orchestration":
        run_leave_agent_orchestration.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Leave agent orchestration enqueued"}
    elif task_key == "onboarding_reminders":
        run_onboarding_reminders.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Onboarding reminders enqueued"}
    elif task_key == "risk_assessment":
        from app.workers.tasks.risk_assessment import enqueue_scheduled_risk_assessments
        enqueue_scheduled_risk_assessments.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Risk assessment enqueued"}
    elif task_key == "auto_archive":
        from app.workers.tasks.auto_archive import run_auto_archive
        run_auto_archive.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Auto-archive enqueued"}
    elif task_key == "vertical_coverage_sweep":
        from app.workers.tasks.vertical_coverage_sweep import run_vertical_coverage_sweep
        # force=True: an admin pressing Trigger means it, so bypass the
        # enabled-row + once-a-day guards (those exist to stop the hourly worker
        # restart from re-billing Gemini, not to override a human).
        run_vertical_coverage_sweep.delay(force=True)
        return {"status": "triggered", "task_key": task_key, "message": "Vertical coverage sweep enqueued"}
    elif task_key == "location_fips_backfill":
        from app.workers.tasks.location_fips_backfill import run_location_fips_backfill
        # force=True: a human pressing Trigger bypasses the disabled-row guard.
        run_location_fips_backfill.delay(force=True)
        return {"status": "triggered", "task_key": task_key, "message": "Location FIPS backfill enqueued"}
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown task key: {task_key}")


@router.get("/schedulers/stats", dependencies=[Depends(require_admin)])
async def scheduler_stats():
    """Aggregate stats and recent activity for schedulers."""
    async with get_connection() as conn:
        overview = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM business_locations WHERE is_active = true) AS total_locations,
                (SELECT COUNT(*) FROM business_locations WHERE auto_check_enabled = true AND is_active = true) AS auto_check_enabled,
                (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours') AS checks_24h,
                (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours' AND status = 'failed') AS failed_24h
        """)

        recent_logs = await conn.fetch("""
            SELECT
                cl.id,
                cl.location_id,
                cl.company_id,
                bl.name AS location_name,
                cl.check_type,
                cl.status,
                cl.started_at,
                cl.completed_at,
                cl.new_count,
                cl.updated_count,
                cl.alert_count,
                cl.error_message
            FROM compliance_check_log cl
            LEFT JOIN business_locations bl ON bl.id = cl.location_id
            ORDER BY cl.started_at DESC
            LIMIT 20
        """)

        return {
            "overview": {
                "total_locations": overview["total_locations"],
                "auto_check_enabled": overview["auto_check_enabled"],
                "checks_24h": overview["checks_24h"],
                "failed_24h": overview["failed_24h"],
            },
            "recent_logs": [
                {
                    "id": str(row["id"]),
                    "location_id": str(row["location_id"]),
                    "company_id": str(row["company_id"]),
                    "location_name": row["location_name"],
                    "check_type": row["check_type"],
                    "status": row["status"],
                    "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                    "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                    "duration_seconds": (
                        (row["completed_at"] - row["started_at"]).total_seconds()
                        if row["completed_at"] and row["started_at"] else None
                    ),
                    "new_count": row["new_count"],
                    "updated_count": row["updated_count"],
                    "alert_count": row["alert_count"],
                    "error_message": row["error_message"],
                }
                for row in recent_logs
            ],
        }


@router.get("/schedulers/locations", dependencies=[Depends(require_admin)])
async def list_scheduler_locations():
    """List all business locations grouped by company, with auto-check schedule fields."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                bl.id AS location_id,
                bl.name AS location_name,
                bl.city,
                bl.state,
                bl.auto_check_enabled,
                bl.auto_check_interval_days,
                bl.next_auto_check,
                bl.company_id,
                c.name AS company_name,
                (SELECT MAX(cl.started_at) FROM compliance_check_log cl WHERE cl.location_id = bl.id) AS last_compliance_check
            FROM business_locations bl
            JOIN companies c ON c.id = bl.company_id
            WHERE bl.is_active = true
            ORDER BY c.name, bl.name
        """)

        grouped: dict[str, dict] = {}
        for row in rows:
            cid = str(row["company_id"])
            if cid not in grouped:
                grouped[cid] = {
                    "company_id": cid,
                    "company_name": row["company_name"],
                    "locations": [],
                }
            grouped[cid]["locations"].append({
                "id": str(row["location_id"]),
                "name": row["location_name"],
                "city": row["city"],
                "state": row["state"],
                "auto_check_enabled": row["auto_check_enabled"],
                "auto_check_interval_days": row["auto_check_interval_days"],
                "next_auto_check": row["next_auto_check"].isoformat() if row["next_auto_check"] else None,
                "last_compliance_check": row["last_compliance_check"].isoformat() if row["last_compliance_check"] else None,
            })

        return list(grouped.values())


@router.patch("/schedulers/locations/{location_id}", dependencies=[Depends(require_admin)])
async def update_scheduler_location(location_id: UUID, request: LocationScheduleUpdateRequest):
    """Admin override: update auto_check_enabled and/or auto_check_interval_days for any location."""
    async with get_connection() as conn:
        loc = await conn.fetchrow(
            "SELECT id, company_id FROM business_locations WHERE id = $1 AND is_active = true",
            location_id,
        )
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        # If next_auto_check_minutes is set, directly override next_auto_check in the DB
        if request.next_auto_check_minutes is not None:
            await conn.execute(
                "UPDATE business_locations SET next_auto_check = NOW() + $1 * INTERVAL '1 minute', auto_check_enabled = true, updated_at = NOW() WHERE id = $2",
                request.next_auto_check_minutes, location_id,
            )

        # Apply normal auto-check settings if provided
        if request.auto_check_enabled is not None or request.auto_check_interval_days is not None:
            settings = AutoCheckSettings(
                auto_check_enabled=request.auto_check_enabled,
                auto_check_interval_days=request.auto_check_interval_days,
            )
            await update_auto_check_settings(location_id, loc["company_id"], settings)

        # Re-read for response
        row = await conn.fetchrow(
            "SELECT id, auto_check_enabled, auto_check_interval_days, next_auto_check FROM business_locations WHERE id = $1",
            location_id,
        )
        return {
            "id": str(row["id"]),
            "auto_check_enabled": row["auto_check_enabled"],
            "auto_check_interval_days": row["auto_check_interval_days"],
            "next_auto_check": row["next_auto_check"].isoformat() if row["next_auto_check"] else None,
        }


@router.get("/platform-settings", response_model=PlatformSettingsResponse, dependencies=[Depends(require_admin)])
async def get_all_platform_settings():
    visible = await get_visible_features()
    mw_mode = await get_matcha_work_model_mode()
    jr_mode = await get_jurisdiction_research_model_mode()
    er_weights = await get_er_similarity_weights()
    codified_only = await get_tenant_codified_only()
    return {
        "visible_features": visible,
        "matcha_work_model_mode": mw_mode,
        "jurisdiction_research_model_mode": jr_mode,
        "er_similarity_weights": er_weights,
        "tenant_codified_only": codified_only,
    }


@router.get("/platform-settings/features")
async def get_platform_features(admin=Depends(require_admin)):
    visible = await get_visible_features()
    return {"visible_features": visible}


@router.put("/platform-settings/features")
async def update_platform_features(
    body: PlatformFeaturesUpdate,
    admin=Depends(require_admin)
):
    unknown = [k for k in body.visible_features if k not in KNOWN_PLATFORM_ITEMS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown feature keys: {unknown}")
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('visible_features', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.visible_features)
        )
    visible = prime_visible_features_cache(body.visible_features)
    return {"visible_features": visible}


@router.put("/platform-settings/matcha-work-model-mode", dependencies=[Depends(require_admin)])
async def update_matcha_work_model_mode(
    body: MatchaWorkModelModeUpdate,
    admin=Depends(require_admin)
):
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('matcha_work_model_mode', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.mode)
        )
    mode = prime_matcha_work_model_mode_cache(body.mode)
    return {"matcha_work_model_mode": mode}


@router.put("/platform-settings/tenant-codified-only", dependencies=[Depends(require_admin)])
async def update_tenant_codified_only(
    body: TenantCodifiedOnlyUpdate,
    admin=Depends(require_admin)
):
    """Flip whether tenants see ONLY requirements with a verified statute citation.

    Turning it OFF shows every researched row again — nothing was deleted, the
    gate is read-time. Turning it ON is the product's default position: a
    business must not be shown unvetted research as if it were law.
    """
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('tenant_codified_only', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps({"enabled": body.enabled})
        )
    enabled = prime_tenant_codified_only_cache(body.enabled)
    return {"tenant_codified_only": enabled}


@router.put("/platform-settings/jurisdiction-research-model-mode", dependencies=[Depends(require_admin)])
async def update_jurisdiction_research_model_mode(
    body: JurisdictionResearchModelModeUpdate,
    admin=Depends(require_admin)
):
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('jurisdiction_research_model_mode', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.mode)
        )
    mode = prime_jurisdiction_research_model_mode_cache(body.mode)
    return {"jurisdiction_research_model_mode": mode}


@router.get("/platform-settings/er-similarity-weights", dependencies=[Depends(require_admin)])
async def get_er_similarity_weights_endpoint():
    weights = await get_er_similarity_weights()
    return {"er_similarity_weights": weights}


@router.put("/platform-settings/er-similarity-weights", dependencies=[Depends(require_admin)])
async def update_er_similarity_weights(
    body: ERSimilarityWeightsUpdate,
    admin=Depends(require_admin)
):
    if set(body.weights.keys()) != EXPECTED_WEIGHT_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Keys must be exactly: {sorted(EXPECTED_WEIGHT_KEYS)}"
        )
    for k, v in body.weights.items():
        if not (0.0 <= v <= 1.0):
            raise HTTPException(status_code=400, detail=f"Weight '{k}' must be between 0 and 1")
    weight_sum = sum(body.weights.values())
    if abs(weight_sum - 1.0) > 0.05:
        raise HTTPException(status_code=400, detail=f"Weights must sum to ~1.0 (got {weight_sum:.3f})")

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('er_similarity_weights', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.weights)
        )
    weights = prime_er_similarity_weights_cache(body.weights)
    return {"er_similarity_weights": weights}


@router.get(
    "/notifications",
    response_model=AdminNotificationsResponse,
    dependencies=[Depends(require_admin)],
)
async def get_admin_notifications(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Return a chronological activity feed of recent platform events across all companies."""

    # Build the UNION ALL dynamically, skipping any tables that are missing.
    async with get_connection() as conn:
        valid_parts: list[str] = []
        for sq in _NOTIFICATION_SUBQUERIES:
            try:
                # Dry-run with LIMIT 0 to verify the table/columns exist.
                await conn.fetch(f"SELECT * FROM ({sq}) _probe LIMIT 0")
                valid_parts.append(sq)
            except asyncpg.UndefinedTableError:
                logger.debug("Skipping notification subquery (table missing): %s", sq[:60])
            except asyncpg.UndefinedColumnError:
                logger.debug("Skipping notification subquery (column missing): %s", sq[:60])

        if not valid_parts:
            return AdminNotificationsResponse(items=[], total=0)

        union_sql = " UNION ALL ".join(valid_parts)

        # Total count
        count_row = await conn.fetchrow(f"SELECT COUNT(*) AS total FROM ({union_sql}) AS _all")
        total = count_row["total"] if count_row else 0

        # Paginated rows with company name join
        rows = await conn.fetch(
            f"""SELECT n.*, c.name AS company_name
                FROM ({union_sql}) AS n
                LEFT JOIN companies c ON c.id::text = n.company_id
                ORDER BY n.created_at DESC
                LIMIT $1 OFFSET $2""",
            limit,
            offset,
        )

    items: list[AdminNotification] = []
    for row in rows:
        row_type = row["type"]
        row_id = row["id"]
        link_template = _NOTIFICATION_LINK_MAP.get(row_type, "")
        link = link_template.replace("{id}", row_id) if link_template else None

        items.append(
            AdminNotification(
                id=row_id,
                type=row_type,
                title=row["title"] or "",
                subtitle=row["subtitle"],
                severity=row["severity"],
                status=row["status"],
                company_id=row["company_id"],
                company_name=row["company_name"],
                created_at=row["created_at"],
                link=link,
            )
        )

    return AdminNotificationsResponse(items=items, total=total)
