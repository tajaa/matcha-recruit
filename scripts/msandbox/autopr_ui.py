"""AutoPR activity and operator actions for the terminal manager."""

from __future__ import annotations

import os
import queue
import shlex
import subprocess
import threading
import time
from pathlib import Path

from . import autopr_cli
from . import autopr_control as control
from . import autopr_queue
from .capabilities import redact
from .dashboard_view import Row
from .terminal_ui import plain


class AutoPRFeed:
    """Local read-only feed; no GitHub polling on each dashboard frame."""

    def __init__(self):
        self.runs = []
        self.activity = ""
        self.activity_id = None
        self.error = ""
        self.pending = False
        self.last_read = 0
        self.completed = queue.SimpleQueue()
        self.cards = []
        self.queue_note = "Choose Refresh queued tickets to load the board."

    def refresh(self, selected: str | None, *, force=False):
        try:
            runs, activity, activity_id, error, cards, queue_note = (
                self.completed.get_nowait()
            )
        except queue.Empty:
            pass
        else:
            self.runs, self.activity, self.error = runs, activity, error
            self.activity_id = activity_id
            self.pending = False
            self.cards, self.queue_note = cards, queue_note
        if self.pending or (not force and time.monotonic() - self.last_read < 1):
            return
        self.pending = True
        self.last_read = time.monotonic()

        def read():
            runs, activity, error, activity_id = [], "", "", None
            try:
                warnings = []
                runs = control.list_runs(warnings)
                error = "\n".join(warnings)
                run = next(
                    (item for item in runs if item.id == selected),
                    runs[0] if runs else None,
                )
                if run:
                    activity_id = run.id
                    with (control.run_dir(run.id) / "activity.log").open(
                        "rb"
                    ) as stream:
                        stream.seek(0, 2)
                        stream.seek(max(0, stream.tell() - 32768))
                        activity = "\n".join(
                            plain(line)
                            for line in redact(
                                stream.read().decode(errors="replace")
                            ).splitlines()[-100:]
                        )
            except (OSError, ValueError, TypeError) as exc:
                error = str(exc)
            finally:
                cards, queue_note = autopr_queue.read_cards()
                self.completed.put(
                    (runs, activity, activity_id, error, cards, queue_note)
                )

        threading.Thread(target=read, daemon=True, name="autopr-activity").start()


