"""Integration tests for employee ↔ IR incident linking.

Verifies that the hybrid matching (involved_employee_ids FK + reporter
email/name fallback) works correctly for both the bulk incident-counts
endpoint and the per-employee incidents endpoint.

Requires DATABASE_URL in environment. All mutations run inside a
rolled-back transaction so production data is unaffected.

Run manually:
    cd server
    python3 -m pytest tests/test_employee_incidents.py -v
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

asyncpg = pytest.importorskip("asyncpg")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set"),
    pytest.mark.asyncio,
]

# Fixed UUIDs for test data
COMPANY_ID = uuid.uuid4()
EMP_ALICE = uuid.uuid4()  # linked via involved_employee_ids FK
EMP_BOB = uuid.uuid4()    # linked via reporter email fallback
EMP_CAROL = uuid.uuid4()  # linked via reporter name fallback
EMP_DAVE = uuid.uuid4()   # not linked to any incident
INCIDENT_FK = uuid.uuid4()
INCIDENT_EMAIL = uuid.uuid4()
INCIDENT_NAME = uuid.uuid4()
INCIDENT_RESOLVED = uuid.uuid4()
CREATOR_USER = uuid.uuid4()


@pytest_asyncio.fixture()
async def conn():
    """Connect, start a transaction, yield, then rollback."""
    c = await asyncpg.connect(DATABASE_URL)
    tx = c.transaction()
    await tx.start()
    yield c
    await tx.rollback()
    await c.close()


async def _seed(conn):
    """Insert test company, employees, and incidents inside the transaction."""
    # Ensure column exists (idempotent — may already exist after migration)
    await conn.execute("""
        ALTER TABLE ir_incidents
        ADD COLUMN IF NOT EXISTS involved_employee_ids UUID[] DEFAULT '{}'
    """)
    # Company
    await conn.execute(
        "INSERT INTO companies (id, name) VALUES ($1, $2)",
        COMPANY_ID, "Test Co",
    )
    # Creator user (needed for created_by FK)
    await conn.execute(
        "INSERT INTO users (id, email, password_hash, role) VALUES ($1, $2, $3, $4)",
        CREATOR_USER, "test-creator@test.local", "x", "admin",
    )
    # Employees
    for emp_id, first, last, email, personal in [
        (EMP_ALICE, "Alice", "Smith", "alice@testco.com", None),
        (EMP_BOB, "Bob", "Jones", "bob@testco.com", "bob.personal@gmail.com"),
        (EMP_CAROL, "Carol", "Davis", "carol@testco.com", None),
        (EMP_DAVE, "Dave", "Wilson", "dave@testco.com", None),
    ]:
        await conn.execute(
            """INSERT INTO employees (id, first_name, last_name, email, personal_email, org_id)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            emp_id, first, last, email, personal, COMPANY_ID,
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Incident 1: Alice linked via involved_employee_ids FK
    await conn.execute(
        """INSERT INTO ir_incidents
           (id, incident_number, title, incident_type, severity, status,
            occurred_at, reported_by_name, reported_by_email,
            involved_employee_ids, company_id, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
        INCIDENT_FK, "IR-TEST-001", "Forklift near miss", "safety", "high",
        "investigating", now - timedelta(days=2), "Manager X", "manager@other.com",
        [EMP_ALICE], COMPANY_ID, CREATOR_USER,
    )

    # Incident 2: Bob linked via reporter email (fallback)
    await conn.execute(
        """INSERT INTO ir_incidents
           (id, incident_number, title, incident_type, severity, status,
            occurred_at, reported_by_name, reported_by_email,
            involved_employee_ids, company_id, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
        INCIDENT_EMAIL, "IR-TEST-002", "Spill in kitchen", "safety", "medium",
        "reported", now - timedelta(days=1), "Bobby J", "bob.personal@gmail.com",
        [], COMPANY_ID, CREATOR_USER,
    )

    # Incident 3: Carol linked via reporter name (fallback)
    await conn.execute(
        """INSERT INTO ir_incidents
           (id, incident_number, title, incident_type, severity, status,
            occurred_at, reported_by_name, reported_by_email,
            involved_employee_ids, company_id, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
        INCIDENT_NAME, "IR-TEST-003", "Verbal altercation", "behavioral", "low",
        "action_required", now, "Carol Davis", None,
        [], COMPANY_ID, CREATOR_USER,
    )

    # Incident 4: Alice FK-linked but resolved (should NOT appear in open counts)
    await conn.execute(
        """INSERT INTO ir_incidents
           (id, incident_number, title, incident_type, severity, status,
            occurred_at, reported_by_name, reported_by_email,
            involved_employee_ids, company_id, created_by, resolved_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)""",
        INCIDENT_RESOLVED, "IR-TEST-004", "Old slip resolved", "safety", "low",
        "resolved", now - timedelta(days=30), "Someone", None,
        [EMP_ALICE], COMPANY_ID, CREATOR_USER, now - timedelta(days=25),
    )


# ── Bulk incident counts ──────────────────────────────────────────────


async def test_bulk_counts_fk_match(conn):
    """Employee linked via involved_employee_ids shows open count."""
    await _seed(conn)
    rows = await conn.fetch(
        """
        SELECT e.id AS employee_id, COUNT(DISTINCT i.id)::int AS open_count
        FROM employees e
        JOIN ir_incidents i ON i.company_id = e.org_id
          AND i.status NOT IN ('resolved', 'closed')
          AND (
            e.id = ANY(i.involved_employee_ids)
            OR i.reported_by_email IN (e.email, e.personal_email)
            OR LOWER(i.reported_by_name) = LOWER(e.first_name || ' ' || e.last_name)
          )
        WHERE e.org_id = $1
        GROUP BY e.id
        """,
        COMPANY_ID,
    )
    counts = {r["employee_id"]: r["open_count"] for r in rows}
    # Alice: 1 open (FK), resolved one excluded
    assert counts.get(EMP_ALICE) == 1
    # Bob: 1 open (email fallback)
    assert counts.get(EMP_BOB) == 1
    # Carol: 1 open (name fallback)
    assert counts.get(EMP_CAROL) == 1
    # Dave: not involved
    assert EMP_DAVE not in counts


async def test_bulk_counts_excludes_resolved(conn):
    """Resolved incidents do not appear in open counts."""
    await _seed(conn)
    rows = await conn.fetch(
        """
        SELECT e.id AS employee_id, COUNT(DISTINCT i.id)::int AS open_count
        FROM employees e
        JOIN ir_incidents i ON i.company_id = e.org_id
          AND i.status NOT IN ('resolved', 'closed')
          AND (
            e.id = ANY(i.involved_employee_ids)
            OR i.reported_by_email IN (e.email, e.personal_email)
            OR LOWER(i.reported_by_name) = LOWER(e.first_name || ' ' || e.last_name)
          )
        WHERE e.org_id = $1
        GROUP BY e.id
        """,
        COMPANY_ID,
    )
    counts = {r["employee_id"]: r["open_count"] for r in rows}
    # Alice has 1 open + 1 resolved; only 1 should count
    assert counts.get(EMP_ALICE) == 1


# ── Per-employee incident detail ──────────────────────────────────────


async def test_employee_incidents_fk_role(conn):
    """FK-linked employee gets role='involved'."""
    await _seed(conn)
    rows = await conn.fetch(
        """
        WITH matched AS (
            SELECT i.id, i.incident_number, i.title, i.incident_type,
                   i.severity, i.status, i.occurred_at, i.reported_by_name,
                   CASE
                       WHEN $2 = ANY(i.involved_employee_ids) THEN 1
                       WHEN i.reported_by_email = ANY($3::text[]) THEN 2
                       WHEN LOWER(i.reported_by_name) = LOWER($4) THEN 2
                   END AS role_priority
            FROM ir_incidents i
            WHERE i.company_id = $1
              AND (
                $2 = ANY(i.involved_employee_ids)
                OR i.reported_by_email = ANY($3::text[])
                OR LOWER(i.reported_by_name) = LOWER($4)
              )
        )
        SELECT DISTINCT ON (id)
            id, incident_number, title, role_priority
        FROM matched
        ORDER BY id, role_priority ASC
        """,
        COMPANY_ID, EMP_ALICE, ["alice@testco.com"], "Alice Smith",
    )
    role_map = {1: "involved", 2: "reporter"}
    results = {r["id"]: role_map.get(r["role_priority"], "involved") for r in rows}
    # FK incident → involved
    assert results[INCIDENT_FK] == "involved"
    # Resolved incident also shows (detail endpoint doesn't filter by status)
    assert results[INCIDENT_RESOLVED] == "involved"


async def test_employee_incidents_email_fallback_role(conn):
    """Employee matched by reporter email gets role='reporter'."""
    await _seed(conn)
    rows = await conn.fetch(
        """
        WITH matched AS (
            SELECT i.id, i.incident_number,
                   CASE
                       WHEN $2 = ANY(i.involved_employee_ids) THEN 1
                       WHEN i.reported_by_email = ANY($3::text[]) THEN 2
                       WHEN LOWER(i.reported_by_name) = LOWER($4) THEN 2
                   END AS role_priority
            FROM ir_incidents i
            WHERE i.company_id = $1
              AND (
                $2 = ANY(i.involved_employee_ids)
                OR i.reported_by_email = ANY($3::text[])
                OR LOWER(i.reported_by_name) = LOWER($4)
              )
        )
        SELECT DISTINCT ON (id) id, role_priority
        FROM matched ORDER BY id, role_priority ASC
        """,
        COMPANY_ID, EMP_BOB, ["bob@testco.com", "bob.personal@gmail.com"], "Bob Jones",
    )
    role_map = {1: "involved", 2: "reporter"}
    results = {r["id"]: role_map.get(r["role_priority"], "involved") for r in rows}
    assert results[INCIDENT_EMAIL] == "reporter"


async def test_employee_incidents_name_fallback_role(conn):
    """Employee matched by reporter name gets role='reporter'."""
    await _seed(conn)
    rows = await conn.fetch(
        """
        WITH matched AS (
            SELECT i.id,
                   CASE
                       WHEN $2 = ANY(i.involved_employee_ids) THEN 1
                       WHEN i.reported_by_email = ANY($3::text[]) THEN 2
                       WHEN LOWER(i.reported_by_name) = LOWER($4) THEN 2
                   END AS role_priority
            FROM ir_incidents i
            WHERE i.company_id = $1
              AND (
                $2 = ANY(i.involved_employee_ids)
                OR i.reported_by_email = ANY($3::text[])
                OR LOWER(i.reported_by_name) = LOWER($4)
              )
        )
        SELECT DISTINCT ON (id) id, role_priority
        FROM matched ORDER BY id, role_priority ASC
        """,
        COMPANY_ID, EMP_CAROL, ["carol@testco.com"], "Carol Davis",
    )
    role_map = {1: "involved", 2: "reporter"}
    results = {r["id"]: role_map.get(r["role_priority"], "involved") for r in rows}
    assert results[INCIDENT_NAME] == "reporter"


async def test_employee_no_incidents(conn):
    """Employee with no involvement returns empty results."""
    await _seed(conn)
    rows = await conn.fetch(
        """
        WITH matched AS (
            SELECT i.id,
                   CASE
                       WHEN $2 = ANY(i.involved_employee_ids) THEN 1
                       WHEN i.reported_by_email = ANY($3::text[]) THEN 2
                       WHEN LOWER(i.reported_by_name) = LOWER($4) THEN 2
                   END AS role_priority
            FROM ir_incidents i
            WHERE i.company_id = $1
              AND (
                $2 = ANY(i.involved_employee_ids)
                OR i.reported_by_email = ANY($3::text[])
                OR LOWER(i.reported_by_name) = LOWER($4)
              )
        )
        SELECT DISTINCT ON (id) id, role_priority
        FROM matched ORDER BY id, role_priority ASC
        """,
        COMPANY_ID, EMP_DAVE, ["dave@testco.com"], "Dave Wilson",
    )
    assert len(rows) == 0


async def test_fk_takes_priority_over_email(conn):
    """When employee matches both FK and email, role should be 'involved' not 'reporter'."""
    await _seed(conn)
    # Update incident to also have Alice's email as reporter
    await conn.execute(
        "UPDATE ir_incidents SET reported_by_email = $1 WHERE id = $2",
        "alice@testco.com", INCIDENT_FK,
    )
    rows = await conn.fetch(
        """
        WITH matched AS (
            SELECT i.id,
                   CASE
                       WHEN $2 = ANY(i.involved_employee_ids) THEN 1
                       WHEN i.reported_by_email = ANY($3::text[]) THEN 2
                       WHEN LOWER(i.reported_by_name) = LOWER($4) THEN 2
                   END AS role_priority
            FROM ir_incidents i
            WHERE i.company_id = $1
              AND (
                $2 = ANY(i.involved_employee_ids)
                OR i.reported_by_email = ANY($3::text[])
                OR LOWER(i.reported_by_name) = LOWER($4)
              )
        )
        SELECT DISTINCT ON (id) id, role_priority
        FROM matched ORDER BY id, role_priority ASC
        """,
        COMPANY_ID, EMP_ALICE, ["alice@testco.com"], "Alice Smith",
    )
    role_map = {1: "involved", 2: "reporter"}
    fk_incident = [r for r in rows if r["id"] == INCIDENT_FK][0]
    assert role_map[fk_incident["role_priority"]] == "involved"
