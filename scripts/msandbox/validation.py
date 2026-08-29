from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from .docker_runtime import ensure_container, exec_in_session
from .git_worktrees import current_head, dirty_fingerprint
from .host_actions import XCODE_TARGETS, affected_xcode_targets, run_xcode_action
from .models import (
    CommandCheck,
    CommandResult,
    SessionRecord,
    TestPlan,
    ValidationReference,
    ValidationReport,
    utc_now,
)
from .state import save_session, session_dir


class ValidationError(RuntimeError):
    pass


def changed_paths(session: SessionRecord) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(session.worktree),
            "diff",
            "--name-only",
            f"{session.base_sha}...HEAD",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    paths = {line for line in result.stdout.splitlines() if line}
    status = subprocess.run(
        ["git", "-C", str(session.worktree), "status", "--porcelain=v1"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    for line in status.splitlines():
        if len(line) > 3:
            paths.add(line[3:].split(" -> ")[-1])
    return sorted(paths)


def _check(identifier: str, title: str, command: str, *, host: bool = False) -> CommandCheck:
    return CommandCheck(identifier, title, ("bash", "-lc", command), "/workspace", True, host)


def build_test_plan(
    session: SessionRecord,
    mode: str,
    *,
    browser: bool = False,
    xcode: str | None = None,
) -> TestPlan:
    if mode not in ("changed", "pr", "all"):
        raise ValidationError(f"unknown validation mode: {mode}")
    paths = changed_paths(session)
    all_mode = mode == "all"
    checks = [
        _check(
            "toolchain-login-shell",
            "Login-shell Node/npm/npx and Python toolchain",
            "node --version && npm --version && npx --version && "
            "server/venv/bin/python -m pytest --version && client/node_modules/.bin/vitest --version",
        ),
        _check(
            "executable-tempdir",
            "Executable temporary directory for OpenCode OpenTUI",
            # Docker Desktop otherwise applies noexec even when the option is
            # merely omitted from Compose, which prevents OpenTUI loading its
            # extracted native renderer.
            "mount | awk '$3 == \"/tmp\" { found=1; if ($6 ~ /noexec/) bad=1 } END { exit (!found || bad) }'",
        ),
        _check(
            "python-compile",
            "Python compile check",
            "server/venv/bin/python -m compileall -q server/app server/alembic scripts",
        ),
    ]
    if mode in ("pr", "all"):
        checks.append(
            _check(
                "isolated-data-services",
                "Isolated PostgreSQL and Redis",
                "pg_isready -h postgres -U matcha -d matcha_test && "
                "test \"$(redis-cli -h redis ping)\" = PONG",
            )
        )
    scripts_changed = all_mode or any(
        path.startswith(("scripts/", "docker/", ".github/")) or path.startswith("docker-compose")
        for path in paths
    )
    server_changed = all_mode or any(path.startswith("server/") for path in paths)
    client_changed = all_mode or any(
        path.startswith("client/") and not path.startswith(("client/tellus/", "client/oceanlab/"))
        for path in paths
    )
    tellus_changed = all_mode or any(path.startswith("client/tellus/") for path in paths)
    oceanlab_changed = all_mode or any(path.startswith("client/oceanlab/") for path in paths)

    if server_changed:
        checks.append(
            _check(
                "server-migrations",
                "Apply migrations to isolated test database",
                "cd server && ./venv/bin/python -m alembic upgrade heads",
            )
        )
    if scripts_changed:
        checks.append(
            _check(
                "automation-contracts",
                "msandbox and AutoPR contract tests",
                "for test in scripts/tests/test_agent_sandbox_lifecycle.sh "
                "scripts/tests/test_agent_sandbox_networking.sh "
                "scripts/tests/test_msandbox_attachments.sh "
                "scripts/tests/test_msandbox_sessions.sh "
                "scripts/tests/test_msandbox_worktrees.sh; do bash \"$test\"; done",
            )
        )
    if server_changed:
        if mode == "changed":
            checks.append(_check("server-targeted", "Server targeted tests", "cd server && ./venv/bin/python -m pytest -q tests"))
        else:
            checks.append(
                _check(
                    "server-full",
                    "Server test suite",
                    "cd server && ./venv/bin/python -m pytest -q tests app/oceanlab/tests",
                )
            )
    if client_changed:
        checks.append(_check("client-tests", "Main client Vitest", "cd client && npm run test:run"))
        if mode != "changed":
            checks.extend(
                [
                    _check("client-lint", "Main client lint", "cd client && npm run lint"),
                    _check("client-build", "Main client production build", "cd client && npm run build"),
                ]
            )
    if tellus_changed:
        checks.append(_check("tellus-build", "Tellus production build", "cd client/tellus && npm run build"))
    if oceanlab_changed:
        checks.extend(
            [
                _check("oceanlab-lint", "Oceanlab lint", "cd client/oceanlab && npm run lint"),
                _check("oceanlab-build", "Oceanlab production build", "cd client/oceanlab && npm run build"),
            ]
        )
    if browser:
        checks.append(
            _check(
                "browser-smoke",
                "Playwright browser capability",
                "test -x /opt/playwright/chromium-*/chrome-linux/chrome || "
                "server/venv/bin/python -c 'from playwright.sync_api import sync_playwright; "
                "p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()'",
            )
        )

    targets: set[str] = set()
    if xcode == "all":
        targets = set(XCODE_TARGETS)
    elif xcode == "affected":
        targets = affected_xcode_targets(paths)
    return TestPlan(mode, tuple(paths), tuple(checks), tuple(sorted(targets)))


def _run_container_check(session: SessionRecord, check: CommandCheck) -> CommandResult:
    started = time.monotonic()
    result = exec_in_session(session, check.argv, tty=False, capture=True)
    elapsed = time.monotonic() - started
    output = ((result.stdout or "") + (result.stderr or ""))[-32000:]
    status = "pass" if result.returncode == 0 else "unavailable" if result.returncode == 127 else "fail"
    return CommandResult(check.id, check.title, status, result.returncode, elapsed, output)


def run_test_plan(session: SessionRecord, plan: TestPlan) -> ValidationReport:
    ensure_container(session, test_services=True)
    results = [_run_container_check(session, check) for check in plan.checks]
    for target in plan.xcode_targets:
        results.append(run_xcode_action(session, target, "build"))
        if target != "espresso":
            results.append(run_xcode_action(session, target, "test"))
    status = "pass" if all(result.status in ("pass", "skip") for result in results) else "fail"
    head = current_head(session.worktree)
    fingerprint = dirty_fingerprint(session.worktree)
    report_dir = session_dir(session.id) / "validation"
    report_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = int(time.time())
    report_path = report_dir / f"{stamp}-{plan.mode}.json"
    payload = {
        "schema_version": 1,
        "mode": plan.mode,
        "status": status,
        "commit_sha": head,
        "dirty_fingerprint": fingerprint,
        "changed_paths": list(plan.changed_paths),
        "results": [result.__dict__ for result in results],
        "finished_at": utc_now(),
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    session.last_validation = ValidationReference(
        plan.mode,
        head,
        fingerprint,
        status,
        str(report_path),
        payload["finished_at"],
    )
    save_session(session)
    return ValidationReport(status, head, fingerprint, tuple(results), report_path)
