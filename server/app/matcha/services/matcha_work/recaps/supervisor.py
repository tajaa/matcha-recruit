"""Linux media-only process supervision, including threaded S3 and browser children.

The single-slot worker becomes a child subreaper before starting a job. Orphaned
Chromium process groups are consequently still its children. The supervisor
owns no unrelated children and never scans/kills arbitrary host processes.
"""
import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import UUID


def children(pid):
    try:
        return [int(value) for value in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
    except FileNotFoundError:
        return []


def stop_owned_children(parent):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        descendants = []
        pending = children(parent)
        if not pending:
            return
        while pending:
            pid = pending.pop()
            descendants.append(pid)
            pending.extend(children(pid))
        for pid in descendants:
            try:
                # A pidfd pins identity even if a process exits while cleanup
                # runs. Only descendants of this dedicated subreaper qualify.
                fd = os.pidfd_open(pid)
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)
            except ProcessLookupError:
                pass
        while True:
            try:
                if os.waitpid(-1, os.WNOHANG)[0] == 0:
                    break
            except ChildProcessError:
                break
        time.sleep(0.02)
    if children(parent):
        # Fail the worker container rather than start another job alongside
        # survivors. Container restart clears its PID namespace and scratch.
        os._exit(70)


def run(kind: str, identifier, *, seconds: int):
    if sys.platform != "linux":
        raise RuntimeError("media supervisor requires the isolated Linux worker")
    if kind not in ("render", "cleanup"):
        raise ValueError("invalid media operation")
    UUID(str(identifier))
    # PR_SET_CHILD_SUBREAPER, available on the Linux production container host.
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise RuntimeError("media child subreaper unavailable")
    # The supervisor, rather than the killable child, owns all job scratch.
    # Python and Playwright/Chromium inherit TMPDIR in their fresh processes.
    with tempfile.TemporaryDirectory(prefix="espresso-recap-job-") as scratch:
        process = subprocess.Popen([sys.executable, "-m", "app.matcha.services.matcha_work.recaps.media_job", kind, str(identifier)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, env={**os.environ, "TMPDIR": scratch})
        try:
            result = process.wait(timeout=seconds)
            if result:
                raise RuntimeError("media child failed")
        finally:
            stop_owned_children(os.getpid())
