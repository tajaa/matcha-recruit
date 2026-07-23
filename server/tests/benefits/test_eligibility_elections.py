"""New-hire-gap suppression predicate — pure, no DB.

Verifies the second enrollment-truth source added to
`detect_eligibility_exceptions`: an approved benefit_elections row (incl. an
approved waive) suppresses the new-hire-gap flag, but only once the roster
row's employee_id has actually been resolved.
"""
from uuid import uuid4

from app.matcha.services.benefits_eligibility import is_addressed_by_election


def test_addressed_employee_is_suppressed():
    emp_id = uuid4()
    assert is_addressed_by_election(emp_id, {emp_id}) is True


def test_unaddressed_employee_is_not_suppressed():
    emp_id = uuid4()
    assert is_addressed_by_election(emp_id, {uuid4()}) is False


def test_empty_addressed_set_never_suppresses():
    # CSV/Finch-only companies with no benefit_elections rows at all — no
    # behavior change from the pre-open-enrollment detector.
    emp_id = uuid4()
    assert is_addressed_by_election(emp_id, set()) is False


def test_unresolved_roster_row_is_never_suppressed():
    # employee_id is None when the roster's email never matched an employees
    # row — this must keep flagging regardless of what's in addressed_ids.
    assert is_addressed_by_election(None, {uuid4()}) is False
