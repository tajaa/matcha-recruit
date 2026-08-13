"""Pure tests for Cappe natural-language booking suggestion rules."""
from datetime import date, time
from uuid import UUID

from app.cappe.services.booking_suggestions import (
    BookingPreference,
    BookingAvailabilityWindow,
    ResolvedBookingWindow,
    coerce_booking_preference,
    rank_booking_suggestions,
    resolve_booking_windows,
    resolve_staff_preferences,
)


def test_coerce_booking_preference_bounds_count_and_normalizes_values():
    pref = coerce_booking_preference({
        "staff_names": [" Maria ", "maria", "Jade"],
        "windows": [{"weekday": "Tuesday", "start_time": "09:00", "end_time": "12:00"}],
        "requested_count": 99,
    })
    assert pref is not None
    assert pref.staff_names == ("Maria", "Jade")
    assert pref.requested_count == 3
    assert pref.windows[0].weekday == 1


def test_coerce_booking_preference_rejects_malformed_windows():
    assert coerce_booking_preference({"staff_names": [], "windows": [{"start_time": "bad"}]}) is None
    assert coerce_booking_preference({"staff_names": [], "windows": [{"start_time": "14:00", "end_time": "09:00"}]}) is None


def test_resolve_windows_uses_next_occurrence_for_weekday():
    pref = BookingPreference(
        staff_names=(),
        windows=(BookingAvailabilityWindow(weekday=1, relative_week=None, explicit_date=None, start_time=None, end_time=None),),
        requested_count=1,
    )
    resolved = resolve_booking_windows(pref, today=date(2026, 8, 13))  # Thursday
    assert resolved[0].start_date == date(2026, 8, 18)
    assert resolved[0].end_date == date(2026, 8, 18)


def test_resolve_windows_handles_this_week_and_next_week():
    pref = BookingPreference(
        staff_names=(),
        windows=(
            BookingAvailabilityWindow(None, "this_week", None, None, None),
            BookingAvailabilityWindow(None, "next_week", None, None, None),
        ),
        requested_count=1,
    )
    resolved = resolve_booking_windows(pref, today=date(2026, 8, 13))
    assert resolved[0].start_date == date(2026, 8, 10)
    assert resolved[0].end_date == date(2026, 8, 16)
    assert resolved[1].start_date == date(2026, 8, 17)
    assert resolved[1].end_date == date(2026, 8, 23)


def test_resolve_staff_preferences_is_case_insensitive_and_fail_closed():
    staff = [
        {"id": UUID("11111111-1111-1111-1111-111111111111"), "name": "Maria"},
        {"id": UUID("22222222-2222-2222-2222-222222222222"), "name": "Jade"},
    ]
    ids, unmatched = resolve_staff_preferences(staff, ["mArIa", "Unknown"])
    assert ids == [staff[0]["id"]]
    assert unmatched == ["Unknown"]


def test_resolve_staff_preferences_accepts_unique_first_name():
    staff = [
        {"id": UUID("11111111-1111-1111-1111-111111111111"), "name": "Maria Alvarez"},
        {"id": UUID("22222222-2222-2222-2222-222222222222"), "name": "Jade Chen"},
    ]
    ids, unmatched = resolve_staff_preferences(staff, ["Maria", "Jade"])
    assert ids == [staff[0]["id"], staff[1]["id"]]
    assert unmatched == []


def test_resolve_staff_preferences_rejects_ambiguous_first_name():
    staff = [
        {"id": UUID("11111111-1111-1111-1111-111111111111"), "name": "Maria Alvarez"},
        {"id": UUID("22222222-2222-2222-2222-222222222222"), "name": "Maria Chen"},
    ]
    ids, unmatched = resolve_staff_preferences(staff, ["Maria"])
    assert ids == []
    assert unmatched == ["Maria"]


def test_rank_prefers_named_staff_and_fits_window():
    maria = UUID("11111111-1111-1111-1111-111111111111")
    jade = UUID("22222222-2222-2222-2222-222222222222")
    slots = [
        {
            "start": "2026-08-18T10:00:00",
            "end": "2026-08-18T11:00:00",
            "date": "2026-08-18",
            "day_label": "Tue Aug 18",
            "time_label": "10:00 AM",
            "price_cents": 5000,
            "available_staff_ids": [str(jade), str(maria)],
        },
        {
            "start": "2026-08-18T12:00:00",
            "end": "2026-08-18T13:00:00",
            "date": "2026-08-18",
            "day_label": "Tue Aug 18",
            "time_label": "12:00 PM",
            "price_cents": 5000,
            "available_staff_ids": [str(jade)],
        },
    ]
    options = rank_booking_suggestions(
        slots,
        staff=[{"id": maria, "name": "Maria"}, {"id": jade, "name": "Jade"}],
        preferred_staff_ids=[maria, jade],
        resolved_windows=[
            ResolvedBookingWindow(
                start_date=date(2026, 8, 18), end_date=date(2026, 8, 18),
                start_time=time(9), end_time=time(12),
            )
        ],
        requested_count=3,
    )
    assert len(options) == 1
    assert options[0]["staff_id"] == maria


def test_rank_returns_at_most_three_options():
    slots = [
        {"start": f"2026-08-1{i}T10:00:00", "end": f"2026-08-1{i}T11:00:00", "date": f"2026-08-1{i}", "day_label": "day", "time_label": "10:00 AM", "price_cents": 0, "available_staff_ids": []}
        for i in range(0, 5)
    ]
    options = rank_booking_suggestions(
        slots, staff=[], preferred_staff_ids=[], resolved_windows=[], requested_count=99,
    )
    assert len(options) == 3
