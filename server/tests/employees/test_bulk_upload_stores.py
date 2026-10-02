"""Bulk roster upload: files Excel actually produces, and who works where."""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.datastructures import UploadFile

from app.matcha.routes.employees import bulk_upload as routes

COMPANY_ID = uuid4()
DOWNTOWN = {"id": uuid4(), "name": "Downtown", "address": "1 Main", "city": "Oakland", "state": "CA"}
MISSION = {"id": uuid4(), "name": "Mission", "address": "9 Oak", "city": "San Francisco", "state": "CA"}


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, stores):
        self.stores = stores
        self.inserts: list[tuple[str, tuple]] = []

    async def fetch(self, query, *args):
        if "FROM business_locations" in query:
            assert args == (COMPANY_ID,), "stores are read for the caller's company only"
            return self.stores
        if "FROM integration_connections" in query:
            return []
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "SELECT id FROM employees" in query:
            return None
        raise AssertionError(query)

    async def fetchrow(self, query, *args):
        if "INSERT INTO employees" in query:
            self.inserts.append((query, args))
            return {"id": uuid4()}
        raise AssertionError(query)


def _patch(monkeypatch, conn):
    monkeypatch.setattr(routes, "get_connection", lambda: _AsyncContext(conn))
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=COMPANY_ID))
    monkeypatch.setattr(routes, "_employee_compensation_fields_available", AsyncMock(return_value=True))
    monkeypatch.setattr(routes, "_employee_org_fields_available", AsyncMock(return_value=True))
    monkeypatch.setattr(routes, "_column_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(routes, "run_jurisdiction_drift_check", AsyncMock())
    sync = AsyncMock()
    monkeypatch.setattr(routes, "_sync_employee_location_for_compliance", sync)
    import app.matcha.services.training.training_assignment as training

    monkeypatch.setattr(training, "evaluate_new_hire_rules", AsyncMock())
    return sync


async def _upload(text: str, *, filename="roster.csv", encoding="utf-8"):
    file = UploadFile(io.BytesIO(text.encode(encoding)), filename=filename)
    return await routes.bulk_upload_employees_csv(
        BackgroundTasks(), file=file, send_invitations=False,
        current_user=SimpleNamespace(id=uuid4(), role="client"),
    )


def _inserted(conn, column):
    """The value written for `column` on each inserted employee (None if absent)."""
    values = []
    for query, args in conn.inserts:
        columns = [name.strip() for name in query.split("(", 1)[1].split(")", 1)[0].split(",")]
        values.append(args[columns.index(column)] if column in columns else None)
    return values


@pytest.mark.asyncio
async def test_an_excel_export_with_a_bom_and_capitalized_headers_imports(monkeypatch):
    # Excel's "CSV UTF-8" prepends a BOM and people capitalize headers. Either
    # one used to fail the whole file with "Missing required columns: email".
    conn = _Conn([DOWNTOWN])
    _patch(monkeypatch, conn)

    result = await _upload(
        "Email, First_Name ,LAST_NAME\nsam@example.com,Sam,Rivera\n",
        filename="ROSTER.CSV", encoding="utf-8-sig",
    )

    assert (result.created, result.failed) == (1, 0)


@pytest.mark.asyncio
async def test_the_location_column_places_each_employee_at_their_store(monkeypatch):
    conn = _Conn([DOWNTOWN, MISSION])
    sync = _patch(monkeypatch, conn)

    result = await _upload(
        "email,first_name,last_name,work_state,location\n"
        "a@example.com,A,One,CA,mission\n"
        "b@example.com,B,Two,CA,\n"
        "c@example.com,C,Three,CA,Uptown\n"
    )

    assert (result.created, result.failed) == (2, 1)
    # Named store → that store. No name with two stores → no honest default.
    assert _inserted(conn, "work_location_id") == [MISSION["id"], None]
    assert result.errors == [{
        "row": 4, "email": "c@example.com",
        "error": "Location 'Uptown' doesn't match any store. Use one of: Downtown, Mission.",
    }]
    # The placed employee's store IS their compliance location; only the
    # unplaced one still derives one from their work state.
    assert sync.await_count == 1
    assert sync.await_args.kwargs["work_state"] == "CA"


@pytest.mark.asyncio
async def test_a_one_store_company_needs_no_location_column(monkeypatch):
    conn = _Conn([DOWNTOWN])
    sync = _patch(monkeypatch, conn)

    result = await _upload(
        "email,first_name,last_name,work_state\n"
        "a@example.com,A,One,CA\n"
        "remote@example.com,R,Emote,NV\n"
    )

    assert result.created == 2
    # Everyone in the store's state lands there; the Nevada worker does not,
    # and keeps a compliance location of their own.
    assert _inserted(conn, "work_location_id") == [DOWNTOWN["id"], None]
    assert sync.await_count == 1
    assert sync.await_args.kwargs["work_state"] == "NV"


@pytest.mark.asyncio
async def test_a_file_that_is_not_a_csv_or_not_text_is_refused(monkeypatch):
    conn = _Conn([])
    _patch(monkeypatch, conn)

    with pytest.raises(HTTPException) as caught:
        await _upload("email\n", filename="roster.xlsx")
    assert caught.value.status_code == 400

    binary = UploadFile(io.BytesIO(b"\xff\xfe\x00bad"), filename="roster.csv")
    with pytest.raises(HTTPException) as caught:
        await routes.bulk_upload_employees_csv(
            BackgroundTasks(), file=binary, send_invitations=False,
            current_user=SimpleNamespace(id=uuid4(), role="client"),
        )
    assert caught.value.status_code == 400
