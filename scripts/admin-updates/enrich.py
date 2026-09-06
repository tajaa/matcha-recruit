#!/usr/bin/env python3
"""Attach bounded PR authorship evidence to the drafting plan.

The writer used to reconstruct every candidate from `git show <mergeOid>`, so a
routine two-thousand-line PR was read as a full diff before a single sentence
was written. Everything it actually needs to describe a shipped change is
already written down by a human in the PR body, the commit messages, and the
review discussion; the diff only ever answered "what is this control called",
which is better answered by reading the current file. Collected here on the
trusted host, truncated, and handed over as plain evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MAX_COMMITS = 20
MAX_COMMIT_BODY = 1200
MAX_DISCUSSION_ITEMS = 12
MAX_DISCUSSION_BODY = 2500
MAX_DISCUSSION_TOTAL = 12000
MAX_FILE_STATS = 60


def _clip(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n[truncated]"


def _commits(detail: dict[str, Any]) -> list[dict[str, str]]:
    commits: list[dict[str, str]] = []
    for commit in (detail.get("commits") or [])[:MAX_COMMITS]:
        if not isinstance(commit, dict):
            continue
        subject = str(commit.get("messageHeadline") or "").strip()
        if not subject:
            continue
        commits.append({
            "subject": subject,
            "body": _clip(commit.get("messageBody"), MAX_COMMIT_BODY),
        })
    return commits


def _discussion(detail: dict[str, Any]) -> list[dict[str, str]]:
    """Human review conversation, newest last, under one shared size budget."""
    items: list[dict[str, str]] = []
    budget = MAX_DISCUSSION_TOTAL
    raw: list[tuple[str, dict[str, Any]]] = []
    for comment in detail.get("comments") or []:
        if isinstance(comment, dict):
            raw.append(("comment", comment))
    for review in detail.get("reviews") or []:
        if isinstance(review, dict):
            raw.append(("review", review))

    for kind, item in raw:
        body = _clip(item.get("body"), min(MAX_DISCUSSION_BODY, max(budget, 0)))
        if not body:
            continue
        author = (item.get("author") or {})
        items.append({
            "kind": kind,
            "author": str(author.get("login") or "unknown"),
            "body": body,
        })
        budget -= len(body)
        if budget <= 0 or len(items) >= MAX_DISCUSSION_ITEMS:
            break
    return items


def _file_stats(detail: dict[str, Any]) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for entry in (detail.get("files") or [])[:MAX_FILE_STATS]:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        stats.append({
            "path": str(entry["path"]),
            "additions": int(entry.get("additions") or 0),
            "deletions": int(entry.get("deletions") or 0),
        })
    return stats


def enrich(plan: dict[str, Any], details: dict[int, dict[str, Any]]) -> dict[str, Any]:
    for candidate in plan.get("candidates") or []:
        detail = details.get(int(candidate.get("sourcePr") or 0))
        if not detail:
            continue
        candidate["commits"] = _commits(detail)
        candidate["discussion"] = _discussion(detail)
        candidate["fileStats"] = _file_stats(detail)
        candidate["changeSize"] = {
            "additions": int(detail.get("additions") or 0),
            "deletions": int(detail.get("deletions") or 0),
            "changedFiles": int(detail.get("changedFiles") or 0),
        }
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("details", nargs="*", type=Path)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    details: dict[int, dict[str, Any]] = {}
    for path in args.details:
        detail = json.loads(path.read_text(encoding="utf-8"))
        number = detail.get("number")
        if number is None:
            continue
        details[int(number)] = detail

    args.plan.write_text(json.dumps(enrich(plan, details), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
