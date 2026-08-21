from uuid import uuid4

import pytest

from app.matcha.services.scheduling.schedule_chat import (
    ProposalExecutionClaimError,
    _claim_proposal_execution,
)


class _Conn:
    def __init__(self, status):
        self.status = status
        self.query = ""

    async def fetchval(self, query, proposal_id):
        self.query = query
        return self.status


@pytest.mark.asyncio
async def test_execution_claim_locks_and_accepts_a_proposed_row():
    conn = _Conn("proposed")

    await _claim_proposal_execution(conn, uuid4())

    assert "FOR UPDATE" in conn.query


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "confirmed", "cancelled", "clarifying"])
async def test_execution_claim_refuses_an_unavailable_row(status):
    with pytest.raises(ProposalExecutionClaimError):
        await _claim_proposal_execution(_Conn(status), uuid4())
