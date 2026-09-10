"""Host-only AutoPR ownership protocol. Also runnable from the trusted archive.

No control file is mounted in a model container. A takeover stops the exact
supervised container before transferring its checkout. Hand-back exports through
a private trusted Git index; the normal AutoPR patch/publish guards still apply.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

PAUSED_EXIT = 75
MAX_PATCH = 5 * 1024 * 1024
MAX_NOTE = 16000
HOLD_STATES = {
    "running",
    "pausing",
    "manual",
    "preparing",
    "ready",
    "resuming",
    "blocked",
    "recovering",
}
EFFORTS = ("low", "medium", "high", "xhigh")
MODEL_CHOICES = ("gpt-5.6-sol", "gpt-5.6-luna", "gpt-6-astra", "gpt-5.5")


def root() -> Path:
    return Path(
        os.environ.get(
            "AUTOPR_CONTROL_STATE_DIR", Path.home() / ".local/state/matcha-autopr"
        )
    )


def run_dir(run_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("invalid AutoPR run ID")
    return root() / "runs" / run_id


def read_json(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("AutoPR state must be a regular file")
        payload = stream.read(131073)
    if len(payload) > 131072:
        raise ValueError("AutoPR state exceeds its size limit")
    return json.loads(payload)


def normalized_path(path: str | Path) -> Path:
    return Path(path).resolve()


def protect_workspace(
    workspace: str, repo: Path | None = None, project: str | None = None
):
    """Recover dead owners before reuse; never delete an unknown owner's files."""
    source = normalized_path(workspace)
    warnings = []
    matches = [
        run
        for run in list_runs(warnings)
        if normalized_path(run.workspace) == source and run.status in HOLD_STATES
    ]
    for run in matches:
        if supervisor_alive(run) or repo is None:
            raise ValueError(
                "This checkout has an active or interrupted owner. Recover it before replacing it."
            )
        recover(run.id, repo)
    # An unreadable host record cannot make the source safe to erase. Its
    # diagnostic marker is not authority to stop a different Compose project.
    marker = source / ".git/autopr-io/control-run.json"
    if not source.exists() or (not marker.exists() and not warnings):
        return
    try:
        owner = load(read_json(marker)["run_id"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        if (
            repo is None
            or not project
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", project)
        ):
            raise ValueError(
                "Unknown checkout owner; exact sandbox identity is required for preservation."
            )
        ids = (
            command(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                    "--filter",
                    "label=com.docker.compose.service=workspace",
                ]
            )
            .decode()
            .split()
        )
        if ids:
            command(["docker", "stop", *ids])
        destination = source.with_name(f"preserved-unknown-{uuid.uuid4().hex}")
        source.rename(destination)
        print(
            f"AutoPR: preserved unknown owner's checkout at {destination}",
            file=sys.stderr,
        )
    else:
        if owner.status in HOLD_STATES and normalized_path(owner.workspace) == source:
            raise ValueError("This checkout is still held; refusing replacement.")


def workflow_identity() -> str:
    return (
        os.environ.get("GITHUB_RUN_ID")
        or os.environ.get("AUTOPR_INVOCATION_ID")
        or "local"
    )


def atomic(path: Path, payload: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload.encode() if isinstance(payload, str) else payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def locked():
    root().mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(
        root() / "ownership.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


@contextmanager
def runtime_locked(run_id: str):
    """Serialize one run's terminals without blocking unrelated supervisors."""
    fd = os.open(
        run_dir(run_id) / "runtime.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(
                "Another action is operating on this run; retry when it finishes."
            ) from exc
        yield
    finally:
        os.close(fd)


@dataclass
class Run:
    id: str
    task_id: str
    project_id: str
    title: str
    repo: str
    workspace: str
    base_sha: str
    branch: str
    project: str
    model: str
    effort: str
    workflow_id: str = ""
    pr_number: int | None = None
    status: str = "running"
    updated_at: float = 0
    supervisor_pid: int = 0
    note: str = ""
    error: str = ""
    patch_sha256: str = ""
    resumed_by: str = ""
    manual_started: bool = False
    runtime_created: bool = False
    resources_cleaned: bool = False
    continuation_pid: int = 0


def load(run_id: str) -> Run:
    path = run_dir(run_id)
    if path.is_symlink():
        raise ValueError("unsafe AutoPR run directory")
    run = Run(**read_json(path / "run.json"))
    if run.id != run_id or not re.fullmatch(r"[0-9a-f]{40}", run.base_sha):
        raise ValueError("invalid AutoPR run metadata")
    uuid.UUID(run.task_id)
    uuid.UUID(run.project_id)
    for key in (
        "workspace",
        "repo",
        "status",
        "project",
        "title",
        "model",
        "effort",
        "workflow_id",
        "resumed_by",
        "error",
    ):
        if not isinstance(getattr(run, key), str):
            raise ValueError(f"invalid run {key}")
    if not isinstance(run.updated_at, (int, float)) or not math.isfinite(
        run.updated_at
    ):
        raise ValueError("invalid run timestamp")
    if not isinstance(run.supervisor_pid, int) or not isinstance(
        run.continuation_pid, int
    ):
        raise ValueError("invalid run process identity")
    return run


def save(run: Run):
    run.updated_at = time.time()
    atomic(
        run_dir(run.id) / "run.json", json.dumps(asdict(run), ensure_ascii=False) + "\n"
    )


def list_runs(warnings: list[str] | None = None) -> list[Run]:
    directory = root() / "runs"
    if not directory.exists():
        return []
    result = []
    for path in directory.iterdir():
        if path.name.startswith("."):
            continue
        try:
            result.append(load(path.name))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            warning = f"Unreadable AutoPR entry {path.name}: {type(exc).__name__}; checkout preservation guards remain active."
            if warnings is not None:
                warnings.append(warning)
            else:
                print(warning, file=sys.stderr)
    return sorted(result, key=lambda run: run.updated_at, reverse=True)


def held_task(task_id: str) -> Run | None:
    return next(
        (
            run
            for run in list_runs()
            if run.task_id == task_id and run.status in HOLD_STATES
        ),
        None,
    )


def request_takeover(run_id: str):
    with locked():
        run = load(run_id)
        if run.status == "pausing":
            return
        if run.status != "running":
            raise ValueError(
                "This run is no longer accepting a takeover; refresh its activity."
            )
        if not supervisor_alive(run):
            raise ValueError(
                "The run's supervisor stopped. Use Recover interrupted run."
            )
        run.status = "pausing"
        save(run)


def supervisor_alive(run: Run) -> bool:
    return process_alive(run.supervisor_pid)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def model_settings(model: str, effort: str):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}", model):
        raise ValueError(
            "Use a model ID containing only letters, numbers, dots, dashes, or underscores."
        )
    if effort not in EFFORTS:
        raise ValueError("Unsupported reasoning effort")


def update_manual(run_id: str, **changes) -> Run:
    """Call while holding runtime_locked; re-read at the ownership boundary."""
    with locked():
        run = load(run_id)
        if run.status != "manual":
            raise ValueError("This run is no longer under manual control.")
        for key, value in changes.items():
            if key not in {"manual_started", "runtime_created", "model", "effort"}:
                raise ValueError("Unsupported manual setting")
            setattr(run, key, value)
        save(run)
        return run


def configure(run_id: str, model: str, effort: str, repo: Path | None = None):
    model_settings(model, effort)
    with runtime_locked(run_id):
        run = update_manual(run_id)
        if repo is not None:
            stop_manual(run, repo)
        update_manual(run_id, model=model, effort=effort)


def command(argv, *, env=None, timeout=60):
    result = subprocess.run(
        argv, env=env, capture_output=True, timeout=timeout, check=False
    )
    if result.returncode:
        raise RuntimeError(
            result.stderr.decode(errors="replace")[-2000:] or "AutoPR command failed"
        )
    return result.stdout


def supervisor(
    card_path: Path, workspace: Path, repo: Path, project: str, argv: list[str]
) -> int:
    card = read_json(card_path)
    task_id, project_id = (
        str(uuid.UUID(card["task_id"])),
        str(uuid.UUID(card["project_id"])),
    )
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", project):
        raise ValueError("invalid sandbox project")
    base = command(["git", "-C", str(repo), "rev-parse", "HEAD"]).decode().strip()
    run = Run(
        uuid.uuid4().hex,
        task_id,
        project_id,
        str(card["title"])[:300],
        str(repo),
        str(workspace),
        base,
        f"bot/task-{task_id.replace('-', '')[:8]}",
        project,
        os.environ.get("AUTOPR_CODEX_MODEL", "gpt-5.6-sol"),
        os.environ.get("AUTOPR_CODEX_REASONING_EFFORT", "medium"),
        workflow_id=workflow_identity(),
        pr_number=card.get("pr_number"),
        supervisor_pid=os.getpid(),
    )
    model_settings(run.model, run.effort)
    with locked():
        held = held_task(task_id)
        if held and not (
            held.status == "resuming" and held.resumed_by == run.workflow_id
        ):
            raise RuntimeError("This task is held for operator work.")
        save(run)
    # This marker is diagnostic only; authoritative ownership stays outside
    # the container. It prevents recovery from adopting a later reused clone.
    atomic(
        workspace / ".git/autopr-io/control-run.json", json.dumps({"run_id": run.id})
    )
    log = run_dir(run.id) / "activity.log"
    proc = None
    try:
        with log.open("wb") as stream, log.open("rb") as reader:
            os.chmod(log, 0o600)
            proc = subprocess.Popen(
                argv, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
            )
            while True:
                chunk = reader.read(65536)
                if chunk:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                # State is atomically replaced by writers. Reading it needs
                # no global lock; acquire that only for the terminal CAS.
                run = load(run.id)
                stopping = run.status == "pausing"
                done = proc.poll()
                if not stopping and done is not None:
                    with locked():
                        run = load(run.id)
                        if run.status == "pausing":
                            continue
                        run.status = "model_done" if done == 0 else "failed"
                        run.error = "" if done == 0 else f"Model exited {done}"
                        save(run)
                        # Drain the final bytes before returning to the patch bridge.
                        sys.stdout.buffer.write(reader.read())
                        sys.stdout.buffer.flush()
                        return done
                if stopping:
                    # The model process lives in Docker; terminating the host exec
                    # client alone would leave a writer racing the checkout move.
                    command(
                        [os.environ["AUTOPR_MSANDBOX_BIN"], "stop"],
                        env=os.environ.copy(),
                        timeout=60,
                    )
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=15)
                    destination = run_dir(run.id) / "workspace"
                    transfer_checkout(workspace, destination)
                    with locked():
                        for prior in list_runs():
                            if (
                                prior.task_id == task_id
                                and prior.status == "resuming"
                                and prior.resumed_by == run.workflow_id
                            ):
                                prior.status = "superseded"
                                save(prior)
                        run = load(run.id)
                        run.workspace = str(destination)
                        run.project = f"matcha-autopr-manual-{run.id[:12]}"
                        run.status = "manual"
                        run.supervisor_pid = 0
                        save(run)
                    if os.environ.get("AUTOPR_PAUSE_RESULT_FILE"):
                        atomic(
                            Path(os.environ["AUTOPR_PAUSE_RESULT_FILE"]),
                            json.dumps({"run_id": run.id, "paused": True}),
                        )
                    print(
                        f"\nAutoPR paused. Checkout preserved for operator takeover ({run.id}).",
                        flush=True,
                    )
                    return PAUSED_EXIT
                if not chunk:
                    time.sleep(0.2)
    except BaseException as exc:
        with locked():
            run = load(run.id)
            run.status = "blocked"
            run.error = f"Supervisor interrupted: {type(exc).__name__}. Checkout preserved; stop its container before recovery."
            save(run)
        raise
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)


