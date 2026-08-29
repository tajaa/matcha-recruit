from __future__ import annotations

import fcntl
import os
import pty
import select
import shlex
import signal
import subprocess
import sys
import termios
import tty
from pathlib import Path
from typing import Callable, Sequence

from .attachments import (
    AttachmentError,
    import_files,
    import_files_to_inbox,
    parse_pasted_file_payload,
)
from .models import Attachment, SessionRecord


PASTE_START = b"\x1b[200~"
PASTE_END = b"\x1b[201~"
MAX_PENDING_PASTE_BYTES = 1024 * 1024
MAX_PENDING_HOST_PATH_BYTES = 4096
HOST_PATH_PREFIXES = (b"/Users/", b"/private/", b"/var/folders/", b"/tmp/")
PasteImporter = Callable[[Sequence[Path]], Sequence[Attachment]]
PasteErrorHandler = Callable[[Exception], None]
StreamRewriter = Callable[[bytes], tuple[bytes, bytes]]


def rewrite_bracketed_paste(record: SessionRecord, data: bytes) -> bytes:
    rewritten, pending = rewrite_paste_stream(record, data)
    return rewritten + pending


def _partial_marker_suffix(data: bytes) -> int:
    maximum = min(len(data), len(PASTE_START) - 1)
    for length in range(maximum, 0, -1):
        if data.endswith(PASTE_START[:length]):
            return length
    return 0


def rewrite_paste_stream(record: SessionRecord, data: bytes) -> tuple[bytes, bytes]:
    """Rewrite every complete paste and retain only an incomplete trailing frame."""
    return rewrite_paste_stream_with_importer(data, lambda paths: import_files(record, paths))


def rewrite_paste_stream_to_inbox(
    data: bytes,
    *,
    inbox: Path,
    container_dir: Path,
    lock_name: str,
    max_bytes: int,
    session_max_bytes: int,
    on_error: PasteErrorHandler | None = None,
) -> tuple[bytes, bytes]:
    """Rewrite pasted host files into a caller-provided mounted inbox."""
    return rewrite_paste_stream_with_importer(
        data,
        lambda paths: import_files_to_inbox(
            paths,
            inbox=inbox,
            container_dir=container_dir,
            lock_name=lock_name,
            max_bytes=max_bytes,
            session_max_bytes=session_max_bytes,
        ),
        on_error=on_error,
    )


def rewrite_paste_stream_with_importer(
    data: bytes,
    importer: PasteImporter,
    *,
    on_error: PasteErrorHandler | None = None,
) -> tuple[bytes, bytes]:
    """Rewrite bracketed pastes and macOS drag-inserted host file paths."""
    bracketed, pending = _rewrite_bracketed_paste_stream_with_importer(
        data,
        importer,
        on_error=on_error,
    )
    rewritten, plain_pending = _rewrite_plain_host_paths(
        bracketed,
        importer,
        on_error=on_error,
    )
    return rewritten, plain_pending + pending


def _rewrite_bracketed_paste_stream_with_importer(
    data: bytes,
    importer: PasteImporter,
    *,
    on_error: PasteErrorHandler | None = None,
) -> tuple[bytes, bytes]:
    output = bytearray()
    cursor = 0
    while cursor < len(data):
        start = data.find(PASTE_START, cursor)
        if start < 0:
            tail = data[cursor:]
            keep = _partial_marker_suffix(tail)
            output.extend(tail[:-keep] if keep else tail)
            return bytes(output), tail[-keep:] if keep else b""
        output.extend(data[cursor:start])
        end = data.find(PASTE_END, start + len(PASTE_START))
        if end < 0:
            pending = data[start:]
            if len(pending) > MAX_PENDING_PASTE_BYTES:
                output.extend(pending)
                return bytes(output), b""
            return bytes(output), pending
        frame_end = end + len(PASTE_END)
        payload = data[start + len(PASTE_START) : end]
        paths = parse_pasted_file_payload(payload)
        if paths is None:
            output.extend(data[start:frame_end])
        else:
            try:
                attachments = importer(paths)
            except (AttachmentError, OSError) as exc:
                if on_error is None:
                    raise
                on_error(exc)
                output.extend(data[start:frame_end])
            else:
                replacement = " ".join(
                    shlex.quote(str(item.container_path)) for item in attachments
                ).encode()
                output.extend(PASTE_START + replacement + PASTE_END)
        cursor = frame_end
    return bytes(output), b""


def _earliest_host_path_start(data: bytes, start: int = 0) -> int:
    matches = [index for prefix in HOST_PATH_PREFIXES if (index := data.find(prefix, start)) >= 0]
    return min(matches) if matches else -1


