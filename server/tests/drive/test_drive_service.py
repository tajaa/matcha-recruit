"""Matcha Drive service — validation, capability enforcement, system-folder
invariants, search scoping. No DB: `QueryConn` dispatches on SQL text.

    cd server && ./venv/bin/python -m pytest tests/drive/test_drive_service.py -q
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.services.drive import drive_service as svc
from app.matcha.services.drive.drive_access import DriveActor, DriveCap
from app.matcha.services.drive.drive_service import DriveError
from tests._helpers.routes import QueryConn as _BaseConn, Queue


class QueryConn(_BaseConn):
    """Every drive write runs in a transaction; the fake is its own context."""

    def transaction(self):
        return self


TxConn = QueryConn

COMPANY = uuid4()
NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)
ALL = frozenset(DriveCap)




def actor(level="operator"):
    return DriveActor(user_id=uuid4(), work_level=level)


def folder(space="general", system_key=None, parent_id=None, **kw):
    base = {
        "id": uuid4(), "company_id": COMPANY, "parent_id": parent_id, "space": space,
        "name": "Folder", "system_key": system_key, "created_by": None,
        "created_at": NOW, "updated_at": NOW,
    }
    base.update(kw)
    return base


def file_row(folder_id, space="general", **kw):
    base = {
        "id": uuid4(), "company_id": COMPANY, "folder_id": folder_id, "filename": "a.pdf",
        "content_type": "application/pdf", "file_size": 10, "text_status": "ok",
        "source": "upload", "linked_type": None, "linked_id": None, "uploaded_by": None,
        "created_at": NOW, "updated_at": NOW, "storage_path": "s3://b/k.pdf", "space": space,
    }
    base.update(kw)
    return base


def patch_caps(monkeypatch, mapping):
    """mapping: folder_id -> (folder dict, caps)."""
    async def fake(conn, *, company_id, folder_id, actor):
        if folder_id not in mapping:
            raise DriveError(404, "That folder doesn't exist.")
        return mapping[folder_id]
    monkeypatch.setattr(svc, "_folder_with_caps", fake)


# ── Pure ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("report.PDF", "report.pdf"),
    ("../../etc/passwd.txt", "passwd.txt"),
    ("C:\\Users\\gm\\write up.docx", "write up.docx"),
    ("a\x00b\x1f:c?.md", "a b c.md"),
    ("", "file"),
    ("...", "file"),
    ("   .pdf", "file.pdf"),
])
def test_sanitize_filename(raw, expected):
    assert svc.sanitize_filename(raw) == expected


def test_sanitize_filename_caps_length_and_keeps_extension():
    out = svc.sanitize_filename("x" * 400 + ".pdf")
    assert len(out) <= svc.MAX_FILENAME_CHARS
    assert out.endswith(".pdf")


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_clean_folder_name_rejects(name):
    with pytest.raises(DriveError):
        svc.clean_folder_name(name)


def test_validate_upload_rules():
    assert svc.validate_upload("a.pdf", b"%PDF-1.7 ...") == ("a.pdf", "application/pdf")
    for name, data, status in [
        ("a.exe", b"MZ", 400),
        ("a.pdf", b"", 400),
        ("a.pdf", b"<html>", 400),
        ("a.docx", b"not a zip", 400),
        ("a.txt", b"x" * (svc.MAX_FILE_BYTES + 1), 413),
    ]:
        with pytest.raises(DriveError) as exc:
            svc.validate_upload(name, data)
        assert exc.value.status == status


def test_extract_text_statuses(monkeypatch):
    assert svc._extract_text_sync(b"\x89PNG", "a.png") == (None, "unsupported")
    assert svc._extract_text_sync(b"hello \x00world", "a.txt") == ("hello world", "ok")
    assert svc._extract_text_sync(b"   ", "a.txt") == (None, "empty")

    from app.matcha.services.er import er_document_parser

    def boom(self, data, name):
        raise RuntimeError("corrupt")
    monkeypatch.setattr(er_document_parser.ERDocumentParser, "extract_text_from_bytes", boom)
    assert svc._extract_text_sync(b"%PDF", "a.pdf") == (None, "failed")


def test_extract_text_is_capped():
    text, status = svc._extract_text_sync(b"a" * (svc.MAX_TEXT_CHARS + 50), "a.txt")
    assert status == "ok" and len(text) == svc.MAX_TEXT_CHARS


@pytest.mark.asyncio
async def test_prepare_file_hashes_and_extracts():
    prepared = await svc.prepare_file("notes.txt", b"policy text")
    assert prepared.text_status == "ok"
    assert prepared.extracted_text == "policy text"
    assert len(prepared.sha256) == 64
    assert prepared.content_type == "text/plain"


def test_like_escape():
    assert svc._like_escape("50%_off\\") == "50\\%\\_off\\\\"


# ── Capability resolution ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_folder_with_caps_unions_chain_grants():
    f = folder(space="hr")
    conn = QueryConn(
        fetch={"WITH RECURSIVE chain": [
            {"id": f["id"], "depth": 0, "name": "Drafts", "permission": "upload"},
            {"id": uuid4(), "depth": 1, "name": "HR", "permission": None},
        ]},
        fetchrow={"FROM drive_folders WHERE id": f},
    )
    _, caps = await svc._folder_with_caps(conn, company_id=COMPANY, folder_id=f["id"], actor=actor())
    assert caps == {DriveCap.ADD}


@pytest.mark.asyncio
async def test_folder_with_caps_missing_is_404():
    conn = QueryConn(fetch={"WITH RECURSIVE chain": []})
    with pytest.raises(DriveError) as exc:
        await svc._folder_with_caps(conn, company_id=COMPANY, folder_id=uuid4(), actor=actor())
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_system_path_has_every_cap():
    f = folder()
    conn = QueryConn(fetch={"WITH RECURSIVE chain": [{"id": f["id"], "depth": 0, "name": "Company", "permission": None}]},
                     fetchrow={"FROM drive_folders WHERE id": f})
    _, caps = await svc._folder_with_caps(conn, company_id=COMPANY, folder_id=f["id"], actor=None)
    assert caps == ALL


@pytest.mark.asyncio
async def test_no_caps_reads_as_not_found(monkeypatch):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, frozenset())})
    with pytest.raises(DriveError) as exc:
        await svc.list_folder(QueryConn(), company_id=COMPANY, folder_id=f["id"], actor=actor())
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_drop_box_lists_nothing(monkeypatch):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.ADD}))})
    out = await svc.list_folder(QueryConn(), company_id=COMPANY, folder_id=f["id"], actor=actor())
    assert out["folder"]["caps"] == ["add"]
    assert out["files"] == [] and out["folders"] == [] and out["breadcrumbs"] == []


@pytest.mark.asyncio
async def test_list_folder_returns_children_and_files(monkeypatch):
    f = folder()
    child = folder(parent_id=f["id"], name="Policies")
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.LIST, DriveCap.READ}))})
    conn = QueryConn(fetch={
        "WITH RECURSIVE chain": [{"id": f["id"], "name": "Company"}],
        "WHERE parent_id = $1": [child],
        "FROM drive_folder_grants": [{"folder_id": child["id"], "permission": "edit"}],
        "FROM drive_files f": [file_row(f["id"])],
    })
    out = await svc.list_folder(conn, company_id=COMPANY, folder_id=f["id"], actor=actor("member"))
    assert [c["name"] for c in out["folders"]] == ["Policies"]
    assert "manage" in out["folders"][0]["caps"]
    assert len(out["files"]) == 1
    assert "storage_path" not in out["files"][0]


# ── Folders ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_folder_requires_manage(monkeypatch):
    parent = folder(space="hr")
    patch_caps(monkeypatch, {parent["id"]: (parent, frozenset({DriveCap.LIST, DriveCap.READ}))})
    with pytest.raises(DriveError) as exc:
        await svc.create_folder(QueryConn(), company_id=COMPANY, parent_id=parent["id"], name="X", actor=actor())
    assert exc.value.status == 403


@pytest.mark.asyncio
async def test_create_folder_inherits_parent_space_and_audits_hr(monkeypatch):
    parent = folder(space="hr")
    patch_caps(monkeypatch, {parent["id"]: (parent, ALL)})
    conn = QueryConn(fetchrow={"INSERT INTO drive_folders": folder(space="hr", name="Cases")})
    out = await svc.create_folder(conn, company_id=COMPANY, parent_id=parent["id"], name=" Cases ", actor=actor("admin"))
    assert out["space"] == "hr"
    assert conn.args_for("INSERT INTO drive_folders")[2:4] == ("hr", "Cases")
    assert conn.sql_for("execute") and "drive_audit_log" in conn.sql_for("execute")[0]


@pytest.mark.asyncio
async def test_create_folder_duplicate_is_409(monkeypatch):
    import asyncpg

    parent = folder()
    patch_caps(monkeypatch, {parent["id"]: (parent, ALL)})

    class Dup(QueryConn):
        async def fetchrow(self, sql, *args):
            raise asyncpg.UniqueViolationError("dup")
    with pytest.raises(DriveError) as exc:
        await svc.create_folder(Dup(), company_id=COMPANY, parent_id=parent["id"], name="X", actor=actor("admin"))
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_system_folder_cannot_be_renamed_or_deleted(monkeypatch):
    f = folder(space="hr", system_key="hr_discipline")
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    with pytest.raises(DriveError):
        await svc.update_folder(QueryConn(), company_id=COMPANY, folder_id=f["id"], actor=actor("admin"), name="X")
    with pytest.raises(DriveError):
        await svc.delete_folder(QueryConn(), company_id=COMPANY, folder_id=f["id"], actor=actor("admin"))


@pytest.mark.asyncio
async def test_folder_move_across_spaces_refused(monkeypatch):
    f = folder(space="hr")
    target = folder(space="general")
    patch_caps(monkeypatch, {f["id"]: (f, ALL), target["id"]: (target, ALL)})
    with pytest.raises(DriveError) as exc:
        await svc.update_folder(QueryConn(), company_id=COMPANY, folder_id=f["id"], actor=actor("admin"), parent_id=target["id"])
    assert "between" in exc.value.detail


@pytest.mark.asyncio
async def test_folder_move_into_own_descendant_refused(monkeypatch):
    f = folder()
    child = folder(parent_id=f["id"])
    patch_caps(monkeypatch, {f["id"]: (f, ALL), child["id"]: (child, ALL)})
    conn = QueryConn(fetchval={"WITH RECURSIVE chain": True})
    with pytest.raises(DriveError) as exc:
        await svc.update_folder(conn, company_id=COMPANY, folder_id=f["id"], actor=actor("admin"), parent_id=child["id"])
    assert "inside itself" in exc.value.detail


@pytest.mark.asyncio
async def test_delete_non_empty_folder_refused(monkeypatch):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    async def seeded(conn, company_id):
        return {"general_root": uuid4(), "hr_root": uuid4()}
    monkeypatch.setattr(svc, "ensure_system_folders", seeded)
    conn = QueryConn(fetchval={"FOR UPDATE": f["id"], "EXISTS (SELECT 1 FROM drive_folders WHERE parent_id": True})
    with pytest.raises(DriveError) as exc:
        await svc.delete_folder(conn, company_id=COMPANY, folder_id=f["id"], actor=actor("admin"))
    assert exc.value.status == 409
    # The emptiness check runs AFTER the row lock, inside the transaction.
    sqls = conn.sql_for("fetchval")
    assert "FOR UPDATE" in sqls[0] and "EXISTS" in sqls[1]


@pytest.mark.asyncio
async def test_delete_folder_rehomes_soft_deleted_files(monkeypatch):
    f = folder(space="hr")
    root = uuid4()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    async def seeded(conn, company_id):
        return {"hr_root": root, "general_root": uuid4()}
    monkeypatch.setattr(svc, "ensure_system_folders", seeded)
    conn = TxConn(fetchval={"FOR UPDATE": f["id"], "EXISTS (SELECT 1 FROM drive_folders WHERE parent_id": False})
    await svc.delete_folder(conn, company_id=COMPANY, folder_id=f["id"], actor=actor("admin"))
    assert conn.args_for("UPDATE drive_files SET folder_id") == (f["id"], root)
    assert any("DELETE FROM drive_folders" in s for s in conn.sql_for("execute"))


# ── System folders ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_system_folders_short_circuits_when_seeded():
    rows = [{"system_key": k, "id": uuid4()} for k in svc.SYSTEM_FOLDERS]
    conn = QueryConn(fetch={"system_key IS NOT NULL": rows})
    out = await svc.ensure_system_folders(conn, COMPANY)
    assert set(out) == set(svc.SYSTEM_FOLDERS)
    assert conn.sql_for("execute") == []


@pytest.mark.asyncio
async def test_ensure_system_folders_seeds_and_grants_hr_approvers_once():
    conn = TxConn(
        fetch={"system_key IS NOT NULL": Queue([[], []])},
        fetchval={"UPDATE drive_folders SET system_key": None, "INSERT INTO drive_folders": uuid4()},
    )
    out = await svc.ensure_system_folders(conn, COMPANY)
    assert set(out) == set(svc.SYSTEM_FOLDERS)
    grants = [s for s in conn.sql_for("execute") if "drive_folder_grants" in s]
    assert len(grants) == 1 and "is_hr_approver" in grants[0]
    assert conn.args_for("INSERT INTO drive_folder_grants")[1] == out["hr_root"]


@pytest.mark.asyncio
async def test_ensure_system_folders_no_grant_seed_when_hr_root_exists():
    hr_root = uuid4()
    conn = TxConn(
        fetch={"system_key IS NOT NULL": Queue([
            [{"system_key": "hr_root", "id": hr_root}],
            [{"system_key": "hr_root", "id": hr_root}],
        ])},
        fetchval={"UPDATE drive_folders SET system_key": None, "INSERT INTO drive_folders": uuid4()},
    )
    out = await svc.ensure_system_folders(conn, COMPANY)
    assert out["hr_root"] == hr_root
    assert not any("drive_folder_grants" in s for s in conn.sql_for("execute"))


# ── Files ───────────────────────────────────────────────────────────────


class FakeStorage:
    def __init__(self, url="https://s3/presigned"):
        self.uploaded = []
        self.deleted = []
        self.url = url

    async def upload_private_file(self, data, filename, prefix, content_type=None):
        self.uploaded.append((filename, prefix, content_type))
        return f"s3://private/{prefix}/x"

    async def delete_private_file(self, path):
        self.deleted.append(path)
        return True

    def get_presigned_download_url(self, path, expires_in=900):
        return self.url

    async def download_file(self, path):
        return b"bytes"


@pytest.fixture
def storage(monkeypatch):
    from app.core.services import storage as storage_mod

    fake = FakeStorage()
    monkeypatch.setattr(storage_mod, "get_storage", lambda: fake)
    return fake


def prepared(name="draft.pdf"):
    return svc.PreparedFile(filename=name, data=b"%PDF-1.7", content_type="application/pdf",
                            sha256="0" * 64, extracted_text="text", text_status="ok")


@pytest.mark.asyncio
async def test_store_file_requires_add(monkeypatch, storage):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.LIST, DriveCap.READ}))})
    with pytest.raises(DriveError) as exc:
        await svc.store_file(QueryConn(), company_id=COMPANY, folder_id=f["id"], prepared=prepared(),
                             uploaded_by=uuid4(), actor=actor())
    assert exc.value.status == 403
    assert storage.uploaded == []


@pytest.mark.asyncio
async def test_store_file_drop_box_upload_goes_private_and_audits(monkeypatch, storage):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.ADD}))})
    conn = QueryConn(fetchrow={"INSERT INTO drive_files": file_row(f["id"], space="hr")})
    out = await svc.store_file(conn, company_id=COMPANY, folder_id=f["id"], prepared=prepared(),
                               uploaded_by=uuid4(), actor=actor(), filename="Doe_Jane/Warning.pdf")
    assert storage.uploaded == [("Warning.pdf", f"drive/{COMPANY}/hr", "application/pdf")]
    assert conn.args_for("INSERT INTO drive_files")[2] == "Warning.pdf"
    assert "storage_path" not in out
    assert any("drive_audit_log" in s for s in conn.sql_for("execute"))


@pytest.mark.asyncio
async def test_store_file_deletes_object_when_insert_fails(monkeypatch, storage):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    class Boom(QueryConn):
        async def fetchrow(self, sql, *args):
            raise RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await svc.store_file(Boom(), company_id=COMPANY, folder_id=f["id"], prepared=prepared(),
                             uploaded_by=None, actor=None)
    assert storage.deleted == [f"s3://private/drive/{COMPANY}/general/x"]


@pytest.mark.asyncio
async def test_store_file_storage_unconfigured_is_503(monkeypatch, storage):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    async def unconfigured(*a, **k):
        raise RuntimeError("S3 not configured for private uploads")
    storage.upload_private_file = unconfigured
    with pytest.raises(DriveError) as exc:
        await svc.store_file(QueryConn(), company_id=COMPANY, folder_id=f["id"], prepared=prepared(),
                             uploaded_by=None, actor=None)
    assert exc.value.status == 503


@pytest.mark.asyncio
async def test_file_without_read_is_not_found(monkeypatch):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.ADD}))})
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"], space="hr")})
    with pytest.raises(DriveError) as exc:
        await svc.get_file(conn, company_id=COMPANY, file_id=uuid4(), actor=actor())
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_presign_download_audits_hr(monkeypatch, storage):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"], space="hr")})
    out = await svc.presign_download(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("admin"))
    assert out["url"] == storage.url and out["expires_in"] == svc.PRESIGN_SECONDS
    assert any("drive_audit_log" in s for s in conn.sql_for("execute"))


@pytest.mark.asyncio
async def test_presign_system_path_audits_the_person_it_serves(monkeypatch, storage):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"], space="hr")})
    reader = uuid4()
    await svc.presign_download(conn, company_id=COMPANY, file_id=uuid4(), actor=None,
                               on_behalf_of=reader, audit_details={"via": "hr_case"})
    audit = conn.args_for("drive_audit_log")
    assert reader in audit and "file_download" in audit


@pytest.mark.asyncio
async def test_read_file_bytes_storage_failure_is_a_502(monkeypatch, storage):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    async def broken(path):
        raise RuntimeError("Failed to download from S3: NoSuchKey")
    storage.download_file = broken
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"])})
    with pytest.raises(DriveError) as exc:
        await svc.read_file_bytes(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("admin"))
    assert exc.value.status == 502


@pytest.mark.asyncio
async def test_presign_unavailable_is_503(monkeypatch, storage):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    storage.url = None
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"])})
    with pytest.raises(DriveError) as exc:
        await svc.presign_download(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("admin"))
    assert exc.value.status == 503


@pytest.mark.asyncio
async def test_general_download_not_audited(monkeypatch, storage):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"])})
    await svc.presign_download(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("admin"))
    assert conn.sql_for("execute") == []


@pytest.mark.asyncio
async def test_file_move_across_spaces_refused(monkeypatch):
    src = folder(space="hr")
    dst = folder(space="general")
    patch_caps(monkeypatch, {src["id"]: (src, ALL), dst["id"]: (dst, ALL)})
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(src["id"], space="hr")})
    with pytest.raises(DriveError) as exc:
        await svc.update_file(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("admin"), folder_id=dst["id"])
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_rename_keeps_original_extension(monkeypatch):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    row = file_row(f["id"], filename="letter.pdf")
    conn = QueryConn(fetchrow={"FROM drive_files f": row, "UPDATE drive_files": row})
    await svc.update_file(conn, company_id=COMPANY, file_id=row["id"], actor=actor("admin"), filename="final.exe")
    assert conn.args_for("UPDATE drive_files")[1] == "final.pdf"


@pytest.mark.asyncio
async def test_delete_file_requires_manage(monkeypatch):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.LIST, DriveCap.READ}))})
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"])})
    with pytest.raises(DriveError) as exc:
        await svc.soft_delete_file(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("member"))
    assert exc.value.status == 403


@pytest.mark.asyncio
async def test_read_file_text_truncates(monkeypatch):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    conn = QueryConn(fetchrow={"FROM drive_files f": file_row(f["id"])},
                     fetchval={"SELECT extracted_text": "abcdef"})
    out = await svc.read_file_text(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("admin"), max_chars=3)
    assert out["text"] == "abc" and out["truncated"] is True


# ── Search ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_only_queries_readable_folders():
    a = actor("operator")
    general = folder(space="general")
    hr = folder(space="hr")
    hr_drop = folder(space="hr", parent_id=hr["id"])
    conn = QueryConn(
        fetch={
            "FROM drive_folders WHERE company_id": [general, hr, hr_drop],
            "FROM drive_folder_grants": [{"folder_id": hr_drop["id"], "permission": "upload"}],
            "FROM drive_files f": [file_row(general["id"])],
        },
    )
    out = await svc.search(conn, company_id=COMPANY, q="policy", actor=a)
    assert conn.args_for("FROM drive_files f")[1] == [general["id"]]
    assert out[0]["folder_name"] == "Folder" and out[0]["space"] == "general"


@pytest.mark.asyncio
async def test_search_nothing_readable_skips_query():
    conn = QueryConn(fetch={
        "FROM drive_folders WHERE company_id": [folder(space="hr")],
        "FROM drive_folder_grants": [],
    })
    assert await svc.search(conn, company_id=COMPANY, q="warning", actor=actor("operator")) == []
    assert not any("drive_files" in s for s in conn.sql_for("fetch"))


@pytest.mark.asyncio
async def test_search_short_query_and_bad_space():
    assert await svc.search(QueryConn(), company_id=COMPANY, q=" a ", actor=actor()) == []
    with pytest.raises(DriveError):
        await svc.search(QueryConn(), company_id=COMPANY, q="policy", actor=actor(), space="other")


# ── Grants ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_grant_requires_grant_cap(monkeypatch):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.LIST, DriveCap.READ, DriveCap.ADD, DriveCap.MANAGE}))})
    with pytest.raises(DriveError) as exc:
        await svc.set_grant(QueryConn(), company_id=COMPANY, folder_id=f["id"], user_id=uuid4(),
                            permission="edit", actor=actor())
    assert exc.value.status == 403


@pytest.mark.asyncio
async def test_set_grant_refuses_non_member_and_bad_permission(monkeypatch):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    with pytest.raises(DriveError):
        await svc.set_grant(QueryConn(), company_id=COMPANY, folder_id=f["id"], user_id=uuid4(),
                            permission="owner", actor=actor("admin"))
    conn = QueryConn(fetchval={"FROM clients WHERE user_id": False})
    with pytest.raises(DriveError) as exc:
        await svc.set_grant(conn, company_id=COMPANY, folder_id=f["id"], user_id=uuid4(),
                            permission="upload", actor=actor("admin"))
    assert "member" in exc.value.detail


@pytest.mark.asyncio
async def test_set_and_remove_grant_are_audited(monkeypatch):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    conn = QueryConn(fetchval={"FROM clients WHERE user_id": True})
    target = uuid4()
    await svc.set_grant(conn, company_id=COMPANY, folder_id=f["id"], user_id=target,
                        permission="upload", actor=actor("admin"))
    await svc.remove_grant(conn, company_id=COMPANY, folder_id=f["id"], user_id=target, actor=actor("admin"))
    audits = [c for c in conn.calls if c[0] == "execute" and "drive_audit_log" in c[1]]
    assert [a[2][4] for a in audits] == ["grant_set", "grant_remove"]


@pytest.mark.asyncio
async def test_load_actor_uses_work_level(monkeypatch):
    from app.matcha.services.matcha_work import work_permissions

    async def fake_access(conn, *, user, company_id):
        return SimpleNamespace(level="reviewer")
    monkeypatch.setattr(work_permissions, "resolve_work_access", fake_access)
    user = SimpleNamespace(id=uuid4(), role="client")
    a = await svc.load_actor(QueryConn(), user=user, company_id=COMPANY)
    assert a == DriveActor(user_id=user.id, work_level="reviewer")


@pytest.mark.asyncio
async def test_get_tree_groups_visible_folders_by_space(monkeypatch):
    a = actor("operator")
    general = folder(space="general", system_key="general_root")
    hr = folder(space="hr", system_key="hr_root")
    drafts = folder(space="hr", parent_id=hr["id"])

    async def seeded(conn, company_id):
        return {"general_root": general["id"], "hr_root": hr["id"]}
    monkeypatch.setattr(svc, "ensure_system_folders", seeded)
    conn = QueryConn(fetch={
        "FROM drive_folders WHERE company_id": [general, hr, drafts],
        "FROM drive_folder_grants": [{"folder_id": drafts["id"], "permission": "upload"}],
    })
    out = await svc.get_tree(conn, company_id=COMPANY, actor=a)
    assert out["spaces"]["general"]["visible"] is True
    hr_space = out["spaces"]["hr"]
    assert [f["id"] for f in hr_space["folders"]] == [drafts["id"]]
    assert hr_space["folders"][0]["caps"] == ["add"]


# ── People search ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_members_admin_only():
    with pytest.raises(DriveError) as exc:
        await svc.search_members(QueryConn(), company_id=COMPANY, q="ja", actor=actor("operator"))
    assert exc.value.status == 403


@pytest.mark.asyncio
async def test_search_members_escapes_and_sorts():
    rows = [
        {"id": uuid4(), "email": "zed@example.com", "name": "Zed", "kind": "employee"},
        {"id": uuid4(), "email": "amy@example.com", "name": "amy", "kind": "business"},
    ]
    conn = QueryConn(fetch={"FROM users u": rows})
    out = await svc.search_members(conn, company_id=COMPANY, q="a%b", actor=actor("admin"))
    assert [p["name"] for p in out] == ["amy", "Zed"]
    assert conn.args_for("FROM users u")[2] == "%a\\%b%"


# ── Review fixes (PR #639) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tree_hides_subfolder_names_behind_a_drop_box(monkeypatch):
    hr = folder(space="hr", system_key="hr_root", name="HR")
    secret = folder(space="hr", parent_id=hr["id"], name="Termination - Jane Doe")

    async def seeded(conn, company_id):
        return {"general_root": uuid4(), "hr_root": hr["id"]}
    monkeypatch.setattr(svc, "ensure_system_folders", seeded)
    conn = QueryConn(fetch={
        "FROM drive_folders WHERE company_id": [hr, secret],
        "FROM drive_folder_grants": [{"folder_id": hr["id"], "permission": "upload"}],
    })
    out = await svc.get_tree(conn, company_id=COMPANY, actor=actor("operator"))
    names = [f["name"] for f in out["spaces"]["hr"]["folders"]]
    assert names == ["HR"] and "Termination - Jane Doe" not in str(out)


def test_breadcrumbs_only_show_listable_ancestors():
    deep = folder(space="hr", name="Jane Doe")
    deep["_chain"] = [
        {"id": deep["id"], "name": "Jane Doe", "permission": "view"},
        {"id": uuid4(), "name": "Investigations", "permission": None},
        {"id": uuid4(), "name": "HR", "permission": None},
    ]
    assert svc._visible_breadcrumbs(deep, actor("operator")) == [{"id": deep["id"], "name": "Jane Doe"}]
    assert [c["name"] for c in svc._visible_breadcrumbs(deep, actor("admin"))] == ["HR", "Investigations", "Jane Doe"]
    assert [c["name"] for c in svc._visible_breadcrumbs(deep, None)] == ["HR", "Investigations", "Jane Doe"]


@pytest.mark.asyncio
async def test_list_folder_breadcrumbs_come_from_the_checked_chain(monkeypatch):
    f = folder(space="hr", name="Jane Doe")
    f["_chain"] = [
        {"id": f["id"], "name": "Jane Doe", "permission": "view"},
        {"id": uuid4(), "name": "Investigations", "permission": None},
    ]
    patch_caps(monkeypatch, {f["id"]: (f, frozenset({DriveCap.LIST, DriveCap.READ}))})
    conn = QueryConn(fetch={"WHERE parent_id = $1": [], "FROM drive_files f": []})
    out = await svc.list_folder(conn, company_id=COMPANY, folder_id=f["id"], actor=actor("operator"))
    assert out["breadcrumbs"] == [{"id": f["id"], "name": "Jane Doe"}]


@pytest.mark.asyncio
async def test_child_of_drop_box_does_not_inherit_add(monkeypatch):
    parent = folder(space="hr", name="HR")
    parent["_chain"] = [{"id": parent["id"], "name": "HR", "permission": "upload"}]
    child = folder(space="hr", parent_id=parent["id"], name="Sub")
    # LIST from somewhere above is needed to list at all; model it on the caps.
    patch_caps(monkeypatch, {parent["id"]: (parent, frozenset({DriveCap.LIST, DriveCap.READ, DriveCap.ADD}))})
    conn = QueryConn(fetch={"WHERE parent_id = $1": [child], "FROM drive_folder_grants": [], "FROM drive_files f": []})
    out = await svc.list_folder(conn, company_id=COMPANY, folder_id=parent["id"], actor=actor("operator"))
    assert "add" not in out["folders"][0]["caps"]


@pytest.mark.asyncio
async def test_store_file_folder_deleted_mid_upload_is_404(monkeypatch, storage):
    import asyncpg

    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    class Gone(QueryConn):
        async def fetchrow(self, sql, *args):
            raise asyncpg.ForeignKeyViolationError("fk")
    with pytest.raises(DriveError) as exc:
        await svc.store_file(Gone(), company_id=COMPANY, folder_id=f["id"], prepared=prepared(),
                             uploaded_by=None, actor=None)
    assert exc.value.status == 404
    assert storage.deleted  # no orphaned object


@pytest.mark.asyncio
async def test_store_file_audit_failure_rolls_back_and_cleans_up(monkeypatch, storage):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    class AuditDown(QueryConn):
        async def execute(self, sql, *args):
            if "drive_audit_log" in sql:
                raise RuntimeError("audit insert failed")
            return "OK"
    conn = AuditDown(fetchrow={"INSERT INTO drive_files": file_row(f["id"], space="hr")})
    with pytest.raises(RuntimeError):
        await svc.store_file(conn, company_id=COMPANY, folder_id=f["id"], prepared=prepared(),
                             uploaded_by=None, actor=None)
    assert storage.deleted


@pytest.mark.asyncio
async def test_create_folder_parent_deleted_is_404(monkeypatch):
    import asyncpg

    parent = folder()
    patch_caps(monkeypatch, {parent["id"]: (parent, ALL)})

    class Gone(QueryConn):
        async def fetchrow(self, sql, *args):
            raise asyncpg.ForeignKeyViolationError("fk")
    with pytest.raises(DriveError) as exc:
        await svc.create_folder(Gone(), company_id=COMPANY, parent_id=parent["id"], name="X", actor=actor("admin"))
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_delete_folder_already_gone_is_404(monkeypatch):
    f = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})

    async def seeded(conn, company_id):
        return {"general_root": uuid4(), "hr_root": uuid4()}
    monkeypatch.setattr(svc, "ensure_system_folders", seeded)
    with pytest.raises(DriveError) as exc:
        await svc.delete_folder(QueryConn(fetchval={"FOR UPDATE": None}), company_id=COMPANY,
                                folder_id=f["id"], actor=actor("admin"))
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_list_grants_one_row_per_person(monkeypatch):
    f = folder(space="hr")
    patch_caps(monkeypatch, {f["id"]: (f, ALL)})
    conn = QueryConn(fetch={"FROM drive_folder_grants g": []})
    await svc.list_grants(conn, company_id=COMPANY, folder_id=f["id"], actor=actor("admin"))
    sql = conn.sql_for("fetch")[0]
    assert "LEFT JOIN employees" not in sql and "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_move_to_deleted_destination_is_404(monkeypatch):
    import asyncpg

    f = folder()
    dst = folder()
    patch_caps(monkeypatch, {f["id"]: (f, ALL), dst["id"]: (dst, ALL)})

    class Gone(QueryConn):
        async def fetchrow(self, sql, *args):
            if sql.lstrip().startswith("UPDATE drive_files"):
                raise asyncpg.ForeignKeyViolationError("fk")
            return await super().fetchrow(sql, *args)
    conn = Gone(fetchrow={"FROM drive_files f": file_row(f["id"])})
    with pytest.raises(DriveError) as exc:
        await svc.update_file(conn, company_id=COMPANY, file_id=uuid4(), actor=actor("admin"), folder_id=dst["id"])
    assert exc.value.status == 404
