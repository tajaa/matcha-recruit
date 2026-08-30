from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Sequence

from .docker_runtime import compose_command, compose_environment, exec_in_session
from .models import Attachment, SessionRecord


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
