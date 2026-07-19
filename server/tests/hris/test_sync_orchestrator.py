"""HRIS sync orchestrator — the field-plumbing guard.

`_sync_single_employee` reads `normalized` with explicit `.get()` calls against two
hand-maintained SQL column lists. A key the normalizer emits but the SQL never
reads is silently discarded: no splat, no unknown-key warning, no error. That is
not hypothetical — `is_manager` was emitted by all three normalizers from day one
and reached no column at all, so the flag simply never existed.

These tests are DB-free: a fake connection records the SQL and args, which is
enough to assert that every key a normalizer emits reaches a SQL parameter.

Finch is the reference contract (it's the primary provider and the only one whose
payload is a superset); Gusto and ADP must match its key set exactly, emitting
None where their payloads have no equivalent.
"""
import asyncio
import re
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.matcha.services.finch_service import FinchHRISService  # noqa: E402
from app.matcha.services.hris_service import GustoHRISService, HRISService  # noqa: E402
from app.matcha.services import hris_sync_orchestrator as orch  # noqa: E402


# Keys the orchestrator handles somewhere other than the employees INSERT/UPDATE.
# `credentials` has its own upsert; `manager_hris_id` resolves in the second pass;
# `demographics` routes to employee_demographics; `email` is read directly.
_NON_COLUMN_KEYS = {"credentials", "manager_hris_id", "demographics", "email"}

# Set on create, never refreshed on resync: these sit in the INSERT list but have no
# COALESCE in the UPDATE. So a worker who marries and changes their surname in the
# HRIS keeps the old name in Matcha forever, and a corrected start_date never lands.
#
# Recorded here rather than asserted, because it is not obviously wrong: it may be
# protecting hand-corrections in Matcha from being overwritten by a messy feed. It is
# undocumented either way, which is the actual problem. Deciding it is out of scope
# for the is_manager/demographics work — but this list should shrink to empty once
# someone rules on it, not grow.
_INSERT_ONLY_KEYS = {"first_name", "last_name", "personal_email", "start_date"}


class FakeConn:
    """Records execute/fetchrow calls. Mimics just enough asyncpg for the upsert."""

    def __init__(self, existing_employee: bool):
        self._existing = existing_employee
        self.calls: list[tuple[str, tuple]] = []
        self.employee_id = uuid4()

    async def fetchrow(self, sql: str, *args):
        self.calls.append((sql, args))
        if "SELECT id FROM employees" in sql:
            return {"id": self.employee_id} if self._existing else None
        if "INSERT INTO employees" in sql:
            return {"id": self.employee_id}
        return None

    async def fetch(self, sql: str, *args):
        self.calls.append((sql, args))
        return []

    async def fetchval(self, sql: str, *args):
        self.calls.append((sql, args))
        return 0

    async def execute(self, sql: str, *args):
        self.calls.append((sql, args))
        return "UPDATE 1"

    def sql_containing(self, needle: str):
        return [(s, a) for s, a in self.calls if needle in s]


def _finch_worker() -> dict:
    """A merged Finch record with every field we read populated."""
    return {
        "id": "finch-emp-1",
        "individual": {
            "id": "finch-emp-1",
            "first_name": "Dana",
            "last_name": "Reyes",
            "dob": "1985-04-12",
            "gender": "female",
            "ethnicity": "hispanic_or_latino",
            "emails": [{"data": "dana@example.com", "type": "work"}],
            "phone_numbers": [{"data": "555-0100"}],
            "residence": {"line1": "1 Main St", "city": "Austin", "state": "TX", "postal_code": "78701"},
        },
        "employment": {
            "title": "Line Cook",
            "department": {"name": "Kitchen"},
            "employment": {"type": "employee", "subtype": "full_time"},
            "location": {"city": "Austin", "state": "TX"},
            "income": {"amount": 5200000, "unit": "yearly"},
            "flsa_status": "exempt",
            "start_date": "2020-01-15",
            "is_active": True,
            "manager": {"id": "finch-mgr-1"},
        },
    }


def _run_sync(normalized: dict, *, existing: bool) -> FakeConn:
    conn = FakeConn(existing_employee=existing)

    async def go():
        return await orch._sync_single_employee(
            conn,
            company_id=uuid4(),
            normalized=normalized,
            raw_worker={},
            triggered_by=uuid4(),
            source="finch",
        )

    asyncio.run(go())
    return conn


# ── the guard: no emitted key may be silently dropped ──────────────────────────

@pytest.mark.parametrize("existing", [False, True], ids=["insert", "update"])
def test_every_normalized_key_reaches_a_sql_param(existing):
    """The regression that motivated this file: a key the normalizer emits but the
    SQL never reads is inert, and nothing anywhere complains."""
    normalized = FinchHRISService.normalize_worker(_finch_worker())
    conn = _run_sync(normalized, existing=existing)

    stmt = "UPDATE employees" if existing else "INSERT INTO employees"
    sql, args = conn.sql_containing(stmt)[0]
    skip = _NON_COLUMN_KEYS | (_INSERT_ONLY_KEYS if existing else set())

    for key, value in normalized.items():
        if key in skip or value is None:
            continue
        # Dates/Decimals are parsed before binding; compare stringified forms.
        bound = {str(a) for a in args}
        assert str(value) in bound, (
            f"normalize_worker emits {key!r}={value!r} but it never reaches the "
            f"{stmt} params — the field is silently dropped."
        )


