"""`_run_huume_dispatch` must name which flag is actually off. It used to OR
`huume` and `employee_schedule` into one check and always blame scheduling —
a real prod company (`employee_schedule=true`, `huume=false`) got that message
for three days before anyone thought to doubt it (2026-08-26 incident)."""

import asyncio
from uuid import uuid4

import pytest

from app.matcha.models.matcha_work.matcha_work import SendMessageRequest
from app.matcha.services.matcha_work import turn_pipeline


def _run_to_list(agen):
    async def _collect():
        return [item async for item in agen]
    return asyncio.run(_collect())


def _tc(*, surface, content="do something"):
    return turn_pipeline.TurnContext(
        thread_id=uuid4(),
        body=SendMessageRequest(content=content),
        current_user=None,
        thread={"huume_mode": True, "surface": surface, "company_id": uuid4()},
        company_id=uuid4(),
    )


@pytest.mark.parametrize(
    "features,expected_fragment",
    [
        ({"huume": True, "employee_schedule": False}, "Scheduling isn't enabled"),
        ({"huume": False, "employee_schedule": True}, "Huume isn't enabled"),
    ],
)
def test_schedule_thread_gate_names_the_failing_flag(monkeypatch, features, expected_fragment):
    async def fake_get_company_features(_company_id):
        return features

    monkeypatch.setattr(turn_pipeline, "get_company_features", fake_get_company_features)

    tc = _tc(surface="schedule_assistant")
    frames = _run_to_list(turn_pipeline._run_huume_dispatch(tc))

    # _run_huume_dispatch yields SSE-encoded strings via _sse_data.
    assert any(expected_fragment in frame for frame in frames)
    assert tc.terminated is True
