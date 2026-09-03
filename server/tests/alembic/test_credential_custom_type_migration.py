import importlib.util
from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "credcustom01_tenant_credential_types.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("credcustom01_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_keeps_tenant_metadata_out_of_legacy_catalog(monkeypatch):
    migration = _load_migration()
    statements = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    sql = "\n".join(statements)
    assert "CREATE TABLE IF NOT EXISTS company_credential_types" in sql
    assert "CREATE OR REPLACE VIEW scoped_credential_types" in sql
    assert "COALESCE(cct.label, ct.label) AS label" in sql
    assert "ALTER TABLE credential_types" not in sql
    assert sql.count("EXECUTE FUNCTION enforce_credential_type_company_scope()") == 4


def test_downgrade_refuses_to_globalize_existing_tenant_types(monkeypatch):
    migration = _load_migration()
    statements = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert "IF EXISTS (SELECT 1 FROM company_credential_types)" in statements[0]
    assert "RAISE EXCEPTION" in statements[0]
    assert statements[-1] == "DROP TABLE IF EXISTS company_credential_types"
