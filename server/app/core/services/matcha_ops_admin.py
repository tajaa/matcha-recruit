"""Read models and mutations for the Matcha Ops admin page."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.core.feature_flags import (
    FEATURE_REQUIRES,
    feature_dependency_violations,
    merge_company_features,
)
from app.core.models.admin_ops import (
    MatchaOpsFeaturePatch,
    OpsCompanyDetail,
    OpsCompanySummary,
    OpsOverview,
)
from app.core.services.company_features import update_company_features
from app.core.services.feature_provenance import feature_provenance, load_active_packs, resolve_addons, resolve_plan
from app.core.services.product_definitions import SELECT_COLUMNS, row_to_product


OPS_FEATURES = frozenset({
    "matcha_ops",
    "matcha_ops_calls_all_members",
    "ems",
    "inventory",
    "inventory_voice",
    "sales_intake",
    "employee_schedule",
    "schedule_intelligence",
    "werk_lite",
})


def _dict_features(raw: Any) -> dict[str, bool]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return {key: bool(value) for key, value in (raw or {}).items()} if isinstance(raw, dict) else {}


def _ops_enabled(features: dict[str, bool]) -> list[str]:
    return sorted(key for key in OPS_FEATURES if features.get(key))


def _summary(row: Any) -> OpsCompanySummary:
    effective = merge_company_features(row["enabled_features"], row["signup_source"])
    violations = feature_dependency_violations(effective)
    return OpsCompanySummary(
        company_id=row["id"],
        company_name=row["name"],
        status=row["status"] or "approved",
        signup_source=row["signup_source"],
        is_personal=bool(row["is_personal"]),
        matcha_ops_enabled=bool(effective.get("matcha_ops")),
        enabled_ops_features=_ops_enabled(effective),
        channel_count=int(row["channel_count"] or 0),
        operations_channel_count=int(row["operations_channel_count"] or 0),
        open_events=int(row["open_events"] or 0),
        low_stock_items=int(row["low_stock_items"] or 0),
        open_orders=int(row["open_orders"] or 0),
        upcoming_shifts=int(row["upcoming_shifts"] or 0),
        pending_schedule_requests=int(row["pending_schedule_requests"] or 0),
        needs_attention=bool(violations) or (
            bool(row["operations_channel_count"] or 0) and not effective.get("matcha_ops")
        ),
    )


async def _company_rows(conn) -> list[Any]:
    return await conn.fetch(
        """
        SELECT c.id, c.name, c.status, c.signup_source,
               COALESCE(c.is_personal, false) AS is_personal,
               c.enabled_features, c.created_at,
               (SELECT COUNT(*) FROM channels ch WHERE ch.company_id = c.id) AS channel_count,
               (SELECT COUNT(*) FROM channels ch WHERE ch.company_id = c.id
                  AND ch.channel_scope = 'operations') AS operations_channel_count,
               (SELECT COUNT(*) FROM ems_events ev WHERE ev.company_id = c.id
                  AND ev.status = 'logged') AS open_events,
               (SELECT COUNT(*) FROM inventory_items ii WHERE ii.company_id = c.id
                  AND ii.archived_at IS NULL
                  AND ii.current_quantity IS NOT NULL
                  AND ii.low_stock_threshold IS NOT NULL
                  AND ii.current_quantity <= ii.low_stock_threshold) AS low_stock_items,
               (SELECT COUNT(*) FROM inventory_orders io WHERE io.company_id = c.id
                  AND io.status IN ('queued', 'ordered')) AS open_orders,
               (SELECT COUNT(*) FROM schedule_shifts ss WHERE ss.company_id = c.id
                  AND ss.status = 'published' AND ss.starts_at >= NOW()) AS upcoming_shifts,
               (SELECT COUNT(*) FROM schedule_requests sr WHERE sr.company_id = c.id
                  AND sr.status = 'pending') AS pending_schedule_requests
        FROM companies c
        WHERE c.deleted_at IS NULL
        ORDER BY c.name
        """
    )


async def list_ops_companies(
    conn,
    *,
    query: str | None = None,
    enabled: bool | None = None,
    needs_attention: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OpsCompanySummary], int]:
    summaries = [_summary(row) for row in await _company_rows(conn)]
    normalized = (query or "").strip().lower()
    filtered = [
        row for row in summaries
        if (not normalized or normalized in row.company_name.lower())
        and (enabled is None or row.matcha_ops_enabled is enabled)
        and (needs_attention is None or row.needs_attention is needs_attention)
    ]
    return filtered[offset:offset + limit], len(filtered)


async def get_ops_overview(conn) -> OpsOverview:
    rows, _ = await list_ops_companies(conn, limit=1_000_000)
    return OpsOverview(
        companies_enabled=sum(row.matcha_ops_enabled for row in rows),
        companies_with_attention=sum(row.needs_attention for row in rows),
        operations_channels=sum(row.operations_channel_count for row in rows),
        open_events=sum(row.open_events for row in rows),
        low_stock_items=sum(row.low_stock_items for row in rows),
        open_orders=sum(row.open_orders for row in rows),
        upcoming_shifts=sum(row.upcoming_shifts for row in rows),
        pending_schedule_requests=sum(row.pending_schedule_requests for row in rows),
    )


async def get_ops_company_detail(conn, *, company_id: UUID) -> OpsCompanyDetail | None:
    row = next((item for item in await _company_rows(conn) if item["id"] == company_id), None)
    if row is None:
        return None
    summary = _summary(row)
    stored = _dict_features(row["enabled_features"])
    effective = merge_company_features(stored, row["signup_source"])

    product_rows = await conn.fetch(f"SELECT {SELECT_COLUMNS} FROM product_definitions")
    products = {item["slug"]: row_to_product(item) for item in product_rows}
    packs = await load_active_packs(conn, company_id)
    provenance = await feature_provenance(
        conn,
        row,
        products,
        packs,
    )
    return OpsCompanyDetail(
        **summary.model_dump(),
        stored_features=stored,
        effective_features=effective,
        dependency_violations={key: list(value) for key, value in feature_dependency_violations(effective).items()},
        feature_provenance=provenance,
        created_at=row["created_at"],
    )


async def update_ops_company_features(
    conn,
    *,
    company_id: UUID,
    updates: MatchaOpsFeaturePatch,
    actor_user_id: UUID,
) -> OpsCompanyDetail:
    unknown = sorted(set(updates.features) - OPS_FEATURES)
    if unknown:
        raise ValueError(f"Unknown Matcha Ops feature: {', '.join(unknown)}")
    await update_company_features(
        conn,
        company_id=company_id,
        updates=updates.features,
        actor_user_id=actor_user_id,
        source="admin_toggle",
    )
    detail = await get_ops_company_detail(conn, company_id=company_id)
    if detail is None:
        raise LookupError("Company not found")
    return detail
