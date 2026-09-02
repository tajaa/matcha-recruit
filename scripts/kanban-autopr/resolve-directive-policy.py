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


_DRAFT_COMMAND_RE = re.compile(
    r"^(?:(?:please\s+)?(?:(?:you\s+)?"
    r"(?:can|may|must|should|need\s+to)\s+)?)?"
    r"(?:draft|create|open)\s+(?:(?:this|a|the)\s+)?"
    r"(?:pr|pull\s+request)\b"
)
_WORK_COMMAND_RE = re.compile(
    r"^(?:(?:please\s+)?(?:go\s+ahead(?:\s+and)?\s+)?)?"
    r"(?:(?:you\s+)?(?:can|may|must|should|need\s+to)\s+)?"
    r"(?:work\s+on|implement|start\s+work\s+on)\s+"
    r"(?:this|it|the\s+(?:ticket|card|pr|pull\s+request))\b"
)
_GO_AHEAD_COMMAND_RE = re.compile(
    r"^(?:(?:please\s+)?(?:just\s+)?)?go\s+ahead"
    r"(?:\s+and\s+(?:do|fix|handle|implement)\s+(?:it|this))?"
    r"(?:\s+(?:with\s+)?(?:it|this))?"
    r"(?:\s+anyways?)?[.!]*$"
)
_FORCE_NEGATION_RE = re.compile(
    r"(?:\b(?:do\s+not|don't|dont|never|not|no)\b.{0,40}"
    r"\b(?:work|implement|draft|create|open|go\s+ahead)\b)"
    r"|(?:\b(?:work|implement|draft|create|open)\b.{0,20}"
    r"\b(?:not|never)\b)"
)
_TEST_ROUTE_RE = re.compile(
    r"(?:test[-_ ]route|reproduce(?:[-_ ]route)?)\s*(?:=|:)\s*(/\S+)",
    re.IGNORECASE,
)


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
        explicit_draft = instruction in {"draft-pr", "draft pr", "force-pr", "force pr"}
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


def resolve(card: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    event_id = str(card.get("autopr_reconsideration_event_id") or "")
    if not event_id or not card.get("autopr_reconsideration_pending", False):
        return {"directives": [], "test_route": None, "source_event_id": None}

    event = next(
        (row for row in reversed(history) if str(row.get("id") or "") == event_id),
        None,
    )
    metadata = event.get("metadata") if isinstance(event, dict) else None
    if not isinstance(metadata, dict) or metadata.get("kind") != "autopr_additional_context":
        return {"directives": [], "test_route": None, "source_event_id": event_id}

    stored = str(metadata.get("autopr_directives") or "").split(",")
    directives = [
        item for item in stored if item in {"draft_pr", "trust_still_broken"}
    ]
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    card = json.loads(Path(args.card).read_text())
    history = json.loads(Path(args.history).read_text())
    Path(args.output).write_text(json.dumps(resolve(card, history), indent=2) + "\n")


if __name__ == "__main__":
    main()
