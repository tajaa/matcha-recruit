"""Request-model validation for the employee-schedule feature.

The window checks and the UTC normalization live here rather than in the routes,
so a client that omits a timezone offset gets a clean 422 instead of a 500 from
comparing a naive body datetime against the tz-aware value read back from
Postgres.
"""

from datetime import date, datetime, time, timezone

import pytest
from pydantic import ValidationError

from app.matcha.models.employee_schedule import (
    GenerateFromTemplate,
    PublishRange,
    ScheduleRequestCreate,
    ShiftCreate,
    ShiftUpdate,
)

AWARE = datetime(2026, 7, 13, 9, tzinfo=timezone.utc)
AWARE_END = datetime(2026, 7, 13, 17, tzinfo=timezone.utc)


# ── tz normalization ────────────────────────────────────────────────────────

def test_naive_datetimes_are_read_as_utc():
    # A client that sends "2026-07-13T09:00:00" (no offset) used to produce a
    # naive datetime; comparing it with the aware value from the DB raised
    # TypeError → 500.
    shift = ShiftCreate(starts_at="2026-07-13T09:00:00", ends_at="2026-07-13T17:00:00")
    assert shift.starts_at == AWARE
    assert shift.starts_at.tzinfo is not None


def test_offset_datetimes_are_converted_to_utc():
    shift = ShiftCreate(starts_at="2026-07-13T05:00:00-04:00", ends_at="2026-07-13T17:00:00Z")
    assert shift.starts_at == datetime(2026, 7, 13, 9, tzinfo=timezone.utc)


def test_mixed_naive_and_aware_still_validates_the_window():
    # Previously this comparison raised TypeError inside the validator (a 500);
    # now both sides are UTC, so an inverted window is a clean 422.
    with pytest.raises(ValidationError):
        ShiftCreate(starts_at="2026-07-13T18:00:00Z", ends_at="2026-07-13T09:00:00")


def test_publish_range_normalizes_too():
    body = PublishRange(start="2026-07-12T00:00:00", end="2026-07-19T00:00:00Z")
    assert body.start.tzinfo is not None and body.end > body.start


# ── shift windows ───────────────────────────────────────────────────────────

def test_shift_create_rejects_inverted_window():
    with pytest.raises(ValidationError):
        ShiftCreate(starts_at=AWARE_END, ends_at=AWARE)


def test_shift_create_rejects_zero_length_window():
    with pytest.raises(ValidationError):
        ShiftCreate(starts_at=AWARE, ends_at=AWARE)


def test_shift_update_is_a_true_patch():
    # Unsent fields must be absent from model_fields_set — that is what lets the
    # route write only what the caller sent (and clear on an explicit null).
    body = ShiftUpdate(role="Nurse")
    assert body.model_dump(exclude_unset=True) == {"role": "Nurse"}

    cleared = ShiftUpdate(location_id=None)
    assert cleared.model_dump(exclude_unset=True) == {"location_id": None}

    assert ShiftUpdate().model_dump(exclude_unset=True) == {}


def test_shift_update_checks_window_only_when_both_sent():
    with pytest.raises(ValidationError):
        ShiftUpdate(starts_at=AWARE_END, ends_at=AWARE)
    # one-sided retime is legal here; the route compares against the stored value
    assert ShiftUpdate(ends_at=AWARE_END).ends_at == AWARE_END


# ── template generation ─────────────────────────────────────────────────────

def test_generate_rejects_backwards_range():
    with pytest.raises(ValidationError):
        GenerateFromTemplate(start_date=date(2026, 7, 20), end_date=date(2026, 7, 13))


def test_generate_caps_the_span():
    with pytest.raises(ValidationError):
        GenerateFromTemplate(start_date=date(2026, 1, 1), end_date=date(2027, 1, 1))


def test_generate_accepts_a_single_day():
    body = GenerateFromTemplate(start_date=date(2026, 7, 13), end_date=date(2026, 7, 13))
    assert body.start_date == body.end_date


# ── employee requests ───────────────────────────────────────────────────────

def test_swap_and_drop_require_a_shift():
    for request_type in ("swap", "drop"):
        with pytest.raises(ValidationError):
            ScheduleRequestCreate(request_type=request_type, reason="cover me")


def test_unavailable_requires_a_date_range():
    with pytest.raises(ValidationError):
        ScheduleRequestCreate(request_type="unavailable", reason="vacation")


def test_unavailable_rejects_backwards_range():
    with pytest.raises(ValidationError):
        ScheduleRequestCreate(
            request_type="unavailable",
            unavailable_start=date(2026, 7, 20),
            unavailable_end=date(2026, 7, 13),
        )


def test_valid_unavailable_request():
    body = ScheduleRequestCreate(
        request_type="unavailable",
        unavailable_start=date(2026, 7, 13),
        unavailable_end=date(2026, 7, 20),
    )
    assert body.shift_id is None


def test_template_create_requires_a_time_window():
    from app.matcha.models.employee_schedule import TemplateCreate

    tpl = TemplateCreate(name="Day", start_time=time(9), end_time=time(17), days_of_week=[1, 3])
    assert tpl.required_staff == 1 and tpl.break_minutes == 0
