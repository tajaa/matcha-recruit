"""Request-model validation for the employee-schedule feature.

The window checks and the UTC normalization live here rather than in the routes,
so a client that omits a timezone offset gets a clean 422 instead of a 500 from
comparing a naive body datetime against the tz-aware value read back from
Postgres.
"""

from datetime import date, datetime, time, timezone

import pytest
from pydantic import ValidationError

from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityReplace,
    AvailabilityWindow,
    AssignmentMove,
    BlockCreate,
    BlockUpdate,
    DuplicateShift,
    GenerateFromWeekTemplate,
    PublishRange,
    ScheduleRequestCreate,
    ShiftCreate,
    ShiftUpdate,
    WeekTemplateCreate,
    WeekTemplateReplace,
    WeekTemplateUpdate,
)

AWARE = datetime(2026, 7, 13, 9, tzinfo=timezone.utc)
AWARE_END = datetime(2026, 7, 13, 17, tzinfo=timezone.utc)


# -- assignment moves ---------------------------------------------------------

def test_assignment_move_accepts_distinct_shifts():
    source = "11111111-1111-1111-1111-111111111111"
    target = "22222222-2222-2222-2222-222222222222"
    move = AssignmentMove(
        employee_id="33333333-3333-3333-3333-333333333333",
        from_shift_id=source,
        to_shift_id=target,
    )
    assert str(move.from_shift_id) == source
    assert str(move.to_shift_id) == target


def test_assignment_move_rejects_same_shift():
    shift_id = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(ValidationError):
        AssignmentMove(
            employee_id="33333333-3333-3333-3333-333333333333",
            from_shift_id=shift_id,
            to_shift_id=shift_id,
        )


def test_assignment_move_rejects_invalid_uuid():
    with pytest.raises(ValidationError):
        AssignmentMove(
            employee_id="not-a-uuid",
            from_shift_id="11111111-1111-1111-1111-111111111111",
            to_shift_id="22222222-2222-2222-2222-222222222222",
        )


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


# ── week template generation ────────────────────────────────────────────────

def test_week_generate_rejects_backwards_range():
    with pytest.raises(ValidationError):
        GenerateFromWeekTemplate(start_date=date(2026, 7, 20), end_date=date(2026, 7, 13))


def test_week_generate_caps_the_span():
    with pytest.raises(ValidationError):
        GenerateFromWeekTemplate(start_date=date(2026, 1, 1), end_date=date(2027, 1, 1))


def test_week_generate_accepts_a_single_day():
    body = GenerateFromWeekTemplate(start_date=date(2026, 7, 13), end_date=date(2026, 7, 13))
    assert body.start_date == body.end_date


def test_block_create_defaults():
    blk = BlockCreate(name="Box Office", start_time=time(9), end_time=time(22), days_of_week=[1, 2, 3, 4, 5])
    assert blk.required_staff == 1 and blk.break_minutes == 0 and blk.role is None


def test_block_create_has_no_location_field():
    # Location lives on the parent week template and is mirrored down by the
    # route — a block payload that could set it independently would let the
    # two diverge, and every read path assumes they cannot.
    assert "location_id" not in BlockCreate.model_fields


def test_block_update_is_a_true_patch():
    assert BlockUpdate(role="Usher").model_dump(exclude_unset=True) == {"role": "Usher"}
    assert BlockUpdate(role=None).model_dump(exclude_unset=True) == {"role": None}
    assert BlockUpdate().model_dump(exclude_unset=True) == {}


def test_week_template_create_accepts_inline_blocks():
    tpl = WeekTemplateCreate(name="Standard Week", blocks=[
        BlockCreate(name="Box Office", start_time=time(9), end_time=time(22), days_of_week=[1, 2, 3, 4, 5]),
        BlockCreate(name="Weekend Crew", start_time=time(9), end_time=time(23), days_of_week=[0, 6]),
    ])
    assert len(tpl.blocks) == 2


def test_week_template_create_allows_no_blocks():
    # A container saved first, blocks added later from the card.
    assert WeekTemplateCreate(name="Christmas Week").blocks == []


def test_week_template_create_caps_block_count():
    with pytest.raises(ValidationError):
        WeekTemplateCreate(name="Silly", blocks=[
            BlockCreate(name=f"B{i}", start_time=time(9), end_time=time(17), days_of_week=[1])
            for i in range(41)
        ])


def test_week_template_update_is_a_true_patch():
    assert WeekTemplateUpdate(name="Renamed").model_dump(exclude_unset=True) == {"name": "Renamed"}
    assert WeekTemplateUpdate(location_id=None).model_dump(exclude_unset=True) == {"location_id": None}


def test_week_template_replace_accepts_existing_and_new_blocks():
    body = WeekTemplateReplace(name="Standard Week", blocks=[
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Front-door opening shift",
            "role": "Usher",
            "start_time": "09:00",
            "end_time": "17:00",
            "days_of_week": [1, 2, 3, 4, 5],
        },
        {
            "name": "Weekend crew",
            "start_time": "10:00",
            "end_time": "18:00",
            "days_of_week": [0, 6],
        },
    ])
    assert str(body.blocks[0].id) == "11111111-1111-1111-1111-111111111111"
    assert body.blocks[1].id is None


