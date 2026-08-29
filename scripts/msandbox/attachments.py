from __future__ import annotations

import hashlib
import mimetypes
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from .docker_runtime import attachment_dir
from .models import Attachment, SessionRecord
from .state import state_lock


DEFAULT_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_SESSION_MAX_BYTES = 200 * 1024 * 1024


class AttachmentError(RuntimeError):
    pass


def _sanitize_name(name: str) -> str:
    safe = "".join(char if char.isalnum() or char in ". _-" else "_" for char in name)
    safe = safe.lstrip(".")[:160]
    return safe or "attachment"


def _existing_bytes(directory: Path) -> int:
    total = 0
    if directory.is_dir():
        for candidate in directory.iterdir():
            try:
                if candidate.is_file() and not candidate.is_symlink():
                    total += candidate.stat().st_size
            except OSError:
                continue
    return total


def import_files(
    session: SessionRecord,
    sources: Sequence[Path],
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    session_max_bytes: int = DEFAULT_SESSION_MAX_BYTES,
) -> list[Attachment]:
    """Copy bounded regular files into the session inbox without following links."""
    if not sources:
        raise AttachmentError("at least one attachment is required")
    inbox = attachment_dir(session)
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    imported: list[Attachment] = []
    with state_lock(f"attachments-{session.id}"):
        current_bytes = _existing_bytes(inbox)
        for source in sources:
            source = source.expanduser()
            try:
                before = source.lstat()
            except OSError as exc:
                raise AttachmentError(f"attachment is not readable: {source}: {exc}") from exc
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
                raise AttachmentError(f"attachment is not a regular non-symlink file: {source}")
            if before.st_size > max_bytes:
                raise AttachmentError(f"attachment exceeds {max_bytes} bytes: {source}")
            digest = hashlib.sha256()
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(source, flags)
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise AttachmentError(f"attachment changed while importing: {source}")
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                after = os.fstat(fd)
                if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
                    raise AttachmentError(f"attachment changed while importing: {source}")
                full_digest = digest.hexdigest()
                short_digest = full_digest[:12]
                safe_name = _sanitize_name(source.name)
                destination = inbox / f"{full_digest}-{safe_name}"
                already_imported = destination.exists()
                if destination.is_symlink():
                    raise AttachmentError(f"unsafe attachment destination: {destination}")
                if already_imported:
                    existing_digest = hashlib.sha256()
                    existing_fd = os.open(destination, flags)
                    try:
                        existing_stat = os.fstat(existing_fd)
                        if not stat.S_ISREG(existing_stat.st_mode):
                            raise AttachmentError(
                                f"attachment destination is not a regular file: {destination}"
                            )
                        while chunk := os.read(existing_fd, 1024 * 1024):
                            existing_digest.update(chunk)
                    finally:
                        os.close(existing_fd)
                    if (
                        existing_stat.st_size != before.st_size
                        or existing_digest.hexdigest() != full_digest
                    ):
                        raise AttachmentError(
                            f"attachment destination failed content verification: {destination}"
                        )
                if not already_imported:
                    if current_bytes + before.st_size > session_max_bytes:
                        raise AttachmentError(
                            f"session attachment limit exceeds {session_max_bytes} bytes"
                        )
                    os.lseek(fd, 0, os.SEEK_SET)
                    temporary_fd, temporary_name = tempfile.mkstemp(prefix=".attachment.", dir=inbox)
                    try:
                        copied_digest = hashlib.sha256()
                        with os.fdopen(temporary_fd, "wb") as output:
                            while True:
                                chunk = os.read(fd, 1024 * 1024)
                                if not chunk:
                                    break
                                copied_digest.update(chunk)
                                output.write(chunk)
                            output.flush()
                            os.fsync(output.fileno())
                        copied_source_stat = os.fstat(fd)
                        if (
                            copied_source_stat.st_size != before.st_size
                            or copied_source_stat.st_mtime_ns != before.st_mtime_ns
                            or copied_digest.hexdigest() != full_digest
                        ):
                            raise AttachmentError(f"attachment changed while importing: {source}")
                        os.chmod(temporary_name, 0o600)
                        os.replace(temporary_name, destination)
                    finally:
                        Path(temporary_name).unlink(missing_ok=True)
            finally:
                os.close(fd)

            size = destination.stat().st_size
            if not already_imported:
                current_bytes += size
            imported.append(
                Attachment(
                    id=short_digest,
                    original_name=source.name,
                    mime_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                    sha256=full_digest,
                    size=size,
                    host_path=destination,
                    container_path=Path("/attachments") / destination.name,
                )
            )
    return imported


def _clipboard_file_paths() -> list[Path]:
    script = r'''
try
    set clipboardItems to the clipboard as alias list
on error
    try
        set clipboardItems to {the clipboard as alias}
    on error
        return ""
    end try
end try
set output to ""
repeat with clipboardItem in clipboardItems
    set output to output & POSIX path of clipboardItem & linefeed
end repeat
return output
'''
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, check=False)
    if result.returncode:
        return []
    return [Path(line) for line in result.stdout.splitlines() if line]


def import_clipboard(session: SessionRecord) -> list[Attachment]:
    """Import Finder aliases first, then fall back to PNG clipboard pixels."""
    paths = _clipboard_file_paths()
    if paths:
        return import_files(session, paths)
    temporary_dir = Path(tempfile.mkdtemp(prefix="matcha-msandbox-clipboard."))
    temporary_image = temporary_dir / "clipboard.png"
    try:
        script = r'''
on run argv
    try
        set imageData to the clipboard as «class PNGf»
    on error
        return "NO_IMAGE"
    end try
    set destinationFile to open for access POSIX file (item 1 of argv) with write permission
    try
        set eof destinationFile to 0
        write imageData to destinationFile
        close access destinationFile
    on error errorMessage
        try
            close access destinationFile
        end try
        error errorMessage
    end try
    return "OK"
end run
'''
        result = subprocess.run(
            ["osascript", "-e", script, str(temporary_image)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode or "OK" not in result.stdout or not temporary_image.is_file():
            raise AttachmentError("clipboard has no Finder file or PNG image")
        return import_files(session, [temporary_image])
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def parse_pasted_file_payload(payload: bytes) -> list[Path] | None:
    """Recognize a complete bracketed paste only when every token is a host file."""
    try:
        text = payload.decode("utf-8")
        tokens = shlex.split(text.strip())
    except (UnicodeDecodeError, ValueError):
        return None
    if not tokens:
        return None
    paths = [Path(token).expanduser() for token in tokens]
    return paths if all(path.is_file() and not path.is_symlink() for path in paths) else None
