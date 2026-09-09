from __future__ import annotations

import curses
import io
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts.msandbox.dashboard import (
    Observations,
    _screen,
    local_details,
    run_dashboard,
    session_rows,
)
from scripts.msandbox.dashboard_view import TABS, Row, ViewState, build_layout
from scripts.msandbox.inspection import Snapshot
from scripts.msandbox.models import (
    CapabilityReport,
    CapabilityResult,
    SessionRecord,
    ValidationReference,
)
from scripts.msandbox.wizard import _open_session, run_wizard


def record(name="414"):
    return SessionRecord(
        1,
        name,
        name,
        "codex",
        "stopped",
        "/repo",
        f"/worktrees/{name}",
        name,
        name,
        name,
        "origin/main",
        "a" * 40,
        None,
    )


class Window:
    def __init__(self, keys, size=(36, 120)):
        self.keys = iter(keys)
        self.size = size
        self.drawn = []

    def timeout(self, _):
        pass

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.drawn = []

    def addstr(self, y, x, text, style):
        self.drawn.append((y, x, text))

    def refresh(self):
        pass

    def get_wch(self):
        key = next(self.keys)
        if isinstance(key, BaseException):
            raise key
        return key


class DashboardTests(unittest.TestCase):
    def screen(self, keys, state=None, records=None, mouse=None):
        state = state or ViewState(session_id="414")
        window = Window(keys)
        observations = Observations()
        with (
            mock.patch("curses.curs_set"),
            mock.patch("curses.mousemask"),
            mock.patch("curses.has_colors", return_value=False),
            mock.patch("curses.getmouse", return_value=mouse),
            mock.patch("scripts.msandbox.dashboard.local_details", return_value={}),
            mock.patch.object(observations, "request"),
        ):
            result = _screen(
                window, [record()] if records is None else records, state, observations
            )
        return result, state, window

    def test_sidebar_reaches_every_session_and_global_action(self):
        records = [record(str(i)) for i in range(40)]
        state = ViewState(session_id="0")
        result, state, _ = self.screen([curses.KEY_DOWN] * 40 + ["\n"], state, records)
        self.assertEqual(result, "new")
        self.assertEqual(state.sidebar, 40)
        layout = build_layout(records, state, [], 100, 24)
        self.assertIn("new", [t.action for t in layout.targets])

    def test_keyboard_tabs_and_scrolled_actions(self):
        result, state, _ = self.screen(
            ["6", "\n", curses.KEY_DOWN, curses.KEY_DOWN, curses.KEY_DOWN, "\n"]
        )
        self.assertEqual(result, "publish")
        self.assertEqual(state.tab, 5)
        result, _, _ = self.screen(["\n", "\n"])
        self.assertEqual(result, "open")
        result, _, _ = self.screen(
            ["\t", curses.KEY_RIGHT, "\t", curses.KEY_DOWN, "\n"]
        )
        self.assertEqual(result, "switch")

    def test_mouse_targets_use_both_coordinates(self):
        state = ViewState(session_id="414")
        rows = session_rows(record(), 0, Observations(), {})
        layout = build_layout([record()], state, rows, 120, 36)
        target = next(t for t in layout.targets if t.action == "switch")
        self.assertIsNone(layout.hit(target.x - 1, target.y))
        result, _, _ = self.screen(
            [curses.KEY_MOUSE],
            mouse=(0, target.x + 1, target.y, 0, curses.BUTTON1_CLICKED),
        )
        self.assertEqual(result, "switch")

    def test_click_session_and_tab_stays_in_dashboard(self):
        state = ViewState(session_id="414")
        layout = build_layout([record()], state, [], 120, 36)
        target = next(t for t in layout.targets if t.action == "tab:4")
        result, state, _ = self.screen(
            [curses.KEY_MOUSE, "q"],
            mouse=(0, target.x, target.y, 0, curses.BUTTON1_PRESSED),
        )
        self.assertEqual(result, "exit")
        self.assertEqual(state.tab, 4)

    def test_scroll_resize_and_control_keys(self):
        result, state, _ = self.screen(
            [
                "\t",
                curses.KEY_BTAB,
                curses.KEY_NPAGE,
                curses.KEY_PPAGE,
                KeyboardInterrupt(),
                "\x1b",
                "r",
            ]
        )
        self.assertEqual(result, "reload")
        self.assertEqual(state.region, 0)
        self.assertEqual(self.screen(["c"])[0], "classic")
        self.assertEqual(self.screen(["n"])[0], "new")
        self.assertEqual(self.screen(["q"], records=[])[0], "exit")

    def test_scrolled_offscreen_action_cannot_run_on_enter(self):
        state = ViewState(session_id="414", region=2, scroll=15)
        window = Window(["\n", "q"], size=(24, 80))
        with (
            mock.patch("curses.curs_set"),
            mock.patch("curses.mousemask"),
            mock.patch("curses.has_colors", return_value=False),
            mock.patch("scripts.msandbox.dashboard.local_details", return_value={}),
        ):
            self.assertEqual(_screen(window, [record()], state, Observations()), "exit")
        self.assertIn("visible action", state.notice)

    def test_layout_clips_untrusted_text_and_keeps_footer(self):
        for width, height in [(1, 1), (50, 10), (73, 20), (100, 30), (160, 50)]:
            state = ViewState(session_id="414", scroll=500)
            layout = build_layout(
                [record()],
                state,
                [Row("\x1b[31m危险" * 200), Row("Run", "validate")],
                width,
                height,
            )
            for x, y, text, _ in layout.draws:
                self.assertLess(x, width)
                self.assertLess(y, height)
                self.assertNotIn("\x1b", text)
            if width >= 73 and height >= 20:
                self.assertTrue(any("Ctrl-b" in text for _, _, text, _ in layout.draws))
                self.assertLess(state.scroll, 500)

    def test_tabs_render_empty_partial_and_historical_data(self):
        item = record()
        observations = Observations()
        for tab in range(len(TABS)):
            self.assertTrue(session_rows(item, tab, observations, {}))
        observations.snapshots[item.id] = Snapshot(
            "now", None, ("Docker unavailable",), reliable=False
        )
        self.assertIn(
            "Partial measurement",
            "\n".join(r.text for r in session_rows(item, 1, observations, {})),
        )
        observations.snapshots[item.id] = "broken probe"
        self.assertIn(
            "broken probe",
            "\n".join(r.text for r in session_rows(item, 1, observations, {})),
        )
        report = CapabilityReport(
            1,
            item.id,
            (CapabilityResult("test", "Test", "available", "ready"),),
            "2000-01-01T00:00:00+00:00",
        )
        self.assertIn(
            "stale",
            "\n".join(
                r.text for r in session_rows(item, 2, observations, {"report": report})
            ),
        )
        item.last_validation = ValidationReference(
            "pr", "abc", "xyz", "pass", "/report", "now"
        )
        self.assertIn(
            "Historical result",
            "\n".join(r.text for r in session_rows(item, 4, observations, {})),
        )

    def test_local_read_errors_do_not_hide_other_tabs(self):
        with (
            mock.patch(
                "scripts.msandbox.dashboard.load_report",
                side_effect=TypeError("bad report"),
            ),
            mock.patch("scripts.msandbox.dashboard.list_files", return_value=[]),
        ):
            details = local_details(record())
        self.assertEqual(details["files"], [])
        self.assertIn("bad report", details["errors"][0])

    def test_probe_is_nonblocking_and_ignores_invalidated_result(self):
        observations = Observations()
        release = threading.Event()
        started = threading.Event()

        def inspect(_):
            started.set()
            release.wait(2)
            return Snapshot("now", None, ())

        with mock.patch(
            "scripts.msandbox.dashboard.inspect_session", side_effect=inspect
        ) as probe:
            observations.request(record())
            self.assertTrue(started.wait(1))
            observations.request(record("another"))
            self.assertEqual(probe.call_count, 1)
            observations.invalidate("414")
            release.set()
            deadline = time.monotonic() + 2
            while observations.pending is not None and time.monotonic() < deadline:
                observations.poll()
                time.sleep(0.005)
        self.assertIsNone(observations.pending)
        self.assertNotIn("414", observations.snapshots)

    def test_runner_hands_action_to_existing_workflow(self):
        item = record()
        with (
            mock.patch("scripts.msandbox.dashboard.list_sessions", return_value=[item]),
            mock.patch("scripts.msandbox.dashboard.load_session", return_value=item),
            mock.patch(
                "scripts.msandbox.sessions.reconcile_session", return_value=item
            ),
            mock.patch(
                "scripts.msandbox.dashboard._terminal_screen",
                side_effect=["publish", "exit"],
            ),
            mock.patch("scripts.msandbox.wizard._open_session") as action,
        ):
            self.assertEqual(run_dashboard(Path("/repo"), output=io.StringIO()), 0)
        self.assertEqual(action.call_args.kwargs["initial_action"], "publish")

    def test_action_failure_and_global_actions_return_to_dashboard(self):
        item = record()
        with (
            mock.patch("scripts.msandbox.dashboard.list_sessions", return_value=[item]),
            mock.patch("scripts.msandbox.dashboard.load_session", return_value=item),
            mock.patch(
                "scripts.msandbox.sessions.reconcile_session", return_value=item
            ),
            mock.patch(
                "scripts.msandbox.dashboard._terminal_screen",
                side_effect=[
                    "shell",
                    "new",
                    "dashboard",
                    "legacy",
                    "cleanup",
                    "reload",
                    "exit",
                ],
            ),
            mock.patch(
                "scripts.msandbox.wizard._open_session", side_effect=OSError("offline")
            ),
            mock.patch("scripts.msandbox.wizard._new_session") as new,
            mock.patch("scripts.msandbox.wizard._open_autopr_dashboard") as autopr,
            mock.patch("scripts.msandbox.wizard._open_legacy_workspace") as legacy,
            mock.patch("scripts.msandbox.wizard._cleanup") as cleanup,
            mock.patch("scripts.msandbox.wizard._acknowledge"),
            mock.patch("scripts.msandbox.manager.show") as show,
            mock.patch.object(Observations, "request") as refresh,
        ):
            self.assertEqual(run_dashboard(Path("/repo"), output=io.StringIO()), 0)
        show.assert_called_once()
        for action in (new, autopr, legacy, cleanup, refresh):
            action.assert_called_once()

    def test_terminal_failure_falls_back_and_interrupt_remains_usable(self):
        with (
            mock.patch("scripts.msandbox.dashboard.list_sessions", return_value=[]),
            mock.patch(
                "scripts.msandbox.dashboard._terminal_screen",
                side_effect=curses.error(),
            ),
        ):
            self.assertIsNone(run_dashboard(Path("/repo"), output=io.StringIO()))
        self.assertEqual(
            self.screen([curses.error(), KeyboardInterrupt(), "q"])[0], "exit"
        )

    def test_probe_errors_are_visible_and_do_not_block_retry(self):
        observations = Observations()
        with mock.patch(
            "scripts.msandbox.dashboard.inspect_session",
            side_effect=OSError("Docker offline"),
        ):
            observations.request(record())
            deadline = time.monotonic() + 2
            while observations.pending is not None and time.monotonic() < deadline:
                observations.poll()
                time.sleep(0.005)
        self.assertIsNone(observations.pending)
        self.assertIn("Docker offline", observations.snapshots["414"])

    def test_single_release_result_waits_for_acknowledgement(self):
        from scripts.msandbox.models import ReleaseResult

        item = record()
        with (
            mock.patch(
                "scripts.msandbox.wizard.exited_agent_output", return_value=None
            ),
            mock.patch(
                "scripts.msandbox.wizard._session_menu_title", return_value="Session"
            ),
            mock.patch("scripts.msandbox.wizard.choose", return_value=True),
            mock.patch(
                "scripts.msandbox.wizard.release_session",
                return_value=ReleaseResult(True, "released"),
            ),
            mock.patch("scripts.msandbox.wizard.reconcile_session", return_value=item),
            mock.patch("scripts.msandbox.wizard._acknowledge") as acknowledge,
        ):
            _open_session(
                item,
                reader=lambda _: "",
                output=io.StringIO(),
                initial_action="release",
            )
        acknowledge.assert_called_once()

    def test_single_action_preserves_dead_pane_until_confirmed(self):
        item = record()
        with (
            mock.patch(
                "scripts.msandbox.wizard.exited_agent_output",
                return_value="failed login",
            ),
            mock.patch(
                "scripts.msandbox.wizard._session_menu_title", return_value="Session"
            ),
            mock.patch("scripts.msandbox.wizard.choose", return_value="back"),
            mock.patch("scripts.msandbox.wizard.start_session") as start,
        ):
            _open_session(
                item, reader=lambda _: "", output=io.StringIO(), initial_action="open"
            )
        start.assert_not_called()

    def test_tty_entry_and_classic_override(self):
        with (
            mock.patch(
                "scripts.msandbox.wizard._can_use_terminal_menu", return_value=True
            ),
            mock.patch(
                "scripts.msandbox.dashboard.run_dashboard", return_value=0
            ) as dashboard,
            mock.patch.dict(os.environ, {"MSANDBOX_UI": "dashboard"}),
        ):
            self.assertEqual(run_wizard(Path("/repo")), 0)
            dashboard.assert_called_once()
        with (
            mock.patch(
                "scripts.msandbox.wizard._can_use_terminal_menu", return_value=True
            ),
            mock.patch("scripts.msandbox.dashboard.run_dashboard") as dashboard,
            mock.patch("scripts.msandbox.wizard.list_sessions", return_value=[]),
            mock.patch("scripts.msandbox.wizard.choose", return_value=("exit", None)),
            mock.patch.dict(os.environ, {"MSANDBOX_UI": "classic"}),
        ):
            self.assertEqual(run_wizard(Path("/repo")), 0)
            dashboard.assert_not_called()

    def test_real_pty_quit_and_resize_restore_terminal(self):
        import fcntl

        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 100, 0, 0))
        script = (
            "from scripts.msandbox.dashboard import _terminal_screen, Observations; "
            "from scripts.msandbox.dashboard_view import ViewState; "
            "_terminal_screen([], ViewState(), Observations())"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        output = b""
        try:
            deadline = time.monotonic() + 5
            while b"Matcha Sandbox" not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 65536)
            self.assertIn(b"Matcha Sandbox", output)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 10, 50, 0, 0))
            process.send_signal(signal.SIGWINCH)
            os.write(master, b"q")
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 65536)
            self.assertEqual(process.wait(timeout=5), 0)
            after = termios.tcgetattr(slave)
            # macOS sets its transient "retype pending input" flag when
            # canonical mode is restored; it is not a changed input mode.
            after[3] &= ~getattr(termios, "PENDIN", 0)
            before[3] &= ~getattr(termios, "PENDIN", 0)
            self.assertEqual(after, before)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
