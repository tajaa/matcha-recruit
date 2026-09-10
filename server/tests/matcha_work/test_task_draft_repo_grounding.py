"""The one-shot AI ticket draft receives connected-repository evidence."""

import json
from types import SimpleNamespace

import pytest

from app.core.services import ai_usage
from app.matcha.services.huume.luna_client import LunaResponse
from app.matcha.services.matcha_work.matcha_work_ai import task_draft


class _Models:
    def __init__(self):
        self.contents = ""

    async def create_response(self, *, model, input, instructions, **kwargs):
        self.model = model
        self.contents = input
        self.instructions = instructions
        self.kwargs = kwargs
        self.feature = ai_usage._feature_override.get()
        return LunaResponse(response_id="r", text=json.dumps({
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
    client = models
    monkeypatch.setattr(task_draft, "get_luna_client", lambda: client)

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

    prompt = models.contents[0]["content"][0]["text"]
    assert models.model == "gpt-5.6-luna"
    assert models.feature == "matcha.espresso.task_draft"
    assert "<repository_context>" in prompt
    assert "server/app/products/routes.py" in prompt
    assert "UNTRUSTED code/document content" in prompt
    assert result["subtasks"] == ["Update server/app/products/routes.py"]
    # JSON mode is what keeps an unparseable reply from degrading into a
    # 200 OK ticket titled with the raw prompt.
    assert models.kwargs["response_format_json"] is True


class _BadJSONModels:
    async def create_response(self, *, model, input, instructions, **kwargs):
        return LunaResponse(response_id="r", text="Sure! Here is the ticket you asked for.")


@pytest.mark.asyncio
async def test_unparseable_model_output_raises_instead_of_silent_fallback(monkeypatch):
    client = _BadJSONModels()
    monkeypatch.setattr(task_draft, "get_luna_client", lambda: client)

    with pytest.raises(RuntimeError):
        await task_draft.generate_task_draft(
            prompt="Let sellers edit products",
            project_title="Marketplace",
            collaborator_names=[],
            elements=[],
        )


def test_subtask_cleanup_keeps_leading_digits():
    assert task_draft._LIST_PREFIX.sub("", "2FA login flow") == "2FA login flow"
    assert task_draft._LIST_PREFIX.sub("", "401 handling in APIClient") == "401 handling in APIClient"
    assert task_draft._LIST_PREFIX.sub("", "1. Wire the UI") == "Wire the UI"
    assert task_draft._LIST_PREFIX.sub("", "- Add tests") == "Add tests"
