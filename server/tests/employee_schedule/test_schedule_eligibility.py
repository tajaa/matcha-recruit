import asyncio
from datetime import date
from uuid import uuid4

from app.matcha.services.scheduling.schedule_eligibility import (
    open_expired_eligibility_cases,
    open_expiring_eligibility_warnings,
    schedule_eligibility_roster_flags,
    schedule_eligibility_violations,
)


class FakeConn:
    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "status": "verified", "expires_at": date(2026, 8, 20),
                     "has_expiration": True, "label": "Food handler card",
                     "legal_basis": '{"citation": "Approved state rule"}'}]
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_expired_approved_schedule_blocking_credential_is_a_block():
    violations = asyncio.run(schedule_eligibility_violations(
        FakeConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    assert violations == [{
        "check": "schedule_eligibility", "severity": "block", "code": "credential_expired",
        "message": "Food handler card expired 2026-08-20 and blocks new scheduling.",
        "statute": "Approved state rule", "state": "",
    }]


class PendingCredentialConn:
    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "status": "pending", "expires_at": None,
                     "has_expiration": True, "label": "Food Handler Card",
                     "legal_basis": '{"citation": "Approved state rule"}'}]
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_missing_schedule_blocking_credential_blocks_immediately():
    violations = asyncio.run(schedule_eligibility_violations(
        PendingCredentialConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    assert violations[0]["code"] == "credential_missing"
    assert "approved credential document" in violations[0]["message"]


class ValidCredentialConn:
    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "status": "verified", "expires_at": date(2026, 8, 21),
                     "has_expiration": True, "label": "Food Handler Card",
                     "legal_basis": {"citation": "Approved state rule"}}]
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_credential_is_valid_through_its_expiration_date():
    violations = asyncio.run(schedule_eligibility_violations(
        ValidCredentialConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    assert violations == []


class MinorPermitConn:
    def __init__(self, permits):
        self.permits = permits

    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return []
        if "employee_work_permits" in query:
            return self.permits
        raise AssertionError(query)


def test_minor_without_a_current_location_permit_is_blocked():
    violations = asyncio.run(schedule_eligibility_violations(
        MinorPermitConn([]),
        uuid4(),
        employee_id=uuid4(),
        location_id=uuid4(),
        employee_age=17,
        shift_date=date(2026, 8, 21),
    ))
    assert violations == [{
        "check": "schedule_eligibility", "severity": "block", "code": "minor_work_permit_missing",
        "message": "A confirmed work permit is required before scheduling this minor at this location.",
        "statute": None, "state": "",
    }]


def test_minor_with_a_current_location_permit_is_allowed():
    violations = asyncio.run(schedule_eligibility_violations(
        MinorPermitConn([{
            "id": uuid4(), "location_id": uuid4(), "issued_at": date(2026, 1, 1),
            "expires_at": date(2026, 8, 21), "legal_basis": {},
        }]),
        uuid4(),
        employee_id=uuid4(),
        location_id=uuid4(),
        employee_age=16,
        shift_date=date(2026, 8, 21),
    ))
    assert violations == []


class RosterFlagConn:
    async def fetch(self, query, *args):
        assert "ANY($2::uuid[])" in query
        return [{"employee_id": args[1][0], "status": "pending", "expires_at": None,
                 "has_expiration": True, "warning_days": 14,
                 "label": "Food Handler Card", "legal_basis": {}}]


def test_roster_flags_expose_missing_blocking_credentials():
    employee_id = uuid4()
    flags = asyncio.run(schedule_eligibility_roster_flags(
        RosterFlagConn(), uuid4(), [employee_id], as_of=date(2026, 8, 21),
    ))
    assert flags[str(employee_id)]["blocking_credentials"] == [
        "Food Handler Card requires an approved credential document before scheduling."
    ]


# ── Regression: a food handler card expiring never blocked scheduling ──────
#
# Root cause was the gate's WHERE clause, not _credential_problem: it required
# crt.schedule_blocking=true + crt.review_status IN ('approved','auto_approved')
# on an INNER-joined template — a template nothing seeds and no tenant
# configures by default. A curated system credential type's OWN
# schedule_blocking (set by migration empsched10 for food_handler_card) must
# be sufficient on its own, with no template at all.

class TypeLevelOnlyConn:
    """A requirement with NO template attached (template_id NULL) — the
    reported bug's exact shape: an admin verified a food handler card
    through the credential document flow and never touched a template."""

    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "status": "verified", "expires_at": date(2026, 1, 10),
                     "has_expiration": True, "label": "Food Handler Card",
                     "legal_basis": None}]
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_type_level_blocking_credential_with_no_template_still_blocks():
    violations = asyncio.run(schedule_eligibility_violations(
        TypeLevelOnlyConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    assert violations == [{
        "check": "schedule_eligibility", "severity": "block", "code": "credential_expired",
        "message": "Food Handler Card expired 2026-01-10 and blocks new scheduling.",
        "statute": None, "state": "",
    }]


class QueryCapturingConn:
    """A fake conn can't validate a WHERE clause's actual filtering, but it
    can pin that the broadened tenant-template-OR-system-credential-type
    predicate is still present in the SQL text after a refactor."""

    def __init__(self):
        self.queries: list[str] = []

    async def fetch(self, query, *args):
        self.queries.append(query)
        return []


def test_violations_query_carries_the_broadened_authority_predicate():
    conn = QueryCapturingConn()
    asyncio.run(schedule_eligibility_violations(
        conn, uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    ecr_query = next(q for q in conn.queries if "employee_credential_requirements" in q)
    assert "COALESCE(ct.schedule_blocking, false) = true" in ecr_query
    assert "LEFT JOIN credential_requirement_templates" in ecr_query


def test_roster_flags_query_carries_the_broadened_authority_predicate():
    conn = QueryCapturingConn()
    asyncio.run(schedule_eligibility_roster_flags(conn, uuid4(), [uuid4()], as_of=date(2026, 8, 21)))
    assert "COALESCE(ct.schedule_blocking, false) = true" in conn.queries[0]


# ── The 2-week advance warning ──────────────────────────────────────────

class WarningWindowConn:
    def __init__(self, rows):
        self.rows = rows
        self.inserted: list[tuple] = []

    async def fetch(self, query, *args):
        assert "employee_credential_requirements" in query
        return self.rows

    async def fetchval(self, query, *args):
        assert "INSERT INTO schedule_eligibility_cases" in query
        self.inserted.append(args)
        return uuid4()


def test_credential_inside_warning_window_opens_a_case():
    row = {"requirement_id": uuid4(), "employee_id": uuid4(),
           "expires_at": date(2026, 8, 31), "legal_basis": None, "warning_days": 14}
    opened = asyncio.run(open_expiring_eligibility_warnings(
        WarningWindowConn([row]), uuid4(), as_of=date(2026, 8, 21),
    ))
    assert len(opened) == 1


def test_credential_outside_warning_window_opens_nothing():
    row = {"requirement_id": uuid4(), "employee_id": uuid4(),
           "expires_at": date(2026, 9, 20), "legal_basis": None, "warning_days": 14}
    conn = WarningWindowConn([row])
    opened = asyncio.run(open_expiring_eligibility_warnings(conn, uuid4(), as_of=date(2026, 8, 21)))
    assert opened == []
    assert conn.inserted == []


def test_already_expired_credential_is_not_a_warning():
    # An already-expired credential is excluded by the SQL predicate itself
    # (ecr.expires_at >= $2); the fake conn simply never returns such a row —
    # open_expired_eligibility_cases owns that case instead.
    conn = WarningWindowConn([])
    opened = asyncio.run(open_expiring_eligibility_warnings(conn, uuid4(), as_of=date(2026, 8, 21)))
    assert opened == []


# ── Promote a live warning_open case rather than silently no-op ────────────
#
# The unique partial index on schedule_eligibility_cases covers warning_open
# too, so once open_expiring_eligibility_warnings has opened one, a plain
# open_expired_eligibility_cases INSERT ON CONFLICT DO NOTHING would silently
# do nothing when the same credential later expires.

class PromoteConn:
    def __init__(self, requirement_id, employee_id, expires_at, promoted_case_id):
        self.requirement_id = requirement_id
        self.employee_id = employee_id
        self.expires_at = expires_at
        self.promoted_case_id = promoted_case_id
        self.inserted_new_case = False
        self.case_assignment_inserts: list[tuple] = []

    async def fetch(self, query, *args):
        if "schedule_shifts" in query:
            return [{"shift_id": uuid4(), "location_id": uuid4(), "starts_at": None}]
        if "employee_credential_requirements" in query:
            return [{"requirement_id": self.requirement_id, "employee_id": self.employee_id,
                     "status": "verified", "expires_at": self.expires_at,
                     "label": "Food Handler Card", "has_expiration": True, "legal_basis": None}]
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "UPDATE schedule_eligibility_cases" in query:
            return self.promoted_case_id
        if "INSERT INTO schedule_eligibility_cases" in query:
            self.inserted_new_case = True
            return uuid4()
        raise AssertionError(query)

    async def execute(self, query, *args):
        assert "schedule_eligibility_case_assignments" in query
        self.case_assignment_inserts.append(args)


def test_expiring_credential_promotes_its_existing_warning_case():
    requirement_id, employee_id, expires_at = uuid4(), uuid4(), date(2026, 8, 20)
    promoted_id = uuid4()
    conn = PromoteConn(requirement_id, employee_id, expires_at, promoted_id)

    opened = asyncio.run(open_expired_eligibility_cases(conn, uuid4(), as_of=date(2026, 8, 21)))

    assert opened == [promoted_id]
    assert conn.inserted_new_case is False
    assert len(conn.case_assignment_inserts) == 1
    assert conn.case_assignment_inserts[0][0] == promoted_id


def test_expired_credential_without_prior_warning_creates_new_case():
    requirement_id, employee_id, expires_at = uuid4(), uuid4(), date(2026, 8, 20)
    conn = PromoteConn(requirement_id, employee_id, expires_at, promoted_case_id=None)

    opened = asyncio.run(open_expired_eligibility_cases(conn, uuid4(), as_of=date(2026, 8, 21)))

    assert len(opened) == 1
    assert conn.inserted_new_case is True
