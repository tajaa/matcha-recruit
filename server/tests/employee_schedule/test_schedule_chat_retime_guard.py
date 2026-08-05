"""Regression for a code-review finding on build_edit_proposal's retime
branch (2026-08-05): coerce_edit_request accepts a retime op carrying only
`new_day_hint` (test_retime_survives_on_new_day_hint_alone in
test_schedule_chat_edits.py), but when that hint doesn't resolve to a date
(resolve_day_hint returns None — e.g. "next friday", not a bare weekday
name), build_edit_proposal used to fall through to "keep the shift's
current date+times", building a confirmable retime proposal that changes
nothing yet still writes shift.update churn on confirm.

_resolve_shift_ref is monkeypatched (on the defining module — a patch on a
re-export would be a silent no-op, per server/CLAUDE.md's patching rule) so
this stays a single-purpose unit test of the retime guard, not a
full DB-backed exercise of shift resolution.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_retime_guard.py -q
"""

from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from app.matcha.services.scheduling import schedule_chat

_COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
_CREATED_BY = UUID("22222222-2222-2222-2222-222222222222")
_SHIFT = {
    "id": UUID("33333333-3333-3333-3333-333333333333"),
    "starts_at": datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc),
    "ends_at": datetime(2026, 8, 7, 16, 0, tzinfo=timezone.utc),
    "location_id": None,
    "kind": "regular",
    "break_minutes": 0,
    "training_requirement_id": None,
    "role": "Opener",
}


class _FakeConn:
    async def fetchval(self, query, *args):
        return None  # unscoped channel lookup

    async def fetchrow(self, query, *args):
        return {"id": UUID("44444444-4444-4444-4444-444444444444")}  # _persist_proposal INSERT


@pytest.mark.asyncio
async def test_unresolvable_new_day_hint_clarifies_instead_of_no_op_retime(monkeypatch):
    async def fake_resolve_shift_ref(conn, company_id, location_id, ref, today, **kwargs):
        return {"shift": _SHIFT}

    monkeypatch.setattr(schedule_chat, "_resolve_shift_ref", fake_resolve_shift_ref)

    parsed = {
        "edit_requests": [{
            "kind": "retime", "target_employee_name": None, "target_date": None,
            "target_day_hint": None, "target_time_hint": None, "target_role_hint": "opener",
            "to_employee_name": None, "second_employee_name": None, "second_date": None,
            "second_day_hint": None, "second_role_hint": None,
            "new_date": None, "new_day_hint": "next friday",  # not a bare weekday name -> unresolvable
            "new_start_time": None, "new_end_time": None, "shift_by_minutes": None,
        }],
    }

    build = await schedule_chat.build_edit_proposal(
        _FakeConn(), company_id=_COMPANY_ID, channel_id=None, source_message_id=None,
        created_by=_CREATED_BY, parsed=parsed, today=date(2026, 8, 5),
        original_content="push the opener back to next friday",
    )

    assert build.kind == "clarify"
    assert "what day" in build.pill_text.lower()


@pytest.mark.asyncio
async def test_resolvable_new_day_hint_still_builds_a_real_retime(monkeypatch):
    """Sanity check that the new guard doesn't over-fire — a resolvable
    hint ("friday") must still reach the actual retime math, not clarify."""
    async def fake_resolve_shift_ref(conn, company_id, location_id, ref, today, **kwargs):
        return {"shift": _SHIFT}

    async def fake_check_shift_compliance(*args, **kwargs):
        return []

    monkeypatch.setattr(schedule_chat, "_resolve_shift_ref", fake_resolve_shift_ref)
    monkeypatch.setattr(schedule_chat, "check_shift_compliance", fake_check_shift_compliance)

    parsed = {
        "edit_requests": [{
            "kind": "retime", "target_employee_name": None, "target_date": None,
            "target_day_hint": None, "target_time_hint": None, "target_role_hint": "opener",
            "to_employee_name": None, "second_employee_name": None, "second_date": None,
            "second_day_hint": None, "second_role_hint": None,
            "new_date": None, "new_day_hint": "friday",
            "new_start_time": None, "new_end_time": None, "shift_by_minutes": None,
        }],
    }

    build = await schedule_chat.build_edit_proposal(
        _FakeConn(), company_id=_COMPANY_ID, channel_id=None, source_message_id=None,
        created_by=_CREATED_BY, parsed=parsed, today=date(2026, 8, 5),
        original_content="push the opener back to friday",
    )

    assert build.kind == "proposal"
