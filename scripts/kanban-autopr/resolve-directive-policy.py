#!/usr/bin/env python3
"""Resolve trusted AutoPR directives from one pending reconsideration event.

New API writes carry structured directive metadata. The bounded event body is
also parsed so an instruction submitted before a parser upgrade is not lost.
Only the event id exposed as pending on the collected card is authoritative.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


# Operator directive grammar. Deliberately generous: this parser only ever
# sees text an authorized owner bound to one exact AutoPR decision, so a plain
# affirmative ("you can work on this", "do it anyway", "draft the migration")
# is authority. Keep byte-identical with the API-side copy in
# server/app/matcha/services/matcha_work/project_task_service.py.
_LEAD_IN = (
    r"^(?:(?:please|pls|hey|ok|okay|yes|yep|yeah|sure|thanks)\b[\s,]*)*"
    r"(?:(?:anyway|anyways|either\s+way|regardless|still|nonetheless)\b[\s,]*)*"
    r"(?:i\s+(?:need|want|expect)\s+(?:you\s+)?to\s+)?"
    r"(?:(?:you|u|it|autopr|the\s+bot|the\s+agent)\s+)?"
    r"(?:(?:can|may|must|should|could|shall|will|need\s+to|have\s+to|ought\s+to"
    r"|are\s+(?:ok|okay|clear|free|allowed)\s+to)\s+)?"
    r"(?:go\s+ahead\s+(?:and\s+)?)?"
    r"(?:(?:just|still|absolutely|definitely|certainly|totally|really|simply"
    r"|please|now|then|instead|anyway|anyways)\s+)*"
)
_DRAFT_COMMAND_RE = re.compile(
    _LEAD_IN
    + r"(?:draft|create|open|make|write|author|submit|raise|put\s+up)\s+"
    r"(?:(?:this|that|a|an|the)\s+)?(?:draft\s+)?"
    r"(?:pr|pull\s+request|migration(?:\s+(?:script|file|version))?s?)\b"
)
_WORK_COMMAND_RE = re.compile(
    _LEAD_IN
    + r"(?:work\s+on|start\s+(?:work\s+)?on|implement|build|do|handle|fix"
    r"|finish|complete|tackle|take\s+on|pick\s+up|proceed\s+with)\s+"
    r"(?:this|that|it|the\s+(?:ticket|card|pr|pull\s+request|work|change|migration))\b"
)
_GO_AHEAD_COMMAND_RE = re.compile(
    _LEAD_IN + r"(?:go\s+ahead|proceed|carry\s+on|keep\s+going)\b"
)
_FORCE_NEGATION_RE = re.compile(
    r"(?:\b(?:do\s+not|don't|dont|never|not|no)\b.{0,40}"
    r"\b(?:work|implement|draft|create|open|build|handle|fix|finish|proceed"
    r"|go\s+ahead)\b)"
    r"|(?:\b(?:work|implement|draft|create|open|build|handle|fix|finish|proceed)\b"
    r".{0,20}\b(?:not|never)\b)"
)
_EXPLICIT_DRAFT_COMMANDS = {
    "draft-pr", "draft pr", "force-pr", "force pr", "force", "override",
    "draft it", "do it", "work on it", "ship it",
}
_TEST_ROUTE_RE = re.compile(
    r"(?:test[-_ ]route|reproduce(?:[-_ ]route)?)\s*(?:=|:)\s*(/\S+)",
    re.IGNORECASE,
)
_RECOVERABLE_NOTE_RE = re.compile(
    r"\[autopr:no-spec [^\]]+\]\s+(already_fixed|migration_required)(?:\s|$)",
    re.IGNORECASE,
)
_DIRECTIVE_MARKER_RE = re.compile(r"\[autopr:directives ([a-z_,]+)\]")
_KNOWN_DIRECTIVES = {"draft_pr", "trust_still_broken", "extend_runtime"}
_STANDING_DIRECTIVES = {"draft_pr", "trust_still_broken"}


def _parse_bound_body(body: str) -> tuple[list[str], str | None]:
    directives: list[str] = []
    test_route: str | None = None
    for raw_line in body.splitlines():
        line = raw_line.strip()
        marked = line.startswith("--")
        directive_text = line[2:] if marked else line
        instruction = " ".join(
            directive_text.strip().lower().replace("’", "'").split()
        )
        explicit_draft = instruction in _EXPLICIT_DRAFT_COMMANDS
        if (
            explicit_draft
            or _DRAFT_COMMAND_RE.search(instruction)
            or _WORK_COMMAND_RE.search(instruction)
            or _GO_AHEAD_COMMAND_RE.search(instruction)
        ) and not _FORCE_NEGATION_RE.search(instruction):
            directives.append("draft_pr")
        if marked and (
            instruction in {"trust-still-broken", "trust still broken"}
            or (
                "trust" in instruction
                and any(
                    phrase in instruction
                    for phrase in (
                        "still not working",
                        "isn't working",
                        "is not working",
                        "still broken",
                    )
                )
            )
        ):
            directives.append("trust_still_broken")
        if marked and instruction in {
            "extend-runtime",
            "extend runtime",
            "allow-more-time",
            "allow more time",
        }:
            directives.append("extend_runtime")
        route_match = _TEST_ROUTE_RE.search(directive_text) if marked else None
        if route_match:
            candidate = route_match.group(1).rstrip(".,;")
            if (
                candidate.startswith("/")
                and not candidate.startswith("//")
                and "://" not in candidate
                and ".." not in candidate
                and "?" not in candidate
                and "#" not in candidate
                and len(candidate) <= 500
            ):
                test_route = candidate
    return list(dict.fromkeys(directives)), test_route


def _standing_directives(card: dict[str, Any]) -> list[str]:
    """Directives already granted on this card, read from its progress note.

    The note prefix is written by the trusted publisher (or edited by the
    card's human owner), never by the model. Once an owner has authorized a
    draft, that authorization survives the run that consumed the event: a
    ticket does not have to be re-authorized after every AutoPR cycle.
    """
    if card.get("board_column") not in {"todo", "changes_requested"}:
        return []
    match = _DIRECTIVE_MARKER_RE.search(str(card.get("progress_note") or ""))
    if not match:
        return []
    return [item for item in match.group(1).split(",") if item in _STANDING_DIRECTIVES]


def resolve(card: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    standing = _standing_directives(card)
    event_id = str(card.get("autopr_reconsideration_event_id") or "")
    if not event_id or not card.get("autopr_reconsideration_pending", False):
        return {"directives": standing, "test_route": None, "source_event_id": None}

    event = next(
        (row for row in reversed(history) if str(row.get("id") or "") == event_id),
        None,
    )
    metadata = event.get("metadata") if isinstance(event, dict) else None
    if not isinstance(metadata, dict) or metadata.get("kind") != "autopr_additional_context":
        return {"directives": standing, "test_route": None, "source_event_id": event_id}

    stored = str(metadata.get("autopr_directives") or "").split(",")
    directives = [*standing, *(item for item in stored if item in _KNOWN_DIRECTIVES)]
    parsed, parsed_route = _parse_bound_body(str(metadata.get("body") or ""))
    directives = list(dict.fromkeys([*directives, *parsed]))

    test_route = metadata.get("autopr_test_route") or parsed_route
    if not isinstance(test_route, str):
        test_route = None
    return {
        "directives": directives,
        "test_route": test_route,
        "source_event_id": event_id,
    }


def recover_consumed(card: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """Recover one explicit directive consumed by an obsolete blocked pass.

    A worker could accept decision-bound additional context, repeat the same
    kind of refusal, and thereby change the progress note so the event no
    longer appeared pending. Recovery is deliberately narrow: both the old
    bound decision and the current decision must be a refusal a ``draft_pr``
    directive mechanically forbids (``already_fixed`` or
    ``migration_required``), and the event itself must contain an explicit
    work/still-broken directive.
    """
    current_note = str(card.get("progress_note") or "")
    if (
        card.get("autopr_reconsideration_pending", False)
        or card.get("board_column") not in {"todo", "changes_requested"}
        or not _RECOVERABLE_NOTE_RE.search(current_note)
    ):
        return {"directives": [], "test_route": None, "source_event_id": None}

    for event in reversed(history):
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("kind") != "autopr_additional_context":
            continue
        prior_note = str(metadata.get("autopr_reconsideration_of") or "")
        if not _RECOVERABLE_NOTE_RE.search(prior_note):
            continue
        stored = str(metadata.get("autopr_directives") or "").split(",")
        directives = [item for item in stored if item in _KNOWN_DIRECTIVES]
        parsed, parsed_route = _parse_bound_body(str(metadata.get("body") or ""))
        directives = list(dict.fromkeys([*directives, *parsed]))
        if not (_STANDING_DIRECTIVES & set(directives)):
            continue
        test_route = metadata.get("autopr_test_route") or parsed_route
        if not isinstance(test_route, str):
            test_route = None
        return {
            "directives": directives,
            "test_route": test_route,
            "source_event_id": str(event.get("id") or "") or None,
            "source_event_at": event.get("created_at"),
        }
    return {"directives": [], "test_route": None, "source_event_id": None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--recover-consumed", action="store_true")
    args = parser.parse_args()

    card = json.loads(Path(args.card).read_text())
    history = json.loads(Path(args.history).read_text())
    result = recover_consumed(card, history) if args.recover_consumed else resolve(card, history)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
