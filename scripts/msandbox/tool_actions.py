"""Explicit, session-scoped tool actions invoked by the operator's menu."""

from __future__ import annotations

import shlex
from urllib.parse import urlsplit
from uuid import uuid4

from .docker_runtime import ensure_container, exec_in_session
from .models import SessionRecord
from .state import load_session, save_session, state_lock

BROWSER_START = """
import signal, time
from playwright.sync_api import sync_playwright
def finish(*_):
    raise SystemExit(0)
for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(sig, finish)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=9222'])
    try:
        while True: time.sleep(.5)
    finally:
        browser.close()
"""

CAPTURE = """
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto(sys.argv[1], wait_until='domcontentloaded', timeout=30000)
        target = Path(sys.argv[2])
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=False, timeout=15000)
    finally:
        browser.close()
print(sys.argv[2])
"""

BROWSER_READY = """
import json, subprocess, time, urllib.request
for attempt in range(40):
    if subprocess.run(['tmux', 'has-session', '-t', '=msandbox-browser'], capture_output=True).returncode:
        raise RuntimeError('Managed browser process exited')
    try:
        with urllib.request.urlopen('http://127.0.0.1:9222/json/version', timeout=.3) as response:
            assert json.load(response)['webSocketDebuggerUrl']
        break
    except OSError: time.sleep(.1)
else: raise RuntimeError('Managed browser did not become ready')
"""


def tool_action(record: SessionRecord, action: str, *, url: str = "") -> str:
    with state_lock(f"session-{record.id}", timeout_s=30):
        current = load_session(record.id)
        if current.phase in (
            "released",
            "orphaned",
            "submitting",
            "submitted_needs_release",
        ):
            raise RuntimeError("This session is not available for tool actions")
        if action == "browser-enable":
            # Recreating a workspace to change images interrupts every process.
            from .sessions import stop_session

            stop_session(current, _lock_held=True)
            current.playwright = True
            save_session(current)
            record.__dict__.update(current.__dict__)
            ensure_container(current)
            return "Browser image ready. Restart the harness when ready."
        if action.startswith("dev-") and not current.dev:
            raise RuntimeError(
                "This session has no published dev ports; create a Development session"
            )
        if action.startswith("browser-") and not current.playwright:
            raise RuntimeError("Enable browser support first")
        if action.endswith("-stop"):
            # Do not boot a stopped workspace just to stop a tool.
            from .inspection import inspect_session

            snapshot = inspect_session(current)
            if not snapshot.reliable:
                raise RuntimeError(
                    "Cannot verify workspace state; retry when Docker is available"
                )
            if not snapshot.container_id:
                return "Workspace is already stopped."
        else:
            ensure_container(current)
        if action == "dev-start":
            # Use the existing script without modifying its startup contract.
            # Its final attach has no TTY and returns, while its panes persist.
            argv = [
                "bash",
                "-c",
                "tmux has-session -t =matcha-dev-remote 2>/dev/null || bash ./scripts/dev-remote.sh",
            ]
        elif action == "dev-stop":
            argv = ["tmux", "kill-session", "-t", "=matcha-dev-remote"]
        elif action == "browser-start":
            command = "exec " + shlex.join(
                ["/workspace/server/venv/bin/python", "-c", BROWSER_START]
            )
            argv = [
                "bash",
                "-c",
                'tmux has-session -t =msandbox-browser 2>/dev/null || tmux new-session -d -s msandbox-browser "$1"',
                "msandbox",
                command,
            ]
        elif action == "browser-stop":
            argv = ["tmux", "kill-session", "-t", "=msandbox-browser"]
        elif action == "browser-capture":
            parsed = urlsplit(url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Enter an http(s) URL without embedded credentials")
            path = f"/workspace/.msandbox/outputs/screenshot-{uuid4().hex[:12]}.png"
            argv = ["/workspace/server/venv/bin/python", "-c", CAPTURE, url, path]
        else:
            raise ValueError("unknown tool action")
        result = exec_in_session(current, argv, tty=False, capture=True, timeout=90)
        if action == "dev-start":
            # dev-remote ends with attach; readiness is measured separately.
            check = exec_in_session(
                current,
                ["tmux", "has-session", "-t", "=matcha-dev-remote"],
                tty=False,
                capture=True,
                timeout=5,
            )
            if check.returncode == 0:
                return "dev-remote.sh panes started. Open Environment to verify service readiness."
        if result.returncode:
            raise RuntimeError(
                f"{action} failed (exit {result.returncode}); inspect the session shell"
            )
        if action == "browser-start":
            ready = exec_in_session(
                current,
                ["/workspace/server/venv/bin/python", "-c", BROWSER_READY],
                tty=False,
                capture=True,
                timeout=8,
            )
            if ready.returncode:
                raise RuntimeError(
                    "Managed browser failed to become ready; inspect browser processes"
                )
            return "Managed Chromium is ready at http://127.0.0.1:9222 inside this sandbox."
        if action == "browser-capture":
            return f"Saved {path}. Open Files & attachments to export it."
        return f"{action} complete. Refresh Environment to inspect running processes."
