"""shift_writes.py's remove/restore assignment primitives — the two-phase
edit executor in schedule_chat.py builds on these for undo-on-refusal.
Fake asyncpg connection, no real DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_shift_writes.py -q
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.matcha.services.scheduling.shift_writes import (
    removal_audit_details, remove_assignment_core, restore_assignment_raw,
)


def _run(coro):
    return asyncio.run(coro)


def _shift_row(**over):
    base = {
        "starts_at": datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
        "status": "published", "kind": "work", "location_id": None,
    }
    base.update(over)
    return base


class FakeConn:
    """Routes each query by a keyword sniff, same fake-conn idiom as
    tests/employee_schedule/test_coverage.py. `delete_count` simulates
    asyncpg's `DELETE n` status tag."""

    def __init__(self, delete_count=1):
        self.delete_count = delete_count
        self.deletes = []
        self.audit_inserts = []
        self.assignment_inserts = []

    async def execute(self, query, *args):
        q = " ".join(query.split())
        if q.startswith("DELETE FROM schedule_shift_assignments"):
            self.deletes.append(args)
            return f"DELETE {self.delete_count}"
        if q.startswith("INSERT INTO schedule_audit_log"):
            self.audit_inserts.append(args)
            return "INSERT 0 1"
        if q.startswith("INSERT INTO schedule_shift_assignments"):
            self.assignment_inserts.append(args)
            return "INSERT 0 1"
        raise AssertionError(f"unexpected query: {q[:80]}")


class TestRemoveAssignmentCore:
    def test_deletes_and_writes_audit_by_default(self):
        conn = FakeConn(delete_count=1)
        deleted = _run(remove_assignment_core(
            conn, "co1", shift_id=uuid4(), employee_id=uuid4(),
            actor_user_id=uuid4(), shift_row=_shift_row(),
        ))
        assert deleted == 1
        assert len(conn.audit_inserts) == 1

    def test_zero_row_delete_never_writes_audit(self):
        # They weren't on the shift — a phantom assignment.delete row here
        # would otherwise feed Fair Workweek / the pretext shield.
        conn = FakeConn(delete_count=0)
        deleted = _run(remove_assignment_core(
            conn, "co1", shift_id=uuid4(), employee_id=uuid4(),
            actor_user_id=uuid4(), shift_row=_shift_row(),
        ))
        assert deleted == 0
        assert conn.audit_inserts == []

    def test_write_audit_false_defers_the_audit_row(self):
        conn = FakeConn(delete_count=1)
        deleted = _run(remove_assignment_core(
            conn, "co1", shift_id=uuid4(), employee_id=uuid4(),
            actor_user_id=uuid4(), shift_row=_shift_row(), write_audit=False,
        ))
        assert deleted == 1
        assert conn.audit_inserts == []


class TestRestoreAssignmentRaw:
    def test_reinserts_with_the_original_assigned_by(self):
        conn = FakeConn()
        original_assigner = uuid4()
        _run(restore_assignment_raw(
            conn, "co1", shift_id=uuid4(), employee_id=uuid4(),
            assigned_by=original_assigner,
        ))
        assert len(conn.assignment_inserts) == 1
        assert original_assigner in conn.assignment_inserts[0]


class TestRemovalAuditDetails:
    def test_shape_matches_the_inline_write(self):
        employee_id = uuid4()
        details = removal_audit_details(_shift_row(), employee_id, {"source": "huume_chat_edit"})
        assert details["employee_id"] == str(employee_id)
        assert details["shift_status"] == "published"
        assert details["source"] == "huume_chat_edit"
