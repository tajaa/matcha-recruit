"""Test for the apply_to_posting double-apply race
(app.werk.routes.channel_job_postings).

The pre-check (SELECT existing application) is best-effort against a
double-click; the real backstop is the UNIQUE(posting_id, applicant_id)
constraint. A race that slips past the pre-check must land as 409, not an
unhandled 500 from an uncaught UniqueViolationError.
"""

import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

# ── Stub google.genai before importing app code ──
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

MOD = "app.werk.routes.channel_job_postings"


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _user():
    return SimpleNamespace(id=uuid4(), email="applicant@example.com", role="employee")


@pytest.mark.asyncio
async def test_concurrent_apply_race_returns_409_not_500():
    from app.werk.routes.channel_job_postings import apply_to_posting, SubmitApplicationRequest

    channel_id = uuid4()
    posting_id = uuid4()
    user = _user()
    posting_row = {
        "id": posting_id, "status": "active", "posted_by": uuid4(),
        "title": "Line Cook", "open_to_all": True,
    }
    resume_row = {"parsed_data": json.dumps({"name": "A. Pplicant"})}

    conn = AsyncMock()
    conn.fetchval.side_effect = ["member", None, None]  # role, invitation, existing (pre-check clean)
    conn.fetchrow.side_effect = [
        posting_row,
        resume_row,
        asyncpg.UniqueViolationError(),  # INSERT races another request
    ]

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)):
        with pytest.raises(HTTPException) as exc:
            await apply_to_posting(
                channel_id, posting_id, SubmitApplicationRequest(cover_letter=None), current_user=user,
            )

    assert exc.value.status_code == 409
    assert "already applied" in exc.value.detail.lower()
