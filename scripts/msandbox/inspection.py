"""Bounded, read-only observations; inspecting a session never starts it."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from .models import SessionRecord, utc_now
from .terminal_ui import plain


@dataclass(frozen=True)
class Snapshot:
    checked_at: str
    container_id: str | None
    lines: tuple[str, ...]
    reliable: bool = True


def run(argv: list[str], timeout: int = 8) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, text=True, capture_output=True, check=False, timeout=timeout
    )


# Probe from the actual workspace network namespace. Never emit environment
# values, response bodies, process argv, credentials, or SSH destinations.
PROBE = r"""
import json, os, socket, subprocess
from urllib.parse import urlsplit
def tcp(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=.4): return True
    except (OSError, ValueError): return False
def endpoint(label, raw):
    try:
        u = urlsplit(raw)
        default = {'https': 443, 'postgresql': 5432, 'postgres': 5432, 'redis': 6379}.get(u.scheme, 80)
        return [label, tcp(u.hostname, u.port or default)]
    except (ValueError, TypeError): return [label, False]
rows = []
for label, key, default in [('Host backend', 'HOST_DEV_BACKEND_URL', 'http://host.docker.internal:8001'), ('Host frontend', 'HOST_DEV_FRONTEND_URL', 'http://host.docker.internal:5174')]:
    rows.append(endpoint(label, os.environ.get(key, default)))
for label, key in [('Development database', 'DATABASE_URL'), ('Development Redis', 'REDIS_URL')]:
    rows.append(endpoint(label, os.environ.get(key, '')))
for label, key, port in [('Session backend', 'BACKEND_PORT', '8001'), ('Session frontend', 'FRONTEND_PORT', '5174'), ('Tell-Us', 'TELLUS_PORT', '5191'), ('Oceanlab', 'OCEANLAB_PORT', '5201')]:
    rows.append([label, tcp('127.0.0.1', os.environ.get(key, port))])
try:
    dev = subprocess.run(['tmux','has-session','-t','=matcha-dev-remote'], capture_output=True, timeout=2).returncode == 0
except (OSError, subprocess.TimeoutExpired): dev = False
print(json.dumps({'connections': rows, 'dev_remote': dev}))
"""


def inspect_session(record: SessionRecord) -> Snapshot:
    lines: list[str] = []
    container_id = None
    try:
        containers = run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={record.compose_project}",
                "--format",
                "{{json .}}",
            ]
        )
        if containers.returncode:
            return Snapshot(
                utc_now(), None, ("Docker unavailable; live state is unknown.",), False
            )
        for line in containers.stdout.splitlines()[:30]:
            item = json.loads(line)
            name = item.get("Names", "container")
            lines.append(
                f"{name}: {item.get('State', 'unknown')} · {item.get('Status', '')}"
            )
            if "workspace" in name and item.get("State") == "running":
                container_id = item["ID"]
        if not lines:
            lines.append("No session containers exist.")
        panes = run(
            [
                "tmux",
                "list-panes",
                "-t",
                f"={record.tmux_session}",
                "-F",
                "#{pane_dead} #{pane_current_command}",
            ]
        )
        lines += [
            f"Harness terminal: {'exited' if row.startswith('1 ') else 'running'}"
            for row in panes.stdout.splitlines()[:5]
        ]
        if container_id:
            probe = run(
                [
                    "docker",
                    "exec",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    container_id,
                    "/workspace/server/venv/bin/python",
                    "-c",
                    PROBE,
                ],
                timeout=12,
            )
            if probe.returncode == 0:
                measured = json.loads(probe.stdout)
                lines.append(
                    "dev-remote.sh: "
                    + (
                        "running inside this sandbox"
                        if measured["dev_remote"]
                        else "not running inside this sandbox"
                    )
                )
                lines.extend(
                    f"{name}: {'TCP reachable' if ok else 'unreachable'}"
                    for name, ok in measured["connections"]
                )
            else:
                lines.append("Connection probes unavailable; reachability unknown.")
            processes = run(
                ["docker", "top", container_id, "-eo", "pid,ppid,etime,comm"]
            )
            if processes.returncode == 0:
                rows = processes.stdout.splitlines()
                ssh = any(
                    row.split()[-1] in ("ssh", "autossh", "sshd")
                    for row in rows[1:]
                    if row.split()
                )
                lines.append(
                    "SSH: "
                    + (
                        "process observed; tunnel health unverified"
                        if ssh
                        else "no SSH process observed in this sandbox"
                    )
                )
                lines += [
                    "",
                    "Processes (PID / parent / elapsed / executable)",
                    *rows[:81],
                ]
            else:
                lines.append("Process inventory unavailable.")
        else:
            lines.append(
                "Workspace stopped; in-container connections and processes are not measured."
            )
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        lines.append("Some probes unavailable or timed out; refresh to retry.")
        return Snapshot(
            utc_now(), container_id, tuple(plain(line) for line in lines), False
        )
    return Snapshot(utc_now(), container_id, tuple(plain(line) for line in lines))
