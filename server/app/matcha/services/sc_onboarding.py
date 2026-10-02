"""Atomic, company-scoped persistence for Matcha S&C account setup."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID, uuid4

import asyncpg

from app.core.services.location_timezone import (
    TimezoneResolutionError,
    timezone_for_create,
)
from app.core.services.product_definitions import (
    get_product_by_signup_source,
    is_tenant_activated,
)
from app.matcha.models.sc_onboarding import (
    ScEmployeeImport,
    ScLocationImport,
    ScOnboardingComplete,
)
from app.matcha.services.employees.roster_csv import (
    ZIPCODE_PATTERN,
    RosterCsvError,
    is_valid_email,
    normalize_key,
    normalize_work_state,
    parse_table,
    require_unique,
)
from app.matcha.services.ir.naics_titles import naics_industry_description
from app.matcha.services.scheduling.job_credential_requirements import (
    replace_job_credential_requirements,
)

logger = logging.getLogger(__name__)

# The features this wizard writes into.  The router mounts the same set as a
# `require_all_features` gate; keeping the list here documents why.
SC_REQUIRED_FEATURES = ("employees", "employee_schedule", "credential_templates")

# The wizard's two import files. These are the ONLY definition — the client
# renders them from `GET /sc-onboarding/status` rather than keeping its own copy.
LOCATION_COLUMNS = ("name", "address", "city", "state", "zipcode")
EMPLOYEE_COLUMNS = ("email", "first_name", "last_name", "work_state", "job_title", "department")
# May follow the required columns, or be left out: the store a person works at,
# by the name given in the locations step.
EMPLOYEE_OPTIONAL_COLUMNS = ("location",)
CSV_MAX_ROWS = 500

# Signup's controlled industry value → the broadest NAICS code that is still
# true for it. Only a starting point the manager can overwrite; an industry
# with no honest default ("other") is left for them to fill in.
INDUSTRY_NAICS_DEFAULTS = {
    "healthcare": "62",
    "biotech": "5417",
    "dental": "6212",
    "technology": "54",
    "retail": "44",
    "hospitality": "72",
    "education": "61",
    "legal": "5411",
    "financial_services": "52",
    "construction": "23",
    "manufacturing": "31",
    "nonprofit": "813",
    "real_estate": "53",
    "transportation": "48",
}

_SIZE_BUCKETS = ((10, "1-10"), (50, "11-50"), (100, "51-100"), (250, "101-250"), (500, "251-500"))

# Shared verbatim with the wizard's own pre-submit check (ScOnboardingWizard.tsx).
UNMATCHED_JOB_TITLES_MESSAGE = (
    "Every employee job title needs a job. Add a job with the same name, or "
    "correct the title in the employee CSV and upload it again. Missing: "
)


class ScOnboardingError(ValueError):
    pass


class ScOnboardingAccessError(ScOnboardingError):
    pass


def _key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def company_size_for_headcount(headcount: int | None) -> str | None:
    """The wizard's size bucket for the headcount typed at signup."""
    if headcount is None or headcount < 1:
        return None
    for ceiling, bucket in _SIZE_BUCKETS:
        if headcount <= ceiling:
            return bucket
    return "501+"


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        normalized = _key(value)
        if normalized in seen:
            duplicates.add(value.strip())
        seen.add(normalized)
    return sorted(duplicates, key=str.casefold)


def _location_key(location) -> tuple[str, str, str, str, str]:
    # Manual locations may legitimately share a city/state (multiple stores in
    # one city), so onboarding treats an exact normalized CSV row as the
    # duplicate identity instead of collapsing distinct physical sites.
    return (
        _key(location.name),
        _key(location.address),
        _key(location.city),
        _key(location.state),
        _key(location.zipcode),
    )


def parse_locations_csv(text: str) -> list[ScLocationImport]:
    """Parse a locations file into validated rows (nothing is written).

    All-or-nothing, and server-side: the wizard holds the parsed rows until the
    manager approves the review, but the RULES that decide whether a row is
    acceptable live here with every other roster-import rule, not in a second
    implementation in the browser.
    """
    parsed = parse_table(text, LOCATION_COLUMNS, max_rows=CSV_MAX_ROWS)
    locations: list[ScLocationImport] = []
    for row, line in parsed:
        state, state_valid = normalize_work_state(row["state"])
        if not state_valid or state is None:
            raise RosterCsvError(f"Row {line} state must use a two-letter code")
        if not ZIPCODE_PATTERN.match(row["zipcode"]):
            raise RosterCsvError(f"Row {line} zipcode must use 12345 or 12345-6789")
        locations.append(ScLocationImport(**{**row, "state": state}))
    require_unique(
        (
            (
                "\u0000".join(normalize_key(getattr(location, column)) for column in LOCATION_COLUMNS),
                line,
            )
            for location, (_, line) in zip(locations, parsed)
        ),
        "duplicates an earlier location row",
    )
    return locations


