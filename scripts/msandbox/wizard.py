from __future__ import annotations

import os
import select
import shutil
import subprocess
import sys
import tempfile
import termios
import tty
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Sequence, TextIO, TypeVar

from .agent_adapters import attach_agent, exited_agent_output
from .capabilities import (
    leaks,
    load_report,
    planned_capabilities,
    render_report_text,
    report_is_stale,
)
from .docker_gc import collect_garbage
from .errors import RECOVERABLE_ERRORS
from .docker_runtime import ensure_container, exec_in_session, session_home
from .models import SessionRecord, SessionSpec
from .session_auth import refresh_github_auth
from .sessions import (
    create_session,
    ensure_capability_report,
    reconcile_session,
    release_session,
    start_session,
    stop_session,
)
from .state import list_sessions, save_session
from .terminal_ui import frame, mouse_key, plain
from .validation import build_test_plan, run_test_plan

ChoiceValue = TypeVar("ChoiceValue")
Reader = Callable[[str], str]


def _cancel_choice_index(choices: Sequence[tuple[str, ChoiceValue]]) -> int | None:
    """Return the safe escape choice, regardless of where it appears."""
    for word in ("back", "cancel", "exit"):
        for index, (label, _) in enumerate(choices):
            if label.strip().lower().split(maxsplit=1)[0].rstrip("—:-") == word:
                return index
    return None


def _interpret_terminal_key(data: bytes) -> str | None:
    mouse = mouse_key(data)
    if mouse:
        return mouse
    if data in (b"\r", b"\n"):
        return "enter"
    if data in (b"k", b"K") or (
        data.startswith((b"\x1b[", b"\x1bO")) and data.endswith(b"A")
    ):
        return "up"
    if data in (b"j", b"J") or (
        data.startswith((b"\x1b[", b"\x1bO")) and data.endswith(b"B")
    ):
        return "down"
    if data in (b"q", b"Q", b"\x1b"):
        return "cancel"
    if data == b"\x04":
        return "eof"
    if len(data) == 1 and data.isdigit():
        return data.decode("ascii")
    return None


def _read_terminal_key(descriptor: int) -> str | None:
    data = os.read(descriptor, 1)
    if data == b"\x1b":
        # Kitty sends arrows as a short escape sequence. Collect only bytes
        # that are already waiting so a bare Escape remains responsive.
        while len(data) < 64 and select.select([descriptor], [], [], 0.04)[0]:
            byte = os.read(descriptor, 1)
            data += byte
            if len(data) >= 3 and (byte.isalpha() or byte == b"~"):
                break
        if data == b"\x1b[M":
            # A terminal without SGR mouse support emits an X10 report. Consume
            # its three payload bytes as one event so coordinates such as "q"
            # or digits can never become navigation keystrokes.
            while len(data) < 6:
                if not select.select([descriptor], [], [], 0.04)[0]:
                    return "ignore"
                chunk = os.read(descriptor, 6 - len(data))
                if not chunk:
                    break
                data += chunk
    return _interpret_terminal_key(data)


def _can_use_terminal_menu(reader: Reader, output: TextIO) -> bool:
    return (
        reader is input
        and sys.stdin.isatty()
        and bool(getattr(output, "isatty", lambda: False)())
    )


