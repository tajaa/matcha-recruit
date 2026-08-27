import asyncio
from datetime import date
from unittest import mock
from uuid import uuid4

from app.workers.tasks import schedule_eligibility


class WarningRecipientConn:
    def __init__(self):
        self.company_id = uuid4()
        self.employee_id = uuid4()
        self.location_id = uuid4()

    async def fetchrow(self, query, *_args):
        assert "schedule_eligibility_cases" in query
        return {
            "company_id": self.company_id,
            "employee_id": self.employee_id,
            "location_id": self.location_id,
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
