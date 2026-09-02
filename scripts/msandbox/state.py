from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import SessionRecord, utc_now


SCHEMA_VERSION = 1
ARTIFACT_LIFECYCLE_LOCK = "artifact-lifecycle"


class StateError(RuntimeError):
    pass


def state_root() -> Path:
    return Path(
        os.environ.get(
            "MSANDBOX_STATE_DIR",
            Path.home() / ".local/state/matcha-msandbox",
        )
    ).expanduser()


def data_root() -> Path:
    return Path(
        os.environ.get(
            "MSANDBOX_DATA_DIR",
            Path.home() / ".local/share/matcha-msandbox",
        )
    ).expanduser()


def config_root() -> Path:
    return Path(
        os.environ.get(
            "MSANDBOX_CONFIG_DIR",
            Path.home() / ".config/matcha-msandbox",
        )
    ).expanduser()


def ensure_roots() -> None:
    for directory in (
        state_root(),
        state_root() / "sessions",
        state_root() / "locks",
        data_root(),
        data_root() / "worktrees",
        data_root() / "attachments",
        data_root() / "homes",
        data_root() / "releases",
        data_root() / "build-contexts",
        data_root() / "git-sessions",
        data_root() / "xcode-derived-data",
        config_root(),
    ):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)


def session_dir(session_id: str) -> Path:
    return state_root() / "sessions" / session_id


def session_file(session_id: str) -> Path:
    return session_dir(session_id) / "session.json"


def save_session(record: SessionRecord) -> None:
    """Validate and atomically replace a session record."""
    if record.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported session schema: {record.schema_version}")
    record.updated_at = utc_now()
    target_dir = session_dir(record.id)
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=".session.", dir=target_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, session_file(record.id))
    finally:
        temporary.unlink(missing_ok=True)


def list_sessions(*, include_released: bool = False, strict: bool = False) -> list[SessionRecord]:
    ensure_roots()
    records: list[SessionRecord] = []
    sessions_root = state_root() / "sessions"
    try:
        entries = sorted(sessions_root.iterdir())
    except OSError as exc:
        if strict:
            raise StateError(f"cannot enumerate session records in {sessions_root}: {exc}") from exc
        return records
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            if strict:
                raise StateError(f"unsafe session state entry: {entry}")
            continue
        path = entry / "session.json"
        if not path.is_file():
            if strict:
                raise StateError(f"session record is missing: {path}")
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            record = SessionRecord.from_dict(raw)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            if strict:
                raise StateError(f"invalid session record {path}: {exc}") from exc
            continue
        if strict and record.schema_version != SCHEMA_VERSION:
            raise StateError(
                f"unsupported session schema in {path}: {record.schema_version}"
            )
        if strict and record.id != entry.name:
            raise StateError(
                f"session id {record.id!r} does not match state directory {entry.name!r}"
            )
        if include_released or record.phase != "released":
            records.append(record)
    return sorted(records, key=lambda item: item.created_at)


def load_session(session_id_or_name: str) -> SessionRecord:
    """Load exactly one session by ID or unique human-readable name."""
    direct = session_file(session_id_or_name)
    if direct.is_file():
        return SessionRecord.from_dict(json.loads(direct.read_text(encoding="utf-8")))
    matches = [item for item in list_sessions(include_released=True) if item.name == session_id_or_name]
    if not matches:
        raise KeyError(f"unknown msandbox session: {session_id_or_name}")
    if len(matches) > 1:
        active = [item for item in matches if item.phase != "released"]
        if len(active) == 1:
            return active[0]
        raise KeyError(f"ambiguous msandbox session name: {session_id_or_name}")
    return matches[0]


def delete_session_state(session_id: str) -> None:
    directory = session_dir(session_id)
    if directory.is_dir():
        shutil.rmtree(directory)


@contextmanager
def state_lock(scope: str, timeout_s: float = 10.0) -> Iterator[None]:
    """Serialize host mutations with a kernel-released advisory lock."""
    ensure_roots()
    safe_scope = "".join(char if char.isalnum() or char in "._-" else "_" for char in scope)
    lock_path = state_root() / "locks" / f"{safe_scope}.lock"
    deadline = time.monotonic() + timeout_s
    with lock_path.open("a+", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for msandbox lock: {scope}")
            time.sleep(0.1)
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "created_at": utc_now()}))
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
