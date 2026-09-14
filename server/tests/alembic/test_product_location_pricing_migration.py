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


def test_migration_preserves_explicit_postgres_constraint_names(monkeypatch):
    migration = _load_migration()
    finalized_names = []
    dropped_names = []
    created_names = []

    def finalize(name):
        finalized_names.append(name)
        return f"final:{name}"

    class Result:
        @staticmethod
        def scalar():
            return False

    class Bind:
        @staticmethod
        def execute(_statement):
            return Result()

    monkeypatch.setattr(migration.op, "f", finalize)
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda name, *_args, **_kwargs: dropped_names.append(name),
    )
    monkeypatch.setattr(
        migration.op,
        "create_check_constraint",
        lambda name, *_args, **_kwargs: created_names.append(name),
    )
    monkeypatch.setattr(migration.op, "add_column", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(migration.op, "drop_column", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(migration.op, "get_bind", Bind)

    migration.upgrade()
    migration.downgrade()

    pricing_name = "product_definitions_pricing_model_check"
    location_name = "company_handbook_profiles_custom_product_location_count_check"
    assert finalized_names == [
        pricing_name,
        pricing_name,
        location_name,
        location_name,
        pricing_name,
        pricing_name,
    ]
    assert dropped_names == [
        f"final:{pricing_name}",
        f"final:{location_name}",
        f"final:{pricing_name}",
    ]
    assert created_names == [
        f"final:{pricing_name}",
        f"final:{location_name}",
        f"final:{pricing_name}",
    ]
