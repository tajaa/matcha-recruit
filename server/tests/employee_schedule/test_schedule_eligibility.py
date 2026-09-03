import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.matcha.services.scheduling.schedule_rules import (
    compliance_relevant_patch, job_changed,
)
from app.matcha.services.scheduling.schedule_eligibility import (
    _schedule_blocking_requirements,
    local_date_at,
    open_expired_eligibility_cases,
    open_expired_job_credential_cases,
    open_expiring_eligibility_warnings,
    schedule_eligibility_roster_flags,
    schedule_eligibility_violations,
)


JOB = uuid4()


def test_local_date_uses_location_timezone_and_falls_back_to_utc():
    instant = datetime(2026, 8, 26, 5, tzinfo=timezone.utc)
    assert local_date_at(instant, "America/Los_Angeles") == date(2026, 8, 25)
    assert local_date_at(instant, "not/a-real-timezone") == date(2026, 8, 26)


def test_food_handler_tracking_migration_backfills_orphan_documents():
    migration = Path(__file__).parents[2] / "alembic/versions/empsched14_food_handler_document_tracking.py"
    source = migration.read_text()
    delivery_migration = (
        Path(__file__).parents[2]
        / "alembic/versions/empsched15_schedule_eligibility_notification_deliveries.py"
    ).read_text()

    assert "ADD COLUMN IF NOT EXISTS expires_at DATE" in source
    assert "document_type='food_handler_card'" in source
    assert "INSERT INTO employee_credential_requirements" in source
    assert "applies_company_wide" in source
    assert "extracted_data #>> '{fields,expiration,value}'" not in source
    assert "schedule_eligibility_notification_deliveries" in delivery_migration
    assert 'down_revision = "empsched14"' in delivery_migration


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


class JobCredentialGraceConn:
    async def fetch(self, query, *args):
        if "schedule_job_credential_requirements" in query:
            return [{
                "job_requirement_id": uuid4(), "schedule_blocking": True, "is_required": True,
                "effective_from": date(2026, 8, 1), "label": "Food Handler Card",
                "has_expiration": True, "status": "pending", "expires_at": None,
                "employee_start_date": date(2026, 8, 10), "employee_created_on": date(2026, 8, 10),
                "grace_days": 7,
            }]
        if "employee_credential_requirements" in query:
            return []
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_job_credential_missing_is_deferred_only_during_its_grace_period():
    company_id, employee_id, job_id = uuid4(), uuid4(), uuid4()
    in_grace = asyncio.run(schedule_eligibility_violations(
        JobCredentialGraceConn(), company_id, employee_id=employee_id, job_id=job_id,
        shift_date=date(2026, 8, 16),
    ))
    after_grace = asyncio.run(schedule_eligibility_violations(
        JobCredentialGraceConn(), company_id, employee_id=employee_id, job_id=job_id,
        shift_date=date(2026, 8, 17),
    ))
    assert in_grace == []
    assert after_grace[0]["code"] == "credential_missing"


def test_job_credential_does_not_block_an_unrelated_job():
    violations = asyncio.run(schedule_eligibility_violations(
        JobCredentialGraceConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 30),
    ))
    assert violations == []


def test_chat_schedule_preserves_template_job_for_eligibility_enforcement():
    chat = Path(__file__).parents[2] / "app/matcha/services/scheduling/schedule_chat.py"
    source = chat.read_text()
    assert "required_staff, days_of_week, job_id" in source
    assert '"job_id": str(s["job_id"]) if s.get("job_id") else None' in source
    assert "job_id=job_id," in source


def test_shift_job_change_rechecks_existing_assignments():
    shifts = Path(__file__).parents[2] / "app/matcha/routes/employee_schedule/shifts.py"
    source = shifts.read_text()
    assert "kind, training_requirement_id, job_id" in source
    assert "unqualified = await check_job_qualification(" in source
    assert "starts_at=new_start" in source
    # The rule itself is asserted on behaviour below, not on this file's text:
    # a job CHANGE re-runs the pass, a job merely resent does not.
    assert compliance_relevant_patch(
        {"job_id": JOB}, {"job_id": None}, retimed=False, auto_break_requested=False,
    )


