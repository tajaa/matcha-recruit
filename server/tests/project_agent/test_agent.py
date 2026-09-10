from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.services import ai_usage
from app.matcha.services.huume.luna_client import LunaResponse
from app.matcha.services.matcha_work.project_agent import agent


def _response(*calls, text=None):
    return LunaResponse(
        response_id="resp_test",
        text=text,
        function_calls=list(calls),
        usage={
            "input_tokens": 10, "output_tokens": 5, "total_tokens": 17,
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    )


def _call(name, args):
    """One Responses function call; `call_id` is what its result pairs back to."""
    _call.counter = getattr(_call, "counter", 0) + 1
    return {"call_id": f"call_{_call.counter}", "name": name, "arguments": args}


class _FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create_response(self, **kwargs):
        self.calls.append({
            **kwargs,
            "feature": ai_usage._feature_override.get(),
        })
        return self.responses.pop(0)


def test_source_citation_must_name_a_file_the_agent_read():
    files = {"client/src/App.tsx"}
    assert agent._has_source_citation("See client/src/App.tsx:42.", files)
    assert not agent._has_source_citation("See server/app/main.py:42.", files)
    assert not agent._has_source_citation("See client/src/App.tsx.", files)


@pytest.mark.asyncio
async def test_repo_question_reads_source_then_posts_grounded_answer(monkeypatch):
    answer = "Use the Projects tab; the route is registered here (`client/src/App.tsx:42`)."
    models = _FakeModels([
        _response(_call("read_file", {"path": "client/src/App.tsx", "start_line": 35, "end_line": 50})),
        _response(_call("answer_question", {"answer": answer})),
    ])
    fake_client = models
    get_client = Mock(return_value=fake_client)
    monkeypatch.setattr(agent, "get_luna_client", get_client)
    monkeypatch.setattr(agent.store, "read_repo_file", AsyncMock(return_value={
        "path": "client/src/App.tsx",
        "start_line": 35,
        "end_line": 50,
        "total_lines": 90,
        "content": "42: registerProjectsRoute()",
    }))
    record_step = AsyncMock()
    mark_run = AsyncMock()
    post_answer = AsyncMock()
    monkeypatch.setattr(agent.store, "record_step", record_step)
    monkeypatch.setattr(agent.store, "mark_run", mark_run)
    monkeypatch.setattr(agent.chat, "post_as_espresso", post_answer)

    company_id, project_id, channel_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    result = await agent.run_repo_question(
        run_id=run_id,
        company_id=company_id,
        project_id=project_id,
        channel_id=channel_id,
        question="How do I use Projects?",
        project_title="MATCHA",
        repo="example/matcha",
        base_branch="main",
    )

    assert result["answer"] == answer
    assert result["files_read"] == 1
    assert result["model_calls"] == 2
    assert result["token_usage"]["total_tokens"] == 34
    assert result["token_usage"]["model"] == "gpt-5.6-luna"
    assert all(call["model"] == "gpt-5.6-luna" for call in models.calls)
    assert all(call["feature"] == "matcha.espresso.repo_question" for call in models.calls)
    # This agent must call a tool; its answer only counts after a real read.
    assert all(call["tool_choice"] == "required" for call in models.calls)
    get_client.assert_called_once_with()
    post_answer.assert_awaited_once_with(company_id, channel_id, answer)
    assert record_step.await_count == 2
    mark_run.assert_awaited_once()
    assert mark_run.await_args.kwargs["status"] == "done"
    assert mark_run.await_args.kwargs["result"] == {"answer": answer}


@pytest.mark.asyncio
async def test_repo_question_refuses_ungrounded_direct_answer(monkeypatch):
    models = _FakeModels([_response(text="It probably works this way.")])
    fake_client = models
    monkeypatch.setattr(agent, "get_luna_client", lambda: fake_client)
    monkeypatch.setattr(agent.store, "record_step", AsyncMock())
    monkeypatch.setattr(agent.chat, "post_as_espresso", AsyncMock())

    with pytest.raises(RuntimeError, match="grounded answer"):
        await agent.run_repo_question(
            run_id=uuid4(),
            company_id=uuid4(),
            project_id=uuid4(),
            channel_id=uuid4(),
            question="How does it work?",
            project_title="MATCHA",
            repo="example/matcha",
            base_branch="main",
        )

    agent.chat.post_as_espresso.assert_not_awaited()


@pytest.mark.asyncio
async def test_repo_question_gives_up_after_repeated_finish_refusals(monkeypatch):
    # Under tool_config=ANY the model can no longer end the run with prose, so a
    # model that keeps failing the finish preconditions must be cut off well
    # before _MAX_MODEL_CALLS rather than burning the whole wall-clock budget.
    refusal = _response(_call("answer_question", {"answer": "It probably works this way."}))
    models = _FakeModels([refusal] * (agent._MAX_MODEL_CALLS + 1))
    fake_client = models
    monkeypatch.setattr(agent, "get_luna_client", lambda: fake_client)
    monkeypatch.setattr(agent.store, "record_step", AsyncMock())
    monkeypatch.setattr(agent.chat, "post_as_espresso", AsyncMock())

    with pytest.raises(RuntimeError, match="grounded answer"):
        await agent.run_repo_question(
            run_id=uuid4(),
            company_id=uuid4(),
            project_id=uuid4(),
            channel_id=uuid4(),
            question="How does it work?",
            project_title="MATCHA",
            repo="example/matcha",
            base_branch="main",
        )

    assert len(models.calls) == agent._MAX_FINISH_REFUSALS
    assert agent._MAX_FINISH_REFUSALS < agent._MAX_MODEL_CALLS
    agent.chat.post_as_espresso.assert_not_awaited()


@pytest.mark.asyncio
async def test_repo_question_refusal_streak_resets_after_a_successful_read(monkeypatch):
    # A refused answer followed by new grounding is progress, not a loop: the
    # streak restarts so the model still gets its full retry budget afterwards.
    def refusal():
        return _response(_call("answer_question", {"answer": "No citation here."}))

    read = _response(_call("read_file", {"path": "client/src/App.tsx"}))
    answer = "Registered here (`client/src/App.tsx:42`)."
    models = _FakeModels([
        refusal(),
        refusal(),
        read,
        refusal(),
        refusal(),
        _response(_call("answer_question", {"answer": answer})),
    ])
    monkeypatch.setattr(
        agent, "get_luna_client", lambda: models,
    )
    monkeypatch.setattr(agent.store, "read_repo_file", AsyncMock(return_value={
        "path": "client/src/App.tsx",
        "start_line": 1,
        "end_line": 50,
        "total_lines": 90,
        "content": "42: registerProjectsRoute()",
    }))
    monkeypatch.setattr(agent.store, "record_step", AsyncMock())
    monkeypatch.setattr(agent.store, "mark_run", AsyncMock())
    post_answer = AsyncMock()
    monkeypatch.setattr(agent.chat, "post_as_espresso", post_answer)

    result = await agent.run_repo_question(
        run_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        channel_id=uuid4(),
        question="How does it work?",
        project_title="MATCHA",
        repo="example/matcha",
        base_branch="main",
    )

    assert result["answer"] == answer
    assert len(models.calls) == 6
    post_answer.assert_awaited_once()
