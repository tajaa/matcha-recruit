import importlib.util
from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "aiusage03_openai_cache_write_costs.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("aiusage03_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_preserves_luna_cost_history(monkeypatch):
    migration = _load_migration()
    statements = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert len(statements) == 1
    assert "DROP COLUMN IF EXISTS cache_write_tokens" in statements[0]
    assert "cost_usd" not in statements[0]
