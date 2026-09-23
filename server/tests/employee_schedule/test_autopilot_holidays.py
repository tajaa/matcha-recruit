"""Autopilot's holiday calendar is fixed calendar arithmetic."""

from datetime import date

import pytest

from app.matcha.services.scheduling.autopilot.holidays import (
    holidays_between,
    us_holidays,
)


@pytest.mark.parametrize("day, name", [
    (date(2026, 1, 1), "New Year's Day"),
    (date(2026, 4, 5), "Easter"),
    (date(2026, 5, 10), "Mother's Day"),
    (date(2026, 5, 25), "Memorial Day"),
    (date(2026, 6, 21), "Father's Day"),
    (date(2026, 9, 7), "Labor Day"),
    (date(2026, 11, 26), "Thanksgiving"),
    (date(2026, 11, 27), "Black Friday"),
    (date(2026, 12, 31), "New Year's Eve"),
    (date(2027, 3, 28), "Easter"),
    (date(2027, 11, 25), "Thanksgiving"),
])
def test_known_dates(day, name):
    assert us_holidays(day.year)[day] == name


def test_range_spans_years_and_is_sorted():
    found = holidays_between(date(2026, 12, 20), date(2027, 1, 5))
    assert list(found) == [date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31), date(2027, 1, 1)]
    assert holidays_between(date(2026, 9, 8), date(2026, 9, 30)) == {}