def test_resending_an_unchanged_job_is_not_compliance_relevant():
    # The editor sends job_id on every save. Reading "sent" as "changed" made a
    # notes-only edit re-run break minimums, conflicts, availability and Fair
    # Workweek — and 422/409 saves that used to go through.
    existing = {"job_id": JOB}

    assert not compliance_relevant_patch(
        {"job_id": JOB, "notes": "restock the back bar"}, existing,
        retimed=False, auto_break_requested=False,
    )
    assert not job_changed({"job_id": JOB}, existing)


def test_clearing_a_job_is_a_change():
    assert job_changed({"job_id": None}, {"job_id": JOB})


def test_an_omitted_job_is_never_a_change():
    assert not job_changed({"notes": "x"}, {"job_id": JOB})


def test_retime_break_and_location_stay_compliance_relevant():
    existing = {"job_id": JOB}
    for patch, kwargs in (
        ({}, {"retimed": True, "auto_break_requested": False}),
        ({}, {"retimed": False, "auto_break_requested": True}),
        ({"break_minutes": 30}, {"retimed": False, "auto_break_requested": False}),
        ({"location_id": None}, {"retimed": False, "auto_break_requested": False}),
    ):
        assert compliance_relevant_patch(patch, existing, **kwargs)


def test_schedule_feature_no_longer_requires_matcha_ops():
    flags = Path(__file__).parents[2] / "app/core/feature_flags.py"
    routes = Path(__file__).parents[2] / "app/matcha/routes/__init__.py"
    worker = Path(__file__).parents[2] / "app/workers/tasks/schedule_eligibility.py"
    assert '"employee_schedule": ("matcha_ops",)' not in flags.read_text()
    assert 'dependencies=[Depends(require_feature("employee_schedule"))]' in routes.read_text()
    assert 'if not features.get("employee_schedule"):' in worker.read_text()


class JobExpiryConn:
    def __init__(self):
        self.company_id, self.job_id, self.employee_id = uuid4(), uuid4(), uuid4()
        self.requirement_id, self.location_id, self.case_id = uuid4(), uuid4(), uuid4()
        self.assigned = True
        self.insert_calls = 0

    async def fetch(self, query, *args):
        if "FROM schedule_job_credential_requirements jr" in query:
            return [{
                "job_id": self.job_id, "requirement_id": self.requirement_id,
                "employee_id": self.employee_id, "status": "verified",
                "expires_at": date(2026, 8, 20), "label": "Food Handler Card",
                "has_expiration": True, "auto_unassign_on_expiry": True,
            }]
        if "FROM schedule_shifts s" in query:
            return ([{"shift_id": uuid4(), "location_id": self.location_id,
                      "starts_at": None, "timezone": "UTC"}] if self.assigned else [])
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "INSERT INTO schedule_eligibility_cases" in query:
            self.insert_calls += 1
            return self.case_id if self.insert_calls == 1 else None
        if "SELECT id FROM schedule_eligibility_cases" in query:
            return self.case_id
        raise AssertionError(query)

    async def execute(self, _query, *_args):
        return None


def test_job_expiry_worker_only_opens_and_removes_once(monkeypatch):
    conn = JobExpiryConn()

    async def remove_once(*_args, **_kwargs):
        conn.assigned = False
        return True

    monkeypatch.setattr("app.matcha.services.scheduling.schedule_eligibility.remove_assignment_core", remove_once)
    first = asyncio.run(open_expired_job_credential_cases(conn, conn.company_id, as_of=date(2026, 8, 21)))
    second = asyncio.run(open_expired_job_credential_cases(conn, conn.company_id, as_of=date(2026, 8, 21)))
    assert first == [conn.case_id]
    assert second == []
    assert conn.insert_calls == 1


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


