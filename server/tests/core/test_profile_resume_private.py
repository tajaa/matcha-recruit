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


def _row(url, text="text"):
    return {"filename": "cv.pdf", "resume_url": url, "raw_text": text, "parsed_data": {"current_title": "COO"},
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


TEXT = "Haley Rivera. Senior software engineer, platform and AI. Seven years at startups. " * 2


@pytest.mark.asyncio
async def test_the_owner_reads_the_text_espresso_uses(wired):
    user = SimpleNamespace(id=uuid4())
    wired.conn.on("FROM user_resumes WHERE user_id", _row("s3://private/profile_resumes/u/cv.pdf", TEXT))
    out = await routes.get_my_resume(user)
    assert out.text == TEXT and out.filename == "cv.pdf"
    assert "raw_text" in wired.conn.ran("FROM user_resumes")[0][1]
    wired.conn.on("FROM user_resumes WHERE user_id", None)
    assert await routes.get_my_resume(user) is None


@pytest.mark.asyncio
async def test_a_recruiter_never_gets_the_text(wired):
    recruiter = SimpleNamespace(id=uuid4())
    wired.conn.on("FROM channel_job_applications", 1)
    wired.conn.on("recruiter_until > NOW()", True)
    wired.conn.on("FROM user_resumes WHERE user_id", _row("s3://private/x.pdf", TEXT))
    out = await routes.get_user_resume_as_recruiter(str(uuid4()), recruiter)
    assert not hasattr(out, "text") and "text" not in out.model_dump()
    assert "raw_text" not in wired.conn.ran("FROM user_resumes")[0][1]


@pytest.mark.asyncio
async def test_editing_the_text_rereads_the_fields_and_keeps_the_file(wired, monkeypatch):
    user = SimpleNamespace(id=uuid4())
    parse = AsyncMock(return_value={"current_title": "Staff Engineer"})
    monkeypatch.setattr(routes, "parse_resume_text", parse)
    wired.conn.on("SELECT 1 FROM user_resumes", 1)
    wired.conn.on("UPDATE user_resumes", lambda uid, text, parsed: {
        **_row("s3://private/x.pdf", text), "parsed_data": parsed or {"current_title": "COO"}})
    out = await routes.update_my_resume_text(routes.ResumeTextUpdate(text=f"  {TEXT}  "), user)
    assert out.text == TEXT.strip() and out.parsed_data == {"current_title": "Staff Engineer"}
    parse.assert_awaited_once_with(TEXT.strip())
    update = wired.conn.ran("UPDATE user_resumes")[0]
    assert "resume_url" not in update[1].split("RETURNING")[0]  # the original file stays
    assert update[2][0] == user.id


@pytest.mark.asyncio
async def test_a_failed_reread_keeps_the_typed_text_and_the_old_fields(wired, monkeypatch):
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(routes, "parse_resume_text", AsyncMock(side_effect=routes.ResumeParseError("down")))
    wired.conn.on("SELECT 1 FROM user_resumes", 1)
    wired.conn.on("UPDATE user_resumes", lambda uid, text, parsed: {**_row("s3://private/x.pdf", text)})
    out = await routes.update_my_resume_text(routes.ResumeTextUpdate(text=TEXT), user)
    assert out.text == TEXT.strip() and out.parsed_data == {"current_title": "COO"}
    assert wired.conn.ran("UPDATE user_resumes")[0][2][2] is None  # COALESCE keeps parsed_data


@pytest.mark.asyncio
async def test_editing_needs_a_resume_and_real_text(wired):
    from fastapi import HTTPException
    from pydantic import ValidationError

    user = SimpleNamespace(id=uuid4())
    with pytest.raises(HTTPException) as exc:
        await routes.update_my_resume_text(routes.ResumeTextUpdate(text=TEXT), user)
    assert exc.value.status_code == 404
    with pytest.raises(ValidationError):
        routes.ResumeTextUpdate(text="too short")
    with pytest.raises(HTTPException) as exc:
        await routes.update_my_resume_text(routes.ResumeTextUpdate(text=" " * 40 + "x" * 20), user)
    assert exc.value.status_code == 422