def parse_employees_csv(text: str) -> list[ScEmployeeImport]:
    """Parse an employee roster file into validated rows (nothing is written)."""
    parsed = parse_table(
        text, EMPLOYEE_COLUMNS, max_rows=CSV_MAX_ROWS,
        optional_columns=EMPLOYEE_OPTIONAL_COLUMNS,
    )
    employees: list[ScEmployeeImport] = []
    for row, line in parsed:
        if not is_valid_email(row["email"]):
            raise RosterCsvError(f"Row {line} email is invalid")
        work_state, state_valid = normalize_work_state(row["work_state"])
        if not state_valid or work_state is None:
            raise RosterCsvError(f"Row {line} work_state must use a two-letter code")
        employees.append(ScEmployeeImport(**{**row, "work_state": work_state}))
    require_unique(
        (
            (str(employee.email).lower(), line)
            for employee, (_, line) in zip(employees, parsed)
        ),
        "duplicates an earlier employee email",
    )
    return employees


def resolve_location_timezone(location) -> tuple[str, str]:
    """`(timezone, source)` for a store, or a refusal that names the store.

    A store with no timezone cannot publish a schedule, so setup never writes
    one without it. A chosen zone is kept as-is; a blank is inferred only for a
    state that sits in a single zone.
    """
    chosen = (location.timezone or "").strip()
    try:
        write = timezone_for_create(
            timezone=chosen or None,
            timezone_source="manual" if chosen else "auto",
            state=location.state,
            country_code="US",
        )
    except TimezoneResolutionError as exc:
        raise ScOnboardingError(
            f"Choose a time zone for {location.name}. {exc}"
        ) from exc
    return write.timezone, write.source


def employee_store_keys(body: ScOnboardingComplete) -> list[str | None]:
    """The normalized store name each employee lands at, in roster order.

    A named store must be one of this submission's locations. An employee with
    no store named goes to the only location when there is exactly one AND it
    is in the state the row says they work in, and is otherwise left unassigned
    (`None`) for the manager to place later.

    The state check matters beyond the roster: handbook scoping prefers the
    store's state over the employee's own `work_state`, so quietly placing a
    Nevada worker at a company's one California store would also put them
    under California's handbook. Same rule as bulk upload's `StoreDirectory`.
    """
    names = [_key(location.name) for location in body.locations]
    display = {_key(location.name): location.name.strip() for location in body.locations}
    known = set(names)
    repeated = {name for name in names if names.count(name) > 1}
    only_store = names[0] if len(names) == 1 else None
    only_store_state = body.locations[0].state.upper() if only_store else None

    keys: list[str | None] = []
    unknown: dict[str, str] = {}
    ambiguous: dict[str, str] = {}
    for employee in body.employees:
        if not employee.location:
            in_store_state = employee.work_state.upper() == only_store_state
            keys.append(only_store if in_store_state else None)
            continue
        key = _key(employee.location)
        if key not in known:
            unknown.setdefault(key, employee.location.strip())
        elif key in repeated:
            ambiguous.setdefault(key, display[key])
        keys.append(key)
    if unknown:
        raise ScOnboardingError(
            "Every employee location must match a location name from the "
            "locations step. Not found: "
            + ", ".join(sorted(unknown.values(), key=str.casefold))
        )
    if ambiguous:
        raise ScOnboardingError(
            "More than one location is named "
            + ", ".join(sorted(ambiguous.values(), key=str.casefold))
            + ". Give each location its own name so employees can be assigned to it."
        )
    return keys


