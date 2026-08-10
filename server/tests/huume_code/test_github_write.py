from app.matcha.services.matcha_work.github_service import GitHubError
from app.matcha.services.matcha_work import github_write


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