def _choose_terminal(
    title: str,
    choices: Sequence[tuple[str, ChoiceValue]],
    *,
    output: TextIO,
    default: int,
) -> ChoiceValue:
    descriptor = sys.stdin.fileno()
    previous_attributes = termios.tcgetattr(descriptor)
    selected = default - 1
    numeric = ""
    cancel_index = _cancel_choice_index(choices)
    output.write("\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1006h")
    output.flush()
    try:
        tty.setcbreak(descriptor)
        while True:
            size = shutil.get_terminal_size((100, 30))
            rendered, targets = frame(title, [label for label, _ in choices], selected, size.columns, size.lines)
            output.write(rendered)
            output.flush()

            try:
                key = _read_terminal_key(descriptor)
            except KeyboardInterrupt:
                key = "cancel"
            if key == "up":
                selected = (selected - 1) % len(choices)
                numeric = ""
            elif key == "down":
                selected = (selected + 1) % len(choices)
                numeric = ""
            elif key == "enter":
                return choices[selected][1]
            elif key == "cancel":
                if cancel_index is not None:
                    return choices[cancel_index][1]
                output.write("\a")
                output.flush()
            elif key and key.startswith("click:"):
                row = int(key.rsplit(":", 1)[1])
                if row in targets:
                    return choices[targets[row]][1]
            elif key == "eof":
                raise EOFError
            elif key is not None and key.isdigit():
                candidate = numeric + key
                if candidate.startswith("0") or int(candidate) > len(choices):
                    candidate = key
                if candidate != "0" and int(candidate) <= len(choices):
                    numeric = candidate
                    selected = int(candidate) - 1
                else:
                    numeric = ""
                    output.write("\a")
                    output.flush()
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous_attributes)
        output.write("\x1b[?1000l\x1b[?1006l\x1b[?25h\x1b[?1049l")
        output.flush()


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
    if _can_use_terminal_menu(reader, output):
        try:
            return _choose_terminal(title, choices, output=output, default=default)
        except termios.error:
            # Redirected or unusual pseudo-terminals retain the portable
            # numbered prompt below.
            pass
    cancel_index = _cancel_choice_index(choices)
    while True:
        print(f"\n{plain(title)}\n", file=output)
        for index, (label, _) in enumerate(choices, start=1):
            marker = "*" if index == default else " "
            print(f" {marker} {index}. {plain(label)}", file=output)
        raw = reader(f"\nChoice [{default}]: ").strip()
        if not raw:
            return choices[default - 1][1]
        if raw.lower() in ("q", "quit", "exit", "back") and cancel_index is not None:
            return choices[cancel_index][1]
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][1]
        print(f"Enter a number from 1 to {len(choices)}.", file=output)


def _acknowledge(reader: Reader, output: TextIO) -> None:
    """Keep action output visible before the full-screen menu redraws."""
    try:
        reader("\nPress Enter to return to Matcha Sandbox...")
    except EOFError:
        print(file=output)


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
            ("Codex — OpenAI coding CLI; uses your Codex login", "codex"),
            ("Claude — Anthropic coding CLI; uses your Claude login", "claude"),
            ("OpenCode — Coding CLI with your configured model provider", "opencode"),
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
    planned = "\n".join(planned_capabilities(dev=dev, playwright=playwright))
    while True:
        confirmed = choose(
            f"Create {name}?\n{summary}\nFiles persist when you return to the manager.",
            (("Create and open", True), ("Cancel", False), ("Review planned tools — Inspect tools and access before creating", "details")),
            reader=reader,
            output=output,
        )
        if confirmed != "details":
            break
        from .manager import show
        show(planned, reader=reader, output=output)
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
    report = ensure_capability_report(record)
    print("", file=output)
    print(render_report_text(report, name=record.name), file=output)
    # The agent takes over the terminal on attach. Let the operator read the
    # measured report first rather than discovering it in scrollback.
    _acknowledge(reader, output)
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
    _acknowledge(reader, output)


def _session_menu_title(record: SessionRecord) -> str:
    """Never open a session without showing what it can actually do.

    Reading is cache-only. Measuring here would make every menu redraw launch
    Chromium, authenticate to GitHub, and query production before it could
    print a line; "Refresh capabilities" is the deliberate remeasure.
    """
    header = f"{record.name} — {record.agent} / {record.permission_mode} / {record.phase}"
    try:
        report = load_report(record)
        if report is None:
            return (
                f"{header}\n\nCapabilities have not been measured yet — "
                "open Tools & access to measure them."
            )
        available = sum(item.status == "available" for item in report.results)
        body = f"Tools: {available} available at last check · open Tools & access for details"
        if leaks(report):
            body = "ATTENTION: capability report found unexpected access — open Tools & access"
    except (KeyError, RuntimeError, ValueError, OSError) as exc:
        return f"{header}\n\nCapabilities are unavailable: {exc}"
    notes = []
    if report.container_available and record.phase != "running":
        notes.append(
            f"  measured while the container was running; this session is now {record.phase}"
        )
    if report_is_stale(report):
        notes.append("  measured more than 15 minutes ago; Tools & access can remeasure")
    return "\n".join([header, f"Branch: {record.target_branch or 'not selected'}", body, *notes])


