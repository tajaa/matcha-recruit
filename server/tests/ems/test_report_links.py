"""services/ir/report_links.py — the shared core behind "@huume send the
reporting link" and the admin Magic Links page's generate button.

    cd server && ./venv/bin/python -m pytest tests/ems/test_report_links.py -q
"""

import pytest

from app.matcha.services.ir import report_links


class TestReportLinkAllowed:
    def test_both_present_and_true(self):
        assert report_links.report_link_allowed({"incidents": True, "ir_magic_links": True}) is True

    def test_missing_incidents_denies(self):
        # `incidents` has no default-allow story — a company that never
        # bought IR has no reporting link to share, missing key or not.
        assert report_links.report_link_allowed({"ir_magic_links": True}) is False

    def test_missing_ir_magic_links_allows(self):
        # Mirrors inbound_email.py:_public_intake_allowed — companies
        # predating the 2026-07-30 ir_magic_links split have no stored key
        # and must not be silently cut off from their existing public links.
        assert report_links.report_link_allowed({"incidents": True}) is True

    def test_explicit_false_ir_magic_links_denies(self):
        assert report_links.report_link_allowed({"incidents": True, "ir_magic_links": False}) is False

    def test_explicit_false_incidents_denies(self):
        assert report_links.report_link_allowed({"incidents": False, "ir_magic_links": True}) is False

    def test_empty_dict_denies(self):
        assert report_links.report_link_allowed({}) is False


class TestPublicReportUrl:
    def test_composes_from_app_base_url(self, monkeypatch):
        from app.matcha.services.ir import report_links as mod

        class _Settings:
            app_base_url = "https://hey-matcha.com"
        monkeypatch.setattr(mod, "get_settings", lambda: _Settings())
        assert mod.public_report_url("abc123") == "https://hey-matcha.com/report/abc123"

    def test_strips_trailing_slash(self, monkeypatch):
        from app.matcha.services.ir import report_links as mod

        class _Settings:
            app_base_url = "https://hey-matcha.com/"
        monkeypatch.setattr(mod, "get_settings", lambda: _Settings())
        assert mod.public_report_url("abc123") == "https://hey-matcha.com/report/abc123"


class _FakeConn:
    def __init__(self, token=None):
        self.token = token
        self.executed = []

    async def fetchval(self, query, *args):
        assert "report_email_token" in query
        return self.token

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "UPDATE 1"


class TestFetchAndGenerate:
    @pytest.mark.asyncio
    async def test_fetch_returns_stored_token(self):
        conn = _FakeConn(token="existing-token")
        assert await report_links.fetch_report_token(conn, "company-id") == "existing-token"

    @pytest.mark.asyncio
    async def test_fetch_returns_none_when_unset(self):
        conn = _FakeConn(token=None)
        assert await report_links.fetch_report_token(conn, "company-id") is None

    @pytest.mark.asyncio
    async def test_generate_writes_and_returns_a_token(self):
        conn = _FakeConn()
        token = await report_links.generate_report_token(conn, "company-id")
        assert isinstance(token, str) and len(token) > 10
        assert len(conn.executed) == 1
        query, args = conn.executed[0]
        assert "report_email_token" in query and "report_token_used_at" in query
        assert args == (token, "company-id")

    @pytest.mark.asyncio
    async def test_generate_produces_distinct_tokens(self):
        conn = _FakeConn()
        first = await report_links.generate_report_token(conn, "company-id")
        second = await report_links.generate_report_token(conn, "company-id")
        assert first != second