def validate_sc_submission(body: ScOnboardingComplete) -> None:
    if naics_industry_description(body.company.naics_code) is None:
        raise ScOnboardingError("NAICS code must use a recognized 2-6 digit sector or subsector")

    for location in body.locations:
        resolve_location_timezone(location)
    employee_store_keys(body)

    emails = _duplicates(str(employee.email) for employee in body.employees)
    if emails:
        raise ScOnboardingError("Employee CSV contains duplicate email(s): " + ", ".join(emails))

    location_keys = [_location_key(location) for location in body.locations]
    if len(set(location_keys)) != len(location_keys):
        raise ScOnboardingError("Location CSV contains a duplicate location row")

    duplicate_jobs = _duplicates(job.name for job in body.jobs)
    if duplicate_jobs:
        raise ScOnboardingError("Jobs contain duplicate name(s): " + ", ".join(duplicate_jobs))

    # "Configured job" means a job in THIS submission — there is no catalog.
    # The title is what assigns an imported employee to a schedule job, and so
    # to that job's credential tasks; an unmatched employee would import with
    # no credential coverage at all, so the rule stays and says how to fix it.
    job_names = {_key(job.name) for job in body.jobs}
    unknown_titles: dict[str, str] = {}
    for employee in body.employees:
        key = _key(employee.job_title)
        if key not in job_names:
            unknown_titles.setdefault(key, employee.job_title.strip())
    if unknown_titles:
        raise ScOnboardingError(
            UNMATCHED_JOB_TITLES_MESSAGE
            + ", ".join(sorted(unknown_titles.values(), key=str.casefold))
        )

    # Certificates are optional across the whole setup: a shop with nothing to
    # certify is not made to invent one before it can schedule anybody.
    for job in body.jobs:
        duplicate_certificates = _duplicates(item.name for item in job.certificates)
        if duplicate_certificates:
            raise ScOnboardingError(f"Job '{job.name}' contains a duplicate certificate")


async def _company_and_product(conn, company_id: UUID, *, lock: bool):
    row = await conn.fetchrow(
        """SELECT id, name, status, signup_source, enabled_features,
                  sc_onboarding_completed_at, industry
             FROM companies WHERE id = $1""" + (" FOR UPDATE" if lock else ""),
        company_id,
    )
    if not row:
        raise ScOnboardingAccessError("Company not found")
    if (row["status"] or "approved") != "approved":
        raise ScOnboardingAccessError("Company must be approved before setup")
    product = await get_product_by_signup_source(
        conn, row["signup_source"], published_only=False
    )
    if not product or product.onboarding_kind != "sc":
        raise ScOnboardingAccessError("Matcha S&C onboarding is not enabled for this company")
    if not is_tenant_activated(product, row["enabled_features"]):
        raise ScOnboardingAccessError("Activate this product before completing setup")
    return row, product


async def get_sc_onboarding_status(conn, *, company_id: UUID) -> dict:
    company, _ = await _company_and_product(conn, company_id, lock=False)
    completed_at = company["sc_onboarding_completed_at"]
    # Signup already asked for headcount and industry; hand both back so the
    # wizard starts from them instead of asking a second time.
    try:
        headcount = await conn.fetchval(
            "SELECT headcount FROM company_handbook_profiles WHERE company_id = $1",
            company_id,
        )
    except asyncpg.UndefinedTableError:
        # Same tolerance as the signup write that seeds this row.
        headcount = None
    return {
        "company_name": company["name"],
        "completed": completed_at is not None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "csv_columns": {
            "locations": list(LOCATION_COLUMNS),
            "employees": list(EMPLOYEE_COLUMNS),
        },
        "csv_optional_columns": {
            "locations": [],
            "employees": list(EMPLOYEE_OPTIONAL_COLUMNS),
        },
        "suggested_company_size": company_size_for_headcount(headcount),
        "suggested_naics_code": INDUSTRY_NAICS_DEFAULTS.get(
            (company.get("industry") or "").strip().lower()
        ),
    }


async def _existing_credential_type(conn, company_id: UUID, label: str):
    return await conn.fetchval(
        """SELECT id FROM scoped_credential_types
            WHERE lower(btrim(label)) = lower(btrim($2))
              AND (company_id IS NULL OR company_id = $1)
            ORDER BY company_id NULLS LAST, id
            LIMIT 1""",
        company_id,
        label,
    )


