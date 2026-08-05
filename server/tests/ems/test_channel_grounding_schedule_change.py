"""`run_schedule_change` — the enforcement point for the ASK-loop's
`propose_schedule_change` write tool. Same posture as `run_coverage_lookup`:
the model's structured args are advisory only, every gate is re-checked
here before any DB write, proven without a real database by asserting the
refusal paths never reach `schedule_chat`.

    cd server && ./venv/bin/python -m pytest tests/ems/test_channel_grounding_schedule_change.py -q
"""

import asyncio
from uuid import uuid4

from app.matcha.services.ems import channel_grounding

COMPANY_ID = uuid4()
USER_ID = uuid4()
CHANNEL_ID = uuid4()


def _run(coro):
    return asyncio.run(coro)


def _features(**over):
    base = {"ems": True, "employee_schedule": True}
    base.update(over)
    return base


def _call(conn=None, *, features, is_admin=True, role="client", location_unavailable=False, args=None):
    return channel_grounding.run_schedule_change(
        conn, company_id=COMPANY_ID, features=features, is_admin=is_admin,
        asker_user_id=USER_ID, asker_role=role, channel_id=CHANNEL_ID,
        location_unavailable=location_unavailable, args=args or {"kind": "cancel"},
    )


class TestGates:
    def test_non_admin_refused_without_touching_conn(self):
        # conn=None — a real DB call here would raise AttributeError, so
        # reaching a DB call at all fails the test as a side effect.
        result = _run(_call(features=_features(), is_admin=False))
        assert "admins" in result["text"]
        assert result["proposal_id"] is None

    def test_wrong_role_refused(self):
        result = _run(_call(features=_features(), role="employee"))
        assert result["proposal_id"] is None

    def test_ems_off_refused(self):
        result = _run(_call(features=_features(ems=False)))
        assert result["proposal_id"] is None

    def test_employee_schedule_off_refused(self):
        result = _run(_call(features=_features(employee_schedule=False)))
        assert result["proposal_id"] is None

    def test_dead_store_refused(self):
        result = _run(_call(features=_features(), location_unavailable=True))
        assert "deactivated" in result["text"]
        assert result["proposal_id"] is None

    def test_rate_limited_refused(self, monkeypatch):
        from fastapi import HTTPException

        async def boom(*a, **k):
            raise HTTPException(status_code=429)

        monkeypatch.setattr(
            "app.core.services.redis_cache.check_rate_limit", boom)
        result = _run(_call(features=_features()))
        assert "limit" in result["text"].lower()
        assert result["proposal_id"] is None

    def test_missing_edit_hints_clarifies_rather_than_crashing(self, monkeypatch):
        async def no_limit(*a, **k):
            return None

        monkeypatch.setattr(
            "app.core.services.redis_cache.check_rate_limit", no_limit)
        # kind='reassign' with nothing else — coerce_edit_request drops it.
        result = _run(_call(features=_features(), args={"kind": "reassign"}))
        assert result["proposal_id"] is None
        assert "enough" in result["text"].lower() or "which" in result["text"].lower()


class TestToolArgsToSentence:
    """`original_content` is what `compose_clarify_followup` (schedule_chat.
    py) feeds back to Stage A's Gemini re-parse verbatim if a clarify round
    follows — it must carry the real names/dates the model already
    extracted, not the old "[via ask] {kind} request" placeholder that
    re-parsed against nothing and looped."""

    def test_create_carries_label_date_and_time(self):
        text = channel_grounding._tool_args_to_sentence("create", {
            "label": "opener", "date": "2026-08-12",
            "start_time": "08:00", "end_time": "16:00",
        })
        assert "opener" in text and "2026-08-12" in text and "08:00" in text and "16:00" in text

    def test_reassign_carries_both_names_and_date(self):
        text = channel_grounding._tool_args_to_sentence("reassign", {
            "target_employee_name": "Cara", "to_employee_name": "Casey",
            "target_date": "2026-08-12", "target_role_hint": "opener",
        })
        assert "Cara" in text and "Casey" in text and "2026-08-12" in text and "opener" in text

    def test_swap_carries_both_shifts(self):
        text = channel_grounding._tool_args_to_sentence("swap", {
            "target_employee_name": "Cara", "target_date": "2026-08-12",
            "second_employee_name": "Casey", "second_date": "2026-08-13",
        })
        assert "Cara" in text and "Casey" in text
        assert "2026-08-12" in text and "2026-08-13" in text

    def test_retime_carries_the_new_window(self):
        text = channel_grounding._tool_args_to_sentence("retime", {
            "target_employee_name": "Cara", "target_date": "2026-08-12",
            "new_start_time": "13:00", "new_end_time": "21:00",
        })
        assert "Cara" in text and "13:00" in text and "21:00" in text

    def test_no_longer_a_bare_placeholder(self):
        text = channel_grounding._tool_args_to_sentence("unassign", {
            "target_employee_name": "Dana", "target_date": "2026-08-12",
        })
        assert text != "[via ask] unassign request"
        assert "Dana" in text
