from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from google.genai import types

from app.core.services import ai_usage
from app.matcha.services.matcha_work.project_agent import agent


def _response(*parts):
    return SimpleNamespace(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))],
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
            thoughts_token_count=2,
            total_token_count=17,
        ),
    )


class _FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def generate_content(self, **kwargs):
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
        _response(types.Part.from_function_call(
            name="read_file",
            args={"path": "client/src/App.tsx", "start_line": 35, "end_line": 50},
        )),
        _response(types.Part.from_function_call(
            name="answer_question",
            args={"answer": answer},
        )),
    ])
    fake_client = SimpleNamespace(aio=SimpleNamespace(models=models))
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
    get_client.assert_called_once_with()
    post_answer.assert_awaited_once_with(company_id, channel_id, answer)
    assert record_step.await_count == 2
    mark_run.assert_awaited_once()
    assert mark_run.await_args.kwargs["status"] == "done"
    assert mark_run.await_args.kwargs["result"] == {"answer": answer}


@pytest.mark.asyncio
async def test_repo_question_refuses_ungrounded_direct_answer(monkeypatch):
    models = _FakeModels([_response(types.Part(text="It probably works this way."))])
    fake_client = SimpleNamespace(aio=SimpleNamespace(models=models))
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
