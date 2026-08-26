"""draft_offer_letter must stamp offer_letters.source_thread_id on both
the INSERT (new offer) and UPDATE (editing an existing draft) branches —
the durable half of the offer<->thread link that
_notify_huume_thread_of_offer_event resolves from. Asserted against the
raw SQL + bound params via a fake connection, not a real DB.

    cd server && ./venv/bin/python -m pytest tests/huume/test_draft_offer_letter_thread_link.py -q
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.huume.onboarding_skill import _draft_offer_letter_impl

COMPANY_ID = uuid4()
THREAD_ID = uuid4()
OFFER_ID = uuid4()


class FakeConn:
    def __init__(self, fetchval_result=None, fetchrow_result=None):
        self._fetchval_result = fetchval_result
        self._fetchrow_result = fetchrow_result
        self.fetchrow_calls = []

    async def fetchval(self, query, *args):
        return self._fetchval_result

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self._fetchrow_result

    async def execute(self, query, *args):
        self.execute_calls = getattr(self, "execute_calls", [])
        self.execute_calls.append((query, args))


@pytest.mark.asyncio
async def test_insert_branch_stamps_source_thread_id():
    row = {"id": OFFER_ID, "status": "draft", "candidate_name": "Jane Doe",
           "candidate_email": None, "position_title": "Dental Assistant",
           "salary": None, "start_date": None, "employment_type": "Full-Time Exempt",
           "location": "Remote"}
    conn = FakeConn(fetchval_result="Sunset Smile", fetchrow_result=row)

    result = await _draft_offer_letter_impl(
        conn, company_id=COMPANY_ID, thread_id=THREAD_ID,
        candidate_name="Jane Doe", position_title="Dental Assistant", reporting_to="Jordan Lee",
    )

    assert result["status"] == "ok"
    insert_query, insert_args = conn.fetchrow_calls[0]
    assert "INSERT INTO offer_letters" in insert_query
    assert "source_thread_id" in insert_query
    assert THREAD_ID in insert_args
    assert "manager_name" in insert_query
    assert "Jordan Lee" in insert_args


@pytest.mark.asyncio
async def test_insert_does_not_invent_optional_draft_fields():
    row = {"id": OFFER_ID, "status": "draft", "candidate_name": "Jane Doe",
           "candidate_email": None, "position_title": "Dental Assistant",
           "salary": None, "start_date": None, "employment_type": None,
           "location": None, "manager_name": None}
    conn = FakeConn(fetchval_result="Sunset Smile", fetchrow_result=row)

    result = await _draft_offer_letter_impl(
        conn, company_id=COMPANY_ID, thread_id=THREAD_ID,
        candidate_name="Jane Doe", position_title="Dental Assistant",
    )

    assert result["status"] == "ok"
    _insert_query, insert_args = conn.fetchrow_calls[0]
    assert insert_args[6:10] == (None, None, None, None)


@pytest.mark.asyncio
async def test_update_branch_stamps_source_thread_id_via_coalesce():
    row = {"id": OFFER_ID, "status": "draft", "candidate_name": "Jane Doe",
           "candidate_email": None, "position_title": "Dental Assistant",
           "salary": None, "start_date": None, "employment_type": "Full-Time Exempt",
           "location": "Remote"}
    conn = FakeConn(fetchval_result="Sunset Smile", fetchrow_result=row)

    result = await _draft_offer_letter_impl(
        conn, company_id=COMPANY_ID, thread_id=THREAD_ID,
        offer_id=str(OFFER_ID), candidate_name="Jane Doe",
        reporting_to="Taylor Morgan",
    )

    assert result["status"] == "ok"
    update_query, update_args = conn.fetchrow_calls[0]
    assert "UPDATE offer_letters" in update_query
    assert "source_thread_id = COALESCE(source_thread_id" in update_query
    assert THREAD_ID in update_args
    assert "manager_name = COALESCE" in update_query
    assert "Taylor Morgan" in update_args
