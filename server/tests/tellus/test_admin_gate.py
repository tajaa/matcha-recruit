"""Pure-function tests for the Tell-Us internal admin allowlist gate
(_is_tellus_admin in app/tellus/dependencies.py). No DB, no HTTP.
"""
from unittest.mock import patch

from app.config import Settings
from app.tellus.dependencies import _is_tellus_admin


def _settings_with(emails: str) -> Settings:
    s = Settings.__new__(Settings)
    s.tellus_admin_emails = emails
    return s


class TestIsTellusAdmin:
    def test_empty_setting_fails_closed(self):
        # Patch the module that DEFINES _is_tellus_admin's caller of
        # get_settings (app.tellus.dependencies), not app.config itself —
        # per server/CLAUDE.md's monkeypatch rule.
        with patch("app.tellus.dependencies.get_settings", return_value=_settings_with("")):
            assert _is_tellus_admin("anyone@example.com") is False

    def test_case_insensitive_match(self):
        with patch("app.tellus.dependencies.get_settings", return_value=_settings_with("admin@x.test")):
            assert _is_tellus_admin("Admin@X.test") is True

    def test_comma_list_with_spaces(self):
        with patch("app.tellus.dependencies.get_settings", return_value=_settings_with("a@x.test, b@y.test")):
            assert _is_tellus_admin("a@x.test") is True
            assert _is_tellus_admin("b@y.test") is True
            assert _is_tellus_admin("c@z.test") is False
