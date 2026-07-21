"""`insert_audit_log` writes the exact row the per-domain helpers used to.

DB-free: a fake connection captures the SQL + bound params so we can assert the
shared helper is byte-for-byte equivalent to the three `log_audit` bodies it
replaced (same column list, same `$1..$7` order, same `json.dumps(details) if
details else None` rule). The three domain wrappers keep their signatures, so
this guards the one thing the refactor could break — the write itself.
"""

import json

import pytest

from app.core.services.audit_log import insert_audit_log


class FakeConn:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))


@pytest.mark.asyncio
async def test_writes_shared_column_shape_in_order():
    conn = FakeConn()
    await insert_audit_log(
        conn,
        table="er_audit_log",
        id_column="case_id",
        id_value="case-1",
        user_id="user-9",
        action="update",
        entity_type="note",
        entity_id="n-3",
        details={"field": "status"},
        ip_address="10.0.0.1",
    )
    sql, args = conn.calls[0]
    # table + fk column interpolated; everything else parameterized
    assert "INSERT INTO er_audit_log (case_id, user_id, action, entity_type, entity_id, details, ip_address)" in sql
    assert "$1, $2, $3, $4, $5, $6, $7" in sql
    assert args == (
        "case-1", "user-9", "update", "note", "n-3",
        json.dumps({"field": "status"}), "10.0.0.1",
    )


@pytest.mark.asyncio
async def test_details_none_becomes_null_not_the_string_null():
    conn = FakeConn()
    await insert_audit_log(
        conn, table="ir_audit_log", id_column="incident_id",
        id_value="IR-1", user_id=None, action="create",
    )
    _, args = conn.calls[0]
    # details defaulted to None → NULL, mirroring `json.dumps(details) if details else None`
    assert args[5] is None
    # nullable user_id passes through (system-triggered IR actions)
    assert args[1] is None
    # unset entity_type/entity_id/ip_address are None, not missing
    assert args[3] is None and args[4] is None and args[6] is None


@pytest.mark.asyncio
async def test_empty_details_dict_is_also_null():
    # `if details else None` treats {} as falsy → NULL, same as the old helpers.
    conn = FakeConn()
    await insert_audit_log(
        conn, table="accommodation_audit_log", id_column="case_id",
        id_value="AC-1", user_id="u1", action="x", details={},
    )
    _, args = conn.calls[0]
    assert args[5] is None
