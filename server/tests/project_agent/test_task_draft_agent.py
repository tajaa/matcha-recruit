from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from google.genai import types

from app.core.services import ai_usage
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
        self.calls.append({
            **kwargs,
            "feature": ai_usage._feature_override.get(),
        })
        return self.responses.pop(0)


def test_task_draft_surface_is_read_only_and_structured():
    names = {tool.name for tool in task_draft_declarations()}
    assert names == {"draft_ticket"}
    assert not names.intersection({"write_file", "open_pr", "run_command", "create_task"})
    prompt = build_task_draft_system_prompt()
    assert "read-only" in prompt
    assert "cannot edit files" in prompt
    assert "path:line" in prompt
    assert "CLAUDE.md" in prompt
    assert "broader source discovery" in prompt


@pytest.mark.asyncio
async def test_task_draft_reads_architecture_guide_and_returns_resolved_review_draft(monkeypatch):
    draft_args = {
        "title": "Add saved project filters",
        "description": "Add reusable filters to the project board.\n\nAcceptance: filters persist and can be cleared.",
        "priority": "medium",
        "category": "product",
        "board_column": "todo",
        "assignee_name": "Haley",
        "element_name": "Desktop",
        "subtasks": ["Update the desktop project board", "Add focused drafting coverage"],
        "sources": ["CLAUDE.md:12-18"],
    }
    models = _FakeModels([
        _response(types.Part.from_function_call(name="draft_ticket", args=draft_args)),
    ])
    fake_client = SimpleNamespace(aio=SimpleNamespace(models=models))
    get_client = Mock(return_value=fake_client)
    monkeypatch.setattr(task_draft_agent, "get_luna_client", get_client)
    read_repo_file = AsyncMock(return_value={
        "path": "CLAUDE.md",
        "start_line": 1,
        "end_line": 20,
        "total_lines": 20,
        "content": "12: Espresso lives under platforms/desktop/Espresso/",
    })
    monkeypatch.setattr(task_draft_agent.store, "read_repo_file", read_repo_file)
    repo_tree = AsyncMock()
    search_snapshot = AsyncMock()
    monkeypatch.setattr(task_draft_agent.store, "repo_tree", repo_tree)
    monkeypatch.setattr(task_draft_agent.store, "search_snapshot", search_snapshot)
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
        collaborators=[{"user_id": str(user_id), "name": "Haley"}],
        elements=[{"id": "element-1", "name": "Desktop", "description": "macOS app"}],
        recent_done=[],
    )

    assert result["draft"]["assigned_to"] == str(user_id)
    assert result["draft"]["element_id"] == "element-1"
    assert result["draft"]["grounding_sources"] == draft_args["sources"]
    assert result["files_read"] == 1
    assert result["model_calls"] == 1
    assert result["token_usage"]["total_tokens"] == 17
    assert result["token_usage"]["model"] == "gpt-5.6-luna"
    assert all(call["model"] == "gpt-5.6-luna" for call in models.calls)
    assert all(call["feature"] == "matcha.espresso.task_draft" for call in models.calls)
    get_client.assert_called_once_with()
    read_repo_file.assert_awaited_once_with(
        "example/matcha", "main", "CLAUDE.md", start_line=1, end_line=400,
    )
    repo_tree.assert_not_awaited()
    search_snapshot.assert_not_awaited()
    assert mark_run.await_args.kwargs["status"] == "done"
    assert mark_run.await_args.kwargs["result"]["title"] == "Add saved project filters"


@pytest.mark.asyncio
async def test_task_draft_falls_back_to_root_agents_guide(monkeypatch):
    models = _FakeModels([
        _response(types.Part.from_function_call(name="draft_ticket", args={
            "title": "Clarify the project task",
            "description": "Use the repository architecture guide to scope the task.",
            "priority": "medium",
            "category": "product",
            "board_column": "todo",
            "subtasks": ["Confirm the owning surface", "Implement and validate the change"],
            "sources": ["AGENTS.md:1"],
        })),
    ])
    monkeypatch.setattr(
        task_draft_agent,
        "get_luna_client",
        Mock(return_value=SimpleNamespace(aio=SimpleNamespace(models=models))),
    )
    read_repo_file = AsyncMock(side_effect=[
        FileNotFoundError("CLAUDE.md"),
        {
            "path": "AGENTS.md",
            "start_line": 1,
            "end_line": 3,
            "total_lines": 3,
            "content": "1: Repository architecture and ownership guidance.",
        },
    ])
    monkeypatch.setattr(task_draft_agent.store, "read_repo_file", read_repo_file)
    monkeypatch.setattr(task_draft_agent.store, "record_step", AsyncMock())
    monkeypatch.setattr(task_draft_agent.store, "mark_run", AsyncMock())

    result = await task_draft_agent.run_task_draft(
        run_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        requested_by=uuid4(),
        request="Clarify this task",
        project_title="MATCHA",
        repo="example/matcha",
        base_branch="main",
        collaborators=[],
        elements=[],
        recent_done=[],
    )

    assert result["draft"]["grounding_sources"] == ["AGENTS.md:1"]
    assert result["files_read"] == 1
    assert [call.args[2] for call in read_repo_file.await_args_list] == [
        "CLAUDE.md", "AGENTS.md",
    ]


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


def test_task_draft_model_is_pinned_to_openai_luna():
    assert task_draft_agent.TASK_DRAFT_MODEL == "gpt-5.6-luna"


def test_match_named_refuses_short_and_ambiguous_fragments():
    people = [
        {"user_id": "user-1", "name": "Haley"},
        {"user_id": "user-2", "name": "Pete"},
        {"user_id": "user-3", "name": "Haley Stewart"},
    ]
    # A one-character artifact used to bind to the first name containing it.
    assert task_draft_agent.match_named("a", people) is None
    assert task_draft_agent.match_named("e", people) is None
    # A real but ambiguous fragment must not pick a person arbitrarily.
    assert task_draft_agent.match_named("haley", people)["user_id"] == "user-1"
    assert task_draft_agent.match_named("stew", people)["user_id"] == "user-3"
    assert task_draft_agent.match_named("hale", people) is None


def test_clean_list_keeps_leading_digits_in_real_text():
    cleaned = task_draft_agent._clean_list(
        ["2FA login flow must be covered", "3D map export", "1. Wire the UI", "- Add tests"],
        limit=10,
        item_chars=200,
    )
    assert cleaned == [
        "2FA login flow must be covered",
        "3D map export",
        "Wire the UI",
        "Add tests",
    ]


def test_task_draft_citations_must_name_the_loaded_root_guide_exactly():
    files_read = {"CLAUDE.md"}
    assert task_draft_agent._is_citation_for_loaded_guide("CLAUDE.md:12-18", files_read)
    assert not task_draft_agent._is_citation_for_loaded_guide(
        "server/CLAUDE.md:12-18", files_read,
    )
    assert not task_draft_agent._is_citation_for_loaded_guide(
        "See CLAUDE.md:12", files_read,
    )