def test_tenant_opt_out_template_suppresses_the_curated_food_handler_fallback():
    conn = QueryCapturingConn()
    asyncio.run(_schedule_blocking_requirements(conn, uuid4(), [uuid4()]))

    query = conn.queries[0]
    assert "credential_requirement_templates opt_out" in query
    assert "opt_out.schedule_blocking = false" in query
    assert "opt_out.review_status IN ('approved', 'auto_approved')" in query


# ── The 2-week advance warning ──────────────────────────────────────────

class WarningWindowConn:
    def __init__(self, rows):
        self.rows = rows
        self.inserted: list[tuple] = []
        self.query = ""

    async def fetch(self, query, *args):
        assert "employee_credential_requirements" in query
        self.query = query
        return self.rows

    async def fetchval(self, query, *args):
        assert "INSERT INTO schedule_eligibility_cases" in query
        self.inserted.append(args)
        return uuid4()


def test_credential_inside_warning_window_opens_a_case():
    row = {"requirement_id": uuid4(), "employee_id": uuid4(),
           "expires_at": date(2026, 8, 31), "legal_basis": None, "warning_days": 14,
           "work_location_id": uuid4()}
    opened = asyncio.run(open_expiring_eligibility_warnings(
        WarningWindowConn([row]), uuid4(), as_of=date(2026, 8, 21),
    ))
    assert len(opened) == 1


def test_pending_renewal_with_known_expiry_still_participates_in_warning_sweep():
    row = {"requirement_id": uuid4(), "employee_id": uuid4(),
           "expires_at": date(2026, 8, 31), "legal_basis": None, "warning_days": 14,
           "work_location_id": uuid4()}
    conn = WarningWindowConn([row])

    asyncio.run(open_expiring_eligibility_warnings(conn, uuid4(), as_of=date(2026, 8, 21)))

    assert "ecr.status <> 'waived'" in conn.query
    assert len(conn.inserted) == 1


def test_expiring_credential_case_is_scoped_to_the_employees_assigned_location():
    assigned_location = uuid4()
    row = {"requirement_id": uuid4(), "employee_id": uuid4(),
           "expires_at": date(2026, 8, 31), "legal_basis": None, "warning_days": 14,
           "work_location_id": assigned_location}
    conn = WarningWindowConn([row])
    asyncio.run(open_expiring_eligibility_warnings(conn, uuid4(), as_of=date(2026, 8, 21)))

    assert conn.inserted[0][2] == assigned_location


def test_credential_outside_warning_window_opens_nothing():
    row = {"requirement_id": uuid4(), "employee_id": uuid4(),
           "expires_at": date(2026, 9, 20), "legal_basis": None, "warning_days": 14,
           "work_location_id": uuid4()}
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
        self.location_id = uuid4()
        self.inserted_new_case = False
        self.case_assignment_inserts: list[tuple] = []

    async def fetch(self, query, *args):
        if "schedule_shifts" in query:
            return [{"shift_id": uuid4(), "location_id": self.location_id, "starts_at": None}]
        if "employee_credential_requirements" in query:
            return [{"requirement_id": self.requirement_id, "employee_id": self.employee_id,
                     "status": "verified", "expires_at": self.expires_at,
                     "label": "Food Handler Card", "has_expiration": True, "legal_basis": None,
                     "work_location_id": self.location_id, "auto_unassign_on_expiry": False}]
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


# ── Food-handler expiry automatically removes future assignments ──────────

class AutoUnassignConn:
    def __init__(self, *, existing_case=False):
        self.company_id = uuid4()
        self.employee_id = uuid4()
        self.requirement_id = uuid4()
        self.location_id = uuid4()
        self.shift_id = uuid4()
        self.case_id = uuid4()
        self.existing_case = existing_case
        self.deleted = False
        self.executed: list[str] = []
        self.fetchval_queries: list[str] = []

    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{
                "requirement_id": self.requirement_id,
                "employee_id": self.employee_id,
                "status": "verified",
                "expires_at": date(2026, 8, 20),
                "label": "Food Handler Card",
                "has_expiration": True,
                "legal_basis": None,
                "work_location_id": self.location_id,
                "auto_unassign_on_expiry": True,
            }]
        if "schedule_shifts" in query:
            return [{
                "shift_id": self.shift_id, "location_id": self.location_id,
                "starts_at": datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 8, 22, 17, tzinfo=timezone.utc),
                "status": "draft", "kind": "work",
                "timezone": "UTC",
            }]
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        self.fetchval_queries.append(query)
        if "UPDATE schedule_eligibility_cases" in query:
            if "AND status='removal_requested'" in query and self.existing_case:
                return self.case_id
            return None
        if "INSERT INTO schedule_eligibility_cases" in query:
            return None if self.existing_case else self.case_id
        raise AssertionError(query)

    async def execute(self, query, *args):
        self.executed.append(query)
        if "DELETE FROM schedule_shift_assignments" in query:
            self.deleted = True
            return "DELETE 1"
        return "UPDATE 1"


