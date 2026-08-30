from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Sequence, TextIO, TypeVar

from .agent_adapters import attach_agent
from .docker_gc import collect_garbage
from .docker_runtime import ensure_container, exec_in_session, session_home
from .models import SessionRecord, SessionSpec
from .sessions import (
    create_session,
    reconcile_session,
    release_session,
    start_session,
    stop_session,
    submit_session,
)
from .state import list_sessions, save_session
from .validation import build_test_plan, run_test_plan


ChoiceValue = TypeVar("ChoiceValue")
Reader = Callable[[str], str]


def choose(
    title: str,
    choices: Sequence[tuple[str, ChoiceValue]],
    *,
    reader: Reader = input,
    output: TextIO = sys.stdout,
    default: int = 1,
) -> ChoiceValue:
    if not choices:
        raise ValueError("a wizard choice list cannot be empty")
    if not 1 <= default <= len(choices):
        raise ValueError("wizard default choice is out of range")
    while True:
        print(f"\n{title}\n", file=output)
        for index, (label, _) in enumerate(choices, start=1):
            marker = "*" if index == default else " "
            print(f" {marker} {index}. {label}", file=output)
        raw = reader(f"\nChoice [{default}]: ").strip()
        if not raw:
            return choices[default - 1][1]
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][1]
        print(f"Enter a number from 1 to {len(choices)}.", file=output)


def next_session_name(
    agent: str,
    records: Sequence[SessionRecord],
    *,
    pr_number: int | None = None,
) -> str:
    stem = f"{agent}-pr-{pr_number}" if pr_number is not None else agent
    names = {record.name for record in records if record.phase != "released"}
    if stem not in names:
        return stem
    index = 2
    while f"{stem}-{index}" in names:
        index += 1
    return f"{stem}-{index}"


def _legacy_script(repo: Path) -> Path:
    script = repo / "scripts/agent-sandbox.sh"
    if not script.is_file() or not os.access(script, os.X_OK):
        raise RuntimeError(f"legacy workspace launcher is unavailable: {script}")
    return script


def _open_legacy_workspace(repo: Path, *, output: TextIO) -> None:
    environment = dict(os.environ)
    environment["MSANDBOX_WIZARD_SHELL"] = "1"
    completed = subprocess.run(
        [str(_legacy_script(repo)), "shell"],
        env=environment,
        check=False,
    )
    if completed.returncode not in (0, 86):
        print(f"Legacy workspace exited with status {completed.returncode}.", file=output)


def _open_autopr_dashboard(repo: Path, *, output: TextIO) -> None:
    started = subprocess.run([str(_legacy_script(repo)), "start"], check=False)
    if started.returncode:
        raise RuntimeError("AutoPR control plane did not start")
    configured = os.environ.get("AUTOPR_TMUX_BIN")
    tmux = configured or shutil.which("tmux")
    if not tmux:
        raise RuntimeError("tmux is required for the AutoPR dashboard")
    dashboard = os.environ.get("AUTOPR_TMUX_SESSION", "matcha-autopr")
    completed = subprocess.run(
        [tmux, "attach-session", "-t", dashboard],
        check=False,
    )
    if completed.returncode:
        print(f"AutoPR dashboard exited with status {completed.returncode}.", file=output)


def _install_session_shell_handoff(record: SessionRecord) -> str:
    """Atomically install the release-owned shell handoff into one session home."""
    source = Path(__file__).with_name("wizard-shell.bash")
    home = session_home(record)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".wizard-shell.", dir=home)
    temporary = Path(temporary_name)
    destination = home / ".msandbox-wizard.bash"
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return "/home/agent/.msandbox-wizard.bash"


def _new_session(
    repo: Path,
    *,
    reader: Reader,
    output: TextIO,
) -> None:
    agent = choose(
        "Choose an agent",
        (
            ("Codex", "codex"),
            ("Claude", "claude"),
            ("OpenCode", "opencode"),
            ("Back", None),
        ),
        reader=reader,
        output=output,
    )
    if agent is None:
        return
    permission_mode = choose(
        "Choose permissions",
        (
            ("Standard — ask before sensitive actions", "standard"),
            ("Autonomous — bypass the agent's approval checks", "autonomous"),
            ("Back", None),
        ),
        reader=reader,
        output=output,
    )
    if permission_mode is None:
        return
    capability = choose(
        "Choose development tools",
        (
            ("Development — tools plus isolated host ports", (True, False)),
            ("Development + browser — include Playwright/Chromium", (True, True)),
            ("Agent only — tools without published dev ports", (False, False)),
            ("Back", None),
        ),
        reader=reader,
        output=output,
    )
    if capability is None:
        return
    dev, playwright = capability
    source = choose(
        "Choose starting point",
        (("Latest main", "main"), ("Existing pull request", "pr"), ("Back", None)),
        reader=reader,
        output=output,
    )
    if source is None:
        return
    pr_number: int | None = None
    if source == "pr":
        while pr_number is None:
            raw = reader("Pull request number (blank to cancel): ").strip().removeprefix("#")
            if not raw:
                return
            if raw.isdigit() and int(raw) > 0:
                pr_number = int(raw)
            else:
                print("Enter a positive pull request number.", file=output)

    suggested = next_session_name(agent, list_sessions(), pr_number=pr_number)
    name = reader(f"Session name [{suggested}]: ").strip() or suggested
    summary = (
        f"{agent} / {permission_mode} / "
        f"{'browser' if playwright else 'development' if dev else 'agent only'} / "
        f"{'PR #' + str(pr_number) if pr_number else 'origin/main'}"
    )
    confirmed = choose(
        f"Create {name}?\n  {summary}",
        (("Create and open", True), ("Cancel", False)),
        reader=reader,
        output=output,
    )
    if not confirmed:
        return
    record = create_session(
        repo,
        SessionSpec(
            name=name,
            agent=agent,
            pr_number=pr_number,
            dev=dev,
            playwright=playwright,
            permission_mode=permission_mode,
        ),
    )
    print(f"\nCreated {record.name}: {record.worktree_path}", file=output)
    if record.ports:
        print(f"Ports: {asdict(record.ports)}", file=output)
    if record.phase == "running":
        attach_agent(record)


