"""The downloadable roster templates."""

import csv
import io

from app.matcha.routes.employees.bulk_upload import bulk_upload_template_csv
from app.matcha.services.employees.roster_csv import is_valid_email

RESERVED = ("@example.com", "@example.org", "@example.net", ".test", ".invalid")


def _rows(variant):
    return list(csv.DictReader(io.StringIO(bulk_upload_template_csv(variant))))


def test_scheduling_template_is_the_short_roster_with_a_store_column():
    rows = _rows("scheduling")
    assert list(rows[0]) == [
        "email", "first_name", "last_name", "job_title", "location", "work_state",
        "phone", "employment_type", "pay_classification", "pay_rate",
    ]
    # pay_rate is refused without pay_classification, so the example has both.
    assert all(row["pay_classification"] and row["pay_rate"] for row in rows)
    assert all(row["location"] for row in rows)


def test_full_template_keeps_every_column_and_gains_location():
    row = _rows("full")[0]
    assert {"license_type", "npi_number", "health_clearances", "location"} <= set(row)
    assert _rows("anything-else")[0].keys() == row.keys()


def test_template_emails_are_reserved_non_deliverable_addresses():
    # A template row gets uploaded verbatim by someone trying it out. A real
    # domain here is how a bounce-storm starts.
    for variant in ("full", "scheduling"):
        for row in _rows(variant):
            for column in ("email", "personal_email", "manager_email"):
                value = row.get(column)
                if value:
                    assert is_valid_email(value)
                    assert value.endswith(RESERVED), value
