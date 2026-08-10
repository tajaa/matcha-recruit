import pytest

from app.matcha.services.matcha_work.github_service import GitHubError
from app.matcha.services.matcha_work import github_write


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.text = ""

    def json(self):
        return self._payload


class _ExistingBranchClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def request(self, method, _url, **_kwargs):
        assert method == "GET"
        return _Response(200, {"object": {"sha": "base-sha"}})

    async def get(self, _url, **_kwargs):
        return _Response(200, {"object": {"sha": "existing-branch-sha"}})


class _ExistingDraftClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, _url, **_kwargs):
        return _Response(422, {"message": "A pull request already exists"})

    async def get(self, _url, **_kwargs):
        return _Response(200, [{"number": 9, "draft": True, "html_url": "https://example.test/pr/9"}])


def test_write_allowlist_fails_closed(monkeypatch):
    monkeypatch.delenv("GITHUB_WRITE_ALLOWED_REPOS", raising=False)
    try:
        github_write.assert_write_allowed("tajaa/scratch")
    except GitHubError as exc:
        assert "GITHUB_WRITE_ALLOWED_REPOS" in str(exc)
    else:
        raise AssertionError("empty write allowlist must deny writes")


def test_write_allowlist_matches_exact_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_WRITE_ALLOWED_REPOS", "tajaa/scratch, other/repo")
    assert github_write.assert_write_allowed("tajaa/scratch") == "tajaa/scratch"
    try:
        github_write.assert_write_allowed("tajaa/scratch-fork")
    except GitHubError:
        pass
    else:
        raise AssertionError("allowlist must be exact")


@pytest.mark.asyncio
async def test_existing_branch_returns_its_head_for_a_non_force_retry(monkeypatch):
    monkeypatch.setenv("GITHUB_WRITE_ALLOWED_REPOS", "tajaa/scratch")
    monkeypatch.setattr(github_write.httpx, "AsyncClient", lambda **_kwargs: _ExistingBranchClient())
    assert await github_write.ensure_branch("tajaa/scratch", "main", "huume/task") == "existing-branch-sha"


@pytest.mark.asyncio
async def test_existing_draft_pr_is_reused(monkeypatch):
    monkeypatch.setenv("GITHUB_WRITE_ALLOWED_REPOS", "tajaa/scratch")
    monkeypatch.setattr(github_write.httpx, "AsyncClient", lambda **_kwargs: _ExistingDraftClient())
    result = await github_write.open_draft_pr("tajaa/scratch", "huume/task", "main", "Title", "Body")
    assert result["number"] == 9
