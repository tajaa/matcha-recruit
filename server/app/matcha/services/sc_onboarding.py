"""Atomic, company-scoped persistence for Matcha S&C account setup."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID, uuid4

from app.core.services.product_definitions import (
    get_product_by_signup_source,
    is_tenant_activated,
)
from app.matcha.models.sc_onboarding import ScOnboardingComplete
from app.matcha.services.ir.naics_titles import naics_industry_description
from app.matcha.services.scheduling.job_credential_requirements import (
    replace_job_credential_requirements,
)


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
    await conn.execute(
        """INSERT INTO credential_types
               (id, key, label, category, description, has_expiration,
                has_number, has_state, verification_method, is_system)
           VALUES ($1, $2, $3, 'other', $4, true, false, false,
                   'document_upload', false)""",
        credential_type_id,
        f"sc_{credential_type_id.hex}",
        label.strip(),
        "Created during Matcha S&C account setup",
    )
    await conn.execute(
        """INSERT INTO company_credential_types
               (credential_type_id, company_id, label, category, description, created_by)
           VALUES ($1, $2, $3, 'other', $4, $5)""",
        credential_type_id,
        company_id,
        label.strip(),
        "Created during Matcha S&C account setup",
        actor_user_id,
    )
    return credential_type_id


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

        await conn.execute(
            "UPDATE companies SET size = $2, naics = $3, industry = $4 WHERE id = $1",
            company_id,
            body.company.company_size,
            body.company.naics_code,
            body.company.industry.strip(),
        )

        for location in body.locations:
            await conn.execute(
                """INSERT INTO business_locations
                       (company_id, name, address, city, state, zipcode, source)
                   VALUES ($1, $2, $3, $4, $5, $6, 'manual')""",
                company_id,
                location.name.strip(),
                location.address.strip(),
                location.city.strip(),
                location.state.upper(),
                location.zipcode,
            )

        employees_by_job: dict[str, list[UUID]] = {}
        for employee in body.employees:
            employee_id = await conn.fetchval(
                """INSERT INTO employees
                       (org_id, email, first_name, last_name, work_state, job_title, department)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   RETURNING id""",
                company_id,
                str(employee.email).lower(),
                employee.first_name.strip(),
                employee.last_name.strip(),
                employee.work_state.upper(),
                employee.job_title.strip(),
                employee.department.strip(),
            )
            employees_by_job.setdefault(_key(employee.job_title), []).append(employee_id)

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
            for employee_id in employees_by_job.get(_key(job.name), []):
                await conn.execute(
                    """INSERT INTO schedule_job_employees
                           (job_id, employee_id, company_id, created_by)
                       VALUES ($1, $2, $3, $4)""",
                    job_id,
                    employee_id,
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
            await replace_job_credential_requirements(
                conn,
                company_id=company_id,
                job_id=job_id,
                requirements=requirements,
                actor_user_id=actor_user_id,
            )

        completed_at = await conn.fetchval(
            """UPDATE companies SET sc_onboarding_completed_at = NOW()
                 WHERE id = $1 RETURNING sc_onboarding_completed_at""",
            company_id,
        )
    return {"already_completed": False, "completed_at": completed_at.isoformat()}
