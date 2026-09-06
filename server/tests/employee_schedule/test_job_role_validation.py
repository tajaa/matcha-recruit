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


def test_company_wide_job_is_available_at_every_location():
    conn = JobConn({"name": "Floater", "location_id": None})

    row = _run(assert_job_in_company(conn, uuid4(), uuid4(), location_id=uuid4()))

    assert row["name"] == "Floater"


def test_location_scoped_job_is_rejected_on_a_location_less_shift():
    # location_id=None is a real constraint, not "don't check": a company-wide
    # shift was otherwise a way to attach another store's job.
    conn = JobConn({"name": "Barista", "location_id": uuid4()})

    with pytest.raises(HTTPException) as exc:
        _run(assert_job_in_company(conn, uuid4(), uuid4(), location_id=None))

    assert exc.value.status_code == 422


def test_omitting_location_skips_the_location_check():
    conn = JobConn({"name": "Barista", "location_id": uuid4()})

    row = _run(assert_job_in_company(conn, uuid4(), uuid4()))

    assert row["name"] == "Barista"


def test_lock_takes_a_row_share_lock():
    conn = JobConn({"name": "Barista", "location_id": None})

    _run(assert_job_in_company(conn, uuid4(), uuid4(), lock=True))

    assert conn.calls[0][0].endswith("FOR SHARE")


def test_no_lock_by_default():
    conn = JobConn({"name": "Barista", "location_id": None})

    _run(assert_job_in_company(conn, uuid4(), uuid4()))

    assert "FOR SHARE" not in conn.calls[0][0]
