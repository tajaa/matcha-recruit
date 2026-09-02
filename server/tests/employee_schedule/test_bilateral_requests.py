from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.matcha.models.scheduling.employee_schedule import ScheduleRequestCreate
from app.matcha.routes.employee_portal import schedule as portal_schedule
from app.matcha.services.scheduling.shift_requests import schedule_day_bounds, same_day_conflict_detail


def test_bilateral_status_fits_persisted_status_width():
    assert len("awaiting_counterparty") <= 32


def test_swap_requires_named_counterparty():
    with pytest.raises(ValidationError, match="target_employee_id is required"):
        ScheduleRequestCreate(request_type="swap", shift_id=uuid4())


def test_pickup_requires_shift_and_accepts_no_target():
    request = ScheduleRequestCreate(request_type="pickup", shift_id=uuid4())
    assert request.target_employee_id is None

    with pytest.raises(ValidationError, match="shift_id is required"):
        ScheduleRequestCreate(request_type="pickup")


def test_schedule_day_bounds_are_utc_wall_clock():
    start, end = schedule_day_bounds(datetime(2026, 8, 21, 23, 59, tzinfo=timezone.utc))
    assert start == datetime(2026, 8, 21, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 22, tzinfo=timezone.utc)

    start, end = schedule_day_bounds(date(2026, 8, 21))
    assert (end - start).days == 1


def test_same_day_conflict_detail_is_stable():
    employee_id = uuid4()
    shift_id = uuid4()
    detail = same_day_conflict_detail(employee_id, [{"shift_id": shift_id}])
    assert detail["code"] == "same_day_assignment"
    assert detail["conflicting_shift_ids"] == [str(shift_id)]


def test_locked_shift_helper_accepts_a_variable_number_of_ids():
    shared = Path(__file__).parents[2] / "app/matcha/routes/employee_schedule/_shared.py"
    source = shared.read_text()
    assert "async def fetch_locked_shift_pair(conn, company_id: UUID, *shift_ids: UUID)" in source
    assert "sorted(set(shift_ids))" in source


def test_bilateral_migration_removes_pickups_before_legacy_constraint():
    migration = Path(__file__).parents[2] / "alembic/versions/empsched05_bilateral_requests.py"
    source = migration.read_text()
    delete_at = source.index("DELETE FROM schedule_requests WHERE request_type = 'pickup'")
    constraint_at = source.rindex("schedule_requests_request_type_check\"")
    assert delete_at < constraint_at


def test_counterparty_confirmation_queues_notification_after_commit():
    portal = Path(__file__).parents[2] / "app/matcha/routes/employee_portal/schedule.py"
    source = portal.read_text()
    commit_read_at = source.index("row = await conn.fetchrow(f\"{REQUEST_SELECT} WHERE r.id = $1\", request_id)")
    enqueue_at = source.index("send_schedule_request_notifications.delay(str(request_id))")
    assert commit_read_at < enqueue_at


def test_swap_confirmation_checks_both_employees_for_same_day_conflicts():
    portal = Path(__file__).parents[2] / "app/matcha/routes/employee_portal/schedule.py"
    source = portal.read_text()
    assert 'if request["request_type"] == "swap":' in source
    assert "reverse_conflicts = await find_same_day_assignments(" in source
    assert 'request["employee_id"], counter["starts_at"]' in source


def test_counterparty_withdrawal_preserves_the_requested_swap_shift():
    portal = Path(__file__).parents[2] / "app/matcha/routes/employee_portal/schedule.py"
    source = portal.read_text()
    assert (
        "counter_shift_id = CASE WHEN request_type = 'pickup' "
        "THEN NULL ELSE counter_shift_id END"
    ) in source


def test_notification_outbox_is_idempotent_and_migration_activates_digest():
    migration = Path(__file__).parents[2] / "alembic/versions/empsched13_schedule_round2_followups.py"
    source = migration.read_text()
    assert "UNIQUE (request_id, recipient_user_id, event_type)" in source
    assert "UPDATE scheduler_settings SET enabled=true WHERE task_key='schedule_daily_digest'" in source
    assert "'schedule_request_notifications'" in source


@pytest.mark.asyncio
async def test_unavailable_request_rejects_a_week_with_published_shifts(monkeypatch):
    class Connection:
        async def fetchval(self, query, *args):
            assert "EXTRACT(DOW FROM s.starts_at)" in query
            assert args[1] == date(2026, 8, 10)
            assert args[2] == date(2026, 8, 11)
            return True

    @asynccontextmanager
    async def fake_get_connection():
        yield Connection()

    monkeypatch.setattr(portal_schedule, "get_connection", fake_get_connection)

    with pytest.raises(HTTPException, match="week with published shifts") as exc_info:
        await portal_schedule.create_my_schedule_request(
            ScheduleRequestCreate(
                request_type="unavailable",
                unavailable_start=date(2026, 8, 10),
                unavailable_end=date(2026, 8, 11),
            ),
            {"id": uuid4(), "org_id": uuid4()},
        )

    assert exc_info.value.status_code == 409
