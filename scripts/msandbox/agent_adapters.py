from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from .capabilities import (
    collect_report,
    container_report_paths,
    render_markdown,
    write_report,
)
from .docker_runtime import compose_command, compose_environment, exec_in_session, session_home
from .models import Attachment, CapabilityReport, SessionRecord
from .session_auth import refresh_github_auth


class AgentError(RuntimeError):
    pass


def agent_argv(
    agent: str,
    extra: Sequence[str] = (),
    *,
    permission_mode: str = "standard",
) -> list[str]:
    if permission_mode not in ("standard", "autonomous"):
        raise AgentError(f"unsupported permission mode: {permission_mode}")
    if agent == "codex":
        autonomous = (
            ["--dangerously-bypass-approvals-and-sandbox"]
            if permission_mode == "autonomous"
            else []
        )
        return ["codex", *autonomous, *extra]
    if agent == "claude":
        autonomous = (
            ["--dangerously-skip-permissions"]
            if permission_mode == "autonomous"
            else []
        )
        return ["claude", *autonomous, *extra]
    if agent == "opencode":
        autonomous = ["--auto"] if permission_mode == "autonomous" else []
        return ["opencode", *autonomous, *extra]
    raise AgentError(f"unsupported agent: {agent}")


# Each agent's own documented context mechanism. Claude Code accepts a system
# prompt file directly; Codex and OpenCode read a global instructions file from
# the agent home, which is private to this session because the whole home is.
CAPABILITY_CONTEXT_FILES: dict[str, tuple[str, ...]] = {
    "codex": (".codex/AGENTS.md",),
    "claude": (".claude/CLAUDE.md",),
    "opencode": (".config/opencode/AGENTS.md",),
}


def capability_context_args(agent: str) -> list[str]:
    """CLI arguments that inject the measured report as developer context."""
    _, markdown = container_report_paths()
    if agent == "claude":
        return ["--append-system-prompt-file", markdown]
    if agent in ("codex", "opencode"):
        # Both read their global instructions file; see CAPABILITY_CONTEXT_FILES.
        return []
    raise AgentError(f"unsupported agent: {agent}")


def _install_capability_files(record: SessionRecord, markdown: str) -> tuple[Path, ...]:
    home = session_home(record)
    written: list[Path] = []
    for relative in CAPABILITY_CONTEXT_FILES.get(record.agent, ()):
        destination = home / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = destination.parent / f".{destination.name}.msandbox"
        temporary.write_text(markdown, encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, destination)
        written.append(destination)
    return tuple(written)


def refresh_capability_context(
    record: SessionRecord,
    *,
    container_available: bool = True,
) -> CapabilityReport | None:
    """Measure this session and publish the same report to disk and the agent.

    A probe failure never blocks the session; the report itself records it.
    """
    try:
        report = collect_report(record, container_available=container_available)
        path = write_report(record, report)
        _install_capability_files(record, render_markdown(report, name=record.name))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Warning: capability report is unavailable ({exc}).", file=sys.stderr)
        return None
    record.last_capability_check_at = report.checked_at
    record.capability_report_path = str(path)
    return report


