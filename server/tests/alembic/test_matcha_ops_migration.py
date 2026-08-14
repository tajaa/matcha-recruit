from pathlib import Path


MIGRATION = Path(__file__).parents[2] / "alembic" / "versions" / "matchaops01_channel_scopes.py"


def test_matcha_ops_migration_declares_cross_branch_dependencies():
    source = MIGRATION.read_text()
    assert '"inventory01"' in source
    assert '"proddef01"' in source
    assert '"v2w3x4y5z6a"' in source
    assert '"feataudit01"' in source


def test_product_backfill_checks_boolean_child_values():
    source = MIGRATION.read_text()
    assert "COALESCE((features->>'ems')::boolean, false)" in source
    assert "COALESCE((preconfigured_features->>'inventory')::boolean, false)" in source
    assert "?| ARRAY" not in source
    assert "WITH changed AS" in source