def _existing_host_file_prefix(data: bytes) -> tuple[int, Path] | None:
    """Return the longest leading host file path, escaped or literal."""
    for end in range(len(data), 0, -1):
        try:
            text = data[:end].decode("utf-8")
        except UnicodeDecodeError:
            continue
        candidates = [(text, end)]
        try:
            tokens = shlex.split(text)
        except ValueError:
            tokens = []
        if len(tokens) == 1 and tokens[0] != text:
            candidates.append((tokens[0], len(data[:end].rstrip(b" \t"))))
        for candidate, raw_end in candidates:
            path = Path(candidate)
            try:
                if path.is_file() and not path.is_symlink():
                    return raw_end, path
            except OSError:
                continue
    return None


def _rewrite_plain_host_paths(
    data: bytes,
    importer: PasteImporter,
    *,
    on_error: PasteErrorHandler | None = None,
) -> tuple[bytes, bytes]:
    """Rewrite host paths emitted as raw keystrokes by macOS file drags."""
    output = bytearray()
    cursor = 0
    while cursor < len(data):
        start = _earliest_host_path_start(data, cursor)
        bracket_start = data.find(PASTE_START, cursor)
        if bracket_start >= 0 and (start < 0 or bracket_start < start):
            bracket_end = data.find(PASTE_END, bracket_start + len(PASTE_START))
            if bracket_end < 0:
                output.extend(data[cursor:])
                return bytes(output), b""
            frame_end = bracket_end + len(PASTE_END)
            output.extend(data[cursor:frame_end])
            cursor = frame_end
            continue
        if start < 0:
            output.extend(data[cursor:])
            return bytes(output), b""
        output.extend(data[cursor:start])
        candidate = data[start:]
        match = _existing_host_file_prefix(candidate)
        if match is not None:
            end, path = match
            # Wait for one following byte so a path which is itself a prefix
            # of a longer dragged filename is not rewritten prematurely.
            if end == len(candidate):
                return bytes(output), candidate
            if candidate[end : end + 1] in b" \t\r\n":
                try:
                    attachments = importer([path])
                except (AttachmentError, OSError) as exc:
                    if on_error is None:
                        raise
                    on_error(exc)
                    output.extend(candidate[:end])
                else:
                    replacement = " ".join(
                        shlex.quote(str(item.container_path)) for item in attachments
                    ).encode()
                    output.extend(replacement)
                cursor = start + end
                continue
        if (
            b"\r" in candidate
            or b"\n" in candidate
            or len(candidate) > MAX_PENDING_HOST_PATH_BYTES
        ):
            output.extend(candidate)
            return bytes(output), b""
        return bytes(output), candidate
    return bytes(output), b""


def _sync_window_size(source_fd: int, target_fd: int) -> None:
    """Copy the real terminal dimensions onto the proxy PTY."""
    try:
        window_size = fcntl.ioctl(source_fd, termios.TIOCGWINSZ, bytes(8))
        fcntl.ioctl(target_fd, termios.TIOCSWINSZ, window_size)
    except OSError:
        pass


def attach_with_file_proxy(record: SessionRecord) -> int:
    """Attach tmux through a PTY and translate dragged host files safely."""
    return run_with_file_proxy(
        ["tmux", "attach-session", "-t", record.tmux_session],
        lambda data: rewrite_paste_stream(record, data),
    )


def run_with_file_proxy(argv: Sequence[str], rewriter: StreamRewriter) -> int:
    """Run an interactive command while translating complete host-file pastes."""
    if not argv:
        raise ValueError("file proxy requires a command")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return subprocess.run(list(argv), check=False).returncode
    child_pid, child_fd = pty.fork()
    if child_pid == 0:
        os.execvp(argv[0], list(argv))

    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    previous = termios.tcgetattr(stdin_fd)
    previous_sigwinch = signal.getsignal(signal.SIGWINCH)
    buffer = b""

    def handle_sigwinch(_signum: int, _frame: object) -> None:
        _sync_window_size(stdin_fd, child_fd)

    signal.signal(signal.SIGWINCH, handle_sigwinch)
    _sync_window_size(stdin_fd, child_fd)
    try:
        tty.setraw(stdin_fd)
        while True:
            readable, _, _ = select.select([stdin_fd, child_fd], [], [])
            if child_fd in readable:
                try:
                    output = os.read(child_fd, 65536)
                except OSError:
                    break
                if not output:
                    break
                os.write(stdout_fd, output)
            if stdin_fd in readable:
                incoming = os.read(stdin_fd, 65536)
                if not incoming:
                    if buffer:
                        os.write(child_fd, buffer)
                    break
                buffer += incoming
                outgoing, buffer = rewriter(buffer)
                if outgoing:
                    os.write(child_fd, outgoing)
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, previous)
        signal.signal(signal.SIGWINCH, previous_sigwinch)
        try:
            os.close(child_fd)
        except OSError:
            pass
    _, status = os.waitpid(child_pid, 0)
    return os.waitstatus_to_exitcode(status)
