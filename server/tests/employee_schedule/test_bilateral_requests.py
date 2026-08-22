from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.matcha.models.scheduling.employee_schedule import ScheduleRequestCreate
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


def test_schedule_request_insert_types_reused_request_type_parameter():
    route = Path(__file__).parents[2] / "app/matcha/routes/employee_portal/schedule.py"
    source = route.read_text()
    assert "CASE WHEN $3::text IN ('pickup', 'swap')" in source


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
