from datetime import date, datetime, timezone
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
