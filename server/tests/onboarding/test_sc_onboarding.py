"""Matcha S&C onboarding contracts and atomic completion flow (no real DB)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
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
        name="  North  ", address="1 Main", city="Austin", state="TX", timezone="America/Chicago", zipcode="78701",
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


def test_a_setup_may_carry_no_certificate_at_all():
    # A roster title with no credential requirement (e.g. a shift supervisor)
    # must still be configurable as a job, or its employees can't import.
    assert ScJobSetup(name="Shift Supervisor").certificates == []

    # And a whole setup may have none: a cafe with nothing to certify used to
    # be refused until it invented a mandatory certificate.
    service.validate_sc_submission(submission().model_copy(update={"jobs": [
        ScJobSetup(name="Shift Supervisor"),
        ScJobSetup(name="Barista", certificates=[
            ScCertificateSetup(name="Food Handler Card", is_required=False, schedule_blocking=False),
        ]),
    ]}))
    service.validate_sc_submission(submission().model_copy(update={"jobs": [
        ScJobSetup(name="Barista"),
    ]}))

    duplicated = submission().model_copy(update={"jobs": [
        ScJobSetup(name="Barista", certificates=[
            ScCertificateSetup(name="Food Handler Card"),
            ScCertificateSetup(name="food handler card"),
        ]),
    ]})
    with pytest.raises(service.ScOnboardingError, match="duplicate certificate"):
        service.validate_sc_submission(duplicated)


def test_optional_imports_can_be_skipped():
    service.validate_sc_submission(submission())


def test_duplicate_location_rejects_exact_rows_but_allows_two_sites_in_one_city():
    locations = [
        ScLocationImport(name="North", address="1 Main", city="Austin", state="TX", timezone="America/Chicago", zipcode="78701"),
        ScLocationImport(name=" north ", address="1 MAIN", city=" austin ", state="tx", timezone="America/Chicago", zipcode="78701"),
    ]
    with pytest.raises(service.ScOnboardingError, match="duplicate location row"):
        service.validate_sc_submission(submission(locations=locations))

    service.validate_sc_submission(submission(locations=[
        locations[0],
        ScLocationImport(name="South", address="99 Other", city="Austin", state="TX", timezone="America/Chicago", zipcode="78702"),
    ]))


def test_employee_email_and_job_title_validation_is_actionable():
    employees = [
        ScEmployeeImport(email="a@example.com", first_name="A", last_name="One", work_state="TX", job_title="Cook", department="Kitchen"),
        ScEmployeeImport(email="A@example.com", first_name="A", last_name="Two", work_state="TX", job_title="Server", department="Dining"),
    ]
    with pytest.raises(service.ScOnboardingError, match="duplicate email"):
        service.validate_sc_submission(submission(employees=employees))

    with pytest.raises(service.ScOnboardingError, match="Every employee job title needs a job"):
        service.validate_sc_submission(submission(employees=employees[:1]).model_copy(update={
            "employees": [employees[1]],
        }))


def _employee(email: str, job_title: str) -> ScEmployeeImport:
    return ScEmployeeImport(
        email=email, first_name="Sam", last_name="Lee",
        work_state="CA", job_title=job_title, department="Front of house",
    )


def test_unmatched_titles_are_all_named_once_with_the_fix():
    # Naming only the first unmatched title made the manager fix the roster
    # one title per attempt (Barista, then Shift Supervisor, ...).
    body = submission(employees=[
        _employee("a@example.com", "Shift Supervisor"),
        _employee("b@example.com", "barista"),
        _employee("c@example.com", "Barista"),
        _employee("d@example.com", "Cook"),
    ])
    with pytest.raises(service.ScOnboardingError) as caught:
        service.validate_sc_submission(body)
    message = str(caught.value)
    assert message.startswith(service.UNMATCHED_JOB_TITLES_MESSAGE)
    assert message.endswith("Missing: barista, Shift Supervisor")


def test_employee_title_matches_a_job_regardless_of_case_and_spacing():
    body = submission(employees=[_employee("a@example.com", "  COOK ")])
    service.validate_sc_submission(body)


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
    def __init__(self, *, completed_at=None, existing_locations=(), headcount=None, industry=None):
        self.completed_at = completed_at
        self.headcount = headcount
        self.industry = industry
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
                "industry": self.industry,
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
        if "FROM company_handbook_profiles" in query:
            return self.headcount
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
    monkeypatch.setattr(service, "_link_jurisdiction", _fake_jurisdiction)


JURISDICTION_ID = uuid4()


async def _fake_jurisdiction(conn, city, state, zipcode):
    return JURISDICTION_ID


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
        name="Downtown", address="1 Main", city="Austin", state="TX", timezone="America/Chicago", zipcode="78701",
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
    # The store the manager entered IS the TX compliance location, so no
    # second, address-less "TX" location is derived next to it. The sync still
    # runs after the commit, with nothing left to derive.
    assert synced == [{}]


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
            state="TX", timezone="America/Chicago", zipcode="78701",
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
        name="downtown", address="99 other", city="austin", state="tx", timezone="America/Chicago", zipcode="78702",
    )

    with pytest.raises(service.ScOnboardingError, match="already exists"):
        await service.complete_sc_onboarding(
            conn, company_id=uuid4(), actor_user_id=uuid4(),
            body=submission(locations=[location]),
        )

    assert conn.rolled_back is True
    assert not any(method == "execute" for method, _, _ in conn.calls)


class _RosterConnection(_Connection):
    """Hands out a distinct id per employee and per job so assignment is checkable."""

    def __init__(self):
        super().__init__()
        self.employee_ids: dict[str, object] = {}
        self.job_ids: dict[str, object] = {}

    async def fetch(self, query, *args):
        if "INSERT INTO employees" in query:
            self.calls.append(("fetch", query, args))
            assert self.in_transaction
            rows = []
            for email in args[1]:
                self.employee_ids[email] = uuid4()
                rows.append({"id": self.employee_ids[email], "email": email})
            return rows
        return await super().fetch(query, *args)

    async def fetchval(self, query, *args):
        if "INSERT INTO schedule_jobs" in query:
            self.calls.append(("fetchval", query, args))
            self.job_ids[args[1]] = uuid4()
            return self.job_ids[args[1]]
        return await super().fetchval(query, *args)


def _shift_supervisor_submission(*, jobs) -> ScOnboardingComplete:
    return submission(employees=[
        _employee("lead@example.com", "Shift Supervisor"),
        _employee("barista@example.com", "Barista"),
    ]).model_copy(update={"jobs": jobs})


_CAFE_JOBS = [
    ScJobSetup(name="Barista", certificates=[ScCertificateSetup(name="Food Handler Card")]),
    ScJobSetup(name="shift supervisor"),
]


@pytest.mark.asyncio
async def test_shift_supervisor_without_a_certificate_persists_and_is_assigned(monkeypatch):
    # The reported case: a company-defined title with no credential rule.
    _allow_sc_product(monkeypatch)
    _capture_location_sync(monkeypatch)
    replacement_calls = []

    async def replace(conn_arg, **kwargs):
        replacement_calls.append(kwargs)
        return []

    monkeypatch.setattr(service, "replace_job_credential_requirements", replace)
    conn = _RosterConnection()

    result = await service.complete_sc_onboarding(
        conn, company_id=uuid4(), actor_user_id=uuid4(),
        body=_shift_supervisor_submission(jobs=_CAFE_JOBS),
    )

    assert result["already_completed"] is False
    assert set(conn.job_ids) == {"Barista", "shift supervisor"}
    assignments = {
        args[0]: args[1]
        for _, query, args in conn.calls
        if "INSERT INTO schedule_job_employees" in query
    }
    assert assignments == {
        conn.job_ids["Barista"]: [conn.employee_ids["barista@example.com"]],
        conn.job_ids["shift supervisor"]: [conn.employee_ids["lead@example.com"]],
    }
    # Only the job that carries a certificate writes credential rules.
    assert [call["job_id"] for call in replacement_calls] == [conn.job_ids["Barista"]]
    assert conn.rolled_back is False


def _route_harness(monkeypatch, conn):
    from contextlib import asynccontextmanager

    from app.matcha.routes.onboarding import sc as sc_route

    @asynccontextmanager
    async def connection():
        yield conn

    async def company_id(current_user):
        return uuid4()

    monkeypatch.setattr(sc_route, "get_connection", connection)
    monkeypatch.setattr(sc_route, "get_client_company_id", company_id)
    return sc_route


@pytest.mark.asyncio
async def test_complete_route_accepts_the_shift_supervisor_setup(monkeypatch):
    _allow_sc_product(monkeypatch)
    _capture_location_sync(monkeypatch)

    async def replace(conn_arg, **kwargs):
        return []

    monkeypatch.setattr(service, "replace_job_credential_requirements", replace)
    conn = _RosterConnection()
    sc_route = _route_harness(monkeypatch, conn)

    response = await sc_route.complete(
        _shift_supervisor_submission(jobs=_CAFE_JOBS),
        BackgroundTasks(),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response == {"already_completed": False, "completed_at": conn.now.isoformat()}


@pytest.mark.asyncio
async def test_complete_route_names_every_missing_title_as_a_422(monkeypatch):
    _allow_sc_product(monkeypatch)
    conn = _RosterConnection()
    sc_route = _route_harness(monkeypatch, conn)

    with pytest.raises(HTTPException) as caught:
        await sc_route.complete(
            _shift_supervisor_submission(jobs=_CAFE_JOBS[:1]),
            BackgroundTasks(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert caught.value.status_code == 422
    assert caught.value.detail == service.UNMATCHED_JOB_TITLES_MESSAGE + "Shift Supervisor"
    # Rejected before the transaction opens: nothing was written.
    assert conn.calls == []


# ── Publishable stores, assigned employees ───────────────────────────────
#
# A schedule can only be published for a store that has a timezone and a
# jurisdiction, and only for employees who have a store. Setup used to write
# none of the three, so a customer who finished every step still could not
# publish — and nothing in a scheduling-first product could repair it.


def _store(name="Downtown", *, state="CA", city="Oakland", **overrides) -> ScLocationImport:
    return ScLocationImport(
        name=name, address="1 Main", city=city, state=state, zipcode="94607", **overrides,
    )


def _crew(email: str, *, location=None, work_state="CA") -> ScEmployeeImport:
    return ScEmployeeImport(
        email=email, first_name="Sam", last_name="Lee", work_state=work_state,
        job_title="Cook", department="Kitchen", location=location,
    )


def test_timezone_is_inferred_for_a_one_zone_state_and_kept_when_chosen():
    assert service.resolve_location_timezone(_store()) == ("America/Los_Angeles", "auto")
    assert service.resolve_location_timezone(
        _store(state="TX", city="El Paso", timezone="America/Denver")
    ) == ("America/Denver", "manual")


def test_a_split_zone_store_with_no_timezone_is_refused_by_name():
    # Texas runs on two clocks; guessing one would publish shifts an hour off.
    with pytest.raises(service.ScOnboardingError, match="Choose a time zone for El Paso"):
        service.validate_sc_submission(
            submission(locations=[_store("El Paso", state="TX", city="El Paso")])
        )
    with pytest.raises(service.ScOnboardingError, match="valid IANA time zone"):
        service.validate_sc_submission(
            submission(locations=[_store(timezone="Pacific")])
        )


def test_employees_land_at_the_named_store_or_the_only_one():
    two_stores = [_store("Downtown"), _store("Mission", city="San Francisco")]
    body = submission(locations=two_stores, employees=[
        _crew("a@example.com", location="  mission "),
        _crew("b@example.com"),
    ])
    # Named store matches regardless of case/spacing; with two stores and no
    # name there is no honest default, so that person stays unassigned.
    assert service.employee_store_keys(body) == ["mission", None]

    one_store = submission(locations=[_store("Downtown")], employees=[_crew("a@example.com")])
    assert service.employee_store_keys(one_store) == ["downtown"]

    no_stores = submission(employees=[_crew("a@example.com")])
    assert service.employee_store_keys(no_stores) == [None]


def test_an_unknown_or_ambiguous_store_name_is_refused_with_the_fix():
    with pytest.raises(service.ScOnboardingError, match="Not found: Uptown"):
        service.validate_sc_submission(submission(
            locations=[_store("Downtown")],
            employees=[_crew("a@example.com", location="Uptown")],
        ))
    twins = [_store("Downtown"), _store("Downtown", city="San Francisco")]
    with pytest.raises(service.ScOnboardingError, match="More than one location is named Downtown"):
        service.validate_sc_submission(submission(
            locations=twins, employees=[_crew("a@example.com", location="downtown")],
        ))
    # Twin names are only a problem once a roster row has to pick between them.
    service.validate_sc_submission(submission(locations=twins))


def test_employee_csv_takes_an_optional_location_column():
    header = "email,first_name,last_name,work_state,job_title,department"
    with_store = service.parse_employees_csv(
        header + ",location\n"
        "a@example.com,A,One,CA,Cook,Kitchen,Downtown\n"
        "b@example.com,B,Two,CA,Cook,Kitchen,\n"
        "c@example.com,C,Three,CA,Cook,Kitchen"
    )
    assert [employee.location for employee in with_store] == ["Downtown", None, None]
    # The file a customer exported before the column existed still imports.
    assert service.parse_employees_csv(
        header + "\na@example.com,A,One,CA,Cook,Kitchen"
    )[0].location is None
    with pytest.raises(RosterCsvError, match=r"Expected header: .*\(optional: location\)"):
        service.parse_employees_csv(header + ",store\na@example.com,A,One,CA,Cook,Kitchen,X")


@pytest.mark.asyncio
async def test_stores_are_written_publishable_and_employees_assigned(monkeypatch):
    _allow_sc_product(monkeypatch)
    synced = _capture_location_sync(monkeypatch)

    async def replace(conn_arg, **kwargs):
        return []

    monkeypatch.setattr(service, "replace_job_credential_requirements", replace)
    linked: list[tuple] = []

    async def link(conn, city, state, zipcode):
        linked.append((city, state, zipcode))
        return JURISDICTION_ID

    monkeypatch.setattr(service, "_link_jurisdiction", link)
    conn = _RosterConnection()
    stores = [
        _store("Downtown"),
        _store("Uptown"),  # same city: one jurisdiction lookup serves both
        _store("El Paso", state="TX", city="El Paso", timezone="America/Denver"),
    ]
    tasks = BackgroundTasks()

    await service.complete_sc_onboarding(
        conn, company_id=uuid4(), actor_user_id=uuid4(),
        body=submission(locations=stores, employees=[
            _crew("a@example.com", location="Uptown"),
            _crew("b@example.com"),
            _crew("remote@example.com", work_state="NV"),
        ]),
        background_tasks=tasks,
    )

    _, _, args = next(call for call in conn.calls if "INSERT INTO business_locations" in call[1])
    store_ids, timezones, sources, jurisdictions = args[1], args[7], args[8], args[9]
    assert timezones == ["America/Los_Angeles", "America/Los_Angeles", "America/Denver"]
    assert sources == ["auto", "auto", "manual"]
    assert jurisdictions == [JURISDICTION_ID] * 3
    assert linked == [("Oakland", "CA", "94607"), ("El Paso", "TX", "94607")]

    _, _, employee_args = next(call for call in conn.calls if "INSERT INTO employees" in call[1])
    # Named store → that store's id; no name with three stores → unassigned.
    assert employee_args[7] == [store_ids[1], None, None]

    # Only the state with no store still derives a compliance location.
    assert synced == [{"NV": conn.employee_ids["remote@example.com"]}]
    # Each real store gets the catalog's requirements projected onto it.
    assert [task.args for task in tasks.tasks] == [
        (store_id, conn.calls[0][2][0]) for store_id in store_ids
    ]
    assert all(task.func is service._project_store_compliance for task in tasks.tasks)


@pytest.mark.asyncio
async def test_store_compliance_projection_spends_no_model_calls(monkeypatch):
    import app.core.services.compliance_service as compliance_service

    seen: list[dict] = []

    async def check(location_id, company_id, **kwargs):
        seen.append(kwargs)
        return {}

    monkeypatch.setattr(compliance_service, "run_compliance_check_background", check)
    await service._project_store_compliance(uuid4(), uuid4())
    assert seen == [{
        "check_type": "proactive",
        "allow_live_research": False,
        "allow_repository_refresh": False,
    }]

    async def explode(*args, **kwargs):
        raise RuntimeError("catalog offline")

    # Best-effort: the store is already schedulable, so a failure is logged.
    monkeypatch.setattr(compliance_service, "run_compliance_check_background", explode)
    await service._project_store_compliance(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_link_jurisdiction_delegates_to_the_compliance_resolver(monkeypatch):
    import app.core.services.compliance_service as compliance_service

    async def resolver(conn, city, state, county, zipcode):
        return (city, state, county, zipcode)

    monkeypatch.setattr(compliance_service, "_get_or_create_jurisdiction", resolver)
    assert await service._link_jurisdiction(object(), "Oakland", "CA", "94607") == (
        "Oakland", "CA", None, "94607",
    )


def test_company_size_bucket_follows_the_signup_headcount():
    assert [service.company_size_for_headcount(n) for n in (None, 0, 1, 10, 11, 50, 100, 250, 500, 501)] == [
        None, None, "1-10", "1-10", "11-50", "11-50", "51-100", "101-250", "251-500", "501+",
    ]


def test_every_industry_default_is_a_naics_code_setup_accepts():
    from app.matcha.services.ir.naics_titles import naics_industry_description

    for industry, code in service.INDUSTRY_NAICS_DEFAULTS.items():
        assert naics_industry_description(code), industry
        ScCompanySetup(company_size="1-10", naics_code=code)


@pytest.mark.asyncio
async def test_status_prefills_what_signup_already_asked(monkeypatch):
    _allow_sc_product(monkeypatch)
    status = await service.get_sc_onboarding_status(
        _Connection(headcount=24, industry="Hospitality"), company_id=uuid4(),
    )
    assert status["suggested_company_size"] == "11-50"
    assert status["suggested_naics_code"] == "72"
    assert status["csv_optional_columns"] == {"locations": [], "employees": ["location"]}

    # "other" (or a missing profile) has no honest default: the wizard asks.
    blank = await service.get_sc_onboarding_status(
        _Connection(industry="other"), company_id=uuid4(),
    )
    assert blank["suggested_company_size"] is None
    assert blank["suggested_naics_code"] is None


@pytest.mark.asyncio
async def test_status_tolerates_a_missing_headcount_table(monkeypatch):
    import asyncpg

    _allow_sc_product(monkeypatch)

    class _NoProfiles(_Connection):
        async def fetchval(self, query, *args):
            if "FROM company_handbook_profiles" in query:
                raise asyncpg.UndefinedTableError("relation does not exist")
            return await super().fetchval(query, *args)

    status = await service.get_sc_onboarding_status(_NoProfiles(), company_id=uuid4())
    assert status["suggested_company_size"] is None
