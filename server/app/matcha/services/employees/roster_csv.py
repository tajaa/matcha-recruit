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
    optional_columns: Sequence[str] = (),
) -> list[tuple[dict[str, str], int]]:
    """Read a fixed-header CSV into `(row_dict, source_line)` pairs.

    All-or-nothing: the first problem raises, because the caller is a wizard
    that imports the whole file inside one transaction or not at all.

    `optional_columns` may follow the required ones, in order. A file can leave
    them out entirely (the header a customer exported last month still works)
    or leave their cells blank; an absent or blank cell comes back as "".
    """
    rows = read_rows(text)
    if not rows:
        raise RosterCsvError("CSV is empty")
    header = [value.lower() for value in rows[0].values]
    required = list(columns)
    optional = list(optional_columns)
    present_optional = header[len(required):]
    if header[: len(required)] != required or present_optional != optional[: len(present_optional)]:
        expected = ",".join(required)
        if optional:
            expected += " (optional: " + ",".join(optional) + ")"
        raise RosterCsvError("Expected header: " + expected)
    if len(rows) == 1:
        raise RosterCsvError("CSV must contain at least one data row")
    if len(rows) - 1 > max_rows:
        raise RosterCsvError(f"CSV cannot contain more than {max_rows} data rows")

    parsed: list[tuple[dict[str, str], int]] = []
    for row in rows[1:]:
        values = row.values
        # A row may stop before its optional cells (spreadsheets drop trailing
        # empty ones), but never run past the header or skip a required value.
        if (
            not len(required) <= len(values) <= len(header)
            or not all(values[: len(required)])
        ):
            raise RosterCsvError(
                f"Row {row.line} must contain all {len(required)} values"
            )
        record = dict(zip(required, values))
        for index, name in enumerate(optional):
            position = len(required) + index
            record[name] = values[position] if position < len(values) else ""
        parsed.append((record, row.line))
    return parsed


def require_unique(keys: Iterable[tuple[str, int]], message: str) -> None:
    """Raise on the first repeated key, naming the line that repeats it."""
    seen: set[str] = set()
    for key, line in keys:
        if key in seen:
            raise RosterCsvError(f"Row {line} {message}")
        seen.add(key)


def decode_csv_bytes(payload: bytes) -> str:
    """Decode an uploaded CSV, dropping the byte-order mark Excel prepends.

    Excel's "CSV UTF-8" export starts with a BOM. Read as plain utf-8 it stays
    glued to the first header, which then is not `email` and the whole file is
    refused for a missing column the customer can plainly see.
    """
    return payload.decode("utf-8-sig")


def normalize_header(fieldnames: Iterable[str | None] | None) -> list[str]:
    """Header names as the importers compare them: trimmed and lower-case."""
    return [(name or "").strip().lower() for name in (fieldnames or [])]


class StoreDirectory:
    """Resolves a roster row to the store (business location) it works at.

    The schedule roster lists only employees with a store, so an import that
    leaves the store off produces people nobody can schedule. A row names its
    store in a `location` column; a row that names none is placed at the
    company's only real store when there is exactly one and nothing on the row
    says the person works somewhere else.

    Pure: built from already-fetched rows (`id`, `name`, `address`, `city`,
    `state`), so both the route and its tests can use it without a database.
    """

    def __init__(self, stores: Iterable[dict]):
        self._by_name: dict[str, list[dict]] = {}
        self._names: list[str] = []
        real: list[dict] = []
        for store in stores:
            name = (store.get("name") or "").strip()
            if name:
                self._by_name.setdefault(normalize_key(name), []).append(store)
                self._names.append(name)
            # An address-less row is a jurisdiction stub derived from an
            # employee's work state, not somewhere a shift can happen.
            if (store.get("address") or "").strip():
                real.append(store)
        self._only_store = real[0] if len(real) == 1 else None

    @staticmethod
    def _covers(store: dict, work_state: str | None, work_city: str | None) -> bool:
        if work_state and (store.get("state") or "").upper() != work_state.upper():
            return False
        if work_city and normalize_key(store.get("city") or "") != normalize_key(work_city):
            return False
        return True

    def resolve(
        self,
        *,
        location_name: str | None,
        work_state: str | None,
        work_city: str | None,
    ) -> tuple[object | None, bool, str | None]:
        """`(store_id, store_covers_work_location, error)` for one row.

        `store_covers_work_location` is True when the store is in the row's own
        work state/city (or the row gives none) — the caller can then skip
        deriving a separate compliance location for the same place.
        """
        name = (location_name or "").strip()
        if not name:
            store = self._only_store
            if store is None or not self._covers(store, work_state, work_city):
                return None, False, None
            return store["id"], True, None

        matches = self._by_name.get(normalize_key(name), [])
        if not matches:
            known = ", ".join(sorted(set(self._names), key=str.casefold))
            hint = f" Use one of: {known}." if known else " Add the store first, then upload again."
            return None, False, f"Location '{name}' doesn't match any store.{hint}"
        if len(matches) > 1:
            return None, False, (
                f"More than one store is named '{name}'. Rename one so the row can be assigned."
            )
        store = matches[0]
        return store["id"], self._covers(store, work_state, work_city), None
