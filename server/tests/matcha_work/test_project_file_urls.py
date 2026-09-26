"""Project file responses give browsers a usable URL without exposing raw S3 paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.routes.matcha_work import projects, _shared
from app.matcha.services.matcha_work import project_file_service


@pytest.mark.asyncio
async def test_project_file_list_signs_storage_paths(monkeypatch):
    project_id = uuid4()
    raw = {"id": str(uuid4()), "storage_url": "s3://private-bucket/file.pdf", "filename": "file.pdf"}
    access = AsyncMock(return_value=({}, "owner"))
    list_files = AsyncMock(return_value=[raw])
    presign = lambda _url, expires_in: f"https://files.example.test/file.pdf?expires={expires_in}"
    monkeypatch.setattr(projects, "_verify_project_access", access)
    monkeypatch.setattr(project_file_service, "list_project_files", list_files)
    monkeypatch.setattr(_shared, "get_storage", lambda: SimpleNamespace(get_presigned_download_url=presign))

    result = await projects.list_project_files_endpoint(project_id, SimpleNamespace(id=uuid4()))

    assert result[0]["storage_url"] == "https://files.example.test/file.pdf?expires=3600"
    assert raw["storage_url"] == "s3://private-bucket/file.pdf"
    access.assert_awaited_once()
    list_files.assert_awaited_once_with(project_id)


@pytest.mark.asyncio
async def test_project_file_upload_returns_signed_url(monkeypatch):
    project_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    raw = {"id": str(uuid4()), "storage_url": "s3://private-bucket/new.pdf", "filename": "new.pdf"}
    store = AsyncMock(return_value=raw)
    presign = lambda _url, expires_in: f"https://files.example.test/new.pdf?expires={expires_in}"
    monkeypatch.setattr(projects, "_verify_project_access", AsyncMock(return_value=({"company_id": "co-1"}, "owner")))
    monkeypatch.setattr(project_file_service, "validate_and_store_project_upload", store)
    monkeypatch.setattr(_shared, "get_storage", lambda: SimpleNamespace(get_presigned_download_url=presign))

    upload = SimpleNamespace(filename="new.pdf")
    result = await projects.upload_project_file(project_id, upload, None, None, user)

    assert result["storage_url"] == "https://files.example.test/new.pdf?expires=3600"
    assert raw["storage_url"] == "s3://private-bucket/new.pdf"
    assert store.await_args.kwargs["prefix"] == f"matcha-work/co-1/{project_id}/files"
