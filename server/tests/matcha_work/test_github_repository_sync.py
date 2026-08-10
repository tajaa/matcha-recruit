"""Connected-repo sync must work before users define component path globs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.matcha.routes.matcha_work import github as github_routes
from app.matcha.services.matcha_work import github_service


@pytest.mark.asyncio
async def test_sync_indexes_connected_repo_without_user_elements():
    project_id = uuid4()
    user = SimpleNamespace(id=uuid4(), role="client")
    root_id = "repository-snapshot-element"
    root_summary = {"stored": 42, "skipped": 3, "total_bytes": 9000, "fetched": 42}

    with (
        patch.object(
            github_routes,
            "_verify_project_access",
            AsyncMock(return_value=({"github_repo": "acme/shop", "github_branch": "main"}, "owner")),
        ),
        patch.object(github_routes, "_list_project_elements", AsyncMock(return_value=[])),
        patch.object(
            github_service,
            "ensure_repository_snapshot_element",
            AsyncMock(return_value=root_id),
        ) as ensure,
        patch.object(
            github_service,
            "sync_element",
            AsyncMock(return_value=root_summary),
        ) as sync,
    ):
        result = await github_routes.github_sync_endpoint(
            project_id=project_id,
            body={},
            current_user=user,
        )

    ensure.assert_awaited_once_with(project_id, "acme/shop", "main")
    sync.assert_awaited_once_with(
        project_id,
        root_id,
        github_service.REPOSITORY_SNAPSHOT_GLOBS,
        repo="acme/shop",
        ref="main",
    )
    assert result["total_stored"] == 42
    assert result["elements"][0]["scope"] == "repository"
