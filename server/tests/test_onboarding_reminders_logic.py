from dataclasses import replace
from datetime import date, datetime

from app.matcha.services.onboarding_reminder_logic import (
    DEFAULT_BUSINESS_DAYS,
    ReminderSettings,
    _is_quiet_hour,
    _normalize_business_days,
    _resolve_recipients,
    determine_reminder_tier,
)


def test_determine_tier_returns_assignee_within_reminder_window():
    settings = ReminderSettings()
    assert (
        determine_reminder_tier(
            due_date=date(2026, 2, 20),
            local_today=date(2026, 2, 19),
            settings=settings,
        )
        == "assignee"
    )


def test_determine_tier_returns_manager_when_overdue_at_threshold():
    settings = replace(ReminderSettings(), escalate_to_manager_after_days=3, escalate_to_hr_after_days=5)
    assert (
        determine_reminder_tier(
            due_date=date(2026, 2, 15),
            local_today=date(2026, 2, 18),
            settings=settings,
        )
        == "manager"
    )


def test_determine_tier_returns_hr_when_overdue_past_hr_threshold():
    settings = replace(ReminderSettings(), escalate_to_manager_after_days=3, escalate_to_hr_after_days=5)
    assert (
        determine_reminder_tier(
            due_date=date(2026, 2, 10),
            local_today=date(2026, 2, 18),
            settings=settings,
        )
        == "hr"
    )


def test_quiet_hours_handles_wraparound_windows():
    assert _is_quiet_hour(datetime(2026, 2, 18, 23, 0), 22, 7) is True
    assert _is_quiet_hour(datetime(2026, 2, 18, 6, 0), 22, 7) is True
    assert _is_quiet_hour(datetime(2026, 2, 18, 12, 0), 22, 7) is False


def test_resolve_recipients_prefers_manager_for_non_employee_tasks():
    row = {
        "is_employee_task": False,
        "employee_first_name": "Alex",
        "employee_last_name": "Casey",
        "employee_work_email": "alex@example.com",
        "employee_personal_email": None,
        "manager_first_name": "Mina",
        "manager_last_name": "Lee",
        "manager_work_email": "manager@example.com",
        "manager_personal_email": None,
    }
    assert _resolve_recipients(row, "assignee", ()) == [("manager@example.com", "Mina Lee")]


def test_normalize_business_days_falls_back_to_defaults_for_invalid_values():
    assert _normalize_business_days(["bad", None, 9]) == DEFAULT_BUSINESS_DAYS
