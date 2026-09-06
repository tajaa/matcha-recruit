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
# Per-candidate caps alone are not a bound on the plan: one backlog run can
# carry dozens of candidates, and the whole plan is read into the sandboxed
# writer's context. Evidence therefore also shares one plan-wide budget.
MAX_PLAN_EVIDENCE_TOTAL = 120000
# Earlier kinds of evidence are listed first but are not the most irreplaceable,
# so each is held to all but this fraction of what the candidate has left.
EVIDENCE_RESERVE_FRACTION = 3
_TRUNCATION_MARKER = "\n[truncated]"


def _clip(text: Any, limit: int) -> str:
    """Clip to `limit` characters *including* the marker, so a caller's budget
    arithmetic stays exact when many clips are summed into one plan."""
    value = str(text or "").strip()
    if len(value) <= max(limit, 0):
        return value
    keep = limit - len(_TRUNCATION_MARKER)
    if keep <= 0:
        return ""
    return value[:keep].rstrip() + _TRUNCATION_MARKER


def _commits(detail: dict[str, Any], budget: int) -> tuple[list[dict[str, str]], int]:
    commits: list[dict[str, str]] = []
    used = 0
    for commit in (detail.get("commits") or [])[:MAX_COMMITS]:
        if not isinstance(commit, dict):
            continue
        subject = str(commit.get("messageHeadline") or "").strip()
        if not subject:
            continue
        if used + len(subject) > budget:
            break
        body = _clip(commit.get("messageBody"), min(MAX_COMMIT_BODY, budget - used - len(subject)))
        commits.append({"subject": subject, "body": body})
        used += len(subject) + len(body)
    return commits, used


def _discussion_items(raw: Any, kind: str) -> list[dict[str, str]]:
    """Normalize one conversation source into chronological order."""
    items: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        author = item.get("author") or {}
        entry = {
            "kind": kind,
            # `comments` carry createdAt and `reviews` carry submittedAt.
            "at": str(item.get("createdAt") or item.get("submittedAt") or ""),
            "author": str(author.get("login") or "unknown"),
            "body": str(item.get("body") or "").strip(),
        }
        state = str(item.get("state") or "").strip()
        if state:
            entry["state"] = state
        items.append(entry)
    items.sort(key=lambda entry: entry["at"])
    return items


def _take_discussion(
    items: list[dict[str, str]], *, max_items: int, budget: int
) -> tuple[list[dict[str, str]], int]:
    taken: list[dict[str, str]] = []
    used = 0
    for item in items:
        if len(taken) >= max_items or used >= budget:
            break
        body = _clip(item["body"], min(MAX_DISCUSSION_BODY, budget - used))
        if not body:
            continue
        taken.append({**item, "body": body})
        used += len(body)
    return taken, used


def _discussion(detail: dict[str, Any], budget: int) -> tuple[list[dict[str, str]], int]:
    """Human review conversation, newest last, under one shared size budget.

    `reviews` hold the approve / request-changes rationale, which is the one
    piece of evidence the writer cannot reconstruct from anywhere else now that
    it never reads the diff. Appending them after every comment let a run of
    long automated review-bot comments spend the entire budget first and drop
    them silently, so reviews get a reserved share of it.
    """
    budget = min(budget, MAX_DISCUSSION_TOTAL)
    comments = _discussion_items(detail.get("comments"), "comment")
    reviews = _discussion_items(detail.get("reviews"), "review")

    reserved_items = min(len(reviews), MAX_DISCUSSION_ITEMS // 2)
    reserved_budget = budget // 2 if reviews else 0
    taken, used = _take_discussion(
        comments,
        max_items=MAX_DISCUSSION_ITEMS - reserved_items,
        budget=budget - reserved_budget,
    )
    review_taken, review_used = _take_discussion(
        reviews,
        max_items=MAX_DISCUSSION_ITEMS - len(taken),
        budget=budget - used,
    )
    taken += review_taken
    taken.sort(key=lambda entry: entry["at"])
    return taken, used + review_used


def _file_stats(detail: dict[str, Any], budget: int) -> tuple[list[dict[str, Any]], int]:
    stats: list[dict[str, Any]] = []
    used = 0
    for entry in (detail.get("files") or [])[:MAX_FILE_STATS]:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        path = str(entry["path"])
        if used + len(path) > budget:
            break
        stats.append({
            "path": path,
            "additions": int(entry.get("additions") or 0),
            "deletions": int(entry.get("deletions") or 0),
        })
        used += len(path)
    return stats, used


def enrich(plan: dict[str, Any], details: dict[int, dict[str, Any]]) -> dict[str, Any]:
    candidates = plan.get("candidates") or []
    budget = MAX_PLAN_EVIDENCE_TOTAL
    for index, candidate in enumerate(candidates):
        detail = details.get(int(candidate.get("sourcePr") or 0))
        if not detail:
            continue
        # Spend an even share of what is left so an early candidate cannot
        # starve the rest; whatever one leaves unspent rolls forward.
        share = max(budget // (len(candidates) - index), 0)
        # Cheapest structural signal first, then the prose, each capped so no
        # one kind of evidence can consume the whole share.
        stats, stat_chars = _file_stats(detail, share // EVIDENCE_RESERVE_FRACTION)
        remaining = share - stat_chars
        commits, commit_chars = _commits(
            detail, remaining - remaining // EVIDENCE_RESERVE_FRACTION
        )
        discussion, discussion_chars = _discussion(detail, remaining - commit_chars)
        budget -= stat_chars + commit_chars + discussion_chars
        candidate["commits"] = commits
        candidate["discussion"] = discussion
        candidate["fileStats"] = stats
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
