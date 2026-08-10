from app.matcha.services.huume_code.guards import (
    MAX_FILE_BYTES,
    WorkingSet,
    branch_name,
    can_dispatch_huume_code,
    is_denied_path,
)


def test_sensitive_paths_are_always_denied():
    for path in (
        ".github/workflows/ci.yml", "secrets/x.pem", ".env.backend",
        "server/.env", "config/.env.production", "deploy/nginx/default.conf",
    ):
        assert is_denied_path(path)
    assert not is_denied_path("server/app/main.py")


def test_working_set_reads_its_own_writes_and_deletions():
    staged = WorkingSet()
    staged.write("server/app/example.py", "new")
    assert staged.read("server/app/example.py", "old") == "new"
    staged.delete("server/app/example.py")
    assert staged.read("server/app/example.py", "old") is None


def test_working_set_enforces_size_cap():
    staged = WorkingSet()
    try:
        staged.write("server/app/large.py", "x" * (MAX_FILE_BYTES + 1))
    except ValueError as exc:
        assert "80 KB" in str(exc)
    else:
        raise AssertionError("expected file cap rejection")


def test_branch_name_is_scoped_and_slugged():
    assert branch_name("12345678-1234", "Fix Login Timeout!") == "huume/12345678-fix-login-timeout"


def test_code_dispatch_requires_project_access_for_platform_admins():
    company_id = object()
    assert not can_dispatch_huume_code(
        sender_role="admin", sender_company_id=None, project_company_id=company_id, collaborator_role=None,
    )
    assert can_dispatch_huume_code(
        sender_role="admin", sender_company_id=None, project_company_id=company_id, collaborator_role="editor",
    )
    assert not can_dispatch_huume_code(
        sender_role="client", sender_company_id=object(), project_company_id=company_id, collaborator_role="owner",
    )
