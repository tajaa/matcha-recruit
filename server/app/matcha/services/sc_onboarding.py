"""Atomic, company-scoped persistence for Matcha S&C account setup."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID, uuid4

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
CSV_MAX_ROWS = 500


class ScOnboardingError(ValueError):
    pass


class ScOnboardingAccessError(ScOnboardingError):
    pass


def _key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


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
    parsed = parse_table(text, EMPLOYEE_COLUMNS, max_rows=CSV_MAX_ROWS)
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


def validate_sc_submission(body: ScOnboardingComplete) -> None:
    if naics_industry_description(body.company.naics_code) is None:
        raise ScOnboardingError("NAICS code must use a recognized 2-6 digit sector or subsector")

    emails = _duplicates(str(employee.email) for employee in body.employees)
    if emails:
        raise ScOnboardingError("Employee CSV contains duplicate email(s): " + ", ".join(emails))

    location_keys = [_location_key(location) for location in body.locations]
    if len(set(location_keys)) != len(location_keys):
        raise ScOnboardingError("Location CSV contains a duplicate location row")

    duplicate_jobs = _duplicates(job.name for job in body.jobs)
    if duplicate_jobs:
        raise ScOnboardingError("Jobs contain duplicate name(s): " + ", ".join(duplicate_jobs))

    job_names = {_key(job.name) for job in body.jobs}
    unknown_titles = sorted(
        {employee.job_title.strip() for employee in body.employees if _key(employee.job_title) not in job_names},
        key=str.casefold,
    )
    if unknown_titles:
        raise ScOnboardingError(
            "Employee job_title must match a configured job: " + ", ".join(unknown_titles)
        )

    required_certificate_count = 0
    for job in body.jobs:
        duplicate_certificates = _duplicates(item.name for item in job.certificates)
        if duplicate_certificates:
            raise ScOnboardingError(f"Job '{job.name}' contains a duplicate certificate")
        required_certificate_count += sum(item.is_required for item in job.certificates)
    if required_certificate_count == 0:
        raise ScOnboardingError("Configure at least one mandatory certificate")


async def _company_and_product(conn, company_id: UUID, *, lock: bool):
    row = await conn.fetchrow(
        """SELECT id, name, status, signup_source, enabled_features,
                  sc_onboarding_completed_at
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
    return {
        "company_name": company["name"],
        "completed": completed_at is not None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "csv_columns": {
            "locations": list(LOCATION_COLUMNS),
            "employees": list(EMPLOYEE_COLUMNS),
        },
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


async def _insert_locations(conn, company_id: UUID, locations) -> None:
    if not locations:
        return
    await conn.execute(
        """INSERT INTO business_locations
               (company_id, name, address, city, state, zipcode, source)
           SELECT $1, name, address, city, state, zipcode, 'manual'
             FROM UNNEST($2::text[], $3::text[], $4::text[], $5::text[], $6::text[])
                  AS t(name, address, city, state, zipcode)""",
        company_id,
        [location.name.strip() for location in locations],
        [location.address.strip() for location in locations],
        [location.city.strip() for location in locations],
        [location.state.upper() for location in locations],
        [location.zipcode for location in locations],
    )


async def _insert_employees(
    conn, company_id: UUID, employees
) -> tuple[dict[str, list[UUID]], dict[str, UUID]]:
    """Insert the roster in one statement and index the new ids by job title.

    Also returns one representative employee id per work state, which the
    post-commit compliance-location sync uses.
    """
    if not employees:
        return {}, {}
    title_by_email = {str(employee.email).lower(): employee.job_title for employee in employees}
    state_by_email = {str(employee.email).lower(): employee.work_state.upper() for employee in employees}
    rows = await conn.fetch(
        """INSERT INTO employees
               (org_id, email, first_name, last_name, work_state, job_title, department)
           SELECT $1, email, first_name, last_name, work_state, job_title, department
             FROM UNNEST($2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[])
                  AS t(email, first_name, last_name, work_state, job_title, department)
           RETURNING id, email""",
        company_id,
        [str(employee.email).lower() for employee in employees],
        [employee.first_name.strip() for employee in employees],
        [employee.last_name.strip() for employee in employees],
        [employee.work_state.upper() for employee in employees],
        [employee.job_title.strip() for employee in employees],
        [employee.department.strip() for employee in employees],
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


async def complete_sc_onboarding(
    conn,
    *,
    company_id: UUID,
    actor_user_id: UUID,
    body: ScOnboardingComplete,
) -> dict:
    validate_sc_submission(body)
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

        await _insert_locations(conn, company_id, body.locations)
        employees_by_job, employee_by_state = await _insert_employees(
            conn, company_id, body.employees
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
    await _sync_compliance_locations(conn, company_id, employee_by_state)
    return {"already_completed": False, "completed_at": completed_at.isoformat()}