def test_week_template_replace_only_retains_editor_owned_block_fields():
    body = WeekTemplateReplace(name="Standard Week", blocks=[{
        "name": "Opening",
        "start_time": "09:00",
        "end_time": "17:00",
        "department": "Operations",
        "color": "#123456",
        "notes": "Managed elsewhere",
        "job_id": "22222222-2222-2222-2222-222222222222",
    }])

    assert set(body.blocks[0].model_dump()) == {
        "id", "name", "role", "start_time", "end_time", "break_minutes",
        "required_staff", "days_of_week",
    }


def test_week_template_replace_rejects_duplicate_existing_block_ids():
    block = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Opening",
        "start_time": "09:00",
        "end_time": "17:00",
    }
    with pytest.raises(ValidationError, match="block ids must be unique"):
        WeekTemplateReplace(name="Standard Week", blocks=[block, block])


# ── employee requests ───────────────────────────────────────────────────────

def test_swap_and_drop_require_a_shift():
    for request_type in ("swap", "drop"):
        with pytest.raises(ValidationError):
            ScheduleRequestCreate(request_type=request_type, reason="cover me")


def test_swap_requires_a_specific_counter_shift():
    with pytest.raises(ValidationError, match="counter_shift_id is required"):
        ScheduleRequestCreate(
            request_type="swap",
            shift_id="11111111-1111-1111-1111-111111111111",
            target_employee_id="22222222-2222-2222-2222-222222222222",
        )


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



# ── training-as-shift (kind) ─────────────────────────────────────────────────

REQ_ID = "11111111-1111-1111-1111-111111111111"


def test_default_kind_is_work_and_requirement_is_optional():
    shift = ShiftCreate(starts_at="2026-07-13T09:00:00Z", ends_at="2026-07-13T17:00:00Z")
    assert shift.kind == "work"
    assert shift.training_requirement_id is None


def test_training_kind_without_requirement_id_is_rejected():
    with pytest.raises(ValidationError):
        ShiftCreate(starts_at="2026-07-13T09:00:00Z", ends_at="2026-07-13T17:00:00Z", kind="training")


def test_work_kind_with_requirement_id_is_rejected():
    with pytest.raises(ValidationError):
        ShiftCreate(
            starts_at="2026-07-13T09:00:00Z", ends_at="2026-07-13T17:00:00Z",
            kind="work", training_requirement_id=REQ_ID,
        )


def test_valid_training_shift():
    shift = ShiftCreate(
        starts_at="2026-07-13T09:00:00Z", ends_at="2026-07-13T17:00:00Z",
        kind="training", training_requirement_id=REQ_ID,
    )
    assert shift.kind == "training"
    assert str(shift.training_requirement_id) == REQ_ID


# ── availability ─────────────────────────────────────────────────────────────

def test_availability_window_end_before_start_is_rejected():
    with pytest.raises(ValidationError):
        AvailabilityWindow(weekday=1, start_time=time(16, 0), end_time=time(8, 0))


def test_availability_window_equal_start_end_is_rejected():
    with pytest.raises(ValidationError):
        AvailabilityWindow(weekday=1, start_time=time(8, 0), end_time=time(8, 0))


def test_availability_replace_rejects_overlap_same_weekday():
    with pytest.raises(ValidationError):
        AvailabilityReplace(windows=[
            AvailabilityWindow(weekday=1, start_time=time(8, 0), end_time=time(13, 0)),
            AvailabilityWindow(weekday=1, start_time=time(12, 0), end_time=time(17, 0)),
        ])


def test_availability_replace_accepts_adjacent_windows():
    replace = AvailabilityReplace(windows=[
        AvailabilityWindow(weekday=1, start_time=time(9, 0), end_time=time(12, 0)),
        AvailabilityWindow(weekday=1, start_time=time(12, 0), end_time=time(17, 0)),
    ])
    assert len(replace.windows) == 2


def test_availability_replace_accepts_empty_list():
    replace = AvailabilityReplace(windows=[])
    assert replace.windows == []


# ── duplicate shift ──────────────────────────────────────────────────────────

def test_duplicate_shift_dedupes_and_sorts_dates():
    dup = DuplicateShift(target_dates=["2026-08-05", "2026-08-03", "2026-08-05"])
    assert dup.target_dates == [date(2026, 8, 3), date(2026, 8, 5)]


def test_duplicate_shift_rejects_empty_dates():
    with pytest.raises(ValidationError):
        DuplicateShift(target_dates=[])


def test_duplicate_shift_rejects_too_many_dates():
    with pytest.raises(ValidationError):
        DuplicateShift(target_dates=[f"2026-08-{d:02d}" for d in range(1, 33)])
