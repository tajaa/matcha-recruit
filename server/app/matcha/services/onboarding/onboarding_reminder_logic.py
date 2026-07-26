"""Shared logic for onboarding reminder and escalation rules."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_BUSINESS_DAYS = (0, 1, 2, 3, 4)
DEFAULT_REMINDER_DAYS_BEFORE_DUE = 1
DEFAULT_ESCALATE_TO_MANAGER_DAYS = 3
DEFAULT_ESCALATE_TO_HR_DAYS = 5
DEFAULT_MAX_PER_CYCLE = 200


@dataclass(frozen=True)
class ReminderSettings:
    timezone_name: str = "UTC"
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None
    business_days: tuple[int, ...] = DEFAULT_BUSINESS_DAYS
    reminder_days_before_due: int = DEFAULT_REMINDER_DAYS_BEFORE_DUE
    escalate_to_manager_after_days: int = DEFAULT_ESCALATE_TO_MANAGER_DAYS
    escalate_to_hr_after_days: int = DEFAULT_ESCALATE_TO_HR_DAYS
    hr_escalation_emails: tuple[str, ...] = ()
    email_enabled: bool = True


def _normalize_business_days(raw_days) -> tuple[int, ...]:
    if not raw_days:
        return DEFAULT_BUSINESS_DAYS

    normalized: set[int] = set()
    for day in raw_days:
        try:
            parsed = int(day)
        except (TypeError, ValueError):
            continue
        if 0 <= parsed <= 6:
            normalized.add(parsed)

    if not normalized:
        return DEFAULT_BUSINESS_DAYS
    return tuple(sorted(normalized))


def _coerce_hour(value) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= parsed <= 23:
        return parsed
    return None


def _build_settings(row) -> ReminderSettings:
    if not row:
        return ReminderSettings()

    manager_days = max(int(row["escalate_to_manager_after_days"] or DEFAULT_ESCALATE_TO_MANAGER_DAYS), 1)
    hr_days = max(int(row["escalate_to_hr_after_days"] or DEFAULT_ESCALATE_TO_HR_DAYS), manager_days)
    reminder_days = max(int(row["reminder_days_before_due"] or DEFAULT_REMINDER_DAYS_BEFORE_DUE), 0)

    hr_emails: list[str] = []
    for email in row["hr_escalation_emails"] or []:
        if not email:
            continue
        normalized = str(email).strip().lower()
        if normalized:
            hr_emails.append(normalized)

    return ReminderSettings(
        timezone_name=(row["timezone"] or "UTC").strip() if row["timezone"] else "UTC",
        quiet_hours_start=_coerce_hour(row["quiet_hours_start"]),
        quiet_hours_end=_coerce_hour(row["quiet_hours_end"]),
        business_days=_normalize_business_days(row["business_days"]),
        reminder_days_before_due=reminder_days,
        escalate_to_manager_after_days=manager_days,
        escalate_to_hr_after_days=hr_days,
        hr_escalation_emails=tuple(sorted(set(hr_emails))),
        email_enabled=bool(row["email_enabled"]),
    )


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _is_quiet_hour(local_now: datetime, quiet_hours_start: Optional[int], quiet_hours_end: Optional[int]) -> bool:
    if quiet_hours_start is None or quiet_hours_end is None:
        return False
    if quiet_hours_start == quiet_hours_end:
        return False

    current_hour = local_now.hour
    if quiet_hours_start < quiet_hours_end:
        return quiet_hours_start <= current_hour < quiet_hours_end
    return current_hour >= quiet_hours_start or current_hour < quiet_hours_end


def determine_reminder_tier(
    due_date: date,
    local_today: date,
    settings: ReminderSettings,
) -> Optional[str]:
    if due_date is None:
        return None

    overdue_days = (local_today - due_date).days
    if overdue_days >= settings.escalate_to_hr_after_days:
        return "hr"
    if overdue_days >= settings.escalate_to_manager_after_days:
        return "manager"

    days_until_due = (due_date - local_today).days
    if days_until_due <= settings.reminder_days_before_due:
        return "assignee"

    return None


def _tier_column(tier: str) -> str:
    mapping = {
        "assignee": "assignee_reminded_at",
        "manager": "manager_reminded_at",
        "hr": "hr_reminded_at",
    }
    return mapping[tier]


def _full_name(first_name: Optional[str], last_name: Optional[str], fallback: str) -> str:
    full_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return full_name or fallback


def _pick_employee_email(row) -> Optional[str]:
    personal = (row["employee_personal_email"] or "").strip().lower()
    work = (row["employee_work_email"] or "").strip().lower()
    return personal or work or None


def _pick_manager_email(row) -> Optional[str]:
    work = (row["manager_work_email"] or "").strip().lower()
    personal = (row["manager_personal_email"] or "").strip().lower()
    return work or personal or None


def _resolve_recipients(row, tier: str, hr_emails: tuple[str, ...]) -> list[tuple[str, str]]:
    if tier == "assignee":
        if row["is_employee_task"]:
            employee_email = _pick_employee_email(row)
            if not employee_email:
                return []
            employee_name = _full_name(
                row["employee_first_name"],
                row["employee_last_name"],
                "Employee",
            )
            return [(employee_email, employee_name)]

        manager_email = _pick_manager_email(row)
        manager_name = _full_name(
            row["manager_first_name"],
            row["manager_last_name"],
            "Manager",
        )
        if manager_email:
            return [(manager_email, manager_name)]

        fallback_email = _pick_employee_email(row)
        if not fallback_email:
            return []
        fallback_name = _full_name(
            row["employee_first_name"],
            row["employee_last_name"],
            "Employee",
        )
        return [(fallback_email, fallback_name)]

    if tier == "manager":
        manager_email = _pick_manager_email(row)
        if not manager_email:
            return []
        manager_name = _full_name(
            row["manager_first_name"],
            row["manager_last_name"],
            "Manager",
        )
        return [(manager_email, manager_name)]

    if tier == "hr":
        return [(email, "HR Team") for email in hr_emails if email]

    return []


def _is_business_day(local_now: datetime, business_days: tuple[int, ...]) -> bool:
    return local_now.weekday() in business_days
