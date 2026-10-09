"""Fractional HR schema bootstrap (split out of the removed broker bootstrap)."""

import asyncio

from app.database.bootstrap.fractional import create_fractional

EXPECTED_TABLES = {
    "fractional_clients",
    "fractional_assignments",
    "fractional_scope_items",
    "fractional_tasks",
    "fractional_time_entries",
    "fractional_audit_log",
}


class _RecordingConn:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, sql: str, *args):
        self.statements.append(sql)


def test_creates_every_fractional_table_and_nothing_broker_related():
    conn = _RecordingConn()
    asyncio.run(create_fractional(conn))
    sql = "\n".join(conn.statements)
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table} " in sql, table
    assert "broker" not in sql.lower()


def test_is_idempotent_ddl_only():
    conn = _RecordingConn()
    asyncio.run(create_fractional(conn))
    for statement in conn.statements:
        head = statement.strip().upper()
        assert head.startswith(("CREATE TABLE IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS")), statement
