from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .agent_adapters import attach_agent, deliver_attachments
from .attachments import AttachmentError, import_clipboard, import_files
from .capabilities import render_report_text, report_ok
from .docker_gc import collect_garbage
from .docker_runtime import ensure_container, exec_in_session
from .git_worktrees import detach_branch_owner, prune_stale_worktree_metadata, resolve_worktree_owner
from .install import install_release, rollback_release
from .models import SessionSpec
from .session_auth import refresh_github_auth
from .sessions import (
    SessionError,
    _github_repo,
    create_session,
    ensure_capability_report,
    reconcile_session,
    release_session,
    resolve_pr,
    start_session,
    stop_session,
    submit_session,
)
from .state import ensure_roots, list_sessions, load_session, save_session
from .validation import build_test_plan, run_test_plan
from .wizard import run_wizard


def default_repo() -> Path:
    configured = os.environ.get("MATCHA_REPO_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()
    return Path(__file__).resolve().parents[2]


def _session_table(records: list) -> None:
    if not records:
        print("No active msandbox sessions.")
        return
    print(f"{'NAME':24} {'AGENT':10} {'PERMISSIONS':12} {'STATE':24} {'PR':7} WORKTREE")
    for record in records:
        pr = f"#{record.pr_number}" if record.pr_number else "-"
        print(
            f"{record.name[:24]:24} {record.agent:10} {record.permission_mode:12} "
            f"{record.phase:24} {pr:7} {record.worktree_path}"
        )


def _add_session_subcommands(parent: argparse._SubParsersAction) -> None:
    session = parent.add_parser("session", help="manage independent agent sessions")
    commands = session.add_subparsers(dest="session_command", required=True)
    create = commands.add_parser("create")
    create.add_argument("name")
    create.add_argument("--agent", choices=("codex", "opencode", "claude"), required=True)
    create.add_argument("--base", default="origin/main")
    create.add_argument("--pr", type=int)
    create.add_argument("--dev", action="store_true")
    create.add_argument("--playwright", action="store_true")
    create.add_argument(
        "--autonomous",
        action="store_true",
        help="explicitly bypass the selected agent's approval checks",
    )
    create.add_argument("--no-start", action="store_true")
    create.add_argument("--no-attach", action="store_true")
    session_list = commands.add_parser("list")
    session_list.add_argument("--all", action="store_true")
    commands.add_parser("has-running", help=argparse.SUPPRESS)
    for name in ("attach", "shell", "stop", "start", "release"):
        command = commands.add_parser(name)
        if name == "stop":
            command.add_argument("session", nargs="?")
            command.add_argument(
                "--all",
                action="store_true",
                help="stop every independent session without releasing its worktree",
            )
            command.add_argument("--force", action="store_true")
        else:
            command.add_argument("session")
        if name == "release":
            command.add_argument("--keep-worktree", action="store_true")
    execute = commands.add_parser("exec")
    execute.add_argument("session")
    execute.add_argument("argv", nargs=argparse.REMAINDER)
    submit = commands.add_parser("submit")
    submit.add_argument("session")
    submit.add_argument("--draft", action=argparse.BooleanOptionalAction, default=True)
    submit.add_argument("--title")


def build_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="msandbox")
    result.add_argument("--repo", type=Path, default=default_repo())
    result.add_argument("--version", action="version", version=f"msandbox {__version__}")
    commands = result.add_subparsers(dest="command")
    _add_session_subcommands(commands)

    attach = commands.add_parser("attach", help="import files for one session")
    attach.add_argument("session")
    attach.add_argument("files", nargs="+")
    attach.add_argument("--send", action="store_true")
    attach.add_argument("--prompt")
    paste = commands.add_parser("paste", help="import Finder files or clipboard image")
    paste.add_argument("session")
    paste.add_argument("--send", action="store_true")
    paste.add_argument("--prompt")

    test = commands.add_parser("test", help="run session validation")
    test.add_argument("session")
    modes = test.add_mutually_exclusive_group(required=True)
    modes.add_argument("--changed", action="store_true")
    modes.add_argument("--pr", action="store_true")
    modes.add_argument("--all", action="store_true")
    test.add_argument("--browser", action="store_true")
    test.add_argument("--xcode", choices=("affected", "all"))

    doctor = commands.add_parser("doctor")
    doctor.add_argument("session", nargs="?")
    capabilities = commands.add_parser(
        "capabilities", help="show this session's measured capability report"
    )
    capabilities.add_argument("session")
    capabilities.add_argument("--refresh", action="store_true")
    worktree = commands.add_parser("worktree")
    worktree_commands = worktree.add_subparsers(dest="worktree_command", required=True)
    worktree_commands.add_parser("doctor")
    gc = worktree_commands.add_parser("gc")
    gc.add_argument("--apply", action="store_true")
    docker_gc = commands.add_parser("gc", help="reclaim unreachable sandbox images and volumes")
    docker_gc.add_argument("--apply", action="store_true")
    pr = commands.add_parser("pr")
    pr_commands = pr.add_subparsers(dest="pr_command", required=True)
    checkout = pr_commands.add_parser("checkout")
    checkout.add_argument("number", type=int)
    install = commands.add_parser("install")
    install.add_argument("--rollback")
    commands.add_parser("wizard", help="open the interactive session manager")
    return result


