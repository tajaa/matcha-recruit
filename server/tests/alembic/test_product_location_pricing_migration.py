import importlib.util
from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "prodloc01_per_location_pricing.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("prodloc01_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_declares_both_cross_branch_table_dependencies():
    migration = _load_migration()

    assert migration.depends_on == ("proddef01", "l7m8n9o0p1q2")
