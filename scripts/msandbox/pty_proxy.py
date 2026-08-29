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


def rewrite_bracketed_paste(record: SessionRecord, data: bytes) -> bytes:
    start = data.find(PASTE_START)
    end = data.find(PASTE_END, start + len(PASTE_START)) if start >= 0 else -1
    if start < 0 or end < 0:
        return data
    payload = data[start + len(PASTE_START) : end]
    paths = parse_pasted_file_payload(payload)
    if paths is None:
        return data
    attachments = import_files(record, paths)
    replacement = " ".join(str(item.container_path) for item in attachments).encode()
    return data[: start + len(PASTE_START)] + replacement + data[end:]


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
                    break
                buffer += incoming
                if PASTE_START in buffer and PASTE_END not in buffer:
                    continue
                os.write(child_fd, rewrite_bracketed_paste(record, buffer))
                buffer = b""
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, previous)
        try:
            os.close(child_fd)
        except OSError:
            pass
    _, status = os.waitpid(child_pid, 0)
    return os.waitstatus_to_exitcode(status)
