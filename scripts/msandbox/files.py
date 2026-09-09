"""Browse/export bounded regular sandbox files, never follow agent-created links."""

from __future__ import annotations

import mimetypes
import os
import stat
import unicodedata
from contextlib import contextmanager
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


def _safe_name(value: str) -> bool:
    return not any(unicodedata.category(char).startswith("C") for char in value)


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
            dirs[:] = sorted(
                d
                for d in dirs
                if _safe_name(d) and not (Path(directory) / d).is_symlink()
            )
            for name in sorted(names):
                if not _safe_name(name):
                    continue
                path = Path(directory) / name
                try:
                    metadata = path.lstat()
                except OSError:
                    continue
                if stat.S_ISREG(metadata.st_mode):
                    relative = path.relative_to(root)
                    if not _safe_name(relative.as_posix()):
                        continue
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


@contextmanager
def open_file(item: SandboxFile):
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
            yield source
            after = os.fstat(source)
            if (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError(
                    "File changed while reading; retry after its writer finishes"
                )
        finally:
            os.close(source)
    finally:
        os.close(fd)


def read_file(item: SandboxFile, limit: int) -> bytes:
    with open_file(item) as source, os.fdopen(source, "rb", closefd=False) as stream:
        return stream.read(limit)


def text_preview(item: SandboxFile, payload: bytes) -> str | None:
    mime = mimetypes.guess_type(item.relative.name)[0]
    if mime and not (mime.startswith("text/") or mime in ("application/json", "application/xml", "application/javascript")):
        return None
    if payload.startswith((b"%PDF-", b"PK\x03\x04", b"\x89PNG", b"\x1f\x8b", b"GIF8", b"\xff\xd8")):
        return None
    try:
        # A bounded read may end within a valid UTF-8 character.
        import codecs

        text = codecs.getincrementaldecoder("utf-8")().decode(payload, final=len(payload) >= item.size)
    except UnicodeDecodeError:
        return None
    if any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in text):
        return None
    return text


def export_file(record: SessionRecord, item: SandboxFile) -> Path:
    with open_file(item) as source:
        exported = import_files_to_inbox(
            [item.relative],
            inbox=data_root() / "exports" / record.id,
            container_dir=Path("/exports"),
            lock_name=f"exports-{record.id}",
            session_max_bytes=1024 * 1024 * 1024,
            source_fd=source,
        )
    return exported[0].host_path
