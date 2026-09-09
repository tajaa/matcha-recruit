from __future__ import annotations

import io
import json
import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from scripts.msandbox.files import SandboxFile, export_file, list_files, read_file
from scripts.msandbox.inspection import inspect_session
from scripts.msandbox.manager import manage
from scripts.msandbox.models import SessionSpec
from scripts.msandbox.publication import (
    PublicationDraft,
    apply_draft,
    generate_copy,
    load_draft,
    save_draft,
    validate_copy,
)
from scripts.msandbox.sessions import create_session, switch_session
from scripts.msandbox.state import load_session, save_session
from scripts.msandbox.terminal_ui import clip, frame, mouse_key, plain
from scripts.msandbox.tool_actions import tool_action
from scripts.tests.test_msandbox_v2 import MsandboxTestCase, git


class ManagerTests(MsandboxTestCase):
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
        self.assertEqual(clip("猫猫a", 3), "猫")
        self.assertNotIn("\x1b", plain("file\x1b]52;c;secret\a"))

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

    def test_docker_error_is_unknown_not_false_health(self):
        with mock.patch(
            "scripts.msandbox.inspection.run",
            return_value=subprocess.CompletedProcess([], 1, "", "secret"),
        ):
            snapshot = inspect_session(self.record())
        self.assertIn("unknown", snapshot.lines[0])
        self.assertNotIn("secret", str(snapshot))

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


if __name__ == "__main__":
    import unittest

    unittest.main()
