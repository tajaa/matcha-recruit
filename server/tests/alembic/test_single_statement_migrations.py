"""Migrations must survive this repo's asyncpg-backed Alembic.

Two failure classes only show up when a migration is actually applied, and
both reached `migrate-dev.sh` before anything caught them:

- asyncpg prepares every statement, so one `op.execute` holding two commands
  fails with "cannot insert multiple commands into a prepared statement"
  (`autopilot02` chained DO blocks with `;`).
- `op.execute` wraps the string in `sqlalchemy.text()`, which reads `:name`
  as a bind parameter, so a JSON literal like `'{"k":true}'` fails with
  "A value is required for bind parameter 'true'" (`zzzzcappe34`).

Each listed migration is run against a recording `op`, and every statement is
checked for both.
"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"
MIGRATIONS = (
    "autopilot01_location_weather.py",
    "autopilot02_autopilot_mode.py",
    "zzzzcappe34_shopper_subscriptions.py",
)


def _statements(filename: str, direction: str) -> list[str]:
    spec = importlib.util.spec_from_file_location(filename[:-3], VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorded: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: recorded.append(str(sql)))
    getattr(module, direction)()
    return recorded


def _outside_dollar_quotes(sql: str) -> str:
    """The SQL with `$$...$$` bodies and '...' literals removed."""
    sql = re.sub(r"\$\$.*?\$\$", "", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


@pytest.mark.parametrize("filename", MIGRATIONS)
@pytest.mark.parametrize("direction", ("upgrade", "downgrade"))
def test_each_execute_is_one_statement_without_bind_params(filename, direction):
    statements = _statements(filename, direction)
    assert statements
    for sql in statements:
        body = _outside_dollar_quotes(sql).strip().rstrip(";")
        assert ";" not in body, f"{filename} {direction}: several commands in one execute:\n{sql}"
        assert not text(sql).compile().params, f"{filename} {direction}: ':name' read as a bind param:\n{sql}"


def test_the_guard_catches_both_failure_classes():
    chained = "DO $$ BEGIN NULL; END $$; DO $$ BEGIN NULL; END $$"
    assert ";" in _outside_dollar_quotes(chained).strip().rstrip(";")
    assert text("""SELECT '{"recurring_orders":true}'::jsonb""").compile().params
