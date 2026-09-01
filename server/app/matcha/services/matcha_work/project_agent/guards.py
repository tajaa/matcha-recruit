"""Pure authorization and repository-read guards for project agents."""
from __future__ import annotations


MAX_READ_LINES = 400
MAX_READ_CHARS = 60_000


def can_ask_project_agent(
    *,
    sender_company_id,
    project_company_id,
    collaborator_role: str | None,
) -> bool:
    """Mirror project read access without trusting channel membership alone.

    Same-company users can read their tenant's projects. Cross-company users
    (including platform admins) must be active project collaborators; callers
    pass ``None`` when no active collaborator row exists. Read-only roles are
    deliberately admitted because this agent cannot mutate the repository.
    """
    return (
        sender_company_id is not None
        and sender_company_id == project_company_id
    ) or collaborator_role is not None


def is_sensitive_read_path(path: str) -> bool:
    """Reject traversal and common secret-bearing tracked paths."""
    normalized = (path or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        return True
    parts = [part.lower() for part in normalized.split("/")]
    filename = parts[-1]
    return (
        "secrets" in parts
        or any(part.startswith(".env") for part in parts)
        or filename in {"credentials", "credentials.json", "id_rsa", "id_ed25519"}
        or filename.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def numbered_line_window(
    content: str,
    start_line: int = 1,
    end_line: int | None = None,
) -> dict:
    """Return a bounded, numbered source window suitable for model grounding."""
    lines = (content or "").splitlines()
    total = len(lines)
    start = max(1, int(start_line or 1))
    requested_end = int(end_line) if end_line is not None else start + 199
    end = min(total, max(start, requested_end), start + MAX_READ_LINES - 1)
    selected = lines[start - 1:end] if start <= total else []
    rendered = "\n".join(f"{number}: {line}" for number, line in enumerate(selected, start))
    if len(rendered) > MAX_READ_CHARS:
        rendered = rendered[:MAX_READ_CHARS] + "\n[window truncated]"
    return {
        "start_line": start,
        "end_line": end if selected else None,
        "total_lines": total,
        "content": rendered,
    }
