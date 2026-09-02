from uuid import uuid4

import pytest

from app.matcha.routes.matcha_work import github
from app.matcha.services.matcha_work import project_task_service


@pytest.mark.asyncio
async def test_resolve_all_cross_lane_tasks_by_exact_persisted_number(monkeypatch):
    task_id, second_task_id = uuid4(), uuid4()
    project_id = next(iter(github._kanban_autopr_project_ids()))
    calls = []
    task = {
        "id": task_id,
        "project_id": project_id,
        "board_column": "in_progress",
        "progress_note": "🤖 AUTO SETUP · ALREADY SCOPED · PR #334",
        "pr_url": "https://github.com/tajaa/matcha-recruit/pull/334",
        "pr_number": 334,
        "pr_columns_exist": True,
    }
    second_task = {**task, "id": second_task_id}

    class Connection:
        async def fetch(self, query, *args):
            calls.append((query, args))
            return [task, second_task]

    class ConnectionContext:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(github, "get_connection", lambda: ConnectionContext())

    resolved = await github._resolve_pull_request_tasks({
        "repository": {"full_name": github._KANBAN_AUTOPR_REPO},
        "pull_request": {
            "number": 334,
            "body": "",
            "head": {"ref": "bot/err-5cf9ce1fea8b"},
        },
    })

    assert resolved == [task, second_task]
    assert len(calls) == 1
    assert "to_jsonb(mw_tasks) ->> 'pr_number' = $1" in calls[0][0]
    assert "LIMIT 1" not in calls[0][0]
    assert calls[0][1] == ("334",)


@pytest.mark.asyncio
async def test_resolver_unions_primary_trailer_task_with_secondary_links(monkeypatch):
    primary_id, secondary_id = uuid4(), uuid4()
    project_id = next(iter(github._kanban_autopr_project_ids()))
    base = {
        "project_id": project_id,
        "board_column": "in_progress",
        "progress_note": None,
        "pr_url": "https://github.com/tajaa/matcha-recruit/pull/334",
        "pr_number": 334,
        "pr_columns_exist": True,
    }
    primary = {**base, "id": primary_id}
    secondary = {**base, "id": secondary_id}

    class Connection:
        async def fetchrow(self, _query, *_args):
            return primary

        async def fetch(self, _query, *_args):
            return [primary, secondary]

    class ConnectionContext:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(github, "get_connection", lambda: ConnectionContext())

    resolved = await github._resolve_pull_request_tasks({
        "repository": {"full_name": github._KANBAN_AUTOPR_REPO},
        "pull_request": {
            "number": 334,
            "body": f"<!-- matcha-task: {primary_id} -->",
            "head": {"ref": "bot/task-primary"},
        },
    })

    assert resolved == [primary, secondary]


def test_autopr_marker_preserves_existing_progress_and_is_idempotent():
    marked = github._with_autopr_progress_note("Waiting on QA")
    assert marked == "🤖 AUTO SETUP · MERGED: READY FOR REVIEW · Waiting on QA"
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

    assert marked == (
        "🤖 AUTO SETUP · MERGED: READY FOR REVIEW · build 550 · "
        "prod c5d3a49 · PR #295 · Waiting on QA"
    )

    reworked = github._with_autopr_progress_note(
        "from auto setup · build 549 · prod abc1234 · PR #294 · Waiting on QA",
        pr_body=body,
        pr_number=295,
    )
    assert reworked == marked


def test_autopr_marker_replaces_stale_triage_suffix_from_rework_trailers():
    body = """<!-- matcha-production-build: 850 -->
<!-- matcha-production-backend-sha: bbbbbbb -->
<!-- matcha-production-frontend-sha: bbbbbbb -->
<!-- matcha-autopr-criticality: yellow -->
<!-- matcha-autopr-confidence-score: 88 -->
<!-- matcha-autopr-note-state: ready_for_review -->"""

    marked = github._with_autopr_progress_note(
        "from auto setup · build 849 · prod aaaaaaa · PR #295 · 🔴 C42 · awaiting answers · Human note",
        pr_body=body,
        pr_number=295,
    )

    assert marked == (
        "🤖 AUTO SETUP · MERGED: READY FOR REVIEW · build 850 · "
        "prod bbbbbbb · PR #295 · 🟡 C88 · Human note"
    )


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
        return [task]

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_tasks", resolve)
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
            "progress_note": "🤖 AUTO SETUP · MERGED: READY FOR REVIEW · PR #42 · Tests are green",
            "pr_url": "https://github.com/tajaa/matcha-recruit/pull/42",
            "pr_number": 42,
        },
    )]


@pytest.mark.asyncio
async def test_merged_owner_pr_moves_every_linked_card_to_review(monkeypatch):
    first_id, second_id, project_id = uuid4(), uuid4(), uuid4()
    base = {
        "project_id": project_id,
        "board_column": "in_progress",
        "progress_note": None,
        "pr_url": "https://github.com/tajaa/matcha-recruit/pull/334",
        "pr_number": 334,
    }
    tasks = [{**base, "id": first_id}, {**base, "id": second_id}]
    updates = []

    async def resolve(_payload):
        return tasks

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_tasks", resolve)
    monkeypatch.setattr(project_task_service, "update_project_task", update)

    result = await github._handle_pull_request_event({
        "action": "closed",
        "pull_request": {
            "merged": True,
            "html_url": "https://github.com/tajaa/matcha-recruit/pull/334",
            "number": 334,
        },
    })

    assert result == {
        "ok": True,
        "task": str(first_id),
        "tasks": [str(first_id), str(second_id)],
        "merged": True,
    }
    assert [task_id for _project_id, task_id, _patch in updates] == [
        first_id,
        second_id,
    ]
    assert all(
        patch["board_column"] == "review"
        for _project_id, _task_id, patch in updates
    )


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
        return [task]

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_tasks", resolve)
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
            "progress_note": "🤖 AUTO SETUP · MERGED: READY FOR REVIEW · PR #43",
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
        return [task]

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_tasks", resolve)
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
            "progress_note": "🤖 AUTO SETUP · MERGED: READY FOR REVIEW · PR #45",
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
        return [task]

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_tasks", resolve)
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
        "progress_note": "🤖 AUTO SETUP · MERGED: READY FOR REVIEW · PR #44 · Tests are green",
        "pr_url": pr_url,
        "pr_number": 44,
    }
    updates = []

    async def resolve(_payload):
        return [task]

    async def update(project, task, patch):
        updates.append((project, task, patch))

    monkeypatch.setattr(github, "_resolve_pull_request_tasks", resolve)
    monkeypatch.setattr(project_task_service, "update_project_task", update)

    await github._handle_pull_request_event({
        "action": "closed",
        "pull_request": {"merged": True, "html_url": pr_url, "number": 44},
    })

    assert updates == []
