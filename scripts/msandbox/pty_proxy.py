from __future__ import annotations

import os
import pty
import select
import signal
import subprocess
import sys
import termios
import tty

from .attachments import import_files, parse_pasted_file_payload
from .models import SessionRecord


PASTE_START = b"\x1b[200~"
PASTE_END = b"\x1b[201~"
MAX_PENDING_PASTE_BYTES = 1024 * 1024


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
            attachments = import_files(record, paths)
            replacement = " ".join(str(item.container_path) for item in attachments).encode()
            output.extend(PASTE_START + replacement + PASTE_END)
        cursor = frame_end
    return bytes(output), b""


def attach_with_file_proxy(record: SessionRecord) -> int:
    """Attach tmux through a PTY and translate dragged host files safely."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return subprocess.run(["tmux", "attach-session", "-t", record.tmux_session], check=False).returncode
    child_pid, child_fd = pty.fork()
    if child_pid == 0:
        os.execvp("tmux", ["tmux", "attach-session", "-t", record.tmux_session])

    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    previous = termios.tcgetattr(stdin_fd)
    buffer = b""
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
                outgoing, buffer = rewrite_paste_stream(record, buffer)
                if outgoing:
                    os.write(child_fd, outgoing)
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, previous)
        try:
            os.close(child_fd)
        except OSError:
            pass
    _, status = os.waitpid(child_pid, 0)
    return os.waitstatus_to_exitcode(status)