def manual_environment(
    run: Run, repo: Path, *, transferred=True, stopping=False
) -> dict[str, str]:
    """One unique sealed Compose project; no port or volume collision with sessions."""
    if transferred and Path(run.workspace) != run_dir(run.id) / "workspace":
        raise ValueError("AutoPR checkout has not been transferred yet")
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in (
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "MATCHA_BOT_PASSWORD",
            "SSH_KEY",
            "EC2_SSH_KEY",
            "AUTOPR_TEST_TENANT_EMAIL",
            "AUTOPR_TEST_TENANT_PASSWORD",
        )
    }
    auth = run_dir(run.id) / "auth.json"
    source = Path.home() / ".codex/auth.json"
    # Read this one file only, as the existing AutoPR bridge does.
    if stopping:
        # Compose only requires a readable path when stopping. Do not require
        # a valid/reachable host login to surrender an already running writer.
        auth = run_dir(run.id) / "stop-auth.json"
        atomic(auth, "{}")
    else:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Codex login exceeds size limit")
        atomic(auth, data)
    env.update(
        {
            "AUTOPR_SANDBOX_PROJECT_NAME": run.project,
            "AGENT_SANDBOX_PROJECT_NAME": run.project,
            "AGENT_SANDBOX_AUTOPR": "1",
            "SANDBOX_WORKSPACE_DIR": run.workspace,
            "SANDBOX_AWS_DIR": str(run_dir(run.id) / "empty-aws"),
            "SANDBOX_CODEX_AUTH_FILE": str(auth),
            "AGENT_SANDBOX_SKIP_HOST_SERVICES": "1",
            "SANDBOX_UID": str(os.getuid()),
            "SANDBOX_GID": str(os.getgid()),
        }
    )
    if transferred:
        for name in (
            "SERVER_VENV",
            "CLIENT_NODE_MODULES",
            "TELLUS_NODE_MODULES",
            "OCEANLAB_NODE_MODULES",
        ):
            env[f"SANDBOX_{name}_VOLUME"] = f"{run.project}_{name.lower()}"
    return env


