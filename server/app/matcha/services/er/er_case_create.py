"""ER case creation — the shared INSERT + audit tail.

Moved from routes/er_copilot/_shared.py (refactor round 2, stage 3).
"""
import json
from typing import Optional


async def create_case_core(
    conn,
    *,
    company_id,
    created_by: Optional[str],
    case,
    ip_address: Optional[str] = None,
) -> tuple[dict, list]:
    """Shared INSERT + audit for an ER case, callable outside a request.

    Mirrors IR's `create_incident_core`: the caller owns the connection +
    transaction and schedules the returned background callables (as
    `(fn, args, kwargs)` tuples — here just the risk-assessment refresh). The
    authed `create_case` route wraps this and adapts the callables onto its
    FastAPI `BackgroundTasks`; HR Pilot's hand-off executor schedules them via
    `asyncio.create_task`. `case` is an `ERCaseCreate`.
    """
    # Lazy: these stay in routes/er_copilot/_shared.py (used widely by other
    # route submodules too) — a module-level import here would pull services
    # back into routes.
    from app.matcha.routes.er_copilot._shared import generate_case_number, log_audit

    case_number = generate_case_number()
    row = await conn.fetchrow(
        """
        INSERT INTO er_cases (case_number, title, description, intake_context, created_by, company_id, category, involved_employees)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8::jsonb)
        RETURNING id, case_number, title, description, intake_context, status, company_id, created_by, assigned_to, created_at, updated_at, closed_at, category, outcome, involved_employees
        """,
        case_number,
        case.title,
        case.description,
        json.dumps(case.intake_context) if case.intake_context is not None else None,
        created_by,
        company_id,
        case.category,
        json.dumps([e.model_dump(mode="json") for e in case.involved_employees]) if case.involved_employees else "[]",
    )

    await log_audit(
        conn,
        str(row["id"]),
        created_by,
        "case_created",
        "case",
        str(row["id"]),
        {"title": case.title},
        ip_address,
    )

    bg_callables: list = []
    if row["company_id"]:
        from app.matcha.services.risk_analytics.risk_assessment_service.refresh import refresh_risk_snapshot
        bg_callables.append((refresh_risk_snapshot, (row["company_id"],), {}))

    return dict(row), bg_callables
