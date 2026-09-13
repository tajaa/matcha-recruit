from __future__ import annotations

import io
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from unittest import mock

from scripts.msandbox.agent_adapters import (
    AgentError,
    deliver_attachments,
    ensure_agent_pane_controls,
    exited_agent_output,
)
from scripts.msandbox.cli import run as run_cli
from scripts.msandbox.docker_runtime import compose_command, session_home
from scripts.msandbox.files import SandboxFile, export_file, list_files, read_file
from scripts.msandbox.git_worktrees import dirty_fingerprint
from scripts.msandbox.inspection import PROBE, Snapshot, inspect_session
from scripts.msandbox.manager import manage
from scripts.msandbox.models import Attachment, SessionSpec
from scripts.msandbox.publication import (
    PublicationDraft,
    apply_draft,
    generate_copy,
    load_draft,
    save_draft,
    validate_copy,
)
from scripts.msandbox.sessions import (
    create_session,
    reconcile_session,
    release_session,
    start_session,
    submit_session,
    switch_session,
)
from scripts.msandbox.state import load_session, save_session
from scripts.msandbox.terminal_ui import clip, frame, mouse_key, plain
from scripts.msandbox.tool_actions import tool_action
from scripts.msandbox.wizard import _open_session
from scripts.tests.test_msandbox_v2 import MsandboxTestCase, git