def _doctor(record) -> int:
    report = ensure_capability_report(record, refresh=True)
    print(render_report_text(report, name=record.name))
    return 0 if report is not None and report_ok(report) else 1


def _checkout_pr(repo: Path, number: int) -> int:
    branch, _ = resolve_pr(repo, number)
    owner = resolve_worktree_owner(repo, branch)
    if owner:
        if not owner.managed:
            raise SessionError(
                f"PR branch {branch} is owned by foreign worktree {owner.path}; "
                "use Codex Handoff or explicitly detach it"
            )
        released = detach_branch_owner(repo, owner)
        if not released.released:
            raise SessionError(f"cannot release {owner.path}: {released.reason}")
    dirty = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), "status", "--porcelain=v1"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if dirty:
        raise SessionError("main checkout has uncommitted changes")
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/dev/null",
        }
    )
    return subprocess.run(
        ["gh", "pr", "checkout", str(number), "--repo", _github_repo(repo)],
        env=environment,
        check=False,
    ).returncode


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_roots()
    repo = args.repo.resolve()
    if args.command is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            return run_wizard(repo)
        _session_table([reconcile_session(item) for item in list_sessions()])
        print("\nRun `msandbox` in an interactive terminal to open the wizard.")
        return 0
    if args.command == "wizard":
        return run_wizard(repo)
    if args.command == "session":
        if args.session_command == "create":
            record = create_session(
                repo,
                SessionSpec(
                    name=args.name,
                    agent=args.agent,
                    base_ref=args.base,
                    pr_number=args.pr,
                    dev=args.dev,
                    playwright=args.playwright,
                    start=not args.no_start,
                    permission_mode="autonomous" if args.autonomous else "standard",
                ),
                (),
            )
            print(f"Created {record.name}: {record.worktree_path}")
            if record.ports:
                print("Ports: " + json.dumps(asdict(record.ports), sort_keys=True))
            if record.phase == "running" and not args.no_attach:
                return attach_agent(record)
            return 0
        if args.session_command == "list":
            _session_table(
                [reconcile_session(item) for item in list_sessions(include_released=args.all)]
            )
            return 0
        if args.session_command == "has-running":
            records = [reconcile_session(item) for item in list_sessions()]
            return 0 if any(item.phase == "running" for item in records) else 1
        if args.session_command == "stop" and args.all:
            if args.session:
                raise SessionError("session stop accepts either SESSION or --all, not both")
            failures: list[str] = []
            stopped = 0
            for record in list_sessions():
                try:
                    stop_session(record, force=args.force)
                    stopped += 1
                except Exception as exc:  # Keep stopping the remaining independent sessions.
                    failures.append(f"{record.name}: {exc}")
            print(f"Stopped {stopped} independent msandbox session(s).")
            if failures:
                raise SessionError("could not stop every session: " + "; ".join(failures))
            return 0
        if args.session_command == "stop" and not args.session:
            raise SessionError("session stop requires SESSION or --all")
        record = load_session(args.session)
        if args.session_command == "attach":
            return attach_agent(record)
        if args.session_command == "shell":
            refresh_github_auth(record)
            ensure_container(record)
            return exec_in_session(record, ["bash"], tty=True).returncode
        if args.session_command == "exec":
            if not args.argv:
                raise SessionError("session exec requires a command after --")
            refresh_github_auth(record)
            ensure_container(record)
            command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            return exec_in_session(record, command, tty=False).returncode
        if args.session_command == "stop":
            stop_session(record, force=args.force)
            return 0
        if args.session_command == "start":
            start_session(record)
            return 0
        if args.session_command == "submit":
            pull_request = submit_session(record, draft=args.draft, title=args.title)
            print(f"PR #{pull_request.number}: {pull_request.url}")
            return 0
        if args.session_command == "release":
            released = release_session(record, keep_worktree=args.keep_worktree)
            print(released.reason)
            return 0 if released.released else 1
    if args.command in ("attach", "paste"):
        record = load_session(args.session)
        attachments = (
            import_files(record, [Path(value) for value in args.files])
            if args.command == "attach"
            else import_clipboard(record)
        )
        for attachment in attachments:
            print(attachment.container_path)
        if args.send:
            deliver_attachments(record, attachments, args.prompt)
        return 0
    if args.command == "test":
        record = load_session(args.session)
        if args.browser and not record.playwright:
            # `--browser` is an explicit request to pay the larger image cost;
            # persist it so subsequent validation and agent restarts reuse the
            # same content-addressed Playwright-capable image.
            record.playwright = True
            save_session(record)
        mode = "changed" if args.changed else "pr" if args.pr else "all"
        plan = build_test_plan(record, mode, browser=args.browser, xcode=args.xcode)
        report = run_test_plan(record, plan)
        for item in report.results:
            print(f"[{item.status.upper():11}] {item.title} ({item.duration_seconds:.1f}s)")
        print(f"Report: {report.result_path}")
        return 0 if report.status == "pass" else 1
    if args.command == "capabilities":
        record = load_session(args.session)
        report = ensure_capability_report(record, refresh=args.refresh)
        print(render_report_text(report, name=record.name))
        return 0 if report is not None and report_ok(report) else 1
    if args.command == "doctor":
        if args.session:
            return _doctor(load_session(args.session))
        _session_table([reconcile_session(item) for item in list_sessions()])
        return 0
    if args.command == "worktree":
        stale = prune_stale_worktree_metadata(
            repo,
            apply=args.worktree_command == "gc" and args.apply,
        )
        if not stale:
            print("No stale worktree metadata.")
        for path in stale:
            print(f"{'pruned' if getattr(args, 'apply', False) else 'stale'}: {path}")
        return 0
    if args.command == "gc":
        report = collect_garbage(repo, apply=args.apply)
        if report.skipped:
            print(f"Collected nothing: {report.skipped}")
            return 1
        if not report:
            print("No unreachable sandbox images, volumes or containers.")
        for item in report.collected:
            print(f"{'reclaimed' if args.apply else 'unreachable'} {item.kind}: {item.name}")
        for item in report.failed:
            print(f"failed {item.kind}: {item.name} ({item.detail})")
        return 1 if report.failed else 0
    if args.command == "pr":
        return _checkout_pr(repo, args.number)
    if args.command == "install":
        installed = rollback_release(args.rollback) if args.rollback else install_release(repo_root=repo)
        print(f"Installed msandbox {__version__}: {installed}")
        return 0
    return 2


def main() -> None:
    try:
        raise SystemExit(run())
    except (SessionError, AttachmentError, KeyError, RuntimeError) as exc:
        print(f"msandbox: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
