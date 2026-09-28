"""The daily digest records each break-reminder email attempt (no DB, no email)."""

import json
from datetime import date
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import daily_digest

DIGEST_DAY = date(2026, 9, 23)
EMPLOYEE_ID = uuid4()
SHIFT_ID = uuid4()
ASSIGNMENT_ID = uuid4()
PLANNED = [{"kind": "meal", "ordinal": 1, "start_local": "2026-09-23T12:00:00", "duration_minutes": 30, "source": "manager"}]


def _shift_row(**overrides):
    row = {
        "name": "Ana Ruiz", "employee_id": EMPLOYEE_ID, "assignment_id": ASSIGNMENT_ID,
        "shift_id": SHIFT_ID, "email": "ana@example.com",
        "compliance_guidance": {"summary": "One 30-minute meal break before the fifth hour."},
        "planned_breaks": json.dumps(PLANNED),
        "manager_note": None, "manager_note_visible_to_employee": False,
        "manager_note_include_in_location_digest": False,
        "manager_note_send_employee_notice": True,
    }
    row.update(overrides)
    return row


class _Conn:
    def __init__(self, rows, *, duplicate_claims=(), record_errors=0):
        self.rows = rows
        self.duplicate_claims = set(duplicate_claims)
        self.record_errors = record_errors
        self.events = []
        self.released = []

    async def fetchrow(self, query, *params):
        assert "FROM business_locations" in query
        return {"name": "Downtown", "timezone": "America/Los_Angeles"}

    async def fetch(self, query, *params):
        if "FROM schedule_shift_assignments a" in query:
            return self.rows
        if "is_manager" in query:
            return [{"email": "lead@example.com"}]
        if "schedule_location_notification_recipients" in query:
            return [{"email": "ops@example.com"}]
        raise AssertionError(query)

    async def fetchval(self, query, *params):
        if "INSERT INTO schedule_digest_deliveries" in query:
            return None if (params[3], params[4]) in self.duplicate_claims else uuid4()
        if "INSERT INTO schedule_break_reminder_events" in query:
            if self.record_errors:
                self.record_errors -= 1
                raise RuntimeError("relation does not exist")
            columns = [c.strip() for c in query.split("(", 1)[1].split(")", 1)[0].replace("\n", " ").split(",")]
            self.events.append(dict(zip(columns, params)))
            return uuid4()
        raise AssertionError(query)

    async def execute(self, query, *params):
        assert "DELETE FROM schedule_digest_deliveries" in query
        self.released.append(params[2])


class _Email:
    def __init__(self, results=None):
        self.results = results or {}
        self.sent = []

    def is_configured(self):
        return True

    async def send_email(self, email, to_name, subject, html):
        self.sent.append(email)
        result = self.results.get(email, True)
        if isinstance(result, Exception):
            raise result
        return result


def _run(monkeypatch, conn, email_service, *, deliverable=True):
    monkeypatch.setattr(daily_digest, "get_email_service", lambda: email_service)
    if deliverable:
        # Test data stays on RFC 2606 domains; pretend they are routable so the
        # accepted/failed paths are reachable without a real address.
        monkeypatch.setattr(daily_digest, "_is_reserved_test_domain", lambda email: False)
    return daily_digest.send_location_daily_digest(
        conn, company_id=uuid4(), location_id=uuid4(), digest_date=DIGEST_DAY,
    )


def _by_recipient(conn):
    return {event["recipient"]: event for event in conn.events}


@pytest.mark.asyncio
async def test_each_break_email_attempt_is_recorded_with_its_outcome(monkeypatch):
    conn = _Conn([_shift_row()])
    service = _Email()

    result = await _run(monkeypatch, conn, service)

    assert result["sent"] == 3
    events = _by_recipient(conn)
    # The operational mailbox gets counts only — it names no one's break.
    assert set(events) == {"ana@example.com", "lead@example.com"}

    employee = events["ana@example.com"]
    assert (employee["channel"], employee["reminder_type"], employee["recipient_type"]) == ("email", "daily_digest", "employee")
    assert employee["outcome"] == "accepted"
    assert employee["employee_id"] == EMPLOYEE_ID and employee["employee_name"] == "Ana Ruiz"
    assert employee["location_name"] == "Downtown" and employee["location_timezone"] == "America/Los_Angeles"
    assert employee["event_date"] == DIGEST_DAY
    assert employee["shift_id"] == SHIFT_ID and employee["assignment_id"] == ASSIGNMENT_ID
    context = json.loads(employee["context"])
    assert context["breaks"] == [{"kind": "meal", "ordinal": 1, "start_local": "2026-09-23T12:00:00", "duration_minutes": 30}]
    assert context["included_break_guidance"] is True

    manager = events["lead@example.com"]
    assert manager["recipient_type"] == "manager" and manager["employee_id"] is None
    assert manager["covered_employee_ids"] == [EMPLOYEE_ID]


@pytest.mark.parametrize("failure,detail", [
    (False, "The email provider did not accept the message"),
    (RuntimeError("SMTP 421"), "RuntimeError: SMTP 421"),
])
@pytest.mark.asyncio
async def test_failed_send_is_recorded_and_its_claim_released(monkeypatch, failure, detail):
    conn = _Conn([_shift_row()])

    await _run(monkeypatch, conn, _Email({"ana@example.com": failure}))

    employee = _by_recipient(conn)["ana@example.com"]
    assert employee["outcome"] == "failed" and employee["outcome_detail"] == detail
    assert conn.released == ["ana@example.com"]  # the next run retries, as before


@pytest.mark.asyncio
async def test_reserved_address_is_recorded_as_unavailable_never_sent(monkeypatch):
    conn = _Conn([_shift_row()])
    service = _Email()

    await _run(monkeypatch, conn, service, deliverable=False)

    assert service.sent == []
    assert {event["outcome"] for event in conn.events} == {"unavailable"}
    assert _by_recipient(conn)["ana@example.com"]["outcome_detail"] == "Reserved test address; never sent"


@pytest.mark.asyncio
async def test_an_already_claimed_recipient_is_no_attempt_and_no_record(monkeypatch):
    conn = _Conn([_shift_row()], duplicate_claims={("ana@example.com", "employee")})
    await _run(monkeypatch, conn, _Email())
    assert "ana@example.com" not in _by_recipient(conn)


@pytest.mark.asyncio
async def test_a_note_only_digest_is_not_a_break_reminder(monkeypatch):
    note_only = _shift_row(
        compliance_guidance=None, planned_breaks=None,
        manager_note="Bring your apron", manager_note_visible_to_employee=True,
    )
    conn = _Conn([note_only])
    service = _Email()

    await _run(monkeypatch, conn, service)

    assert "ana@example.com" in service.sent
    assert conn.events == []


@pytest.mark.asyncio
async def test_a_lost_record_does_not_stop_later_recipients(monkeypatch):
    conn = _Conn([_shift_row()], record_errors=1)
    service = _Email()

    await _run(monkeypatch, conn, service)

    assert set(service.sent) == {"lead@example.com", "ops@example.com", "ana@example.com"}
    assert list(_by_recipient(conn)) == ["ana@example.com"]
