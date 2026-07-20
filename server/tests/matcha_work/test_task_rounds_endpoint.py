"""Regression tests for POST /projects/{id}/tasks/{id}/rounds.

Guards a NameError that shipped in the 2026-07-19 tasks.py split:
`start_task_round_endpoint` called `_verify_task_belongs_to_project`, but the
name lived only in `task_files.py` and was never imported into `tasks.py`, so
every "start next round" action 500'd on an unbound name. An import-only smoke
test can't catch that -- the lookup happens inside the function body -- so these
assert the name resolves in the handler's module globals AND drive the handler
far enough to execute that call.
"""
import pathlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.matcha.routes.matcha_work import tasks as tasks_mod
from app.matcha.routes.matcha_work import _shared, task_files


def test_verify_task_belongs_to_project_resolves_in_tasks_globals():
    """The exact name looked up at runtime inside start_task_round_endpoint."""
    fn = tasks_mod.__dict__.get("_verify_task_belongs_to_project")
    assert fn is not None, "_verify_task_belongs_to_project unbound in tasks.py"
    assert fn is _shared._verify_task_belongs_to_project


def test_single_definition_shared_by_both_modules():
    """_shared owns it; task_files no longer keeps a private copy."""
    assert task_files._verify_task_belongs_to_project is _shared._verify_task_belongs_to_project
    pkg_dir = pathlib.Path(_shared.__file__).parent
    definers = [
        p.name for p in sorted(pkg_dir.glob("*.py"))
        if "def _verify_task_belongs_to_project(" in p.read_text()
    ]
    assert definers == ["_shared.py"], definers


@pytest.mark.asyncio
async def test_start_round_executes_task_ownership_guard():
    """Drive the handler past the guard call: a task in another project 404s
    (rather than blowing up with NameError before it ever gets there)."""
    project_id, task_id = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="client")

    with patch.object(tasks_mod, "_verify_project_access", AsyncMock(return_value=({}, "owner"))), \
         patch.object(tasks_mod, "_verify_task_belongs_to_project", AsyncMock(
             side_effect=HTTPException(status_code=404, detail="Task not found"))) as guard:
        with pytest.raises(HTTPException) as exc:
            await tasks_mod.start_task_round_endpoint(
                project_id=project_id,
                task_id=task_id,
                body={"suggested_fix_title": "fix the thing"},
                current_user=user,
            )

    guard.assert_awaited_once_with(project_id, task_id)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Task not found"


@pytest.mark.asyncio
async def test_start_round_rejects_blank_title_after_guard_passes():
    """Guard passes -> handler continues to its own validation, proving the
    call at that line is reached and returns normally."""
    project_id, task_id = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="client")

    with patch.object(tasks_mod, "_verify_project_access", AsyncMock(return_value=({}, "owner"))), \
         patch.object(tasks_mod, "_verify_task_belongs_to_project", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await tasks_mod.start_task_round_endpoint(
                project_id=project_id,
                task_id=task_id,
                body={"suggested_fix_title": "   "},
                current_user=user,
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "suggested_fix_title required"
