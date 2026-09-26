"""Unit coverage for post-confirmation manager-request notification delivery."""

from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import schedule_request_notifications as notifications


class _NoRequestConn:
    async def fetchrow(self, *_args):
        return None


@pytest.mark.asyncio
async def test_notification_skips_requests_that_are_not_manager_ready():
    result = await notifications.send_manager_ready_notifications(
        _NoRequestConn(), request_id=uuid4(),
    )
    assert result == {"sent": 0, "skipped": 1}


class _ReadyConn:
    def __init__(self):
        self.delivery_id = uuid4()
        self.request_id = uuid4()
        self.company_id = uuid4()
        self.recipient_id = uuid4()
        self.executed = []
        self.claims = []

    async def fetchrow(self, *_args):
        return {
            "id": self.request_id,
            "company_id": self.company_id,
            "request_type": "swap",
            "counterparty_confirmed_at": object(),
            "owner_name": "Avery Owner",
            "target_name": "Blair Target",
        }

    async def fetch(self, *_args):
        return [{"id": self.recipient_id, "email": "manager@company.example", "name": "Manager"}]

    async def fetchval(self, query, *_args):
        self.claims.append(query)
        return self.delivery_id

    async def execute(self, query, *args):
        self.executed.append((query, args))


@pytest.mark.asyncio
async def test_notification_claims_then_marks_delivery_sent(monkeypatch):
    conn = _ReadyConn()

    class _Email:
        def is_configured(self):
            return True

        async def send_email(self, *_args):
            return True

    monkeypatch.setattr(notifications, "get_email_service", lambda: _Email())
    monkeypatch.setattr(notifications, "get_settings", lambda: SimpleNamespace(app_base_url="https://matcha.example"))
    monkeypatch.setattr(notifications, "_is_reserved_test_domain", lambda _email: False)

    result = await notifications.send_manager_ready_notifications(conn, request_id=conn.request_id)

    assert result == {"sent": 1, "recipients": 1}
    assert any("SET sent_at=NOW()" in query for query, _args in conn.executed)
    assert any("ON CONFLICT (request_id, recipient_user_id, event_type)" in query for query in conn.claims)


@pytest.mark.asyncio
@pytest.mark.parametrize("request_type", ["drop", "claim"])
async def test_unilateral_requests_notify_manager_without_counterparty(monkeypatch, request_type):
    conn = _ReadyConn()

    async def unilateral_request(*_args):
        return {
            "id": conn.request_id, "company_id": conn.company_id,
            "request_type": request_type, "counterparty_confirmed_at": None,
            "owner_name": "Avery Owner", "target_name": "",
        }

    class _Email:
        def is_configured(self):
            return False

    conn.fetchrow = unilateral_request
    monkeypatch.setattr(notifications, "get_email_service", lambda: _Email())
    monkeypatch.setattr(notifications, "get_settings", lambda: SimpleNamespace(app_base_url="https://matcha.example"))
    result = await notifications.send_manager_ready_notifications(conn, request_id=conn.request_id)
    assert result["recipients"] == 1
    bell = next(args for query, args in conn.executed if "WITH notification" in query)
    assert f"Avery Owner submitted a {request_type} request." in bell[3]


@pytest.mark.asyncio
async def test_resolved_request_marks_every_matching_manager_alert_read():
    company_id = uuid4()
    request_id = uuid4()

    class _Conn:
        def __init__(self):
            self.query = ""
            self.args = ()

        async def execute(self, query, *args):
            self.query = query
            self.args = args
            return "UPDATE 2"

    conn = _Conn()
    updated = await notifications.mark_manager_ready_notifications_resolved(
        conn, company_id=company_id, request_id=request_id,
    )

    assert updated == 2
    assert "type = 'schedule_request_pending'" in conn.query
    assert "is_read = FALSE" in conn.query
    assert "metadata->>'request_id' = $2" in conn.query
    assert conn.args == (company_id, str(request_id))


def test_every_manager_ready_exit_resolves_its_alerts():
    root = Path(__file__).parents[2] / "app/matcha/routes"
    manager = (root / "employee_schedule/requests.py").read_text()
    portal = (root / "employee_portal/schedule.py").read_text()
    assert "await mark_manager_ready_notifications_resolved(" in manager
    assert portal.count("await mark_manager_ready_notifications_resolved(") == 2


def test_recovery_reclaims_only_stale_unsent_delivery_claims():
    service = Path(__file__).parents[2] / "app/matcha/services/scheduling/schedule_request_notifications.py"
    worker = Path(__file__).parents[2] / "app/workers/tasks/schedule_request_notifications.py"
    assert "sent_at IS NULL" in service.read_text()
    assert "INTERVAL '5 minutes'" in service.read_text()
    # The sweep only selects requests some active reviewer has not been told
    # about on BOTH channels; otherwise the whole backlog is re-scanned every
    # run and, past the LIMIT, the newest requests are never reached.
    sweep = worker.read_text()
    assert "d.event_type = 'manager_ready' AND d.sent_at IS NOT NULL" in sweep
    assert "d.event_type = 'manager_ready_in_app' AND d.sent_at IS NOT NULL" in sweep
    assert "u.is_active = true" in sweep
