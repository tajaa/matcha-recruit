"""DB-free unit tests for `_resolve_shift_ref`'s narrowing tiers — the
staffed/unstaffed discriminator and the exact-date-drops-the-window rule.

A fake `conn.fetch` always returns the same candidate rows regardless of the
generated SQL/params (this test is about the narrowing logic downstream of
the query, not the query itself — `_resolve_shift_ref`'s SQL correctness is
exercised live, see the plan doc). `conn.fetch` records the last params list
so the window-boundary tests can assert on how many params were bound
(target_date present -> window_end param dropped).

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_resolve_shift_ref.py -q
"""

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.matcha.services.scheduling.schedule_chat import EDIT_LOOKUP_WINDOW_DAYS, _resolve_shift_ref

_COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
_TODAY = date(2026, 8, 12)

_BASE_ROW = {
    "id": UUID("33333333-3333-3333-3333-333333333333"),
    "starts_at": datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
    "ends_at": datetime(2026, 8, 12, 22, 0, tzinfo=timezone.utc),
    "status": "published",
    "role": "closer",
    "location_id": None,
    "break_minutes": 0,
    "kind": "regular",
    "training_requirement_id": None,
    "published_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    "assignee_names": "Diego Petrov",
}
_UNSTAFFED_ROW = {**_BASE_ROW, "id": UUID("44444444-4444-4444-4444-444444444444"), "assignee_names": ""}


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.last_params = None

    async def fetch(self, query, *params):
        self.last_params = params
        return self._rows


class TestStaffingHintNarrowing:
    @pytest.mark.asyncio
    async def test_unstaffed_hint_picks_the_empty_row(self):
        conn = _FakeConn([_BASE_ROW, _UNSTAFFED_ROW])
        ref = {"target_date": "2026-08-12", "target_role_hint": "closer", "target_staffing_hint": "unstaffed"}
        found = await _resolve_shift_ref(conn, _COMPANY_ID, None, ref, _TODAY)
        assert "shift" in found
        assert found["shift"]["id"] == _UNSTAFFED_ROW["id"]

    @pytest.mark.asyncio
    async def test_staffed_hint_picks_the_assigned_row(self):
        conn = _FakeConn([_BASE_ROW, _UNSTAFFED_ROW])
        ref = {"target_date": "2026-08-12", "target_role_hint": "closer", "target_staffing_hint": "staffed"}
        found = await _resolve_shift_ref(conn, _COMPANY_ID, None, ref, _TODAY)
        assert "shift" in found
        assert found["shift"]["id"] == _BASE_ROW["id"]

    @pytest.mark.asyncio
    async def test_no_staffing_hint_stays_ambiguous(self):
        conn = _FakeConn([_BASE_ROW, _UNSTAFFED_ROW])
        ref = {"target_date": "2026-08-12", "target_role_hint": "closer"}
        found = await _resolve_shift_ref(conn, _COMPANY_ID, None, ref, _TODAY)
        assert "ambiguous" in found
        assert len(found["ambiguous"]) == 2

    @pytest.mark.asyncio
    async def test_staffing_hint_matching_nothing_stays_ambiguous_not_a_guess(self):
        # Both rows staffed — an "unstaffed" hint that narrows to zero must
        # fall back to the pickable listing, not silently guess one.
        conn = _FakeConn([_BASE_ROW, {**_BASE_ROW, "id": UUID("55555555-5555-5555-5555-555555555555")}])
        ref = {"target_date": "2026-08-12", "target_role_hint": "closer", "target_staffing_hint": "unstaffed"}
        found = await _resolve_shift_ref(conn, _COMPANY_ID, None, ref, _TODAY)
        assert "ambiguous" in found
        assert len(found["ambiguous"]) == 2

    @pytest.mark.asyncio
    async def test_single_row_resolves_without_needing_a_hint(self):
        conn = _FakeConn([_UNSTAFFED_ROW])
        ref = {"target_date": "2026-08-12", "target_role_hint": "closer"}
        found = await _resolve_shift_ref(conn, _COMPANY_ID, None, ref, _TODAY)
        assert found["shift"]["id"] == _UNSTAFFED_ROW["id"]


class TestWindowBoundary:
    @pytest.mark.asyncio
    async def test_exact_target_date_drops_the_window_cap(self):
        # A real prod miss: a shift correctly created 15+ days out was
        # invisible because the window used to cap at 14 days regardless of
        # an exact date being given. An exact date now binds the DATE itself
        # as a param — never a window_end datetime bounding it away.
        conn = _FakeConn([_UNSTAFFED_ROW])
        ref = {"target_date": "2026-09-30", "target_role_hint": "closer"}
        found = await _resolve_shift_ref(conn, _COMPANY_ID, None, ref, _TODAY)
        assert "shift" in found
        assert date(2026, 9, 30) in conn.last_params
        assert not any(
            isinstance(p, datetime) and p != conn.last_params[1] for p in conn.last_params
        )  # only window_start is a datetime — no second (window_end) datetime param

    @pytest.mark.asyncio
    async def test_hint_only_search_keeps_the_window_cap(self):
        conn = _FakeConn([_UNSTAFFED_ROW])
        ref = {"target_role_hint": "closer"}
        await _resolve_shift_ref(conn, _COMPANY_ID, None, ref, _TODAY)
        expected_window_end = datetime.combine(_TODAY, datetime.min.time(), tzinfo=timezone.utc) + timedelta(
            days=EDIT_LOOKUP_WINDOW_DAYS)
        assert expected_window_end in conn.last_params

    def test_window_constant_is_60_days(self):
        assert EDIT_LOOKUP_WINDOW_DAYS == 60
