"""Pure tests for the schedule-warning EMS source identity and copy."""

from datetime import date
from uuid import uuid4

from app.matcha.services.scheduling.schedule_warning_events import (
    _warning_label,
    _warning_ref,
)


def test_warning_label_names_the_specific_training_and_due_date():
    assert _warning_label({
        "source": "training",
        "item": "Food handler certification",
        "date": date(2026, 8, 12),
    }) == "Overdue training: Food handler certification (due 2026-08-12)"


def test_warning_label_names_the_specific_credential_and_due_date():
    assert _warning_label({
        "source": "credential",
        "item": "License",
        "date": date(2026, 8, 12),
    }) == "Lapsed credential: License (due 2026-08-12)"


def test_warning_source_changes_when_the_underlying_lapse_changes():
    shift_id = uuid4()
    employee_id = uuid4()
    first = _warning_ref(shift_id, employee_id, {
        "source": "training", "item": "Food handler", "date": date(2026, 8, 12),
    })
    second = _warning_ref(shift_id, employee_id, {
        "source": "training", "item": "Food handler", "date": date(2026, 8, 13),
    })
    assert first != second
