"""Optional Docker smoke: one disposable browser container, no credentials/data."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import uuid

from scripts.msandbox.tool_actions import BROWSER_START, CAPTURE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    name = f"msandbox-manager-smoke-{uuid.uuid4().hex[:12]}"

    def run(*argv):
        result = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=60, check=False
        )
        if result.returncode:
            raise RuntimeError(result.stderr[-3000:])
        return result.stdout.strip()

    def execute(*argv):
        return run("docker", "exec", name, *argv)

    python = "/opt/bootstrap/server-venv/bin/python"
    try:
        run(
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--network=none",
            "--tmpfs",
            "/tmp:rw,exec,nosuid,size=256m,mode=1777",
            "--tmpfs",
            "/workspace:rw,nosuid,size=32m,mode=1777",
            "--entrypoint",
            "sleep",
            args.image,
            "180",
        )
        execute(
            "tmux",
            "new-session",
            "-d",
            "-s",
            "msandbox-browser",
            "exec " + shlex.join([python, "-c", BROWSER_START]),
        )
        ready = """
import json, time, urllib.request
for attempt in range(40):
    try:
        with urllib.request.urlopen('http://127.0.0.1:9222/json/version', timeout=.3) as r:
            assert json.load(r)['webSocketDebuggerUrl']
        print('Managed browser CDP ready')
        break
    except OSError: time.sleep(.1)
else: raise RuntimeError('browser did not start')
"""
        print(execute(python, "-c", ready))
        execute(
            "tmux",
            "new-session",
            "-d",
            "-s",
            "smoke-page",
            "exec python3 -m http.server 8765 --bind 127.0.0.1 --directory /tmp",
        )
        path = "/workspace/.msandbox/outputs/smoke.png"
        execute(python, "-c", CAPTURE, "http://127.0.0.1:8765/", path)
        print(
            execute(
                python,
                "-c",
                "from pathlib import Path; p=Path('/workspace/.msandbox/outputs/smoke.png'); assert p.read_bytes().startswith(bytes.fromhex('89504e470d0a1a0a')); print('Screenshot PNG verified')",
            )
        )
        execute("tmux", "kill-session", "-t", "=msandbox-browser")
        stopped = """
import socket, time
for attempt in range(40):
    try:
        with socket.create_connection(('127.0.0.1',9222),timeout=.2): pass
    except OSError:
        print('Managed browser stopped; CDP port closed')
        break
    time.sleep(.1)
else: raise RuntimeError('browser survived stop')
"""
        print(execute(python, "-c", stopped))
        # Verify required CLI options without sending data or making a model call.
        help_text = execute("codex", "exec", "--help")
        for flag in ("--ephemeral", "--json", "--disable", "--model"):
            assert flag in help_text, flag
        print(
            json.dumps(
                {
                    "browser_start": "pass",
                    "capture": "pass",
                    "browser_stop": "pass",
                    "codex_options": "pass",
                }
            )
        )
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name], capture_output=True, timeout=15, check=False
        )


if __name__ == "__main__":
    main()
