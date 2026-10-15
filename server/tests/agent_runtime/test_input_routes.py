"""The routes around the files a person gives Espresso."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.matcha_work import assistant as routes
from app.matcha.services.matcha_work.agent_runtime import inputs
from app.werk.routes import channels
from app.werk.services.channel_access import ChannelScope

from .helpers import FakeConn, connection


def _user():
    return SimpleNamespace(id=uuid4(), role="individual", email="ana@example.com")


class _Upload:
    def __init__(self, data: bytes, filename: str, content_type: str = "application/pdf"):
        self.filename, self.content_type, self._data, self._pos = filename, content_type, data, 0

    async def read(self, n: int = -1) -> bytes:
        size = n if n and n > 0 else len(self._data)
        chunk = self._data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


@pytest.fixture
def assistant_channel(monkeypatch):
    company = uuid4()
    conn = FakeConn([("assistant_user_id = $2", company)])
    monkeypatch.setattr(channels, "get_connection", connection(conn))
    monkeypatch.setattr(channels, "_require_channel_capability",
                        AsyncMock(return_value=SimpleNamespace(scope=ChannelScope.ASSISTANT)))
    public = AsyncMock()
    monkeypatch.setattr(channels, "get_storage", lambda: SimpleNamespace(upload_file=public))
    saved = AsyncMock(return_value=[{"url": "espresso-input:1", "filename": "cv.pdf",
                                     "content_type": "application/pdf", "size": 3, "input_id": "1"}])
    monkeypatch.setattr(inputs, "save", saved)
    return SimpleNamespace(company=company, conn=conn, public=public, saved=saved)


@pytest.mark.asyncio
async def test_files_in_a_private_conversation_go_to_private_storage(assistant_channel):
    user, channel = _user(), uuid4()
    out = await channels.upload_channel_files(channel, [_Upload(b"pdf", "cv.pdf")], user)
    assert out["attachments"][0]["url"] == "espresso-input:1"
    kwargs = assistant_channel.saved.await_args.kwargs
    assert kwargs["user_id"] == user.id and kwargs["company_id"] == assistant_channel.company
    assert kwargs["channel_id"] == channel and kwargs["uploads"][0].data == b"pdf"
    assistant_channel.public.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_conversation_uploads_have_espressos_limits(assistant_channel):
    with pytest.raises(HTTPException) as exc:
        await channels.upload_channel_files(uuid4(), [_Upload(b"x", f"{i}.txt") for i in range(6)], _user())
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await channels.upload_channel_files(
            uuid4(), [_Upload(b"x" * (inputs.MAX_FILE_BYTES + 1), "big.pdf")], _user())
    assert exc.value.status_code == 413
    assistant_channel.saved.side_effect = inputs.InputError("setup.zip: Espresso takes PDF")
    with pytest.raises(HTTPException) as exc:
        await channels.upload_channel_files(uuid4(), [_Upload(b"x", "setup.zip")], _user())
    assert exc.value.status_code == 400 and "setup.zip" in exc.value.detail
    assistant_channel.saved.side_effect = RuntimeError("S3 not configured for private uploads")
    with pytest.raises(HTTPException) as exc:
        await channels.upload_channel_files(uuid4(), [_Upload(b"x", "a.txt")], _user())
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_someone_elses_conversation_is_refused(assistant_channel):
    assistant_channel.conn.on("assistant_user_id = $2", None)
    with pytest.raises(HTTPException) as exc:
        await channels.upload_channel_files(uuid4(), [_Upload(b"x", "a.txt")], _user())
    assert exc.value.status_code == 403
    assistant_channel.saved.assert_not_awaited()


@pytest.mark.asyncio
async def test_file_links_and_deletes(monkeypatch):
    user, file_id = _user(), uuid4()
    monkeypatch.setattr(inputs, "presigned", AsyncMock(return_value={"url": "https://signed.test/x"}))
    assert (await routes.get_input_url(file_id, user))["url"] == "https://signed.test/x"
    assert inputs.presigned.await_args.kwargs == {"input_id_value": file_id, "user_id": user.id}
    inputs.presigned.return_value = None
    with pytest.raises(HTTPException) as exc:
        await routes.get_input_url(file_id, user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(inputs, "delete", AsyncMock(return_value=True))
    assert await routes.delete_input(file_id, user) is None
    inputs.delete.return_value = False
    with pytest.raises(HTTPException) as exc:
        await routes.delete_input(file_id, user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_message_deletes_the_files_it_gave_espresso(monkeypatch):
    from datetime import datetime, timezone

    from app.werk.routes import channels_ws

    user, channel_id, message_id = _user(), uuid4(), uuid4()
    conn = FakeConn([
        ("FROM channel_messages m", {"id": message_id, "sender_id": user.id, "deleted_at": None,
                                     "created_at": datetime.now(timezone.utc), "message_type": "user",
                                     "reply_metadata": None}),
        ("SELECT role FROM channel_members", "owner"),
        ("DELETE FROM mw_agent_inputs WHERE message_id", [{"storage_path": "s3://p/cv.pdf"}]),
    ])
    monkeypatch.setattr(channels, "get_connection", connection(conn))
    monkeypatch.setattr(channels, "_require_channel_capability", AsyncMock())
    monkeypatch.setattr(channels_ws, "broadcast_message_deleted", AsyncMock())
    removed = AsyncMock()
    monkeypatch.setattr(inputs, "remove_stored", removed)

    assert (await channels.delete_channel_message(channel_id, message_id, user))["ok"] is True
    assert conn.ran("SET deleted_at = NOW()")
    assert conn.ran("DELETE FROM mw_agent_inputs")[0][2] == (message_id,)
    removed.assert_awaited_once_with(["s3://p/cv.pdf"])
