from __future__ import annotations

import io
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.msandbox.agent_adapters import (
    AgentError,
    agent_argv,
    capability_context_args,
    launch_agent,
    refresh_capability_context,
)
from scripts.msandbox.attachments import AttachmentError, import_files, parse_pasted_file_payload
from scripts.msandbox.capabilities import (
    CONTAINER_CONFIG_DIR,
    PRODUCTION_TEST_DIR,
    _PROD_TEST_API_SCRIPT,
    collect_report,
    leaks,
    load_report,
    native_builder_socket,
    planned_capabilities,
    probe_registry,
    render_markdown,
    render_report_text,
    report_ok,
    report_paths,
    write_report,
)
from scripts.msandbox.cli import run as run_cli
from scripts.msandbox.docker_gc import collect_garbage, reachable, runtime_roots
from scripts.msandbox.docker_runtime import (
    BUILDER_NAME,
    BUILDER_BOOTSTRAP_TIMEOUT_S,
    DEFAULT_BUILD_CACHE_MAX,
    _ensure_builder,
    _ensure_workspace_image,
    _prune_builder_cache,
    allocate_port_block,
    build_context_sources,
    build_identifier,
    compose_environment,
    session_home,
)
from scripts.msandbox.git_worktrees import (
    GitError,
    branch_publish_state,
    create_detached_worktree,
    detach_branch_owner,
    fetch_origin,
    github_https_url,
    list_worktrees,
    push_detached_head,
    remove_session_worktree,
    resolve_worktree_owner,
    session_git_dir,
)
from scripts.msandbox.host_actions import HostActionError, build_xcode_command
from scripts.msandbox.install import InstallError, install_release, rollback_release
from scripts.msandbox.models import (
    CapabilityReport,
    PortSet,
    SessionRecord,
    SessionSpec,
    TestPlan,
    ValidationReference,
    utc_now,
)
from scripts.msandbox.session_auth import SessionAuthError, refresh_github_auth
from scripts.msandbox.pty_proxy import (
    PASTE_END,
    PASTE_START,
    _sync_window_size,
    rewrite_paste_stream,
    rewrite_paste_stream_with_importer,
    rewrite_paste_stream_to_inbox,
    run_with_file_proxy,
)
from scripts.msandbox.sessions import (
    SessionError,
    ensure_capability_report,
    _validation_current,
    create_session,
    release_session,
    start_session,
    stop_session,
    submit_session,
)
from scripts.msandbox.state import (
    ARTIFACT_LIFECYCLE_LOCK,
    SCHEMA_VERSION,
    list_sessions,
    load_session,
    save_session,
    state_lock,
)
from scripts.msandbox.validation import build_test_plan, changed_paths, run_test_plan
from scripts.msandbox.wizard import (
    _choose_terminal,
    _open_session,
    _session_menu_title,
    _install_session_shell_handoff,
    _interpret_terminal_key,
    _new_session,
    choose,
    next_session_name,
    run_wizard,
)


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

    def test_legacy_records_are_labeled_autonomous(self) -> None:
        raw = self.record().to_dict()
        raw.pop("permission_mode")
        self.assertEqual(SessionRecord.from_dict(raw).permission_mode, "autonomous")

    def test_new_session_specs_default_to_standard_permissions(self) -> None:
        self.assertEqual(SessionSpec("safe", "codex").permission_mode, "standard")

    def test_cli_reports_and_stops_all_running_sessions_without_releasing_them(self) -> None:
        first = self.record("session-1")
        second = self.record("session-2")
        second.name = "other"
        first.phase = "running"
        second.phase = "stopped"
        with (
            mock.patch("scripts.msandbox.cli.list_sessions", return_value=[first, second]),
            mock.patch(
                "scripts.msandbox.cli.reconcile_session", side_effect=lambda item: item
            ),
        ):
            self.assertEqual(
                run_cli(["--repo", str(self.repo), "session", "has-running"]), 0
            )

        first.phase = "stopped"
        with (
            mock.patch("scripts.msandbox.cli.list_sessions", return_value=[first, second]),
            mock.patch(
                "scripts.msandbox.cli.reconcile_session", side_effect=lambda item: item
            ),
        ):
            self.assertEqual(
                run_cli(["--repo", str(self.repo), "session", "has-running"]), 1
            )

        output = io.StringIO()
        with (
            mock.patch("scripts.msandbox.cli.list_sessions", return_value=[first, second]),
            mock.patch("scripts.msandbox.cli.stop_session") as stop,
            redirect_stdout(output),
        ):
            self.assertEqual(
                run_cli(
                    [
                        "--repo",
                        str(self.repo),
                        "session",
                        "stop",
                        "--all",
                        "--force",
                    ]
                ),
                0,
            )
        self.assertEqual(
            stop.call_args_list,
            [mock.call(first, force=True), mock.call(second, force=True)],
        )
        self.assertIn("Stopped 2 independent msandbox session(s).", output.getvalue())

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
    def test_initial_session_registration_holds_artifact_lifecycle_lock(self) -> None:
        active_locks: list[str] = []

        @contextmanager
        def tracked_lock(scope: str, *args, **kwargs):
            with state_lock(scope, *args, **kwargs):
                active_locks.append(scope)
                try:
                    yield
                finally:
                    active_locks.remove(scope)

        def assert_registration_locked(_record: SessionRecord) -> None:
            self.assertIn(ARTIFACT_LIFECYCLE_LOCK, active_locks)

        with mock.patch("scripts.msandbox.sessions.state_lock", tracked_lock), mock.patch(
            "scripts.msandbox.sessions.provision_session_auth",
            side_effect=assert_registration_locked,
        ):
            create_session(self.repo, SessionSpec("locked", "codex", "main", start=False))

    def test_github_auth_materializes_keychain_token_and_repairs_git(self) -> None:
        record = self.record()
        private_git = session_git_dir(record.id)
        private_git.mkdir(parents=True)
        (private_git / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
        calls: list[list[str]] = []

        def run(argv, **kwargs):
            command = [str(item) for item in argv]
            calls.append(command)
            if command[:4] == ["git", "-C", str(self.repo), "remote"]:
                return subprocess.CompletedProcess(argv, 0, "https://github.com/tajaa/matcha-recruit.git\n", "")
            if command[1:4] == ["auth", "token", "--hostname"]:
                return subprocess.CompletedProcess(argv, 0, "test-token\n", "")
            if command[1:3] == ["auth", "login"]:
                config = Path(kwargs["env"]["GH_CONFIG_DIR"])
                config.mkdir(parents=True, exist_ok=True)
                (config / "hosts.yml").write_text(
                    "github.com:\n  user: tajaa\n  oauth_token: test-token\n",
                    encoding="utf-8",
                )
                self.assertEqual(kwargs["input"], "test-token\n")
                self.assertIn("--insecure-storage", command)
                return subprocess.CompletedProcess(argv, 0, "", "")
            if command[:2] == ["git", "config"]:
                return subprocess.CompletedProcess(argv, 0, "", "")
            raise AssertionError(command)

        with mock.patch("scripts.msandbox.session_auth.shutil.which", return_value="/opt/gh"), mock.patch(
            "scripts.msandbox.session_auth.subprocess.run", side_effect=run
        ):
            refresh_github_auth(record)
            refresh_github_auth(record)

        hosts = self.root / "data/homes/session-1/.config/gh/hosts.yml"
        self.assertEqual(hosts.stat().st_mode & 0o777, 0o600)
        self.assertEqual(sum(call[1:3] == ["auth", "login"] for call in calls), 1)
        self.assertEqual(sum(call[:2] == ["git", "config"] for call in calls), 2)

    def test_github_auth_replaces_marker_symlink_without_following_it(self) -> None:
        record = self.record()
        config = self.root / "data/homes/session-1/.config/gh"
        config.mkdir(parents=True)
        victim = self.root / "host-file"
        victim.write_text("keep\n", encoding="utf-8")
        marker = config / ".msandbox-token-sha256"
        marker.symlink_to(victim)

        def run(argv, **kwargs):
            command = [str(item) for item in argv]
            if command[:4] == ["git", "-C", str(self.repo), "remote"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    "https://github.com/tajaa/matcha-recruit.git\n",
                    "",
                )
            if command[1:4] == ["auth", "token", "--hostname"]:
                return subprocess.CompletedProcess(argv, 0, "test-token\n", "")
            if command[1:3] == ["auth", "login"]:
                generated = Path(kwargs["env"]["GH_CONFIG_DIR"]) / "hosts.yml"
                generated.write_text(
                    "github.com:\n  oauth_token: test-token\n", encoding="utf-8"
                )
                return subprocess.CompletedProcess(argv, 0, "", "")
            raise AssertionError(command)

        with mock.patch("scripts.msandbox.session_auth.shutil.which", return_value="/opt/gh"), mock.patch(
            "scripts.msandbox.session_auth.subprocess.run", side_effect=run
        ):
            refresh_github_auth(record)

        self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")
        self.assertFalse(marker.is_symlink())
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

    def test_github_auth_rejects_symlinked_config_directory(self) -> None:
        record = self.record()
        config_root = self.root / "data/homes/session-1/.config"
        config_root.mkdir(parents=True)
        outside = self.root / "outside-gh"
        outside.mkdir()
        (config_root / "gh").symlink_to(outside, target_is_directory=True)
        origin = subprocess.CompletedProcess(
            [], 0, "https://github.com/tajaa/matcha-recruit.git\n", ""
        )
        token = subprocess.CompletedProcess([], 0, "test-token\n", "")

        with mock.patch("scripts.msandbox.session_auth.shutil.which", return_value="/opt/gh"), mock.patch(
            "scripts.msandbox.session_auth.subprocess.run", side_effect=(origin, token)
        ):
            with self.assertRaisesRegex(SessionAuthError, "unsafe private controller directory"):
                refresh_github_auth(record)

        self.assertEqual(list(outside.iterdir()), [])

    def test_github_auth_rejects_symlinked_isolated_git_config(self) -> None:
        record = self.record()
        private_git = session_git_dir(record.id)
        private_git.mkdir(parents=True)
        victim = self.root / "host-git-config"
        victim.write_text("keep\n", encoding="utf-8")
        (private_git / "config").symlink_to(victim)

        def run(argv, **kwargs):
            command = [str(item) for item in argv]
            if command[:4] == ["git", "-C", str(self.repo), "remote"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    "https://github.com/tajaa/matcha-recruit.git\n",
                    "",
                )
            if command[1:4] == ["auth", "token", "--hostname"]:
                return subprocess.CompletedProcess(argv, 0, "test-token\n", "")
            if command[1:3] == ["auth", "login"]:
                generated = Path(kwargs["env"]["GH_CONFIG_DIR"]) / "hosts.yml"
                generated.write_text(
                    "github.com:\n  oauth_token: test-token\n", encoding="utf-8"
                )
                return subprocess.CompletedProcess(argv, 0, "", "")
            raise AssertionError(command)

        with mock.patch("scripts.msandbox.session_auth.shutil.which", return_value="/opt/gh"), mock.patch(
            "scripts.msandbox.session_auth.subprocess.run", side_effect=run
        ):
            with self.assertRaisesRegex(SessionAuthError, "isolated Git config is unsafe"):
                refresh_github_auth(record)

        self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")

    def test_github_auth_fails_with_one_host_login_instruction(self) -> None:
        record = self.record()
        origin = subprocess.CompletedProcess(
            [], 0, "git@github.com:tajaa/matcha-recruit.git\n", ""
        )
        missing = subprocess.CompletedProcess([], 1, "", "not logged in")
        with mock.patch("scripts.msandbox.session_auth.shutil.which", return_value="/opt/gh"), mock.patch(
            "scripts.msandbox.session_auth.subprocess.run", side_effect=(origin, missing)
        ):
            with self.assertRaisesRegex(SessionAuthError, "gh auth login"):
                refresh_github_auth(record)

    def test_failed_pristine_startup_removes_all_session_state(self) -> None:
        with (
            mock.patch(
                "scripts.msandbox.sessions.start_session",
                side_effect=RuntimeError("container startup failed"),
            ),
            mock.patch("scripts.msandbox.sessions.stop_agent"),
            mock.patch("scripts.msandbox.sessions.remove_container_project") as remove,
            self.assertRaisesRegex(RuntimeError, "container startup failed"),
        ):
            create_session(self.repo, SessionSpec("failed-start", "codex", "main"))

        self.assertEqual(list_sessions(include_released=True), [])
        self.assertEqual(len(list_worktrees(self.repo)), 1)
        self.assertEqual(list((self.root / "data/git-sessions").glob("*")), [])
        remove.assert_called_once_with(mock.ANY, volumes=True)

    def test_cancelled_pristine_startup_removes_all_session_state(self) -> None:
        with (
            mock.patch(
                "scripts.msandbox.sessions.start_session",
                side_effect=KeyboardInterrupt,
            ),
            mock.patch("scripts.msandbox.sessions.stop_agent"),
            mock.patch("scripts.msandbox.sessions.remove_container_project") as remove,
            self.assertRaises(KeyboardInterrupt),
        ):
            create_session(self.repo, SessionSpec("cancelled-start", "codex", "main"))

        self.assertEqual(list_sessions(include_released=True), [])
        self.assertEqual(len(list_worktrees(self.repo)), 1)
        self.assertEqual(list((self.root / "data/git-sessions").glob("*")), [])
        remove.assert_called_once_with(mock.ANY, volumes=True)

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

    def test_github_ssh_remote_is_scoped_to_https_for_network_operations(self) -> None:
        self.assertEqual(
            github_https_url("git@github.com:tajaa/matcha-recruit.git"),
            "https://github.com/tajaa/matcha-recruit.git",
        )
        origin = subprocess.CompletedProcess(
            [], 0, "git@github.com:tajaa/matcha-recruit.git\n", ""
        )
        fetched = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch(
            "scripts.msandbox.git_worktrees._git", side_effect=(origin, fetched)
        ) as run:
            fetch_origin(self.repo, "main")
        command = run.call_args_list[1].args
        self.assertIn("url.https://github.com/.insteadOf=git@github.com:", command)
        self.assertEqual(command[-4:], ("fetch", "--prune", "origin", "main"))

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

    def test_legacy_drag_rewrites_into_workspace_attachment_mount(self) -> None:
        source = self.root / "prod screenshot.png"
        source.write_bytes(b"png")
        frame = PASTE_START + str(source).replace(" ", "\\ ").encode() + PASTE_END
        inbox = self.root / "legacy-inbox"

        emitted, pending = rewrite_paste_stream_to_inbox(
            frame,
            inbox=inbox,
            container_dir=Path("/workspace/.msandbox/attachments"),
            lock_name="legacy-test",
            max_bytes=1024,
            session_max_bytes=4096,
        )

        self.assertEqual(pending, b"")
        self.assertIn(b"/workspace/.msandbox/attachments/", emitted)
        imported = list(inbox.iterdir())
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0].read_bytes(), b"png")
        payload = emitted[len(PASTE_START) : -len(PASTE_END)].decode()
        self.assertEqual(
            shlex.split(payload),
            [str(Path("/workspace/.msandbox/attachments") / imported[0].name)],
        )

    def test_legacy_drag_error_preserves_frame_and_reports_without_raising(self) -> None:
        source = self.root / "oversized.png"
        source.write_bytes(b"too large")
        frame = PASTE_START + str(source).encode() + PASTE_END
        errors: list[AttachmentError] = []

        emitted, pending = rewrite_paste_stream_to_inbox(
            frame,
            inbox=self.root / "legacy-inbox",
            container_dir=Path("/workspace/.msandbox/attachments"),
            lock_name="legacy-error-test",
            max_bytes=1,
            session_max_bytes=4096,
            on_error=errors.append,
        )

        self.assertEqual(emitted, frame)
        self.assertEqual(pending, b"")
        self.assertEqual(len(errors), 1)
        self.assertIn("exceeds 1 bytes", str(errors[0]))

    def test_plain_macos_drag_path_is_rewritten_before_prompt_text(self) -> None:
        source = self.root / "Screenshot 2026 at 5.40 PM.png"
        source.write_bytes(b"png")
        payload = f"{source} what does this image show\r".encode()
        inbox = self.root / "legacy-inbox"

        emitted, pending = rewrite_paste_stream_to_inbox(
            payload,
            inbox=inbox,
            container_dir=Path("/workspace/.msandbox/attachments"),
            lock_name="plain-drag-test",
            max_bytes=1024,
            session_max_bytes=4096,
        )

        self.assertEqual(pending, b"")
        self.assertNotIn(str(source).encode(), emitted)
        self.assertIn(b"/workspace/.msandbox/attachments/", emitted)
        self.assertTrue(emitted.endswith(b" what does this image show\r"))

    def test_plain_shell_escaped_drag_waits_for_delimiter_across_reads(self) -> None:
        source = self.root / "Screen Shot.png"
        source.write_bytes(b"png")
        escaped = str(source).replace(" ", "\\ ").encode()
        inbox = self.root / "legacy-inbox"

        emitted, pending = rewrite_paste_stream_to_inbox(
            escaped,
            inbox=inbox,
            container_dir=Path("/workspace/.msandbox/attachments"),
            lock_name="plain-drag-split-test",
            max_bytes=1024,
            session_max_bytes=4096,
        )
        self.assertEqual(emitted, b"")
        self.assertEqual(pending, escaped)

        emitted, pending = rewrite_paste_stream_to_inbox(
            pending + b" describe it\r",
            inbox=inbox,
            container_dir=Path("/workspace/.msandbox/attachments"),
            lock_name="plain-drag-split-test",
            max_bytes=1024,
            session_max_bytes=4096,
        )
        self.assertEqual(pending, b"")
        self.assertIn(b"/workspace/.msandbox/attachments/", emitted)
        self.assertTrue(emitted.endswith(b" describe it\r"))

    def test_plain_drag_rewrites_when_terminal_delivers_one_byte_at_a_time(self) -> None:
        source = self.root / "Screenshot bytewise.png"
        source.write_bytes(b"png")
        payload = f"{source} whats in the screenshot\r".encode()
        inbox = self.root / "legacy-inbox"
        emitted = bytearray()
        pending = b""

        for byte in payload:
            chunk, pending = rewrite_paste_stream_to_inbox(
                pending + bytes([byte]),
                inbox=inbox,
                container_dir=Path("/workspace/.msandbox/attachments"),
                lock_name="plain-drag-bytewise-test",
                max_bytes=1024,
                session_max_bytes=4096,
            )
            emitted.extend(chunk)

        self.assertEqual(pending, b"")
        self.assertNotIn(str(source).encode(), emitted)
        self.assertIn(b"/workspace/.msandbox/attachments/", emitted)
        self.assertTrue(emitted.endswith(b" whats in the screenshot\r"))

    def test_nonexistent_plain_host_path_is_forwarded_on_enter(self) -> None:
        payload = b"/Users/example/missing.png explain this\r"

        emitted, pending = rewrite_paste_stream_with_importer(
            payload,
            lambda paths: self.fail(f"unexpected import: {paths}"),
        )

        self.assertEqual(emitted, payload)
        self.assertEqual(pending, b"")

    def test_proxy_copies_terminal_window_size(self) -> None:
        window_size = b"\x18\x00\x50\x00\x00\x00\x00\x00"
        with mock.patch("scripts.msandbox.pty_proxy.fcntl.ioctl") as ioctl:
            ioctl.return_value = window_size
            _sync_window_size(10, 11)

        self.assertEqual(
            ioctl.call_args_list,
            [
                mock.call(10, termios.TIOCGWINSZ, bytes(8)),
                mock.call(11, termios.TIOCSWINSZ, window_size),
            ],
        )

    def test_proxy_syncs_initial_and_resized_window(self) -> None:
        stdin = mock.Mock()
        stdin.isatty.return_value = True
        stdin.fileno.return_value = 10
        stdout = mock.Mock()
        stdout.isatty.return_value = True
        stdout.fileno.return_value = 11
        previous_handler = mock.sentinel.previous_handler

        with (
            mock.patch("scripts.msandbox.pty_proxy.sys.stdin", stdin),
            mock.patch("scripts.msandbox.pty_proxy.sys.stdout", stdout),
            mock.patch(
                "scripts.msandbox.pty_proxy.pty.fork",
                return_value=(321, 12),
            ),
            mock.patch("scripts.msandbox.pty_proxy.termios.tcgetattr", return_value=[]),
            mock.patch("scripts.msandbox.pty_proxy.termios.tcsetattr"),
            mock.patch("scripts.msandbox.pty_proxy.tty.setraw"),
            mock.patch(
                "scripts.msandbox.pty_proxy.select.select",
                return_value=([12], [], []),
            ),
            mock.patch("scripts.msandbox.pty_proxy.os.read", return_value=b""),
            mock.patch("scripts.msandbox.pty_proxy.os.close"),
            mock.patch("scripts.msandbox.pty_proxy.os.waitpid", return_value=(321, 0)),
            mock.patch(
                "scripts.msandbox.pty_proxy.signal.getsignal",
                return_value=previous_handler,
            ),
            mock.patch("scripts.msandbox.pty_proxy.signal.signal") as set_signal,
            mock.patch("scripts.msandbox.pty_proxy._sync_window_size") as sync_window,
        ):
            self.assertEqual(run_with_file_proxy(["true"], lambda data: (data, b"")), 0)
            resize_handler = set_signal.call_args_list[0].args[1]
            resize_handler(signal.SIGWINCH, None)

        self.assertEqual(
            sync_window.call_args_list,
            [mock.call(10, 12), mock.call(10, 12)],
        )
        self.assertEqual(
            set_signal.call_args_list[-1],
            mock.call(signal.SIGWINCH, previous_handler),
        )

    def test_legacy_interactive_entrypoints_use_file_proxy(self) -> None:
        launcher = (Path(__file__).resolve().parents[2] / "scripts/agent-sandbox.sh").read_text()
        self.assertIn("exec_workspace_with_file_proxy codex", launcher)
        self.assertIn("exec_workspace_with_file_proxy claude", launcher)
        self.assertIn("exec_workspace_with_file_proxy opencode", launcher)
        self.assertGreaterEqual(launcher.count("exec_workspace_with_file_proxy bash"), 2)
        self.assertIn("call_v2_controller session stop --all --force", launcher)
        self.assertIn("ensure_v2_system_plane", launcher)


