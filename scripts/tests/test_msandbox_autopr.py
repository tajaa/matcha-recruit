from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from scripts.msandbox import autopr_control as control
from scripts.msandbox import autopr_ui


class AutoPRTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.env = mock.patch.dict(
            os.environ, {"AUTOPR_CONTROL_STATE_DIR": str(self.path / "state")}
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.repo = self.path / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        (self.repo / "code.py").write_text("original\n")
        (self.repo / ".gitignore").write_text(".msandbox/\nignored.txt\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def run_record(self, *, status="manual", identifier="a" * 32):
        workspace = control.run_dir(identifier) / "workspace"
        workspace.parent.mkdir(parents=True)
        subprocess.run(
            ["git", "clone", "--quiet", str(self.repo), str(workspace)], check=True
        )
        run = control.Run(
            identifier,
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
            "Test task",
            str(self.repo),
            str(workspace),
            self.base,
            "bot/task-11111111",
            "matcha-autopr-manual-test",
            "gpt-5.6-sol",
            "medium",
            status=status,
        )
        control.save(run)
        (control.run_dir(run.id) / "activity.log").write_text("reading code.py\n")
        return run

    def test_export_keeps_uncommitted_new_and_committed_work_without_touching_main(
        self,
    ):
        run = self.run_record()
        workspace = Path(run.workspace)
        (workspace / "committed.py").write_text("committed\n")
        subprocess.run(["git", "-C", run.workspace, "add", "committed.py"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                run.workspace,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-qm",
                "manual commit",
            ],
            check=True,
        )
        (workspace / "code.py").write_text("edited\n")
        (workspace / "new.py").write_text("new\n")
        (workspace / ".msandbox").mkdir()
        (workspace / ".msandbox/output.txt").write_text("private output")
        # A container may rewrite its Git config. The host exporter must not
        # run an external diff command or read its index.
        sentinel = self.path / "executed"
        subprocess.run(
            [
                "git",
                "-C",
                run.workspace,
                "config",
                "diff.external",
                f"touch {sentinel}",
            ],
            check=True,
        )
        patch = control.export_patch(run)
        self.assertIn(b"+edited", patch)
        self.assertIn(b"+committed", patch)
        self.assertIn(b"+new", patch)
        self.assertNotIn(b"private output", patch)
        self.assertFalse(sentinel.exists())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.base)

    def test_handback_is_claimed_once_and_keeps_operator_settings(self):
        run = self.run_record()
        control.configure(run.id, "gpt-5.6-luna", "high")
        with mock.patch.object(control, "stop_manual"):
            control.prepare_return(
                run.id, self.repo, "Finish tests, preserve my change."
            )
        claimed = control.continuation(run.task_id, "123")
        self.assertEqual((claimed.model, claimed.effort), ("gpt-5.6-luna", "high"))
        self.assertEqual(claimed.note, "Finish tests, preserve my change.")
        with self.assertRaisesRegex(ValueError, "held"):
            control.continuation(run.task_id, "124")
        control.finish_return(run.task_id, "wrong-run", False)
        self.assertEqual(control.load(run.id).status, "resuming")
        control.finish_return(run.task_id, "123", False)
        self.assertEqual(control.load(run.id).status, "ready")
        self.assertTrue(Path(run.workspace).exists())

    def test_failed_export_restores_manual_ownership_and_never_queues(self):
        run = self.run_record()
        with (
            mock.patch.object(control, "stop_manual"),
            mock.patch.object(
                control, "export_patch", side_effect=ValueError("too large")
            ),
            self.assertRaisesRegex(ValueError, "too large"),
        ):
            control.prepare_return(run.id, self.repo, "continue")
        self.assertEqual(control.load(run.id).status, "manual")
        self.assertTrue(Path(run.workspace).exists())

    def test_modified_handback_fails_closed(self):
        run = self.run_record()
        with mock.patch.object(control, "stop_manual"):
            control.prepare_return(run.id, self.repo, "continue")
        (control.run_dir(run.id) / "handoff.patch").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "changed"):
            control.continuation(run.task_id, "123")
        self.assertEqual(control.load(run.id).status, "ready")

    def test_success_archives_ignored_outputs_and_removes_only_its_checkout(self):
        run = self.run_record()
        (Path(run.workspace) / "ignored.txt").write_text("preserve this output")
        other = self.run_record(identifier="b" * 32, status="model_done")
        with mock.patch.object(control, "stop_manual"):
            control.prepare_return(run.id, self.repo, "finish")
        control.continuation(run.task_id, "123")
        control.finish_return(run.task_id, "123", True)
        self.assertEqual(control.load(run.id).status, "returned")
        self.assertFalse(Path(run.workspace).exists())
        self.assertTrue(Path(other.workspace).is_dir())
        with tarfile.open(
            control.run_dir(run.id) / "checkout-recovery.tar.gz"
        ) as archive:
            self.assertEqual(
                archive.extractfile("workspace/ignored.txt").read(),
                b"preserve this output",
            )

    def test_live_supervisor_transfers_only_after_stopping_the_model(self):
        workspace = self.path / "runtime/workspace"
        workspace.parent.mkdir()
        subprocess.run(
            ["git", "clone", "--quiet", str(self.repo), str(workspace)], check=True
        )
        card = self.path / "card.json"
        card.write_text(
            json.dumps(
                {
                    "task_id": "11111111-1111-4111-8111-111111111111",
                    "project_id": "22222222-2222-4222-8222-222222222222",
                    "title": "Live task",
                }
            )
        )
        stop = self.path / "stop"
        stop.write_text("#!/bin/sh\nexit 0\n")
        stop.chmod(0o755)
        child = "import pathlib,time; pathlib.Path('new.py').write_text('partial'); time.sleep(30)"
        env = {**os.environ, "AUTOPR_MSANDBOX_BIN": str(stop)}
        with (self.path / "output").open("wb") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    control.__file__,
                    "supervise",
                    "--card",
                    str(card),
                    "--workspace",
                    str(workspace),
                    "--repo",
                    str(self.repo),
                    "--project",
                    "test-autopr",
                    "--",
                    sys.executable,
                    "-c",
                    child,
                ],
                cwd=workspace,
                stdout=output,
                stderr=output,
                env=env,
            )
            self.addCleanup(lambda: process.poll() is None and process.kill())
            deadline = time.monotonic() + 5
            while not (workspace / "new.py").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((workspace / "new.py").exists())
            run = control.list_runs()[0]
            control.request_takeover(run.id)
            self.assertEqual(process.wait(timeout=5), control.PAUSED_EXIT)
        current = control.load(run.id)
        self.assertEqual(current.status, "manual")
        self.assertEqual((Path(current.workspace) / "new.py").read_text(), "partial")
        self.assertFalse(workspace.exists())
        self.assertEqual((self.repo / "code.py").read_text(), "original\n")

    def test_nested_takeovers_archive_superseded_checkouts_on_success(self):
        prior = self.run_record(identifier="b" * 32)
        with mock.patch.object(control, "stop_manual"):
            control.prepare_return(prior.id, self.repo, "first handback")
        prior = control.load(prior.id)
        prior.status = "superseded"
        control.save(prior)
        run = self.run_record()
        with mock.patch.object(control, "stop_manual"):
            control.prepare_return(run.id, self.repo, "finish")
        control.continuation(run.task_id, "123")
        control.finish_return(run.task_id, "123", True)
        for item in (prior, run):
            self.assertFalse(Path(item.workspace).exists())
            self.assertTrue(
                (control.run_dir(item.id) / "checkout-recovery.tar.gz").exists()
            )

    def test_ready_checkout_cannot_open_a_manual_writer(self):
        run = self.run_record(status="ready")
        with (
            mock.patch.object(autopr_ui.subprocess, "run") as command,
            self.assertRaisesRegex(ValueError, "owns"),
        ):
            autopr_ui.open_manual(run.id, self.repo)
        command.assert_not_called()

    def test_ui_renders_activity_for_selected_run_only(self):
        run = self.run_record()
        other = self.run_record(identifier="b" * 32, status="model_done")
        feed = autopr_ui.AutoPRFeed()
        feed.runs = [run, other]
        feed.activity_id = other.id
        feed.activity = "other task output"
        rows = autopr_ui.rows(feed, run.id)
        self.assertNotIn("other task output", "\n".join(row.text for row in rows))
        self.assertIn(f"autopr:return:{run.id}", [row.action for row in rows])
        self.assertNotIn(f"autopr:return:{other.id}", [row.action for row in rows])

    def test_run_history_is_paged_without_hiding_older_runs(self):
        run = self.run_record()
        feed = autopr_ui.AutoPRFeed()
        feed.runs = [replace(run, id=f"{i:032x}") for i in range(40)]
        rows = autopr_ui.rows(feed, feed.runs[35].id)
        actions = [row.action for row in rows]
        self.assertIn(f"autopr:select:{feed.runs[34].id}", actions)
        self.assertIn(f"autopr:select:{feed.runs[39].id}", actions)
        self.assertIn(f"autopr:return:{feed.runs[35].id}", actions)
        self.assertLess(
            sum(
                bool(action and action.startswith("autopr:select:"))
                for action in actions
            ),
            8,
        )

    def test_installed_selector_ships_ownership_helper_and_skips_held_task(self):
        run = self.run_record()
        scripts = Path(__file__).resolve().parents[1]
        installer = scripts / "kanban-autopr/install-launch-agent.sh"
        install_root = self.path / "installed"
        # Only the pure file-copy function is invoked: no launchd, dashboard,
        # credential validation, or service startup during this test.
        env = {
            **os.environ,
            "AUTOPR_DISPATCH_INSTALL_ROOT": str(install_root),
            "AUTOPR_SELECT_READ_ONLY": "true",
            "AUTOPR_CACHE_DIR": str(self.path / "cache"),
            "GITHUB_REPOSITORY": "test/example",
            "MATCHA_AUTOPR_ENV": str(self.path / "no-credentials"),
        }
        source = installer.read_text().replace('main "$@"', "install_runtime")
        source = source.replace(
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            f'SCRIPT_DIR="{installer.parent}"',
        )
        subprocess.run(["bash", "-c", source], env=env, check=True, capture_output=True)
        self.assertEqual(
            (install_root / "autopr_control.py").read_bytes(),
            (scripts / "msandbox/autopr_control.py").read_bytes(),
        )
        cards = self.path / "cards.json"
        cards.write_text(
            json.dumps(
                [
                    {
                        "task_id": run.task_id,
                        "id8": "11111111",
                        "project_id": run.project_id,
                        "title": run.title,
                        "board_column": "todo",
                        "created_at": "2026-09-01T00:00:00Z",
                    }
                ]
            )
        )
        result = subprocess.run(
            ["bash", str(install_root / "select.sh"), str(cards)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_queue_error_leaves_saved_return_retryable(self):
        run = self.run_record()
        with (
            mock.patch.object(control, "stop_manual"),
            mock.patch.object(
                autopr_ui, "queue_return", side_effect=RuntimeError("offline")
            ),
            mock.patch("scripts.msandbox.wizard.choose", return_value=True),
            mock.patch("scripts.msandbox.manager.show"),
        ):
            notice = autopr_ui.manage(
                "return",
                run.id,
                self.repo,
                reader=lambda _: "finish this",
                output=io.StringIO(),
            )
        self.assertIn("retry", notice)
        self.assertEqual(control.load(run.id).status, "ready")
        self.assertTrue((control.run_dir(run.id) / "handoff.patch").exists())

    def test_model_and_effort_validate_before_mutation(self):
        run = self.run_record()
        for model, effort in [
            ("--config=secret", "high"),
            ("luna;echo injected", "high"),
            ("gpt-5.6-luna", "unknown"),
        ]:
            with self.assertRaises(ValueError):
                control.configure(run.id, model, effort)
        self.assertEqual(control.load(run.id).model, "gpt-5.6-sol")

    def test_stop_does_not_require_host_login_and_isolates_dependencies(self):
        run = self.run_record()
        with mock.patch.object(Path, "home", return_value=self.path / "no-login"):
            env = control.manual_environment(run, self.repo, stopping=True)
        self.assertEqual(
            json.loads(Path(env["SANDBOX_CODEX_AUTH_FILE"]).read_text()), {}
        )
        self.assertEqual(env["AUTOPR_SANDBOX_PROJECT_NAME"], run.project)
        for name in (
            "SERVER_VENV",
            "CLIENT_NODE_MODULES",
            "TELLUS_NODE_MODULES",
            "OCEANLAB_NODE_MODULES",
        ):
            self.assertTrue(env[f"SANDBOX_{name}_VOLUME"].startswith(run.project + "_"))
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("GITHUB_TOKEN", env)

    def test_dead_supervisor_source_cannot_be_replaced(self):
        run = self.run_record(status="running")
        self.assertFalse(control.supervisor_alive(run))
        with self.assertRaisesRegex(ValueError, "owner"):
            control.protect_workspace(run.workspace)
        run.status = "model_done"
        control.save(run)
        control.protect_workspace(run.workspace)

    def test_recovery_refuses_a_different_run_without_stopping_anything(self):
        run = self.run_record(status="blocked")
        source = self.path / "runtime"
        Path(run.workspace).rename(source)
        run.workspace = str(source)
        control.save(run)
        control.atomic(
            source / ".git/autopr-io/control-run.json", json.dumps({"run_id": "b" * 32})
        )
        with (
            mock.patch.object(control, "command") as command,
            self.assertRaisesRegex(ValueError, "another run"),
        ):
            control.recover(run.id, self.repo)
        command.assert_not_called()
        self.assertTrue(source.exists())

    def test_recovery_stops_exact_project_before_adopting_checkout(self):
        run = self.run_record(status="blocked")
        destination = Path(run.workspace)
        source = self.path / "runtime"
        destination.rename(source)
        run.workspace = str(source)
        control.save(run)
        control.atomic(
            source / ".git/autopr-io/control-run.json", json.dumps({"run_id": run.id})
        )

        def stop(argv, **kwargs):
            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())
            self.assertEqual(argv[-1], "stop")
            self.assertEqual(kwargs["env"]["AUTOPR_SANDBOX_PROJECT_NAME"], run.project)

        with mock.patch.object(control, "command", side_effect=stop):
            control.recover(run.id, self.repo)
        self.assertEqual(control.load(run.id).status, "manual")
        self.assertTrue(destination.exists())

    def test_cleanup_preserves_edits_made_outside_controller_after_handback(self):
        run = self.run_record()
        with mock.patch.object(control, "stop_manual"):
            control.prepare_return(run.id, self.repo, "continue")
        control.continuation(run.task_id, "123")
        (Path(run.workspace) / "code.py").write_text("late host edit\n")
        control.finish_return(run.task_id, "123", True)
        self.assertTrue(Path(run.workspace).exists())
        self.assertIn("retained", control.load(run.id).error)

    def test_cleanup_export_failure_keeps_checkout_and_reports_it(self):
        run = self.run_record()
        with mock.patch.object(control, "stop_manual"):
            control.prepare_return(run.id, self.repo, "continue")
        control.continuation(run.task_id, "123")
        with mock.patch.object(
            control, "export_patch", side_effect=RuntimeError("git failed")
        ):
            control.finish_return(run.task_id, "123", True)
        self.assertTrue(Path(run.workspace).exists())
        self.assertIn("git failed", control.load(run.id).error)

    def test_manual_restart_uses_selected_model_and_resumes_conversation(self):
        run = self.run_record()
        run.manual_started = True
        run.model, run.effort = "gpt-5.6-luna", "high"
        control.save(run)
        with (
            mock.patch.object(control, "manual_environment", return_value={}),
            mock.patch.object(
                autopr_ui.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 1),
            ),
            mock.patch.object(
                control, "command", side_effect=[b"", b"abc123\n", b""]
            ) as command,
        ):
            autopr_ui.open_manual(run.id, self.repo)
        create = command.call_args_list[-1].args[0]
        self.assertEqual(create[:3], ["tmux", "new-session", "-d"])
        self.assertIn("codex resume --last", create[-1])
        self.assertNotIn("--ignore-user-config", create[-1])
        self.assertNotIn("Continue this AutoPR task", create[-1])
        self.assertIn("--model gpt-5.6-luna", create[-1])
        self.assertIn('model_reasoning_effort="high"', create[-1])
        self.assertIn(
            "label=com.docker.compose.service=workspace",
            command.call_args_list[1].args[0],
        )

    def test_reclaim_checks_workflow_and_rejects_live_owner(self):
        run = self.run_record(status="resuming")
        run.resumed_by = "123"
        control.save(run)
        with (
            mock.patch.object(control, "command", return_value=b"in_progress\n"),
            self.assertRaisesRegex(ValueError, "still running"),
        ):
            autopr_ui.manage(
                "reclaim", run.id, self.repo, reader=None, output=io.StringIO()
            )
        self.assertEqual(control.load(run.id).status, "resuming")
        with mock.patch.object(control, "command", return_value=b"completed\n"):
            autopr_ui.manage(
                "reclaim", run.id, self.repo, reader=None, output=io.StringIO()
            )
        self.assertEqual(control.load(run.id).status, "manual")

    def test_completed_workflow_does_not_override_a_surviving_local_writer(self):
        run = self.run_record(status="resuming")
        run.resumed_by = "123"
        control.save(run)
        active = self.run_record(identifier="b" * 32, status="running")
        active.supervisor_pid = os.getpid()
        control.save(active)
        with (
            mock.patch.object(control, "command", return_value=b"completed\n"),
            self.assertRaisesRegex(ValueError, "local supervisor"),
        ):
            autopr_ui.manage(
                "reclaim", run.id, self.repo, reader=None, output=io.StringIO()
            )
        self.assertEqual(control.load(run.id).status, "resuming")

    def bridge(self, patch: bytes):
        script_dir = Path(__file__).resolve().parents[1] / "kanban-autopr"
        fake_bin = self.path / "bin"
        fake_bin.mkdir(exist_ok=True)
        codex = fake_bin / "codex"
        codex.write_text(
            "#!/usr/bin/env python3\nimport pathlib, sys\np = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n(p / '.git/autopr-io/output/report.md').write_text('report')\n(p / '.git/autopr-io/output/decision.json').write_text('{}')\nprint('FAKE MODEL INVOKED')\n"
        )
        codex.chmod(0o755)
        template, context, resume = [
            self.path / name for name in ("prompt", "context.json", "resume.patch")
        ]
        template.write_text("Inspect the supplied files.")
        context.write_text("{}")
        resume.write_bytes(patch)
        env = {
            **os.environ,
            "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
            "AUTOPR_SANDBOX_TEST_DIRECT": "1",
            "GITHUB_ACTIONS": "false",
            "AUTOPR_SANDBOX_REPO_ROOT": str(self.repo),
            "AUTOPR_SANDBOX_RUNTIME_ROOT": str(self.path / "bridge"),
            "AUTOPR_RESUME_PATCH": str(resume),
            "AUTOPR_REQUIRE_RESUME_PATCH": "1",
            "AUTOPR_CODEX_BACKOFF": str(self.path / "no-backoff"),
        }
        return subprocess.run(
            [
                "bash",
                str(script_dir / "run-codex-sandboxed.sh"),
                str(template),
                str(self.path / "report"),
                str(self.path / "decision"),
                "-f",
                str(context),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_instruction_only_handback_reaches_the_model(self):
        result = self.bridge(b"")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FAKE MODEL INVOKED", result.stdout)
        self.assertIn("instructions only", result.stdout)

    def test_runtime_action_lock_blocks_same_run_but_not_another(self):
        run = self.run_record()
        other = self.run_record(identifier="b" * 32)
        with control.runtime_locked(run.id):
            with self.assertRaisesRegex(ValueError, "Another action"):
                control.prepare_return(run.id, self.repo, "continue")
            control.configure(other.id, "gpt-5.6-luna", "high")
        self.assertEqual(control.load(run.id).status, "manual")
        self.assertEqual(control.load(other.id).model, "gpt-5.6-luna")

    def test_interrupted_preparation_can_be_recovered_but_live_export_cannot(self):
        run = self.run_record(status="preparing")
        with mock.patch.object(control, "stop_manual") as stop:
            with (
                control.runtime_locked(run.id),
                self.assertRaisesRegex(ValueError, "Another action"),
            ):
                autopr_ui.manage(
                    "reclaim", run.id, self.repo, reader=None, output=io.StringIO()
                )
            stop.assert_not_called()
            autopr_ui.manage(
                "reclaim", run.id, self.repo, reader=None, output=io.StringIO()
            )
            stop.assert_called_once()
        self.assertEqual(control.load(run.id).status, "manual")

    def test_conflicting_handback_never_runs_model_or_modifies_source(self):
        result = self.bridge(b"not a patch\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("operator hand-back no longer applies", result.stderr)
        self.assertNotIn("FAKE MODEL INVOKED", result.stdout)
        self.assertEqual(self.git("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
