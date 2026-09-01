from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from google.genai import types

from app.matcha.services.matcha_work.project_agent import task_draft_agent
from app.matcha.services.matcha_work.project_agent.prompt import build_task_draft_system_prompt
from app.matcha.services.matcha_work.project_agent.tools import task_draft_declarations


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
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_task_draft_surface_is_read_only_and_structured():
    names = {tool.name for tool in task_draft_declarations()}
    assert names == {"list_files", "search_repo", "read_file", "draft_ticket"}
    assert not names.intersection({"write_file", "open_pr", "run_command", "create_task"})
    prompt = build_task_draft_system_prompt()
    assert "read-only" in prompt
    assert "cannot edit files" in prompt
    assert "path:line" in prompt


@pytest.mark.asyncio
async def test_task_draft_reads_repo_and_returns_resolved_review_draft(monkeypatch):
    draft_args = {
        "title": "Add saved project filters",
        "description": "Add reusable filters to the project board.\n\nAcceptance: filters persist and can be cleared.",
        "priority": "medium",
        "category": "product",
        "board_column": "todo",
        "assignee_name": "Haley",
        "element_name": "Desktop",
        "subtasks": ["Extend ProjectFilters.swift", "Add filtering coverage"],
        "sources": ["platforms/desktop/Espresso/ProjectFilters.swift:12-80"],
    }
    models = _FakeModels([
        _response(types.Part.from_function_call(
            name="read_file",
            args={
                "path": "platforms/desktop/Espresso/ProjectFilters.swift",
                "start_line": 1,
                "end_line": 90,
            },
        )),
        _response(types.Part.from_function_call(name="draft_ticket", args=draft_args)),
    ])
    fake_client = SimpleNamespace(aio=SimpleNamespace(models=models))
    monkeypatch.setattr(task_draft_agent, "get_luna_client", lambda: fake_client)
    monkeypatch.setattr(task_draft_agent.store, "read_repo_file", AsyncMock(return_value={
        "path": "platforms/desktop/Espresso/ProjectFilters.swift",
        "start_line": 1,
        "end_line": 90,
        "total_lines": 100,
        "content": "12: struct ProjectFilters {}",
    }))
    monkeypatch.setattr(task_draft_agent.store, "record_step", AsyncMock())
    mark_run = AsyncMock()
    monkeypatch.setattr(task_draft_agent.store, "mark_run", mark_run)

    company_id, project_id, user_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    result = await task_draft_agent.run_task_draft(
        run_id=run_id,
        company_id=company_id,
        project_id=project_id,
        requested_by=user_id,
        request="It would be helpful to save project filters. Assign Haley.",
        project_title="MATCHA",
        repo="example/matcha",
        base_branch="main",
        model=None,
        collaborators=[{"user_id": str(user_id), "name": "Haley"}],
        elements=[{"id": "element-1", "name": "Desktop", "description": "macOS app"}],
        recent_done=[],
    )

    assert result["draft"]["assigned_to"] == str(user_id)
    assert result["draft"]["element_id"] == "element-1"
    assert result["draft"]["grounding_sources"] == draft_args["sources"]
    assert result["files_read"] == 1
    assert result["model_calls"] == 2
    assert result["token_usage"]["total_tokens"] == 34
    assert result["token_usage"]["model"] == "gpt-5.6-luna"
    assert all(call["model"] == "gpt-5.6-luna" for call in models.calls)
    assert mark_run.await_args.kwargs["status"] == "done"
    assert mark_run.await_args.kwargs["result"]["title"] == "Add saved project filters"


def test_normalize_draft_drops_unknown_assignee_and_clamps_enums():
    result = task_draft_agent.normalize_draft(
        {
            "title": "Try it",
            "description": "Details",
            "priority": "immediate",
            "category": "magic",
            "board_column": "backlog",
            "assignee_name": "Not a collaborator",
            "subtasks": ["One", "Two"],
        },
        collaborators=[{"user_id": "user-1", "name": "Haley"}],
        elements=[],
        sources=["README.md:1"],
    )
    assert result["priority"] == "medium"
    assert result["category"] == "product"
    assert result["board_column"] == "todo"
    assert result["assigned_to"] is None


@pytest.mark.asyncio
async def test_task_draft_model_is_pinned_to_openai_luna():
    result = await task_draft_agent.resolve_model(
        "gemini-3.7-flash",
        company_id=uuid4(),
        user_id=uuid4(),
    )

    assert result == "gpt-5.6-luna"