def tmux_running(record: SessionRecord) -> bool:
    if not shutil.which("tmux"):
        return False
    exists = subprocess.run(
        ["tmux", "has-session", "-t", record.tmux_session],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not exists:
        return False
    panes = subprocess.run(
        ["tmux", "list-panes", "-t", record.tmux_session, "-F", "#{pane_dead}"],
        check=False,
        text=True,
        capture_output=True,
    )
    return panes.returncode == 0 and any(line.strip() == "0" for line in panes.stdout.splitlines())


def _tmux_exists(record: SessionRecord) -> bool:
    return bool(
        shutil.which("tmux")
        and subprocess.run(
            ["tmux", "has-session", "-t", record.tmux_session],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def launch_agent(record: SessionRecord, extra: Sequence[str] = ()) -> None:
    """Start one durable TUI per session; other sessions are never inspected or blocked."""
    if not shutil.which("tmux"):
        raise AgentError("tmux is required for durable msandbox sessions")
    if tmux_running(record):
        return
    context_args = capability_context_args(record.agent)
    if not context_args:
        _start_agent_pane(record, extra)
        return
    try:
        _start_agent_pane(record, [*context_args, *extra])
    except AgentError:
        # An older pinned agent build may not accept the context flag. The
        # session is more valuable than the injection, and the same report is
        # still on disk at the path the report itself names.
        print(
            "Warning: this agent build rejected the capability-context flag; "
            "the report remains at "
            f"{container_report_paths()[1]}.",
            file=sys.stderr,
        )
        _start_agent_pane(record, extra)


def _start_agent_pane(record: SessionRecord, extra: Sequence[str] = ()) -> None:
    subprocess.run(
        ["tmux", "kill-session", "-t", record.tmux_session],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    compose = compose_command(
        record,
        "exec",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "workspace",
        *agent_argv(record.agent, extra, permission_mode=record.permission_mode),
    )
    compose_env = compose_environment(record)
    forwarded = [
        f"{key}={value}"
        for key, value in sorted(compose_env.items())
        if key.startswith(("SANDBOX_", "MSANDBOX_"))
    ]
    command = ["env", *forwarded, *compose]
    # A long-lived host tmux server can retain PWD from an older, pruned
    # controller release. tmux's -c records the requested session path, but
    # zsh can still inherit the deleted server cwd. Repair it in the command
    # itself before Docker Compose starts so neither this pane nor terminals
    # opened from it propagate an unreachable directory.
    shell_command = (
        f"cd {shlex.quote(str(record.worktree))} && exec {shlex.join(command)}"
    )
    result = subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            record.tmux_session,
            "-c",
            str(record.worktree),
            shell_command,
        ],
        env=compose_env,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise AgentError(result.stderr.strip() or "tmux could not start the agent")
    subprocess.run(
        ["tmux", "set-option", "-t", record.tmux_session, "remain-on-exit", "on"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "tmux",
            "set-option",
            "-t",
            record.tmux_session,
            "status-right",
            "Ctrl-b s: sessions · Ctrl-b d: detach | %H:%M",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Catch immediate failures such as a missing login, executable, or native
    # renderer instead of recording a dead pane as a running session.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and tmux_running(record):
        time.sleep(0.1)
    if not tmux_running(record):
        captured = subprocess.run(
            ["tmux", "capture-pane", "-pt", record.tmux_session, "-S", "-120"],
            check=False,
            text=True,
            capture_output=True,
        )
        detail = captured.stdout.strip()[-4000:]
        raise AgentError(detail or f"{record.agent} exited during startup")


def attach_agent(record: SessionRecord) -> int:
    refresh_github_auth(record)
    if not tmux_running(record):
        raise AgentError(f"agent session is not running: {record.name}")
    # The PTY proxy preserves arbitrary input while rewriting a complete
    # bracketed-paste host file path into a session-local /attachments path.
    from .pty_proxy import attach_with_file_proxy

    return attach_with_file_proxy(record)


def stop_agent(record: SessionRecord, *, force: bool = False) -> None:
    if not _tmux_exists(record):
        return
    if not force and tmux_running(record):
        subprocess.run(
            ["tmux", "send-keys", "-t", record.tmux_session, "C-c"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    subprocess.run(
        ["tmux", "kill-session", "-t", record.tmux_session],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def deliver_attachments(
    record: SessionRecord,
    attachments: Sequence[Attachment],
    prompt: str | None = None,
) -> str:
    if not attachments:
        raise AgentError("no attachments to deliver")
    paths = " ".join(shlex.quote(str(item.container_path)) for item in attachments)
    message = " ".join(part for part in (paths, prompt or "") if part).strip()
    if record.agent == "codex" and record.agent_session_id:
        argv = ["codex", "queue", "--thread", record.agent_session_id]
        for attachment in attachments:
            if attachment.mime_type.startswith("image/"):
                argv.extend(["--image", str(attachment.container_path)])
        argv.extend(["--message", prompt or f"Inspect the attached files: {paths}"])
        result = exec_in_session(record, argv, tty=False, capture=True)
        if result.returncode == 0:
            return message
    if not tmux_running(record):
        return message
    subprocess.run(["tmux", "set-buffer", "--", message], check=True)
    subprocess.run(["tmux", "paste-buffer", "-t", record.tmux_session], check=True)
    return message
