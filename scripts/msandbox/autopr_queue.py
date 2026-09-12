"""Cached queue and scheduler timing for the terminal dashboard.

Rendering never contacts GitHub or the board. Refresh is an explicit background
read; starting a ticket revalidates it through the board's run-now endpoint.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from . import autopr_control as control

UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_refresh_lock = threading.Lock()
_refresh_error = ""


def cards_path() -> Path:
    return Path(
        os.environ.get(
            "AUTOPR_CARD_SNAPSHOT",
            Path.home() / "Library/Caches/matcha-kanban-autopr/cards.json",
        )
    )


def read_cards() -> tuple[list[dict], str]:
    try:
        path = cards_path()
        with path.open("rb") as stream:
            data = stream.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("Queue snapshot exceeds 4 MiB")
        cards = json.loads(data)
        if not isinstance(cards, list):
            raise ValueError("Queue snapshot must be a list")
        # Held (autopr_paused) and claimed In Progress cards stay visible: an
        # operator needs to see what is held and why, and to unstick a
        # stranded claim. Only malformed identities are dropped.
        valid = [
            card
            for card in cards
            if isinstance(card, dict)
            and all(
                isinstance(card.get(key), str) and UUID.fullmatch(card[key])
                for key in ("task_id", "project_id")
            )
        ]
        age = max(0, int(time.time() - path.stat().st_mtime))
        note = (
            f"Board snapshot: {age // 60}m {age % 60}s old (refresh to check changes)"
        )
        if len(valid) != len(cards):
            note += "; malformed entries omitted"
        if _refresh_lock.locked():
            note += " · refreshing…"
        if _refresh_error:
            note += f" · refresh failed: {_refresh_error}"
        return valid, note
    except (OSError, ValueError, TypeError) as exc:
        return (
            [],
            "Refreshing queue…"
            if _refresh_lock.locked()
            else f"Queue unavailable: {exc}. Choose Refresh queued tickets.",
        )


def refresh(repo: Path) -> str:
    global _refresh_error
    if not _refresh_lock.acquire(blocking=False):
        return "Queue refresh is already running; you can keep navigating."
    _refresh_error = ""

    def collect():
        global _refresh_error
        temporary = None
        try:
            payload = control.command(
                ["bash", str(repo / "scripts/kanban-autopr/collect.sh")], timeout=150
            )
            if len(payload) > 4 * 1024 * 1024 or not isinstance(
                json.loads(payload), list
            ):
                raise ValueError("Invalid board snapshot")
            path = cards_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".cards-", dir=path.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
            os.replace(temporary, path)
        except Exception as exc:
            _refresh_error = str(exc)
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
            _refresh_lock.release()

    threading.Thread(target=collect, daemon=True, name="autopr-queue-refresh").start()
    return "Refreshing queued tickets in the background; you can keep navigating."


def scheduler_lines(now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    state = Path(
        os.environ.get(
            "AUTOPR_DISPATCH_STATE_DIR",
            Path.home() / "Library/Caches/matcha-autopr-dashboard/dispatch",
        )
    )
    try:
        data = control.read_json(state / "status.json")
        times = [data[key] for key in ("checked_at", "next_check_at", "eligible_at")]
        if any(
            not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in times
        ):
            raise ValueError("Invalid scheduler timestamps")
        checked, next_check, eligible = times
        if now - checked > 360 or checked > now + 5:
            return [
                "Scheduler status is stale — next pickup unknown. Check the installed LaunchAgents."
            ]
        remaining = max(0, math.ceil(next_check - now))
        result = [
            f"Next scheduler check: {remaining // 60:02d}:{remaining % 60:02d}"
            if next_check > now
            else "Scheduler check due — awaiting its next heartbeat"
        ]
        reason = data.get("reason", "unknown")
        labels = {
            "msandbox-off": "Blocked: AutoPR master switch / primary sandbox is off",
            "active-autopr-workflow": "Waiting: another AutoPR workflow is active",
            "codex-usage-limit-backoff": "Paused: model usage limit backoff",
            "request-already-dispatched": "Start request already dispatched; waiting for the workflow",
            "recent-dispatch-pending": "Waiting: a recent dispatch is becoming visible on GitHub",
        }
        if reason in labels:
            result.append(labels[reason])
        elif data.get("action") == "error":
            result.append(f"Scheduler error: {reason}; pickup time unknown")
        elif data.get("action") == "dispatch":
            result.append(
                "Workflow dispatched — ticket pickup follows its startup and eligibility checks"
            )
        elif eligible > now:
            remaining = math.ceil(eligible - now)
            result.append(
                f"Routine Kanban eligibility: {remaining // 60:02d}:{remaining % 60:02d}"
            )
        else:
            result.append(
                "Routine Kanban eligible; other lanes and ticket gates may take priority"
            )
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return [
            "Next pickup unknown — no valid scheduler status yet (install/update the dispatcher)."
        ]


def start(task_id: str, repo: Path) -> str:
    if not UUID.fullmatch(task_id):
        raise ValueError("Invalid queued ticket ID")
    card = next((card for card in read_cards()[0] if card["task_id"] == task_id), None)
    if card is None:
        raise ValueError("Ticket is no longer in the cached queue; refresh first.")
    if card.get("board_column") not in ("todo", "changes_requested"):
        raise ValueError("Only Todo or Changes Requested tickets can be started; unstick it first.")
    with control.locked():
        held = control.held_task(task_id)
        if held and held.status != "ready":
            raise ValueError(
                "This task is under operator control or already running; use its run actions."
            )
    output = control.command(
        [
            "bash",
            str(repo / "scripts/kanban-autopr/queue-handoff.sh"),
            card["project_id"],
            task_id,
        ],
        timeout=150,
    ).decode(errors="replace")
    try:
        status = json.loads(output)
        if status.get("action") == "dispatch":
            return "Workflow dispatched for this ticket. Pickup follows startup and eligibility checks."
        reasons = {
            "active-autopr-workflow": "another AutoPR workflow is active",
            "msandbox-off": "the AutoPR master switch / primary sandbox is off",
            "codex-usage-limit-backoff": "model usage is paused",
            "request-already-dispatched": "its start request was already dispatched",
            "recent-dispatch-pending": "a recent dispatch is becoming visible on GitHub",
            "local-lock": "the scheduler is processing another request",
            "requested-ticket-no-longer-pending": "the board no longer reports a pending request; refresh its state",
        }
        reason = reasons.get(
            status.get("reason"), "check the scheduler status for its next attempt"
        )
        return f"Ticket request recorded; {reason}."
    except (ValueError, AttributeError):
        return "Ticket request recorded. Immediate dispatch status unavailable; check the scheduler status."
