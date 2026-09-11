"""project_file_service upload policy: one whitelist / size limit / sink for
files a person uploads and for bytes the server renders itself (the email
snapshots an `email` kanban card carries)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.services.matcha_work import project_file_service as pfs


@pytest.fixture
def sink(monkeypatch):
    upload = AsyncMock(return_value="https://cdn.example.com/f")
    add = AsyncMock(side_effect=lambda **kw: kw)
    monkeypatch.setattr(pfs, "get_storage", lambda: SimpleNamespace(upload_file=upload))
    monkeypatch.setattr(pfs, "add_project_file", add)
    return SimpleNamespace(upload=upload, add=add)


def _store(content=b"# hi\n", **overrides):
    kwargs = {
        "filename": "email-abc.md",
        "content_type": "text/markdown",
        "project_id": uuid4(),
        "uploaded_by": uuid4(),
        "prefix": "p/x",
        **overrides,
    }
    return pfs.store_project_file_bytes(content, **kwargs)


@pytest.mark.asyncio
async def test_store_bytes_uploads_and_records(sink):
    task_id = uuid4()
    row = await _store(task_id=task_id)
    sink.upload.assert_awaited_once_with(
        b"# hi\n", "email-abc.md", prefix="p/x", content_type="text/markdown"
    )
    assert row["storage_url"] == "https://cdn.example.com/f"
    assert row["file_size"] == 5
    assert row["task_id"] == task_id
    assert row["folder_id"] is None and row["element_id"] is None


@pytest.mark.asyncio
async def test_store_bytes_refuses_a_type_off_the_whitelist(sink):
    with pytest.raises(HTTPException) as exc:
        await _store(filename="payload.exe")
    assert exc.value.status_code == 400
    sink.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_bytes_refuses_an_oversize_body(sink, monkeypatch):
    monkeypatch.setattr(pfs, "PROJECT_FILE_MAX_BYTES", 4)
    with pytest.raises(HTTPException) as exc:
        await _store(content=b"12345")
    assert exc.value.status_code == 400
    sink.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_bytes_400s_on_a_bad_folder_id(sink):
    with pytest.raises(HTTPException) as exc:
        await _store(folder_id="not-a-uuid")
    assert exc.value.status_code == 400
    sink.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_refuses_a_bad_type_before_reading_the_body(sink):
    file = SimpleNamespace(filename="x.exe", content_type=None, read=AsyncMock(return_value=b"x"))
    with pytest.raises(HTTPException):
        await pfs.validate_and_store_project_upload(
            file, project_id=uuid4(), uploaded_by=uuid4(), prefix="p"
        )
    file.read.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_goes_through_the_bytes_path(sink):
    folder_id = uuid4()
    file = SimpleNamespace(
        filename="notes.md", content_type="text/markdown", read=AsyncMock(return_value=b"hello")
    )
    row = await pfs.validate_and_store_project_upload(
        file, project_id=uuid4(), uploaded_by=uuid4(), prefix="p", folder_id=str(folder_id)
    )
    assert row["filename"] == "notes.md"
    assert row["file_size"] == 5
    assert row["folder_id"] == folder_id
    sink.upload.assert_awaited_once_with(b"hello", "notes.md", prefix="p", content_type="text/markdown")
