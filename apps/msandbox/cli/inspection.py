"""Bounded, read-only observations; inspecting a session never starts it."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from .models import SessionRecord, utc_now
from .terminal_ui import plain


@dataclass(frozen=True)
class ContainerObservation:
    name: str
    state: str
    status: str
    id: str | None


@dataclass(frozen=True)
class HarnessObservation:
    state: str
    command: str


@dataclass(frozen=True)
class ConnectionObservation:
    name: str
    reachable: bool


@dataclass(frozen=True)
class ProcessObservation:
    pid: str
    parent_pid: str
    elapsed: str
    executable: str


@dataclass(frozen=True)
class Snapshot:
    checked_at: str
    container_id: str | None
    lines: tuple[str, ...]
    reliable: bool = True
    containers: tuple[ContainerObservation, ...] = ()
    harness_terminals: tuple[HarnessObservation, ...] = ()
    dev_remote_running: bool | None = None
    connections: tuple[ConnectionObservation, ...] = ()
    ssh_process_observed: bool | None = None
    processes: tuple[ProcessObservation, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Stable machine-readable contract; human prose stays out of JSON."""
        return {
            "schema_version": 1,
            "checked_at": self.checked_at,
            "reliable": self.reliable,
            "container_id": self.container_id,
            "containers": [vars(item) for item in self.containers],
            "harness_terminals": [vars(item) for item in self.harness_terminals],
            "dev_remote_running": self.dev_remote_running,
            "connections": [vars(item) for item in self.connections],
            "ssh_process_observed": self.ssh_process_observed,
            "processes": [vars(item) for item in self.processes],
            "errors": list(self.errors),
        }


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
        if u.scheme not in ('http', 'https', 'postgresql', 'postgres', 'redis') or not u.hostname:
            return [label, False]
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
    containers_seen: list[ContainerObservation] = []
    harnesses: list[HarnessObservation] = []
    connections: list[ConnectionObservation] = []
    processes_seen: list[ProcessObservation] = []
    dev_remote_running = None
    ssh_process_observed = None
    errors: list[str] = []
    reliable = True

    def result() -> Snapshot:
        return Snapshot(
            utc_now(),
            container_id,
            tuple(plain(line) for line in lines),
            reliable,
            tuple(containers_seen),
            tuple(harnesses),
            dev_remote_running,
            tuple(connections),
            ssh_process_observed,
            tuple(processes_seen),
            tuple(errors),
        )

    try:
        containers = run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={record.compose_project}",
                "--filter",
                "label=com.docker.compose.service=workspace",
                "--format",
                "{{json .}}",
            ]
        )
        if containers.returncode:
            lines.append("Docker unavailable; live state is unknown.")
            errors.append("docker_unavailable")
            reliable = False
            return result()
        for line in containers.stdout.splitlines()[:30]:
            item = json.loads(line)
            name = item.get("Names", "container")
            state = item.get("State", "unknown")
            status = item.get("Status", "")
            observed_id = item.get("ID")
            containers_seen.append(
                ContainerObservation(name, state, status, observed_id)
            )
            lines.append(
                f"{name}: {state} · {status}"
            )
            if state == "running":
                container_id = observed_id
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
        for row in panes.stdout.splitlines()[:5]:
            dead, _, command = row.partition(" ")
            state = "exited" if dead == "1" else "running"
            harnesses.append(HarnessObservation(state, command))
            lines.append(f"Harness terminal: {state}")
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
                dev_remote_running = bool(measured["dev_remote"])
                lines.append(
                    "dev-remote.sh: "
                    + (
                        "running inside this sandbox"
                        if dev_remote_running
                        else "not running inside this sandbox"
                    )
                )
                for name, reachable in measured["connections"]:
                    observation = ConnectionObservation(name, bool(reachable))
                    connections.append(observation)
                    lines.append(
                        f"{name}: {'TCP reachable' if observation.reachable else 'unreachable'}"
                    )
            else:
                lines.append("Connection probes unavailable; reachability unknown.")
                errors.append("connection_probe_unavailable")
                reliable = False
            processes = run(
                ["docker", "top", container_id, "-eo", "pid,ppid,etime,comm"]
            )
            if processes.returncode == 0:
                rows = processes.stdout.splitlines()
                for row in rows[1:81]:
                    fields = row.split(maxsplit=3)
                    if len(fields) == 4:
                        processes_seen.append(ProcessObservation(*fields))
                ssh_process_observed = any(
                    item.executable in ("ssh", "autossh", "sshd")
                    for item in processes_seen
                )
                lines.append(
                    "SSH: "
                    + (
                        "process observed; tunnel health unverified"
                        if ssh_process_observed
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
                errors.append("process_inventory_unavailable")
                reliable = False
        else:
            lines.append(
                "Workspace stopped; in-container connections and processes are not measured."
            )
    except (
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        subprocess.TimeoutExpired,
    ):
        lines.append("Some probes unavailable or timed out; refresh to retry.")
        errors.append("inspection_failed")
        reliable = False
        return result()
    return result()