def transfer_checkout(source: Path, destination: Path):
    """Publish a complete copy before removing the source across filesystems."""
    if destination.exists():
        raise ValueError(
            "Transfer destination already exists; refusing to overwrite it"
        )
    try:
        source.rename(destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        temporary = Path(tempfile.mkdtemp(prefix=".transfer-", dir=destination.parent))
        try:
            shutil.copytree(source, temporary / "workspace", symlinks=True)
            (temporary / "workspace").rename(destination)
            shutil.rmtree(source)
        finally:
            shutil.rmtree(temporary)


def recover(run_id: str, repo: Path):
    with runtime_locked(run_id):
        with locked():
            run = load(run_id)
            if run.status not in (
                "blocked",
                "running",
                "pausing",
                "recovering",
            ) or supervisor_alive(run):
                raise ValueError(
                    "Recovery requires an interrupted supervisor; a live run must acknowledge takeover."
                )
            if any(
                other.id != run.id
                and other.project == run.project
                and other.status in ("running", "pausing")
                and supervisor_alive(other)
                for other in list_runs()
            ):
                raise ValueError("Another live run owns this container.")
            source = normalized_path(run.workspace)
            destination = run_dir(run.id) / "workspace"
            run.status = "recovering"
            save(run)
        try:
            if source != destination and not destination.exists():
                if read_json(source / ".git/autopr-io/control-run.json") != {
                    "run_id": run.id
                }:
                    raise ValueError(
                        "This runtime belongs to another run. Its files were not touched."
                    )
            command(
                [str(repo / "scripts/agent-sandbox.sh"), "stop"],
                env=manual_environment(run, repo, transferred=False, stopping=True),
            )
            if source != destination and not destination.exists():
                # Free the shared runtime with a same-filesystem rename first.
                # Even a later copy failure cannot wedge unrelated tickets.
                preserved = source.with_name(f"preserved-{run.id}")
                if source != preserved:
                    source.rename(preserved)
                    source = preserved
                    with locked():
                        run = load(run_id)
                        run.workspace = str(source)
                        save(run)
                transfer_checkout(source, destination)
            with locked():
                run = load(run_id)
                run.workspace = str(destination)
                run.project = f"matcha-autopr-manual-{run.id[:12]}"
                run.status, run.error, run.supervisor_pid = (
                    "manual",
                    "Recovered interrupted run; no manual time limit.",
                    0,
                )
                save(run)
        except BaseException as exc:
            with locked():
                run = load(run_id)
                run.status, run.error = (
                    "blocked",
                    f"Recovery stopped: {exc}. Files preserved.",
                )
                save(run)
            raise


def tmux_name(run: Run) -> str:
    return f"autopr-manual-{run.id}"


def stop_manual(run: Run, repo: Path):
    env = manual_environment(run, repo, stopping=True)
    command([str(repo / "scripts/agent-sandbox.sh"), "stop"], env=env)
    # The container has stopped; only this run's host terminal may be removed.
    subprocess.run(
        ["tmux", "kill-session", "-t", "=" + tmux_name(run)],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["tmux", "kill-session", "-t", "=" + tmux_name(run) + "-shell"],
        capture_output=True,
        check=False,
    )


def export_patch(run: Run) -> bytes:
    """Never execute configuration or hooks from the model-writable .git."""
    directory = run_dir(run.id)
    git_dir = directory / "capture.git"
    git_env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    git_env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    if not git_dir.exists():
        command(["git", "init", "--bare", str(git_dir)], env=git_env)
    atomic(git_dir / "info/exclude", ".msandbox/\n")
    command(
        [
            "git",
            "--git-dir",
            str(git_dir),
            "fetch",
            "--no-tags",
            "--no-recurse-submodules",
            run.repo,
            run.base_sha,
        ],
        env=git_env,
    )
    git_env.update(
        {
            "GIT_DIR": str(git_dir),
            "GIT_WORK_TREE": run.workspace,
            "GIT_INDEX_FILE": str(directory / "capture.index"),
        }
    )
    command(["git", "read-tree", run.base_sha], env=git_env)
    command(
        [
            "git",
            "-C",
            run.workspace,
            "-c",
            "core.hooksPath=/dev/null",
            "add",
            "--all",
            "--",
            ".",
        ],
        env=git_env,
    )
    patch = command(
        [
            "git",
            "-C",
            run.workspace,
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "--full-index",
            "--no-renames",
            run.base_sha,
        ],
        env=git_env,
    )
    if len(patch) > MAX_PATCH:
        raise ValueError(
            "Handoff patch exceeds AutoPR's 5 MiB limit; checkout preserved."
        )
    return patch


def prepare_return(run_id: str, repo: Path, note: str):
    with runtime_locked(run_id):
        _prepare_return(run_id, repo, note)


def _prepare_return(run_id: str, repo: Path, note: str):
    if len(note.encode()) > MAX_NOTE:
        raise ValueError("Continuation note is too long")
    with locked():
        run = load(run_id)
        if run.status != "manual":
            raise ValueError("Only an operator-owned run can be handed back.")
        run.status = "preparing"
        save(run)
    try:
        stop_manual(run, repo)
        patch = export_patch(run)
        atomic(run_dir(run.id) / "handoff.patch", patch)
        atomic(run_dir(run.id) / "operator-note.txt", note)
        with locked():
            run = load(run_id)
            run.patch_sha256 = hashlib.sha256(patch).hexdigest()
            run.note = note
            run.status = "ready"
            save(run)
    except BaseException:
        with locked():
            run = load(run_id)
            run.status = "manual"
            save(run)
        raise


def continuation(task_id: str, workflow_id: str) -> Run | None:
    """Claim one immutable hand-back; live board claim is still required."""
    if not (root() / "runs").exists():
        return None
    with locked():
        run = held_task(task_id)
        if run is None:
            return None
        if run.status != "ready":
            raise ValueError("Task is held for an operator; automation cannot edit it.")
        patch = (run_dir(run.id) / "handoff.patch").read_bytes()
        if (
            len(patch) > MAX_PATCH
            or hashlib.sha256(patch).hexdigest() != run.patch_sha256
        ):
            raise ValueError(
                "Saved hand-back patch changed; refusing automatic continuation."
            )
        run.status, run.resumed_by = "resuming", workflow_id
        run.continuation_pid = int(os.environ.get("AUTOPR_CONTINUATION_PID", "0"))
        save(run)
        return run


def finish_return(
    task_id: str, workflow_id: str, success: bool, pr_number: int | None = None
):
    if not (root() / "runs").exists():
        return
    with locked():
        for item in list_runs():
            if (
                item.task_id == task_id
                and item.workflow_id == workflow_id
                and item.status == "model_done"
            ):
                item.status = "completed" if success else "needs_attention"
                if pr_number:
                    item.pr_number = pr_number
                item.error = (
                    ""
                    if success
                    else "No product PR publication was confirmed. View the workflow outcome."
                )
                save(item)
        run = held_task(task_id)
        if not run or run.status != "resuming" or run.resumed_by != workflow_id:
            return
        run.status = "returned" if success else "ready"
        if pr_number:
            run.pr_number = pr_number
        run.error = (
            ""
            if success
            else "No product PR publication was confirmed. Saved edits remain available for manual work or another hand-back."
        )
        save(run)
    if success:
        archive_checkout(run)
        # Taking over a continuation supersedes its previous immutable clone.
        # Retire those too once this task finishes, preserving their outputs.
        for prior in list_runs():
            if (
                prior.task_id == task_id
                and prior.status == "superseded"
                and Path(prior.workspace).exists()
            ):
                archive_checkout(prior)


def archive_checkout(run: Run):
    # Keep an exact recovery copy (including ignored/generated files and
    # local Git history), then remove this one managed checkout. Nothing
    # is checked out or merged in the user's primary repository.
    workspace = run_dir(run.id) / "workspace"
    if Path(run.workspace) != workspace or workspace.is_symlink():
        raise ValueError("Refusing cleanup of an unrecognized AutoPR checkout")
    archive = run_dir(run.id) / "checkout-recovery.tar.gz"
    temporary = archive.with_suffix(".tmp")
    try:
        if hashlib.sha256(export_patch(run)).hexdigest() != run.patch_sha256:
            raise OSError("files changed after hand-back; retained for manual recovery")
        with tarfile.open(temporary, "w:gz", dereference=False) as backup:
            backup.add(workspace, arcname="workspace")
        os.chmod(temporary, 0o600)
        os.replace(temporary, archive)
        cleanup_resources(run)
        shutil.rmtree(workspace)
        with locked():
            current = load(run.id)
            current.error = ""
            save(current)
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as exc:
        with locked():
            run = load(run.id)
            run.error = (
                f"AutoPR completed; checkout retained because cleanup failed: {exc}"
            )
            save(run)
    finally:
        temporary.unlink(missing_ok=True)


def cleanup_resources(run: Run):
    if run.resources_cleaned:
        return
    if run.project != f"matcha-autopr-manual-{run.id[:12]}":
        if not (run.runtime_created or run.manual_started):
            return
        raise ValueError("Refusing cleanup outside this run's exact managed namespace")
    # Old shell-only takeovers predate runtime_created. Their deterministic
    # namespace is still ours; down is harmless when it contains no resources.
    env = manual_environment(run, Path(run.repo), stopping=True)
    command(
        [
            "docker",
            "compose",
            "--project-name",
            run.project,
            "--file",
            str(Path(run.repo) / "docker-compose.sandbox.yml"),
            "--file",
            str(Path(run.repo) / "docker-compose.autopr-sandbox.yml"),
            "down",
            "--volumes",
        ],
        env=env,
        timeout=90,
    )
    with locked():
        current = load(run.id)
        current.resources_cleaned = True
        save(current)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("supervise")
    p.add_argument("--card", type=Path, required=True)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--project", required=True)
    p.add_argument("argv", nargs=argparse.REMAINDER)
    p = sub.add_parser("held")
    p.add_argument("task")
    sub.add_parser("held-tasks")
    p = sub.add_parser("continue")
    p.add_argument("task")
    p = sub.add_parser("finish")
    p.add_argument("task")
    p.add_argument("--success", action="store_true")
    p.add_argument("--published-pr", type=int)
    p = sub.add_parser("protect-workspace")
    p.add_argument("workspace")
    p.add_argument("--repo", type=Path)
    p.add_argument("--project")
    args = parser.parse_args()
    if args.action == "supervise":
        return supervisor(
            args.card, args.workspace, args.repo, args.project, args.argv[1:]
        )
    if args.action == "held":
        run = held_task(args.task)
        print("held" if run and run.status != "ready" else "available")
    elif args.action == "held-tasks":
        print(
            json.dumps(
                sorted(
                    {
                        run.task_id
                        for run in list_runs()
                        if run.status in HOLD_STATES - {"ready"}
                    }
                )
            )
        )
    elif args.action == "continue":
        run = continuation(args.task, workflow_identity())
        print(
            json.dumps(
                {
                    "patch": str(run_dir(run.id) / "handoff.patch"),
                    "note": str(run_dir(run.id) / "operator-note.txt"),
                    "model": run.model,
                    "effort": run.effort,
                }
                if run
                else {}
            )
        )
    elif args.action == "protect-workspace":
        protect_workspace(args.workspace, args.repo, args.project)
    else:
        if args.published_pr is not None and args.published_pr <= 0:
            raise ValueError("Invalid published PR number")
        finish_return(
            args.task, workflow_identity(), bool(args.published_pr), args.published_pr
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"AutoPR control: {error}", file=sys.stderr)
        sys.exit(1)
