"""Behavioural coverage for the `is_current` projection in the credentials route.

This one exercises real SQL, so it needs a real database and is skipped unless
`MATCHA_TEST_DATABASE_URL` points at a dev Postgres:

    MATCHA_TEST_DATABASE_URL=postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha \
        python3 -m pytest tests/employees/test_credential_current_document_sql.py -v

Everything runs inside a transaction that is always rolled back — no schema
changes, no rows left behind. Never point it at production.
"""
import asyncio
import os
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.matcha.routes.employees.credentials import _CREDENTIAL_DOCUMENTS_SQL

DSN = os.getenv("MATCHA_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DSN, reason="set MATCHA_TEST_DATABASE_URL to run the credential SQL tests"
)

# The credential timestamp columns are `timestamp without time zone`.
NOW = datetime(2026, 9, 3, 12, 0)


async def _seed_employee(conn):
    company_id = uuid4()
    await conn.execute(
        "INSERT INTO companies (id, name, is_test) VALUES ($1, $2, true)",
        company_id, f"Credential SQL Test {company_id}",
    )
    employee_id = uuid4()
    await conn.execute(
        """INSERT INTO employees (id, org_id, email, first_name, last_name, is_supervisor)
           VALUES ($1, $2, $3, 'Credential', 'Tester', false)""",
        employee_id, company_id, f"credential-{employee_id}@example.com",
    )
    return company_id, employee_id


async def _seed_document(conn, *, company_id, employee_id, document_type, review_status, reviewed_at):
    document_id = uuid4()
    await conn.execute(
        """INSERT INTO credential_documents
           (id, company_id, employee_id, document_type, filename, file_path,
            review_status, reviewed_at, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)""",
        document_id, company_id, employee_id, document_type,
        f"{document_id}.pdf", f"private/{document_id}.pdf",
        review_status, reviewed_at,
    )
    return document_id


async def _credential_type_id(conn, key):
    existing = await conn.fetchval("SELECT id FROM credential_types WHERE key = $1", key)
    if existing:
        return existing
    return await conn.fetchval(
        """INSERT INTO credential_types (key, label, category)
           VALUES ($1, $2, 'clearance') RETURNING id""",
        key, key.replace("_", " ").title(),
    )


async def _is_current_by_id(conn, *, company_id, employee_id):
    rows = await conn.fetch(_CREDENTIAL_DOCUMENTS_SQL, employee_id, company_id, None)
    return {row["id"]: row["is_current"] for row in rows}


def _run(scenario):
    import asyncpg

    async def main():
        conn = await asyncpg.connect(DSN)
        try:
            transaction = conn.transaction()
            await transaction.start()
            try:
                await scenario(conn)
            finally:
                # Always roll back: this test writes to a shared dev database.
                await transaction.rollback()
        finally:
            await conn.close()

    asyncio.run(main())


def test_latest_approved_document_is_current_without_a_requirement():
    async def scenario(conn):
        company_id, employee_id = await _seed_employee(conn)
        older = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="food_handler_card", review_status="approved",
            reviewed_at=NOW - timedelta(days=30),
        )
        newer = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="food_handler_card", review_status="approved",
            reviewed_at=NOW,
        )
        current = await _is_current_by_id(conn, company_id=company_id, employee_id=employee_id)
        assert current[newer] is True
        assert current[older] is False

    _run(scenario)


def test_requirement_without_a_document_pointer_keeps_the_approved_document_current():
    """HRIS-verified, waived and freshly materialized requirements leave the
    pointer NULL. That must not demote the employee's approved document."""
    async def scenario(conn):
        company_id, employee_id = await _seed_employee(conn)
        type_id = await _credential_type_id(conn, "food_handler_card")
        await conn.execute(
            """INSERT INTO employee_credential_requirements
               (employee_id, credential_type_id, status, verified_at)
               VALUES ($1, $2, 'verified', $3)""",
            employee_id, type_id, NOW,
        )
        approved = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="food_handler_card", review_status="approved", reviewed_at=NOW,
        )
        current = await _is_current_by_id(conn, company_id=company_id, employee_id=employee_id)
        assert current[approved] is True

    _run(scenario)


def test_requirement_pointer_wins_over_recency():
    async def scenario(conn):
        company_id, employee_id = await _seed_employee(conn)
        type_id = await _credential_type_id(conn, "food_handler_card")
        pointed = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="food_handler_card", review_status="approved",
            reviewed_at=NOW - timedelta(days=30),
        )
        newer = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="food_handler_card", review_status="approved", reviewed_at=NOW,
        )
        await conn.execute(
            """INSERT INTO employee_credential_requirements
               (employee_id, credential_type_id, status, credential_document_id, verified_at)
               VALUES ($1, $2, 'verified', $3, $4)""",
            employee_id, type_id, pointed, NOW,
        )
        current = await _is_current_by_id(conn, company_id=company_id, employee_id=employee_id)
        assert current[pointed] is True
        assert current[newer] is False

    _run(scenario)


def test_unapproved_and_legacy_null_status_documents_are_never_current():
    async def scenario(conn):
        company_id, employee_id = await _seed_employee(conn)
        pending = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="medical_license", review_status="pending", reviewed_at=None,
        )
        legacy_null = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="medical_license", review_status=None, reviewed_at=None,
        )
        rejected = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="medical_license", review_status="rejected", reviewed_at=NOW,
        )
        current = await _is_current_by_id(conn, company_id=company_id, employee_id=employee_id)
        assert current[pending] is False
        assert current[legacy_null] is False
        assert current[rejected] is False

    _run(scenario)


def test_history_is_scoped_per_document_type():
    async def scenario(conn):
        company_id, employee_id = await _seed_employee(conn)
        card = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="food_handler_card", review_status="approved", reviewed_at=NOW,
        )
        licence = await _seed_document(
            conn, company_id=company_id, employee_id=employee_id,
            document_type="medical_license", review_status="approved",
            reviewed_at=NOW - timedelta(days=90),
        )
        current = await _is_current_by_id(conn, company_id=company_id, employee_id=employee_id)
        assert current[card] is True
        assert current[licence] is True

    _run(scenario)
