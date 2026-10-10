"""brokerdrop01 removes the broker product's tables and the `broker` role.

Static checks only (no DB): the statements are shaped for this repo's
asyncpg-backed Alembic, the drop list covers every broker table a migration ever
created, and no application code still runs SQL against a dropped table.
"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

SERVER = Path(__file__).parents[2]
VERSIONS = SERVER / "alembic" / "versions"
MIGRATION = VERSIONS / "brokerdrop01_remove_broker_product.py"


def _load():
    spec = importlib.util.spec_from_file_location("brokerdrop01", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_statements(module) -> list[str]:
    recorded: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: recorded.append(str(sql)))
    module.upgrade()
    return recorded


def _outside_dollar_quotes(sql: str) -> str:
    sql = re.sub(r"\$\$.*?\$\$", "", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def test_broker_users_are_deleted_after_the_drops_then_the_role_constraint_loses_broker():
    statements = _upgrade_statements(_load())
    delete_users = statements.index("DELETE FROM users WHERE role = 'broker'")
    last_drop = max(i for i, s in enumerate(statements) if s.startswith("DROP TABLE"))
    # broker_client_setups / broker_company_links reference users with no
    # delete rule, so the users can only go once those tables are gone.
    assert delete_users > last_drop
    assert not any("RAISE EXCEPTION" in s for s in statements)  # no longer refuses to run
    assert statements[-2].strip() == "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"
    assert delete_users == len(statements) - 3
    assert "'broker'" not in statements[-1]
    assert "'individual'" in statements[-1]


def test_the_removed_celery_tasks_scheduler_rows_are_deleted_before_the_drops():
    statements = _upgrade_statements(_load())
    cleanup = next(i for i, s in enumerate(statements) if s.startswith("DELETE FROM scheduler_settings"))
    first_drop = next(i for i, s in enumerate(statements) if s.startswith("DROP TABLE"))
    assert cleanup < first_drop
    assert "'broker_risk_alerts'" in statements[cleanup] and "'broker_milestones'" in statements[cleanup]


def test_every_statement_is_one_statement_without_bind_params():
    for sql in _upgrade_statements(_load()):
        body = _outside_dollar_quotes(sql).strip().rstrip(";")
        assert ";" not in body, f"multiple commands in one execute: {sql!r}"
        assert not text(sql).compile().params, f"bind parameter in: {sql!r}"


def test_drop_list_covers_every_broker_table_a_migration_created():
    module = _load()
    created: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        if path == MIGRATION:
            continue
        src = path.read_text()
        created.update(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?\"?(brokers?(?:_\w+)?)\"?", src))
        created.update(re.findall(r"create_table\(\s*['\"](brokers?(?:_\w+)?)['\"]", src))
    assert created, "expected to find the broker tables created by older migrations"
    missing = created - set(module.BROKER_TABLES)
    assert not missing, f"tables created by migrations but not dropped: {sorted(missing)}"


def test_each_table_is_dropped_exactly_once_with_cascade():
    module = _load()
    assert len(set(module.BROKER_TABLES)) == len(module.BROKER_TABLES)
    drops = [s for s in _upgrade_statements(module) if s.startswith("DROP TABLE")]
    assert drops == [f"DROP TABLE IF EXISTS {t} CASCADE" for t in module.BROKER_TABLES]


def test_no_app_code_still_runs_sql_against_a_dropped_table():
    module = _load()
    names = "|".join(re.escape(t) for t in module.BROKER_TABLES)
    pattern = re.compile(rf"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+({names})\b", re.IGNORECASE)
    offenders = []
    for path in (SERVER / "app").rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.relative_to(SERVER)}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_downgrade_is_refused():
    with pytest.raises(RuntimeError, match="irreversible"):
        _load().downgrade()


def test_chains_off_an_existing_revision():
    module = _load()
    revisions = set()
    for path in VERSIONS.glob("*.py"):
        found = re.search(r"^revision(?:: str)? = ['\"]([^'\"]+)['\"]", path.read_text(), re.MULTILINE)
        if found:
            revisions.add(found.group(1))
    assert module.down_revision in revisions