def rows(feed: AutoPRFeed, selected: str | None) -> list[Row]:
    result = [
        Row("AUTOPR RUNS", tone="accent"),
        Row(
            "Runs use a dedicated checkout. Your main checkout and sandbox sessions stay available."
        ),
        Row("Open full AutoPR observer dashboard", "dashboard"),
    ]
    result += [Row(line) for line in autopr_queue.scheduler_lines()]
    result += [
        Row(""),
        Row("QUEUED TICKETS", tone="accent"),
        Row(feed.queue_note),
        Row("Refresh queued tickets", "autopr:refresh:queue"),
    ]
    held = {
        item.task_id
        for item in feed.runs
        if item.status in control.HOLD_STATES and item.status != "ready"
    }
    for card in feed.cards:
        title = plain(str(card.get("title", "Untitled")))
        task_id = card["task_id"]
        badge = plain(autopr_cli.hold_badge(card))
        if task_id in held:
            result.append(Row(f"{title} · held by an existing run"))
        elif badge:
            result.append(Row(f"Release · {title} · {badge}", f"autopr:release:{task_id}"))
        elif card.get("board_column") == "in_progress":
            result.append(
                Row(f"Unstick · {title} · claimed, back to its lane", f"autopr:unstick:{task_id}")
            )
        else:
            result.append(Row(f"Start now · {title}", f"autopr:start:{task_id}"))
            result.append(Row(f"Hold · {title}", f"autopr:hold:{task_id}"))
    if not feed.cards:
        result.append(Row("No queued tickets in the current snapshot."))
    result.append(
        Row("Cancel the active Kanban run · settles its card", "autopr:cancel-run:-")
    )
    if feed.error:
        result.append(Row(feed.error, tone="warning"))
    if not feed.runs:
        return result + [
            Row(
                "No supervised runs recorded yet. New Kanban investigations appear here after the runner uses this release."
            )
        ]
    run = next((item for item in feed.runs if item.id == selected), feed.runs[0])
    result += [Row(""), Row("SELECT A RUN", tone="accent")]
    # Keep actions and activity reachable even after weeks of run history.
    start = (feed.runs.index(run) // 5) * 5
    if start:
        result.append(Row("Previous runs", f"autopr:select:{feed.runs[start - 1].id}"))
    for item in feed.runs[start : start + 5]:
        label = f"{'● ' if item.id == run.id else ''}{item.title} · {item.status}"
        result.append(Row(label, f"autopr:select:{item.id}"))
    if start + 5 < len(feed.runs):
        result.append(Row("More runs", f"autopr:select:{feed.runs[start + 5].id}"))
    result += [
        Row(""),
        Row(run.title, tone="accent"),
        Row(f"Owner: {'you' if run.status == 'manual' else 'AutoPR / ' + run.status}"),
        Row(f"Model: {run.model} · effort: {run.effort}"),
        Row("Time limit: none — manual takeover is outside the workflow timer")
        if run.status == "manual"
        else Row("Autonomous limits apply only while AutoPR owns the run"),
        Row(
            f"PR: #{run.pr_number}"
            if run.pr_number
            else f"Branch: {run.branch} · no PR link recorded for this pass"
        ),
        Row(f"Checkout: {run.workspace}"),
        Row(f"Workflow run: {run.workflow_id or 'local'}"),
    ]
    if run.error:
        result.append(Row(run.error, tone="warning"))
        if run.status == "returned":
            result.append(
                Row("Retry cleanup of this completed run", f"autopr:cleanup:{run.id}")
            )
    if run.status in (
        "running",
        "pausing",
        "blocked",
        "recovering",
    ) and not control.supervisor_alive(run):
        result.append(
            Row(
                "Recover interrupted run  ·  verify ownership and preserve its checkout",
                f"autopr:recover:{run.id}",
            )
        )
    elif run.status == "running":
        result.append(
            Row(
                "Take over / correct course  ·  stops this run and preserves its edits",
                f"autopr:take:{run.id}",
            )
        )
    elif run.status == "pausing":
        result.append(
            Row("Stopping its model before transferring the checkout…", tone="warning")
        )
    elif run.status == "manual":
        result += [
            Row(
                "Open your Codex session  ·  Ctrl-b d returns here",
                f"autopr:open:{run.id}",
            ),
            Row("Open sandbox shell", f"autopr:shell:{run.id}"),
            Row(
                "Change model / effort…  ·  restarts your harness",
                f"autopr:model:{run.id}",
            ),
            Row(
                "Hand back to AutoPR…  ·  preserve edits and add instructions",
                f"autopr:return:{run.id}",
            ),
        ]
    elif run.status == "ready":
        result += [
            Row("Retry queueing the continuation", f"autopr:queue:{run.id}"),
            Row("Return to manual editing", f"autopr:reclaim:{run.id}"),
        ]
    elif run.status == "resuming":
        result.append(
            Row(
                "Recover manual control if the workflow stopped",
                f"autopr:reclaim:{run.id}",
            )
        )
    elif run.status == "preparing":
        result.append(
            Row("Recover an interrupted hand-back", f"autopr:reclaim:{run.id}")
        )
    elif run.status == "returned":
        result.append(
            Row(
                "AutoPR completed the continuation. The normal PR workflow owns publication.",
                tone="accent",
            )
        )
    result += [Row(""), Row("RECENT ACTIVITY", tone="accent")]
    activity = feed.activity if feed.activity_id == run.id else ""
    result += [Row(line) for line in activity.splitlines()] or [
        Row("Waiting for model output…")
    ]
    return result


def open_manual(run_id: str, repo: Path, *, shell=False):
    with control.runtime_locked(run_id):
        run = control.load(run_id)
        if run.status != "manual":
            raise ValueError(
                "AutoPR owns this checkout. Take it over before opening a writer."
            )
        target = control.tmux_name(run) + ("-shell" if shell else "")
        exists = (
            subprocess.run(
                ["tmux", "has-session", "-t", "=" + target],
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
        if not exists:
            env = control.manual_environment(run, repo)
            control.update_manual(run_id, runtime_created=True)
            control.command(
                [str(repo / "scripts/agent-sandbox.sh"), "start"], env=env, timeout=300
            )
            ids = (
                control.command(
                    [
                        "docker",
                        "ps",
                        "--filter",
                        f"label=com.docker.compose.project={run.project}",
                        "--filter",
                        "label=com.docker.compose.service=workspace",
                        "--format",
                        "{{.ID}}",
                    ]
                )
                .decode()
                .split()
            )
            if len(ids) != 1:
                raise RuntimeError(
                    "Could not identify this run's one sandbox container"
                )
            argv = [
                "docker",
                "exec",
                "-it",
                "--user",
                f"{env.get('SANDBOX_UID', str(os.getuid()))}:{env.get('SANDBOX_GID', str(os.getgid()))}",
                "--workdir",
                "/workspace",
                ids[0],
            ]
            argv += (
                ["bash"]
                if shell
                else [
                    "codex",
                    *(["resume", "--last"] if run.manual_started else []),
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--model",
                    run.model,
                    "-c",
                    f'model_reasoning_effort="{run.effort}"',
                ]
            )
            if not shell and not run.manual_started:
                argv.append(
                    "Continue this AutoPR task from the current files. Read .git/autopr-io/input and any .git/autopr-io/output/report.md for prior context. The human now directs this session. Preserve their edits."
                )
            control.command(
                ["tmux", "new-session", "-d", "-s", target, shlex.join(argv)]
            )
            if not shell:
                control.update_manual(run_id, manual_started=True)
    subprocess.run(["tmux", "attach-session", "-t", "=" + target], check=False)


def queue_return(run_id: str, repo: Path):
    with control.locked():
        run = control.load(run_id)
        if run.status == "resuming":
            return
        if run.status != "ready":
            raise ValueError("Only a saved hand-back can be queued.")
    # The fixed helper is trusted repo tooling. Task/Project IDs travel as argv;
    # the note remains local input, never a shell command or public PR comment.
    control.command(
        [
            "bash",
            str(repo / "scripts/kanban-autopr/queue-handoff.sh"),
            run.project_id,
            run.task_id,
        ],
        timeout=150,
    )


def manage(action: str, run_id: str, repo: Path, *, reader, output):
    from .manager import show
    from .wizard import choose

    if action == "refresh":
        return autopr_queue.refresh(repo)
    if action == "cleanup":
        with control.runtime_locked(run_id):
            run = control.load(run_id)
            if run.status != "returned":
                raise ValueError("Only completed hand-backs can be cleaned up.")
            control.archive_checkout(run)
            return (
                control.load(run_id).error
                or "Cleanup complete; recovery archive retained."
            )
    if action == "start":
        if not choose(
            "Request immediate pickup of this queued ticket? Active runs and usage limits still apply.",
            [("Cancel", False), ("Start ticket", True)],
            reader=reader,
            output=output,
        ):
            return "Ticket unchanged."
        return autopr_queue.start(run_id, repo)
    if action in autopr_cli.CARD_VERBS and action != "log":
        # run_id is a task id here (or "-" for the active run). Board writes
        # go through card-control.sh so the terminal and the tab agree.
        prompts = {
            "hold": "Hold this ticket so AutoPR skips it until released or edited?",
            "release": "Lift the hold and let the routine sweep pick this ticket up again?",
            "run-now": "Queue an immediate AutoPR run for this ticket?",
            "unstick": "Move this claimed ticket back to its lane (Todo, or Changes Requested when it has a PR)?",
            "cancel-run": "Cancel the active Kanban run and move its card back to its lane?",
        }
        if not choose(prompts[action], [("Cancel", False), ("Confirm", True)], reader=reader, output=output):
            return "Ticket unchanged."
        reason = reader("Reason (optional): ").strip() if action == "hold" else None
        code = autopr_cli.card_action(
            action, None if run_id == "-" else run_id, reason=reason or None, repo=repo
        )
        autopr_queue.refresh(repo)
        return (
            f"{action} done; refreshing the queue."
            if code == 0
            else f"{action} failed (exit {code}); see the terminal output."
        )
    if action == "take":
        control.request_takeover(run_id)
        return "Takeover requested. The run will appear as yours once its model has stopped."
    if action == "recover":
        control.recover(run_id, repo)
        return "Interrupted run recovered. Its checkout is now yours."
    if action in ("open", "shell"):
        open_manual(run_id, repo, shell=action == "shell")
    elif action == "model":
        run = control.load(run_id)
        model = choose(
            "Model for your session and its AutoPR continuation",
            [
                (value, value)
                for value in dict.fromkeys((run.model, *control.MODEL_CHOICES))
            ]
            + [("Enter another model ID", "custom"), ("Cancel", None)],
            reader=reader,
            output=output,
        )
        if model is None:
            return "Model unchanged."
        if model == "custom":
            model = reader("Model ID: ").strip()
        effort = choose(
            "Reasoning effort",
            [(value, value) for value in dict.fromkeys((run.effort, *control.EFFORTS))]
            + [("Cancel", None)],
            reader=reader,
            output=output,
        )
        if effort is None:
            return "Model unchanged."
        control.configure(run_id, model, effort, repo)
        return "Model saved. Open your Codex session to continue with it."
    elif action == "return":
        note = reader("What should AutoPR do next? ").strip()
        if not choose(
            "Stop your harness and hand these edits back for validation and PR publication?",
            [("Cancel", False), ("Hand back", True)],
            reader=reader,
            output=output,
        ):
            return "Your checkout remains under manual control."
        control.prepare_return(run_id, repo, note)
        try:
            queue_return(run_id, repo)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            show(
                f"Edits are saved, but AutoPR could not be queued: {exc}\nUse Retry queueing the continuation.",
                reader=reader,
                output=output,
            )
            return "Saved hand-back needs queue retry."
        return "Continuation queued. Other sandbox sessions remain available."
    elif action == "queue":
        queue_return(run_id, repo)
        return "Continuation queued."
    elif action == "reclaim":
        current = control.load(run_id)
        if current.status == "preparing":
            # A live exporter holds this lock. Only a process that actually
            # stopped can leave a preparation eligible for recovery.
            with control.runtime_locked(run_id):
                current = control.load(run_id)
                if current.status != "preparing":
                    raise ValueError("Hand-back advanced; refresh its state first.")
                control.stop_manual(current, repo)
                with control.locked():
                    current = control.load(run_id)
                    if current.status != "preparing":
                        raise ValueError("Hand-back advanced; refresh its state first.")
                    current.status = "manual"
                    control.save(current)
            return "Interrupted hand-back recovered; your checkout is yours again."
        if current.status == "resuming":
            if not current.resumed_by.isdigit():
                if control.process_alive(current.continuation_pid):
                    raise ValueError("The local continuation is still running.")
            # A crashed job may never reach its finalizer. Consult the actual
            # workflow before allowing another writer into the saved checkout.
            state = (
                "completed"
                if not current.resumed_by.isdigit()
                else (
                    control.command(
                        [
                            "gh",
                            "run",
                            "view",
                            current.resumed_by,
                            "--repo",
                            "tajaa/matcha-recruit",
                            "--json",
                            "status",
                            "--jq",
                            ".status",
                        ]
                    )
                    .decode()
                    .strip()
                )
            )
            if state != "completed":
                raise ValueError(
                    "AutoPR is still running. Take over its active run first."
                )
        with control.locked():
            run = control.load(run_id)
            if any(
                item.task_id == run.task_id
                and item.id != run.id
                and item.status in ("running", "pausing")
                and control.supervisor_alive(item)
                for item in control.list_runs()
            ):
                raise ValueError(
                    "A local supervisor is still running. Take over its active entry first."
                )
            if (
                run.status != current.status
                or run.resumed_by != current.resumed_by
                or run.status not in ("ready", "resuming")
            ):
                raise ValueError(
                    "The continuation has already started; refresh and take over that run."
                )
            run.status = "manual"
            control.save(run)
        return "Checkout is yours again; automation will skip this held task."
    else:
        raise ValueError("Unknown AutoPR action")
    return "Returned to AutoPR activity."
