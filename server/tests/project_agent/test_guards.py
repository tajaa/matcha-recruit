from app.matcha.services.matcha_work.project_agent.guards import (
    MAX_READ_LINES,
    can_ask_project_agent,
    is_sensitive_read_path,
    numbered_line_window,
)
from app.matcha.services.matcha_work.project_agent.prompt import build_system_prompt
from app.matcha.services.matcha_work.project_agent.tools import declarations


def test_project_access_allows_tenant_users_and_external_collaborators():
    company_id = object()
    assert can_ask_project_agent(
        sender_company_id=company_id,
        project_company_id=company_id,
        collaborator_role=None,
    )
    assert can_ask_project_agent(
        sender_company_id=object(),
        project_company_id=company_id,
        collaborator_role="viewer",
    )
    assert not can_ask_project_agent(
        sender_company_id=None,
        project_company_id=company_id,
        collaborator_role=None,
    )


def test_secret_paths_and_traversal_are_never_read():
    for path in (
        ".env",
        "server/.env.production",
        "secrets/token.txt",
        "config/credentials.json",
        "keys/signing.pem",
        "../outside.txt",
    ):
        assert is_sensitive_read_path(path)
    assert not is_sensitive_read_path("server/app/main.py")
    assert not is_sensitive_read_path(".github/workflows/tests.yml")


def test_source_windows_are_numbered_and_bounded():
    source = "\n".join(f"line {number}" for number in range(1, 1000))
    window = numbered_line_window(source, start_line=10, end_line=900)
    assert window["start_line"] == 10
    assert window["end_line"] == 10 + MAX_READ_LINES - 1
    assert window["content"].startswith("10: line 10")
    assert f"{window['end_line']}: line {window['end_line']}" in window["content"]


def test_agent_surface_has_only_read_and_answer_tools():
    names = {tool.name for tool in declarations()}
    assert names == {"list_files", "search_repo", "read_file", "answer_question"}
    assert not names.intersection({"write_file", "delete_file", "open_pr", "run_command"})


def test_prompt_requires_grounding_and_forbids_mutation():
    prompt = build_system_prompt()
    assert "read-only" in prompt
    assert "cannot edit files" in prompt
    assert "path:line" in prompt
    assert "instead of\nguessing" in prompt
