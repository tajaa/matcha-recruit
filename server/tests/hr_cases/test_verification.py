"""Signed-copy check: filename template, PDF inspection, the model read, the
pure decision, and the case transition.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_verification.py -q
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.services.hr_cases import verification as v
from tests._helpers.routes import QueryConn


def _pdf(text="Signed by Jane Doe", pages=1, password=None) -> bytes:
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    if password:
        return doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=password, user_pw=password)
    return doc.tobytes()


# ── Filename template ───────────────────────────────────────────────────


def test_validate_template():
    assert v.validate_template(" {last_name}_{case_number} ") == "{last_name}_{case_number}"
    for bad in ("", "no fields", "{last_name}_{ssn}", "{last_name}}", "x" * 201):
        with pytest.raises(v.TemplateError):
            v.validate_template(bad)


def test_render_filename_and_values():
    case = {"case_number": "HRC-2026-0004", "incident_number": "IR-9", "action_type": "written_warning",
            "delivered_at": datetime(2026, 9, 28, 15, tzinfo=timezone.utc),
            "review": {"input": {"infraction_type": "policy_violation"}}}
    values = v.filename_values(case, {"first_name": "José", "last_name": "O'Brien/Smith"})
    name = v.render_filename("{last_name}_{first_name}_{action_type}_{infraction_type}_{delivered_date}",
                             values=values, extension=".pdf")
    assert name == "O'Brien-Smith_José_written-warning_policy-violation_2026-09-28.pdf"
    assert "/" not in name


def test_render_filename_bad_stored_template_falls_back():
    values = {"last_name": "Doe", "first_name": "Jane", "action_type": "pip", "delivered_date": "2026-09-28"}
    assert v.render_filename("{ssn}", values=values, extension=".png") == "Doe_Jane_pip_2026-09-28.png"


def test_render_filename_missing_values():
    assert v.render_filename("{last_name}", values={}, extension=".pdf") == "unknown.pdf"


# ── Inspection ──────────────────────────────────────────────────────────


def test_inspect_real_pdfs():
    ok = v.inspect_pdf(_pdf(pages=2))
    assert ok == {"is_pdf": True, "encrypted": False, "page_count": 2, "has_text_layer": True}
    scan = v.inspect_pdf(_pdf(text=None))
    assert scan["is_pdf"] and scan["has_text_layer"] is False
    locked = v.inspect_pdf(_pdf(password="secret"))
    assert locked["encrypted"] is True
    assert v.inspect_pdf(b"<html>")["is_pdf"] is False
    assert v.inspect_pdf(b"%PDF-1.7 garbage")["is_pdf"] is False


# ── Decision ────────────────────────────────────────────────────────────

CLEAN = {"available": True, "legible": True, "employee_signature_present": True, "printed_name_matches": True,
         "manager_signature_present": True, "employee_comments_present": False, "refusal_noted": False,
         "matches_letter": True, "pages_look_complete": True}
PDF_OK = {"is_pdf": True, "encrypted": False, "page_count": 1, "has_text_layer": True}


@pytest.mark.parametrize("inspection,reading_over,esigned,expected", [
    (PDF_OK, {}, False, []),
    (None, {}, False, []),
    ({"is_pdf": False}, {}, False, ["unreadable_pdf"]),
    ({**PDF_OK, "encrypted": True}, {}, False, ["encrypted_pdf"]),
    ({**PDF_OK, "page_count": 0}, {}, False, ["empty_pdf"]),
    (PDF_OK, {"legible": False}, False, ["illegible_scan"]),
    (PDF_OK, {"employee_signature_present": False}, False, ["employee_signature_missing"]),
    (PDF_OK, {"employee_signature_present": False}, True, []),
    (PDF_OK, {"employee_signature_present": False, "refusal_noted": True}, False, ["refusal_noted"]),
    (PDF_OK, {"printed_name_matches": False}, False, ["signature_name_mismatch"]),
    (PDF_OK, {"printed_name_matches": None, "matches_letter": None}, False, []),
    (PDF_OK, {"matches_letter": False}, False, ["letter_mismatch"]),
    (PDF_OK, {"pages_look_complete": False}, False, ["pages_missing"]),
    (PDF_OK, {"employee_comments_present": True}, False, ["employee_comments"]),
    (PDF_OK, {"available": False}, False, ["check_unavailable"]),
])
def test_decide(inspection, reading_over, esigned, expected):
    out = v.decide(inspection, {**CLEAN, **reading_over}, esigned=esigned)
    assert out["reasons"] == expected
    assert out["outcome"] == ("needs_attention" if expected else "verified")
    assert out["flag_hr_comments"] is ("employee_comments" in expected)
    assert len(out["reason_text"]) == len(expected)


def test_unavailable_check_is_never_a_pass():
    assert v.decide(None, {"available": False})["outcome"] == "needs_attention"


def test_coerce_reading():
    out = v._coerce_reading({"legible": "yes", "employee_signature_present": True, "printed_name_matches": "maybe",
                             "employee_comments_text": "  I disagree  ", "employee_signature_date": "2026-09-28T00"})
    assert out["available"] is True and out["legible"] is False and out["printed_name_matches"] is None
    assert out["employee_comments_text"] == "I disagree" and out["employee_signature_date"] == "2026-09-28"
    assert v._coerce_reading({"legible": True})["available"] is False
    assert v._coerce_reading("junk")["available"] is False


class FakeModels:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, []

    async def generate_content(self, model, contents):
        self.calls.append(contents)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


def _genai(monkeypatch, models):
    from app.matcha.services._shared import gemini

    monkeypatch.setattr(gemini, "_genai", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))


@pytest.mark.asyncio
async def test_read_signed_copy(monkeypatch):
    models = FakeModels(text='{"legible": true, "employee_signature_present": true, "employee_comments_present": false}')
    _genai(monkeypatch, models)
    out = await v.read_signed_copy(_pdf(), mime_type="application/pdf", employee_name="Jane Doe", letter_text="Dear Jane")
    assert out["available"] and out["legible"]
    assert "Jane Doe" in models.calls[0][0] and "Dear Jane" in models.calls[0][0]
    _genai(monkeypatch, FakeModels(error=TimeoutError()))
    assert (await v.read_signed_copy(b"x", mime_type="image/png", employee_name=None, letter_text=None)) == {"available": False}


def test_validate_signed_upload():
    assert v.validate_signed_upload("scan.JPG", b"x") == (".jpg", "image/jpeg")
    for name, data in (("s.docx", b"x"), ("s.pdf", b""), ("s.pdf", b"x" * (25 * 1024 * 1024 + 1))):
        with pytest.raises(ValueError):
            v.validate_signed_upload(name, data)


# ── Filing + transition ─────────────────────────────────────────────────


class TxConn(QueryConn):
    def transaction(self):
        return self


@pytest.mark.asyncio
async def test_ensure_employee_folder_reuses_or_creates(monkeypatch):
    from app.matcha.services.drive import drive_service

    signed = uuid4()

    async def seeded(conn, company_id):
        return {"hr_discipline_signed": signed}
    monkeypatch.setattr(drive_service, "ensure_system_folders", seeded)
    existing = uuid4()
    conn = QueryConn(fetchval={"SELECT id FROM drive_folders": existing})
    assert await v.ensure_employee_folder(conn, company_id=uuid4(), employee={"first_name": "Jane", "last_name": "Doe"}) == existing
    assert conn.args_for("SELECT id FROM drive_folders")[2] == "Doe, Jane"
    new = uuid4()
    conn = QueryConn(fetchval={"SELECT id FROM drive_folders": None, "INSERT INTO drive_folders": new})
    assert await v.ensure_employee_folder(conn, company_id=uuid4(), employee={}) == new
    assert conn.args_for("INSERT INTO drive_folders")[2] == "Unknown employee"


@pytest.mark.asyncio
@pytest.mark.parametrize("reading,event", [
    ({**CLEAN}, "verified"),
    ({**CLEAN, "employee_comments_present": True, "employee_comments_text": "I disagree"}, "attention"),
])
async def test_run_check_moves_case(monkeypatch, reading, event):
    from app.matcha.services.hr_cases import case_service

    cid = uuid4()

    async def get_case(conn, **kw):
        return {"id": cid, "employee_id": uuid4(), "draft_file_id": uuid4()}
    seen = {}

    async def apply_event(conn, **kw):
        seen.update(kw)
        return {"id": cid, "stage": "closed" if kw["event"] == "verified" else "needs_attention"}

    async def read(data, **kw):
        return reading
    monkeypatch.setattr(case_service, "get_case", get_case)
    monkeypatch.setattr(case_service, "apply_event", apply_event)
    monkeypatch.setattr(v, "read_signed_copy", read)
    conn = QueryConn(fetchrow={"FROM employees": {"first_name": "Jane", "last_name": "Doe"}},
                     fetchval={"SELECT extracted_text": "Dear Jane"})
    await v.run_check(conn, company_id=uuid4(), case_id=cid, data=_pdf(), mime_type="application/pdf", actor_user_id=None)
    assert seen["event"] == event
    if event == "attention":
        assert seen["sets"]["attention_reasons"] == ["employee_comments"]
        assert seen["sets"]["verification"]["reading"]["employee_comments_text"] == "I disagree"
