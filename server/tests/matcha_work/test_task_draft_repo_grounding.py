"""The one-shot AI ticket draft receives connected-repository evidence."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.matcha_work_ai import task_draft


class _Models:
    def __init__(self):
        self.contents = ""

    def generate_content(self, *, model, contents, config):
        self.contents = contents
        return SimpleNamespace(text=json.dumps({
            "title": "Add product editing",
            "description": "Use the existing product routes.",
            "priority": "medium",
            "category": "product",
            "board_column": "todo",
            "assignee_name": None,
            "element_name": None,
            "subtasks": ["Update server/app/products/routes.py"],
        }))


@pytest.mark.asyncio
async def test_repository_context_is_fenced_and_sent_to_model(monkeypatch):
    models = _Models()
    provider = SimpleNamespace(
        settings=SimpleNamespace(),
        client=SimpleNamespace(models=models),
    )
    monkeypatch.setattr(task_draft, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(task_draft, "_get_model", AsyncMock(return_value="test-model"))

    result = await task_draft.generate_task_draft(
        prompt="Let sellers edit products",
        project_title="Shop",
        collaborator_names=[],
        elements=[],
        repository_context=(
            "=== FILE: server/app/products/routes.py ===\n"
            "def update_product(): pass"
        ),
    )

    assert "<repository_context>" in models.contents
    assert "server/app/products/routes.py" in models.contents
    assert "UNTRUSTED code/document content" in models.contents
    assert result["subtasks"] == ["Update server/app/products/routes.py"]