async def _credential_type(conn, company_id: UUID, label: str, actor_user_id: UUID) -> UUID:
    existing = await _existing_credential_type(conn, company_id, label)
    if existing:
        return existing
    credential_type_id = uuid4()
    # credcustom01's invariant: the `credential_types` row is only an opaque FK
    # target, so the tenant's own wording never lands in the shared catalog
    # (an older app during a blue/green deploy still selects that table whole).
    # The real label lives in company_credential_types and is read back through
    # the scoped_credential_types view — same shape as
    # documents/credential_templates.py:create_credential_type.
    await conn.execute(
        """INSERT INTO credential_types
               (id, key, label, category, description, has_expiration,
                has_number, has_state, verification_method, is_system)
           VALUES ($1, $2, 'Tenant credential', 'custom', NULL, true, false, false,
                   'document_upload', false)""",
        credential_type_id,
        f"custom_{credential_type_id.hex}",
    )
    await conn.execute(
        """INSERT INTO company_credential_types
               (credential_type_id, company_id, label, category, description, created_by)
           VALUES ($1, $2, $3, 'custom', $4, $5)""",
        credential_type_id,
        company_id,
        label.strip(),
        "Created during Matcha S&C account setup",
        actor_user_id,
    )
    # A configured allowlist would otherwise hide the type we just created and
    # make replace_job_credential_requirements reject it.
    await conn.execute(
        """INSERT INTO company_credential_type_filter_items
               (company_id, credential_type_id)
           SELECT $1, $2
            WHERE EXISTS (
                SELECT 1 FROM company_credential_type_filters WHERE company_id = $1
            )
           ON CONFLICT DO NOTHING""",
        company_id,
        credential_type_id,
    )
    return credential_type_id


async def _link_jurisdiction(conn, city: str, state: str, zipcode: str) -> UUID:
    """The jurisdiction a store sits in — publishing a schedule requires one."""
    # Lazy: the compliance package is heavy and this module is imported by the
    # route table at startup.
    from app.core.services.compliance_service import _get_or_create_jurisdiction

    return await _get_or_create_jurisdiction(conn, city, state, None, zipcode)


async def _link_jurisdiction_in_savepoint(conn, city: str, state: str, zipcode: str) -> UUID | None:
    """Link a jurisdiction without letting the lookup sink the whole setup.

    The resolver swallows some of its own statement failures (a missing
    reference table). Outside a transaction that is harmless; inside this one
    the failed statement would leave it aborted, and every write after it —
    the roster, the jobs, the completion stamp — would fail for a reason that
    has nothing to do with them. A savepoint confines the damage to the lookup.

    None means "not linked yet": the store still saves, the post-commit
    compliance run links it, and the schedule's own store form repairs it.
    """
    try:
        async with conn.transaction():
            return await _link_jurisdiction(conn, city, state, zipcode)
    except Exception:
        logger.exception(
            "S&C onboarding could not link a jurisdiction for %s, %s", city, state
        )
        return None


async def _insert_locations(conn, company_id: UUID, locations) -> list[UUID]:
    """Insert the stores publish-ready; returns their ids in submission order.

    `schedule_location_readiness` refuses to publish a store with no timezone
    or no jurisdiction, and nothing else in a scheduling-first setup would fill
    them in later — so they are written here, with the row.
    """
    if not locations:
        return []
    # Ids are minted here rather than read back: RETURNING order is not
    # contractual, and two stores may share every column but the name.
    location_ids = [uuid4() for _ in locations]
    timezones = [resolve_location_timezone(location) for location in locations]
    jurisdictions: dict[tuple[str, str], UUID | None] = {}
    jurisdiction_ids: list[UUID | None] = []
    for location in locations:
        place = (_key(location.city), location.state.upper())
        if place not in jurisdictions:
            jurisdictions[place] = await _link_jurisdiction_in_savepoint(
                conn, location.city.strip(), location.state.upper(), location.zipcode
            )
        jurisdiction_ids.append(jurisdictions[place])
    await conn.execute(
        """INSERT INTO business_locations
               (id, company_id, name, address, city, state, zipcode, source,
                timezone, timezone_source, jurisdiction_id)
           SELECT id, $1, name, address, city, state, zipcode, 'manual',
                  timezone, timezone_source, jurisdiction_id
             FROM UNNEST($2::uuid[], $3::text[], $4::text[], $5::text[], $6::text[],
                         $7::text[], $8::text[], $9::text[], $10::uuid[])
                  AS t(id, name, address, city, state, zipcode,
                       timezone, timezone_source, jurisdiction_id)""",
        company_id,
        location_ids,
        [location.name.strip() for location in locations],
        [location.address.strip() for location in locations],
        [location.city.strip() for location in locations],
        [location.state.upper() for location in locations],
        [location.zipcode for location in locations],
        [timezone for timezone, _ in timezones],
        [source for _, source in timezones],
        jurisdiction_ids,
    )
    return location_ids


