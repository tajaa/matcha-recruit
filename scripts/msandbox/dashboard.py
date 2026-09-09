"""Terminal dashboard; existing wizard flows own all lifecycle mutations."""

from __future__ import annotations

import queue
import sys
import termios
import threading
from pathlib import Path

from .capabilities import leaks, load_report, missing_required, report_is_stale
from .dashboard_view import GLOBALS, TABS, Row, ViewState, build_layout, overview
from .errors import RECOVERABLE_ERRORS
from .files import list_files
from .inspection import inspect_session
from .state import list_sessions, load_session


class Observations:
    """Queue bounded process probes; explicit refreshes are never dropped."""

    def __init__(self):
        self.snapshots = {}
        self.pending = None
        self.completed = queue.SimpleQueue()
        self.versions = {}
        self.queued = {}

    def request(self, record):
        version = self.versions.get(record.id, 0) + 1
        self.versions[record.id] = version
        self.snapshots.pop(record.id, None)
        self.queued[record.id] = (version, record)
        self._start_next()

    def ensure(self, record):
        if record.id not in self.snapshots and not self.is_pending(record.id):
            self.request(record)

    def is_pending(self, session_id):
        return self.pending == session_id or session_id in self.queued

    def _start_next(self):
        if self.pending is not None or not self.queued:
            return
        session_id = next(iter(self.queued))
        version, record = self.queued.pop(session_id)
        self.pending = session_id

        def inspect():
            result = "Inspection failed before producing a result."
            try:
                result = inspect_session(record)
            except BaseException as exc:  # noqa: BLE001 - worker must always release the probe slot
                try:
                    result = f"{type(exc).__name__}: {exc}"
                except BaseException:  # noqa: BLE001
                    result = "Unexpected inspection failure."
            finally:
                self.completed.put((session_id, version, result))

        # Inspection has subprocess timeouts and never starts containers. A slow
        # Docker daemon must not hold the UI or keep a quitting manager alive.
        threading.Thread(
            target=inspect, daemon=True, name="msandbox-inspection"
        ).start()

    def poll(self):
        while True:
            try:
                session_id, version, result = self.completed.get_nowait()
            except queue.Empty:
                break
            if self.versions.get(session_id, 0) == version:
                self.snapshots[session_id] = result
            if self.pending == session_id:
                self.pending = None
            self._start_next()

    def invalidate(self, session_id):
        self.versions[session_id] = self.versions.get(session_id, 0) + 1
        self.snapshots.pop(session_id, None)
        self.queued.pop(session_id, None)


