"""Assignment-time training/credential-lapse gate (feature: training +
employee_schedule linked, migration `trainsched01`) — pure shaping logic,
no DB.

`shape_lapse_advisories` is the DB-free half of
`_compliance._training_lapse_advisories`: it turns
`schedule_intelligence.fetch_lapse_items` rows into scheduling-compliance
violation dicts. These tests pin the contract the gate depends on: an item
lapses only when strictly before the shift date, the severity is always
advisory (there's no statute behind a training gap the way there is for a
minor-hour cap), and a training-kind shift excludes only the requirement it
itself teaches — not the employee's other lapses.
"""

from datetime import date

from app.matcha.routes.employee_schedule._compliance import shape_lapse_advisories
from app.matcha.services.training_assignment import VALID_SOURCE_TYPES
from app.matcha.routes.employee_lifecycle.training import VALID_RULE_TRIGGERS

SHIFT_DATE = date(2026, 8, 1)
REQ_A = "11111111-1111-1111-1111-111111111111"
REQ_B = "22222222-2222-2222-2222-222222222222"


def _training_item(item_date, requirement_id=REQ_A, title="Forklift Cert"):
    return {"source": "training", "item": title, "date": item_date, "requirement_id": requirement_id}


def _credential_item(item_date, title="License"):
    return {"source": "credential", "item": title, "date": item_date, "requirement_id": None}


# ── date comparison ─────────────────────────────────────────────────────────

def test_item_dated_before_shift_is_an_advisory():
    items = [_training_item(date(2026, 7, 1))]
    out = shape_lapse_advisories(items, shift_date=SHIFT_DATE)
    assert len(out) == 1
    assert out[0]["check"] == "training_lapse"


def test_item_dated_on_or_after_shift_is_dropped():
    for item_date in (SHIFT_DATE, date(2026, 8, 2)):
        out = shape_lapse_advisories([_training_item(item_date)], shift_date=SHIFT_DATE)
        assert out == [], f"item dated {item_date} should not be overdue as of {SHIFT_DATE}"


def test_item_with_no_date_is_dropped():
    out = shape_lapse_advisories(
        [{"source": "training", "item": "x", "date": None, "requirement_id": REQ_A}],
        shift_date=SHIFT_DATE,
    )
    assert out == []


# ── severity ─────────────────────────────────────────────────────────────────

def test_severity_is_always_advisory_never_block():
    items = [_training_item(date(2026, 1, 1)), _credential_item(date(2026, 1, 1))]
    out = shape_lapse_advisories(items, shift_date=SHIFT_DATE)
    assert len(out) == 2
    assert all(v["severity"] == "advisory" for v in out)
    assert all(v["statute"] is None for v in out)


def test_credential_and_training_get_distinct_check_names():
    items = [_training_item(date(2026, 1, 1)), _credential_item(date(2026, 1, 1))]
    out = shape_lapse_advisories(items, shift_date=SHIFT_DATE)
    checks = {v["check"] for v in out}
    assert checks == {"training_lapse", "credential_lapse"}


# ── exclude_requirement_id (training-as-shift) ───────────────────────────────

def test_exclude_requirement_id_suppresses_only_that_training_item():
    items = [
        _training_item(date(2026, 1, 1), requirement_id=REQ_A, title="Forklift Cert"),
        _training_item(date(2026, 1, 1), requirement_id=REQ_B, title="Fire Safety"),
    ]
    out = shape_lapse_advisories(items, shift_date=SHIFT_DATE, exclude_requirement_id=REQ_A)
    assert len(out) == 1
    assert "Fire Safety" in out[0]["message"]


def test_exclude_requirement_id_does_not_suppress_credential_items():
    # Attending the training session doesn't cure a lapsed license — a
    # training-kind shift still warns about credential lapses.
    items = [
        _training_item(date(2026, 1, 1), requirement_id=REQ_A),
        _credential_item(date(2026, 1, 1)),
    ]
    out = shape_lapse_advisories(items, shift_date=SHIFT_DATE, exclude_requirement_id=REQ_A)
    assert len(out) == 1
    assert out[0]["check"] == "credential_lapse"


def test_no_exclude_requirement_id_keeps_all_lapsed_training():
    items = [_training_item(date(2026, 1, 1), requirement_id=REQ_A)]
    out = shape_lapse_advisories(items, shift_date=SHIFT_DATE)
    assert len(out) == 1


# ── vocabulary drift guards ───────────────────────────────────────────────────

def test_schedule_source_type_is_registered():
    assert "schedule" in VALID_SOURCE_TYPES


def test_scheduled_role_trigger_is_registered():
    assert "scheduled_role" in VALID_RULE_TRIGGERS
