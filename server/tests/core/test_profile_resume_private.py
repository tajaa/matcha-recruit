"""A profile résumé is stored privately and only ever handed out as a short link."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.routes.identity import profile_resume as routes
from tests.agent_runtime.helpers import FakeConn, connection


class _Storage:
    def __init__(self):
        self.private = []
        self.deleted_private = []
        self.deleted_public = []

    async def upload_private_file(self, data, filename, prefix="documents", content_type=None, bucket=None):
        path = f"s3://private/{prefix}/{filename}"
        self.private.append((path, data))
        return path

    async def upload_file(self, *_a, **_k):  # never used for a résumé any more
        raise AssertionError("a résumé must not be uploaded publicly")

    def get_presigned_download_url(self, path, expires_in=900):
        return f"https://signed.test/{path}?ttl={expires_in}"

    async def delete_private_file(self, path):
        self.deleted_private.append(path)
        return True

    async def delete_file(self, path):
        self.deleted_public.append(path)
        return True


class _Upload:
    def __init__(self, data, filename="cv.pdf", content_type="application/pdf"):
        self.data, self.filename, self.content_type = data, filename, content_type

    async def read(self):
        return self.data


@pytest.fixture
def wired(monkeypatch):
    storage = _Storage()
    monkeypatch.setattr(routes, "get_storage", lambda: storage)
    conn = FakeConn()
    monkeypatch.setattr(routes, "get_connection", connection(conn))
    monkeypatch.setattr(routes, "parse_resume_file", AsyncMock(return_value=({"current_title": "COO"}, "text")))
    return SimpleNamespace(storage=storage, conn=conn)


def _row(url):
    return {"filename": "cv.pdf", "resume_url": url, "parsed_data": {"current_title": "COO"},
            "updated_at": datetime(2026, 10, 14, tzinfo=timezone.utc)}


def test_the_link_is_short_lived_for_a_private_file(wired):
    assert routes._resume_link("s3://private/profile_resumes/u/cv.pdf") == (
        "https://signed.test/s3://private/profile_resumes/u/cv.pdf?ttl=900")
    assert routes._resume_link("https://cdn.test/old.pdf") == "https://cdn.test/old.pdf"
    assert routes._resume_link("") == "" and routes._resume_link(None) == ""


@pytest.mark.asyncio
async def test_upload_is_private_and_replaces_the_old_file(wired):
    user = SimpleNamespace(id=uuid4())
    wired.conn.on("SELECT resume_url FROM user_resumes", "https://cdn.test/old.pdf")
    wired.conn.on("INSERT INTO user_resumes", lambda *args: _row(args[2]))
    out = await routes.upload_my_resume(_Upload(b"%PDF"), user)
    [(path, data)] = wired.storage.private
    assert path == f"s3://private/profile_resumes/{user.id}/cv.pdf" and data == b"%PDF"
    assert out.resume_url == f"https://signed.test/{path}?ttl=900"
    assert wired.storage.deleted_public == ["https://cdn.test/old.pdf"]


@pytest.mark.asyncio
async def test_delete_removes_the_stored_file(wired):
    user = SimpleNamespace(id=uuid4())
    wired.conn.on("DELETE FROM user_resumes", "s3://private/profile_resumes/u/cv.pdf")
    await routes.delete_my_resume(user)
    assert wired.storage.deleted_private == ["s3://private/profile_resumes/u/cv.pdf"]
    wired.conn.on("DELETE FROM user_resumes", None)
    await routes.delete_my_resume(user)
    assert len(wired.storage.deleted_private) == 1


@pytest.mark.asyncio
async def test_a_failed_cleanup_never_fails_the_request(wired, monkeypatch):
    async def broken(_path):
        raise RuntimeError("s3 down")

    monkeypatch.setattr(wired.storage, "delete_private_file", broken)
    await routes._delete_stored("s3://private/x")
