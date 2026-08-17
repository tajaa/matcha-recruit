"""Pure rules for the "scheduling requires a location" feature — the 422
detail bodies `assert_employee_schedulable_at` raises. No DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_location_scope.py -q
"""

from uuid import uuid4

from app.matcha.services.scheduling.schedule_rules import (
    location_mismatch_detail,
    unlocated_employee_detail,
)


class TestUnlocatedEmployeeDetail:
    def test_code_and_shape(self):
        employee_id = uuid4()
        detail = unlocated_employee_detail(employee_id)
        assert detail["code"] == "employee_has_no_location"
        assert detail["employee_id"] == str(employee_id)

    def test_not_forceable(self):
        # Unlike conflict_detail/shift_full_detail/availability_detail, this
        # is missing data, not a judgement call — no ?force=true escape hatch.
        detail = unlocated_employee_detail(uuid4())
        assert "force" not in detail
        assert "code" in detail and detail["code"] != "schedule_conflict"


class TestLocationMismatchDetail:
    def test_carries_both_locations(self):
        employee_id = uuid4()
        employee_loc = uuid4()
        shift_loc = uuid4()
        detail = location_mismatch_detail(employee_id, employee_loc, shift_loc)
        assert detail["code"] == "employee_wrong_location"
        assert detail["employee_id"] == str(employee_id)
        assert detail["employee_location_id"] == str(employee_loc)
        assert detail["shift_location_id"] == str(shift_loc)

    def test_not_forceable(self):
        detail = location_mismatch_detail(uuid4(), uuid4(), uuid4())
        assert "force" not in detail
