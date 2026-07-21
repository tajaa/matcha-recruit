"""Broker reporting routes (J7 split)."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field

from app.config import get_settings
from app.core.feature_flags import default_company_features_json, merge_company_features
from app.core.models.auth import CurrentUser
from app.core.services.email import get_email_service
from app.database import get_connection
from app.matcha.dependencies import require_broker

from app.matcha.routes.broker.brokers._models import *  # noqa: F401,F403
from app.matcha.routes.broker.brokers._shared import *  # noqa: F401,F403

router = APIRouter()


@router.get("/reporting/portfolio")
async def get_broker_portfolio_reporting(current_user: CurrentUser = Depends(require_broker)):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _expire_stale_setups(conn, broker_id=membership["broker_id"])

        setup_counts = await conn.fetch(
            """
            SELECT status, COUNT(*)::int AS count
            FROM broker_client_setups
            WHERE broker_id = $1
            GROUP BY status
            """,
            membership["broker_id"],
        )
        setup_status_counts = {row["status"]: row["count"] for row in setup_counts}

        try:
            rows = await conn.fetch(
                """
                SELECT
                    c.id AS company_id,
                    c.name AS company_name,
                    l.status AS link_status,
                    COALESCE(s.status, 'none') AS setup_status,
                    COALESCE(ps.active_policy_count, 0) AS active_policy_count,
                    COALESCE(ps.pending_signatures, 0) AS pending_signatures,
                    COALESCE(ps.policy_compliance_rate, 0)::numeric AS policy_compliance_rate,
                    COALESCE(isum.open_incidents, 0) AS open_incidents,
                    COALESCE(es.active_employees, 0) AS active_employees,
                    COALESCE(ptm.total_checks, 0) AS total_checks,
                    COALESCE(ptm.avg_separation_risk, 0) AS avg_separation_risk,
                    COALESCE(ptm.override_rate, 0) AS override_rate
                FROM broker_company_links l
                JOIN companies c ON c.id = l.company_id
                LEFT JOIN broker_client_setups s
                    ON s.broker_id = l.broker_id
                   AND s.company_id = l.company_id
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(DISTINCT p.id)::int AS active_policy_count,
                        COUNT(*) FILTER (WHERE ps.status = 'pending')::int AS pending_signatures,
                        CASE
                            WHEN COUNT(*) = 0 THEN 0
                            ELSE ROUND(
                                (COUNT(*) FILTER (WHERE ps.status = 'signed')::numeric / COUNT(*)::numeric) * 100,
                                1
                            )
                        END AS policy_compliance_rate
                    FROM policies p
                    LEFT JOIN policy_signatures ps ON ps.policy_id = p.id
                    WHERE p.company_id = c.id
                      AND p.status = 'active'
                ) ps ON true
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS open_incidents
                    FROM ir_incidents i
                    WHERE i.company_id = c.id
                      AND i.status IN ('reported', 'investigating', 'action_required')
                ) isum ON true
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS active_employees
                    FROM employees e
                    WHERE e.org_id = c.id
                      AND e.termination_date IS NULL
                ) es ON true
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*)::int AS total_checks,
                        COALESCE(AVG(overall_score), 0)::int AS avg_separation_risk,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE overall_band IN ('high', 'critical')) = 0 THEN 0
                            ELSE ROUND(
                                COUNT(*) FILTER (WHERE overall_band IN ('high', 'critical') AND outcome = 'proceeded')::numeric /
                                NULLIF(COUNT(*) FILTER (WHERE overall_band IN ('high', 'critical')), 0)::numeric,
                                2
                            )
                        END AS override_rate
                    FROM pre_termination_checks ptc
                    WHERE ptc.company_id = c.id
                      AND ptc.computed_at > NOW() - INTERVAL '12 months'
                ) ptm ON true
                WHERE l.broker_id = $1
                  AND l.status <> 'terminated'
                ORDER BY c.name
                """,
                membership["broker_id"],
            )
            has_pre_term = True
        except Exception:
            has_pre_term = False
            rows = await conn.fetch(
                """
                SELECT
                    c.id as company_id,
                    c.name as company_name,
                    l.status as link_status,
                    COALESCE(s.status, 'none') as setup_status,
                    COALESCE(ps.active_policy_count, 0) as active_policy_count,
                    COALESCE(ps.pending_signatures, 0) as pending_signatures,
                    COALESCE(ps.policy_compliance_rate, 0)::numeric as policy_compliance_rate,
                    COALESCE(isum.open_incidents, 0) as open_incidents,
                    COALESCE(es.active_employees, 0) as active_employees
                FROM broker_company_links l
                JOIN companies c ON c.id = l.company_id
                LEFT JOIN broker_client_setups s
                    ON s.broker_id = l.broker_id
                   AND s.company_id = l.company_id
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(DISTINCT p.id)::int AS active_policy_count,
                        COUNT(*) FILTER (WHERE ps.status = 'pending')::int AS pending_signatures,
                        CASE
                            WHEN COUNT(*) = 0 THEN 0
                            ELSE ROUND(
                                (COUNT(*) FILTER (WHERE ps.status = 'signed')::numeric / COUNT(*)::numeric) * 100,
                                1
                            )
                        END AS policy_compliance_rate
                    FROM policies p
                    LEFT JOIN policy_signatures ps ON ps.policy_id = p.id
                    WHERE p.company_id = c.id
                      AND p.status = 'active'
                ) ps ON true
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS open_incidents
                    FROM ir_incidents i
                    WHERE i.company_id = c.id
                      AND i.status IN ('reported', 'investigating', 'action_required')
                ) isum ON true
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS active_employees
                    FROM employees e
                    WHERE e.org_id = c.id
                      AND e.termination_date IS NULL
                ) es ON true
                WHERE l.broker_id = $1
                  AND l.status <> 'terminated'
                ORDER BY c.name
                """,
                membership["broker_id"],
            )

    company_metrics = []
    healthy_count = 0
    at_risk_count = 0
    total_compliance_rate = 0.0
    action_item_total = 0
    for row in rows:
        compliance_rate = float(row["policy_compliance_rate"] or 0)
        active_policy_count = int(row["active_policy_count"] or 0)
        pending_signatures = int(row["pending_signatures"] or 0)
        open_incidents = int(row["open_incidents"] or 0)
        open_action_items = pending_signatures + open_incidents
        action_item_total += open_action_items
        total_compliance_rate += compliance_rate

        # A company with no active policies has a compliance_rate of 0 only because
        # there's nothing to measure — that's "no data", not "at risk". Treating it
        # as at_risk flagged every policy-less client and made the row statuses
        # disagree with the real risk picture. Only let compliance drag a company to
        # at_risk / healthy when there are actually policies to assess.
        has_policy_data = active_policy_count > 0
        if has_policy_data and compliance_rate >= 90 and open_action_items == 0:
            risk_signal = "healthy"
            healthy_count += 1
        elif open_action_items >= 5 or (has_policy_data and compliance_rate < 75):
            risk_signal = "at_risk"
            at_risk_count += 1
        else:
            risk_signal = "watch"

        metrics = {
            "company_id": str(row["company_id"]),
            "company_name": row["company_name"],
            "link_status": row["link_status"],
            "setup_status": row["setup_status"],
            "policy_compliance_rate": compliance_rate,
            "open_action_items": open_action_items,
            "active_employee_count": int(row["active_employees"] or 0),
            "risk_signal": risk_signal,
        }
        if has_pre_term:
            metrics["pre_term_checks"] = int(row.get("total_checks") or 0)
            metrics["avg_separation_risk"] = int(row.get("avg_separation_risk") or 0)
            metrics["separation_override_rate"] = float(row.get("override_rate") or 0)

        company_metrics.append(metrics)

    company_count = len(company_metrics)
    avg_compliance_rate = round(total_compliance_rate / company_count, 1) if company_count else 0.0

    summary = {
        "total_linked_companies": company_count,
        "active_link_count": sum(1 for row in company_metrics if row["link_status"] in {"active", "grace"}),
        "pending_setup_count": setup_status_counts.get("draft", 0) + setup_status_counts.get("invited", 0),
        "expired_setup_count": setup_status_counts.get("expired", 0),
        "healthy_companies": healthy_count,
        "at_risk_companies": at_risk_count,
        "average_policy_compliance_rate": avg_compliance_rate,
        "open_action_item_total": action_item_total,
    }
    if has_pre_term:
        summary["total_pre_term_checks"] = sum(m.get("pre_term_checks", 0) for m in company_metrics)
        summary["avg_portfolio_override_rate"] = round(
            sum(m.get("separation_override_rate", 0) for m in company_metrics) / max(len(company_metrics), 1), 2
        ) if company_metrics else 0

    return {
        "summary": summary,
        "setup_status_counts": setup_status_counts,
        "companies": company_metrics,
        "redaction": {
            "employee_level_pii_included": False,
            "incident_detail_included": False,
            "note": "Broker portfolio reporting is intentionally aggregated for privacy and minimum necessary access.",
        },
    }
@router.get("/referred-clients")
async def list_referred_clients(current_user: CurrentUser = Depends(require_broker)):
    """List all companies that came through this broker's referral link or client setup flow."""
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]

        rows = await conn.fetch(
            """
            SELECT
                c.id AS company_id,
                c.name AS company_name,
                c.industry,
                c.size AS company_size,
                c.status AS company_status,
                bcl.status AS link_status,
                bcl.linked_at,
                bcl.activated_at,
                COUNT(DISTINCT e.id) FILTER (WHERE e.termination_date IS NULL) AS active_employee_count,
                c.enabled_features
            FROM broker_company_links bcl
            JOIN companies c ON c.id = bcl.company_id
            LEFT JOIN employees e ON e.org_id = c.id
            WHERE bcl.broker_id = $1
            GROUP BY c.id, c.name, c.industry, c.size, c.status,
                     bcl.status, bcl.linked_at, bcl.activated_at,
                     c.enabled_features
            ORDER BY bcl.linked_at DESC
            """,
            broker_id,
        )

        broker_slug = await conn.fetchval("SELECT slug FROM brokers WHERE id = $1", broker_id)

        clients = []
        for row in rows:
            features = row["enabled_features"]
            if isinstance(features, str):
                try:
                    features = json.loads(features)
                except Exception:
                    features = {}
            enabled_count = sum(1 for v in (features or {}).values() if v)
            clients.append({
                "company_id": str(row["company_id"]),
                "company_name": row["company_name"],
                "industry": row["industry"],
                "company_size": row["company_size"],
                "company_status": row["company_status"],
                "link_status": row["link_status"],
                "linked_at": row["linked_at"].isoformat() if row["linked_at"] else None,
                "activated_at": row["activated_at"].isoformat() if row["activated_at"] else None,
                "active_employee_count": row["active_employee_count"] or 0,
                "enabled_feature_count": enabled_count,
            })

        return {
            "broker_slug": broker_slug,
            "total": len(clients),
            "clients": clients,
        }
@router.get("/reporting/handbook-coverage")
async def get_broker_handbook_coverage(current_user: CurrentUser = Depends(require_broker)):
    from app.core.services.handbook_service import HandbookService

    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)

        company_ids = [
            str(row["company_id"])
            for row in await conn.fetch(
                "SELECT company_id FROM broker_company_links WHERE broker_id = $1 AND status <> 'terminated'",
                membership["broker_id"],
            )
        ]

    summaries = await HandbookService.compute_coverage_summaries(company_ids)
    return summaries
