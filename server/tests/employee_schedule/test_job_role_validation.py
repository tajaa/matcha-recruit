"""Tenant and location validation for manually selected shift roles."""

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.employee_schedule._shared import assert_job_in_company


def _run(coro):
    return asyncio.run(coro)


class JobConn:
    def __init__(self, row):
        self.row = row
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((" ".join(query.split()), args))
        return self.row


def test_company_job_available_at_location_is_returned_for_canonical_role():
    company_id, job_id, location_id = uuid4(), uuid4(), uuid4()
    conn = JobConn({"name": "Barista", "location_id": location_id})

    row = _run(assert_job_in_company(
        conn, company_id, job_id, location_id=location_id,
    ))

    assert row["name"] == "Barista"
    assert conn.calls[0][1] == (job_id, company_id)


def test_job_from_another_company_is_rejected():
    conn = JobConn(None)

    with pytest.raises(HTTPException) as exc:
        _run(assert_job_in_company(conn, uuid4(), uuid4(), location_id=uuid4()))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Job not found"


def test_job_from_another_location_is_rejected():
    conn = JobConn({"name": "Barista", "location_id": uuid4()})

    with pytest.raises(HTTPException) as exc:
        _run(assert_job_in_company(conn, uuid4(), uuid4(), location_id=uuid4()))

    assert exc.value.status_code == 422
    assert exc.value.detail == "Job is not available at this location"
