import asyncio
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.models.auth import CurrentUser
from app.matcha.routes import employee_portal as employee_portal_routes
from app.matcha.routes import internal_mobility as internal_mobility_routes


class _ConnectionContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _connection_factory(conn):
    return lambda: _ConnectionContext(conn)


def _scope_resolver_factory(company_id):
    async def _resolver(current_user, requested_company_id=None):
        return {"company_id": requested_company_id or company_id}

    return _resolver


class _CreateOpportunityConn:
    def __init__(self, row):
        self.row = row
        self.insert_args = None

    async def fetchrow(self, query, *args):
        if "INSERT INTO internal_opportunities" in query:
            self.insert_args = args
            return self.row
        raise AssertionError(f"Unexpected fetchrow query: {query}")


class _PortalSaveConn:
    def __init__(self, profile_row, opportunity_row):
        self._profile_row = profile_row
        self._opportunity_row = opportunity_row

    async def fetchrow(self, query, *args):
        if "FROM employee_career_profiles" in query:
            return self._profile_row
        if "FROM internal_opportunities" in query:
            return self._opportunity_row
        if "SELECT match_score, reasons" in query:
            return {
                "match_score": 87.5,
                "reasons": {"matched_skills": ["Python"], "missing_skills": []},
                "updated_at": datetime(2026, 2, 21, 13, 0, tzinfo=timezone.utc),
            }
        if "INSERT INTO internal_opportunity_matches" in query and "RETURNING status" in query:
            return {"status": "saved"}
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query, *args):
        raise AssertionError(f"Unexpected execute query: {query}")


class _PortalApplyConn:
    def __init__(self, profile_row, opportunity_row, application_id):
        self._profile_row = profile_row
        self._opportunity_row = opportunity_row
        self._application_id = application_id
        self.execute_queries: list[str] = []

    async def fetchrow(self, query, *args):
        if "FROM employee_career_profiles" in query:
            return self._profile_row
        if "FROM internal_opportunities" in query:
            return self._opportunity_row
        if "SELECT match_score, reasons" in query:
            return None
        if "INSERT INTO internal_opportunity_applications" in query:
            return {
                "id": self._application_id,
                "status": "new",
                "submitted_at": datetime(2026, 2, 21, 12, 30, tzinfo=timezone.utc),
                "manager_notified_at": None,
            }
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query, *args):
        self.execute_queries.append(query)
        return "INSERT 0 1"


def test_create_internal_opportunity_returns_created_payload(monkeypatch):
    asyncio.run(_run_create_internal_opportunity_test(monkeypatch))