def test_expired_food_handler_card_removes_future_assignments_automatically():
    conn = AutoUnassignConn()
    opened = asyncio.run(open_expired_eligibility_cases(conn, conn.company_id, as_of=date(2026, 8, 21)))

    assert opened == [conn.case_id]
    assert conn.deleted is True
    assert any("INSERT INTO schedule_eligibility_case_assignments" in query for query in conn.executed)
    assert any("action_status=$1" in query for query in conn.executed)


class RemovedExpiredCardConn(AutoUnassignConn):
    async def fetch(self, query, *args):
        rows = await super().fetch(query, *args)
        if "employee_credential_requirements" in query:
            rows[0]["status"] = "pending"
        return rows


def test_removed_card_keeps_known_expiry_for_automatic_unassignment():
    conn = RemovedExpiredCardConn()

    asyncio.run(open_expired_eligibility_cases(conn, conn.company_id, as_of=date(2026, 8, 21)))

    assert conn.deleted is True


def test_auto_enforcement_removes_shifts_for_an_already_open_case():
    conn = AutoUnassignConn(existing_case=True)
    opened = asyncio.run(open_expired_eligibility_cases(conn, conn.company_id, as_of=date(2026, 8, 21)))

    assert opened == []  # no duplicate notification for an old open case
    assert conn.deleted is True
    assert any("blocking_reason_code" in query for query in conn.fetchval_queries)


class MultiLocationAutoUnassignConn(AutoUnassignConn):
    def __init__(self):
        super().__init__()
        self.second_location_id = uuid4()
        self.second_shift_id = uuid4()
        self.second_case_id = uuid4()
        self.case_ids = iter((self.case_id, self.second_case_id))
        self.deleted_shifts: list = []

    async def fetch(self, query, *args):
        if "schedule_shifts" in query:
            return [
                {"shift_id": self.shift_id, "location_id": self.location_id,
                 "starts_at": datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
                 "ends_at": datetime(2026, 8, 22, 17, tzinfo=timezone.utc),
                 "status": "draft", "kind": "work", "timezone": "UTC"},
                {"shift_id": self.second_shift_id, "location_id": self.second_location_id,
                 "starts_at": datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
                 "ends_at": datetime(2026, 8, 22, 17, tzinfo=timezone.utc),
                 "status": "draft", "kind": "work", "timezone": "UTC"},
            ]
        return await super().fetch(query, *args)

    async def fetchval(self, query, *args):
        self.fetchval_queries.append(query)
        if "UPDATE schedule_eligibility_cases" in query:
            return None
        if "INSERT INTO schedule_eligibility_cases" in query:
            return next(self.case_ids)
        raise AssertionError(query)

    async def execute(self, query, *args):
        self.executed.append(query)
        if "DELETE FROM schedule_shift_assignments" in query:
            self.deleted_shifts.append(args[0])
            return "DELETE 1"
        return "UPDATE 1"


def test_multi_location_employee_gets_one_case_per_affected_location():
    conn = MultiLocationAutoUnassignConn()
    opened = asyncio.run(open_expired_eligibility_cases(conn, conn.company_id, as_of=date(2026, 8, 21)))

    assert set(opened) == {conn.case_id, conn.second_case_id}
    assert set(conn.deleted_shifts) == {conn.shift_id, conn.second_shift_id}
