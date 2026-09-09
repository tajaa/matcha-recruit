"""Operator screens layered over the sandbox's existing lifecycle contracts."""

from __future__ import annotations

import mimetypes
import shlex
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .agent_adapters import deliver_attachments
from .attachments import import_clipboard, import_files
from .capabilities import load_report, render_report_text, report_is_stale
from .files import export_file, list_files, read_file
from .inspection import inspect_session
from .models import Attachment, SessionRecord
from .publication import apply_draft, generate_draft, load_draft, save_draft
from .sessions import ensure_capability_report, submit_session, switch_session
from .terminal_ui import plain
from .tool_actions import tool_action


def show(text: str, *, reader, output) -> None:
    """Long details get a scrollable pager, never push navigation off-screen."""
    if reader is input and output.isatty() and shutil.which("less"):
        subprocess.run(
            ["less", "-X", "-F"], input=plain(text) + "\n", text=True, check=False
        )
    else:
        print(plain(text), file=output)
        reader("\nEnter to return...")


def manage(
    action: str, record: SessionRecord, *, reader=input, output=sys.stdout
) -> None:
    # Import at dispatch time: wizard owns only navigation primitives.
    from .wizard import choose

    def pick(title, choices, default=1):
        return choose(title, choices, reader=reader, output=output, default=default)

    def view(text):
        show(text, reader=reader, output=output)

    if action == "switch":
        selected = pick(
            f"{record.name} / Change harness\nFiles and commits stay. Conversations remain separate.\nThe workspace stops before switching; permissions stay the same.",
            [
                ("Codex — OpenAI CLI, Codex login", "codex"),
                ("Claude — Anthropic CLI, Claude login", "claude"),
                ("OpenCode — Your configured model provider", "opencode"),
                ("Back", None),
            ],
        )
        if selected:
            switch_session(record, selected)
            view(f"Harness changed to {selected}. Choose Start {selected} to continue.")
        return

    if action == "environment":
        snapshot = inspect_session(record)
        while True:
            status = next(
                (line for line in snapshot.lines if line.startswith("dev-remote.sh:")),
                "Workspace stopped or not measurable",
            )
            selected = pick(
                f"{record.name} / Environment\n{status}\nMeasured {snapshot.checked_at}\nTCP reachability does not prove application health.",
                [
                    (
                        "Connections & processes — Inspect actual containers, endpoints and executable names",
                        "details",
                    ),
                    ("Refresh status — Read-only; never starts containers", "refresh"),
                    (
                        "Start dev-remote.sh — Run this session’s development stack using host dev data",
                        "dev-start",
                    ),
                    (
                        "Stop dev-remote.sh — Stop only the stack inside this sandbox",
                        "dev-stop",
                    ),
                    ("Back", None),
                ],
            )
            if selected is None:
                return
            if selected == "details":
                ports = (
                    "\n".join(
                        f"{name}: http://127.0.0.1:{value} (configured publication)"
                        for name, value in vars(record.ports).items()
                    )
                    if record.ports
                    else "No published development ports."
                )
                view("\n".join(snapshot.lines) + "\n\n" + ports)
            elif selected != "refresh":
                view(tool_action(record, selected))
            snapshot = inspect_session(record)

    if action == "browser":
        while True:
            selected = pick(
                f"{record.name} / Headless browser\nBrowser image: {'requested' if record.playwright else 'not requested'}\nManaged Chromium uses port 9222 inside the container only.",
                [
                    (
                        "Enable browser support — Stops workspace and prepares the Chromium image",
                        "browser-enable",
                    ),
                    (
                        "Start managed browser — Launch a session-local headless Chromium",
                        "browser-start",
                    ),
                    (
                        "Stop managed browser — Close only the browser started by this manager",
                        "browser-stop",
                    ),
                    (
                        "Capture screenshot — Open an HTTP(S) page; save a PNG under generated files",
                        "browser-capture",
                    ),
                    (
                        "Inspect browser processes — View live executable names and uptime",
                        "inspect",
                    ),
                    ("Back", None),
                ],
            )
            if selected is None:
                return
            if selected == "inspect":
                view("\n".join(inspect_session(record).lines))
                continue
            if selected == "browser-enable" and not pick(
                "Preparing the browser image stops this workspace’s processes.",
                [("Cancel", False), ("Stop workspace and enable browser", True)],
            ):
                continue
            url = ""
            if selected == "browser-capture":
                url = reader("Page URL (blank cancels): ").strip()
                if not url:
                    continue
            view(tool_action(record, selected, url=url))

    if action == "tools":
        while True:
            report = load_report(record)
            label = (
                "No measurements yet"
                if report is None
                else f"Last checked {report.checked_at}"
                + (" · stale" if report_is_stale(report) else "")
            )
            selected = pick(
                f"{record.name} / Tools & access\n{label}\nHistorical measurements are not live process status.",
                [
                    (
                        "View measured capabilities — Invocations, versions, requirements and access boundaries",
                        "view",
                    ),
                    (
                        "Remeasure capabilities — Starts the workspace if needed; checks real tools and access",
                        "refresh",
                    ),
                    ("Back", None),
                ],
            )
            if selected is None:
                return
            if selected == "refresh":
                report = ensure_capability_report(record, refresh=True)
            view(render_report_text(report, name=record.name))

    if action == "files":
        while True:
            items = list_files(record)
            options = [
                (
                    "Import files — Paste or drag quoted host paths into the next prompt",
                    "import",
                ),
                (
                    "Import clipboard — Copy a screenshot or files from the clipboard",
                    "clipboard",
                ),
            ]
            options += [
                (
                    f"{'Uploaded' if item.container_path.startswith('/attachments/') else 'Generated'}: {item.relative} — {item.size:,} bytes",
                    index,
                )
                for index, item in enumerate(items)
            ]
            selected = pick(
                f"{record.name} / Files & attachments\nUploads: /attachments (read-only)\nGenerated: /workspace/.msandbox/outputs\nShowing up to 200 files; refresh by returning here.",
                [*options, ("Back", None)],
            )
            if selected is None:
                return
            if selected in ("import", "clipboard"):
                if selected == "import":
                    paths = shlex.split(
                        reader("Host file paths (blank cancels): ").strip()
                    )
                    if not paths:
                        continue
                    attachments = import_files(record, [Path(value) for value in paths])
                else:
                    attachments = import_clipboard(record)
                view("\n".join(str(item.container_path) for item in attachments))
                continue
            item = items[selected]
            operation = pick(
                str(item.container_path),
                [
                    (
                        "Preview text — First 16 KiB; binary files display metadata",
                        "preview",
                    ),
                    (
                        "Export copy — Preserve outside the worktree and reveal in Finder",
                        "export",
                    ),
                    (
                        "Send path to harness — Paste a reference into the current conversation",
                        "send",
                    ),
                    ("Back", None),
                ],
            )
            if operation == "preview":
                payload = read_file(item, 16384)
                view(
                    payload.decode("utf-8", errors="replace")
                    if b"\0" not in payload
                    else f"Binary file · {item.size:,} bytes\nExport a copy to view it on the host."
                )
            elif operation == "export":
                exported = export_file(record, item)
                if sys.platform == "darwin":
                    subprocess.run(["open", "-R", str(exported)], check=False)
                view(f"Exported a preserved copy:\n{exported}")
            elif operation == "send":
                attachment = Attachment(
                    "",
                    item.relative.name,
                    mimetypes.guess_type(item.relative.name)[0]
                    or "application/octet-stream",
                    "",
                    item.size,
                    item.root / item.relative,
                    Path(item.container_path),
                )
                message = deliver_attachments(record, [attachment])
                view(
                    f"Attachment reference: {message}\nIf the harness is running, the reference is pasted for you to send."
                )

    if action == "publish":
        draft = load_draft(record)
        while True:
            selected = pick(
                f"{record.name} / Branch & pull request\nTarget: {record.target_branch or 'not selected'}\nLuna high proposes copy; you review before Git changes.\nSubmission requires passing validation for the committed tree.",
                [
                    (
                        "Draft with Luna high — Stops workspace; generates branch, commit and PR copy",
                        "draft",
                    ),
                    (
                        "Review draft — Read the complete proposed copy and change list",
                        "review",
                    ),
                    (
                        "Edit branch and title — Adjust Luna’s suggestions before applying",
                        "edit",
                    ),
                    (
                        "Create branch / commit — Apply the reviewed name and commit all shown changes",
                        "apply",
                    ),
                    (
                        "Validate full PR — Run required checks for this commit",
                        "validate",
                    ),
                    (
                        "Publish draft pull request — Push, create/update draft PR, release clean worktree",
                        "submit",
                    ),
                    ("Back", None),
                ],
            )
            if selected is None:
                return
            if selected == "draft":
                print("Drafting with gpt-5.6-luna / high…", file=output, flush=True)
                draft = generate_draft(record)
                save_draft(record, draft)
                view(f"{draft.branch}\n{draft.commit}\n\n{draft.title}\n\n{draft.body}")
            elif selected == "validate":
                from .validation import build_test_plan, run_test_plan

                result = run_test_plan(
                    record, build_test_plan(record, "pr", browser=record.playwright)
                )
                view(f"Validation: {result.status}\n{result.result_path}")
            elif draft is None:
                view("Generate a Luna draft first.")
            elif selected == "review":
                from .publication import git

                view(
                    f"{draft.branch}\n{draft.commit}\n\n{draft.title}\n\n{draft.body}\n\nFiles to commit:\n{git(record, 'status', '--short')}"
                )
            elif selected == "edit":
                from .publication import validate_copy

                proposed = replace(
                    draft,
                    branch=reader(f"Branch [{draft.branch}]: ").strip() or draft.branch,
                    title=reader(f"PR title [{draft.title}]: ").strip() or draft.title,
                    commit=reader(f"Commit [{draft.commit}]: ").strip() or draft.commit,
                )
                validate_copy(
                    {
                        key: getattr(proposed, key)
                        for key in ("branch", "title", "commit", "body")
                    }
                )
                draft = proposed
                save_draft(record, draft)
            elif selected == "apply":
                from .publication import git

                view(
                    f"Files to commit:\n{git(record, 'status', '--short')}\n\nCommit: {draft.commit}\nBranch: {record.target_branch if record.pr_number else draft.branch}"
                )
                if pick(
                    "Apply reviewed branch and commit all displayed changes?",
                    [("Cancel", False), ("Create branch and commit", True)],
                ):
                    apply_draft(record, draft, commit=True)
                    from .git_worktrees import current_head, dirty_fingerprint

                    draft = replace(
                        draft,
                        head=current_head(record.worktree),
                        fingerprint=dirty_fingerprint(record.worktree),
                    )
                    save_draft(record, draft)
                    view(
                        "Branch selected and changes committed. Run full PR validation next."
                    )
            elif selected == "submit":
                from .git_worktrees import current_head, dirty_fingerprint

                if not record.pr_number and record.target_branch != draft.branch:
                    view("Apply the reviewed branch before publishing this draft.")
                    continue
                if (
                    current_head(record.worktree) != draft.head
                    or dirty_fingerprint(record.worktree) != draft.fingerprint
                ):
                    view(
                        "Workspace changed since this copy was reviewed. Generate a fresh draft."
                    )
                    continue
                if pick(
                    "Publish this validated commit and release its clean worktree?\nExport wanted generated files first; unexported files are removed with it.",
                    [("Cancel", False), ("Publish draft PR", True)],
                ):
                    pr = submit_session(
                        record, draft=True, title=draft.title, body=draft.body
                    )
                    view(f"PR #{pr.number}: {pr.url}")
                    return
