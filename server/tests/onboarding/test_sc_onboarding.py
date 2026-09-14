"""Matcha S&C onboarding contracts and atomic completion flow (no real DB)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.routes.admin.products import ProductUpsert, _validated
from app.matcha.models.sc_onboarding import (
    ScCertificateSetup,
    ScCompanySetup,
    ScEmployeeImport,
    ScJobSetup,
    ScLocationImport,
    ScOnboardingComplete,
)
from app.matcha.services import sc_onboarding as service


def sc_product(**overrides) -> ProductUpsert:
    values = {
        "slug": "safety-co",
        "name": "Safety & Compliance",
        "features": {
            "employees": True,
            "employee_schedule": True,
            "credential_templates": True,
        },
        "gate_feature": None,
        "pricing_model": "free",
        "onboarding_kind": "sc",
    }
    values.update(overrides)
    return ProductUpsert(**values)


def test_sc_product_requires_all_wizard_features():
    body = sc_product(features={"employees": True})
    with pytest.raises(HTTPException, match="requires"):
        _validated(body, frozenset())


def test_sc_product_persists_explicit_onboarding_kind():
    assert _validated(sc_product(), frozenset())["onboarding_kind"] == "sc"


def submission(*, locations=(), employees=()) -> ScOnboardingComplete:
    return ScOnboardingComplete(
        company=ScCompanySetup(company_size="11-50", naics_code="722511", industry="Restaurants"),
        locations=list(locations),
        employees=list(employees),
        jobs=[ScJobSetup(
            name="Cook",
            credential_grace_days=7,
            certificates=[ScCertificateSetup(name="Food Handler Card")],
        )],
    )


def test_strings_are_trimmed_before_length_validation():
    company = ScCompanySetup(company_size="1-10", naics_code="722", industry="  Food service  ")
    assert company.industry == "Food service"
    with pytest.raises(ValidationError):
        ScJobSetup(name="   ")


def test_company_fields_and_schedule_blocking_are_validated():
    with pytest.raises(ValidationError):
        ScCompanySetup(company_size="11-50", naics_code="72-2", industry="Restaurants")
    with pytest.raises(ValidationError, match="schedule-blocking"):
        ScCertificateSetup(name="Card", is_required=False, schedule_blocking=True)


def test_optional_imports_can_be_skipped():
    service.validate_sc_submission(submission())


def test_duplicate_location_rejects_exact_rows_but_allows_two_sites_in_one_city():
    locations = [
        ScLocationImport(name="North", address="1 Main", city="Austin", state="TX", zipcode="78701"),
        ScLocationImport(name=" north ", address="1 MAIN", city=" austin ", state="tx", zipcode="78701"),
    ]
    with pytest.raises(service.ScOnboardingError, match="duplicate location row"):
        service.validate_sc_submission(submission(locations=locations))

    service.validate_sc_submission(submission(locations=[
        locations[0],
        ScLocationImport(name="South", address="99 Other", city="Austin", state="TX", zipcode="78702"),
    ]))


def test_employee_email_and_job_title_validation_is_actionable():
    employees = [
        ScEmployeeImport(email="a@example.com", first_name="A", last_name="One", work_state="TX", job_title="Cook", department="Kitchen"),
        ScEmployeeImport(email="A@example.com", first_name="A", last_name="Two", work_state="TX", job_title="Server", department="Dining"),
    ]
    with pytest.raises(service.ScOnboardingError, match="duplicate email"):
        service.validate_sc_submission(submission(employees=employees))

    with pytest.raises(service.ScOnboardingError, match="must match a configured job"):
        service.validate_sc_submission(submission(employees=employees[:1]).model_copy(update={
            "employees": [employees[1]],
        }))


class _Transaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        assert not self.conn.in_transaction
        self.conn.in_transaction = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.in_transaction = False
        self.conn.rolled_back = exc_type is not None


class _Connection:
    def __init__(self, *, completed_at=None, existing_locations=()):
        self.completed_at = completed_at
        self.existing_locations = list(existing_locations)
        self.in_transaction = False
        self.rolled_back = False
        self.calls: list[tuple[str, str, tuple]] = []
        self.employee_id = uuid4()
        self.job_id = uuid4()
        self.now = datetime(2026, 9, 14, tzinfo=timezone.utc)

    def transaction(self):
        return _Transaction(self)

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FROM companies WHERE id" in query:
            return {
                "id": args[0], "name": "Example Co", "status": "approved",
                "signup_source": "product:safety-co", "enabled_features": {"employees": True},
                "sc_onboarding_completed_at": self.completed_at,
            }
        raise AssertionError(query)

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "SELECT email FROM employees" in query:
            return []
        if "FROM business_locations" in query:
            return self.existing_locations
        if "SELECT name FROM schedule_jobs" in query:
            return []
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "SELECT id FROM scoped_credential_types" in query:
            return None
        if "INSERT INTO employees" in query:
            return self.employee_id
        if "INSERT INTO schedule_jobs" in query:
            return self.job_id
        if "UPDATE companies SET sc_onboarding_completed_at" in query:
            return self.now
        raise AssertionError(query)

    async def execute(self, query, *args):
        assert self.in_transaction
        self.calls.append(("execute", query, args))
        return "OK"


def _allow_sc_product(monkeypatch):
    async def product(*args, **kwargs):
        return SimpleNamespace(onboarding_kind="sc")

    monkeypatch.setattr(service, "get_product_by_signup_source", product)
    monkeypatch.setattr(service, "is_tenant_activated", lambda *args, **kwargs: True)


@pytest.mark.asyncio
async def test_status_rejects_non_sc_and_inactive_companies(monkeypatch):
    async def standard_product(*args, **kwargs):
        return SimpleNamespace(onboarding_kind=None)

    conn = _Connection()
    monkeypatch.setattr(service, "get_product_by_signup_source", standard_product)
    with pytest.raises(service.ScOnboardingAccessError, match="not enabled"):
        await service.get_sc_onboarding_status(conn, company_id=uuid4())

    async def sc_product_result(*args, **kwargs):
        return SimpleNamespace(onboarding_kind="sc")

    monkeypatch.setattr(service, "get_product_by_signup_source", sc_product_result)
    monkeypatch.setattr(service, "is_tenant_activated", lambda *args, **kwargs: False)
    with pytest.raises(service.ScOnboardingAccessError, match="Activate this product"):
        await service.get_sc_onboarding_status(conn, company_id=uuid4())


@pytest.mark.asyncio
async def test_completion_is_company_scoped_and_materializes_after_rules(monkeypatch):
    _allow_sc_product(monkeypatch)
    conn = _Connection()
    employee = ScEmployeeImport(
        email="cook@example.com", first_name="Casey", last_name="Cook",
        work_state="TX", job_title="Cook", department="Kitchen",
    )
    location = ScLocationImport(
        name="Downtown", address="1 Main", city="Austin", state="TX", zipcode="78701",
    )
    replacement_calls = []

    async def replace(conn_arg, **kwargs):
        assert conn_arg.in_transaction
        assert any("INSERT INTO schedule_jobs" in query for _, query, _ in conn_arg.calls)
        replacement_calls.append(kwargs)
        return []

    monkeypatch.setattr(service, "replace_job_credential_requirements", replace)

    result = await service.complete_sc_onboarding(
        conn, company_id=uuid4(), actor_user_id=uuid4(),
        body=submission(locations=[location], employees=[employee]),
    )

    assert result == {"already_completed": False, "completed_at": conn.now.isoformat()}
    assert replacement_calls[0]["job_id"] == conn.job_id
    assert replacement_calls[0]["requirements"][0]["is_required"] is True
    assert any("INSERT INTO schedule_job_employees" in query for _, query, _ in conn.calls)
    assert any("UPDATE companies SET sc_onboarding_completed_at" in query for _, query, _ in conn.calls)
    assert conn.rolled_back is False


@pytest.mark.asyncio
async def test_duplicate_submission_returns_prior_completion_without_writes(monkeypatch):
    _allow_sc_product(monkeypatch)
    completed_at = datetime(2026, 9, 13, tzinfo=timezone.utc)
    conn = _Connection(completed_at=completed_at)

    result = await service.complete_sc_onboarding(
        conn, company_id=uuid4(), actor_user_id=uuid4(), body=submission(),
    )

    assert result == {"already_completed": True, "completed_at": completed_at.isoformat()}
    assert not any(method == "execute" for method, _, _ in conn.calls)


@pytest.mark.asyncio
async def test_failure_before_completion_rolls_back_transaction(monkeypatch):
    _allow_sc_product(monkeypatch)
    conn = _Connection()

    async def fail(*args, **kwargs):
        raise ValueError("credential failure")

    monkeypatch.setattr(service, "replace_job_credential_requirements", fail)

    with pytest.raises(ValueError, match="credential failure"):
        await service.complete_sc_onboarding(
            conn, company_id=uuid4(), actor_user_id=uuid4(), body=submission(),
        )

    assert conn.rolled_back is True
    assert not any("sc_onboarding_completed_at = NOW" in query for _, query, _ in conn.calls)


@pytest.mark.asyncio
async def test_existing_company_location_is_rejected_before_mutation(monkeypatch):
    _allow_sc_product(monkeypatch)
    conn = _Connection(existing_locations=[{
        "name": "Downtown", "address": "99 Other", "city": "Austin",
        "state": "TX", "zipcode": "78702",
    }])
    location = ScLocationImport(
        name="downtown", address="99 other", city="austin", state="tx", zipcode="78702",
    )

    with pytest.raises(service.ScOnboardingError, match="already exists"):
        await service.complete_sc_onboarding(
            conn, company_id=uuid4(), actor_user_id=uuid4(),
            body=submission(locations=[location]),
        )

    assert conn.rolled_back is True
    assert not any(method == "execute" for method, _, _ in conn.calls)