async def _run_create_internal_opportunity_test(monkeypatch):
    app = FastAPI()
    app.include_router(internal_mobility_routes.router, prefix="/api/internal-mobility")

    user_id = uuid4()
    org_id = uuid4()
    opportunity_id = uuid4()
    now = datetime.now(timezone.utc)

    app.dependency_overrides[internal_mobility_routes.require_admin_or_client] = lambda: CurrentUser(
        id=user_id,
        email="client@example.com",
        role="client",
    )
    monkeypatch.setattr(
        internal_mobility_routes,
        "resolve_accessible_company_scope",
        _scope_resolver_factory(org_id),
    )

    conn = _CreateOpportunityConn(
        {
            "id": opportunity_id,
            "org_id": org_id,
            "type": "project",
            "position_id": None,
            "title": "Data Platform Rotation",
            "department": "Data",
            "description": "Help modernize pipelines",
            "required_skills": ["Python", "SQL"],
            "preferred_skills": ["Airflow"],
            "duration_weeks": 10,
            "status": "active",
            "created_by": user_id,
            "created_at": now,
            "updated_at": now,
        }
    )
    monkeypatch.setattr(internal_mobility_routes, "get_connection", _connection_factory(conn))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/internal-mobility/opportunities",
            json={
                "type": "project",
                "title": "  Data Platform Rotation  ",
                "department": "Data",
                "description": "Help modernize pipelines",
                "required_skills": ["Python", "python", "SQL"],
                "preferred_skills": ["Airflow"],
                "duration_weeks": 10,
                "status": "active",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(opportunity_id)
    assert payload["title"] == "Data Platform Rotation"
    assert payload["status"] == "active"
    assert conn.insert_args is not None
    assert conn.insert_args[3] == "Data Platform Rotation"


def test_update_internal_opportunity_rejects_null_title(monkeypatch):
    asyncio.run(_run_update_opportunity_null_title_test(monkeypatch))


async def _run_update_opportunity_null_title_test(monkeypatch):
    app = FastAPI()
    app.include_router(internal_mobility_routes.router, prefix="/api/internal-mobility")

    app.dependency_overrides[internal_mobility_routes.require_admin_or_client] = lambda: CurrentUser(
        id=uuid4(),
        email="client@example.com",
        role="client",
    )
    org_id = uuid4()
    monkeypatch.setattr(
        internal_mobility_routes,
        "resolve_accessible_company_scope",
        _scope_resolver_factory(org_id),
    )

    class _NoDbConn:
        async def fetchrow(self, query, *args):
            raise AssertionError("Database should not be called for invalid payload")

    monkeypatch.setattr(internal_mobility_routes, "get_connection", _connection_factory(_NoDbConn()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.patch(
            f"/api/internal-mobility/opportunities/{uuid4()}",
            json={"title": None},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "title cannot be null"


def test_update_mobility_profile_requires_fields():
    asyncio.run(_run_update_mobility_profile_requires_fields_test())


async def _run_update_mobility_profile_requires_fields_test():
    app = FastAPI()
    app.include_router(employee_portal_routes.router, prefix="/api/v1/portal")

    app.dependency_overrides[employee_portal_routes.require_employee_record] = lambda: {
        "id": uuid4(),
        "org_id": uuid4(),
        "start_date": date(2024, 1, 15),
    }
    mobility_feature_dep = employee_portal_routes._mobility_dep[0].dependency
    app.dependency_overrides[mobility_feature_dep] = lambda: CurrentUser(
        id=uuid4(),
        email="employee@example.com",
        role="employee",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.put(
            "/api/v1/portal/me/mobility/profile",
            json={},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "No fields to update"


def test_save_mobility_opportunity_returns_saved_status(monkeypatch):
    asyncio.run(_run_save_mobility_opportunity_test(monkeypatch))


async def _run_save_mobility_opportunity_test(monkeypatch):
    app = FastAPI()
    app.include_router(employee_portal_routes.router, prefix="/api/v1/portal")

    employee_id = uuid4()
    org_id = uuid4()
    opportunity_id = uuid4()

    app.dependency_overrides[employee_portal_routes.require_employee_record] = lambda: {
        "id": employee_id,
        "org_id": org_id,
        "start_date": date(2022, 6, 1),
    }
    mobility_feature_dep = employee_portal_routes._mobility_dep[0].dependency
    app.dependency_overrides[mobility_feature_dep] = lambda: CurrentUser(
        id=uuid4(),
        email="employee@example.com",
        role="employee",
    )

    profile_row = {
        "id": uuid4(),
        "employee_id": employee_id,
        "org_id": org_id,
        "target_roles": ["Data Scientist"],
        "target_departments": ["Data"],
        "skills": ["Python", "SQL"],
        "interests": ["analytics"],
        "mobility_opt_in": True,
        "visibility": "private",
        "created_at": datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 2, 21, 10, 0, tzinfo=timezone.utc),
    }
    opportunity_row = {
        "id": opportunity_id,
        "org_id": org_id,
        "type": "role",
        "title": "Senior Data Scientist",
        "department": "Data",
        "description": "Build forecasting models",
        "required_skills": ["Python", "SQL"],
        "preferred_skills": ["Looker"],
        "status": "active",
        "updated_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc),
    }
    conn = _PortalSaveConn(profile_row=profile_row, opportunity_row=opportunity_row)
    monkeypatch.setattr(employee_portal_routes, "get_connection", _connection_factory(conn))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            f"/api/v1/portal/me/mobility/opportunities/{opportunity_id}/save",
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["opportunity_id"] == str(opportunity_id)
    assert payload["status"] == "saved"


def test_apply_to_mobility_opportunity_creates_application_and_updates_match(monkeypatch):
    asyncio.run(_run_apply_to_mobility_opportunity_test(monkeypatch))


async def _run_apply_to_mobility_opportunity_test(monkeypatch):
    app = FastAPI()
    app.include_router(employee_portal_routes.router, prefix="/api/v1/portal")

    employee_id = uuid4()
    org_id = uuid4()
    opportunity_id = uuid4()
    application_id = uuid4()

    app.dependency_overrides[employee_portal_routes.require_employee_record] = lambda: {
        "id": employee_id,
        "org_id": org_id,
        "start_date": date(2020, 1, 10),
    }
    mobility_feature_dep = employee_portal_routes._mobility_dep[0].dependency
    app.dependency_overrides[mobility_feature_dep] = lambda: CurrentUser(
        id=uuid4(),
        email="employee@example.com",
        role="employee",
    )

    profile_row = {
        "id": uuid4(),
        "employee_id": employee_id,
        "org_id": org_id,
        "target_roles": ["Engineering Manager"],
        "target_departments": ["Platform"],
        "skills": ["python", "coaching", "roadmapping"],
        "interests": ["leadership", "platform"],
        "mobility_opt_in": True,
        "visibility": "private",
        "created_at": datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 2, 21, 10, 0, tzinfo=timezone.utc),
    }
    opportunity_row = {
        "id": opportunity_id,
        "org_id": org_id,
        "type": "project",
        "title": "Platform Enablement Lead",
        "department": "Platform",
        "description": "Lead migration initiative and mentor engineers",
        "required_skills": ["Python", "Leadership"],
        "preferred_skills": ["Roadmapping"],
        "status": "active",
        "updated_at": datetime(2026, 2, 21, 11, 0, tzinfo=timezone.utc),
    }
    conn = _PortalApplyConn(
        profile_row=profile_row,
        opportunity_row=opportunity_row,
        application_id=application_id,
    )
    monkeypatch.setattr(employee_portal_routes, "get_connection", _connection_factory(conn))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            f"/api/v1/portal/me/mobility/opportunities/{opportunity_id}/apply",
            json={"employee_notes": "Interested in a cross-functional leadership stretch assignment."},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["application_id"] == str(application_id)
    assert payload["status"] == "new"
    assert payload["manager_notified"] is False
    assert len(conn.execute_queries) == 2
    assert any("status = 'applied'" in query for query in conn.execute_queries)


def test_internal_mobility_admin_requires_company_scope(monkeypatch):
    asyncio.run(_run_internal_mobility_admin_requires_company_scope_test(monkeypatch))


async def _run_internal_mobility_admin_requires_company_scope_test(monkeypatch):
    app = FastAPI()
    app.include_router(internal_mobility_routes.router, prefix="/api/internal-mobility")

    app.dependency_overrides[internal_mobility_routes.require_admin_or_client] = lambda: CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
    )

    class _NoDbConn:
        async def fetch(self, query, *args):
            raise AssertionError("Database should not be called when company scope is missing")

    monkeypatch.setattr(internal_mobility_routes, "get_connection", _connection_factory(_NoDbConn()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/internal-mobility/opportunities")

    assert response.status_code == 400
    assert response.json()["detail"] == "company_id query parameter is required for admin users"


def test_get_mobility_feed_rejects_non_active_status():
    asyncio.run(_run_get_mobility_feed_rejects_non_active_status_test())


async def _run_get_mobility_feed_rejects_non_active_status_test():
    app = FastAPI()
    app.include_router(employee_portal_routes.router, prefix="/api/v1/portal")

    app.dependency_overrides[employee_portal_routes.require_employee_record] = lambda: {
        "id": uuid4(),
        "org_id": uuid4(),
        "start_date": date(2024, 1, 15),
    }
    mobility_feature_dep = employee_portal_routes._mobility_dep[0].dependency
    app.dependency_overrides[mobility_feature_dep] = lambda: CurrentUser(
        id=uuid4(),
        email="employee@example.com",
        role="employee",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/portal/me/mobility/feed?status_filter=draft")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only active opportunities are available in the employee mobility feed"


def test_get_mobility_feed_returns_empty_when_opted_out(monkeypatch):
    asyncio.run(_run_get_mobility_feed_returns_empty_when_opted_out_test(monkeypatch))


async def _run_get_mobility_feed_returns_empty_when_opted_out_test(monkeypatch):
    app = FastAPI()
    app.include_router(employee_portal_routes.router, prefix="/api/v1/portal")

    employee_id = uuid4()
    org_id = uuid4()

    app.dependency_overrides[employee_portal_routes.require_employee_record] = lambda: {
        "id": employee_id,
        "org_id": org_id,
        "start_date": date(2023, 2, 2),
    }
    mobility_feature_dep = employee_portal_routes._mobility_dep[0].dependency
    app.dependency_overrides[mobility_feature_dep] = lambda: CurrentUser(
        id=uuid4(),
        email="employee@example.com",
        role="employee",
    )

    profile_row = {
        "id": uuid4(),
        "employee_id": employee_id,
        "org_id": org_id,
        "target_roles": ["Product Manager"],
        "target_departments": ["Product"],
        "skills": ["SQL"],
        "interests": ["growth"],
        "mobility_opt_in": False,
        "visibility": "private",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    class _PortalOptOutConn:
        async def fetchrow(self, query, *args):
            if "FROM employee_career_profiles" in query:
                return profile_row
            raise AssertionError(f"Unexpected fetchrow query: {query}")

        async def fetch(self, query, *args):
            raise AssertionError("Opportunity query should not run when mobility_opt_in is false")

    monkeypatch.setattr(employee_portal_routes, "get_connection", _connection_factory(_PortalOptOutConn()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/portal/me/mobility/feed?status_filter=active")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0


def test_apply_to_mobility_opportunity_enforces_note_max_length(monkeypatch):
    asyncio.run(_run_apply_to_mobility_opportunity_enforces_note_max_length_test(monkeypatch))


async def _run_apply_to_mobility_opportunity_enforces_note_max_length_test(monkeypatch):
    app = FastAPI()
    app.include_router(employee_portal_routes.router, prefix="/api/v1/portal")

    app.dependency_overrides[employee_portal_routes.require_employee_record] = lambda: {
        "id": uuid4(),
        "org_id": uuid4(),
        "start_date": date(2021, 1, 1),
    }
    mobility_feature_dep = employee_portal_routes._mobility_dep[0].dependency
    app.dependency_overrides[mobility_feature_dep] = lambda: CurrentUser(
        id=uuid4(),
        email="employee@example.com",
        role="employee",
    )

    class _NoDbConn:
        async def fetchrow(self, query, *args):
            raise AssertionError("Database should not be called for invalid payload")

    monkeypatch.setattr(employee_portal_routes, "get_connection", _connection_factory(_NoDbConn()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            f"/api/v1/portal/me/mobility/opportunities/{uuid4()}/apply",
            json={"employee_notes": "x" * 501},
        )

    assert response.status_code == 422
    assert "at most 500 characters" in response.text
