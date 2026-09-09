"""Terminal dashboard; existing wizard flows own all lifecycle mutations."""

from __future__ import annotations

import queue
import sys
import termios
import threading
from pathlib import Path

from .capabilities import load_report, report_is_stale
from .dashboard_view import GLOBALS, TABS, Row, ViewState, build_layout, overview
from .errors import RECOVERABLE_ERRORS
from .files import list_files
from .inspection import inspect_session
from .state import list_sessions, load_session


class Observations:
    """One bounded read-only probe at a time; results retain their session ID."""

    def __init__(self):
        self.snapshots = {}
        self.pending = None
        self.completed = queue.SimpleQueue()
        self.versions = {}

    def request(self, record):
        if self.pending is not None:
            return
        self.pending = record.id
        version = self.versions.get(record.id, 0)

        def inspect():
            try:
                result = inspect_session(record)
            except (*RECOVERABLE_ERRORS, TypeError) as exc:
                result = str(exc)
            self.completed.put((record.id, version, result))

        # Inspection has subprocess timeouts and never starts containers. A slow
        # Docker daemon must not hold the UI or keep a quitting manager alive.
        threading.Thread(
            target=inspect, daemon=True, name="msandbox-inspection"
        ).start()

    def poll(self):
        try:
            session_id, version, result = self.completed.get_nowait()
        except queue.Empty:
            return
        if self.versions.get(session_id, 0) == version:
            self.snapshots[session_id] = result
        self.pending = None

    def invalidate(self, session_id):
        self.versions[session_id] = self.versions.get(session_id, 0) + 1
        self.snapshots.pop(session_id, None)


def session_rows(record, tab, observations, local):
    if record is None:
        return [
            Row("A workspace for each task", tone="accent"),
            Row(
                "Create an isolated session, choose Codex, Claude or OpenCode, and select a starting branch or PR."
            ),
            Row("+ New session", "new"),
            Row("Open AutoPR dashboard", "dashboard"),
        ]
    rows = [
        Row(f"Start / resume {record.agent}", "open"),
        Row("Change harness…", "switch"),
        Row("Open shell", "shell"),
        Row(""),
    ]
    if tab == 0:
        return rows + overview(record)
    if tab == 1:
        rows += [
            Row("Refresh processes & connections", "refresh"),
            Row("Manage dev-remote.sh  /  start or stop", "environment"),
            Row("Manage Chromium  /  start, stop, screenshot", "browser"),
            Row(""),
        ]
        snapshot = observations.snapshots.get(record.id)
        if observations.pending == record.id:
            rows.append(Row("Inspecting… you can keep navigating.", tone="accent"))
        if snapshot is None:
            rows.append(
                Row("No measurement yet. Refresh inspects without starting services.")
            )
        elif isinstance(snapshot, str):
            rows.append(Row(f"Inspection unavailable: {snapshot}", tone="warning"))
        else:
            rows += [
                Row(f"Measured {snapshot.checked_at}", tone="muted"),
                Row(
                    "Snapshot only; refresh after external changes. TCP reachability does not prove app health.",
                    tone="muted",
                ),
            ]
            if not snapshot.reliable:
                rows.append(
                    Row(
                        "Partial measurement — some live state is unknown",
                        tone="warning",
                    )
                )
            rows += [Row(line) for line in snapshot.lines]
        return rows
    if tab == 2:
        rows += [Row("Tools & access  /  details or remeasure", "tools"), Row("")]
        report = local.get("report")
        if report is None:
            rows.append(
                Row("No cached capability report. Open Tools & access to measure.")
            )
        else:
            rows += [
                Row(
                    f"Last measured {report.checked_at}"
                    + (" · stale" if report_is_stale(report) else ""),
                    tone="muted",
                ),
                Row(
                    "Historical access checks; live processes are in Processes.",
                    tone="muted",
                ),
            ]
            for item in report.results:
                rows += [
                    Row(
                        f"{item.status.upper()}  {item.title}",
                        tone="accent" if item.status == "available" else "warning",
                    ),
                    Row(item.detail),
                    Row(""),
                ]
        return rows
    if tab == 3:
        rows += [
            Row("Manage files  /  import, preview, send, export", "files"),
            Row(""),
        ]
        files = local.get("files", [])
        rows.append(Row("UPLOADED & GENERATED FILES", tone="accent"))
        rows += [Row(f"{item.container_path}  ({item.size:,} bytes)") for item in files]
        if not files:
            rows.append(
                Row(
                    "No files yet. Import attachments or save generated work in .msandbox/outputs/."
                )
            )
        rows.append(
            Row(
                "Export files you want to keep before releasing the workspace.",
                tone="muted",
            )
        )
        return rows
    if tab == 4:
        rows += [
            Row("Run validation  /  changed files, PR, browser or Xcode", "validate"),
            Row(""),
        ]
        result = record.last_validation
        if result:
            rows += [
                Row(f"LAST VALIDATION: {result.status.upper()}", tone="accent"),
                Row(f"{result.mode} · {result.finished_at}"),
                Row(f"Commit: {result.commit_sha}"),
                Row(f"Report: {result.result_path}"),
                Row(
                    "Historical result; publication revalidates the current commit.",
                    tone="muted",
                ),
            ]
        else:
            rows.append(Row("No validation has run for this session."))
        return rows
    return rows + [
        Row("BRANCH & PULL REQUEST", tone="accent"),
        Row(f"Branch: {record.target_branch or 'Not selected'}"),
        Row(f"PR: {record.pr_url or 'Not published'}"),
        Row("Open branch / PR workflow", "publish"),
        Row(""),
        Row("1. Optionally draft branch, commit and PR copy with Luna high."),
        Row("2. Review and edit the copy and changed files."),
        Row("3. Create branch / commit (stops the harness and workspace)."),
        Row("4. Validate and publish after confirmation."),
        Row("Already committed work can publish without a Luna draft.", tone="muted"),
    ]


