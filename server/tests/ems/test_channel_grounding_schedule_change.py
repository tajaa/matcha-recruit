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
