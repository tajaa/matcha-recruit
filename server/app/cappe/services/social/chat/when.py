""""2pm tomorrow" → a time, in the store's own clock — no model involved.

The chat composer's model is told never to compute a date: it copies what
the owner said and suggests a time only when none was given. The owner's own
words are read here first, deterministically, against "now" in the site's
timezone, and whatever is found wins over the model's guess.

`parse` returns a `When` with whichever parts the text gave (a day, a clock
time, or "now"), or None when it names no time at all. Anything ambiguous is
left out rather than guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
# Words for a time of day, when no clock time is given.
_PARTS_OF_DAY = {
    "morning": time(9, 0), "noon": time(12, 0), "midday": time(12, 0), "lunchtime": time(12, 0),
    "afternoon": time(14, 0), "evening": time(18, 0), "tonight": time(19, 0), "midnight": time(0, 0),
}

_NOW = re.compile(r"\b(right now|right away|immediately|asap|straight away|"
                  r"(?:post|share|publish|send|put)(?: (?:it|this|these|them|that|those))?(?: up| out)? now)\b")
_RELATIVE = re.compile(r"\bin (an?|\d+(?:\.\d+)?) ?(minutes?|mins?|hours?|hrs?|days?)\b")
_CLOCK = re.compile(r"\b(?:at |@ ?)?(\d{1,2})(?::(\d{2}))? ?(am|pm|a\.m\.|p\.m\.)(?![a-z])")
_CLOCK_24 = re.compile(r"\b(?:at |@ ?)?([01]?\d|2[0-3]):([0-5]\d)\b")
_AT_HOUR = re.compile(r"\bat (\d{1,2})(?![\d:])(?! ?(?:%|percent|off|items?|posts?|photos?|people|days?))")
_MONTH_DAY = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.? (\d{1,2})(?:st|nd|rd|th)?\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)? (?:of )?(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_WEEKDAY = re.compile(r"\b(next |this |on )?(" + "|".join(sorted(_WEEKDAYS, key=len, reverse=True)) + r")\b")


@dataclass(frozen=True)
class When:
    """What the text said. `now` excludes the rest; otherwise either part may
    be missing (the caller fills it from the model or a default)."""
    now: bool = False
    day: Optional[date] = None
    clock: Optional[time] = None

    @property
    def empty(self) -> bool:
        return not (self.now or self.day or self.clock)


def _hour(hour: int, minute: int, ampm: Optional[str]) -> Optional[time]:
    if minute > 59:
        return None
    if ampm:
        if not 1 <= hour <= 12:
            return None
        pm = ampm.startswith("p")
        hour = (hour % 12) + (12 if pm else 0)
    elif hour > 23:
        return None
    return time(hour, minute)


def _business_hour(hour: int) -> Optional[time]:
    """"at 2" with no am/pm: a shop posts in the daytime, so 1–7 is the
    afternoon and 8–11 the morning. 12 is noon."""
    if hour == 12:
        return time(12, 0)
    if 1 <= hour <= 7:
        return time(hour + 12, 0)
    if 8 <= hour <= 11:
        return time(hour, 0)
    return None


def _clock(text: str) -> Optional[time]:
    m = _CLOCK.search(text)
    if m:
        return _hour(int(m.group(1)), int(m.group(2) or 0), m.group(3).replace(".", ""))
    m = _CLOCK_24.search(text)
    if m:
        return time(int(m.group(1)), int(m.group(2)))
    for word, at in _PARTS_OF_DAY.items():
        if re.search(rf"\b{word}\b", text):
            return at
    m = _AT_HOUR.search(text)
    if m:
        return _business_hour(int(m.group(1)))
    return None


def _future_date(month: int, day: int, today: date, year: Optional[int] = None) -> Optional[date]:
    try:
        if year is not None:
            return date(year if year > 99 else 2000 + year, month, day)
        found = date(today.year, month, day)
        return found if found >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def _day(text: str, today: date, clock: Optional[time], now_clock: time) -> Optional[date]:
    if re.search(r"\b(day after tomorrow)\b", text):
        return today + timedelta(days=2)
    if re.search(r"\b(tomorrow|tmrw|tmr|tomorow)\b", text):
        return today + timedelta(days=1)
    if re.search(r"\b(today|tonight|this (?:morning|afternoon|evening))\b", text):
        return today
    m = _MONTH_DAY.search(text)
    if m:
        return _future_date(_MONTHS[m.group(1)], int(m.group(2)), today)
    m = _DAY_MONTH.search(text)
    if m:
        return _future_date(_MONTHS[m.group(2)], int(m.group(1)), today)
    m = _SLASH_DATE.search(text)
    if m:
        return _future_date(int(m.group(1)), int(m.group(2)), today, int(m.group(3)) if m.group(3) else None)
    m = _WEEKDAY.search(text)
    if m:
        ahead = (_WEEKDAYS[m.group(2)] - today.weekday()) % 7
        # Its own weekday means today while the time is still ahead; "next
        # Friday" said on a Friday is a week out.
        if ahead == 0 and ((m.group(1) or "").strip() == "next" or (clock is not None and clock <= now_clock)):
            ahead = 7
        return today + timedelta(days=ahead)
    return None


def parse(text: str, now_local: datetime) -> Optional[When]:
    """The time the owner's words name, read against `now_local` (the
    store's clock). None when they name none."""
    t = " ".join((text or "").lower().split())
    if not t:
        return None
    m = _RELATIVE.search(t)
    if m:
        amount = 1.0 if m.group(1) in ("a", "an") else float(m.group(1))
        unit = m.group(2)
        delta = (timedelta(days=amount) if unit.startswith("day")
                 else timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount))
        at = (now_local + delta).replace(second=0, microsecond=0)
        return When(day=at.date(), clock=at.time())
    clock = _clock(t)
    day = _day(t, now_local.date(), clock, now_local.time())
    if day is None and clock is None:
        return When(now=True) if _NOW.search(t) else None
    if day is None and clock is not None:
        # A bare time is the next one: today if it hasn't passed.
        day = now_local.date() if clock > now_local.time() else now_local.date() + timedelta(days=1)
    return When(day=day, clock=clock)


__all__ = ["When", "parse"]
