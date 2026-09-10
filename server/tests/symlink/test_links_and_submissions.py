"""Pure-logic + SQL-shape tests for links.py / submissions.py (no DB, no S3).

Fake connections capture the SQL so the shape of a write can be asserted
without a live Postgres — the merge on `employees.emergency_contact` and the
reminder reset on resend are both invariants worth pinning.
"""
import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.matcha.models.symlink import DEFAULT_EXPIRY_DAYS, MAX_EXPIRY_DAYS
from app.matcha.services._shared import public_links
from app.matcha.services.symlink import links, submissions


def _now():
    return datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def test_expiry_days_of_recovers_the_senders_window():
    now = _now()
    row = {"last_sent_at": now, "created_at": now - timedelta(days=5), "expires_at": now + timedelta(days=2)}
    assert links.expiry_days_of(row) == 2
    # Never sent yet: the window runs from creation.
    row = {"last_sent_at": None, "created_at": now, "expires_at": now + timedelta(days=14, seconds=-3)}
    assert links.expiry_days_of(row) == 14
    # Clamped to the model's bounds; missing data falls back to the default.
    row = {"last_sent_at": now, "created_at": now, "expires_at": now + timedelta(days=400)}
    assert links.expiry_days_of(row) == MAX_EXPIRY_DAYS
    assert links.expiry_days_of({"last_sent_at": None, "created_at": None, "expires_at": None}) == DEFAULT_EXPIRY_DAYS
    row = {"last_sent_at": now, "created_at": now, "expires_at": now + timedelta(hours=1)}
    assert links.expiry_days_of(row) == 1


def test_rotate_token_persists_the_quoted_expiry_and_resets_the_reminder():
    captured = {}

    class Conn:
        async def fetchrow(self, sql, *params):
            captured["sql"] = sql
            captured["params"] = params
            return {"ok": True}

    expires_at = _now() + timedelta(days=2)
    asyncio.run(links.rotate_token(Conn(), "L", "C", token="tok", expires_at=expires_at))
    assert captured["params"][3] is expires_at
    assert "reminder_sent_at = NULL" in captured["sql"]
    assert "last_sent_at = NOW()" in captured["sql"]


def test_public_link_from_settings_ignores_request_headers(monkeypatch):
    from app import config

    class S:
        app_base_url = "https://hey-matcha.com/"

    monkeypatch.setattr(config, "get_settings", lambda: S())
    assert public_links.public_link_from_settings("abc", "sym") == "https://hey-matcha.com/sym/abc"
    assert public_links.public_link_from_settings("id1", "app/symlink") == "https://hey-matcha.com/app/symlink/id1"


def test_public_submit_and_worker_do_not_build_urls_from_headers():
    """Both paths leave the process (email/worker); neither may read X-Forwarded-Host."""
    from pathlib import Path

    server = Path(__file__).resolve().parents[2]
    public_src = (server / "app/matcha/routes/intake/symlink_public.py").read_text()
    worker_src = (server / "app/workers/tasks/symlink.py").read_text()
    for src in (public_src, worker_src):
        assert "public_link_from_settings" in src
        assert "build_public_link(" not in src
    assert "COALESCE(s.last_sent_at, s.sent_at) <= $1" in worker_src


def test_info_update_merges_emergency_contact_instead_of_replacing():
    captured = {}

    class Conn:
        async def fetchval(self, sql, *params):
            captured["sql"] = sql
            captured["params"] = params
            return "emp-1"

    link_row = {"employee_id": "emp-1", "company_id": "co-1", "kind": "info_update"}
    submission = {"fields": {"phone": " 555-0100 ", "emergency_contact_name": "Ana Ruiz", "emergency_contact_phone": "555-0199"}}
    ref = asyncio.run(submissions._apply_info_update(Conn(), link_row, submission))
    assert ref["updated_columns"] == ["emergency_contact", "phone"]
    sql = captured["sql"]
    assert "emergency_contact = COALESCE(emergency_contact, '{}'::jsonb) || $4::jsonb" in sql
    assert "phone = $3" in sql
    assert captured["params"][2] == "555-0100"
    assert json.loads(captured["params"][3]) == {"name": "Ana Ruiz", "phone": "555-0199"}


def test_apply_credential_upload_carries_paths_not_bytes():
    """Post-commit extraction takes the S3 path; the request must not retain
    the attachment bytes across the response boundary."""
    sig = inspect.signature(submissions.run_credential_extraction)
    assert list(sig.parameters) == ["doc_id", "file_path", "mime", "document_type"]
    src = inspect.getsource(submissions._apply_credential_upload)
    assert "read_bytes" not in src and "upload_private_file" not in src


def test_copy_credential_objects_discards_partial_copies_on_failure(monkeypatch):
    uploaded, discarded = [], []

    class Storage:
        async def upload_private_file(self, content, name, *, prefix, content_type):
            path = f"{prefix}/{name}"
            uploaded.append(path)
            return path

    import app.core.services.storage as storage_mod
    monkeypatch.setattr(storage_mod, "get_storage", lambda: Storage())

    async def read_bytes(path):
        return None if path.endswith("second") else b"bytes"

    async def discard(path):
        discarded.append(path)

    monkeypatch.setattr(submissions.att, "read_bytes", read_bytes)
    monkeypatch.setattr(submissions.att, "discard", discard)

    rows = [
        {"id": "a1", "storage_path": "s/first", "file_name": "first.pdf", "content_type": "application/pdf"},
        {"id": "a2", "storage_path": "s/second", "file_name": "second.pdf", "content_type": "application/pdf"},
    ]
    link_row = {"company_id": "co", "employee_id": "emp"}
    with pytest.raises(submissions.ApplyError):
        asyncio.run(submissions.copy_credential_objects(link_row, rows))
    assert uploaded == ["employee-credentials/co/emp/first.pdf"]
    assert discarded == uploaded


def test_run_credential_extraction_marks_failed_on_throw(monkeypatch):
    marks = []

    async def read_bytes(path):
        return b"pdf"

    async def boom(*a, **k):
        raise RuntimeError("gemini down")

    async def mark(doc_id, status, result=None):
        marks.append((doc_id, status))

    import app.core.services.credential_extraction as ce
    monkeypatch.setattr(submissions.att, "read_bytes", read_bytes)
    monkeypatch.setattr(ce, "extract_credential_info", boom)
    monkeypatch.setattr(submissions, "_mark_extraction", mark)
    asyncio.run(submissions.run_credential_extraction("d1", "p", "application/pdf", "other"))
    assert marks == [("d1", "failed")]