class LocalDetails:
    """Load cached reports and file indexes off the curses input thread."""

    def __init__(self):
        self.values = {}
        self.errors = {}
        self.pending = set()
        self.completed = queue.SimpleQueue()
        self.versions = {}
        self.queued = {}
        self.active = None

    def ensure(self, record, tab):
        kind = {2: "report", 3: "files"}.get(tab)
        if kind is None:
            return
        key = (record.id, kind)
        if key in self.values or key in self.errors or key in self.pending:
            return
        version = self.versions.get(key, 0)
        self.pending.add(key)
        self.queued[key] = (version, record, kind)
        self._start_next()

    def _start_next(self):
        if self.active is not None or not self.queued:
            return
        key = next(iter(self.queued))
        version, record, kind = self.queued.pop(key)
        self.active = key

        def read():
            value, error = None, None
            try:
                value = load_report(record) if kind == "report" else list_files(record)
            except BaseException as exc:  # noqa: BLE001 - worker must always release the read slot
                try:
                    error = f"{kind}: {type(exc).__name__}: {exc}"
                except BaseException:  # noqa: BLE001
                    error = f"{kind}: unexpected read failure"
            finally:
                self.completed.put((key, version, value, error))

        threading.Thread(
            target=read, daemon=True, name=f"msandbox-{kind}-{record.id}"
        ).start()

    def poll(self):
        while True:
            try:
                key, version, value, error = self.completed.get_nowait()
            except queue.Empty:
                break
            self.pending.discard(key)
            if self.active == key:
                self.active = None
            if self.versions.get(key, 0) != version:
                self._start_next()
                continue
            if error:
                self.errors[key] = error
            else:
                self.values[key] = value
            self._start_next()

    def for_record(self, record):
        if record is None:
            return {}
        result = {
            kind: self.values[(record.id, kind)]
            for kind in ("report", "files")
            if (record.id, kind) in self.values
        }
        errors = [
            error
            for (session_id, _), error in self.errors.items()
            if session_id == record.id
        ]
        if errors:
            result["errors"] = errors
        result["pending"] = {
            kind for session_id, kind in self.pending if session_id == record.id
        }
        return result

    def invalidate(self, session_id):
        for kind in ("report", "files"):
            key = (session_id, kind)
            self.versions[key] = self.versions.get(key, 0) + 1
            self.values.pop(key, None)
            self.errors.pop(key, None)
            if key in self.queued:
                self.queued.pop(key)
                self.pending.discard(key)


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
        if observations.is_pending(record.id):
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
                Row(
                    "Loading cached capability report…"
                    if "report" in local.get("pending", set())
                    else "No cached capability report. Open Tools & access to measure."
                )
            )
        else:
            leaked = {item.id for item in leaks(report)}
            required = {item.id for item in missing_required(report)}
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
            if leaked:
                rows.append(
                    Row(
                        "ATTENTION: unexpected sandbox access was measured — review leaked capabilities below.",
                        tone="warning",
                    )
                )
            elif required:
                rows.append(
                    Row(
                        "Required capabilities are unavailable — review the affected tools below.",
                        tone="warning",
                    )
                )
            for item in report.results:
                problem = item.id in leaked or item.id in required
                label = (
                    "LEAK"
                    if item.id in leaked
                    else "REQUIRED MISSING"
                    if item.id in required
                    else item.status.upper()
                )
                rows += [
                    Row(
                        f"{label}  {item.title}",
                        tone="warning"
                        if problem
                        else "accent"
                        if item.status == "available"
                        else "muted",
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
                    "Loading file index…"
                    if "files" in local.get("pending", set())
                    else "No files yet. Import attachments or save generated work in .msandbox/outputs/."
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


def _screen(window, records, state, observations, details=None):
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
    details = details or LocalDetails()
    while True:
        observations.poll()
        details.poll()
        record = next((r for r in records if r.id == state.session_id), None)
        if record and state.tab == 1:
            observations.ensure(record)
        if record:
            details.ensure(record, state.tab)
        local = details.for_record(record)
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
            wheel_down = getattr(curses, "BUTTON5_PRESSED", None)
            if wheel_down and buttons & curses.BUTTON4_PRESSED:
                state.scroll = max(0, state.scroll - 3)
            elif wheel_down and buttons & wheel_down:
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


def _terminal_screen(records, state, observations, details=None):
    import curses

    descriptor = sys.stdin.fileno()
    attributes = termios.tcgetattr(descriptor)
    try:
        return curses.wrapper(_screen, records, state, observations, details)
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

    state, observations, details = ViewState(), Observations(), LocalDetails()
    curses_failures = 0
    while True:
        failures = []
        try:
            records = []
            for record in list_sessions():
                try:
                    records.append(reconcile_session(record))
                except (*RECOVERABLE_ERRORS, TypeError) as exc:
                    records.append(record)
                    failures.append(f"{record.name}: {exc}")
            records.reverse()
        except KeyboardInterrupt:
            state.notice = (
                "Refresh interrupted. Saved session records remain available."
            )
            continue
        selected = next(
            (
                index
                for index, record in enumerate(records)
                if record.id == state.session_id
            ),
            None,
        )
        if selected is None:
            state.session_id = records[0].id if records else None
            state.sidebar = state.scroll = state.cursor = 0
        else:
            state.sidebar = selected
        if failures:
            state.notice = "Sessions needing repair: " + "; ".join(failures)
        try:
            command = _terminal_screen(records, state, observations, details)
            curses_failures = 0
        except KeyboardInterrupt:
            state.region = 0
            state.notice = "Returned to session navigation. Running work continues."
            continue
        except curses.error:
            curses_failures += 1
            if curses_failures == 1:
                state.notice = "Terminal changed while drawing; dashboard recovered."
                continue
            print(
                "Dashboard unavailable in this terminal; opening classic menu.",
                file=output,
            )
            return None
        except termios.error:
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
                    record = load_session(state.session_id)
                    observations.request(record)
                    details.invalidate(record.id)
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
                wizard._perform_session_action(
                    record, command, reader=input, output=output
                )
                observations.invalidate(record.id)
                details.invalidate(record.id)
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
