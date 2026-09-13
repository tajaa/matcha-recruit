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
from types import SimpleNamespace
from unittest import mock

from scripts.msandbox.dashboard import (
    LocalDetails,
    Observations,
    _screen,
    run_dashboard,
    session_rows,
)
from scripts.msandbox.dashboard_view import (
    TABS,
    Row,
    SidebarEntry,
    ViewState,
    build_layout,
    sidebar_entries,
)
from scripts.msandbox.autopr_ui import live_entry
from scripts.msandbox.inspection import Snapshot
from scripts.msandbox.models import (
    CapabilityReport,
    CapabilityResult,
    SessionRecord,
    ValidationReference,
    port_lines,
)
from scripts.msandbox.wizard import _perform_session_action, run_wizard


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


def autopr_run(status="running", *, alive=True, run_id="r1", title="Add pricing"):
    return SimpleNamespace(
        id=run_id,
        status=status,
        title=title,
        model="gpt-5.6-sol",
        effort="medium",
        workflow_id="34726444986",
        updated_at=time.time() - 245,
        supervisor_pid=os.getpid() if alive else 0,
        task_id="bbbb0000-0000-4000-8000-000000000002",
        pr_number=None,
        branch="bot/task-bbbb0000",
        workspace="/tmp/ws",
        error="",
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
    def test_autopr_tab_opens_without_an_independent_session(self):
        with mock.patch("scripts.msandbox.dashboard.AutoPRFeed") as feed:
            feed.return_value.runs = []
            feed.return_value.error = ""
            result, state, window = self.screen(["7", "q"], records=[])
        self.assertEqual(result, "exit")
        self.assertEqual(state.tab, 6)
        self.assertIn(
            "AutoPR activity & handoff", " ".join(item[2] for item in window.drawn)
        )
        self.assertIn("AutoPR", TABS)

    def screen(self, keys, state=None, records=None, mouse=None, runs=None):
        state = state or ViewState(session_id="414")
        window = Window(keys)
        observations = Observations()
        details = LocalDetails()
        # The sidebar row means the feed is read on every frame, not only on
        # the AutoPR tab. Stub it so these tests never depend on whatever runs
        # happen to be on the developer's machine.
        feed = mock.Mock()
        feed.runs = list(runs or [])
        feed.activity = ""
        feed.activity_id = None
        feed.error = ""
        feed.cards = []
        feed.queue_note = ""
        with (
            mock.patch("curses.curs_set"),
            mock.patch("curses.mousemask"),
            mock.patch("curses.has_colors", return_value=False),
            mock.patch("curses.getmouse", return_value=mouse),
            mock.patch("scripts.msandbox.dashboard.AutoPRFeed", return_value=feed),
            mock.patch.object(observations, "request"),
            mock.patch.object(details, "ensure"),
        ):
            result = _screen(
                window,
                [record()] if records is None else records,
                state,
                observations,
                details,
            )
        return result, state, window

    def test_live_autopr_run_leads_the_sidebar_and_history_does_not(self):
        entries = sidebar_entries(
            [record()], live_entry(SimpleNamespace(runs=[autopr_run()]))
        )
        # State leads: the sidebar clips from the right, so a long card title
        # must not push the badge off the row.
        self.assertTrue(entries[0].label.startswith("AutoPR ● running"))
        self.assertEqual(entries[0].action, "autopr-live:r1")
        self.assertEqual(entries[0].detail, "Add pricing")
        self.assertEqual(entries[1].session_id, "414")
        # A finished run is history: it belongs on the AutoPR tab, not next to
        # the sessions, or the sidebar grows a row nobody can act on.
        for status in ("needs_attention", "failed", "completed", "superseded"):
            self.assertIsNone(live_entry(SimpleNamespace(runs=[autopr_run(status)])))

    def test_autopr_row_labels_each_state_it_can_be_acted_on_in(self):
        taking_over = live_entry(SimpleNamespace(runs=[autopr_run("pausing")]))
        self.assertIn("taking over", taking_over.label)
        self.assertEqual(taking_over.hint, "")
        yours = live_entry(SimpleNamespace(runs=[autopr_run("manual")]))
        self.assertIn("◆ yours", yours.label)
        self.assertIn("hand back", yours.hint)

    def test_enter_on_the_autopr_row_opens_that_run_live(self):
        state = ViewState(session_id="414")
        _, state, _ = self.screen(["\n", "q"], state, [record()], runs=[autopr_run()])
        self.assertEqual(state.tab, 6)
        self.assertEqual(state.autopr_id, "r1")
        self.assertEqual(state.region, 2)

    def test_escape_takes_over_only_a_working_run_on_the_autopr_tab(self):
        # _screen hands the verb up; run_dashboard is what calls manage().
        result, _, _ = self.screen(
            ["7", "\x1b"],
            ViewState(session_id="414", autopr_id="r1"),
            [record()],
            runs=[autopr_run()],
        )
        self.assertEqual(result, "autopr:take:r1")

    def test_escape_still_just_returns_to_the_sidebar_everywhere_else(self):
        # Wrong tab, dead supervisor, and a run that is not working: Esc is the
        # key people mash to back out, so it must not stop anything here.
        for keys, runs in (
            (["\x1b", "q"], [autopr_run()]),
            (["7", "\x1b", "q"], [autopr_run(alive=False)]),
            (["7", "\x1b", "q"], [autopr_run("manual")]),
        ):
            result, state, _ = self.screen(
                keys, ViewState(session_id="414", autopr_id="r1"), [record()], runs=runs
            )
            self.assertEqual(result, "exit")
            self.assertEqual(state.region, 0)

    def test_h_hands_back_only_a_run_this_operator_owns(self):
        result, _, _ = self.screen(
            ["7", "h"],
            ViewState(session_id="414", autopr_id="r1"),
            [record()],
            runs=[autopr_run("manual")],
        )
        self.assertEqual(result, "autopr:return:r1")
        result, state, _ = self.screen(
            ["7", "h", "q"],
            ViewState(session_id="414", autopr_id="r1"),
            [record()],
            runs=[autopr_run()],
        )
        self.assertEqual(result, "exit")
        self.assertIn("taken over", state.notice)

    def test_sidebar_clamps_when_the_autopr_row_disappears_mid_frame(self):
        # A run ending while the operator sits on its row must not leave the
        # cursor pointing one past the end, or Enter acts on the wrong entry.
        records = [record(str(i)) for i in range(3)]
        with_run = sidebar_entries(records, live_entry(SimpleNamespace(runs=[autopr_run()])))
        without = sidebar_entries(records, None)
        self.assertEqual(len(with_run), len(without) + 1)
        entry = live_entry(SimpleNamespace(runs=[autopr_run()]))
        state = ViewState(session_id="0", sidebar=len(with_run) - 1)
        build_layout(records, state, [], 100, 24, entry)
        self.assertEqual(state.sidebar, len(with_run) - 1)
        state.sidebar = len(with_run) - 1
        build_layout(records, state, [], 100, 24, None)
        self.assertEqual(state.sidebar, len(without) - 1)

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

    def test_small_layout_clamps_removed_sidebar_entries(self):
        state = ViewState(session_id="414", sidebar=100)
        window = Window(["\n"], size=(10, 50))
        details = LocalDetails()
        with (
            mock.patch("curses.curs_set"),
            mock.patch("curses.mousemask"),
            mock.patch("curses.has_colors", return_value=False),
            mock.patch.object(details, "ensure"),
        ):
            result = _screen(window, [record()], state, Observations(), details)
        self.assertEqual(result, "exit")
        self.assertEqual(state.sidebar, 5)

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
        leaked = CapabilityReport(
            1,
            item.id,
            (
                CapabilityResult(
                    "prod_admin", "Production admin/secrets", "available", "reachable"
                ),
            ),
            "now",
        )
        risk_rows = session_rows(item, 2, observations, {"report": leaked})
        self.assertTrue(any(row.text.startswith("ATTENTION:") for row in risk_rows))
        leak_row = next(
            row for row in risk_rows if "Production admin/secrets" in row.text
        )
        self.assertEqual(leak_row.tone, "warning")
        self.assertTrue(leak_row.text.startswith("LEAK"))
        item.last_validation = ValidationReference(
            "pr", "abc", "xyz", "pass", "/report", "now"
        )
        self.assertIn(
            "Historical result",
            "\n".join(r.text for r in session_rows(item, 4, observations, {})),
        )

    def test_local_reads_are_async_bounded_and_tab_specific(self):
        details = LocalDetails()
        release = threading.Event()
        started = threading.Event()

        def report(_):
            started.set()
            release.wait(2)
            raise TypeError("bad report")

        with (
            mock.patch("scripts.msandbox.dashboard.load_report", side_effect=report),
            mock.patch(
                "scripts.msandbox.dashboard.list_files", return_value=[]
            ) as files,
        ):
            before = time.monotonic()
            details.ensure(record(), 2)
            details.ensure(record(), 3)
            self.assertLess(time.monotonic() - before, 0.1)
            self.assertTrue(started.wait(1))
            files.assert_not_called()
            release.set()
            deadline = time.monotonic() + 2
            while details.pending and time.monotonic() < deadline:
                details.poll()
                time.sleep(0.005)
        current = details.for_record(record())
        self.assertEqual(current["files"], [])
        self.assertIn("bad report", current["errors"][0])

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

    def test_refresh_queues_behind_another_session_probe(self):
        observations = Observations()
        observations.snapshots["a"] = Snapshot("old", None, ())
        first = threading.Event()
        release = threading.Event()

        def inspect(item):
            if item.id == "b":
                first.set()
                release.wait(2)
            return Snapshot(item.id, None, ())

        with mock.patch(
            "scripts.msandbox.dashboard.inspect_session", side_effect=inspect
        ):
            observations.request(record("b"))
            self.assertTrue(first.wait(1))
            observations.request(record("a"))
            self.assertNotIn("a", observations.snapshots)
            self.assertTrue(observations.is_pending("a"))
            release.set()
            deadline = time.monotonic() + 2
            while (
                observations.pending or observations.queued
            ) and time.monotonic() < deadline:
                observations.poll()
                time.sleep(0.005)
        self.assertEqual(observations.snapshots["a"].checked_at, "a")

    def test_unexpected_probe_exception_releases_queue(self):
        observations = Observations()
        with mock.patch(
            "scripts.msandbox.dashboard.inspect_session", side_effect=KeyboardInterrupt
        ):
            observations.request(record())
            deadline = time.monotonic() + 2
            while observations.pending and time.monotonic() < deadline:
                observations.poll()
                time.sleep(0.005)
        self.assertIsNone(observations.pending)
        self.assertIn("KeyboardInterrupt", observations.snapshots["414"])

    def test_shared_port_renderer_is_used_by_overview(self):
        from scripts.msandbox.models import PortSet

        item = record()
        item.ports = PortSet(18001, 15174, 15191, 15201, 18080)
        expected = port_lines(item.ports)
        rendered = {row.text for row in session_rows(item, 0, Observations(), {})}
        self.assertTrue(set(expected).issubset(rendered))

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
            mock.patch(
                "scripts.msandbox.wizard._perform_session_action", return_value=item
            ) as action,
        ):
            self.assertEqual(run_dashboard(Path("/repo"), output=io.StringIO()), 0)
        self.assertEqual(action.call_args.args[1], "publish")

    def test_dashboard_reconciles_every_session_and_surfaces_repairs(self):
        healthy, broken = record("healthy"), record("broken")

        def reconcile(item):
            if item.id == "broken":
                raise OSError("isolated git unavailable")
            item.phase = "stopped"
            return item

        def screen(records, state, _observations, _details):
            self.assertEqual([item.id for item in records], ["broken", "healthy"])
            self.assertEqual(records[1].phase, "stopped")
            self.assertIn("broken: isolated git unavailable", state.notice)
            return "exit"

        with (
            mock.patch(
                "scripts.msandbox.dashboard.list_sessions",
                return_value=[healthy, broken],
            ),
            mock.patch(
                "scripts.msandbox.sessions.reconcile_session", side_effect=reconcile
            ),
            mock.patch(
                "scripts.msandbox.dashboard._terminal_screen", side_effect=screen
            ),
        ):
            self.assertEqual(run_dashboard(Path("/repo"), output=io.StringIO()), 0)

    def test_sidebar_is_rederived_when_session_order_changes(self):
        old, selected, new = record("old"), record("selected"), record("new")
        calls = 0

        def screen(records, state, _observations, _details):
            nonlocal calls
            calls += 1
            if calls == 1:
                self.assertEqual(state.session_id, "selected")
                self.assertEqual(state.sidebar, 0)
                return "reload"
            self.assertEqual([item.id for item in records], ["new", "selected", "old"])
            self.assertEqual(state.session_id, "selected")
            self.assertEqual(state.sidebar, 1)
            return "exit"

        with (
            mock.patch(
                "scripts.msandbox.dashboard.list_sessions",
                side_effect=[[old, selected], [old, selected, new]],
            ),
            mock.patch(
                "scripts.msandbox.sessions.reconcile_session",
                side_effect=lambda item: item,
            ),
            mock.patch(
                "scripts.msandbox.dashboard.load_session", return_value=selected
            ),
            mock.patch(
                "scripts.msandbox.dashboard._terminal_screen", side_effect=screen
            ),
            mock.patch.object(Observations, "request"),
        ):
            self.assertEqual(run_dashboard(Path("/repo"), output=io.StringIO()), 0)

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
                "scripts.msandbox.wizard._perform_session_action",
                side_effect=OSError("offline"),
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
                side_effect=[curses.error(), "exit"],
            ),
        ):
            self.assertEqual(run_dashboard(Path("/repo"), output=io.StringIO()), 0)
        with (
            mock.patch("scripts.msandbox.dashboard.list_sessions", return_value=[]),
            mock.patch(
                "scripts.msandbox.dashboard._terminal_screen",
                side_effect=[curses.error(), curses.error()],
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

    def test_interrupt_outside_key_read_reopens_dashboard(self):
        with (
            mock.patch("scripts.msandbox.dashboard.list_sessions", return_value=[]),
            mock.patch(
                "scripts.msandbox.dashboard._terminal_screen",
                side_effect=[KeyboardInterrupt(), "exit"],
            ),
        ):
            self.assertEqual(run_dashboard(Path("/repo"), output=io.StringIO()), 0)

    def test_single_release_result_waits_for_acknowledgement(self):
        from scripts.msandbox.models import ReleaseResult

        item = record()
        with (
            mock.patch("scripts.msandbox.wizard.choose", return_value=True),
            mock.patch(
                "scripts.msandbox.wizard.release_session",
                return_value=ReleaseResult(True, "released"),
            ),
            mock.patch("scripts.msandbox.wizard.reconcile_session", return_value=item),
            mock.patch("scripts.msandbox.wizard._acknowledge") as acknowledge,
        ):
            _perform_session_action(
                item, "release", reader=lambda _: "", output=io.StringIO()
            )
        acknowledge.assert_called_once()

    def test_single_action_preserves_dead_pane_until_confirmed(self):
        item = record()
        with (
            mock.patch(
                "scripts.msandbox.wizard.exited_agent_output",
                return_value="failed login",
            ),
            mock.patch("scripts.msandbox.wizard.choose", return_value="back"),
            mock.patch("scripts.msandbox.wizard.start_session") as start,
        ):
            _perform_session_action(
                item, "open", reader=lambda _: "", output=io.StringIO()
            )
        start.assert_not_called()

    def test_single_action_does_not_build_the_classic_menu(self):
        item = record()
        with (
            mock.patch("scripts.msandbox.wizard.exited_agent_output") as exited,
            mock.patch("scripts.msandbox.wizard._session_menu_title") as title,
            mock.patch("scripts.msandbox.wizard.stop_session"),
            mock.patch("scripts.msandbox.wizard.reconcile_session", return_value=item),
        ):
            self.assertIs(
                _perform_session_action(
                    item, "stop", reader=lambda _: "", output=io.StringIO()
                ),
                item,
            )
        exited.assert_not_called()
        title.assert_not_called()

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