async def _insert_employees(
    conn, company_id: UUID, employees, work_location_ids: list[UUID | None]
) -> tuple[dict[str, list[UUID]], dict[str, UUID]]:
    """Insert the roster in one statement and index the new ids by job title.

    `work_location_ids` runs parallel to `employees`: the store each person is
    scheduled at, or None. The schedule roster only lists people who have one.

    Also returns one representative employee id per work state, which the
    post-commit compliance-location sync uses.
    """
    if not employees:
        return {}, {}
    title_by_email = {str(employee.email).lower(): employee.job_title for employee in employees}
    state_by_email = {str(employee.email).lower(): employee.work_state.upper() for employee in employees}
    rows = await conn.fetch(
        """INSERT INTO employees
               (org_id, email, first_name, last_name, work_state, job_title, department,
                work_location_id)
           SELECT $1, email, first_name, last_name, work_state, job_title, department,
                  work_location_id
             FROM UNNEST($2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[],
                         $8::uuid[])
                  AS t(email, first_name, last_name, work_state, job_title, department,
                       work_location_id)
           RETURNING id, email""",
        company_id,
        [str(employee.email).lower() for employee in employees],
        [employee.first_name.strip() for employee in employees],
        [employee.last_name.strip() for employee in employees],
        [employee.work_state.upper() for employee in employees],
        [employee.job_title.strip() for employee in employees],
        [employee.department.strip() for employee in employees],
        work_location_ids,
    )
    employees_by_job: dict[str, list[UUID]] = {}
    employee_by_state: dict[str, UUID] = {}
    for row in rows:
        # RETURNING order is not contractual, so the job title is recovered from
        # the row's own email rather than from the input position.
        email = str(row["email"]).lower()
        employees_by_job.setdefault(_key(title_by_email[email]), []).append(row["id"])
        employee_by_state.setdefault(state_by_email[email], row["id"])
    return employees_by_job, employee_by_state


async def _sync_compliance_locations(conn, company_id: UUID, employee_by_state: dict[str, UUID]) -> None:
    """Derive the compliance/jurisdiction rows every other roster path creates.

    Runs after the setup transaction commits: the helper swallows its own
    errors, and an aborted statement inside the transaction would otherwise
    poison writes that already succeeded. One call per distinct work state is
    enough — the S&C import has no per-employee work city.

    The caller passes only the states with no store of their own. A state the
    manager just gave a real store already has its jurisdiction; deriving a
    second, address-less "CA" location for it put a store nobody created into
    the schedule's store picker.
    """
    from app.matcha.routes.employees._shared import (
        _sync_employee_location_for_compliance,
    )

    for state, employee_id in employee_by_state.items():
        try:
            await _sync_employee_location_for_compliance(
                conn,
                company_id=company_id,
                employee_id=employee_id,
                work_state=state,
                work_city=None,
            )
        except Exception:
            logger.exception(
                "S&C onboarding could not sync compliance location %s for company %s",
                state,
                company_id,
            )


async def _project_store_compliance(location_id: UUID, company_id: UUID) -> None:
    """Give a new store the requirements the shared catalog already holds.

    A pure projection — no live research, no catalog refresh, so no model call
    is spent on a signup. Best-effort: the store is already schedulable.
    """
    from app.core.services.compliance_service import run_compliance_check_background

    try:
        await run_compliance_check_background(
            location_id,
            company_id,
            check_type="proactive",
            allow_live_research=False,
            allow_repository_refresh=False,
        )
    except Exception:
        logger.exception(
            "S&C onboarding could not project compliance for location %s", location_id
        )


