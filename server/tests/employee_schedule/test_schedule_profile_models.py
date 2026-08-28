"""Validation contracts for employee scheduling inputs."""
from datetime import time

import pytest
from pydantic import ValidationError

from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityReplace, AvailabilityWindow, EmployeeJobAssignmentInput,
    EmployeeJobsReplace, EmployeeScheduleProfileUpdate,
)
from app.matcha.services.scheduling.schedule_profiles import effective_availability_state

JOB_A = "11111111-1111-1111-1111-111111111111"
JOB_B = "22222222-2222-2222-2222-222222222222"
WINDOW = AvailabilityWindow(weekday=1, start_time=time(9), end_time=time(17))


def test_rejects_two_primary_jobs():
    with pytest.raises(ValidationError, match="only one primary"):
        EmployeeJobsReplace(assignments=[
            EmployeeJobAssignmentInput(job_id=JOB_A, is_primary=True),
            EmployeeJobAssignmentInput(job_id=JOB_B, is_primary=True),
        ])


def test_rejects_duplicate_job_ids():
    with pytest.raises(ValidationError, match="must be unique"):
        EmployeeJobsReplace(assignments=[
            EmployeeJobAssignmentInput(job_id=JOB_A),
            EmployeeJobAssignmentInput(job_id=JOB_A),
        ])


def test_rejects_inverted_qualification_dates():
    with pytest.raises(ValidationError, match="qualified_until"):
        EmployeeJobAssignmentInput(
            job_id=JOB_A, qualified_from="2026-09-01", qualified_until="2026-08-01",
        )


@pytest.mark.parametrize("values", [
    {"min_weekly_minutes": 1200, "target_weekly_minutes": 600},
    {"target_weekly_minutes": 1800, "max_weekly_minutes": 1200},
    {"min_weekly_minutes": 1800, "max_weekly_minutes": 1200},
])
def test_rejects_inverted_weekly_hour_targets(values):
    with pytest.raises(ValidationError):
        EmployeeScheduleProfileUpdate(**values)


def test_old_client_availability_state_is_derived():
    assert effective_availability_state(None, []) == "always_available"
    assert effective_availability_state(None, [WINDOW]) == "windows"


def test_windows_state_requires_a_window():
    with pytest.raises(ValidationError, match="requires at least one"):
        AvailabilityReplace(availability_state="windows", windows=[])


def test_always_available_rejects_windows():
    with pytest.raises(ValidationError, match="cannot include"):
        AvailabilityReplace(availability_state="always_available", windows=[WINDOW])
