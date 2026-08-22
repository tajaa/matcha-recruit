"""DB-free tests for digest rendering and claim/retry semantics."""

from datetime import date

import pytest

from app.matcha.services.scheduling import daily_digest


class _Conn:
    def __init__(self, claim_result, send_result):
        self.claim_result = claim_result
        self.send_result = send_result
        self.executed = []

    async def fetchval(self, query, *params):
        return self.claim_result

    async def execute(self, query, *params):
        self.executed.append((query, params))


class _Service:
    def __init__(self, configured=True, send_result=False):
        self.configured = configured
        self.send_result = send_result

    def is_configured(self):
        return self.configured

    async def send_email(self, *args):
        return self.send_result


@pytest.mark.asyncio
async def test_transient_delivery_failure_releases_claim_for_retry():
    conn = _Conn(claim_result=object(), send_result=False)
    result = await daily_digest._deliver(
        conn, _Service(send_result=False), company_id="company", location_id="location",
        digest_date=date(2026, 8, 21), email="Manager@acme.co", recipient_type="manager",
        to_name=None, subject="subject", html="html",
    )

    assert result == "failed_released"
    assert len(conn.executed) == 1
    assert "DELETE FROM schedule_digest_deliveries" in conn.executed[0][0]
    assert conn.executed[0][1][2] == "Manager@acme.co"


@pytest.mark.asyncio
async def test_reserved_domain_keeps_permanent_claim():
    conn = _Conn(claim_result=object(), send_result=True)
    result = await daily_digest._deliver(
        conn, _Service(send_result=True), company_id="company", location_id="location",
        digest_date=date(2026, 8, 21), email="manager@example.test", recipient_type="manager",
        to_name=None, subject="subject", html="html",
    )

    assert result == "skipped_permanent"
    assert conn.executed == []


def test_guidance_jsonb_is_rendered_as_summary_not_python_dict():
    assert daily_digest._guidance_text('{"summary": "Take a 30-minute meal break."}') == "Take a 30-minute meal break."