async def complete_sc_onboarding(
    conn,
    *,
    company_id: UUID,
    actor_user_id: UUID,
    body: ScOnboardingComplete,
    background_tasks=None,
) -> dict:
    validate_sc_submission(body)
    store_keys = employee_store_keys(body)
    async with conn.transaction():
        company, _ = await _company_and_product(conn, company_id, lock=True)
        if company["sc_onboarding_completed_at"]:
            completed_at = company["sc_onboarding_completed_at"]
            return {"already_completed": True, "completed_at": completed_at.isoformat()}

        existing_emails = await conn.fetch(
            """SELECT email FROM employees
                WHERE org_id = $1 AND lower(email) = ANY($2::text[])""",
            company_id,
            [str(employee.email).lower() for employee in body.employees],
        ) if body.employees else []
        if existing_emails:
            raise ScOnboardingError(
                "Employee email already exists for this company: "
                + ", ".join(sorted({row["email"] for row in existing_emails}, key=str.casefold))
            )

        existing_locations = await conn.fetch(
            """SELECT name, address, city, state, zipcode
                 FROM business_locations WHERE company_id = $1""",
            company_id,
        ) if body.locations else []
        existing_location_keys = {
            (
                _key(str(row["name"] or "")),
                _key(str(row["address"] or "")),
                _key(str(row["city"] or "")),
                _key(str(row["state"] or "")),
                _key(str(row["zipcode"] or "")),
            )
            for row in existing_locations
        }
        if any(_location_key(location) in existing_location_keys for location in body.locations):
            raise ScOnboardingError("This location already exists for this company")

        existing_jobs = await conn.fetch(
            "SELECT name FROM schedule_jobs WHERE company_id = $1",
            company_id,
        )
        existing_job_names = {_key(row["name"]) for row in existing_jobs}
        conflict = next((job.name for job in body.jobs if _key(job.name) in existing_job_names), None)
        if conflict:
            raise ScOnboardingError(f"Job already exists for this company: {conflict}")

        # `industry` is intentionally not written here — signup owns it and uses
        # the controlled INDUSTRY_OPTIONS vocabulary.
        await conn.execute(
            "UPDATE companies SET size = $2, naics = $3 WHERE id = $1",
            company_id,
            body.company.company_size,
            body.company.naics_code,
        )

        location_ids = await _insert_locations(conn, company_id, body.locations)
        # Safe to key by name: employee_store_keys already refused a roster
        # that names a store two locations share.
        location_id_by_name = {
            _key(location.name): location_id
            for location, location_id in zip(body.locations, location_ids)
        }
        employees_by_job, employee_by_state = await _insert_employees(
            conn,
            company_id,
            body.employees,
            [location_id_by_name.get(key) if key else None for key in store_keys],
        )

        credential_types: dict[str, UUID] = {}
        for job in body.jobs:
            job_id = await conn.fetchval(
                """INSERT INTO schedule_jobs
                       (company_id, name, credential_grace_days, created_by)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                company_id,
                job.name.strip(),
                job.credential_grace_days,
                actor_user_id,
            )
            job_employee_ids = employees_by_job.get(_key(job.name), [])
            if job_employee_ids:
                await conn.execute(
                    """INSERT INTO schedule_job_employees
                           (job_id, employee_id, company_id, created_by)
                       SELECT $1, employee_id, $3, $4
                         FROM UNNEST($2::uuid[]) AS t(employee_id)""",
                    job_id,
                    job_employee_ids,
                    company_id,
                    actor_user_id,
                )
            requirements: list[dict] = []
            for certificate in job.certificates:
                certificate_key = _key(certificate.name)
                credential_type_id = credential_types.get(certificate_key)
                if credential_type_id is None:
                    credential_type_id = await _credential_type(
                        conn, company_id, certificate.name, actor_user_id
                    )
                    credential_types[certificate_key] = credential_type_id
                requirements.append(
                    {
                        "credential_type_id": credential_type_id,
                        "is_required": certificate.is_required,
                        "schedule_blocking": certificate.schedule_blocking,
                    }
                )
            if not requirements:
                # A brand-new job with no certificate has no rules to write and
                # no credential tasks to materialize.
                continue
            # This shared scheduling write path persists the job rules first,
            # then materializes employee upload tasks with the job's grace
            # period. Calling materialization before the rules exist silently
            # leaves imported employees with no credential tasks.
            try:
                await replace_job_credential_requirements(
                    conn,
                    company_id=company_id,
                    job_id=job_id,
                    requirements=requirements,
                    actor_user_id=actor_user_id,
                )
            except ScOnboardingError:
                raise
            except ValueError as exc:
                # The shared helper refuses hidden/unknown credential types with
                # a bare ValueError; that is a submission problem, not a bug.
                raise ScOnboardingError(str(exc)) from exc

        completed_at = await conn.fetchval(
            """UPDATE companies SET sc_onboarding_completed_at = NOW()
                 WHERE id = $1 RETURNING sc_onboarding_completed_at""",
            company_id,
        )
    store_states = {location.state.upper() for location in body.locations}
    await _sync_compliance_locations(
        conn,
        company_id,
        {
            state: employee_id
            for state, employee_id in employee_by_state.items()
            if state not in store_states
        },
    )
    if background_tasks is not None:
        for location_id in location_ids:
            background_tasks.add_task(_project_store_compliance, location_id, company_id)
    return {"already_completed": False, "completed_at": completed_at.isoformat()}