def test_is_manager_is_bound_in_both_branches():
    """The specific field that was dropped. Pinned explicitly so a future refactor
    of the column lists can't quietly lose it again."""
    normalized = FinchHRISService.normalize_worker(_finch_worker())
    normalized["is_manager"] = True

    insert_sql, insert_args = _run_sync(normalized, existing=False).sql_containing("INSERT INTO employees")[0]
    assert "is_manager" in insert_sql
    assert True in insert_args

    update_sql, update_args = _run_sync(normalized, existing=True).sql_containing("UPDATE employees")[0]
    assert "is_manager = COALESCE(" in update_sql
    assert True in update_args


def test_insert_placeholder_count_matches_columns_and_args():
    """The two parallel lists are positional: an off-by-one writes the right value
    into the wrong column instead of raising."""
    normalized = FinchHRISService.normalize_worker(_finch_worker())
    sql, args = _run_sync(normalized, existing=False).sql_containing("INSERT INTO employees")[0]

    columns = sql.split("INSERT INTO employees (")[1].split(")")[0]
    n_columns = len([c for c in columns.split(",") if c.strip()])
    placeholders = sql.split("VALUES (")[1].split(")")[0]
    n_placeholders = len(re.findall(r"\$\d+", placeholders))

    assert n_columns == n_placeholders == len(args), (
        f"{n_columns} columns / {n_placeholders} placeholders / {len(args)} args"
    )


# ── Finch is the reference contract ───────────────────────────────────────────

def test_normalizer_key_sets_match_finch():
    """finch_service's docstring promises the normalizers share an output shape, but
    nothing enforced it — Gusto silently lacked termination_date/address/manager_hris_id
    and ADP also lacked pay_rate/pay_classification. Because every read is a .get(),
    the drift degraded to None and stayed invisible."""
    finch_keys = set(FinchHRISService.normalize_worker(_finch_worker()))

    gusto_keys = set(GustoHRISService.normalize_worker({
        "uuid": "g-1", "first_name": "A", "last_name": "B",
        "work_email": "a@example.com", "jobs": [], "terminated": False,
    }))
    adp_keys = set(HRISService.normalize_worker({
        "associateOID": "a-1",
        "person": {"legalName": {"givenName": "A", "familyName1": "B"}},
        "workAssignments": [{}],
    }))

    assert gusto_keys == finch_keys, f"Gusto drift: {finch_keys ^ gusto_keys}"
    assert adp_keys == finch_keys, f"ADP drift: {finch_keys ^ adp_keys}"


def test_finch_reports_unknown_manager_rather_than_false():
    """Finch has no management flag — only manager edges. Claiming False would assert
    every Finch employee manages nobody; None means 'no new fact' to the COALESCE and
    lets the org-graph pass decide."""
    normalized = FinchHRISService.normalize_worker(_finch_worker())
    assert normalized["is_manager"] is None


# ── demographics route to their own table, never onto employees ───────────────

def test_demographics_go_to_restricted_table_not_employees():
    normalized = FinchHRISService.normalize_worker(_finch_worker())
    assert normalized["demographics"] == {
        "date_of_birth": "1985-04-12", "gender": "female", "ethnicity": "hispanic_or_latino",
    }

    conn = _run_sync(normalized, existing=False)

    emp_sql, _ = conn.sql_containing("INSERT INTO employees")[0]
    for forbidden in ("gender", "ethnicity", "date_of_birth"):
        assert forbidden not in emp_sql, f"{forbidden} must not be a column on employees"

    demo = conn.sql_containing("INSERT INTO employee_demographics")
    assert demo, "demographics were emitted but never stored"
    _, args = demo[0]
    assert "female" in args and "hispanic_or_latino" in args


def test_no_demographics_writes_nothing():
    """A provider returning no demographics must not create a blank row, and must not
    blank a row an earlier sync populated."""
    normalized = FinchHRISService.normalize_worker(_finch_worker())
    normalized["demographics"] = None
    conn = _run_sync(normalized, existing=True)
    assert not conn.sql_containing("employee_demographics")


def test_ssn_is_never_taken_from_the_finch_payload():
    """SSN rides the same individual payload as the demographics we do take. It is
    left there on purpose; this pins that so a future field addition can't sweep it in."""
    worker = _finch_worker()
    worker["individual"]["ssn"] = "123-45-6789"
    worker["individual"]["encrypted_ssn"] = "enc:abc"

    normalized = FinchHRISService.normalize_worker(worker)
    flat = str(normalized)
    assert "123-45-6789" not in flat and "enc:abc" not in flat
    assert "ssn" not in normalized and "ssn" not in (normalized["demographics"] or {})
