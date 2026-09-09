"""Browse/export bounded regular sandbox files, never follow agent-created links."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .attachments import DEFAULT_MAX_BYTES, import_files_to_inbox
from .models import SessionRecord
from .state import data_root


@dataclass(frozen=True)
class SandboxFile:
    root: Path
    relative: Path
    container_path: str
    size: int


def list_files(record: SessionRecord) -> list[SandboxFile]:
    result = []
    roots = (
        (data_root().resolve() / "attachments" / record.id, "/attachments"),
        (
            record.worktree.resolve() / ".msandbox/outputs",
            "/workspace/.msandbox/outputs",
        ),
    )
    for root, mounted in roots:
        if root.is_symlink() or not root.is_dir():
            continue
        # Refuse symlink ancestors too. Exports repeat the checks with dirfds.
        if any(p.is_symlink() for p in (root, *root.parents)):
            continue
        visited = 0
        for directory, dirs, names in os.walk(root, followlinks=False):
            visited += 1
            dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
            for name in sorted(names):
                path = Path(directory) / name
                try:
                    metadata = path.lstat()
                except OSError:
                    continue
                if stat.S_ISREG(metadata.st_mode):
                    relative = path.relative_to(root)
                    result.append(
                        SandboxFile(
                            root,
                            relative,
                            f"{mounted}/{relative.as_posix()}",
                            metadata.st_size,
                        )
                    )
                if len(result) >= 200:
                    return result
            if visited >= 500:
                break
    return result


def read_file(item: SandboxFile, limit: int) -> bytes:
    path = item.root.absolute() / item.relative
    if ".." in path.parts:
        raise ValueError("unsafe file path")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        source = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
        )
        try:
            before = os.fstat(source)
            if not stat.S_ISREG(before.st_mode) or before.st_size > DEFAULT_MAX_BYTES:
                raise ValueError(
                    "Only regular files up to 50 MiB can be opened/exported"
                )
            with os.fdopen(source, "rb", closefd=False) as stream:
                payload = stream.read(limit)
            after = os.fstat(source)
            if (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError(
                    "File changed while reading; retry after its writer finishes"
                )
            return payload
        finally:
            os.close(source)
    finally:
        os.close(fd)


def export_file(record: SessionRecord, item: SandboxFile) -> Path:
    payload = read_file(item, DEFAULT_MAX_BYTES + 1)
    with tempfile.TemporaryDirectory(prefix="msandbox-export-") as temporary:
        source = Path(temporary) / item.relative.name
        source.write_bytes(payload)
        exported = import_files_to_inbox(
            [source],
            inbox=data_root() / "exports" / record.id,
            container_dir=Path("/exports"),
            lock_name=f"exports-{record.id}",
            session_max_bytes=1024 * 1024 * 1024,
        )
    return exported[0].host_path