class HostAndInstallTests(MsandboxTestCase):
    def test_terminal_menu_accepts_kitty_arrows_numbers_and_safe_cancel(self) -> None:
        self.assertEqual(_interpret_terminal_key(b"\x1b[A"), "up")
        self.assertEqual(_interpret_terminal_key(b"\x1b[B"), "down")
        self.assertEqual(_interpret_terminal_key(b"\x1b[1;1B"), "down")
        self.assertEqual(_interpret_terminal_key(b"2"), "2")

        attributes = [0, 0, 0, 0, 0, 0, []]
        with (
            mock.patch("scripts.msandbox.wizard.sys.stdin.fileno", return_value=12),
            mock.patch("scripts.msandbox.wizard.termios.tcgetattr", return_value=attributes),
            mock.patch("scripts.msandbox.wizard.termios.tcsetattr") as restore,
            mock.patch("scripts.msandbox.wizard.tty.setcbreak"),
            mock.patch(
                "scripts.msandbox.wizard._read_terminal_key",
                side_effect=("down", "enter"),
            ),
        ):
            selected = _choose_terminal(
                "Agent",
                (("Codex", "codex"), ("Claude", "claude"), ("Back", None)),
                output=io.StringIO(),
                default=1,
            )
        self.assertEqual(selected, "claude")
        restore.assert_called_once_with(12, termios.TCSADRAIN, attributes)

        self.assertFalse(
            choose(
                "Destructive confirmation",
                (("Cancel", False), ("Reclaim", True)),
                reader=lambda _prompt: "q",
                output=io.StringIO(),
            )
        )

    def test_initializer_creates_nested_cache_mountpoints_before_returning(self) -> None:
        entrypoint = (
            Path(__file__).resolve().parents[2] / "docker/agent-sandbox/entrypoint.sh"
        ).read_text(encoding="utf-8")
        mountpoint = entrypoint.index("/workspace/client/node_modules/.vite")
        initializer_return = entrypoint.index(
            'if [[ "${MSANDBOX_INITIALIZE_DEPENDENCIES:-0}" == "1" ]]'
        )
        self.assertLess(mountpoint, initializer_return)

    def test_agent_permission_profiles_are_explicit(self) -> None:
        self.assertEqual(agent_argv("codex"), ["codex"])
        self.assertEqual(
            agent_argv("codex", permission_mode="autonomous"),
            ["codex", "--dangerously-bypass-approvals-and-sandbox"],
        )
        self.assertEqual(agent_argv("claude"), ["claude"])
        self.assertEqual(
            agent_argv("claude", permission_mode="autonomous"),
            ["claude", "--dangerously-skip-permissions"],
        )
        self.assertEqual(agent_argv("opencode"), ["opencode"])
        self.assertEqual(
            agent_argv("opencode", permission_mode="autonomous"),
            ["opencode", "--auto"],
        )

    def test_agent_tmux_repairs_a_pruned_controller_working_directory(self) -> None:
        record = self.record()
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            mock.patch("scripts.msandbox.agent_adapters.shutil.which", return_value="/bin/tmux"),
            mock.patch(
                "scripts.msandbox.agent_adapters.tmux_running",
                side_effect=(False, True),
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.compose_command",
                return_value=["docker", "compose", "exec", "workspace", "codex"],
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.compose_environment",
                return_value={"SANDBOX_IMAGE": "workspace:test"},
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.time.monotonic",
                side_effect=(0.0, 2.0),
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            launch_agent(record)

        new_session = next(
            call.args[0]
            for call in run.call_args_list
            if call.args[0][:2] == ["tmux", "new-session"]
        )
        self.assertEqual(
            new_session[5:7],
            ["-c", str(record.worktree)],
        )
        self.assertTrue(
            new_session[-1].startswith(
                f"cd {shlex.quote(str(record.worktree))} && exec env "
            ),
            new_session[-1],
        )

    def test_wizard_requires_an_explicit_autonomous_choice(self) -> None:
        record = self.record()
        record.phase = "running"
        answers = iter(("", "2", "", "", "", "", ""))
        with mock.patch("scripts.msandbox.wizard.list_sessions", return_value=[]), mock.patch(
            "scripts.msandbox.wizard.create_session", return_value=record
        ) as create, mock.patch(
            "scripts.msandbox.wizard.ensure_capability_report", return_value=None
        ), mock.patch("scripts.msandbox.wizard.attach_agent") as attach:
            _new_session(
                self.repo,
                reader=lambda _prompt: next(answers),
                output=io.StringIO(),
            )
        spec = create.call_args.args[1]
        self.assertEqual(spec.permission_mode, "autonomous")
        self.assertTrue(spec.dev)
        self.assertFalse(spec.playwright)
        attach.assert_called_once_with(record)

    def test_wizard_defaults_to_standard_permissions(self) -> None:
        record = self.record()
        record.phase = "running"
        answers = iter(("", "", "", "", "", "", ""))
        with mock.patch("scripts.msandbox.wizard.list_sessions", return_value=[]), mock.patch(
            "scripts.msandbox.wizard.create_session", return_value=record
        ) as create, mock.patch(
            "scripts.msandbox.wizard.ensure_capability_report", return_value=None
        ), mock.patch("scripts.msandbox.wizard.attach_agent"):
            _new_session(
                self.repo,
                reader=lambda _prompt: next(answers),
                output=io.StringIO(),
            )
        self.assertEqual(create.call_args.args[1].permission_mode, "standard")

    def test_wizard_generates_names_and_can_exit_without_side_effects(self) -> None:
        first = self.record("one")
        first.name = "codex"
        second = self.record("two")
        second.name = "codex-2"
        self.assertEqual(next_session_name("codex", [first, second]), "codex-3")
        with mock.patch("scripts.msandbox.wizard.list_sessions", return_value=[]):
            self.assertEqual(
                run_wizard(
                    self.repo,
                    reader=lambda _prompt: "5",
                    output=io.StringIO(),
                ),
                0,
            )

    def test_wizard_keeps_action_errors_visible_until_acknowledged(self) -> None:
        prompts: list[str] = []

        def acknowledge(prompt: str) -> str:
            prompts.append(prompt)
            return ""

        with mock.patch(
            "scripts.msandbox.wizard.list_sessions", return_value=[]
        ), mock.patch(
            "scripts.msandbox.wizard.choose",
            side_effect=(("new", None), ("exit", None)),
        ), mock.patch(
            "scripts.msandbox.wizard._new_session",
            side_effect=RuntimeError("fetch failed"),
        ):
            output = io.StringIO()
            self.assertEqual(
                run_wizard(self.repo, reader=acknowledge, output=output),
                0,
            )
        self.assertIn("Could not complete that action: fetch failed", output.getvalue())
        self.assertEqual(prompts, ["\nPress Enter to return to Matcha Sandbox..."])

    def test_shell_handoff_atomically_replaces_a_session_symlink(self) -> None:
        record = self.record()
        home = self.root / "data/homes/session-1"
        home.mkdir(parents=True)
        victim = self.root / "victim"
        victim.write_text("untouched\n", encoding="utf-8")
        destination = home / ".msandbox-wizard.bash"
        destination.symlink_to(victim)

        container_path = _install_session_shell_handoff(record)

        self.assertEqual(container_path, "/home/agent/.msandbox-wizard.bash")
        self.assertFalse(destination.is_symlink())
        self.assertIn("exit 86", destination.read_text(encoding="utf-8"))
        self.assertEqual(victim.read_text(encoding="utf-8"), "untouched\n")

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
            record.playwright = True
            browser = compose_environment(record)
            record.playwright = False
            entrypoint = runtime_root / "docker/agent-sandbox/entrypoint.sh"
            entrypoint.write_text(
                entrypoint.read_text(encoding="utf-8") + "\n# toolchain revision\n",
                encoding="utf-8",
            )
            toolchain_changed = compose_environment(record)
            (fixture / "client/package.json").write_text("{}\n", encoding="utf-8")
            second = compose_environment(record)
        self.assertEqual(browser["SANDBOX_BASE_IMAGE"], first["SANDBOX_IMAGE"])
        self.assertNotEqual(browser["SANDBOX_IMAGE"], first["SANDBOX_IMAGE"])
        self.assertEqual(
            browser["SANDBOX_CLIENT_NODE_MODULES_VOLUME"],
            first["SANDBOX_CLIENT_NODE_MODULES_VOLUME"],
        )
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
        self.assertTrue((release / "scripts/msandbox/wizard-shell.bash").is_file())
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
        self.assertEqual(completed.stdout.strip(), "msandbox 2.0.1")
        launcher_text = launcher.read_text(encoding="utf-8")
        self.assertIn("scripts/agent-sandbox.sh", launcher_text)
        self.assertIn("legacy control plane", launcher_text)
        self.assertEqual(rollback_release(release.name, bin_dir=bin_dir), release)
        with self.assertRaises(InstallError):
            rollback_release("../escape", bin_dir=bin_dir)

    def test_installed_launcher_routes_legacy_control_plane_commands(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        fixture = self.root / "controller-repo"
        (fixture / "scripts").mkdir(parents=True)
        shutil.copy2(project_root / "scripts/__init__.py", fixture / "scripts/__init__.py")
        shutil.copytree(project_root / "scripts/msandbox", fixture / "scripts/msandbox")
        legacy = fixture / "scripts/agent-sandbox.sh"
        legacy.write_text(
            '#!/bin/sh\n'
            'if [ "$*" = "autopr-ready" ]; then exit "${MSANDBOX_TEST_READY_RC:-0}"; fi\n'
            'if [ "$*" = "system up" ] && [ -n "${MSANDBOX_TEST_UP_MARKER:-}" ]; then : > "$MSANDBOX_TEST_UP_MARKER"; fi\n'
            'if [ "${MSANDBOX_TEST_FAIL_UP:-0}" = 1 ] && [ "$*" = "system up" ]; then exit 42; fi\n'
            'printf "legacy:%s\\n" "$*"\n',
            encoding="utf-8",
        )
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
        bare_environment = dict(os.environ)
        up_marker = self.root / "system-up-called"
        bare_environment["MSANDBOX_TEST_UP_MARKER"] = str(up_marker)
        bare = subprocess.run(
            [str(bin_dir / "msandbox")],
            check=True,
            text=True,
            capture_output=True,
            env=bare_environment,
        )
        self.assertTrue(up_marker.is_file())
        self.assertIn("msandbox + AutoPR ready", bare.stdout)
        self.assertNotIn("legacy:system up", bare.stdout)
        self.assertIn("No active msandbox sessions", bare.stdout)
        failed_environment = dict(os.environ)
        failed_environment["MSANDBOX_TEST_FAIL_UP"] = "1"
        failed_bare = subprocess.run(
            [str(bin_dir / "msandbox")],
            check=False,
            text=True,
            capture_output=True,
            env=failed_environment,
        )
        self.assertEqual(failed_bare.returncode, 42)
        self.assertNotIn("msandbox + AutoPR ready", failed_bare.stdout)
        self.assertNotIn("No active msandbox sessions", failed_bare.stdout)
        interactive_environment = dict(os.environ)
        interactive_marker = self.root / "interactive-system-up-called"
        interactive_environment["MSANDBOX_TEST_READY_RC"] = "1"
        interactive_environment["MSANDBOX_TEST_UP_MARKER"] = str(interactive_marker)
        wizard = subprocess.run(
            [str(bin_dir / "msandbox"), "wizard"],
            check=True,
            text=True,
            capture_output=True,
            env=interactive_environment,
        )
        self.assertTrue(interactive_marker.is_file())
        self.assertIn("legacy:system up", wizard.stdout)
        interactive_marker.unlink()
        repo_wizard = subprocess.run(
            [str(bin_dir / "msandbox"), "--repo", str(fixture), "wizard"],
            check=True,
            text=True,
            capture_output=True,
            env=interactive_environment,
        )
        self.assertTrue(interactive_marker.is_file())
        self.assertIn("legacy:system up", repo_wizard.stdout)
        interactive_marker.unlink()
        missing = subprocess.run(
            [
                str(bin_dir / "msandbox"),
                f"--repo={fixture}",
                "session",
                "start",
                "missing",
            ],
            check=False,
            text=True,
            capture_output=True,
            env=interactive_environment,
        )
        self.assertTrue(interactive_marker.is_file())
        self.assertEqual(missing.returncode, 1)
        self.assertIn("unknown msandbox session", missing.stderr)
        # `gc` is a v2 verb, so it must not fall through to the legacy script.
        garbage_environment = dict(os.environ)
        garbage_environment["PATH"] = str(Path(sys.executable).parent)
        garbage = subprocess.run(
            [str(bin_dir / "msandbox"), "gc"],
            check=False,
            text=True,
            capture_output=True,
            env=garbage_environment,
        )
        self.assertEqual(garbage.returncode, 1)
        self.assertIn("docker is not available", garbage.stdout)
        self.assertNotIn("legacy:", garbage.stdout)

    def test_install_retains_only_current_and_one_rollback_release(self) -> None:
        bin_dir = self.root / "bin"
        project_root = Path(__file__).resolve().parents[2]
        with mock.patch(
            "scripts.msandbox.install._release_id",
            side_effect=(
                "release-one",
                "release-two",
                "release-three",
                "release-three",
            ),
        ):
            install_release(repo_root=project_root, bin_dir=bin_dir)
            second = install_release(repo_root=project_root, bin_dir=bin_dir)
            third = install_release(repo_root=project_root, bin_dir=bin_dir)
            install_release(repo_root=project_root, bin_dir=bin_dir)

        releases = self.root / "data/releases"
        self.assertEqual(
            {entry.name for entry in releases.iterdir()},
            {second.name, third.name},
        )
        self.assertEqual(rollback_release(second.name, bin_dir=bin_dir), second)
        with self.assertRaises(InstallError):
            rollback_release("release-one", bin_dir=bin_dir)

    def test_content_addressed_image_is_reused_without_rebuilding(self) -> None:
        environment = {"SANDBOX_IMAGE": "matcha-agent-sandbox-workspace:content"}
        record = self.record()
        with mock.patch(
            "scripts.msandbox.docker_runtime._image_exists", return_value=True
        ), mock.patch("scripts.msandbox.docker_runtime._ensure_builder") as builder, mock.patch(
            "scripts.msandbox.docker_runtime.subprocess.run"
        ) as run:
            built = _ensure_workspace_image(
                record, environment, test_services=False
            )
        self.assertFalse(built)
        builder.assert_not_called()
        run.assert_not_called()

    def test_missing_image_uses_the_bounded_private_builder(self) -> None:
        environment = {"SANDBOX_IMAGE": "matcha-agent-sandbox-workspace:content"}
        record = self.record()
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch(
            "scripts.msandbox.docker_runtime._image_exists", return_value=False
        ), mock.patch(
            "scripts.msandbox.docker_runtime._ensure_builder", return_value=BUILDER_NAME
        ), mock.patch(
            "scripts.msandbox.docker_runtime.subprocess.run", return_value=completed
        ) as run, mock.patch(
            "scripts.msandbox.docker_runtime._prune_builder_cache"
        ) as prune:
            built = _ensure_workspace_image(
                record, environment, test_services=False
            )
        self.assertTrue(built)
        command = run.call_args.args[0]
        self.assertIn("build", command)
        self.assertEqual(command[command.index("--builder") + 1], BUILDER_NAME)
        prune.assert_called_once_with()

    def test_missing_image_falls_back_to_builtin_builder(self) -> None:
        environment = {"SANDBOX_IMAGE": "matcha-agent-sandbox-workspace:content"}
        record = self.record()
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch(
            "scripts.msandbox.docker_runtime._image_exists", return_value=False
        ), mock.patch(
            "scripts.msandbox.docker_runtime._ensure_builder", return_value=None
        ), mock.patch(
            "scripts.msandbox.docker_runtime.subprocess.run", return_value=completed
        ) as run, mock.patch(
            "scripts.msandbox.docker_runtime._prune_builder_cache"
        ) as prune:
            built = _ensure_workspace_image(
                record, environment, test_services=False
            )
        self.assertTrue(built)
        command = run.call_args.args[0]
        self.assertIn("build", command)
        self.assertNotIn("--builder", command)
        prune.assert_not_called()

    def test_browser_image_layers_onto_existing_workspace(self) -> None:
        context = self.root / "browser-context"
        overlay = context / "docker/agent-sandbox/Dockerfile.browser"
        overlay.parent.mkdir(parents=True)
        overlay.write_text("ARG SANDBOX_BASE_IMAGE\n", encoding="utf-8")
        environment = {
            "SANDBOX_IMAGE": "matcha-agent-sandbox-workspace:browser",
            "SANDBOX_BASE_IMAGE": "matcha-agent-sandbox-workspace:base",
            "SANDBOX_BUILD_CONTEXT": str(context),
        }
        record = self.record()
        record.playwright = True
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch(
            "scripts.msandbox.docker_runtime._image_exists",
            side_effect=(False, True),
        ), mock.patch(
            "scripts.msandbox.docker_runtime._ensure_builder", return_value=BUILDER_NAME
        ), mock.patch(
            "scripts.msandbox.docker_runtime.subprocess.run", return_value=completed
        ) as run, mock.patch(
            "scripts.msandbox.docker_runtime._prune_builder_cache"
        ) as prune:
            built = _ensure_workspace_image(
                record, environment, test_services=False
            )
        self.assertTrue(built)
        self.assertEqual(run.call_count, 1)
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["docker", "buildx", "build"])
        self.assertNotIn("--builder", command)
        self.assertIn(
            "SANDBOX_BASE_IMAGE=matcha-agent-sandbox-workspace:base",
            command,
        )
        self.assertIn("matcha-agent-sandbox-workspace:browser", command)
        prune.assert_called_once_with()

    def test_private_builder_bootstrap_timeout_falls_back(self) -> None:
        inspected = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch(
            "scripts.msandbox.docker_runtime.subprocess.run",
            side_effect=(
                inspected,
                subprocess.TimeoutExpired([], BUILDER_BOOTSTRAP_TIMEOUT_S),
            ),
        ) as run, mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            builder = _ensure_builder()
        self.assertIsNone(builder)
        self.assertEqual(run.call_count, 2)
        self.assertIn("built-in builder", stderr.getvalue())

    def test_private_builder_cache_has_a_small_default_ceiling(self) -> None:
        with mock.patch(
            "scripts.msandbox.docker_runtime.subprocess.run"
        ) as run, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MSANDBOX_BUILD_CACHE_MAX", None)
            _prune_builder_cache()
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--builder") + 1], BUILDER_NAME)
        self.assertEqual(
            command[command.index("--max-used-space") + 1],
            DEFAULT_BUILD_CACHE_MAX,
        )
        self.assertEqual(DEFAULT_BUILD_CACHE_MAX, "2GB")


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


class FakeDocker:
    """Stand-in for the docker CLI, dispatching on the argv docker_gc builds."""

    def __init__(
        self,
        *,
        images: tuple[str, ...] = (),
        volumes: tuple[str, ...] = (),
        containers: tuple[tuple[str, str, str, str], ...] = (),
        mounts: dict[str, tuple[str, ...]] | None = None,
        binds: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.images = list(images)
        self.volumes = list(volumes)
        self.containers = list(containers)
        self.mounts = dict(mounts or {})
        self.binds = dict(binds or {})
        self.removed: list[tuple[str, ...]] = []

    def __call__(self, *argv: str) -> subprocess.CompletedProcess[str]:
        out = ""
        if argv[:2] == ("ps", "--all"):
            out = "\n".join("\t".join(row) for row in self.containers)
        elif argv[:2] == ("container", "inspect"):
            out = json.dumps(
                [
                    {
                        "Name": f"/{name}",
                        "Mounts": [
                            {
                                "Type": "volume",
                                "Name": volume,
                                "Source": f"/var/lib/docker/volumes/{volume}/_data",
                            }
                            for volume in self.mounts.get(name, ())
                        ]
                        + [
                            {"Type": "bind", "Name": "", "Source": source}
                            for source in self.binds.get(name, ())
                        ],
                    }
                    for name in argv[2:]
                ]
            )
        elif argv[0] == "images":
            out = "\n".join(self.images)
        elif argv[:2] == ("volume", "ls"):
            out = "\n".join(self.volumes)
        elif argv[0] == "rmi":
            self.removed.append(argv)
            self.images = [item for item in self.images if item != argv[1]]
        elif argv[:2] == ("volume", "rm"):
            self.removed.append(argv)
            self.volumes = [item for item in self.volumes if item != argv[2]]
        elif argv[0] == "rm":
            self.removed.append(argv)
            self.containers = [row for row in self.containers if row[0] != argv[1]]
        else:  # pragma: no cover - an argv shape the collector does not build
            raise AssertionError(f"unexpected docker invocation: {argv}")
        return subprocess.CompletedProcess(list(argv), 0, out, "")


class DockerGcTests(MsandboxTestCase):
    MANIFESTS = (
        "server/requirements.txt",
        "client/package.json",
        "client/package-lock.json",
        "client/tellus/package.json",
        "client/tellus/package-lock.json",
        "client/oceanlab/package.json",
        "client/oceanlab/package-lock.json",
    )

    def sandbox_tree(self, root: Path, marker: str) -> Path:
        directory = root / "docker/agent-sandbox"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "Dockerfile").write_text(f"FROM scratch # {marker}\n", encoding="utf-8")
        (directory / "Dockerfile.browser").write_text(
            f"ARG SANDBOX_BASE_IMAGE\nFROM ${{SANDBOX_BASE_IMAGE}} # {marker}\n",
            encoding="utf-8",
        )
        (directory / "Dockerfile.dockerignore").write_text("*\n", encoding="utf-8")
        (directory / "entrypoint.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        return root

    def worktree_manifests(self, worktree: Path) -> Path:
        for relative in self.MANIFESTS:
            path = worktree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        return worktree

    def live_session(self, session_id: str = "live-1") -> SessionRecord:
        record = self.record(session_id)
        self.worktree_manifests(record.worktree)
        save_session(record)
        return record

    def test_live_session_artifacts_are_reachable_and_stale_ones_are_not(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        record = self.live_session()
        live = reachable(self.repo)
        self.assertTrue(live.complete)
        # One tag per (root, playwright) pair, plus the protected :latest.
        self.assertIn("matcha-agent-sandbox-workspace:latest", live.images)
        self.assertEqual(len(live.images), 3)
        self.assertEqual(len(live.volumes), 4)
        self.assertIn(record.compose_project, live.projects)
        self.assertTrue(live.covers_volume(f"{record.compose_project}_sandbox_npm_cache"))
        self.assertFalse(live.covers_volume("matcha-ms-dead-9999_sandbox_npm_cache"))

    def test_protected_lanes_survive_with_zero_session_records(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        docker = FakeDocker(
            images=("matcha-agent-sandbox-workspace:latest", "matcha-agent-sandbox-workspace:deadbeef"),
            volumes=(
                "matcha-agent-sandbox_sandbox_home",
                "matcha-kanban-autopr-sandbox_sandbox_home",
                "matcha-kanban-autopr-sandbox_sandbox_npm_cache",
                "matcha-ms-dead-9999_sandbox_npm_cache",
            ),
            containers=(
                ("matcha-agent-sandbox-workspace-1", "exited", "matcha-agent-sandbox-workspace:latest", "matcha-agent-sandbox"),
            ),
        )
        with mock.patch("scripts.msandbox.docker_gc._docker", docker), mock.patch(
            "scripts.msandbox.docker_gc.shutil.which", return_value="/usr/bin/docker"
        ):
            report = collect_garbage(self.repo, apply=True)
        collected = {(item.kind, item.name) for item in report.collected}
        self.assertEqual(
            collected,
            {("image", "matcha-agent-sandbox-workspace:deadbeef"),
             ("volume", "matcha-kanban-autopr-sandbox_sandbox_npm_cache"),
             ("volume", "matcha-ms-dead-9999_sandbox_npm_cache")},
        )
        # The lane with no SessionRecord keeps its login volume and its image.
        self.assertIn("matcha-agent-sandbox_sandbox_home", docker.volumes)
        self.assertIn("matcha-kanban-autopr-sandbox_sandbox_home", docker.volumes)
        self.assertIn("matcha-agent-sandbox-workspace:latest", docker.images)
        self.assertEqual(
            docker.containers,
            [("matcha-agent-sandbox-workspace-1", "exited", "matcha-agent-sandbox-workspace:latest", "matcha-agent-sandbox")],
        )

    def test_rollback_release_sources_do_not_pin_multi_gigabyte_images(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        releases = self.root / "data/releases"
        for name in ("release-old", "release-new"):
            self.sandbox_tree(releases / name, name)
        record = self.live_session()
        live = reachable(self.repo)
        self.assertEqual(runtime_roots(self.repo), [self.repo.resolve()])
        # Active root x two Playwright variants, plus protected :latest.
        self.assertEqual(len(live.images), 3)
        for root in (releases / "release-old", releases / "release-new"):
            identifier = build_identifier(
                build_context_sources(record, root), playwright=False
            )
            self.assertNotIn(f"matcha-agent-sandbox-workspace:{identifier}", live.images)

    def test_shared_dependency_volume_is_matched_by_name_not_compose_label(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        record = self.live_session()
        live = reachable(self.repo)
        shared = sorted(live.volumes)[0]
        docker = FakeDocker(
            images=("matcha-agent-sandbox-workspace:latest",),
            volumes=(shared, "matcha-ms-dead-9999_sandbox_npm_cache"),
            # The volume still carries the compose label of the dead project
            # that happened to create it first; selecting by label would delete
            # a volume the live session depends on.
            containers=(
                ("matcha-ms-dead-9999-workspace-1", "exited", "matcha-agent-sandbox-workspace:deadbeef", "matcha-ms-dead-9999"),
            ),
        )
        with mock.patch("scripts.msandbox.docker_gc._docker", docker), mock.patch(
            "scripts.msandbox.docker_gc.shutil.which", return_value="/usr/bin/docker"
        ):
            report = collect_garbage(self.repo, apply=True)
        self.assertIn(shared, docker.volumes)
        self.assertNotIn(("volume", shared), {(item.kind, item.name) for item in report.collected})
        self.assertIn(("container", "matcha-ms-dead-9999-workspace-1"), {(i.kind, i.name) for i in report.collected})

    def test_dry_run_reports_without_removing_anything(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        (self.root / "data/homes/orphan").mkdir(parents=True)
        docker = FakeDocker(
            images=("matcha-agent-sandbox-workspace:deadbeef",),
            volumes=("matcha-ms-dead-9999_sandbox_npm_cache",),
            containers=(
                ("matcha-ms-dead-9999-workspace-1", "exited", "matcha-agent-sandbox-workspace:deadbeef", "matcha-ms-dead-9999"),
            ),
        )
        with mock.patch("scripts.msandbox.docker_gc._docker", docker), mock.patch(
            "scripts.msandbox.docker_gc.shutil.which", return_value="/usr/bin/docker"
        ):
            report = collect_garbage(self.repo, apply=False)
        self.assertEqual(docker.removed, [])
        self.assertIn("matcha-agent-sandbox-workspace:deadbeef", docker.images)
        self.assertTrue((self.root / "data/homes/orphan").is_dir())
        self.assertEqual(
            {(item.kind, item.name) for item in report.collected},
            {
                ("container", "matcha-ms-dead-9999-workspace-1"),
                ("image", "matcha-agent-sandbox-workspace:deadbeef"),
                ("volume", "matcha-ms-dead-9999_sandbox_npm_cache"),
                ("session-home", "orphan"),
            },
        )

    def test_unreadable_build_inputs_collect_nothing(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        # A live session whose worktree lost its lockfiles makes every image
        # indistinguishable from garbage; GC must refuse rather than guess.
        save_session(self.record("broken-1"))
        docker = FakeDocker(images=("matcha-agent-sandbox-workspace:deadbeef",))
        with mock.patch("scripts.msandbox.docker_gc._docker", docker), mock.patch(
            "scripts.msandbox.docker_gc.shutil.which", return_value="/usr/bin/docker"
        ):
            report = collect_garbage(self.repo, apply=True)
        self.assertIsNotNone(report.skipped)
        self.assertEqual(docker.removed, [])
        self.assertIn("matcha-agent-sandbox-workspace:deadbeef", docker.images)

    def test_invalid_session_record_makes_reachability_incomplete(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        invalid = self.root / "state/sessions/live-corrupt/session.json"
        invalid.parent.mkdir(parents=True)
        invalid.write_text("{not-json\n", encoding="utf-8")
        home = self.root / "data/homes/live-corrupt"
        home.mkdir(parents=True)
        docker = FakeDocker(
            images=("matcha-agent-sandbox-workspace:deadbeef",),
            volumes=("matcha-ms-dead-9999_sandbox_npm_cache",),
        )
        with mock.patch("scripts.msandbox.docker_gc._docker", docker), mock.patch(
            "scripts.msandbox.docker_gc.shutil.which", return_value="/usr/bin/docker"
        ):
            report = collect_garbage(self.repo, apply=True)
        self.assertIn("invalid session record", report.skipped or "")
        self.assertEqual(docker.removed, [])
        self.assertTrue(home.is_dir())

    def test_docker_inventory_failure_aborts_before_host_cleanup(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        home = self.root / "data/homes/orphan"
        home.mkdir(parents=True)
        docker = FakeDocker(
            images=("matcha-agent-sandbox-workspace:deadbeef",),
            containers=(
                (
                    "matcha-ms-dead-workspace-1",
                    "exited",
                    "matcha-agent-sandbox-workspace:deadbeef",
                    "matcha-ms-dead",
                ),
            ),
        )

        def failed_inventory(*argv: str) -> subprocess.CompletedProcess[str]:
            if argv[0] == "images":
                return subprocess.CompletedProcess(list(argv), 1, "", "daemon unavailable")
            return docker(*argv)

        with mock.patch(
            "scripts.msandbox.docker_gc._docker", side_effect=failed_inventory
        ), mock.patch(
            "scripts.msandbox.docker_gc.shutil.which", return_value="/usr/bin/docker"
        ):
            report = collect_garbage(self.repo, apply=True)
        self.assertIn("Docker inventory is incomplete", report.skipped or "")
        self.assertEqual(docker.removed, [])
        self.assertTrue(home.is_dir())

    def test_running_orphan_container_protects_its_bind_mounted_home(self) -> None:
        self.sandbox_tree(self.repo, "repo")
        running_home = self.root / "data/homes/running-orphan"
        stale_home = self.root / "data/homes/stale-orphan"
        running_home.mkdir(parents=True)
        stale_home.mkdir(parents=True)
        container = "matcha-ms-running-orphan-workspace-1"
        mounted_volume = "matcha-ms-running-orphan_sandbox_npm_cache"
        docker = FakeDocker(
            images=("matcha-agent-sandbox-workspace:deadbeef",),
            volumes=(mounted_volume,),
            containers=(
                (
                    container,
                    "running",
                    "matcha-agent-sandbox-workspace:deadbeef",
                    "matcha-ms-running-orphan",
                ),
            ),
            mounts={container: (mounted_volume,)},
            binds={container: (str(running_home),)},
        )
        with mock.patch("scripts.msandbox.docker_gc._docker", docker), mock.patch(
            "scripts.msandbox.docker_gc.shutil.which", return_value="/usr/bin/docker"
        ):
            report = collect_garbage(self.repo, apply=True)
        self.assertTrue(running_home.is_dir())
        self.assertFalse(stale_home.exists())
        self.assertIn(mounted_volume, docker.volumes)
        self.assertIn("matcha-agent-sandbox-workspace:deadbeef", docker.images)
        self.assertIn(
            ("session-home", "stale-orphan"),
            {(item.kind, item.name) for item in report.collected},
        )


class FakeContainer:
    """Answer container probes by matching a substring of the probe script."""

    def __init__(self, responses, default=(1, "", "not configured")):
        self.responses = list(responses)
        self.default = default
        self.scripts: list[str] = []

    def __call__(self, record, argv, *, tty, capture=False, timeout=None, login_shell=False):
        script = argv[-1]
        self.scripts.append(script)
        for needle, code, out, err in self.responses:
            if callable(needle):
                if needle(script):
                    return subprocess.CompletedProcess(argv, code, out, err)
                continue
            if needle in script:
                if isinstance(code, BaseException):
                    raise code
                return subprocess.CompletedProcess(argv, code, out, err)
        return subprocess.CompletedProcess(argv, *self.default)


def fake_host(argv, **kwargs):
    if argv[:1] == ["xcodebuild"]:
        return subprocess.CompletedProcess(argv, 0, "Xcode 26.1\nBuild version 17B55\n", "")
    if "port" in argv:
        return subprocess.CompletedProcess(argv, 0, "127.0.0.1:18001\n", "")
    return subprocess.CompletedProcess(argv, 1, "", "unsupported host probe")


HEALTHY_CONTAINER = (
    ("git -C /workspace rev-parse", 0, "abc1234\n", ""),
    ("python3 --version", 0, "Python 3.12.7\nv22.23.2\n10.9.2\npytest 8.3.2\n3.2.4\n", ""),
    ("test -x scripts/dev-remote.sh", 0, "", ""),
    ("import socket, sys", 0, "PORTS ok\nDB ok\n", ""),
    ("sync_playwright", 0, "141.0.7390.37\n", ""),
    ("/attachments/", 0, "", ""),
    ("gh auth status", 0, "octocat\nexample/matcha push=true admin=false\n", ""),
    # The profile sweep asks STS which profiles authenticate; it names both the
    # sts and configure commands, so it is matched before either of them.
    ("AWS_RETRY_MODE", 0, "", ""),
    ("aws sts get-caller-identity", 0,
     '{"Arn": "arn:aws:iam::123456789012:role/matcha-msandbox"}', ""),
    ("service=matcha_prod_test", 0, "matcha_test_agent\n0\n", ""),
    ("urllib.request", 0, "primary\nTrue\n", ""),
    ("ssh -o BatchMode=yes", 0, "", ""),
    ("test -e", 0, "", ""),
)


class CapabilityTests(MsandboxTestCase):
    def setUp(self) -> None:
        super().setUp()
        git(self.repo, "remote", "set-url", "origin", "https://github.com/example/matcha.git")

    def session(self, *, dev: bool = True, playwright: bool = True, agent: str = "codex"):
        record = self.record()
        record.agent = agent
        record.dev = dev
        record.playwright = playwright
        record.ports = PortSet(18001, 15174, 15191, 15201, 18080)
        return record

    def configure_production_credentials(self) -> None:
        root = self.root / "config/production-test"
        (root / "ssh").mkdir(parents=True, exist_ok=True)
        (root / "accounts.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "base_url": "https://hey-matcha.com",
                    "accounts": [
                        {
                            "label": "primary",
                            "email": "builder@example.com",
                            "password_file": "accounts/primary.password",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "pg_service.conf").write_text("[matcha_prod_test]\n", encoding="utf-8")
        (root / "ssh/matcha-prod-test").write_text("restricted-key-placeholder\n", encoding="utf-8")

    def collect(self, record, responses=HEALTHY_CONTAINER, **kwargs):
        container = FakeContainer(responses)
        report = collect_report(
            record,
            run_container=container,
            run_host=fake_host,
            **kwargs,
        )
        return report, container

    # -- full and partial reports ------------------------------------------

    def test_full_report_renders_checks_and_explicit_denials(self) -> None:
        self.configure_production_credentials()
        record = self.session()
        report, _ = self.collect(record)
        statuses = {item.id: item.status for item in report.results}
        self.assertEqual(
            statuses,
            {
                "repo_rw": "available",
                "linux_build": "available",
                "isolated_dev": "available",
                "browser": "available",
                "attachments": "available",
                "github": "available",
                "aws": "available",
                "prod_test_api": "available",
                "prod_test_db": "available",
                "prod_diagnostics": "available",
                # Xcode is measured on the host; no builder broker is installed
                # in the test root, so it is honestly unavailable.
                "xcode": "unavailable",
                # Nothing documented is reachable in this fixture, so the
                # by-design host mount reads as an honest cross.
                "host_credentials": "unavailable",
                "non_test_mutation": "denied",
                "prod_admin": "denied",
                "code_signing": "denied",
            },
        )
        self.assertTrue(report_ok(report))
        rendered = render_report_text(report, name=record.name)
        self.assertIn("✅ Repository read/write", rendered)
        self.assertIn("❌ Non-test tenant mutation", rendered)
        self.assertIn("is_test enforced", rendered)

    def test_unconfigured_production_access_is_an_honest_cross(self) -> None:
        record = self.session()
        report, _ = self.collect(record)
        for capability in ("prod_test_api", "prod_test_db", "prod_diagnostics"):
            result = report.by_id(capability)
            self.assertEqual(result.status, "unavailable")
            self.assertIn("configured", result.detail)
        # A denial without a production identity is still a denial, not a leak.
        self.assertEqual(report.by_id("non_test_mutation").status, "denied")
        self.assertTrue(report_ok(report))

    def test_capability_choices_are_reported_rather_than_assumed(self) -> None:
        record = self.session(dev=False, playwright=False)
        report, container = self.collect(record)
        self.assertEqual(report.by_id("browser").status, "unavailable")
        self.assertEqual(report.by_id("isolated_dev").status, "unavailable")
        # A capability the session never had must not cost a container probe.
        self.assertFalse(any("sync_playwright" in script for script in container.scripts))

    # -- a probe must exercise the boundary it claims ----------------------

    def test_a_read_only_workspace_is_never_reported_as_writable(self) -> None:
        refused = tuple(
            item for item in HEALTHY_CONTAINER if item[0] != "git -C /workspace rev-parse"
        ) + (
            (
                "git -C /workspace rev-parse",
                1,
                "",
                "mktemp: cannot create '/workspace/.msandbox-write-probe.XXXXXX': Read-only file system",
            ),
        )
        report, _ = self.collect(self.session(), refused)
        self.assertEqual(report.by_id("repo_rw").status, "unavailable")
        self.assertFalse(report_ok(report))
        # The shape a swallowed failure produces: exit 0 with nothing to show.
        quiet = tuple(
            item for item in HEALTHY_CONTAINER if item[0] != "git -C /workspace rev-parse"
        ) + (("git -C /workspace rev-parse", 0, "", ""),)
        silent, _ = self.collect(self.session(), quiet)
        self.assertEqual(silent.by_id("repo_rw").status, "unavailable")
        self.assertNotIn("unknown", silent.by_id("repo_rw").detail)

    def test_deploy_authority_is_measured_on_the_token_not_assumed_absent(self) -> None:
        report, _ = self.collect(self.session())
        github = report.by_id("github")
        # The push-capable token can dispatch deploy.yml and merge a PR. The
        # report says so rather than letting a denial claim otherwise.
        self.assertIn("workflow dispatch and merge are reachable", github.detail)
        signing = report.by_id("code_signing")
        self.assertEqual(signing.status, "denied")
        self.assertNotIn("merge", signing.title.lower())
        self.assertNotIn("deploy", signing.detail.lower())
        readonly = tuple(item for item in HEALTHY_CONTAINER if item[0] != "gh auth status") + (
            ("gh auth status", 0, "octocat\nexample/matcha push=false admin=false\n", ""),
        )
        limited, _ = self.collect(self.session(), readonly)
        self.assertIn("read-only", limited.by_id("github").detail)

    def test_isolated_development_is_measured_not_inferred_from_a_flag(self) -> None:
        busy = tuple(item for item in HEALTHY_CONTAINER if item[0] != "import socket, sys") + (
            ("import socket, sys", 1, "BUSY 18001 Address already in use\n", ""),
        )
        report, _ = self.collect(self.session(), busy)
        self.assertEqual(report.by_id("isolated_dev").status, "unavailable")
        self.assertIn("BUSY 18001", report.by_id("isolated_dev").detail)
        healthy, container = self.collect(self.session())
        self.assertEqual(healthy.by_id("isolated_dev").status, "available")
        self.assertIn("127.0.0.1:18001", healthy.by_id("isolated_dev").detail)
        self.assertTrue(any("host.docker.internal" in script for script in container.scripts))
        # The bind test uses the container-side ports; the host publication is
        # the Mac-facing half of the same mapping.
        bind = next(script for script in container.scripts if "import socket, sys" in script)
        self.assertIn("(8001, 5174, 5191, 5201)", bind)
        self.assertNotIn("18001", bind)

    def test_a_stale_builder_socket_is_not_an_xcode_capability(self) -> None:
        socket_path = native_builder_socket()
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        # A file at the path proves nothing; only an answering socket does.
        socket_path.write_text("", encoding="utf-8")
        report, _ = self.collect(self.session())
        result = report.by_id("xcode")
        self.assertEqual(result.status, "unavailable")
        self.assertIn("stale", result.detail)

    def test_production_is_queried_once_per_report(self) -> None:
        self.configure_production_credentials()
        _, container = self.collect(self.session())
        # prod_test_db and the non_test_mutation denial share one measurement.
        self.assertEqual(
            sum("service=matcha_prod_test" in script for script in container.scripts), 1
        )

    def test_the_container_credential_path_is_derived_from_one_constant(self) -> None:
        self.assertIn(repr(CONTAINER_CONFIG_DIR), _PROD_TEST_API_SCRIPT)
        self.assertIn(repr(PRODUCTION_TEST_DIR), _PROD_TEST_API_SCRIPT)
        # The host gate resolves the same directory through config_root(), which
        # honours MSANDBOX_CONFIG_DIR; neither side may retype the path.
        self.assertNotIn("pathlib.Path.home()", _PROD_TEST_API_SCRIPT)

    def test_a_report_without_results_renders_instead_of_crashing(self) -> None:
        empty = CapabilityReport(
            schema_version=1,
            session_id="session-1",
            results=(),
            checked_at=utc_now(),
        )
        rendered = render_report_text(empty, name="empty")
        self.assertIn("no capability was measured", rendered)

    def test_the_create_screen_plan_comes_from_the_registry(self) -> None:
        planned = planned_capabilities(dev=True, playwright=True)
        rendered = "\n".join(planned)
        width = max(len(probe.title) for probe in probe_registry()) + 2
        for probe in probe_registry():
            self.assertIn(probe.title, rendered)
            row = next((line for line in planned if line.startswith(f"  ") and probe.title in line), None)
            if row is None:
                # Measured only after the session starts; named in the footnote.
                continue
            tail = row[row.index(probe.title) + width:]
            self.assertTrue(tail, f"{probe.title} row has no detail")
            self.assertFalse(tail.startswith(" "), f"{probe.title} column is misaligned")

    # -- probe failure modes ----------------------------------------------

    def test_probe_failures_never_abort_the_report(self) -> None:
        self.configure_production_credentials()
        responses = (
            ("git -C /workspace rev-parse", 0, "abc1234\n", ""),
            ("python3 --version", subprocess.TimeoutExpired(["bash"], 90.0), "", ""),
            ("test -x scripts/dev-remote.sh", 0, "", ""),
            ("sync_playwright", 127, "", "bash: playwright: command not found"),
            ("/attachments/", 0, "", ""),
            ("gh auth status", 1, "", "gh: authentication failed"),
            ("aws sts get-caller-identity", 0, "not json at all", ""),
            ("service=matcha_prod_test", 1, "", "FATAL: password authentication failed"),
            ("urllib.request", 1, "", "HTTP Error 401: Unauthorized"),
            ("ssh -o BatchMode=yes", 255, "", "Permission denied (publickey)"),
            ("AWS_RETRY_MODE", 0, "", ""),
            ("test -e", 0, "", ""),
        )
        report, _ = self.collect(self.session(), responses)
        self.assertEqual(len(report.results), len(probe_registry()))
        self.assertEqual(report.by_id("linux_build").detail, "the probe exceeded its timeout")
        self.assertEqual(report.by_id("browser").status, "unavailable")
        self.assertEqual(report.by_id("github").status, "unavailable")
        self.assertEqual(report.by_id("aws").status, "unavailable")
        self.assertEqual(report.by_id("prod_test_db").status, "unavailable")
        self.assertEqual(report.by_id("prod_test_api").status, "unavailable")
        # A failed production probe must never be read as production access.
        self.assertEqual(report.by_id("non_test_mutation").status, "denied")
        self.assertFalse(report_ok(report))

    def test_a_stopped_container_reports_every_container_probe_honestly(self) -> None:
        report, container = self.collect(self.session(), container_available=False)
        self.assertEqual(container.scripts, [])
        self.assertEqual(
            report.by_id("repo_rw").detail, "the session container is not running"
        )
        self.assertEqual(report.by_id("prod_admin").status, "denied")
        self.assertEqual(report.by_id("xcode").status, "unavailable")

    def test_a_missing_host_executable_is_a_fallback_not_a_crash(self) -> None:
        def missing_xcodebuild(argv, **kwargs):
            raise FileNotFoundError(argv[0])

        report = collect_report(
            self.session(),
            run_container=FakeContainer(HEALTHY_CONTAINER),
            run_host=missing_xcodebuild,
        )
        result = report.by_id("xcode")
        self.assertEqual(result.status, "unavailable")
        self.assertIn("native-builds", result.detail)

    # -- redaction ---------------------------------------------------------

    def test_probe_output_is_redacted_before_it_enters_the_report(self) -> None:
        secretive = (
            "ghp_0123456789abcdefghijABCDEFGHIJ0123 "
            "AKIAIOSFODNN7EXAMPLE "
            "password=hunter2 "
            "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha "
            "Authorization: Bearer abcdef.ghijkl "
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
        )
        responses = (("gh auth status", 1, "", secretive),)
        report, _ = self.collect(self.session(), responses)
        detail = report.by_id("github").detail
        for leaked in (
            "ghp_0123456789abcdefghijABCDEFGHIJ0123",
            "AKIAIOSFODNN7EXAMPLE",
            "hunter2",
            "matcha_dev",
            "MIIEow",
            "abcdef.ghijkl",
        ):
            self.assertNotIn(leaked, detail)
        serialized = json.dumps(report.to_dict())
        for leaked in ("ghp_0123", "AKIAIOSFODNN7EXAMPLE", "hunter2", "matcha_dev"):
            self.assertNotIn(leaked, serialized)

    def test_an_aws_account_number_never_reaches_the_report(self) -> None:
        report, _ = self.collect(self.session())
        self.assertNotIn("123456789012", report.by_id("aws").detail)
        self.assertIn("matcha-msandbox", report.by_id("aws").detail)

    # -- session record compatibility --------------------------------------

    def test_records_written_before_capability_reporting_still_load(self) -> None:
        raw = self.record().to_dict()
        raw.pop("last_capability_check_at")
        raw.pop("capability_report_path")
        restored = SessionRecord.from_dict(raw)
        self.assertIsNone(restored.last_capability_check_at)
        self.assertIsNone(restored.capability_report_path)
        save_session(restored)
        self.assertIsNone(load_session(restored.id).capability_report_path)

    # -- persistence and agent context -------------------------------------

    def test_the_agent_receives_the_same_report_the_picker_shows(self) -> None:
        for agent, relative in (
            ("codex", ".codex/AGENTS.md"),
            ("opencode", ".config/opencode/AGENTS.md"),
        ):
            with self.subTest(agent=agent):
                record = self.session(agent=agent)
                expected = collect_report(
                    record,
                    run_container=FakeContainer(HEALTHY_CONTAINER),
                    run_host=fake_host,
                )
                with mock.patch(
                    "scripts.msandbox.agent_adapters.collect_report", return_value=expected
                ):
                    report = refresh_capability_context(record)
                self.assertIsNotNone(report)
                json_path, markdown_path = report_paths(record)
                self.assertEqual(json_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(markdown_path.stat().st_mode & 0o777, 0o600)
                markdown = markdown_path.read_text(encoding="utf-8")
                self.assertIn(
                    "This capability report was measured for this session. Test the "
                    "named invocation before claiming the capability is absent.",
                    markdown,
                )
                self.assertIn("gh pr view", markdown)
                self.assertIn("psql 'service=matcha_prod_test'", markdown)
                delivered = session_home(record) / relative
                self.assertEqual(delivered.read_text(encoding="utf-8"), markdown)
                self.assertEqual(record.capability_report_path, str(json_path))
                self.assertEqual(record.last_capability_check_at, report.checked_at)
                round_tripped = load_report(record)
                self.assertEqual(round_tripped, expected)

    def test_claude_is_not_given_the_report_twice(self) -> None:
        record = self.session(agent="claude")
        expected = collect_report(
            record,
            run_container=FakeContainer(HEALTHY_CONTAINER),
            run_host=fake_host,
        )
        with mock.patch(
            "scripts.msandbox.agent_adapters.collect_report", return_value=expected
        ):
            self.assertIsNotNone(refresh_capability_context(record))
        _, markdown_path = report_paths(record)
        self.assertTrue(markdown_path.is_file())
        # The flag already loads this content at startup; writing the user-level
        # memory file too would put the same report in context twice.
        self.assertFalse((session_home(record) / ".claude/CLAUDE.md").exists())
        self.assertIn("--append-system-prompt-file", capability_context_args("claude"))

    def test_a_rejected_context_flag_falls_back_to_the_memory_file(self) -> None:
        record = self.session(agent="claude")
        expected = collect_report(
            record,
            run_container=FakeContainer(HEALTHY_CONTAINER),
            run_host=fake_host,
        )
        with mock.patch(
            "scripts.msandbox.agent_adapters.collect_report", return_value=expected
        ):
            refresh_capability_context(record)
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            mock.patch("scripts.msandbox.agent_adapters.shutil.which", return_value="/bin/tmux"),
            # An agent that rejects the flag exits immediately, so the pane is
            # dead when the launcher checks it: the first attempt raises and the
            # retry without the flag succeeds.
            mock.patch(
                "scripts.msandbox.agent_adapters.tmux_running",
                side_effect=(False, False, True),
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.compose_command",
                return_value=["docker", "compose", "exec", "workspace", "claude"],
            ) as compose,
            mock.patch(
                "scripts.msandbox.agent_adapters.compose_environment",
                return_value={"SANDBOX_IMAGE": "workspace:test"},
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.time.monotonic",
                side_effect=(0.0, 2.0, 0.0, 2.0),
            ),
            mock.patch(
                "scripts.msandbox.agent_adapters.subprocess.run", return_value=completed
            ) as run,
        ):
            launch_agent(record)
        started = [
            call.args[0]
            for call in run.call_args_list
            if call.args[0][:2] == ["tmux", "new-session"]
        ]
        self.assertEqual(len(started), 2)
        attempts = [list(call.args) for call in compose.call_args_list]
        self.assertIn("--append-system-prompt-file", attempts[0])
        self.assertNotIn("--append-system-prompt-file", attempts[1])
        delivered = session_home(record) / ".claude/CLAUDE.md"
        self.assertEqual(
            delivered.read_text(encoding="utf-8"),
            report_paths(record)[1].read_text(encoding="utf-8"),
        )

    def test_the_agent_context_file_is_published_without_a_symlink_hop(self) -> None:
        record = self.session(agent="codex")
        instructions = session_home(record) / ".codex/AGENTS.md"
        instructions.parent.mkdir(parents=True, exist_ok=True)
        outside = self.root / "outside.md"
        outside.write_text("untouched", encoding="utf-8")
        instructions.symlink_to(outside)
        expected = collect_report(
            record,
            run_container=FakeContainer(HEALTHY_CONTAINER),
            run_host=fake_host,
        )
        with mock.patch(
            "scripts.msandbox.agent_adapters.collect_report", return_value=expected
        ):
            refresh_capability_context(record)
        self.assertEqual(outside.read_text(encoding="utf-8"), "untouched")
        self.assertFalse(instructions.is_symlink())
        self.assertEqual(instructions.stat().st_mode & 0o777, 0o600)
        # No fixed-name temp file survives a publish.
        leftovers = sorted(
            item.name for item in instructions.parent.iterdir() if item.name.startswith(".AGENTS")
        )
        self.assertEqual(leftovers, [])

    def test_claude_receives_the_report_through_its_system_prompt_flag(self) -> None:
        self.assertEqual(
            capability_context_args("claude"),
            ["--append-system-prompt-file", "/home/agent/.msandbox/capabilities.md"],
        )
        self.assertEqual(capability_context_args("codex"), [])
        self.assertEqual(capability_context_args("opencode"), [])

    def test_no_credential_value_reaches_the_agent_context(self) -> None:
        self.configure_production_credentials()
        record = self.session()
        expected = collect_report(
            record,
            run_container=FakeContainer(HEALTHY_CONTAINER),
            run_host=fake_host,
        )
        markdown = render_markdown(expected, name=record.name)
        for forbidden in ("password", "PRIVATE KEY", "ghp_", "AKIA", "123456789012"):
            self.assertNotIn(forbidden, markdown)

    # -- picker and doctor share one registry -------------------------------

    def test_the_picker_shows_a_measured_report_before_the_agent_opens(self) -> None:
        record = self.session()
        save_session(record)
        report, _ = self.collect(record)
        write_report(record, report)
        # A menu redraw must not launch Chromium, hit GitHub, and query
        # production before it can print its first line.
        with mock.patch(
            "scripts.msandbox.wizard.ensure_capability_report"
        ) as measured:
            title = _session_menu_title(record)
        measured.assert_not_called()
        self.assertIn("test — codex / standard / created", title)
        self.assertIn("✅ GitHub CLI", title)
        self.assertIn("❌ Production admin/secrets", title)
        # The report was measured with the container up; this session is not.
        self.assertIn("measured while the container was running", title)

    def test_an_unmeasured_session_asks_for_a_measurement_instead_of_guessing(self) -> None:
        record = self.session()
        save_session(record)
        with mock.patch("scripts.msandbox.wizard.ensure_capability_report") as measured:
            title = _session_menu_title(record)
        measured.assert_not_called()
        self.assertIn("have not been measured yet", title)

    def test_opening_a_running_session_attaches_without_remeasuring(self) -> None:
        record = self.session()
        record.phase = "running"
        save_session(record)
        with mock.patch(
            "scripts.msandbox.wizard.choose", side_effect=["open", "back"]
        ), mock.patch(
            "scripts.msandbox.wizard.reconcile_session", side_effect=lambda item: item
        ), mock.patch("scripts.msandbox.wizard.attach_agent") as attach, mock.patch(
            "scripts.msandbox.wizard.start_session"
        ) as started, mock.patch(
            "scripts.msandbox.wizard.ensure_capability_report"
        ) as measured:
            _open_session(record, reader=lambda prompt: "", output=io.StringIO())
        attach.assert_called_once()
        started.assert_not_called()
        # The live agent read its context at startup; rewriting the report
        # cannot reach that process, so the attach must not pay for a remeasure.
        measured.assert_not_called()

    def test_refresh_capabilities_is_an_explicit_menu_action(self) -> None:
        record = self.session()
        save_session(record)
        report, _ = self.collect(record)
        output = io.StringIO()
        with mock.patch(
            "scripts.msandbox.wizard.choose", side_effect=["capabilities", "back"]
        ), mock.patch(
            "scripts.msandbox.wizard.reconcile_session", side_effect=lambda item: item
        ), mock.patch(
            "scripts.msandbox.wizard.ensure_capability_report", return_value=report
        ) as measured:
            _open_session(record, reader=lambda prompt: "", output=output)
        self.assertEqual(measured.call_args.kwargs, {"refresh": True})
        self.assertIn("✅ Repository read/write", output.getvalue())

    def test_the_new_session_screen_shows_what_it_plans_to_measure(self) -> None:
        planned = "\n".join(planned_capabilities(dev=True, playwright=False))
        self.assertIn("✅ Repository read/write", planned)
        self.assertIn("❌ Headless browser", planned)
        self.assertIn("❌ Production admin/secrets", planned)
        self.assertIn(
            "✅ Isolated development",
            "\n".join(planned_capabilities(dev=True, playwright=True)),
        )

    def test_doctor_reuses_the_shared_registry_and_reports_its_result(self) -> None:
        record = self.session()
        save_session(record)
        report, _ = self.collect(record)
        output = io.StringIO()
        with mock.patch(
            "scripts.msandbox.cli.ensure_capability_report", return_value=report
        ) as shared, redirect_stdout(output):
            self.assertEqual(run_cli(["--repo", str(self.repo), "doctor", record.name]), 0)
        shared.assert_called_once()
        self.assertEqual(shared.call_args.kwargs, {"refresh": True})
        self.assertIn("✅ Linux build tools", output.getvalue())

    def test_capabilities_command_prefers_a_fresh_cached_report(self) -> None:
        record = self.session()
        save_session(record)
        report, _ = self.collect(record)
        write_report(record, report)
        output = io.StringIO()
        with mock.patch(
            "scripts.msandbox.sessions.container_running", return_value=True
        ), mock.patch(
            "scripts.msandbox.sessions.ensure_container"
        ) as ensure, mock.patch(
            "scripts.msandbox.agent_adapters.collect_report"
        ) as remeasured, redirect_stdout(output):
            self.assertEqual(
                run_cli(["--repo", str(self.repo), "capabilities", record.name]), 0
            )
        ensure.assert_not_called()
        remeasured.assert_not_called()
        self.assertIn("✅ Repository read/write", output.getvalue())

    def test_a_cached_report_is_dropped_when_the_container_stopped(self) -> None:
        record = self.session()
        save_session(record)
        report, _ = self.collect(record)
        write_report(record, report)
        self.assertTrue(load_report(record).container_available)
        with mock.patch(
            "scripts.msandbox.sessions.container_running", return_value=False
        ), mock.patch("scripts.msandbox.sessions.ensure_container") as ensure, mock.patch(
            "scripts.msandbox.agent_adapters.collect_report",
            side_effect=lambda item, container_available=True: collect_report(
                item,
                run_container=FakeContainer(HEALTHY_CONTAINER),
                run_host=fake_host,
                container_available=container_available,
            ),
        ):
            fresh = ensure_capability_report(record)
        # Age said the report was fresh; the container it described is gone.
        ensure.assert_not_called()
        self.assertEqual(fresh.by_id("repo_rw").status, "unavailable")
        self.assertFalse(fresh.container_available)

    def test_refresh_repairs_session_auth_before_it_measures(self) -> None:
        record = self.session()
        save_session(record)
        with mock.patch(
            "scripts.msandbox.sessions.container_running", return_value=True
        ), mock.patch(
            "scripts.msandbox.sessions.refresh_github_auth"
        ) as auth, mock.patch(
            "scripts.msandbox.sessions.ensure_container"
        ) as ensure, mock.patch(
            "scripts.msandbox.agent_adapters.collect_report",
            side_effect=lambda item, container_available=True: collect_report(
                item,
                run_container=FakeContainer(HEALTHY_CONTAINER),
                run_host=fake_host,
                container_available=container_available,
            ),
        ):
            self.assertIsNotNone(ensure_capability_report(record, refresh=True))
        # An expired in-container gh token is renewed, not reported as a
        # required capability that failed.
        auth.assert_called_once()
        ensure.assert_called_once()

    def test_redrawing_the_picker_never_starts_a_container(self) -> None:
        record = self.session()
        save_session(record)
        with mock.patch(
            "scripts.msandbox.sessions.container_running", return_value=False
        ), mock.patch("scripts.msandbox.sessions.ensure_container") as ensure, mock.patch(
            "scripts.msandbox.sessions.refresh_github_auth"
        ) as auth, mock.patch(
            "scripts.msandbox.agent_adapters.collect_report",
            side_effect=lambda item, container_available=True: collect_report(
                item,
                run_container=FakeContainer(HEALTHY_CONTAINER),
                run_host=fake_host,
                container_available=container_available,
            ),
        ) as collected:
            report = ensure_capability_report(record)
        ensure.assert_not_called()
        auth.assert_not_called()
        self.assertEqual(collected.call_args.kwargs, {"container_available": False})
        self.assertEqual(report.by_id("repo_rw").status, "unavailable")

    # -- leaks --------------------------------------------------------------

    def test_an_undocumented_host_credential_turns_the_whole_result_red(self) -> None:
        responses = tuple(item for item in HEALTHY_CONTAINER if item[0] != "test -e") + (
            (
                "test -e",
                0,
                "LEAK /var/run/docker.sock\nLEAK /home/agent/.ssh/roonMT-arm.pem\n",
                "",
            ),
        )
        record = self.session()
        save_session(record)
        report, _ = self.collect(record, responses)
        leaked = report.by_id("prod_admin")
        self.assertEqual(leaked.status, "available")
        self.assertIn("docker.sock", leaked.detail)
        self.assertEqual({item.id for item in leaks(report)}, {"prod_admin", "code_signing"})
        self.assertFalse(report_ok(report))
        rendered = render_report_text(report, name=record.name)
        self.assertIn("⚠️", rendered)
        self.assertIn("LEAK: Production admin/secrets", rendered)
        output = io.StringIO()
        with mock.patch(
            "scripts.msandbox.cli.ensure_capability_report", return_value=report
        ), redirect_stdout(output):
            self.assertEqual(run_cli(["--repo", str(self.repo), "doctor", record.name]), 1)

    def test_the_documented_host_mount_is_a_warning_not_a_leak(self) -> None:
        # docker-compose.sandbox.yml mounts the repo and ~/.aws on purpose. A
        # healthy interactive session must not fail its own doctor for that.
        responses = (
            ("AWS_RETRY_MODE", 0, "AWS default\n", ""),
            (
                lambda script: "/workspace/secrets/roonMT-arm.pem" in script,
                0,
                "LEAK /workspace/secrets/roonMT-arm.pem\nLEAK /workspace/server/.env\n",
                "",
            ),
            ("test -e", 0, "", ""),
        ) + tuple(
            item for item in HEALTHY_CONTAINER if item[0] not in ("test -e", "AWS_RETRY_MODE")
        )
        record = self.session()
        report, _ = self.collect(record, responses)
        reachable = report.by_id("host_credentials")
        self.assertEqual(reachable.status, "available")
        self.assertIn("roonMT-arm.pem", reachable.detail)
        self.assertIn("default", reachable.detail)
        self.assertEqual(report.by_id("prod_admin").status, "denied")
        self.assertEqual(leaks(report), ())
        self.assertTrue(report_ok(report))
        rendered = render_report_text(report, name=record.name)
        self.assertIn("⚠️ Host credentials in reach", rendered)
        self.assertNotIn("LEAK", rendered)
        markdown = render_markdown(report, name=record.name)
        self.assertIn("Reachable by design — operator-gated", markdown)

    def test_a_named_aws_profile_is_not_authority_until_sts_answers(self) -> None:
        responses = (
            # The profile exists in the mounted config but authenticates to
            # nothing, so it is configuration, not a reachable identity.
            ("AWS_RETRY_MODE", 0, "", ""),
        ) + tuple(item for item in HEALTHY_CONTAINER if item[0] != "AWS_RETRY_MODE")
        report, _ = self.collect(self.session(), responses)
        self.assertEqual(report.by_id("host_credentials").status, "unavailable")
        self.assertTrue(report_ok(report))

    def test_a_visible_non_test_company_is_a_leak_not_a_capability(self) -> None:
        self.configure_production_credentials()
        responses = tuple(
            item for item in HEALTHY_CONTAINER if item[0] != "service=matcha_prod_test"
        ) + (("service=matcha_prod_test", 0, "matcha_test_agent\n41\n", ""),)
        report, _ = self.collect(self.session(), responses)
        self.assertEqual(report.by_id("prod_test_db").status, "unavailable")
        self.assertEqual(report.by_id("non_test_mutation").status, "available")
        self.assertFalse(report_ok(report))


if __name__ == "__main__":
    unittest.main()
