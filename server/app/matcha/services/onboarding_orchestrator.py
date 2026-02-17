"""Orchestrates external provisioning runs for employee onboarding."""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from ...database import get_connection
from .google_workspace_service import GoogleWorkspaceProvisioningError, GoogleWorkspaceService

PROVIDER_GOOGLE_WORKSPACE = "google_workspace"
STEP_GOOGLE_PROVISION_USER = "google_workspace.provision_user"


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _to_step_payload(row) -> dict:
    return {
        "step_id": row["id"],
        "step_key": row["step_key"],
        "status": row["status"],
        "attempts": row["attempts"],
        "last_error": row["last_error"],
        "last_response": _json_object(row["last_response"]),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _to_run_payload(run_row, step_rows: list) -> dict:
    metadata = _json_object(run_row["metadata"])
    retry_of = metadata.get("retry_of_run_id")
    return {
        "run_id": run_row["id"],
        "company_id": run_row["company_id"],
        "employee_id": run_row["employee_id"],
        "provider": run_row["provider"],
        "status": run_row["status"],
        "trigger_source": run_row["trigger_source"],
        "triggered_by": run_row["triggered_by"],
        "retry_of_run_id": retry_of,
        "last_error": run_row["last_error"],
        "started_at": run_row["started_at"],
        "completed_at": run_row["completed_at"],
        "metadata": metadata,
        "created_at": run_row["created_at"],
        "updated_at": run_row["updated_at"],
        "steps": [_to_step_payload(step) for step in step_rows],
    }


async def _insert_audit_log(
    conn,
    *,
    company_id: UUID,
    employee_id: UUID,
    run_id: UUID,
    step_id: Optional[UUID],
    actor_user_id: UUID,
    provider: str,
    action: str,
    status: str,
    detail: Optional[str] = None,
    error_code: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO provisioning_audit_logs (
            company_id, employee_id, run_id, step_id, actor_user_id,
            provider, action, status, detail, error_code, payload
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
        """,
        company_id,
        employee_id,
        run_id,
        step_id,
        actor_user_id,
        provider,
        action,
        status,
        detail,
        error_code,
        json.dumps(payload or {}),
    )


async def _fetch_run_payload(conn, run_id: UUID) -> dict:
    run_row = await conn.fetchrow("SELECT * FROM onboarding_runs WHERE id = $1", run_id)
    if not run_row:
        raise ValueError("Onboarding run not found")
    step_rows = await conn.fetch(
        "SELECT * FROM onboarding_steps WHERE run_id = $1 ORDER BY created_at ASC",
        run_id,
    )
    return _to_run_payload(run_row, list(step_rows))


async def start_google_workspace_onboarding(
    *,
    company_id: UUID,
    employee_id: UUID,
    triggered_by: UUID,
    trigger_source: str = "manual",
    retry_of_run_id: Optional[UUID] = None,
) -> dict:
    service = GoogleWorkspaceService()

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            """
            SELECT id, org_id, email, first_name, last_name
            FROM employees
            WHERE id = $1 AND org_id = $2
            """,
            employee_id,
            company_id,
        )
        if not employee:
            raise ValueError("Employee not found for this company")

        metadata = {}
        if retry_of_run_id:
            metadata["retry_of_run_id"] = str(retry_of_run_id)

        run_row = await conn.fetchrow(
            """
            INSERT INTO onboarding_runs (
                company_id, employee_id, provider, status, trigger_source, triggered_by, metadata
            )
            VALUES ($1, $2, $3, 'pending', $4, $5, $6::jsonb)
            RETURNING *
            """,
            company_id,
            employee_id,
            PROVIDER_GOOGLE_WORKSPACE,
            trigger_source,
            triggered_by,
            json.dumps(metadata),
        )
        run_id = run_row["id"]

        step_row = await conn.fetchrow(
            """
            INSERT INTO onboarding_steps (run_id, step_key, status)
            VALUES ($1, $2, 'pending')
            RETURNING *
            """,
            run_id,
            STEP_GOOGLE_PROVISION_USER,
        )
        step_id = step_row["id"]

        await conn.execute(
            """
            UPDATE onboarding_runs
            SET status = 'running', started_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            run_id,
        )
        await conn.execute(
            """
            UPDATE onboarding_steps
            SET status = 'running', started_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            step_id,
        )

        connection = await conn.fetchrow(
            """
            SELECT *
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_GOOGLE_WORKSPACE,
        )
        if not connection:
            message = "Google Workspace integration is not connected"
            await conn.execute(
                """
                UPDATE onboarding_steps
                SET status = 'needs_action', attempts = attempts + 1, last_error = $2, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                step_id,
                message,
            )
            await conn.execute(
                """
                UPDATE onboarding_runs
                SET status = 'needs_action', last_error = $2, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
                message,
            )
            await _insert_audit_log(
                conn,
                company_id=company_id,
                employee_id=employee_id,
                run_id=run_id,
                step_id=step_id,
                actor_user_id=triggered_by,
                provider=PROVIDER_GOOGLE_WORKSPACE,
                action="provision_user",
                status="error",
                detail=message,
                error_code="integration_not_connected",
            )
            return await _fetch_run_payload(conn, run_id)

        config = _json_object(connection["config"])
        secrets = _json_object(connection["secrets"])
        mode = config.get("mode") or "mock"
        if mode == "api_token" and not secrets.get("access_token"):
            message = "Google Workspace access token is missing"
            await conn.execute(
                """
                UPDATE onboarding_steps
                SET status = 'needs_action', attempts = attempts + 1, last_error = $2, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                step_id,
                message,
            )
            await conn.execute(
                """
                UPDATE onboarding_runs
                SET status = 'needs_action', last_error = $2, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
                message,
            )
            await _insert_audit_log(
                conn,
                company_id=company_id,
                employee_id=employee_id,
                run_id=run_id,
                step_id=step_id,
                actor_user_id=triggered_by,
                provider=PROVIDER_GOOGLE_WORKSPACE,
                action="provision_user",
                status="error",
                detail=message,
                error_code="missing_access_token",
            )
            return await _fetch_run_payload(conn, run_id)

        try:
            result = await service.provision_user(config, secrets, dict(employee))
            await conn.execute(
                """
                UPDATE onboarding_steps
                SET status = 'completed',
                    attempts = attempts + 1,
                    last_error = NULL,
                    last_response = $2::jsonb,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                step_id,
                json.dumps(result),
            )
            await conn.execute(
                """
                UPDATE onboarding_runs
                SET status = 'completed', last_error = NULL, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
            )
            await conn.execute(
                """
                INSERT INTO external_identities (
                    company_id, employee_id, provider, external_user_id, external_email, status, raw_profile
                )
                VALUES ($1, $2, $3, $4, $5, 'active', $6::jsonb)
                ON CONFLICT (employee_id, provider)
                DO UPDATE SET
                    company_id = EXCLUDED.company_id,
                    external_user_id = EXCLUDED.external_user_id,
                    external_email = EXCLUDED.external_email,
                    status = EXCLUDED.status,
                    raw_profile = EXCLUDED.raw_profile,
                    updated_at = NOW()
                """,
                company_id,
                employee_id,
                PROVIDER_GOOGLE_WORKSPACE,
                result.get("external_user_id"),
                result.get("external_email"),
                json.dumps(result),
            )
            await _insert_audit_log(
                conn,
                company_id=company_id,
                employee_id=employee_id,
                run_id=run_id,
                step_id=step_id,
                actor_user_id=triggered_by,
                provider=PROVIDER_GOOGLE_WORKSPACE,
                action="provision_user",
                status="success",
                payload=result,
            )
        except GoogleWorkspaceProvisioningError as exc:
            failed_status = "needs_action" if exc.needs_action else "failed"
            await conn.execute(
                """
                UPDATE onboarding_steps
                SET status = $2,
                    attempts = attempts + 1,
                    last_error = $3,
                    last_response = $4::jsonb,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                step_id,
                failed_status,
                str(exc),
                json.dumps({"error_code": exc.code, "error_message": str(exc)}),
            )
            await conn.execute(
                """
                UPDATE onboarding_runs
                SET status = $2, last_error = $3, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
                failed_status,
                str(exc),
            )
            await _insert_audit_log(
                conn,
                company_id=company_id,
                employee_id=employee_id,
                run_id=run_id,
                step_id=step_id,
                actor_user_id=triggered_by,
                provider=PROVIDER_GOOGLE_WORKSPACE,
                action="provision_user",
                status="error",
                detail=str(exc),
                error_code=exc.code,
                payload={"needs_action": exc.needs_action},
            )
        except Exception as exc:
            message = f"Unexpected provisioning error: {exc}"
            await conn.execute(
                """
                UPDATE onboarding_steps
                SET status = 'failed',
                    attempts = attempts + 1,
                    last_error = $2,
                    last_response = $3::jsonb,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                step_id,
                message,
                json.dumps({"error_code": "unexpected_error", "error_message": message}),
            )
            await conn.execute(
                """
                UPDATE onboarding_runs
                SET status = 'failed', last_error = $2, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
                message,
            )
            await _insert_audit_log(
                conn,
                company_id=company_id,
                employee_id=employee_id,
                run_id=run_id,
                step_id=step_id,
                actor_user_id=triggered_by,
                provider=PROVIDER_GOOGLE_WORKSPACE,
                action="provision_user",
                status="error",
                detail=message,
                error_code="unexpected_error",
            )

        return await _fetch_run_payload(conn, run_id)


async def retry_google_workspace_onboarding(
    *,
    company_id: UUID,
    run_id: UUID,
    triggered_by: UUID,
) -> dict:
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT id, employee_id, status, provider
            FROM onboarding_runs
            WHERE id = $1 AND company_id = $2
            """,
            run_id,
            company_id,
        )
        if not existing:
            raise ValueError("Onboarding run not found for this company")
        if existing["provider"] != PROVIDER_GOOGLE_WORKSPACE:
            raise ValueError("Only Google Workspace runs can be retried by this endpoint")
        if existing["status"] not in {"failed", "needs_action"}:
            raise ValueError("Only failed or needs_action runs can be retried")

        employee_id = existing["employee_id"]

    return await start_google_workspace_onboarding(
        company_id=company_id,
        employee_id=employee_id,
        triggered_by=triggered_by,
        trigger_source="retry",
        retry_of_run_id=run_id,
    )
