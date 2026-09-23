"""US holiday calendar facts for Schedule Autopilot.

Calendar dates only — never law, and never a demand modifier. The engine keeps
these days out of what it learns (a Thanksgiving Thursday is not a normal
Thursday, and one would drag a four-observation median) and labels a
target-week holiday so the manager staffs it by hand instead of trusting an
ordinary-day forecast. The list is the days that move restaurant and retail
demand, not the federal-closure list.
"""

from __future__ import annotations

from datetime import date, timedelta


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th `weekday` (Monday=0, as `date.weekday()`) of the month."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """Western (Gregorian) Easter Sunday — the anonymous Gregorian algorithm."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    j = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * j) // 451
    month = (h + j - 7 * m + 114) // 31
    day = (h + j - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def us_holidays(year: int) -> dict[date, str]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    return {
        date(year, 1, 1): "New Year's Day",
        date(year, 2, 14): "Valentine's Day",
        _easter(year): "Easter",
        _nth_weekday(year, 5, 6, 2): "Mother's Day",
        _last_weekday(year, 5, 0): "Memorial Day",
        _nth_weekday(year, 6, 6, 3): "Father's Day",
        date(year, 7, 4): "Independence Day",
        _nth_weekday(year, 9, 0, 1): "Labor Day",
        date(year, 10, 31): "Halloween",
        thanksgiving: "Thanksgiving",
        thanksgiving + timedelta(days=1): "Black Friday",
        date(year, 12, 24): "Christmas Eve",
        date(year, 12, 25): "Christmas Day",
        date(year, 12, 31): "New Year's Eve",
    }


def holidays_between(start: date, end: date) -> dict[date, str]:
    out: dict[date, str] = {}
    for year in range(start.year, end.year + 1):
        out.update({day: name for day, name in us_holidays(year).items() if start <= day <= end})
    return dict(sorted(out.items()))
