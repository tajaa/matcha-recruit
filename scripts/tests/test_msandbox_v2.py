from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.msandbox.attachments import AttachmentError, import_files, parse_pasted_file_payload
from scripts.msandbox.docker_runtime import compose_environment
from scripts.msandbox.git_worktrees import (
    branch_publish_state,
    create_detached_worktree,
    detach_branch_owner,
    list_worktrees,
    push_detached_head,
    remove_session_worktree,
    resolve_worktree_owner,
)
from scripts.msandbox.host_actions import HostActionError, _write_json_atomic, build_xcode_command
from scripts.msandbox.install import install_release
from scripts.msandbox.models import SessionRecord, SessionSpec
from scripts.msandbox.sessions import create_session
from scripts.msandbox.state import SCHEMA_VERSION, list_sessions, load_session, save_session, state_lock
from scripts.msandbox.validation import build_test_plan


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


class MsandboxTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="msandbox-v2-test.")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "origin.git"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Msandbox Test")
        git(self.repo, "config", "user.email", "msandbox@example.invalid")
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-m", "base")
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        self.environment = mock.patch.dict(
            os.environ,
            {
                "MSANDBOX_STATE_DIR": str(self.root / "state"),
                "MSANDBOX_DATA_DIR": str(self.root / "data"),
                "MSANDBOX_CONFIG_DIR": str(self.root / "config"),
                "MSANDBOX_SKIP_FETCH": "1",
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        for worktree in list_worktrees(self.repo)[1:]:
            subprocess.run(
                ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(worktree.path)],
                check=False,
                capture_output=True,
            )
        self.environment.stop()
        self.temporary.cleanup()

    def record(self, session_id: str = "session-1") -> SessionRecord:
        worktree = self.root / "worktree"
        worktree.mkdir(exist_ok=True)
        return SessionRecord(
            SCHEMA_VERSION,
            session_id,
            "test",
            "codex",
            "created",
            str(self.repo),
            str(worktree),
            "admin",
            f"matcha-ms-{session_id}",
            f"ms-{session_id}",
            "main",
            git(self.repo, "rev-parse", "HEAD"),
            "codex/test",
        )


class StateTests(MsandboxTestCase):
    def test_atomic_round_trip_and_unique_name_lookup(self) -> None:
        record = self.record()
        save_session(record)
        loaded = load_session("test")
        self.assertEqual(loaded.id, record.id)
        self.assertEqual([item.id for item in list_sessions()], [record.id])
        self.assertEqual((self.root / "state/sessions/session-1/session.json").stat().st_mode & 0o777, 0o600)

    def test_stale_same_host_lock_is_recovered(self) -> None:
        lock = self.root / "state/locks/repo.lock"
        lock.mkdir(parents=True)
        (lock / "owner.json").write_text(
            json.dumps({"pid": 99999999, "host": __import__("socket").gethostname()}),
            encoding="utf-8",
        )
        with state_lock("repo", timeout_s=0.5):
            self.assertTrue(lock.is_dir())
        self.assertFalse(lock.exists())


class WorktreeTests(MsandboxTestCase):
    def test_sessions_are_parallel_and_detached(self) -> None:
        first = create_session(self.repo, SessionSpec("first", "codex", "main", start=False))
        second = create_session(self.repo, SessionSpec("second", "codex", "main", start=False))
        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.worktree_path, second.worktree_path)
        self.assertEqual(git(Path(first.worktree_path), "branch", "--show-current"), "")
        self.assertEqual(git(Path(second.worktree_path), "branch", "--show-current"), "")
        worktrees = list_worktrees(self.repo)
        self.assertFalse(
            any(item.branch for item in worktrees if item.path.resolve() != self.repo.resolve()),
            worktrees,
        )

    def test_release_requires_clean_published_head(self) -> None:
        path = self.root / "managed/repo"
        create_detached_worktree(self.repo, "release", "main", path)
        (path / "README.md").write_text("changed\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "-m", "change")
        unpublished = remove_session_worktree(self.repo, path, "codex/release")
        self.assertFalse(unpublished.released)
        git(path, "push", "origin", "HEAD:refs/heads/codex/release")
        git(self.repo, "fetch", "origin", "codex/release")
        published = branch_publish_state(self.repo, path, "codex/release")
        self.assertTrue(published.published)
        released = remove_session_worktree(self.repo, path, "codex/release")
        self.assertTrue(released.released)
        self.assertFalse(path.exists())

    def test_clean_published_branch_owner_can_be_detached(self) -> None:
        git(self.repo, "branch", "feature", "main")
        path = self.root / "branch-owner"
        git(self.repo, "worktree", "add", str(path), "feature")
        git(path, "push", "-u", "origin", "feature")
        git(self.repo, "fetch", "origin", "feature")
        owner = resolve_worktree_owner(self.repo, "feature")
        self.assertIsNotNone(owner)
        result = detach_branch_owner(self.repo, owner)  # type: ignore[arg-type]
        self.assertTrue(result.released)
        self.assertEqual(git(path, "branch", "--show-current"), "")

    def test_detached_push_creates_and_safely_updates_remote_branch(self) -> None:
        path = self.root / "push/repo"
        create_detached_worktree(self.repo, "push", "main", path)
        (path / "README.md").write_text("first\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "-m", "first")
        first = push_detached_head(self.repo, path, "codex/push", None)
        self.assertEqual(git(self.repo, "rev-parse", "origin/codex/push"), first)
        (path / "README.md").write_text("second\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "-m", "second")
        second = push_detached_head(self.repo, path, "codex/push", first)
        self.assertEqual(git(self.repo, "rev-parse", "origin/codex/push"), second)


class AttachmentTests(MsandboxTestCase):
    def test_import_is_bounded_idempotent_and_session_local(self) -> None:
        record = self.record()
        source = self.root / "Screen Shot ü.png"
        source.write_bytes(b"png bytes")
        first = import_files(record, [source])[0]
        second = import_files(record, [source])[0]
        self.assertEqual(first.host_path, second.host_path)
        self.assertEqual(first.container_path.parent, Path("/attachments"))
        self.assertEqual(first.host_path.read_bytes(), b"png bytes")
        self.assertEqual(first.host_path.stat().st_mode & 0o777, 0o600)

    def test_reimport_does_not_consume_session_quota_twice(self) -> None:
        record = self.record()
        source = self.root / "same.pdf"
        source.write_bytes(b"four")
        import_files(record, [source], session_max_bytes=4)
        imported = import_files(record, [source], session_max_bytes=4)
        self.assertEqual(imported[0].size, 4)

    def test_symlink_and_oversize_are_rejected(self) -> None:
        record = self.record()
        source = self.root / "source.png"
        source.write_bytes(b"1234")
        link = self.root / "link.png"
        link.symlink_to(source)
        with self.assertRaises(AttachmentError):
            import_files(record, [link])
        with self.assertRaises(AttachmentError):
            import_files(record, [source], max_bytes=1)

    def test_drag_payload_recognizes_shell_escaped_paths_only(self) -> None:
        source = self.root / "Screen Shot.png"
        source.write_bytes(b"x")
        escaped = str(source).replace(" ", "\\ ").encode()
        self.assertEqual(parse_pasted_file_payload(escaped), [source])
        self.assertIsNone(parse_pasted_file_payload(b"what does this code do?"))


class HostAndInstallTests(MsandboxTestCase):
    def test_xcode_boundary_rejects_arbitrary_targets_and_paths(self) -> None:
        record = self.record()
        with self.assertRaises(HostActionError):
            build_xcode_command(record, "../../evil", "build")
        with self.assertRaises(HostActionError):
            build_xcode_command(record, "espresso", "open")

    def test_host_result_replaces_container_controlled_symlink(self) -> None:
        target = self.root / "must-not-change"
        target.write_text("safe", encoding="utf-8")
        result = self.root / "bridge/results/request.json"
        result.parent.mkdir(parents=True)
        result.symlink_to(target)
        _write_json_atomic(result, {"status": "pass"})
        self.assertEqual(target.read_text(encoding="utf-8"), "safe")
        self.assertFalse(result.is_symlink())

    def test_container_image_is_content_addressed_by_session_manifests(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        fixture = self.root / "fixture"
        for relative in (
            "server/requirements.txt",
            "client/package.json",
            "client/package-lock.json",
            "client/tellus/package.json",
            "client/tellus/package-lock.json",
            "client/oceanlab/package.json",
            "client/oceanlab/package-lock.json",
        ):
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project_root / relative, target)
        record = self.record()
        record.worktree_path = str(fixture)
        with mock.patch.dict(os.environ, {"MSANDBOX_RUNTIME_ROOT": str(project_root)}):
            first = compose_environment(record)
            (fixture / "client/package.json").write_text("{}\n", encoding="utf-8")
            second = compose_environment(record)
        self.assertNotEqual(first["SANDBOX_IMAGE"], second["SANDBOX_IMAGE"])
        self.assertTrue(Path(first["SANDBOX_BUILD_CONTEXT"]).is_dir())

    def test_installed_launcher_is_a_copied_release_not_repo_symlink(self) -> None:
        bin_dir = self.root / "bin"
        project_root = Path(__file__).resolve().parents[2]
        release = install_release(repo_root=project_root, bin_dir=bin_dir)
        launcher = bin_dir / "msandbox"
        self.assertTrue((release / "scripts/msandbox/cli.py").is_file())
        self.assertTrue((release / "server/requirements.txt").is_file())
        self.assertTrue((release / "client/package-lock.json").is_file())
        self.assertFalse(launcher.is_symlink())
        self.assertIn("MSANDBOX_RUNTIME_ROOT", launcher.read_text(encoding="utf-8"))
        completed = subprocess.run(
            [str(launcher), "--version"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.stdout.strip(), "msandbox 2.0.0")


class ValidationPlannerTests(MsandboxTestCase):
    def test_pr_server_change_uses_isolated_services_migrations_and_full_suite(self) -> None:
        with mock.patch("scripts.msandbox.validation.changed_paths", return_value=["server/app/example.py"]):
            plan = build_test_plan(self.record(), "pr")
        identifiers = [check.id for check in plan.checks]
        self.assertIn("isolated-data-services", identifiers)
        self.assertIn("server-migrations", identifiers)
        self.assertIn("server-full", identifiers)

    def test_all_selects_every_linux_and_xcode_target(self) -> None:
        with mock.patch("scripts.msandbox.validation.changed_paths", return_value=[]):
            plan = build_test_plan(self.record(), "all", browser=True, xcode="all")
        identifiers = {check.id for check in plan.checks}
        self.assertTrue(
            {
                "server-full",
                "client-tests",
                "client-lint",
                "client-build",
                "tellus-build",
                "oceanlab-lint",
                "oceanlab-build",
                "browser-smoke",
            }.issubset(identifiers)
        )
        self.assertEqual(set(plan.xcode_targets), {"espresso", "matchatutor", "tellus", "gummfit"})


if __name__ == "__main__":
    unittest.main()
