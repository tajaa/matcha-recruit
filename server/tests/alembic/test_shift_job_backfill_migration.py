"""empsched20 — the backfill that makes a mandatory job_id survivable.

Requiring job_id on create assumes the tenant has jobs. Every company that has
been scheduling since empsched01 without opening the Jobs tab has none, so the
migration has to mint them from the labels already in the data.
"""

import importlib.util
from pathlib import Path

import pytest


MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "empsched20_backfill_shift_jobs.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("empsched20_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def statements(monkeypatch):
    migration = _load_migration()
    captured: list[str] = []
    monkeypatch.setattr(migration.op, "execute", captured.append)
    return migration, captured


def test_it_chains_onto_the_scheduling_head():
    migration = _load_migration()

    assert migration.revision == "empsched20"
    assert migration.down_revision == "credvis01"


def test_jobs_are_derived_from_both_shifts_and_template_blocks(statements):
    migration, captured = statements

    migration.upgrade()

    inserts = [s for s in captured if "INSERT INTO schedule_jobs" in s]
    assert any("FROM schedule_shifts r" in s for s in inserts)
    assert any("FROM schedule_shift_templates r" in s for s in inserts)


def test_a_label_the_company_already_has_a_job_for_is_not_duplicated(statements):
    # Also what makes the migration re-runnable.
    migration, captured = statements

    migration.upgrade()

    derive = next(s for s in captured if "DISTINCT ON" in s)
    assert "NOT EXISTS" in derive
    assert "lower(j.name) = lower(btrim(r.role))" in derive
    assert "j.location_id IS NULL OR j.location_id = r.location_id" in derive


def test_a_company_that_labels_nothing_still_gets_something_to_pick(statements):
    migration, captured = statements

    migration.upgrade()

    fallback = next(s for s in captured if "'General'" in s)
    # Company-wide (NULL location), so it is available at every location.
    assert "NULL::uuid" in fallback
    assert "NOT EXISTS" in fallback


def test_the_backfill_is_set_based_and_deterministic(statements):
    # A row-by-row loop is ~20k sequential round-trips over the prod tunnel.
    migration, captured = statements

    migration.upgrade()

    plan = next(s for s in captured if "CREATE TEMP TABLE job_backfill_plan" in s)
    assert "JOIN LATERAL" in plan
    # Every LIMIT 1 needs a deterministic ORDER BY, and location-scoped jobs
    # win over company-wide ones — resolve_job_by_name's runtime precedence.
    assert "ORDER BY (j.location_id IS NULL), j.created_at, j.id" in plan
    assert "LIMIT 1" in plan


def test_the_backfill_normalizes_the_label_to_the_job_name(statements):
    # The route now writes the job's name as the role; a backfilled row that
    # kept ' barista ' would contradict its own job from day one.
    migration, captured = statements

    migration.upgrade()

    updates = [s for s in captured if s.strip().startswith("UPDATE")]
    assert len(updates) == 2
    for update in updates:
        assert "SET job_id = p.job_id, role = p.job_name" in update


def test_the_temp_plan_is_dropped_between_the_two_tables(statements):
    # Both passes build a table of the same name inside one transaction.
    migration, captured = statements

    migration.upgrade()

    assert captured.count("DROP TABLE job_backfill_plan") == 2


def test_downgrade_only_removes_jobs_nobody_has_qualified_anyone_on(statements):
    migration, captured = statements

    migration.downgrade()

    assert len(captured) == 1
    delete = captured[0]
    assert migration.DERIVED_NOTE in delete
    assert "schedule_job_employees" in delete
    assert "NOT EXISTS" in delete
