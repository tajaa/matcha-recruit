import asyncio
import json
import os
from uuid import uuid4

import asyncpg
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.models.auth import CurrentUser
from app.database import close_pool, get_connection, init_pool
from app.matcha.routes import employees as employees_routes


def _get_database_url() -> str:
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")


def test_api_create_employee_triggers_google_workspace_onboarding_run():
    database_url = _get_database_url()
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    try:
        asyncio.run(_run_api_employee_onboarding_test(database_url))
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Database unavailable for integration test: {exc}")


async def _run_api_employee_onboarding_test(database_url: str) -> None:
    await init_pool(database_url)

    company_id = uuid4()
    user_id = uuid4()
    email_suffix = uuid4().hex[:8]
    user_email = f"hr-admin-{email_suffix}@itsmatcha.net"
    employee_email = f"new-hire-{email_suffix}@itsmatcha.net"
    personal_email = f"new-hire-personal-{email_suffix}@gmail.com"

    app = FastAPI()
    app.include_router(employees_routes.router, prefix="/api/employees")

    current_user = CurrentUser(id=user_id, email=user_email, role="client")

    async def _override_require_admin_or_client():
        return current_user

    app.dependency_overrides[employees_routes.require_admin_or_client] = _override_require_admin_or_client

    async with get_connection() as conn:
        required_tables_present = await conn.fetchval(
            """
            SELECT
                to_regclass('public.users') IS NOT NULL
                AND to_regclass('public.companies') IS NOT NULL
                AND to_regclass('public.clients') IS NOT NULL
                AND to_regclass('public.employees') IS NOT NULL
                AND to_regclass('public.integration_connections') IS NOT NULL
                AND to_regclass('public.onboarding_runs') IS NOT NULL
                AND to_regclass('public.external_identities') IS NOT NULL
            """
        )
    if not required_tables_present:
        await close_pool()
        pytest.skip("Required tables for onboarding integration test are not present")

    try:
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, email, password_hash, role, is_active)
                VALUES ($1, $2, $3, 'client', TRUE)
                """,
                user_id,
                user_email,
                "test-password-hash",
            )
            await conn.execute(
                """
                INSERT INTO companies (id, name, status)
                VALUES ($1, $2, 'approved')
                """,
                company_id,
                f"Integration Test Co {email_suffix}",
            )
            await conn.execute(
                """
                INSERT INTO clients (id, user_id, company_id, name)
                VALUES ($1, $2, $3, $4)
                """,
                uuid4(),
                user_id,
                company_id,
                "HR Admin",
            )
            await conn.execute(
                """
                INSERT INTO integration_connections (
                    company_id, provider, status, config, secrets, created_by, updated_by
                )
                VALUES ($1, 'google_workspace', 'connected', $2::jsonb, '{}'::jsonb, $3, $3)
                ON CONFLICT (company_id, provider)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    config = EXCLUDED.config,
                    secrets = EXCLUDED.secrets,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                """,
                company_id,
                json.dumps(
                    {
                        "mode": "mock",
                        "domain": "itsmatcha.net",
                        "auto_provision_on_employee_create": True,
                    }
                ),
                user_id,
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/employees",
                json={
                    "work_email": employee_email,
                    "personal_email": personal_email,
                    "first_name": "New",
                    "last_name": "Hire",
                    "work_state": "CA",
                    "employment_type": "full_time",
                    "start_date": "2026-02-17",
                },
            )

        assert response.status_code == 200, response.text
        assert response.json().get("work_email") == employee_email
        assert response.json().get("personal_email") == personal_email
        employee_id = response.json()["id"]

        run_row = None
        step_row = None
        identity_row = None
        for _ in range(20):
            async with get_connection() as conn:
                run_row = await conn.fetchrow(
                    """
                    SELECT id, provider, trigger_source, status
                    FROM onboarding_runs
                    WHERE company_id = $1
                      AND employee_id = $2
                      AND provider = 'google_workspace'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    company_id,
                    employee_id,
                )
                if run_row:
                    step_row = await conn.fetchrow(
                        """
                        SELECT step_key, status
                        FROM onboarding_steps
                        WHERE run_id = $1
                        ORDER BY created_at ASC
                        LIMIT 1
                        """,
                        run_row["id"],
                    )
                    identity_row = await conn.fetchrow(
                        """
                        SELECT provider, external_email, status
                        FROM external_identities
                        WHERE company_id = $1
                          AND employee_id = $2
                          AND provider = 'google_workspace'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        company_id,
                        employee_id,
                    )
            if run_row and identity_row:
                break
            await asyncio.sleep(0.1)

        assert run_row is not None, "Expected onboarding run to be created after employee API call"
        assert run_row["provider"] == "google_workspace"
        assert run_row["trigger_source"] == "employee_create"
        assert run_row["status"] in {"pending", "running", "completed", "failed", "needs_action"}

        assert step_row is not None, "Expected onboarding step for onboarding run"
        assert step_row["step_key"] == "google_workspace.provision_user"

        assert identity_row is not None, "Expected external identity to be created for employee"
        assert identity_row["provider"] == "google_workspace"
        assert identity_row["status"] == "active"
        assert identity_row["external_email"] == employee_email

    finally:
        async with get_connection() as conn:
            await conn.execute("DELETE FROM companies WHERE id = $1", company_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        await close_pool()
