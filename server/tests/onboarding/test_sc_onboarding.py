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
from app.matcha.services.employees.roster_csv import RosterCsvError


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


def test_router_gate_matches_the_features_the_wizard_writes():
    # The mount-time require_all_features gate and the product-builder
    # validation must name the same flags, or a product can be composed that
    # the wizard is then refused access to (or vice versa).
    assert set(service.SC_REQUIRED_FEATURES) == {
        "employees", "employee_schedule", "credential_templates",
    }


def test_csv_parsing_is_server_side_and_shares_the_roster_rules():
    # One implementation of these rules, in Python, next to bulk upload's — the
    # wizard uploads the file instead of parsing it in the browser.
    locations = service.parse_locations_csv(
        'name,address,city,state,zipcode\r\nHQ,"1 Main, Suite 2",Austin,California,78701'
    )
    assert locations[0].address == "1 Main, Suite 2"
    assert locations[0].state == "CA"  # full state names normalize, as on /employees

    employees = service.parse_employees_csv(
        "email,first_name,last_name,work_state,job_title,department\n"
        "cook@example.com,Casey,Cook,texas,Cook,Kitchen"
    )
    assert employees[0].work_state == "TX"


def test_csv_errors_name_the_real_source_line():
    with pytest.raises(RosterCsvError, match="Row 4 must contain all 5 values"):
        service.parse_locations_csv(
            "name,address,city,state,zipcode\n\n\nHQ,1 Main,,TX,78701"
        )
    with pytest.raises(RosterCsvError, match="Row 3 duplicates an earlier employee email"):
        service.parse_employees_csv(
            "email,first_name,last_name,work_state,job_title,department\n"
            "a@example.com,A,One,TX,Cook,Kitchen\n"
            "A@example.com,A,Two,TX,Cook,Kitchen"
        )
    with pytest.raises(RosterCsvError, match="Row 3 duplicates an earlier location row"):
        service.parse_locations_csv(
            "name,address,city,state,zipcode\n"
            "HQ,1 Main,Austin,TX,78701\n"
            " hq ,1 MAIN,austin,tx,78701"
        )
    with pytest.raises(RosterCsvError, match="Row 2 email is invalid"):
        service.parse_employees_csv(
            "email,first_name,last_name,work_state,job_title,department\n"
            "not-email,A,One,TX,Cook,Kitchen"
        )
    with pytest.raises(RosterCsvError, match="Row 2 zipcode must use"):
        service.parse_locations_csv(
            "name,address,city,state,zipcode\nHQ,1 Main,Austin,TX,7870"
        )


def test_status_publishes_the_columns_the_parser_expects():
    assert service.LOCATION_COLUMNS == ("name", "address", "city", "state", "zipcode")
    assert service.EMPLOYEE_COLUMNS == (
        "email", "first_name", "last_name", "work_state", "job_title", "department",
    )


def submission(*, locations=(), employees=()) -> ScOnboardingComplete:
    return ScOnboardingComplete(
        company=ScCompanySetup(company_size="11-50", naics_code="722511"),
        locations=list(locations),
        employees=list(employees),
        jobs=[ScJobSetup(
            name="Cook",
            credential_grace_days=7,
            certificates=[ScCertificateSetup(name="Food Handler Card")],
        )],
    )


def test_strings_are_trimmed_before_length_validation():
    location = ScLocationImport(
        name="  North  ", address="1 Main", city="Austin", state="TX", zipcode="78701",
    )
    assert location.name == "North"
    with pytest.raises(ValidationError):
        ScJobSetup(name="   ", certificates=[ScCertificateSetup(name="Card")])


def test_company_setup_does_not_accept_an_industry_override():
    # Signup already stores the controlled INDUSTRY_OPTIONS value; re-asking
    # here as free text would break industry_tag resolution.
    company = ScCompanySetup.model_validate(
        {"company_size": "1-10", "naics_code": "722", "industry": "Dental practice"}
    )
    assert not hasattr(company, "industry")


def test_company_fields_and_schedule_blocking_are_validated():
    with pytest.raises(ValidationError):
        ScCompanySetup(company_size="11-50", naics_code="72-2")
    with pytest.raises(ValidationError, match="schedule-blocking"):
        ScCertificateSetup(name="Card", is_required=False, schedule_blocking=True)


def test_a_job_must_carry_at_least_one_certificate():
    # The wizard enforces the same rule client-side; the contracts must agree.
    with pytest.raises(ValidationError):
        ScJobSetup(name="Cook", certificates=[])


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
        if "INSERT INTO employees" in query:
            assert self.in_transaction
            return [{"id": self.employee_id, "email": email} for email in args[1]]
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
        if "INSERT INTO schedule_jobs" in query:
            return self.job_id
        if "UPDATE companies SET sc_onboarding_completed_at" in query:
            return self.now
        raise AssertionError(query)

    async def execute(self, query, *args):
        assert self.in_transaction
        self.calls.append(("execute", query, args))
        return "OK"

    def queries(self) -> str:
        return "\n".join(query for _, query, _ in self.calls)


