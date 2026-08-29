from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.msandbox.attachments import AttachmentError, import_files, parse_pasted_file_payload
from scripts.msandbox.docker_runtime import allocate_port_block, compose_environment
from scripts.msandbox.git_worktrees import (
    GitError,
    branch_publish_state,
    create_detached_worktree,
    detach_branch_owner,
    list_worktrees,
    push_detached_head,
    remove_session_worktree,
    resolve_worktree_owner,
    session_git_dir,
)
from scripts.msandbox.host_actions import HostActionError, build_xcode_command
from scripts.msandbox.install import InstallError, install_release, rollback_release
from scripts.msandbox.models import PortSet, SessionRecord, SessionSpec, TestPlan, ValidationReference
from scripts.msandbox.pty_proxy import PASTE_END, PASTE_START, rewrite_paste_stream
from scripts.msandbox.sessions import (
    SessionError,
    _validation_current,
    create_session,
    release_session,
    start_session,
    stop_session,
    submit_session,
)
from scripts.msandbox.state import SCHEMA_VERSION, list_sessions, load_session, save_session, state_lock
from scripts.msandbox.validation import build_test_plan, changed_paths, run_test_plan


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

    def test_kernel_lock_survives_its_owner_file_and_is_reacquirable(self) -> None:
        lock = self.root / "state/locks/repo.lock"
        child = os.fork()
        if child == 0:
            with state_lock("repo", timeout_s=0.5):
                os._exit(0)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        # The file is persistent; the kernel lock, unlike a mkdir/owner.json
        # protocol, is released even when the owner exits inside the context.
        self.assertTrue(lock.is_file())
        with state_lock("repo", timeout_s=0.5):
            self.assertTrue(lock.is_file())

    def test_released_sessions_do_not_reserve_ports_forever(self) -> None:
        record = self.record()
        record.phase = "released"
        record.ports = PortSet(18001, 15174, 15191, 15201, 18080)
        save_session(record)
        with mock.patch("scripts.msandbox.docker_runtime._port_available", return_value=True):
            allocated = allocate_port_block()
        self.assertEqual(allocated, record.ports)


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

    def test_isolated_git_config_and_objects_sync_without_mutating_common_config(self) -> None:
        record = create_session(
            self.repo, SessionSpec("git-isolation", "codex", "main", start=False)
        )
        worktree = record.worktree
        private_git = session_git_dir(record.id)
        common_config = self.repo / ".git/config"
        config_before = common_config.read_bytes()
        isolated_before = git(worktree, "rev-parse", "HEAD")
        subprocess.run(
            ["git", "--git-dir", str(private_git), "config", "core.hooksPath", "/tmp/isolated-hooks"],
            check=True,
        )
        (worktree / "README.md").write_text("isolated commit\n", encoding="utf-8")
        subprocess.run(
            ["git", "--git-dir", str(private_git), "--work-tree", str(worktree), "add", "README.md"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "--git-dir",
                str(private_git),
                "--work-tree",
                str(worktree),
                "commit",
                "-m",
                "isolated",
            ],
            check=True,
            capture_output=True,
        )
        isolated_head = subprocess.run(
            ["git", "--git-dir", str(private_git), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(git(worktree, "rev-parse", "HEAD"), isolated_before)
        self.assertEqual(common_config.read_bytes(), config_before)
        with (
            mock.patch("scripts.msandbox.sessions.ensure_container"),
            mock.patch("scripts.msandbox.sessions.launch_agent"),
        ):
            start_session(record)
        self.assertEqual(git(worktree, "rev-parse", "HEAD"), isolated_head)
        self.assertEqual(git(worktree, "status", "--porcelain"), "")
        self.assertEqual(common_config.read_bytes(), config_before)

    def test_stop_preserves_a_host_commit_when_the_isolated_head_did_not_move(self) -> None:
        record = create_session(
            self.repo, SessionSpec("host-advanced", "codex", "main", start=False)
        )
        (record.worktree / "host.txt").write_text("host commit\n", encoding="utf-8")
        git(record.worktree, "add", "host.txt")
        git(record.worktree, "commit", "-m", "host commit")
        host_head = git(record.worktree, "rev-parse", "HEAD")
        with (
            mock.patch("scripts.msandbox.sessions.stop_agent"),
            mock.patch("scripts.msandbox.sessions.stop_container"),
        ):
            stop_session(record)
        self.assertEqual(git(record.worktree, "rev-parse", "HEAD"), host_head)
        isolated_head = subprocess.run(
            ["git", "--git-dir", str(session_git_dir(record.id)), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(isolated_head, host_head)

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

    def test_push_lease_rejects_a_branch_created_by_another_session(self) -> None:
        path = self.root / "push-race/repo"
        create_detached_worktree(self.repo, "push-race", "main", path)
        (path / "README.md").write_text("session\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "-m", "session")
        git(self.repo, "push", "origin", "main:refs/heads/codex/race")
        with self.assertRaises(GitError):
            push_detached_head(self.repo, path, "codex/race", None)

    def test_push_publishes_the_captured_sha_not_a_later_worktree_head(self) -> None:
        path = self.root / "captured-head/repo"
        create_detached_worktree(self.repo, "captured-head", "main", path)
        (path / "README.md").write_text("validated\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "-m", "validated")
        validated = git(path, "rev-parse", "HEAD")
        (path / "later.txt").write_text("later\n", encoding="utf-8")
        git(path, "add", "later.txt")
        git(path, "commit", "-m", "later")
        pushed = push_detached_head(
            self.repo, path, "codex/captured", None, head_sha=validated
        )
        self.assertEqual(pushed, validated)
        self.assertEqual(git(self.repo, "rev-parse", "origin/codex/captured"), validated)

    def test_release_checks_live_origin_not_stale_tracking_ref(self) -> None:
        path = self.root / "live-remote/repo"
        create_detached_worktree(self.repo, "live-remote", "main", path)
        git(path, "push", "origin", "HEAD:refs/heads/codex/live")
        git(self.repo, "fetch", "origin", "codex/live")
        old_remote = git(self.repo, "rev-parse", "origin/codex/live")
        (self.repo / "other.txt").write_text("remote moved\n", encoding="utf-8")
        git(self.repo, "add", "other.txt")
        git(self.repo, "commit", "-m", "remote moved")
        new_remote = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "push", "origin", f"{new_remote}:refs/heads/remote-source")
        git(self.remote, "update-ref", "refs/heads/codex/live", new_remote)
        self.assertEqual(git(self.repo, "rev-parse", "origin/codex/live"), old_remote)
        released = remove_session_worktree(self.repo, path, "codex/live")
        self.assertFalse(released.released)
        self.assertTrue(path.exists())

    def test_release_retains_unpublished_isolated_git_when_worktree_is_missing(self) -> None:
        record = create_session(
            self.repo, SessionSpec("missing-tree", "codex", "main", start=False)
        )
        git(self.repo, "worktree", "remove", str(record.worktree))
        with (
            mock.patch("scripts.msandbox.sessions.stop_agent"),
            mock.patch("scripts.msandbox.sessions.remove_orphaned_container_project"),
        ):
            released = release_session(record)
        self.assertFalse(released.released)
        self.assertTrue(session_git_dir(record.id).is_dir())

    def test_colliding_target_branches_are_rejected(self) -> None:
        create_session(self.repo, SessionSpec("A B", "codex", "main", start=False))
        with self.assertRaises(SessionError):
            create_session(self.repo, SessionSpec("a-b", "opencode", "main", start=False))

    def test_submit_rejects_remote_branch_drift_since_session_creation(self) -> None:
        record = create_session(
            self.repo, SessionSpec("lease-drift", "codex", "main", start=False)
        )
        head = git(record.worktree, "rev-parse", "HEAD")
        record.last_validation = ValidationReference(
            "pr", head, "clean", "pass", "/tmp/result.json", "now"
        )
        git(self.repo, "push", "origin", f"main:refs/heads/{record.target_branch}")
        with (
            mock.patch("scripts.msandbox.sessions.stop_session"),
            self.assertRaises(SessionError),
        ):
            submit_session(record)

    def test_pr_session_compares_the_pr_head_to_its_merge_base(self) -> None:
        git(self.repo, "switch", "-c", "feature")
        (self.repo / "pr-only.txt").write_text("from PR\n", encoding="utf-8")
        git(self.repo, "add", "pr-only.txt")
        git(self.repo, "commit", "-m", "PR change")
        feature_sha = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "push", "origin", "feature")
        git(self.repo, "switch", "main")
        main_sha = git(self.repo, "rev-parse", "HEAD")
        with mock.patch(
            "scripts.msandbox.sessions.resolve_pr", return_value=("feature", feature_sha)
        ):
            record = create_session(
                self.repo,
                SessionSpec("review-pr", "codex", "main", pr_number=350, start=False),
            )
        self.assertEqual(record.start_sha, feature_sha)
        self.assertEqual(record.base_sha, main_sha)
        self.assertIn("pr-only.txt", changed_paths(record))


class AttachmentTests(MsandboxTestCase):
    def test_import_is_bounded_idempotent_and_session_local(self) -> None:
        record = self.record()
        source = self.root / "Screen Shot ü.png"
        source.write_bytes(b"png bytes")
        first = import_files(record, [source])[0]
        second = import_files(record, [source])[0]
        self.assertEqual(first.host_path, second.host_path)
        self.assertTrue(first.host_path.name.startswith(first.sha256))
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

    def test_streaming_drag_handles_split_markers_and_multiple_frames(self) -> None:
        record = self.record()
        first = self.root / "first image.png"
        second = self.root / "second.pdf"
        first.write_bytes(b"png")
        second.write_bytes(b"pdf")
        first_frame = PASTE_START + str(first).replace(" ", "\\ ").encode() + PASTE_END
        second_frame = PASTE_START + str(second).encode() + PASTE_END
        emitted, pending = rewrite_paste_stream(record, b"hello" + first_frame[:4])
        self.assertEqual(emitted, b"hello")
        emitted2, pending = rewrite_paste_stream(
            record, pending + first_frame[4:] + b" " + second_frame + b"!"
        )
        self.assertEqual(pending, b"")
        self.assertEqual(emitted2.count(PASTE_START), 2)
        self.assertEqual(emitted2.count(PASTE_END), 2)
        self.assertIn(b"/attachments/", emitted2)
        self.assertTrue(emitted2.endswith(b"!"))


class HostAndInstallTests(MsandboxTestCase):
    def test_xcode_boundary_rejects_arbitrary_targets_and_paths(self) -> None:
        record = self.record()
        with self.assertRaises(HostActionError):
            build_xcode_command(record, "../../evil", "build")
        with self.assertRaises(HostActionError):
            build_xcode_command(record, "espresso", "open")

    def test_image_and_dependency_volumes_include_manifests_and_controller_toolchain(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        runtime_root = self.root / "runtime"
        shutil.copytree(project_root / "docker/agent-sandbox", runtime_root / "docker/agent-sandbox")
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
        git_metadata = self.root / "git-metadata"
        (git_metadata / "objects").mkdir(parents=True)
        isolated_git = self.root / "data/git-sessions/session-1/repo.git"
        isolated_git.mkdir(parents=True)
        (isolated_git.parent / "workspace.git").write_text(
            "gitdir: /msandbox-git\n", encoding="utf-8"
        )
        with (
            mock.patch.dict(os.environ, {"MSANDBOX_RUNTIME_ROOT": str(runtime_root)}),
            mock.patch(
                "scripts.msandbox.docker_runtime.git_common_dir", return_value=git_metadata
            ),
        ):
            first = compose_environment(record)
            entrypoint = runtime_root / "docker/agent-sandbox/entrypoint.sh"
            entrypoint.write_text(
                entrypoint.read_text(encoding="utf-8") + "\n# toolchain revision\n",
                encoding="utf-8",
            )
            toolchain_changed = compose_environment(record)
            (fixture / "client/package.json").write_text("{}\n", encoding="utf-8")
            second = compose_environment(record)
        self.assertNotEqual(first["SANDBOX_IMAGE"], toolchain_changed["SANDBOX_IMAGE"])
        self.assertNotEqual(
            first["SANDBOX_CLIENT_NODE_MODULES_VOLUME"],
            toolchain_changed["SANDBOX_CLIENT_NODE_MODULES_VOLUME"],
        )
        self.assertNotEqual(toolchain_changed["SANDBOX_IMAGE"], second["SANDBOX_IMAGE"])
        self.assertNotEqual(
            toolchain_changed["SANDBOX_CLIENT_NODE_MODULES_VOLUME"],
            second["SANDBOX_CLIENT_NODE_MODULES_VOLUME"],
        )
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
        launcher_text = launcher.read_text(encoding="utf-8")
        self.assertIn("scripts/agent-sandbox.sh", launcher_text)
        self.assertIn("legacy control plane", launcher_text)
        self.assertEqual(rollback_release(release.name, bin_dir=bin_dir), release)
        with self.assertRaises(InstallError):
            rollback_release("../escape", bin_dir=bin_dir)

    def test_installed_launcher_routes_legacy_system_commands(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        fixture = self.root / "controller-repo"
        (fixture / "scripts").mkdir(parents=True)
        shutil.copy2(project_root / "scripts/__init__.py", fixture / "scripts/__init__.py")
        shutil.copytree(project_root / "scripts/msandbox", fixture / "scripts/msandbox")
        legacy = fixture / "scripts/agent-sandbox.sh"
        legacy.write_text('#!/bin/sh\nprintf "legacy:%s\\n" "$*"\n', encoding="utf-8")
        legacy.chmod(0o755)
        for relative in (
            "docker-compose.sandbox.yml",
            "docker-compose.sandbox-session.yml",
            "docker-compose.sandbox-dev.yml",
            "docker-compose.sandbox-test.yml",
            "docker-compose.autopr-sandbox.yml",
        ):
            shutil.copy2(project_root / relative, fixture / relative)
        shutil.copytree(project_root / "docker/agent-sandbox", fixture / "docker/agent-sandbox")
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
        bin_dir = self.root / "legacy-bin"
        install_release(repo_root=fixture, bin_dir=bin_dir)
        completed = subprocess.run(
            [str(bin_dir / "msandbox"), "system", "status"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.stdout.strip(), "legacy:system status")


class ValidationPlannerTests(MsandboxTestCase):
    def test_pr_server_change_uses_isolated_services_migrations_and_full_suite(self) -> None:
        with mock.patch("scripts.msandbox.validation.changed_paths", return_value=["server/app/example.py"]):
            plan = build_test_plan(self.record(), "pr")
        identifiers = [check.id for check in plan.checks]
        self.assertIn("isolated-data-services", identifiers)
        self.assertIn("server-migrations", identifiers)
        self.assertIn("server-full", identifiers)

    def test_changed_validation_is_never_accepted_for_submission(self) -> None:
        record = self.record()
        head = git(self.repo, "rev-parse", "HEAD")
        record.last_validation = ValidationReference(
            "changed", head, "clean", "pass", "/tmp/result.json", "now"
        )
        self.assertFalse(_validation_current(record, head, "clean"))

    def test_pr_automatically_selects_affected_xcode_targets(self) -> None:
        with mock.patch(
            "scripts.msandbox.validation.changed_paths",
            return_value=["platforms/ios/TellUs/App.swift"],
        ):
            plan = build_test_plan(self.record(), "pr")
        self.assertEqual(plan.xcode_targets, ("tellus",))

    def test_validation_uses_a_fresh_compose_project_and_removes_its_volumes(self) -> None:
        record = create_session(
            self.repo, SessionSpec("validate", "codex", "main", start=False)
        )
        plan = TestPlan("pr", tuple(changed_paths(record)), ())
        with (
            mock.patch("scripts.msandbox.sessions.stop_session") as stop,
            mock.patch("scripts.msandbox.validation.ensure_container") as ensure,
            mock.patch("scripts.msandbox.validation.remove_container_project") as remove,
        ):
            report = run_test_plan(record, plan)
        self.assertEqual(report.status, "pass")
        stop.assert_called_once_with(record, _lock_held=True)
        validation_record = ensure.call_args.args[0]
        self.assertNotEqual(validation_record.compose_project, record.compose_project)
        self.assertFalse(validation_record.dev)
        self.assertIsNone(validation_record.ports)
        remove.assert_called_once_with(validation_record, volumes=True)

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