def _run_validation(
    record: SessionRecord,
    *,
    reader: Reader,
    output: TextIO,
) -> None:
    selection = choose(
        f"Validate {record.name}",
        (
            ("Changed files", ("changed", False)),
            ("Full PR — includes affected Xcode targets", ("pr", False)),
            ("Full PR + browser", ("pr", True)),
            ("Complete suite — includes all Xcode targets", ("all", False)),
            ("Back", None),
        ),
        reader=reader,
        output=output,
    )
    if selection is None:
        return
    mode, browser = selection
    if browser and not record.playwright:
        record.playwright = True
        save_session(record)
    plan = build_test_plan(record, mode, browser=browser)
    report = run_test_plan(record, plan)
    print(f"\nValidation: {report.status.upper()}", file=output)
    for result in report.results:
        print(f"  [{result.status.upper():11}] {result.title}", file=output)
    print(f"Report: {report.result_path}", file=output)


def _open_session(
    record: SessionRecord,
    *,
    reader: Reader,
    output: TextIO,
) -> None:
    while record.phase != "released":
        action = choose(
            f"{record.name} — {record.agent} / {record.permission_mode} / {record.phase}",
            (
                ("Open agent", "open"),
                ("Open shell", "shell"),
                ("Run validation", "validate"),
                ("Stop session", "stop"),
                ("Submit draft pull request", "submit"),
                ("Release published session", "release"),
                ("Back", "back"),
            ),
            reader=reader,
            output=output,
        )
        if action == "back":
            return
        if action == "open":
            if record.phase != "running":
                start_session(record)
            attach_agent(record)
        elif action == "shell":
            ensure_container(record)
            shell_handoff = _install_session_shell_handoff(record)
            exec_in_session(
                record,
                ["bash", "--rcfile", shell_handoff],
                tty=True,
            )
        elif action == "validate":
            _run_validation(record, reader=reader, output=output)
        elif action == "stop":
            stop_session(record)
        elif action == "submit":
            confirmed = choose(
                "Submission validates the exact commit and publishes its PR branch.",
                (("Submit as draft", True), ("Cancel", False)),
                reader=reader,
                output=output,
                default=2,
            )
            if confirmed:
                pull_request = submit_session(record, draft=True)
                print(f"PR #{pull_request.number}: {pull_request.url}", file=output)
        elif action == "release":
            confirmed = choose(
                "Release only removes a clean worktree whose HEAD is published.",
                (("Cancel", False), ("Release", True)),
                reader=reader,
                output=output,
            )
            if confirmed:
                released = release_session(record)
                print(released.reason, file=output)
        record = reconcile_session(record)


def _cleanup(repo: Path, *, reader: Reader, output: TextIO) -> None:
    preview = collect_garbage(repo, apply=False)
    if preview.skipped:
        print(f"Cleanup unavailable: {preview.skipped}", file=output)
        return
    if not preview:
        print("No unreachable sandbox resources.", file=output)
        return
    print("\nUnreachable resources:", file=output)
    for item in preview.collected:
        print(f"  {item.kind}: {item.name}", file=output)
    confirmed = choose(
        "Reclaim these resources? Live and published-session resources stay protected.",
        (("Cancel", False), ("Reclaim", True)),
        reader=reader,
        output=output,
    )
    if not confirmed:
        return
    report = collect_garbage(repo, apply=True)
    for item in report.collected:
        print(f"Reclaimed {item.kind}: {item.name}", file=output)
    for item in report.failed:
        print(f"Failed {item.kind}: {item.name} ({item.detail})", file=output)


def run_wizard(
    repo: Path,
    *,
    reader: Reader = input,
    output: TextIO = sys.stdout,
) -> int:
    repo = repo.resolve()
    while True:
        try:
            records = [reconcile_session(record) for record in list_sessions()]
            choices: list[tuple[str, tuple[str, str | None]]] = [
                (
                    f"{record.name} — {record.agent} / {record.permission_mode} / {record.phase}",
                    ("session", record.id),
                )
                for record in reversed(records)
            ]
            choices.extend(
                [
                    ("New isolated session", ("new", None)),
                    ("Legacy workspace", ("legacy", None)),
                    ("AutoPR dashboard", ("dashboard", None)),
                    ("Clean up unused resources", ("cleanup", None)),
                    ("Exit", ("exit", None)),
                ]
            )
            action, value = choose(
                "Matcha Sandbox",
                choices,
                reader=reader,
                output=output,
            )
            if action == "exit":
                return 0
            if action == "new":
                _new_session(repo, reader=reader, output=output)
            elif action == "legacy":
                _open_legacy_workspace(repo, output=output)
            elif action == "dashboard":
                _open_autopr_dashboard(repo, output=output)
            elif action == "cleanup":
                _cleanup(repo, reader=reader, output=output)
            elif action == "session" and value:
                record = next(item for item in records if item.id == value)
                _open_session(record, reader=reader, output=output)
        except (EOFError, KeyboardInterrupt):
            print(file=output)
            return 0
        except (KeyError, RuntimeError, OSError) as exc:
            print(f"\nCould not complete that action: {exc}", file=output)
