"""Broker risk alerts routes (J7 split)."""
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


# ── Risk-trend alerts (read surface for the broker_risk_alerts worker) ───────
@router.get("/risk-alerts")
async def list_broker_risk_alerts(
    include_resolved: bool = Query(False),
    current_user: CurrentUser = Depends(require_broker),
):
    """Risk-trend alerts for the current broker's portfolio.

    Active (unresolved) first, then recently-resolved when include_resolved=true.
    Rows are written by the broker_risk_alerts Celery task.
    """
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]

        rows = await conn.fetch(
            """
            SELECT ra.id, ra.company_id, c.name AS company_name,
                   ra.metric_key, ra.severity, ra.current_value, ra.prior_value,
                   ra.delta_pct, ra.message, ra.is_read, ra.metadata,
                   ra.first_alerted_at, ra.last_alerted_at, ra.resolved_at
            FROM broker_risk_alerts ra
            JOIN companies c ON c.id = ra.company_id
            WHERE ra.broker_id = $1
              AND ($2::bool OR ra.resolved_at IS NULL)
              -- Behavioral Friction & Retention Risk retired 2026-06-08 (EB-broker
              -- feature, low value). Exclude legacy rows so the Alerts tab and the
              -- sidebar's active_unread badge stay in sync.
              AND ra.metric_key <> 'behavioral_friction'
            ORDER BY ra.resolved_at IS NOT NULL, ra.last_alerted_at DESC
            """,
            broker_id,
            include_resolved,
        )

        alerts = []
        for r in rows:
            meta = r["metadata"]
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = None
            meta = meta if isinstance(meta, dict) else {}
            alerts.append({
                "id": str(r["id"]),
                "company_id": str(r["company_id"]),
                "company_name": r["company_name"],
                "metric_key": r["metric_key"],
                "severity": r["severity"],
                "current_value": float(r["current_value"]) if r["current_value"] is not None else None,
                "prior_value": float(r["prior_value"]) if r["prior_value"] is not None else None,
                "delta_pct": float(r["delta_pct"]) if r["delta_pct"] is not None else None,
                "message": r["message"],
                "is_read": r["is_read"],
                # theme-alert extras (null for quantitative trend alerts)
                "kind": meta.get("kind"),
                "suggestion": meta.get("suggestion"),
                "location_name": meta.get("location_name"),
                "first_alerted_at": r["first_alerted_at"].isoformat() if r["first_alerted_at"] else None,
                "last_alerted_at": r["last_alerted_at"].isoformat() if r["last_alerted_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            })
        unread = sum(1 for a in alerts if not a["is_read"] and a["resolved_at"] is None)
        return {"alerts": alerts, "active_unread": unread}
@router.post("/risk-alerts/scan-themes")
async def scan_broker_theme_alerts_endpoint(current_user: CurrentUser = Depends(require_broker)):
    """(Re)generate qualitative risk-theme alerts for the broker's clients from the
    IR Themes & People analysis. Runs in FastAPI (the theme detection needs the DB
    pool, which the alert worker doesn't have). The FE calls this when the Alerts
    tab opens; results land in the same broker_risk_alerts table as trend alerts."""
    from app.matcha.services.broker_theme_alerts import scan_broker_theme_alerts
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]
    return await scan_broker_theme_alerts(broker_id)
@router.post("/risk-alerts/{alert_id}/read")
async def mark_broker_risk_alert_read(
    alert_id: str,
    current_user: CurrentUser = Depends(require_broker),
):
    """Mark a risk-trend alert read. 404 if it belongs to another broker."""
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]

        row = await conn.fetchrow(
            """
            UPDATE broker_risk_alerts
            SET is_read = true
            WHERE id = $1 AND broker_id = $2
            RETURNING id
            """,
            UUID(alert_id),
            broker_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"status": "read"}