class ManagerTests(MsandboxTestCase):
    def test_submenu_load_failure_has_a_back_choice(self):
        with (
            mock.patch("scripts.msandbox.manager.list_files", side_effect=OSError("offline")),
            mock.patch("scripts.msandbox.wizard.choose", return_value=False) as choose,
        ):
            manage("files", self.record(), reader=lambda _: "", output=io.StringIO())
        self.assertEqual(choose.call_args.args[1][0], ("Back", False))

    def test_frame_empty_title_and_sixth_line_notice(self):
        screen, _ = frame("", ["Back"], 0, 100, 24)
        self.assertIn("Sandbox", screen)
        screen, _ = frame("one\ntwo\nthree\nfour\nfive\nHarness exited", ["Back"], 0, 100, 24)
        self.assertIn("Harness exited", screen)

    def test_truncated_mouse_report_does_not_block(self):
        from scripts.msandbox.wizard import _read_terminal_key

        read, write = os.pipe()
        try:
            os.write(write, b"\x1b[M")
            before = time.monotonic()
            self.assertEqual(_read_terminal_key(read), "ignore")
            self.assertLess(time.monotonic() - before, 0.5)
        finally:
            os.close(read)
            os.close(write)

    def test_validation_back_does_not_acknowledge(self):
        from scripts.msandbox.wizard import _run_validation

        reader = mock.Mock()
        with mock.patch("scripts.msandbox.wizard.choose", return_value=None):
            _run_validation(self.record(), reader=reader, output=io.StringIO())
        reader.assert_not_called()

    def test_unconfigured_probe_never_connects_to_loopback(self):
        namespace = {}
        with (
            mock.patch("socket.create_connection") as connect,
            mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1)),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            exec(PROBE, namespace)  # noqa: S102 — execute the fixed probe with network mocked
            connect.reset_mock()
            for raw in ("", "postgresql:///db", "redis://", "localhost:5432"):
                self.assertEqual(namespace["endpoint"]("Database", raw), ["Database", False])
            connect.assert_not_called()

    def test_binary_preview_rejects_pdf_without_nuls_and_invalid_utf8(self):
        from scripts.msandbox.files import text_preview

        item = SandboxFile(self.root, Path("report.pdf"), "/report.pdf", 100)
        self.assertIsNone(text_preview(item, b"%PDF-1.4\nplain header"))
        item = replace(item, relative=Path("unknown"))
        self.assertIsNone(text_preview(item, b"%PDF-1.4\nplain header"))
        self.assertIsNone(text_preview(item, b"\xffbad"))
        self.assertEqual(text_preview(item, b"valid text"), "valid text")

    def test_export_streams_validated_descriptor_without_read_file(self):
        record = self.record()
        path = record.worktree / ".msandbox/outputs/report.txt"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"abc" * 400000)
        item = list_files(record)[0]
        with mock.patch("scripts.msandbox.files.read_file", side_effect=AssertionError("buffered")):
            exported = export_file(record, item)
        self.assertEqual(exported.read_bytes(), path.read_bytes())

    def test_release_finalizes_despite_local_branch_cleanup_failure(self):
        record = create_session(self.repo, SessionSpec("release-warning", "codex", "main", start=False))
        record.managed_local_branch = True
        save_session(record)
        git(record.worktree, "push", "origin", f"HEAD:refs/heads/{record.target_branch}")
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.sessions.remove_container_project"),
            mock.patch("scripts.msandbox.sessions.remove_managed_local_branch", return_value="ref moved"),
        ):
            result = release_session(record)
        self.assertTrue(result.released)
        self.assertIn("local branch retained", result.reason)
        self.assertEqual(load_session(record.id).phase, "released")
        self.assertIsNone(load_session(record.id).ports)
        from scripts.msandbox.git_worktrees import session_git_dir
        self.assertFalse(session_git_dir(record.id).exists())

    def test_reconcile_skips_exclusion_repair(self):
        record = create_session(self.repo, SessionSpec("redraw", "codex", "main", start=False))
        with (
            mock.patch("scripts.msandbox.sessions.exclude_generated_outputs") as repair,
            mock.patch("scripts.msandbox.sessions.ensure_agent_pane_controls"),
            mock.patch("scripts.msandbox.sessions.container_running", return_value=False),
        ):
            reconcile_session(record)
        repair.assert_not_called()

    def test_picker_keeps_healthy_sessions_when_one_reconcile_fails(self):
        from scripts.msandbox.wizard import run_wizard

        broken, healthy = self.record(), self.record("session-2")
        with (
            mock.patch("scripts.msandbox.wizard.list_sessions", return_value=[broken, healthy]),
            mock.patch("scripts.msandbox.wizard.reconcile_session", side_effect=[RuntimeError("broken git"), healthy]),
            mock.patch("scripts.msandbox.wizard.choose", return_value=("exit", None)) as choose,
        ):
            run_wizard(self.repo, reader=lambda _: "", output=io.StringIO())
        self.assertIn("broken git", choose.call_args.args[0])
        self.assertIn(("session", healthy.id), [value for _, value in choose.call_args.args[1]])

    def test_tracked_ignore_leaves_shared_exclude_untouched(self):
        (self.repo / ".gitignore").write_text(".msandbox/outputs/\n")
        git(self.repo, "add", ".gitignore")
        git(self.repo, "commit", "-m", "ignore outputs")
        exclude = self.repo / ".git/info/exclude"
        before = exclude.read_bytes()
        create_session(self.repo, SessionSpec("ignored", "codex", "main", start=False))
        self.assertEqual(exclude.read_bytes(), before)

    def _check_pager_exit(self, key):
        if not shutil.which("less"):
            self.skipTest("less unavailable")
        code = """
import sys, termios
from scripts.msandbox.manager import show
before = termios.tcgetattr(0)
try:
    show('SHORT RESULT', reader=input, output=sys.stdout)
except KeyboardInterrupt:
    pass
after = termios.tcgetattr(0)
# macOS sets PENDIN when tcsetattr requests reprocessing pending input.
before[3] &= ~getattr(termios, 'PENDIN', 0)
after[3] &= ~getattr(termios, 'PENDIN', 0)
print('RESTORED=' + str(after == before), flush=True)
print('ANSWER=' + input('NEXT PROMPT: '), flush=True)
"""
        pid, master = pty.fork()
        if pid == 0:
            os.execve(
                sys.executable,
                [sys.executable, "-c", code],
                {**os.environ, "TERM": "xterm", "LESS": "-F"},
            )
        output = b""
        try:
            deadline = time.monotonic() + 8
            for marker, response in (
                (b"SHORT RESULT", key),
                (b"NEXT PROMPT:", b"hello\n"),
                (b"ANSWER=hello", None),
            ):
                while marker not in output and time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        output += os.read(master, 65536)
                self.assertIn(marker, output)
                if marker == b"SHORT RESULT":
                    # The short report must wait even when LESS=-F is inherited.
                    time.sleep(0.2)
                    if select.select([master], [], [], 0)[0]:
                        output += os.read(master, 65536)
                    self.assertNotIn(b"RESTORED=", output)
                if response:
                    os.write(master, response)
            self.assertIn(b"RESTORED=True", output)
        finally:
            import signal

            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
            os.close(master)

    def test_short_pager_waits_for_quit(self):
        self._check_pager_exit(b"q")

    def test_pager_interrupt_restores_canonical_input(self):
        self._check_pager_exit(b"\x03")

    def test_real_terminal_mouse_selects_action_and_restores_screen(self):
        master, slave = pty.openpty()
        code = "from scripts.msandbox.wizard import choose; print('RESULT=' + choose('Sandbox', [('First', 'one'), ('Second', 'two'), ('Back', 'back')]))"
        child = subprocess.Popen(
            [sys.executable, "-c", code], stdin=slave, stdout=slave, stderr=slave
        )
        os.close(slave)
        output = b""
        sent = False
        deadline = time.monotonic() + 5
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        break
                    output += data
                    if b"Esc / q" in output and not sent:
                        os.write(master, b"\x1b[<0;5;4M")
                        sent = True
                if child.poll() is not None:
                    break
            child.wait(timeout=2)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            os.close(master)
        self.assertIn(b"RESULT=two", output)
        self.assertIn(b"\x1b[?1000l", output)

    def test_luna_is_isolated_pinned_and_cleans_up_after_failure(self):
        auth = self.root / ".codex/auth.json"
        auth.parent.mkdir()
        auth.write_text("{}")
        with (
            mock.patch(
                "scripts.msandbox.publication.Path.home", return_value=self.root
            ),
            mock.patch(
                "scripts.msandbox.publication.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, "", "failed"),
            ) as run,
            self.assertRaises(RuntimeError),
        ):
            generate_copy("test-image", {"changes": "menu"})
        command = run.call_args_list[0].args[0]
        self.assertIn("gpt-5.6-luna", command)
        self.assertIn('model_reasoning_effort="high"', command)
        self.assertIn("--read-only", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[command.index("-a") + 1], "never")
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        disabled = {
            command[i + 1] for i, arg in enumerate(command) if arg == "--disable"
        }
        self.assertTrue(
            {
                "shell_tool",
                "unified_exec",
                "browser_use",
                "computer_use",
                "code_mode_host",
                "apps",
                "plugins",
                "multi_agent",
                "multi_agent_v2",
                "image_generation",
                "hooks",
            }
            <= disabled
        )
        self.assertEqual(sum(str(arg).startswith("type=bind") for arg in command), 1)
        name = command[command.index("--name") + 1]
        self.assertEqual(run.call_args_list[-1].args[0], ["docker", "rm", "-f", name])

    def test_draft_survives_returning_to_other_screens(self):
        record = self.record()
        save_session(record)
        draft = PublicationDraft(
            "codex/new-menu",
            "feat: add menu",
            "Add menu",
            "Tests pending.",
            record.base_sha,
            "clean",
        )
        save_draft(record, draft)
        self.assertEqual(load_draft(record), draft)

    def test_terminal_viewport_keeps_last_action_and_footer_visible(self):
        text, targets = frame(
            "Sandbox\nbranch",
            [f"Session {i} — detail {i}" for i in range(300)],
            299,
            80,
            24,
        )
        self.assertLessEqual(len(text.splitlines()), 24)
        self.assertIn(299, targets.values())
        self.assertIn("detail 299", text)
        self.assertIn("Esc / q", text)

    def test_mouse_and_unicode_do_not_corrupt_terminal(self):
        self.assertEqual(mouse_key(b"\x1b[<0;12;4M"), "click:12:4")
        self.assertEqual(mouse_key(b"\x1b[<65;12;4M"), "down")
        self.assertEqual(mouse_key(b"\x1b[M q1"), "ignore")
        self.assertEqual(clip("猫猫a", 3), "猫")
        self.assertNotIn("\x1b", plain("file\x1b]52;c;secret\a"))

    def test_legacy_mouse_payload_cannot_become_navigation_keys(self):
        from scripts.msandbox.wizard import _read_terminal_key

        read_fd, write_fd = os.pipe()
        try:
            # X10 button + column + row bytes include q and 1, both active keys.
            os.write(write_fd, b"\x1b[M q1\n")
            self.assertEqual(_read_terminal_key(read_fd), "ignore")
            self.assertEqual(_read_terminal_key(read_fd), "enter")
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_stopped_inspection_never_executes_or_starts_container(self):
        record = self.record()

        def run(argv, **kwargs):
            if argv[:2] == ["docker", "ps"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    json.dumps(
                        {
                            "Names": "workspace",
                            "State": "exited",
                            "Status": "Exited",
                            "ID": "abc",
                        }
                    ),
                    "",
                )
            return subprocess.CompletedProcess(argv, 1, "", "")

        with mock.patch("scripts.msandbox.inspection.run", side_effect=run) as calls:
            snapshot = inspect_session(record)
        self.assertIsNone(snapshot.container_id)
        self.assertTrue(any("not measured" in line for line in snapshot.lines))
        self.assertFalse(
            any(
                "exec" in call.args[0] or "start" in call.args[0]
                for call in calls.call_args_list
            )
        )
        docker_ps = calls.call_args_list[0].args[0]
        self.assertIn("label=com.docker.compose.service=workspace", docker_ps)

    def test_malformed_probe_json_is_an_unreliable_snapshot_not_a_crash(self):
        def run(argv, **kwargs):
            if argv[:2] == ["docker", "ps"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    json.dumps(
                        {
                            "Names": "session-workspace-1",
                            "State": "running",
                            "Status": "Up",
                            "ID": "workspace-id",
                        }
                    ),
                    "",
                )
            if argv[:2] == ["docker", "exec"]:
                return subprocess.CompletedProcess(argv, 0, "null\n", "")
            return subprocess.CompletedProcess(argv, 1, "", "")

        with mock.patch("scripts.msandbox.inspection.run", side_effect=run):
            snapshot = inspect_session(self.record())
        self.assertFalse(snapshot.reliable)
        self.assertEqual(snapshot.container_id, "workspace-id")
        self.assertIn("Some probes unavailable", snapshot.lines[-1])

    def test_docker_error_is_unknown_not_false_health(self):
        with mock.patch(
            "scripts.msandbox.inspection.run",
            return_value=subprocess.CompletedProcess([], 1, "", "secret"),
        ):
            snapshot = inspect_session(self.record())
        self.assertIn("unknown", snapshot.lines[0])
        self.assertNotIn("secret", str(snapshot))
        self.assertFalse(snapshot.reliable)
        self.assertEqual(snapshot.errors, ("docker_unavailable",))

    def test_session_ps_json_is_structured_and_unreliable_exits_nonzero(self):
        record = self.record()
        save_session(record)
        snapshot = Snapshot(
            "2026-09-09T00:00:00+00:00",
            None,
            ("Docker unavailable; live state is unknown.",),
            False,
            errors=("docker_unavailable",),
        )
        output = io.StringIO()
        with (
            mock.patch(
                "scripts.msandbox.inspection.inspect_session", return_value=snapshot
            ),
            mock.patch("sys.stdout", output),
        ):
            status = run_cli(["--repo", str(self.repo), "session", "ps", record.id, "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["reliable"])
        self.assertEqual(payload["errors"], ["docker_unavailable"])
        self.assertNotIn("lines", payload)

    def test_session_inspection_inherits_documented_host_endpoints(self):
        command = compose_command(self.record(), "config")
        files = [command[index + 1] for index, value in enumerate(command) if value == "--file"]
        self.assertTrue(files[0].endswith("docker-compose.sandbox.yml"))
        self.assertTrue(files[1].endswith("docker-compose.sandbox-session.yml"))
        self.assertIn("HOST_DEV_BACKEND_URL", PROBE)
        self.assertIn("HOST_DEV_FRONTEND_URL", PROBE)

    def test_files_skip_symlinks_and_export_survives_source_removal(self):
        record = self.record()
        directory = record.worktree / ".msandbox/outputs"
        directory.mkdir(parents=True)
        (directory / "output.txt").write_text("generated content")
        (directory / "unsafe").symlink_to(self.repo / "README.md")
        files = list_files(record)
        self.assertEqual(len(files), 1)
        self.assertEqual(read_file(files[0], 100), b"generated content")
        exported = export_file(record, files[0])
        (directory / "output.txt").unlink()
        self.assertEqual(exported.read_text(), "generated content")

    def test_control_character_filenames_are_hidden_and_cannot_be_delivered(self):
        record = self.record()
        directory = record.worktree / ".msandbox/outputs"
        directory.mkdir(parents=True)
        (directory / "safe.txt").write_text("safe")
        (directory / "report\nq.txt").write_text("unsafe")
        self.assertEqual([item.relative.name for item in list_files(record)], ["safe.txt"])

        unsafe = Attachment(
            "",
            "report.txt",
            "text/plain",
            "",
            6,
            directory / "report\nq.txt",
            Path("/workspace/.msandbox/outputs/report\nq.txt"),
        )
        with (
            mock.patch("scripts.msandbox.agent_adapters.tmux_running") as running,
            mock.patch("scripts.msandbox.agent_adapters.subprocess.run") as run,
            self.assertRaisesRegex(AgentError, "control characters"),
        ):
            deliver_attachments(record, [unsafe])
        running.assert_not_called()
        run.assert_not_called()

    def test_tmux_attachment_delivery_uses_bracketed_paste(self):
        record = self.record()
        attachment = Attachment(
            "",
            "safe.txt",
            "text/plain",
            "",
            4,
            record.worktree / "safe.txt",
            Path("/workspace/.msandbox/outputs/safe.txt"),
        )
        with (
            mock.patch(
                "scripts.msandbox.agent_adapters.tmux_running", return_value=True
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as run,
        ):
            deliver_attachments(record, [attachment])
        self.assertEqual(
            run.call_args_list[-1].args[0],
            ["tmux", "paste-buffer", "-p", "-t", record.tmux_session],
        )

    def test_file_export_rechecks_ancestor_symlinks(self):
        record = self.record()
        directory = record.worktree / ".msandbox"
        directory.mkdir()
        directory.joinpath("outputs").symlink_to(self.repo, target_is_directory=True)
        item = SandboxFile(
            directory / "outputs",
            Path("README.md"),
            "/workspace/.msandbox/outputs/README.md",
            5,
        )
        with self.assertRaises(OSError):
            read_file(item, 100)
        self.assertEqual(list_files(record), [])

    def test_existing_agent_panes_receive_exit_preservation_controls(self):
        record = self.record()
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            mock.patch("scripts.msandbox.agent_adapters._configured_panes", set()),
            mock.patch(
                "scripts.msandbox.agent_adapters._tmux_exists", return_value=True
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            ensure_agent_pane_controls(record)
            first_count = run.call_count
            ensure_agent_pane_controls(record)
            self.assertEqual(run.call_count, first_count)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any("remain-on-exit" in command for command in commands))
        self.assertTrue(any("pane-died" in command for command in commands))

    def test_exited_agent_output_reads_preserved_dead_pane(self):
        record = self.record()
        with (
            mock.patch(
                "scripts.msandbox.agent_adapters._tmux_exists", return_value=True
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.tmux_running", return_value=False
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    [], 0, "fatal: login expired\n", ""
                ),
            ),
        ):
            self.assertEqual(exited_agent_output(record), "fatal: login expired")

    def test_exited_harness_output_is_visible_before_restart(self):
        record = self.record()
        choices = iter(("harness-output", "back"))
        menus = []

        def choose(title, options, **_kwargs):
            menus.append((title, [label for label, _ in options]))
            return next(choices)

        output = io.StringIO()
        with (
            mock.patch(
                "scripts.msandbox.wizard.exited_agent_output",
                return_value="fatal: login expired",
            ),
            mock.patch("scripts.msandbox.wizard.choose", side_effect=choose),
            mock.patch(
                "scripts.msandbox.wizard.reconcile_session", return_value=record
            ),
        ):
            _open_session(record, reader=lambda _prompt: "", output=output)
        self.assertIn("fatal: login expired", output.getvalue())
        labels = [label for _, options in menus for label in options]
        self.assertTrue(any(label.startswith("View exited harness output") for label in labels))
        self.assertTrue(any(label.startswith("Restart codex") for label in labels))

    def test_start_protects_preserved_harness_output_by_default(self):
        record = self.record()
        with (
            mock.patch(
                "scripts.msandbox.sessions.exited_agent_output", return_value="failure"
            ),
            self.assertRaisesRegex(RuntimeError, "output is preserved"),
        ):
            start_session(record)

    def test_reconcile_retrofits_controls_on_existing_agent_pane(self):
        record = self.record()
        save_session(record)
        with (
            mock.patch("scripts.msandbox.sessions._ensure_isolated_git"),
            mock.patch(
                "scripts.msandbox.sessions.ensure_agent_pane_controls"
            ) as controls,
            mock.patch("scripts.msandbox.sessions.container_running", return_value=False),
        ):
            reconcile_session(record, _lock_held=True)
        controls.assert_called_once_with(record)

    def test_harness_switch_preserves_workspace_and_explicit_permissions(self):
        record = self.record()
        record.permission_mode = "autonomous"
        record.agent_session_id = "old-conversation"
        save_session(record)
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.sessions.provision_session_auth") as auth,
        ):
            switch_session(record, "claude")
        saved = load_session(record.id)
        self.assertEqual(saved.agent, "claude")
        self.assertEqual(saved.permission_mode, "autonomous")
        self.assertEqual(saved.worktree_path, record.worktree_path)
        self.assertIsNone(saved.agent_session_id)
        self.assertEqual(saved.phase, "stopped")
        auth.assert_called_once()

    def test_switch_preserves_orphaned_phase_discovered_while_stopping(self):
        record = self.record()
        record.phase = "running"
        save_session(record)

        def orphan(current, **_kwargs):
            current.phase = "orphaned"
            save_session(current)

        with (
            mock.patch("scripts.msandbox.sessions.stop_session", side_effect=orphan),
            mock.patch("scripts.msandbox.sessions.provision_session_auth") as provision,
            self.assertRaisesRegex(RuntimeError, "became orphaned"),
        ):
            switch_session(record, "claude")
        current = load_session(record.id)
        self.assertEqual(current.phase, "orphaned")
        self.assertEqual(current.agent, "codex")
        provision.assert_not_called()

    def test_harness_auth_failure_keeps_old_record(self):
        record = self.record()
        save_session(record)
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch(
                "scripts.msandbox.sessions.provision_session_auth",
                side_effect=RuntimeError("login failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            switch_session(record, "claude")
        self.assertEqual(load_session(record.id).agent, "codex")

    def test_switch_removes_only_other_logins_and_reseeds_on_return(self):
        from scripts.msandbox.session_auth import AGENT_AUTH_FILES

        record = self.record()
        save_session(record)
        home = session_home(record)
        for paths in AGENT_AUTH_FILES.values():
            for relative in paths:
                for root in (self.root, home):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("synthetic-login")
        history = home / ".codex/history.jsonl"
        history.write_text("conversation")
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch(
                "scripts.msandbox.session_auth.Path.home", return_value=self.root
            ),
        ):
            for selected in ("claude", "opencode", "codex"):
                switch_session(record, selected)
                for agent, paths in AGENT_AUTH_FILES.items():
                    for relative in paths:
                        self.assertEqual((home / relative).exists(), agent == selected)
                self.assertEqual(history.read_text(), "conversation")

    def test_switch_save_failure_restores_previous_credentials(self):
        record = self.record()
        save_session(record)
        old = session_home(record) / ".codex/auth.json"
        old.parent.mkdir(parents=True)
        old.write_text("old-login")
        new_source = self.root / ".claude/.credentials.json"
        new_source.parent.mkdir()
        new_source.write_text("new-login")
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch(
                "scripts.msandbox.session_auth.Path.home", return_value=self.root
            ),
            mock.patch(
                "scripts.msandbox.sessions.save_session",
                side_effect=OSError("disk full"),
            ),
            self.assertRaises(OSError),
        ):
            switch_session(record, "claude")
        self.assertEqual(old.read_text(), "old-login")
        self.assertFalse((session_home(record) / ".claude/.credentials.json").exists())
        self.assertEqual(load_session(record.id).agent, "codex")

    def test_switch_refuses_credential_directory_symlink_before_removing_logins(self):
        record = self.record()
        save_session(record)
        home = session_home(record)
        old = home / ".codex/auth.json"
        old.parent.mkdir(parents=True)
        old.write_text("old-login")
        (home / ".claude").symlink_to(self.root, target_is_directory=True)
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            self.assertRaises(RuntimeError),
        ):
            switch_session(record, "claude")
        self.assertEqual(old.read_text(), "old-login")
        self.assertEqual(load_session(record.id).agent, "codex")

    def test_switch_unlinks_final_credential_symlink_without_touching_target(self):
        record = self.record()
        save_session(record)
        target = self.root / "keep-login"
        target.write_text("keep")
        old = session_home(record) / ".codex/auth.json"
        old.parent.mkdir(parents=True)
        old.symlink_to(target)
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.sessions.provision_session_auth"),
        ):
            switch_session(record, "claude")
        self.assertFalse(old.is_symlink())
        self.assertEqual(target.read_text(), "keep")

    def test_publish_without_luna_for_each_harness_and_existing_pr(self):
        for agent in ("codex", "claude", "opencode"):
            for pr in (None, 7):
                with self.subTest(agent=agent, pr=pr):
                    record = self.record()
                    record.agent, record.pr_number = agent, pr
                    with (
                        mock.patch(
                            "scripts.msandbox.manager.load_draft", return_value=None
                        ),
                        mock.patch(
                            "scripts.msandbox.wizard.choose",
                            side_effect=["submit", True],
                        ),
                        mock.patch(
                            "scripts.msandbox.manager.generate_draft"
                        ) as generate,
                        mock.patch("scripts.msandbox.manager.submit_session") as submit,
                    ):
                        submit.return_value.number = 7
                        submit.return_value.url = (
                            "https://github.com/example/test/pull/7"
                        )
                        output = io.StringIO()
                        manage("publish", record, reader=lambda _: "", output=output)
                    generate.assert_not_called()
                    submit.assert_called_once_with(
                        record, draft=True, title=record.name, body=None
                    )
                    self.assertIn("PR #7:", output.getvalue())

    def test_existing_pr_publish_confirms_copy_replacement(self):
        record = self.record()
        record.pr_number = 7
        draft = PublicationDraft(
            "codex/existing",
            "fix: existing",
            "Replacement title",
            "Replacement body",
            "head",
            "clean",
        )
        prompts = []
        answers = iter(("submit", False, None))

        def choose(title, choices, **kwargs):
            prompts.append(title)
            return next(answers)

        with (
            mock.patch("scripts.msandbox.manager.load_draft", return_value=draft),
            mock.patch("scripts.msandbox.wizard.choose", side_effect=choose),
            mock.patch(
                "scripts.msandbox.git_worktrees.current_head", return_value="head"
            ),
            mock.patch(
                "scripts.msandbox.git_worktrees.dirty_fingerprint",
                return_value="clean",
            ),
            mock.patch("scripts.msandbox.manager.submit_session") as submit,
        ):
            manage("publish", record, reader=lambda _: "", output=io.StringIO())
        submit.assert_not_called()
        self.assertTrue(
            any(
                "Existing PR #7: its title and description will be replaced" in prompt
                for prompt in prompts
            )
        )

    def test_submenu_error_stays_in_browser_menu(self):
        record = self.record()
        record.playwright = True
        save_session(record)
        choices = iter(("browser-capture", None))
        reader_prompts = []

        def reader(prompt):
            reader_prompts.append(prompt)
            return "ftp://invalid" if prompt.startswith("Page URL") else ""

        with (
            mock.patch(
                "scripts.msandbox.wizard.choose",
                side_effect=lambda *args, **kwargs: next(choices),
            ) as choose,
            mock.patch("scripts.msandbox.tool_actions.ensure_container"),
        ):
            output = io.StringIO()
            manage("browser", record, reader=reader, output=output)
        self.assertEqual(choose.call_count, 2)
        self.assertIn("still in this submenu", output.getvalue())
        self.assertIn("Enter to return", " ".join(reader_prompts))

    def test_invalid_draft_edit_keeps_other_fields_for_correction(self):
        record = self.record()
        save_session(record)
        draft = PublicationDraft(
            "codex/original",
            "fix: original",
            "Original title",
            "Body",
            "head",
            "clean",
        )
        choices = iter(("edit", "edit", None))
        reader_prompts = []

        def reader(prompt):
            reader_prompts.append(prompt)
            if prompt == "Branch [codex/original]: ":
                return "main"
            if prompt == "PR title [Original title]: ":
                return "Retained title"
            if prompt == "Commit [fix: original]: ":
                return "fix: retained"
            if prompt == "Branch [main]: ":
                return "codex/corrected"
            return ""

        with (
            mock.patch("scripts.msandbox.manager.load_draft", return_value=draft),
            mock.patch(
                "scripts.msandbox.wizard.choose",
                side_effect=lambda *args, **kwargs: next(choices),
            ),
        ):
            manage("publish", record, reader=reader, output=io.StringIO())
        saved = load_draft(record)
        self.assertEqual(saved.branch, "codex/corrected")
        self.assertEqual(saved.title, "Retained title")
        self.assertEqual(saved.commit, "fix: retained")
        self.assertIn("PR title [Retained title]: ", reader_prompts)
        self.assertIn("Commit [fix: retained]: ", reader_prompts)

    def test_branch_commit_action_discloses_workspace_stop(self):
        record = self.record()
        draft = PublicationDraft(
            "codex/apply",
            "fix: apply",
            "Apply",
            "Body",
            "head",
            "clean",
        )
        answers = iter(("apply", False, None))
        menus = []

        def choose(title, choices, **kwargs):
            menus.append((title, [label for label, _ in choices]))
            return next(answers)

        with (
            mock.patch("scripts.msandbox.manager.load_draft", return_value=draft),
            mock.patch("scripts.msandbox.wizard.choose", side_effect=choose),
            mock.patch("scripts.msandbox.publication.git", return_value="M README.md"),
        ):
            manage("publish", record, reader=lambda _: "", output=io.StringIO())
        labels = [label for _, choices in menus for label in choices]
        self.assertTrue(
            any(
                label.startswith("Create branch / commit — Stops workspace")
                for label in labels
            )
        )
        self.assertTrue(
            any("stops the running harness and workspace" in title for title, _ in menus)
        )

    def test_released_session_cannot_switch_or_launch_tools(self):
        record = self.record()
        record.phase = "released"
        save_session(record)
        with self.assertRaises(RuntimeError):
            switch_session(record, "claude")
        with self.assertRaises(RuntimeError):
            tool_action(record, "dev-start")

    def test_stopping_browser_does_not_boot_workspace(self):
        record = self.record()
        record.playwright = True
        save_session(record)
        with (
            mock.patch("scripts.msandbox.inspection.inspect_session") as inspect,
            mock.patch("scripts.msandbox.tool_actions.ensure_container") as start,
        ):
            inspect.return_value.container_id = None
            self.assertIn("already stopped", tool_action(record, "browser-stop"))
        start.assert_not_called()

    def test_stop_reports_already_stopped_when_tmux_session_is_absent(self):
        for action in ("browser-stop", "dev-stop"):
            with self.subTest(action=action):
                record = self.record()
                record.playwright = True
                record.dev = True
                save_session(record)
                snapshot = mock.Mock(reliable=True, container_id="workspace-id")
                with (
                    mock.patch(
                        "scripts.msandbox.inspection.inspect_session",
                        return_value=snapshot,
                    ),
                    mock.patch(
                        "scripts.msandbox.tool_actions.ensure_container"
                    ) as start,
                    mock.patch(
                        "scripts.msandbox.tool_actions.exec_in_session",
                        return_value=subprocess.CompletedProcess([], 1, "", ""),
                    ),
                ):
                    result = tool_action(record, action)
                self.assertIn("already stopped", result)
                start.assert_not_called()

    def test_browser_readiness_host_timeout_covers_probe_budget(self):
        record = self.record()
        record.playwright = True
        save_session(record)
        with (
            mock.patch("scripts.msandbox.tool_actions.ensure_container"),
            mock.patch(
                "scripts.msandbox.tool_actions.exec_in_session",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                ],
            ) as execute,
        ):
            self.assertIn("is ready", tool_action(record, "browser-start"))
        self.assertEqual(execute.call_args_list[1].kwargs["timeout"], 20)

    def test_browser_url_is_argument_not_shell_code(self):
        record = self.record()
        record.playwright = True
        save_session(record)
        url = "http://localhost:5174/?q=$(touch%20/tmp/wrong)"
        with (
            mock.patch("scripts.msandbox.tool_actions.ensure_container"),
            mock.patch(
                "scripts.msandbox.tool_actions.exec_in_session",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as execute,
        ):
            tool_action(record, "browser-capture", url=url)
        args = execute.call_args.args[1]
        self.assertIn(url, args)
        self.assertNotEqual(args[0], "bash")

    def test_draft_validation_rejects_ref_injection_and_multibyte_overflow(self):
        raw = {
            "branch": "codex/good-name",
            "commit": "feat: add controls",
            "title": "Add controls",
            "body": "Tests not run.",
        }
        validate_copy(raw)
        for update in (
            {"branch": "main"},
            {"branch": "codex/a..b"},
            {"title": "\x1b[31m"},
            {"commit": "猫" * 25},
        ):
            with self.assertRaises(ValueError):
                validate_copy({**raw, **update})

    def test_apply_checks_draft_fingerprint_before_git_writes(self):
        record = create_session(
            self.repo, SessionSpec("draft", "codex", "main", start=False)
        )
        head = git(record.worktree, "rev-parse", "HEAD")
        draft = PublicationDraft(
            "codex/generated-name",
            "feat: update readme",
            "Update readme",
            "Description",
            head,
            "clean",
        )
        (record.worktree / "README.md").write_text("new change")
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            self.assertRaisesRegex(RuntimeError, "changed since"),
        ):
            apply_draft(record, draft, commit=True)
        self.assertEqual(git(record.worktree, "rev-parse", "HEAD"), head)
        self.assertEqual(load_session(record.id).target_branch, "codex/draft")

    def test_apply_creates_local_branch_without_checking_it_out(self):
        record = create_session(
            self.repo, SessionSpec("draft", "codex", "main", start=False)
        )
        head = git(record.worktree, "rev-parse", "HEAD")
        draft = PublicationDraft(
            "codex/generated-name",
            "feat: update readme",
            "Update readme",
            "Description",
            head,
            "clean",
        )
        with mock.patch("scripts.msandbox.sessions.stop_session"):
            apply_draft(record, draft, commit=False)
        self.assertEqual(
            git(record.worktree, "rev-parse", "codex/generated-name"), head
        )
        self.assertEqual(
            git(record.worktree, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD"
        )
        self.assertEqual(load_session(record.id).target_branch, draft.branch)
        self.assertTrue(load_session(record.id).managed_local_branch)

    def test_release_removes_managed_local_branch_for_future_sessions(self):
        record = create_session(
            self.repo, SessionSpec("first", "codex", "main", start=False)
        )
        head = git(record.worktree, "rev-parse", "HEAD")
        draft = PublicationDraft(
            "codex/reusable",
            "fix: reusable",
            "Reusable",
            "Tests pending",
            head,
            "clean",
        )
        with mock.patch("scripts.msandbox.sessions.stop_session"):
            apply_draft(record, draft, commit=False)
        git(record.worktree, "push", "origin", f"HEAD:refs/heads/{draft.branch}")
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.sessions.remove_container_project"),
        ):
            released = release_session(record)
        self.assertTrue(released.released)
        local_ref = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{draft.branch}",
            ],
            check=False,
        )
        self.assertEqual(local_ref.returncode, 1)

        git(self.remote, "update-ref", "-d", f"refs/heads/{draft.branch}")
        next_record = create_session(
            self.repo, SessionSpec("second", "codex", "main", start=False)
        )
        next_draft = replace(
            draft,
            head=git(next_record.worktree, "rev-parse", "HEAD"),
            fingerprint="clean",
        )
        with mock.patch("scripts.msandbox.sessions.stop_session"):
            apply_draft(next_record, next_draft, commit=False)
        self.assertEqual(load_session(next_record.id).target_branch, draft.branch)

    def test_apply_adopts_safe_remote_deleted_local_branch(self):
        git(self.repo, "branch", "codex/legacy-clean", "main")
        record = create_session(
            self.repo, SessionSpec("different-name", "codex", "main", start=False)
        )
        draft = PublicationDraft(
            "codex/legacy-clean",
            "fix: reuse branch",
            "Reuse branch",
            "Tests pending",
            git(record.worktree, "rev-parse", "HEAD"),
            "clean",
        )
        with mock.patch("scripts.msandbox.sessions.stop_session"):
            apply_draft(record, draft, commit=False)
        saved = load_session(record.id)
        self.assertEqual(saved.target_branch, draft.branch)
        self.assertTrue(saved.managed_local_branch)

    def test_apply_refuses_local_branch_with_unpublished_commits(self):
        tree = git(self.repo, "rev-parse", "main^{tree}")
        parent = git(self.repo, "rev-parse", "main")
        unique = git(
            self.repo,
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            "local-only",
        )
        git(self.repo, "branch", "codex/local-only", unique)
        record = create_session(
            self.repo, SessionSpec("different-name", "codex", "main", start=False)
        )
        draft = PublicationDraft(
            "codex/local-only",
            "fix: do not overwrite",
            "Do not overwrite",
            "Tests pending",
            git(record.worktree, "rev-parse", "HEAD"),
            "clean",
        )
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            self.assertRaisesRegex(RuntimeError, "outside this session"),
        ):
            apply_draft(record, draft, commit=False)
        self.assertEqual(git(self.repo, "rev-parse", draft.branch), unique)

    def test_old_records_default_to_no_managed_local_branch(self):
        raw = self.record().to_dict()
        raw.pop("managed_local_branch")
        restored = type(self.record()).from_dict(raw)
        self.assertFalse(restored.managed_local_branch)

    def test_capability_details_use_same_report_without_refresh(self):
        record = self.record()
        with (
            mock.patch("scripts.msandbox.wizard.choose", side_effect=["view", None]),
            mock.patch("scripts.msandbox.manager.load_report", return_value=None),
            mock.patch("scripts.msandbox.manager.ensure_capability_report") as measure,
        ):
            output = io.StringIO()
            manage("tools", record, reader=lambda _: "", output=output)
        measure.assert_not_called()

    def test_second_apply_updates_local_branch_and_excludes_old_base_outputs(self):
        record = create_session(
            self.repo, SessionSpec("retry", "codex", "main", start=False)
        )
        output = record.worktree / ".msandbox/outputs/screenshot.png"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"private screenshot")
        self.assertFalse((record.worktree / ".gitignore").exists())
        for content in ("first", "second"):
            (record.worktree / "README.md").write_text(content)
            draft = PublicationDraft(
                "codex/retry",
                "fix: retry",
                "Retry",
                "Tests pending",
                git(record.worktree, "rev-parse", "HEAD"),
                dirty_fingerprint(record.worktree),
            )
            with mock.patch("scripts.msandbox.sessions.stop_session"):
                apply_draft(record, draft, commit=True)
            self.assertEqual(
                git(record.worktree, "rev-parse", draft.branch),
                git(record.worktree, "rev-parse", "HEAD"),
            )
            self.assertEqual(
                git(record.worktree, "ls-tree", "-r", "--name-only", "HEAD"),
                "README.md",
            )
            self.assertTrue(output.exists())
            self.assertEqual(git(record.worktree, "status", "--porcelain"), "")
        from scripts.msandbox.git_worktrees import session_git_dir

        self.assertEqual(
            git(
                record.worktree,
                f"--git-dir={session_git_dir(record.id)}",
                f"--work-tree={record.worktree}",
                "check-ignore",
                ".msandbox/outputs/screenshot.png",
            ),
            ".msandbox/outputs/screenshot.png",
        )

    def test_apply_refuses_already_staged_sandbox_files(self):
        record = create_session(
            self.repo, SessionSpec("staged", "codex", "main", start=False)
        )
        output = record.worktree / ".msandbox/outputs/private.txt"
        output.parent.mkdir(parents=True)
        output.write_text("private")
        git(record.worktree, "add", "--force", ".msandbox/outputs/private.txt")
        head = git(record.worktree, "rev-parse", "HEAD")
        draft = PublicationDraft(
            "codex/staged",
            "fix: change",
            "Change",
            "Tests pending",
            head,
            dirty_fingerprint(record.worktree),
        )
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            self.assertRaisesRegex(RuntimeError, "unstage"),
        ):
            apply_draft(record, draft, commit=True)
        self.assertEqual(git(record.worktree, "rev-parse", "HEAD"), head)

    def test_reconcile_repairs_old_excludes_preserving_existing_rules(self):
        from scripts.msandbox.git_worktrees import session_git_dir
        from scripts.msandbox.sessions import _ensure_isolated_git

        record = create_session(
            self.repo, SessionSpec("old", "codex", "main", start=False)
        )
        host = self.repo / ".git/info/exclude"
        isolated = session_git_dir(record.id) / "info/exclude"
        for path in (host, isolated):
            path.write_text("custom-file\n/.msandbox/outputs/\n!/.msandbox/outputs/\n")
        _ensure_isolated_git(record)
        before = [path.read_bytes() for path in (host, isolated)]
        _ensure_isolated_git(record)
        self.assertEqual([path.read_bytes() for path in (host, isolated)], before)
        for path in (host, isolated):
            self.assertIn("custom-file", path.read_text())
            self.assertTrue(path.read_text().endswith("/.msandbox/outputs/\n"))

    def test_exclude_repair_refuses_symlinks(self):
        from scripts.msandbox.git_worktrees import (
            exclude_generated_outputs,
            session_git_dir,
        )

        record = create_session(
            self.repo, SessionSpec("unsafe", "codex", "main", start=False)
        )
        target = self.root / "keep"
        target.write_text("preserved")
        path = session_git_dir(record.id) / "info/exclude"
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(OSError):
            exclude_generated_outputs(record.worktree, record.id)
        self.assertEqual(target.read_text(), "preserved")

    def test_apply_does_not_overwrite_local_ref_changed_during_commit(self):
        from scripts.msandbox.publication import git as publication_git

        record = create_session(
            self.repo, SessionSpec("race", "codex", "main", start=False)
        )
        (record.worktree / "README.md").write_text("changed")
        head = git(record.worktree, "rev-parse", "HEAD")
        draft = PublicationDraft(
            "codex/race",
            "fix: race",
            "Race",
            "Tests pending",
            head,
            dirty_fingerprint(record.worktree),
        )
        # An unrelated commit owned by another caller, with the same tree.
        external = git(
            self.repo, "commit-tree", f"{head}^{{tree}}", "-p", head, "-m", "external"
        )

        def race(record, *args):
            result = publication_git(record, *args)
            if args[0] == "commit":
                git(self.repo, "update-ref", "refs/heads/codex/race", external)
            return result

        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.publication.git", side_effect=race),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            apply_draft(record, draft, commit=True)
        self.assertEqual(git(self.repo, "rev-parse", draft.branch), external)

    def test_oversized_login_snapshot_rolls_back_on_missing_target_login(self):
        record = self.record()
        save_session(record)
        old = session_home(record) / ".codex/auth.json"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"x" * (1024 * 1024 + 1))
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.session_auth.Path.home", return_value=self.root),
            self.assertRaisesRegex(RuntimeError, "No host claude login"),
        ):
            switch_session(record, "claude")
        self.assertTrue(old.exists())
        self.assertEqual(old.read_bytes(), b"x" * (1024 * 1024 + 1))
        self.assertEqual(load_session(record.id).agent, "codex")

    def test_large_claude_configuration_can_switch_and_return(self):
        record = self.record()
        save_session(record)
        config = self.root / ".claude.json"
        config.write_bytes(b"x" * (2 * 1024 * 1024))
        for name in (".claude/.credentials.json", ".codex/auth.json"):
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("synthetic-login")
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.session_auth.Path.home", return_value=self.root),
        ):
            switch_session(record, "claude")
            self.assertEqual((session_home(record) / ".claude.json").stat().st_size, config.stat().st_size)
            switch_session(record, "codex")
            switch_session(record, "claude")
        self.assertEqual((session_home(record) / ".claude.json").read_bytes(), config.read_bytes())

    def test_failed_commit_can_redraft_and_update_existing_local_branch(self):
        from scripts.msandbox.publication import git as publication_git

        record = create_session(
            self.repo, SessionSpec("retry", "codex", "main", start=False)
        )
        (record.worktree / "README.md").write_text("changed")
        draft = PublicationDraft(
            "codex/retry",
            "fix: retry",
            "Retry",
            "Tests pending",
            git(record.worktree, "rev-parse", "HEAD"),
            dirty_fingerprint(record.worktree),
        )

        def fail_commit(record, *args):
            if args[0] == "commit":
                raise subprocess.CalledProcessError(1, ["git", "commit"])
            return publication_git(record, *args)

        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch("scripts.msandbox.publication.git", side_effect=fail_commit),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            apply_draft(record, draft, commit=True)
        draft = replace(draft, fingerprint=dirty_fingerprint(record.worktree))
        with mock.patch("scripts.msandbox.sessions.stop_session"):
            apply_draft(record, draft, commit=True)
        self.assertNotEqual(git(record.worktree, "rev-parse", "HEAD"), draft.head)
        self.assertEqual(
            git(record.worktree, "rev-parse", draft.branch),
            git(record.worktree, "rev-parse", "HEAD"),
        )

    def test_commit_keeps_isolated_git_reconcilable(self):
        from scripts.msandbox.git_worktrees import dirty_fingerprint, session_git_head
        from scripts.msandbox.sessions import start_session

        record = create_session(
            self.repo, SessionSpec("commit-test", "codex", "main", start=False)
        )
        head = git(record.worktree, "rev-parse", "HEAD")
        (record.worktree / "README.md").write_text("changed\n")
        draft = PublicationDraft(
            "codex/commit-test-name",
            "feat: improve readme",
            "Improve readme",
            "Tests pending",
            head,
            dirty_fingerprint(record.worktree),
        )
        with mock.patch("scripts.msandbox.sessions.stop_session"):
            apply_draft(record, draft, commit=True)
        updated = git(record.worktree, "rev-parse", "HEAD")
        self.assertNotEqual(updated, head)
        self.assertEqual(git(record.worktree, "rev-parse", draft.branch), updated)
        with (
            mock.patch("scripts.msandbox.sessions.ensure_container"),
            mock.patch("scripts.msandbox.sessions.launch_agent"),
            mock.patch("scripts.msandbox.sessions.refresh_capability_context"),
        ):
            start_session(record)
        self.assertEqual(session_git_head(record.id), updated)

    def test_pr_copy_is_transmitted_verbatim_via_body_file(self):
        from scripts.msandbox.sessions import _find_or_create_pr

        record = self.record()
        body = "A multiline description.\n\nLiteral `code` and $variables.\n"

        def run(argv, **kwargs):
            if argv[:3] == ["gh", "pr", "list"]:
                return subprocess.CompletedProcess(argv, 0, "[]", "")
            self.assertIn("--body-file", argv)
            self.assertEqual(
                Path(argv[argv.index("--body-file") + 1]).read_text(), body
            )
            return subprocess.CompletedProcess(
                argv, 0, "https://github.com/example/test/pull/7\n", ""
            )

        with (
            mock.patch(
                "scripts.msandbox.sessions._github_repo", return_value="example/test"
            ),
            mock.patch("scripts.msandbox.sessions.subprocess.run", side_effect=run),
        ):
            number, _ = _find_or_create_pr(record, draft=True, title="Title", body=body)
        self.assertEqual(number, 7)

    def test_pr_step_failure_returns_submission_to_stopped_and_retries(self):
        record = create_session(
            self.repo, SessionSpec("submit-retry", "codex", "main", start=False)
        )
        head = git(record.worktree, "rev-parse", "HEAD")
        with (
            mock.patch.dict(os.environ, {"MSANDBOX_NO_VERIFY": "1"}),
            mock.patch("scripts.msandbox.sessions.stop_session"),
            mock.patch(
                "scripts.msandbox.sessions.remote_branch_sha",
                side_effect=[None, head],
            ),
            mock.patch(
                "scripts.msandbox.sessions.push_detached_head", return_value=head
            ) as push,
            mock.patch(
                "scripts.msandbox.sessions._find_or_create_pr",
                side_effect=[
                    RuntimeError("gh pr edit failed"),
                    (7, "https://github.com/example/test/pull/7"),
                ],
            ),
            mock.patch(
                "scripts.msandbox.sessions.release_session",
                return_value=mock.Mock(released=True),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "edit failed"):
                submit_session(record, title="Replacement", body="Replacement")
            saved = load_session(record.id)
            self.assertEqual(saved.phase, "stopped")
            self.assertEqual(saved.expected_remote_sha, head)
            self.assertEqual(saved.remote_head_sha, head)

            result = submit_session(record, title="Replacement", body="Replacement")

        self.assertEqual(result.number, 7)
        self.assertEqual(push.call_args_list[1].args[3], head)


if __name__ == "__main__":
    import unittest

    unittest.main()
