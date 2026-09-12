"""`msandbox autopr …`: queue visibility and card control from any terminal.

Reads stay local (scheduler status, run records, the cached card snapshot,
the status-bar segment). Every board write goes through
scripts/kanban-autopr/card-control.sh, which owns the bot login and the
one-card-only resolution rules; this module only relays its exit code.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import autopr_control as control
from . import autopr_queue

CARD_VERBS = ("hold", "release", "run-now", "unstick", "cancel-run")


def _kanban_script(name: str, repo: Path | None) -> Path | None:
    """Installed dispatcher copy first (what the LaunchAgent runs), then the checkout.

    Releases never carry scripts/kanban-autopr, so a release alone cannot
    resolve these; the launcher exports MATCHA_REPO_ROOT for that case.
    """
    candidates = [Path.home() / ".local/share/matcha-kanban-autopr" / name]
    for root in (repo, os.environ.get("MATCHA_REPO_ROOT")):
        if root:
            candidates.append(Path(root) / "scripts/kanban-autopr" / name)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def hold_badge(card: dict) -> str:
    if not card.get("autopr_paused"):
        return ""
    reason = str(card.get("autopr_hold_reason") or "").strip()
    return f"HOLD · {reason}" if reason else "HOLD"


def queue_lines(cards: list[dict]) -> list[str]:
    lines = []
    for card in cards:
        badge = hold_badge(card) or (
            "REWORK" if card.get("board_column") == "changes_requested" else "TODO"
        )
        if card.get("board_column") == "in_progress":
            badge = "IN PROGRESS"
        lines.append(
            f"{card['task_id'][:8]}  {badge:<24} {card.get('project_title', '?')[:9]:<9} "
            f"{str(card.get('title', 'Untitled'))[:60]}"
        )
    return lines


def status(repo: Path | None = None) -> int:
    segment = _kanban_script("status-segment.sh", repo)
    if segment is None:
        print("AUTOPR status segment unavailable (dispatcher not installed)")
    else:
        result = subprocess.run(
            [str(segment)],
            env={**os.environ, "AUTOPR_SEGMENT_PLAIN": "1"},
            check=False,
            text=True,
            capture_output=True,
        )
        print(result.stdout.strip() or "AUTOPR status segment failed")
    for line in autopr_queue.scheduler_lines():
        print(line)
    warnings: list[str] = []
    runs = control.list_runs(warnings)
    for warning in warnings:
        print(f"warning: {warning}")
    if runs:
        print("Supervised runs:")
        for run in runs[:5]:
            print(f"  {run.status:<16} {run.title[:50]}  {run.workflow_id or 'local'}")
    return 0


def queue() -> int:
    cards, note = autopr_queue.read_cards()
    print(note)
    if not cards:
        return 0
    for line in queue_lines(cards):
        print(line)
    return 0


def card_action(
    verb: str,
    target: str | None,
    *,
    reason: str | None = None,
    hold: bool = False,
    repo: Path | None = None,
) -> int:
    if verb not in CARD_VERBS:
        raise ValueError(f"unknown autopr verb: {verb}")
    script = _kanban_script("card-control.sh", repo)
    if script is None:
        print(
            "msandbox: card-control.sh is not installed; run scripts/kanban-autopr/install-launch-agent.sh",
            file=sys.stderr,
        )
        return 2
    argv = [str(script), verb]
    if target:
        argv.append(target)
    if reason:
        argv += ["--reason", reason]
    if hold:
        argv.append("--hold")
    return subprocess.run(argv, check=False).returncode
