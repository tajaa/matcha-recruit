"""`research` is a first-class kanban template kind (Espresso + web compose
sheets write `mw_tasks.category = "research"`, and the Kanban AutoPR lane
selects it as `mode: research`). Every server-side category allowlist must
accept it, or a research card 400s on create and the draft agents silently
downgrade it to another kind."""
import pytest

from app.matcha.services.matcha_work import project_task_service
from app.matcha.services.matcha_work.matcha_work_ai import task_draft
from app.matcha.services.matcha_work.project_agent import task_draft_agent


def test_every_category_allowlist_accepts_research():
    assert "research" in project_task_service._ALLOWED_CATEGORIES
    assert "research" in task_draft._TASK_DRAFT_CATEGORIES
    assert "research" in task_draft_agent._CATEGORIES


def test_category_allowlists_stay_in_sync():
    """Three copies of one list; a template added to one and not the others is
    exactly the drift this guards."""
    assert task_draft._TASK_DRAFT_CATEGORIES == project_task_service._ALLOWED_CATEGORIES
    assert task_draft_agent._CATEGORIES == project_task_service._ALLOWED_CATEGORIES


@pytest.mark.asyncio
async def test_create_task_rejects_unknown_category_before_touching_the_db():
    from uuid import uuid4

    with pytest.raises(ValueError, match="Invalid category"):
        await project_task_service.create_project_task(
            project_id=uuid4(),
            company_id=uuid4(),
            created_by=uuid4(),
            title="Research how AWS Lambda works",
            category="reserch",
        )