def _open_session(
    record: SessionRecord,
    *,
    reader: Reader,
    output: TextIO,
    initial_action: str | None = None,
) -> None:
    while record.phase != "released":
        preserved_output = exited_agent_output(record)
        title = _session_menu_title(record)
        choices = [
            (
                (
                    f"Restart {record.agent} — Replaces the preserved exit output"
                    if preserved_output is not None
                    else f"{'Resume' if record.phase == 'running' else 'Start'} {record.agent} — Open this harness; Ctrl-b d returns here"
                ),
                "open",
            ),
            (
                (
                    "Change harness — Replaces preserved exit output; keeps files and commits"
                    if preserved_output is not None
                    else "Change harness — Keep files and commits; start a different conversation"
                ),
                "switch",
            ),
            ("Open shell — Terminal in this workspace; exit returns here", "shell"),
            ("Environment & processes — Connections, dev-remote.sh, SSH and running tools", "environment"),
            ("Browser — Enable Chromium, check it, or capture a screenshot", "browser"),
            ("Files & attachments — Import, inspect, deliver and export sandbox files", "files"),
            ("Testing — Changed files, full PR, browser and Xcode validation", "validate"),
            ("Tools & access — Measured capabilities and configuration requirements", "tools"),
            ("Branch & pull request — Luna high drafts branch, commit and PR copy", "publish"),
            ("Stop session — Stop its harness and container; preserve files", "stop"),
            ("Release published session — Free a clean, published worktree", "release"),
            ("Back", "back"),
        ]
        if preserved_output is not None:
            title += (
                "\nHarness exited; its last output is preserved below until restart, "
                "harness switch, or stop."
            )
            choices.insert(
                0,
                (
                    "View exited harness output — Inspect up to 120 lines without replacing them",
                    "harness-output",
                ),
            )
        action = initial_action or choose(
            title,
            choices,
            reader=reader,
            output=output,
        )
        if initial_action == "open" and preserved_output is not None:
            action = choose(
                "Harness exited. Restart replaces its preserved output.",
                [("View exited output", "harness-output"), ("Restart harness", "open"), ("Cancel", "back")],
                reader=reader,
                output=output,
            )
        if action == "back":
            return
        if action in ("switch", "environment", "browser", "files", "tools", "publish"):
            from .manager import manage

            manage(action, record, reader=reader, output=output)
        if action == "harness-output":
            from .manager import show

            show(
                preserved_output or "The exited harness produced no captured output.",
                reader=reader,
                output=output,
            )
        elif action == "open":
            # A running session's agent already read its context at startup;
            # rewriting the report cannot reach that process, and remeasuring
            # would block the attach behind the whole probe suite.
            if record.phase != "running" or preserved_output is not None:
                start_session(record, replace_exited=preserved_output is not None)
            attach_agent(record)
        elif action == "shell":
            refresh_github_auth(record)
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
        elif action == "release":
            confirmed = choose(
                "Release removes a clean worktree whose HEAD is published.\nExport wanted generated files first; unexported files are removed with it.",
                (("Cancel", False), ("Release", True)),
                reader=reader,
                output=output,
            )
            if confirmed:
                released = release_session(record)
                print(released.reason, file=output)
                if initial_action is not None:
                    _acknowledge(reader, output)
        record = reconcile_session(record)
        if initial_action is not None:
            return


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
    if _can_use_terminal_menu(reader, output) and os.environ.get("MSANDBOX_UI") != "classic":
        from .dashboard import run_dashboard

        result = run_dashboard(repo, output=output)
        if result is not None:
            return result
    while True:
        try:
            records = []
            failures = []
            for record in list_sessions():
                try:
                    records.append(reconcile_session(record))
                except RECOVERABLE_ERRORS as exc:
                    records.append(record)
                    failures.append(f"{record.name}: {exc}")
            choices: list[tuple[str, tuple[str, str | None]]] = [
                (
                    f"{record.name} [{record.phase}] · {record.agent} — {record.permission_mode} permissions; open session controls",
                    ("session", record.id),
                )
                for record in reversed(records)
            ]
            choices.extend(
                [
                    ("New isolated session — Choose harness, permissions and starting branch / PR", ("new", None)),
                    ("Legacy workspace — Shared original workspace terminal", ("legacy", None)),
                    ("AutoPR dashboard — Background work and automation health", ("dashboard", None)),
                    ("Clean up unused resources — Preview unused Docker resources before removal", ("cleanup", None)),
                    ("Exit — Close manager; running sessions continue", ("exit", None)),
                ]
            )
            action, value = choose(
                "Matcha Sandbox" + ("\nSessions needing repair: " + "; ".join(failures) if failures else ""),
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
        except EOFError:
            print(file=output)
            return 0
        except KeyboardInterrupt:
            print('\nReturned to Sandbox. Check process status for interrupted actions.', file=output)
        except RECOVERABLE_ERRORS as exc:
            print(f"\nCould not complete that action: {exc}", file=output)
            _acknowledge(reader, output)
