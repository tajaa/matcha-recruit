from unittest.mock import AsyncMock

import pytest

from app.core.services import error_notifier


@pytest.mark.asyncio
async def test_server_error_alerts_on_error(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(error_notifier, "_alerts_enabled", lambda: True)
    monkeypatch.setattr(error_notifier, "_should_send", lambda _: True)
    monkeypatch.setattr(error_notifier, "_admin_link", lambda: ("https://app.test/admin/server-errors", ""))
    monkeypatch.setattr(error_notifier, "_send", send)

    await error_notifier.notify_server_error({
        "fingerprint": "fingerprint",
        "level": "ERROR",
        "kind": "exception",
        "message": "unexpected failure",
    })

    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_server_warning_does_not_alert(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(error_notifier, "_alerts_enabled", lambda: True)
    monkeypatch.setattr(error_notifier, "_send", send)

    await error_notifier.notify_server_error({"level": "WARNING", "fingerprint": "fingerprint"})

    send.assert_not_awaited()
