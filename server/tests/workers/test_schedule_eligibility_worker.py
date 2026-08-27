import asyncio
from datetime import date
from unittest import mock
from uuid import uuid4

from app.workers import celery_app
from app.workers.tasks import schedule_eligibility


def test_schedule_eligibility_task_is_registered():
    assert "app.workers.tasks.schedule_eligibility" in celery_app.celery_app.conf.include
    assert (
        "schedule_eligibility",
        "app.workers.tasks.schedule_eligibility",
        "run_schedule_eligibility",
    ) in celery_app._SCHEDULED_TASKS
    assert schedule_eligibility.run_schedule_eligibility.name == "schedule_eligibility.run"


class WarningRecipientConn:
    def __init__(self, *, company_id=None, employee_id=None, requirement_id=None,
                 location_id=None, deliveries=None):
        self.company_id = company_id or uuid4()
        self.employee_id = employee_id or uuid4()
        self.requirement_id = requirement_id or uuid4()
        self.location_id = location_id or uuid4()
        self.deliveries = deliveries if deliveries is not None else set()
        self.executed: list[tuple] = []

    async def fetchrow(self, query, *_args):
        assert "schedule_eligibility_cases" in query
        return {
            "company_id": self.company_id,
            "employee_id": self.employee_id,
            "location_id": self.location_id,
            "requirement_id": self.requirement_id,
            "expires_at": date(2026, 9, 10),
            "first_name": "Nadia",
            "last_name": "Hassan",
            "employee_email": "nadia@example.com",
        }

    async def fetch(self, query, *_args):
        if "schedule_location_notification_recipients" in query:
            return []
        assert "is_manager" in query
        return [{"email": "manager@example.com", "first_name": "Manager"}]

    async def fetchval(self, query, *args):
        assert "schedule_eligibility_notification_deliveries" in query
        key = (args[0], args[2], args[3], args[4], args[5].lower())
        if key in self.deliveries:
            return None
        self.deliveries.add(key)
        return uuid4()

    async def execute(self, query, *args):
        self.executed.append((query, args))


class CapturingEmailService:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_email(self, **message):
        self.messages.append(message)


def test_expiry_warning_notifies_employee_and_location_manager():
    conn = WarningRecipientConn()
    email_service = CapturingEmailService()

    with mock.patch(
        "app.core.services.email.get_email_service",
        return_value=email_service,
    ):
        asyncio.run(schedule_eligibility._send_expiry_warning_email(conn, uuid4()))

    assert {message["to_email"] for message in email_service.messages} == {
        "nadia@example.com",
        "manager@example.com",
    }
    assert all("Credential expiring soon: Nadia Hassan" == message["subject"] for message in email_service.messages)
    assert all("2026-09-10" in message["html_content"] for message in email_service.messages)
    assert len(conn.executed) == 2
    assert all("SET sent_at=NOW()" in query for query, _args in conn.executed)


def test_expiry_warning_sends_employee_once_but_managers_once_per_location():
    company_id = uuid4()
    employee_id = uuid4()
    requirement_id = uuid4()
    deliveries: set[tuple] = set()
    first = WarningRecipientConn(
        company_id=company_id, employee_id=employee_id,
        requirement_id=requirement_id, location_id=uuid4(), deliveries=deliveries,
    )
    second = WarningRecipientConn(
        company_id=company_id, employee_id=employee_id,
        requirement_id=requirement_id, location_id=uuid4(), deliveries=deliveries,
    )
    email_service = CapturingEmailService()

    with mock.patch(
        "app.core.services.email.get_email_service",
        return_value=email_service,
    ):
        asyncio.run(schedule_eligibility._send_expiry_warning_email(first, uuid4()))
        asyncio.run(schedule_eligibility._send_expiry_warning_email(second, uuid4()))

    employee_messages = [
        message for message in email_service.messages
        if message["to_email"] == "nadia@example.com"
    ]
    manager_messages = [
        message for message in email_service.messages
        if message["to_email"] == "manager@example.com"
    ]
    assert len(employee_messages) == 1
    assert len(manager_messages) == 2