def _allow_sc_product(monkeypatch):
    async def product(*args, **kwargs):
        return SimpleNamespace(onboarding_kind="sc")

    monkeypatch.setattr(service, "get_product_by_signup_source", product)
    monkeypatch.setattr(service, "is_tenant_activated", lambda *args, **kwargs: True)


def _capture_location_sync(monkeypatch) -> list[dict]:
    synced: list[dict] = []

    async def sync(conn, company_id, employee_by_state):
        synced.append(dict(employee_by_state))

    monkeypatch.setattr(service, "_sync_compliance_locations", sync)
    return synced


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
async def test_status_carries_the_csv_columns(monkeypatch):
    _allow_sc_product(monkeypatch)
    status = await service.get_sc_onboarding_status(_Connection(), company_id=uuid4())
    assert status["csv_columns"] == {
        "locations": list(service.LOCATION_COLUMNS),
        "employees": list(service.EMPLOYEE_COLUMNS),
    }


@pytest.mark.asyncio
async def test_completion_is_company_scoped_and_materializes_after_rules(monkeypatch):
    _allow_sc_product(monkeypatch)
    synced = _capture_location_sync(monkeypatch)
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
    # Imported employees must get the same derived jurisdiction coverage the
    # employees CSV endpoint produces, and the sync runs after the commit.
    assert synced == [{"TX": conn.employee_id}]


@pytest.mark.asyncio
async def test_roster_and_locations_are_written_in_set_based_statements(monkeypatch):
    _allow_sc_product(monkeypatch)
    _capture_location_sync(monkeypatch)

    async def replace(conn_arg, **kwargs):
        return []

    monkeypatch.setattr(service, "replace_job_credential_requirements", replace)
    conn = _Connection()
    employees = [
        ScEmployeeImport(
            email=f"cook{index}@example.com", first_name="Casey", last_name=str(index),
            work_state="TX", job_title="Cook", department="Kitchen",
        )
        for index in range(25)
    ]
    locations = [
        ScLocationImport(
            name=f"Store {index}", address=f"{index} Main", city="Austin",
            state="TX", zipcode="78701",
        )
        for index in range(25)
    ]

    await service.complete_sc_onboarding(
        conn, company_id=uuid4(), actor_user_id=uuid4(),
        body=submission(locations=locations, employees=employees),
    )

    inserts = [query for _, query, _ in conn.calls if "INSERT INTO employees" in query]
    location_inserts = [query for _, query, _ in conn.calls if "INSERT INTO business_locations" in query]
    assert len(inserts) == 1
    assert len(location_inserts) == 1


@pytest.mark.asyncio
async def test_tenant_certificate_name_never_lands_in_the_shared_catalog(monkeypatch):
    _allow_sc_product(monkeypatch)
    _capture_location_sync(monkeypatch)

    async def replace(conn_arg, **kwargs):
        return []

    monkeypatch.setattr(service, "replace_job_credential_requirements", replace)
    conn = _Connection()

    await service.complete_sc_onboarding(
        conn, company_id=uuid4(), actor_user_id=uuid4(), body=submission(),
    )

    base_insert = next(
        (query, args) for _, query, args in conn.calls if "INSERT INTO credential_types" in query
    )
    # credcustom01: the base row is an opaque FK target. Only the tenant-scoped
    # company_credential_types row may carry the customer's wording.
    assert "'Tenant credential'" in base_insert[0]
    assert "Food Handler Card" not in str(base_insert[1])
    scoped_insert = next(
        (query, args) for _, query, args in conn.calls
        if "INSERT INTO company_credential_types" in query
    )
    assert "Food Handler Card" in str(scoped_insert[1])
    # A configured allowlist must not hide the type the wizard just created.
    assert any(
        "company_credential_type_filter_items" in query for _, query, _ in conn.calls
    )


@pytest.mark.asyncio
async def test_signup_industry_is_not_overwritten(monkeypatch):
    _allow_sc_product(monkeypatch)
    _capture_location_sync(monkeypatch)

    async def replace(conn_arg, **kwargs):
        return []

    monkeypatch.setattr(service, "replace_job_credential_requirements", replace)
    conn = _Connection()

    await service.complete_sc_onboarding(
        conn, company_id=uuid4(), actor_user_id=uuid4(), body=submission(),
    )

    company_update = next(
        query for _, query, _ in conn.calls if query.startswith("UPDATE companies SET size")
    )
    assert "industry" not in company_update


@pytest.mark.asyncio
async def test_unavailable_credential_type_is_a_422_not_a_500(monkeypatch):
    _allow_sc_product(monkeypatch)
    _capture_location_sync(monkeypatch)
    conn = _Connection()

    async def refuse(*args, **kwargs):
        raise ValueError("One or more credential types are not available to this company")

    monkeypatch.setattr(service, "replace_job_credential_requirements", refuse)

    with pytest.raises(service.ScOnboardingError, match="not available to this company"):
        await service.complete_sc_onboarding(
            conn, company_id=uuid4(), actor_user_id=uuid4(), body=submission(),
        )
    assert conn.rolled_back is True


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
