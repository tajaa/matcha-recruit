"""discipline_notifications audience targeting: hr_only / manager_only /
the pre-existing "all" default must keep behaving exactly as before.

    cd server && ./venv/bin/python -m pytest tests/discipline/test_discipline_notifications_audience.py -q
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.discipline import discipline_notifications as notif

EMPLOYEE_ID = uuid4()
COMPANY_ID = uuid4()
MANAGER_USER_ID = uuid4()
CLIENT_A = uuid4()
CLIENT_B = uuid4()


def test_new_titles_registered():
    for action in ("discipline_approval_requested", "discipline_approved", "discipline_denied"):
        assert action in notif._TITLES


class TestDesignatedApprovers:
    @pytest.mark.asyncio
    async def test_hr_only_targets_designated_approvers(self, monkeypatch):
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[{"id": CLIENT_A}])  # is_hr_approver = TRUE query
        result = await notif._designated_approver_user_ids(conn, COMPANY_ID)
        assert result == {CLIENT_A}

    @pytest.mark.asyncio
    async def test_hr_only_falls_back_to_all_clients_when_none_designated(self, monkeypatch):
        conn = MagicMock()
        calls = {"n": 0}

        async def fetch(query, *args):
            calls["n"] += 1
            if "is_hr_approver = TRUE" in query:
                return []
            return [{"id": CLIENT_A}, {"id": CLIENT_B}]

        conn.fetch = AsyncMock(side_effect=fetch)
        result = await notif._designated_approver_user_ids(conn, COMPANY_ID)
        assert result == {CLIENT_A, CLIENT_B}
        assert calls["n"] == 2


class TestResolveRecipientsAudience:
    @pytest.mark.asyncio
    async def test_hr_only_never_includes_manager(self, monkeypatch):
        conn = MagicMock()
        # Manager chain would resolve if consulted — hr_only must never call it.
        manager_chain_mock = AsyncMock(return_value=([uuid4()], []))
        monkeypatch.setattr(notif, "_resolve_manager_chain", manager_chain_mock)
        monkeypatch.setattr(notif, "_designated_approver_user_ids", AsyncMock(return_value={CLIENT_A}))

        recipients = await notif._resolve_recipients(
            conn, {"employee_id": EMPLOYEE_ID, "company_id": COMPANY_ID, "issued_by": None},
            notify_grandparent=True, audience="hr_only",
        )

        manager_chain_mock.assert_not_called()
        assert recipients == [{"user_id": CLIENT_A, "kind": "hr"}]

    @pytest.mark.asyncio
    async def test_manager_only_falls_back_to_hr_when_no_manager_resolves(self, monkeypatch):
        conn = MagicMock()
        monkeypatch.setattr(notif, "_resolve_manager_chain", AsyncMock(return_value=([], [])))
        monkeypatch.setattr(notif, "_designated_approver_user_ids", AsyncMock(return_value={CLIENT_A}))

        recipients = await notif._resolve_recipients(
            conn, {"employee_id": EMPLOYEE_ID, "company_id": COMPANY_ID, "issued_by": None},
            notify_grandparent=True, audience="manager_only",
        )

        assert recipients == [{"user_id": CLIENT_A, "kind": "hr"}]

    @pytest.mark.asyncio
    async def test_manager_only_uses_manager_chain_when_it_resolves(self, monkeypatch):
        conn = MagicMock()
        monkeypatch.setattr(notif, "_resolve_manager_chain", AsyncMock(return_value=([MANAGER_USER_ID], [])))
        designated_mock = AsyncMock(return_value={CLIENT_A})
        monkeypatch.setattr(notif, "_designated_approver_user_ids", designated_mock)

        recipients = await notif._resolve_recipients(
            conn, {"employee_id": EMPLOYEE_ID, "company_id": COMPANY_ID, "issued_by": None},
            notify_grandparent=True, audience="manager_only",
        )

        designated_mock.assert_not_called()
        assert recipients == [{"user_id": MANAGER_USER_ID, "kind": "direct_manager"}]

    @pytest.mark.asyncio
    async def test_default_audience_all_unchanged(self, monkeypatch):
        conn = MagicMock()
        monkeypatch.setattr(notif, "_resolve_manager_chain", AsyncMock(return_value=([MANAGER_USER_ID], [])))
        monkeypatch.setattr(notif, "_all_client_user_ids", AsyncMock(return_value={CLIENT_A, CLIENT_B}))

        recipients = await notif._resolve_recipients(
            conn, {"employee_id": EMPLOYEE_ID, "company_id": COMPANY_ID, "issued_by": CLIENT_A},
            notify_grandparent=True,
        )

        kinds = {r["kind"] for r in recipients}
        user_ids = {r["user_id"] for r in recipients}
        assert "direct_manager" in kinds
        assert MANAGER_USER_ID in user_ids
        assert CLIENT_A in user_ids and CLIENT_B in user_ids

    @pytest.mark.asyncio
    async def test_invalid_audience_raises(self):
        conn = MagicMock()
        with pytest.raises(ValueError):
            await notif._resolve_recipients(
                conn, {"employee_id": EMPLOYEE_ID, "company_id": COMPANY_ID, "issued_by": None},
                notify_grandparent=True, audience="bogus",
            )


class TestDispatchUnknownAction:
    @pytest.mark.asyncio
    async def test_dispatch_drops_unknown_action(self, monkeypatch):
        resolve_mock = AsyncMock()
        monkeypatch.setattr(notif, "_resolve_recipients", resolve_mock)
        await notif.dispatch(record={"id": uuid4(), "employee_id": EMPLOYEE_ID, "company_id": COMPANY_ID}, action="not_a_real_action")
        resolve_mock.assert_not_called()