def local_details(record):
    details = {}
    if record:
        for name, read in (("report", load_report), ("files", list_files)):
            try:
                details[name] = read(record)
            except (*RECOVERABLE_ERRORS, TypeError) as exc:
                details.setdefault("errors", []).append(f"{name}: {exc}")
    return details


def _screen(window, records, state, observations):
    import curses

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    curses.mousemask(curses.ALL_MOUSE_EVENTS)
    window.timeout(150)
    colors = {}
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        for index, (tone, fg, bg) in enumerate(
            (
                ("text", curses.COLOR_WHITE, -1),
                ("accent", curses.COLOR_CYAN, -1),
                ("muted", curses.COLOR_WHITE, -1),
                ("border", curses.COLOR_CYAN, -1),
                ("button", curses.COLOR_CYAN, -1),
                ("selected", curses.COLOR_BLACK, curses.COLOR_CYAN),
                ("warning", curses.COLOR_YELLOW, -1),
                ("title", curses.COLOR_WHITE, -1),
            ),
            1,
        ):
            if curses.COLORS >= 256:
                fg, bg = {
                    "accent": (79, 233),
                    "button": (79, 235),
                    "selected": (16, 79),
                    "muted": (245, 233),
                    "border": (239, 233),
                    "warning": (222, 233),
                }.get(tone, (253, 233))
            try:
                curses.init_pair(index, fg, bg)
                colors[tone] = curses.color_pair(index)
            except curses.error:
                pass
        window.bkgd(" ", colors.get("text", 0))
    local_id, local = None, {}
    while True:
        observations.poll()
        record = next((r for r in records if r.id == state.session_id), None)
        if record and local_id != record.id:
            local_id, local = record.id, local_details(record)
        if record and state.tab == 1 and record.id not in observations.snapshots:
            observations.request(record)
        rows = session_rows(record, state.tab, observations, local)
        rows += [Row(error, tone="warning") for error in local.get("errors", [])]
        height, width = window.getmaxyx()
        layout = build_layout(records, state, rows, width, height)
        window.erase()
        for x, y, text, tone in layout.draws:
            style = colors.get(tone, 0)
            if tone in ("accent", "title", "selected"):
                style |= curses.A_BOLD
            if tone in ("muted", "border"):
                style |= curses.A_DIM
            try:
                window.addstr(y, x, text, style)
            except curses.error:
                # Terminal resize can race a frame; retry at the next tick.
                pass
        window.refresh()
        try:
            key = window.get_wch()
        except curses.error:
            continue
        except KeyboardInterrupt:
            state.region = 0
            state.notice = "Returned to session navigation. Running work continues."
            continue
        command = None
        if key in ("q", "Q", "\x04"):
            return "exit"
        if key == "c":
            return "classic"
        if key == "n":
            return "new"
        if key == "r":
            return "reload"
        elif key == "\t":
            state.region = (state.region + 1) % 3
        elif key == curses.KEY_BTAB:
            state.region = (state.region - 1) % 3
        elif key == "\x1b":
            state.region = 0
        elif isinstance(key, str) and key in "123456":
            state.tab, state.scroll, state.cursor = int(key) - 1, 0, 0
            state.region = 1
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT) and state.region == 1:
            state.tab = (state.tab + (1 if key == curses.KEY_RIGHT else -1)) % len(TABS)
            state.scroll = state.cursor = 0
        elif key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
            state.scroll = max(
                0,
                state.scroll
                + (1 if key == curses.KEY_NPAGE else -1) * layout.content_height,
            )
        elif key in (curses.KEY_UP, curses.KEY_DOWN, "j", "k"):
            direction = 1 if key in (curses.KEY_DOWN, "j") else -1
            if state.region == 0:
                state.sidebar = (state.sidebar + direction) % (
                    len(records) + len(GLOBALS)
                )
                if state.sidebar < len(records):
                    state.session_id = records[state.sidebar].id
                    state.scroll = state.cursor = 0
            elif state.region == 1:
                state.tab = (state.tab + direction) % len(TABS)
                state.scroll = state.cursor = 0
            elif layout.action_lines:
                state.cursor = (state.cursor + direction) % len(layout.action_lines)
                line = layout.action_lines[state.cursor]
                state.scroll = max(0, min(state.scroll, line))
                state.scroll = max(state.scroll, line - layout.content_height + 1)
        elif key in ("\n", "\r", curses.KEY_ENTER, " "):
            if state.region == 0:
                if state.sidebar < len(records):
                    state.session_id = records[state.sidebar].id
                    state.region = 2
                else:
                    command = GLOBALS[state.sidebar - len(records)][1]
            elif state.region == 1:
                state.region = 2
            else:
                actions = [row.action for row in rows if row.action]
                line = (
                    layout.action_lines[state.cursor] if layout.action_lines else None
                )
                if (
                    actions
                    and line is not None
                    and (
                        line < 0
                        or state.scroll <= line < state.scroll + layout.content_height
                    )
                ):
                    command = actions[state.cursor]
                else:
                    state.notice = (
                        "Use ↑↓ to select a visible action before pressing Enter."
                    )
        elif key == curses.KEY_MOUSE:
            try:
                _, x, y, _, buttons = curses.getmouse()
            except curses.error:
                continue
            if buttons & curses.BUTTON4_PRESSED:
                state.scroll = max(0, state.scroll - 3)
            elif buttons & getattr(curses, "BUTTON5_PRESSED", 0):
                state.scroll += 3
            elif buttons & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                command = layout.hit(x, y)
        if command and command.startswith("session:"):
            state.session_id = command.partition(":")[2]
            state.sidebar = next(
                i for i, r in enumerate(records) if r.id == state.session_id
            )
            state.region, state.scroll, state.cursor = 0, 0, 0
        elif command and command.startswith("tab:"):
            state.tab, state.region = int(command.partition(":")[2]), 1
            state.scroll = state.cursor = 0
        elif command == "refresh":
            if record:
                observations.request(record)
        elif command:
            return command


