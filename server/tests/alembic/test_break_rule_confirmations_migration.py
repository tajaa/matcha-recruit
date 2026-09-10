"""Compatibility guarantees for empsched23 break-rule decisions."""

import importlib.util
import inspect
from pathlib import Path
from uuid import uuid4

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/empsched23_break_rule_confirmations.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("empsched23_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_grandfathering_is_scoped_and_does_not_fabricate_confirmation():
    migration = _migration_module()
    company_id = uuid4()
    location_id = uuid4()
    generic_rule_id = uuid4()
    retail_rule_id = uuid4()
    future_rule_id = uuid4()
    candidates = [
        {
            "company_id": company_id,
            "location_id": location_id,
            "rule_set_id": retail_rule_id,
            "naics": None,
            "company_industry": "Retail",
            "rule_industry_code": "retail",
        },
        {
            "company_id": company_id,
            "location_id": location_id,
            "rule_set_id": generic_rule_id,
            "naics": None,
            "company_industry": "Retail",
            "rule_industry_code": None,
        },
        # A future-effective approved row is also grandfathered; runtime decides
        # which row to select from the shift date.
        {
            "company_id": company_id,
            "location_id": location_id,
            "rule_set_id": future_rule_id,
            "naics": None,
            "company_industry": "Retail",
            "rule_industry_code": "retail",
        },
        # Duplicate ancestor traversal cannot mint a duplicate compatibility row.
        {
            "company_id": company_id,
            "location_id": location_id,
            "rule_set_id": future_rule_id,
            "naics": None,
            "company_industry": "Retail",
            "rule_industry_code": "retail",
        },
        {
            "company_id": company_id,
            "location_id": location_id,
            "rule_set_id": uuid4(),
            "naics": None,
            "company_industry": "Retail",
            "rule_industry_code": "healthcare",
        },
    ]

    rows = migration._grandfathered_rows(candidates, lambda raw: raw.lower())

    assert {row["rule_set_id"] for row in rows} == {
        retail_rule_id, generic_rule_id, future_rule_id,
    }
    assert all(set(row) == {"company_id", "location_id", "rule_set_id"} for row in rows)

    source = inspect.getsource(migration.upgrade)
    assert "'grandfathered'" in source
    assert "CURRENT_DATE" not in source
    assert "confirmed_by" not in source[source.index("if rows:"):]


def test_migration_schema_separates_compatibility_from_tenant_decisions():
    migration = _migration_module()
    source = inspect.getsource(migration.upgrade)

    assert "decision IN ('confirmed', 'rejected', 'grandfathered')" in source
    assert "decision = 'grandfathered' AND context_hash IS NULL AND confirmed_by IS NULL" in source
    assert "decision IN ('confirmed', 'rejected')" in source
    assert "context_hash IS NOT NULL AND confirmed_by IS NOT NULL" in source
    assert "company_schedule_break_rule_confirmations_grandfathered" in source
