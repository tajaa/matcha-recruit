"""Field rules and strict CSV reading shared by every roster import path.

Two importers write employees from a spreadsheet — `routes/employees/
bulk_upload.py` (partial success, per-row errors, optional invitations) and the
Matcha S&C setup wizard (all-or-nothing, nothing created until the manager
approves the review). Their *transaction* semantics differ on purpose; the
field rules must not. Email shape, work-state normalization and "which line of
the file was that" live here so there is one answer per question.

Everything in this module is pure: no DB, no FastAPI, no I/O.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Sequence

from app.core.us_states import US_STATE_CODES
from app.matcha.services.employees.us_states import STATE_NAME_TO_CODE

# Accepted on every roster import path. Deliberately looser than RFC 5322 and
# deliberately stricter than "has an @": it is a typo guard, and the model's
# EmailStr (or the email service) is the real gate.
EMAIL_PATTERN = re.compile(r"^[\w\.\-\+]+@[\w\.-]+\.\w+$")

ZIPCODE_PATTERN = re.compile(r"^\d{5}(?:-\d{4})?$")


class RosterCsvError(ValueError):
    """A CSV the user must fix before anything can be imported."""


def is_valid_email(value: str | None) -> bool:
    return bool(EMAIL_PATTERN.match((value or "").strip()))


def normalize_work_state(raw: str | None) -> tuple[str | None, bool]:
    """Normalize a `work_state` value to a 2-letter USPS code.

    Returns `(normalized_code_or_None, is_valid)`. Blank/None input is valid
    (no work location provided — counted separately by callers, e.g. as
    `rows_missing_work_location` in bulk upload). A non-blank value that
    isn't a recognized state/territory abbreviation or full name is invalid.
    """
    value = (raw or "").strip()
    if not value:
        return None, True
    if len(value) == 2 and value.isalpha() and value.upper() in US_STATE_CODES:
        return value.upper(), True
    mapped = STATE_NAME_TO_CODE.get(value.lower())
    if mapped:
        return mapped, True
    return None, False


def normalize_key(value: str) -> str:
    """The comparison form used for duplicate detection across importers."""
    return " ".join((value or "").strip().casefold().split())


class SourceRow:
    """A record plus the 1-based line of the file it started on."""

    __slots__ = ("line", "values")

    def __init__(self, values: list[str], line: int):
        self.values = values
        self.line = line


def read_rows(text: str) -> list[SourceRow]:
    """Parse CSV text into non-blank records carrying their real source line.

    Blank lines are skipped, so a record's index is not its line number — an
    error message that says "Row 2" has to mean the second line of the user's
    file. `csv.reader.line_num` counts physical lines, which also keeps a
    quoted value containing a newline from shifting every later row.
    """
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff"), newline=""))
    rows: list[SourceRow] = []
    previous_line = 0
    try:
        for values in reader:
            start_line = previous_line + 1
            previous_line = reader.line_num
            stripped = [value.strip() for value in values]
            if any(stripped):
                rows.append(SourceRow(stripped, start_line))
    except csv.Error as exc:
        raise RosterCsvError(f"CSV could not be read: {exc}") from exc
    return rows


def parse_table(
    text: str,
    columns: Sequence[str],
    *,
    max_rows: int,
) -> list[tuple[dict[str, str], int]]:
    """Read a fixed-header CSV into `(row_dict, source_line)` pairs.

    All-or-nothing: the first problem raises, because the caller is a wizard
    that imports the whole file inside one transaction or not at all.
    """
    rows = read_rows(text)
    if not rows:
        raise RosterCsvError("CSV is empty")
    header = [value.lower() for value in rows[0].values]
    if header != list(columns):
        raise RosterCsvError("Expected header: " + ",".join(columns))
    if len(rows) == 1:
        raise RosterCsvError("CSV must contain at least one data row")
    if len(rows) - 1 > max_rows:
        raise RosterCsvError(f"CSV cannot contain more than {max_rows} data rows")

    parsed: list[tuple[dict[str, str], int]] = []
    for row in rows[1:]:
        if len(row.values) != len(columns) or not all(row.values):
            raise RosterCsvError(
                f"Row {row.line} must contain all {len(columns)} values"
            )
        parsed.append((dict(zip(columns, row.values)), row.line))
    return parsed


def require_unique(keys: Iterable[tuple[str, int]], message: str) -> None:
    """Raise on the first repeated key, naming the line that repeats it."""
    seen: set[str] = set()
    for key, line in keys:
        if key in seen:
            raise RosterCsvError(f"Row {line} {message}")
        seen.add(key)
