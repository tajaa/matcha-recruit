from uuid import uuid4

import pytest

from app.matcha.routes.matcha_work import github
from app.matcha.services.matcha_work import project_task_service


def test_autopr_marker_preserves_existing_progress_and_is_idempotent():
    marked = github._with_autopr_progress_note("Waiting on QA")
    assert marked == "from auto setup · Waiting on QA"
    assert github._with_autopr_progress_note(marked) == marked


def test_autopr_marker_recovers_production_build_from_pr_trailers():
    body = """<!-- matcha-production-build: 550 -->
<!-- matcha-production-backend-sha: c5d3a49 -->
<!-- matcha-production-frontend-sha: c5d3a49 -->"""

    marked = github._with_autopr_progress_note(
        "Waiting on QA",
        pr_body=body,
        pr_number=295,
    )

    assert marked == "from auto setup · build 550 · prod c5d3a49 · PR #295 · Waiting on QA"

    reworked = github._with_autopr_progress_note(
        "from auto setup · build 549 · prod abc1234 · PR #294 · Waiting on QA",
        pr_body=body,
        pr_number=295,
    )
    assert reworked == marked


@pytest.mark.asyncio
async def test_merged_autopr_moves_card_to_review_and_marks_its_origin(monkeypatch):
    task_id, project_id = uuid4(), uuid4()
    task = {
        "id": task_id,
        "project_id": project_id,
        "board_column": "in_progress",
        "progress_note": "Tests are green",
        "pr_url": None,
        "pr_number": None,
    }
    updates = []

    async def resolve(_payload):
        return task

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_task", resolve)
    monkeypatch.setattr(project_task_service, "update_project_task", update)

    result = await github._handle_pull_request_event({
        "action": "closed",
        "pull_request": {
            "merged": True,
            "html_url": "https://github.com/tajaa/matcha-recruit/pull/42",
            "number": 42,
        },
    })

    assert result == {"ok": True, "task": str(task_id), "merged": True}
    assert updates == [(
        project_id,
        task_id,
        {
            "board_column": "review",
            "progress_note": "from auto setup · Tests are green",
            "pr_url": "https://github.com/tajaa/matcha-recruit/pull/42",
            "pr_number": 42,
        },
    )]


@pytest.mark.asyncio
async def test_merged_autopr_marks_a_card_already_in_review_without_moving_it(monkeypatch):
    task_id, project_id = uuid4(), uuid4()
    task = {
        "id": task_id,
        "project_id": project_id,
        "board_column": "review",
        "progress_note": None,
        "pr_url": None,
        "pr_number": None,
    }
    updates = []

    async def resolve(_payload):
        return task

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_task", resolve)
    monkeypatch.setattr(project_task_service, "update_project_task", update)

    await github._handle_pull_request_event({
        "action": "closed",
        "pull_request": {
            "merged": True,
            "html_url": "https://github.com/tajaa/matcha-recruit/pull/43",
            "number": 43,
        },
    })

    assert updates == [(
        project_id,
        task_id,
        {
            "progress_note": "from auto setup",
            "pr_url": "https://github.com/tajaa/matcha-recruit/pull/43",
            "pr_number": 43,
        },
    )]


@pytest.mark.asyncio
async def test_merged_autopr_without_pr_columns_still_moves_card(monkeypatch):
    task_id, project_id = uuid4(), uuid4()
    task = {
        "id": task_id,
        "project_id": project_id,
        "board_column": "in_progress",
        "progress_note": None,
        "pr_url": None,
        "pr_number": None,
        "pr_columns_exist": False,
    }
    updates = []

    async def resolve(_payload):
        return task

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_task", resolve)
    monkeypatch.setattr(project_task_service, "update_project_task", update)

    result = await github._handle_pull_request_event({
        "action": "closed",
        "pull_request": {
            "merged": True,
            "html_url": "https://github.com/tajaa/matcha-recruit/pull/45",
            "number": 45,
        },
    })

    assert result == {"ok": True, "task": str(task_id), "merged": True}
    assert updates == [(
        project_id,
        task_id,
        {
            "board_column": "review",
            "progress_note": "from auto setup",
        },
    )]


@pytest.mark.asyncio
async def test_opened_autopr_without_pr_columns_still_starts_card(monkeypatch):
    task_id, project_id = uuid4(), uuid4()
    task = {
        "id": task_id,
        "project_id": project_id,
        "board_column": "todo",
        "progress_note": None,
        "pr_url": None,
        "pr_number": None,
        "pr_columns_exist": False,
    }
    updates = []

    async def resolve(_payload):
        return task

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_task", resolve)
    monkeypatch.setattr(project_task_service, "update_project_task", update)

    result = await github._handle_pull_request_event({
        "action": "opened",
        "pull_request": {
            "html_url": "https://github.com/tajaa/matcha-recruit/pull/46",
            "number": 46,
        },
    })

    assert result == {"ok": True, "task": str(task_id)}
    assert updates == [(project_id, task_id, {"board_column": "in_progress"})]


@pytest.mark.asyncio
async def test_merged_autopr_redelivery_is_a_true_noop(monkeypatch):
    task_id, project_id = uuid4(), uuid4()
    pr_url = "https://github.com/tajaa/matcha-recruit/pull/44"
    task = {
        "id": task_id,
        "project_id": project_id,
        "board_column": "review",
        "progress_note": "from auto setup · Tests are green",
        "pr_url": pr_url,
        "pr_number": 44,
    }
    updates = []

    async def resolve(_payload):
        return task

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_task", resolve)
    monkeypatch.setattr(project_task_service, "update_project_task", update)

    await github._handle_pull_request_event({
        "action": "closed",
        "pull_request": {"merged": True, "html_url": pr_url, "number": 44},
    })

    assert updates == []
