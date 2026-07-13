"""Pure scheduling rules — the decisions the routes make, without a DB.

Each test here pins a bug the first cut of the feature actually shipped (the
review of PR #36): an offboarded employee staying assignable, COALESCE swallowing
an intentional null, the week grid disagreeing with what publish-week publishes,
and the two forceable 409s the frontend keys on by `code`.
"""

import ast
from datetime import date, datetime, time, timezone
from pathlib import Path
from uuid import uuid4

from app.matcha.services.schedule_rules import (
    INACTIVE_EMPLOYMENT_STATUSES,
    build_patch,
    conflict_detail,
    shift_full_detail,
    summarize_shifts,
    sunday_indexed_weekday,
    template_windows,
    week_bounds,
)


# ── who can be scheduled ────────────────────────────────────────────────────

_CRUD = Path(__file__).resolve().parents[2] / "app/matcha/routes/employees/crud.py"


def _employment_status_vocabulary() -> set[str]:
    """VALID_EMPLOYMENT_STATUSES straight from the employees module's source.

    Read rather than imported: importing anything under routes/ pulls in the
    whole app (and its env). The point is to catch drift between the two lists,
    so the value has to come from the real definition, not a copy.
    """
    tree = ast.parse(_CRUD.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "VALID_EMPLOYMENT_STATUSES"
            for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError(f"VALID_EMPLOYMENT_STATUSES not found in {_CRUD}")


def test_inactive_statuses_are_real_employment_statuses():
    # The first cut filtered on 'inactive' — a value nothing writes — so
    # offboarded people stayed in the assignment picker. Every status we exclude
    # must exist in the vocabulary the employees module actually stores.
    unknown = set(INACTIVE_EMPLOYMENT_STATUSES) - _employment_status_vocabulary()
    assert unknown == set(), f"filtering on statuses nobody writes: {unknown}"


def test_offboarded_and_terminated_are_both_excluded():
    assert "offboarded" in INACTIVE_EMPLOYMENT_STATUSES
    assert "terminated" in INACTIVE_EMPLOYMENT_STATUSES


def test_working_statuses_stay_schedulable():
    for status in ("active", "on_leave", "suspended", "on_notice", "furloughed"):
        assert status not in INACTIVE_EMPLOYMENT_STATUSES


# ── week bounds + summary ───────────────────────────────────────────────────

def test_week_bounds_is_seven_utc_days():
    lo, hi = week_bounds(date(2026, 7, 12))
    assert lo == datetime(2026, 7, 12, tzinfo=timezone.utc)
    assert hi == datetime(2026, 7, 19, tzinfo=timezone.utc)


def _shift(status="draft", assigned=0, required=1):
    return {
        "status": status,
        "required_staff": required,
        "assignments": [{"employee_id": str(uuid4())} for _ in range(assigned)],
    }


def test_summarize_counts_by_status_and_staffing():
    s = summarize_shifts([
        _shift("published", assigned=2, required=2),
        _shift("draft", assigned=0, required=1),
        _shift("draft", assigned=1, required=3),
        _shift("cancelled", assigned=0, required=5),
    ])
    assert s["total_shifts"] == 4
    assert s["published"] == 1
    assert s["draft"] == 2
    assert s["assigned"] == 3
    # cancelled is never "open" — nobody needs to staff a dead shift
    assert s["open_shifts"] == 2


def test_summarize_empty_week():
    assert summarize_shifts([]) == {
        "total_shifts": 0, "published": 0, "draft": 0, "open_shifts": 0, "assigned": 0,
    }


# ── template materialization ────────────────────────────────────────────────

def test_sunday_indexed_weekday():
    assert sunday_indexed_weekday(date(2026, 7, 12)) == 0   # Sunday
    assert sunday_indexed_weekday(date(2026, 7, 13)) == 1   # Monday
    assert sunday_indexed_weekday(date(2026, 7, 18)) == 6   # Saturday


def test_template_windows_only_matching_weekdays():
    starts, ends = template_windows(
        date(2026, 7, 12), date(2026, 7, 18), {1, 3},   # Mon + Wed
        time(9, 0), time(17, 0),
    )
    assert [s.date() for s in starts] == [date(2026, 7, 13), date(2026, 7, 15)]
    assert all(s.hour == 9 and e.hour == 17 for s, e in zip(starts, ends))
    assert all(s.tzinfo == timezone.utc for s in starts)


def test_template_windows_overnight_rolls_to_next_day():
    starts, ends = template_windows(
        date(2026, 7, 13), date(2026, 7, 13), {1},
        time(22, 0), time(6, 0),            # 10pm → 6am
    )
    assert starts[0] == datetime(2026, 7, 13, 22, tzinfo=timezone.utc)
    assert ends[0] == datetime(2026, 7, 14, 6, tzinfo=timezone.utc)
    assert ends[0] > starts[0]


def test_template_windows_no_matching_days():
    starts, ends = template_windows(
        date(2026, 7, 13), date(2026, 7, 17), {0},   # Sunday only, Mon–Fri range
        time(9, 0), time(17, 0),
    )
    assert (starts, ends) == ([], [])


# ── PATCH builder ───────────────────────────────────────────────────────────

def test_build_patch_writes_only_sent_fields():
    sql, params = build_patch({"role": "Nurse", "notes": "x"}, first_param=3)
    assert sql == "role = $3, notes = $4"
    assert params == ["Nurse", "x"]


def test_build_patch_explicit_null_clears_the_column():
    # The COALESCE form this replaced could not express "clear it": an unsent
    # field and an explicit null both left the old value in place.
    sql, params = build_patch({"location_id": None}, first_param=3)
    assert sql == "location_id = $3"
    assert params == [None]


def test_build_patch_applies_casts():
    sql, params = build_patch(
        {"name": "Late", "days_of_week": "[1,2]"},
        first_param=3, casts={"days_of_week": "jsonb"},
    )
    assert sql == "name = $3, days_of_week = $4::jsonb"
    assert params == ["Late", "[1,2]"]


def test_build_patch_numbering_survives_a_new_column():
    # The spliced clause this replaced hardcoded $10; adding a column above it
    # silently rebound that parameter to a different value.
    sql, params = build_patch(
        {"a": 1, "b": 2, "c": 3, "published_at": None}, first_param=3,
    )
    assert sql.endswith("published_at = $6")
    assert len(params) == 4


def test_build_patch_empty():
    assert build_patch({}, first_param=3) == ("", [])


# ── forceable 409 shapes (the frontend keys on `code`) ───────────────────────

def test_conflict_detail_shape():
    employee_id = uuid4()
    detail = conflict_detail(employee_id, [{"shift_id": "s1"}])
    assert detail["code"] == "schedule_conflict"
    assert detail["employee_id"] == str(employee_id)
    assert detail["conflicts"] == [{"shift_id": "s1"}]


def test_shift_full_detail_shape():
    detail = shift_full_detail(2, 2)
    assert detail["code"] == "shift_full"
    assert detail["assigned"] == 2 and detail["required_staff"] == 2
    assert "2 of 2" in detail["message"]