def _terminal_screen(records, state, observations):
    import curses

    descriptor = sys.stdin.fileno()
    attributes = termios.tcgetattr(descriptor)
    try:
        return curses.wrapper(_screen, records, state, observations)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, attributes)


def run_dashboard(repo: Path, *, output=sys.stdout):
    """Suspend the full screen before prompts, pagers, shell, or tmux attach."""
    try:
        import curses
    except ImportError:
        print("Python curses is unavailable; opening classic menu.", file=output)
        return None

    from . import wizard
    from .manager import show
    from .sessions import reconcile_session

    state, observations = ViewState(), Observations()
    while True:
        records = list(reversed(list_sessions()))
        if not any(r.id == state.session_id for r in records):
            state.session_id = records[0].id if records else None
            state.sidebar = state.scroll = state.cursor = 0
        try:
            command = _terminal_screen(records, state, observations)
        except (curses.error, termios.error):
            print(
                "Dashboard unavailable in this terminal; opening classic menu.",
                file=output,
            )
            return None
        if command == "exit":
            return 0
        if command == "classic":
            return None
        try:
            if command == "reload":
                if state.session_id:
                    observations.request(load_session(state.session_id))
            elif command == "new":
                wizard._new_session(repo, reader=input, output=output)
                state.session_id = None
            elif command == "dashboard":
                wizard._open_autopr_dashboard(repo, output=output)
            elif command == "legacy":
                wizard._open_legacy_workspace(repo, output=output)
            elif command == "cleanup":
                wizard._cleanup(repo, reader=input, output=output)
                wizard._acknowledge(input, output)
            elif state.session_id:
                record = reconcile_session(load_session(state.session_id))
                wizard._open_session(
                    record, reader=input, output=output, initial_action=command
                )
                observations.invalidate(record.id)
            state.notice = (
                "Returned to dashboard. r refreshes processes and connections."
            )
        except EOFError:
            return 0
        except KeyboardInterrupt:
            state.notice = "Action interrupted. Refresh processes to check its state."
        except (*RECOVERABLE_ERRORS, TypeError) as exc:
            try:
                show(
                    f"Could not complete that action: {exc}",
                    reader=input,
                    output=output,
                )
            except EOFError:
                return 0
            except KeyboardInterrupt:
                pass
            state.notice = "Action failed. Select another action or retry."
