"""send_admin_interview_invitation_email addresses the candidate it was given."""

import asyncio

from app.core.services.email.auth import AuthEmailMixin


class _Service(AuthEmailMixin):
    def __init__(self, configured=True):
        self.configured = configured
        self.sent: list[tuple] = []

    def is_configured(self):
        return self.configured

    async def _send_with_fallback(self, to_email, to_name, subject, html_content, text_content):
        self.sent.append((to_email, to_name, subject, text_content))
        return True


def test_sends_to_the_candidate_address_and_name():
    svc = _Service()
    ok = asyncio.run(svc.send_admin_interview_invitation_email(
        candidate_email="candidate@example.com", candidate_name="Casey",
        company_name="Acme Test", position_title="Line Cook",
    ))
    assert ok is True
    to_email, to_name, subject, text = svc.sent[0]
    assert (to_email, to_name) == ("candidate@example.com", "Casey")
    assert subject == "You're a top candidate: Line Cook at Acme Test"
    assert text.startswith("Hi Casey,")


def test_skips_when_email_is_not_configured():
    svc = _Service(configured=False)
    assert asyncio.run(svc.send_admin_interview_invitation_email(
        candidate_email="candidate@example.com", candidate_name=None,
        company_name="Acme Test", position_title="Line Cook",
    )) is False
    assert svc.sent == []
