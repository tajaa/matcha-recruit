#!/usr/bin/env python3
"""Build one deterministic work/merge plan from board cards and open bot PRs.

This planner intentionally does not execute model-authored instructions. It
uses paths, stable ids, labels, and bounded natural-language token overlap to
cluster related work. The selected implementation agent receives the resulting
related-work excerpts as evidence and makes the code-level boundary decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any


STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
    "card", "change", "changes", "do", "does", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "main", "need", "needs", "of", "on",
    "or", "our", "pr", "pull", "request", "should", "task", "that", "the",
    "this", "ticket", "to", "todo", "we", "when", "with", "work",
}
TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
BOT_LABELS = {"autopr", "autofix", "autopr-self-audit"}
BLOCKING_LABELS = {
    "autopr-awaiting-input", "needs-work", "possible-duplicate",
    "production-verification-failed",
}


def text_tokens(*parts: Any) -> set[str]:
    text = " ".join(str(part or "") for part in parts).lower()
    return {token for token in TOKEN_RE.findall(text) if token not in STOP}


def comment_text(pr: dict[str, Any]) -> str:
    pieces = [pr.get("body") or ""]
    for key in ("comments", "reviews"):
        for row in pr.get(key) or []:
            pieces.append(row.get("body") or "")
    return " ".join(pieces)


def paths_for_card(card: dict[str, Any]) -> set[str]:
    return {str(path).strip("/") for path in card.get("repo_paths") or [] if str(path).strip("/")}


def paths_for_pr(pr: dict[str, Any]) -> set[str]:
    return {str(path).strip("/") for path in pr.get("files") or [] if str(path).strip("/")}


def path_related(left: set[str], right: set[str]) -> list[str]:
    matches: set[str] = set()
    for a in left:
        a_root = a.split("*")[0].rstrip("/")
        for b in right:
            b_root = b.split("*")[0].rstrip("/")
            if not a_root or not b_root:
                continue
            if a_root == b_root or a_root.startswith(b_root + "/") or b_root.startswith(a_root + "/"):
                matches.add(a_root if len(a_root) <= len(b_root) else b_root)
            elif PurePosixPath(a_root).parts[:2] == PurePosixPath(b_root).parts[:2]:
                # A shared two-component product package is useful context but
                # weaker than an exact/ancestor path match.
                matches.add("/".join(PurePosixPath(a_root).parts[:2]))
    return sorted(matches)


def relation(
    left_tokens: set[str], left_paths: set[str], left_element: str | None,
    right_tokens: set[str], right_paths: set[str], right_element: str | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if left_element and right_element and left_element == right_element:
        score += 7
        reasons.append("same project element")
    shared_paths = path_related(left_paths, right_paths)
    if shared_paths:
        score += min(8, 4 + len(shared_paths))
        reasons.append("shared code area: " + ", ".join(shared_paths[:3]))
    shared_tokens = sorted(left_tokens & right_tokens)
    if len(shared_tokens) >= 2:
        score += min(5, len(shared_tokens))
        reasons.append("shared topic: " + ", ".join(shared_tokens[:5]))
    return score, reasons


def priority_value(value: str | None) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get((value or "").lower(), 2)


def parse_time(value: str | None) -> str:
    return value or "9999-12-31T23:59:59Z"


def card_base_key(card: dict[str, Any]) -> tuple[Any, ...]:
    reconsider = bool(card.get("autopr_reconsideration_pending"))
    column = card.get("board_column")
    progress = (card.get("progress_note") or "").lower()
    has_pr = isinstance(card.get("pr_number"), int)
    if reconsider:
        lane = 0
    elif column == "changes_requested" and has_pr:
        lane = 1
    elif column == "changes_requested":
        lane = 2
    elif "awaiting answers" in progress:
        lane = 4
    else:
        lane = 3
    return (
        lane,
        priority_value(card.get("priority")),
        parse_time(card.get("last_moved_at") or card.get("created_at")),
        card.get("task_id") or "",
    )


def card_context_state(card: dict[str, Any]) -> str | None:
    """Describe unresolved context, including a challenged already-fixed call."""
    if card.get("autopr_reconsideration_pending"):
        return "context received; re-investigation required"
    progress = (card.get("progress_note") or "").lower()
    if "awaiting answers" in progress:
        return "additional context required"
    if "[autopr:no-spec " in progress and "already_fixed" in progress:
        return "additional context required; prior already-fixed decision is not accepted as proof"
    return None


def pr_id8(pr: dict[str, Any]) -> str | None:
    match = re.fullmatch(r"bot/task-([0-9a-fA-F]{8})", pr.get("headRefName") or "")
    return match.group(1).lower() if match else None


def pr_is_ready(pr: dict[str, Any]) -> bool:
    # GitHub's ready-for-review transition is the requested exclusion boundary.
    return pr.get("state") == "OPEN" and pr.get("isDraft") is False


def pr_blockers(pr: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    labels = set(pr.get("labels") or [])
    blockers.extend(sorted(labels & BLOCKING_LABELS))
    if pr.get("reviewDecision") == "CHANGES_REQUESTED":
        blockers.append("review changes requested")
    checks = pr.get("checks") or []
    if any((row.get("conclusion") or "").upper() in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for row in checks):
        blockers.append("failing checks")
    elif any((row.get("status") or "").upper() not in {"COMPLETED", "SUCCESS"} for row in checks):
        blockers.append("checks pending")
    return blockers


def short_comment_evidence(pr: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for kind in ("comments", "reviews"):
        for row in (pr.get(kind) or [])[-3:]:
            body = " ".join((row.get("body") or "").split())[:500]
            if body:
                rows.append({
                    "kind": kind[:-1],
                    "author": row.get("author") or "unknown",
                    "body": body,
                })
    return rows[-4:]


def build_plan(cards: list[dict[str, Any]], prs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cards = [dict(card) for card in cards]
    prs = [dict(pr) for pr in prs if set(pr.get("labels") or []) & BOT_LABELS]
    card_by_id8 = {(card.get("id8") or "").lower(): card for card in cards}
    card_tokens = {
        card["task_id"]: text_tokens(card.get("title"), card.get("description"), card.get("review_note"), card.get("progress_note"))
        for card in cards
    }
    card_paths = {card["task_id"]: paths_for_card(card) for card in cards}
    pr_tokens = {
        pr["number"]: text_tokens(pr.get("title"), comment_text(pr)) for pr in prs
    }
    pr_paths = {pr["number"]: paths_for_pr(pr) for pr in prs}

    # Undirected card graph; connected components become contiguous work
    # clusters so three related tickets are not independently interleaved.
    edges: dict[str, list[tuple[str, int, list[str]]]] = defaultdict(list)
    for index, left in enumerate(cards):
        for right in cards[index + 1:]:
            score, reasons = relation(
                card_tokens[left["task_id"]], card_paths[left["task_id"]], left.get("element_id"),
                card_tokens[right["task_id"]], card_paths[right["task_id"]], right.get("element_id"),
            )
            if score >= 5:
                edges[left["task_id"]].append((right["task_id"], score, reasons))
                edges[right["task_id"]].append((left["task_id"], score, reasons))

    components: list[list[dict[str, Any]]] = []
    seen: set[str] = set()
    by_task = {card["task_id"]: card for card in cards}
    for card in sorted(cards, key=card_base_key):
        task_id = card["task_id"]
        if task_id in seen:
            continue
        queue = deque([task_id])
        seen.add(task_id)
        component: list[dict[str, Any]] = []
        while queue:
            current = queue.popleft()
            component.append(by_task[current])
            for neighbor, _score, _reasons in edges.get(current, []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        component.sort(key=card_base_key)
        components.append(component)
    components.sort(key=lambda rows: min(card_base_key(row) for row in rows))
    ordered_cards = [card for component in components for card in component]

    cluster_for: dict[str, str] = {}
    for index, component in enumerate(components, 1):
        cluster_id = f"C{index}"
        for card in component:
            cluster_for[card["task_id"]] = cluster_id

    related_prs_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    best_card_for_pr: dict[int, tuple[int, dict[str, Any]]] = {}
    for card in cards:
        for pr in prs:
            linked = pr_id8(pr) == (card.get("id8") or "").lower() or pr.get("number") == card.get("pr_number")
            score, reasons = relation(
                card_tokens[card["task_id"]], card_paths[card["task_id"]], card.get("element_id"),
                pr_tokens[pr["number"]], pr_paths[pr["number"]], None,
            )
            if linked:
                score += 100
                reasons.insert(0, "linked implementation PR")
            if linked or score >= 4:
                previous = best_card_for_pr.get(pr["number"])
                if previous is None or score > previous[0]:
                    best_card_for_pr[pr["number"]] = (score, card)
                related_prs_by_task[card["task_id"]].append({
                    "number": pr["number"],
                    "title": pr.get("title") or "Untitled PR",
                    "head": pr.get("headRefName"),
                    "lane": next((label for label in pr.get("labels") or [] if label in BOT_LABELS), "bot"),
                    "is_ready": pr_is_ready(pr),
                    "relation_score": score,
                    "reasons": reasons,
                    "blockers": pr_blockers(pr),
                    "comment_evidence": short_comment_evidence(pr),
                })
        related_prs_by_task[card["task_id"]].sort(key=lambda row: (-row["relation_score"], row["number"]))

    # Include every field that can affect relationships, ordering, evidence,
    # or release safety. The explicit release command must go stale whenever
    # any of those inputs changes.
    canonical = {
        "cards": [{key: card.get(key) for key in (
            "task_id", "id8", "title", "description", "review_note",
            "board_column", "priority", "created_at", "last_moved_at",
            "progress_note", "autopr_reconsideration_pending", "pr_number",
            "repo_paths", "element_id",
        )} for card in cards],
        "prs": [{key: pr.get(key) for key in (
            "number", "title", "body", "state", "isDraft", "headRefName",
            "createdAt", "updatedAt", "labels", "reviewDecision", "checks",
            "files", "comments", "reviews",
        )} for pr in prs],
    }
    plan_id = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]

    enriched_cards: list[dict[str, Any]] = []
    work_order: list[dict[str, Any]] = []
    position_for_task: dict[str, int] = {}
    context_blockers: list[dict[str, Any]] = []
    for position, card in enumerate(ordered_cards, 1):
        position_for_task[card["task_id"]] = position
        related_tickets: list[dict[str, Any]] = []
        for neighbor, score, reasons in sorted(edges.get(card["task_id"], []), key=lambda row: (-row[1], row[0]))[:5]:
            other = by_task[neighbor]
            related_tickets.append({
                "task_id": neighbor,
                "id8": other.get("id8"),
                "title": other.get("title"),
                # The implementation agent needs the neighboring card's actual
                # bounded substance, not merely a title generated from it.
                "description": str(other.get("description") or "")[:4000],
                "review_note": str(other.get("review_note") or "")[:2000],
                "progress_note": str(other.get("progress_note") or "")[:1000],
                "repo_paths": list(other.get("repo_paths") or [])[:20],
                "board_column": other.get("board_column"),
                "relation_score": score,
                "reasons": reasons,
            })
        reconsider = bool(card.get("autopr_reconsideration_pending"))
        context_state = card_context_state(card)
        waiting = context_state is not None and not reconsider
        if reconsider:
            urgency = "escalated additional context"
        elif card.get("board_column") == "changes_requested":
            urgency = "unblock rework already in flight"
        elif waiting:
            urgency = "waiting for human context"
        else:
            urgency = "planned new work"
        if context_state is not None:
            context_blockers.append({
                "task_id": card["task_id"], "id8": card.get("id8"),
                "title": card.get("title"),
                "state": context_state,
            })
        planning = {
            "plan_id": plan_id,
            "work_position": position,
            "cluster_id": cluster_for[card["task_id"]],
            "urgency": urgency,
            "related_tickets": related_tickets,
            "related_bot_prs": related_prs_by_task[card["task_id"]][:5],
        }
        enriched = dict(card)
        enriched["autopr_plan"] = planning
        enriched_cards.append(enriched)
        work_order.append({
            "position": position,
            "kind": "ticket",
            "task_id": card["task_id"],
            "id8": card.get("id8"),
            "title": card.get("title"),
            "project_title": card.get("project_title"),
            "board_column": card.get("board_column"),
            "cluster_id": planning["cluster_id"],
            "urgency": urgency,
            "blocked": waiting and not reconsider,
        })

    not_ready_prs = [pr for pr in prs if pr.get("state") == "OPEN" and not pr_is_ready(pr)]
    ready_excluded = [pr for pr in prs if pr_is_ready(pr)]

    def merge_key(pr: dict[str, Any]) -> tuple[Any, ...]:
        linked_card = card_by_id8.get(pr_id8(pr) or "")
        if linked_card is None and pr["number"] in best_card_for_pr:
            linked_card = best_card_for_pr[pr["number"]][1]
        linked_position = position_for_task.get(linked_card["task_id"], 10_000) if linked_card else 10_000
        labels = set(pr.get("labels") or [])
        rework = 0 if ("autopr-rework" in labels or pr.get("reviewDecision") == "CHANGES_REQUESTED") else 1
        return linked_position, rework, parse_time(pr.get("createdAt")), pr.get("number")

    not_ready_prs.sort(key=merge_key)
    merge_order: list[dict[str, Any]] = []
    prior: list[dict[str, Any]] = []
    for position, pr in enumerate(not_ready_prs, 1):
        dependencies: list[int] = []
        dependency_reasons: list[str] = []
        for earlier in prior:
            shared = path_related(pr_paths[pr["number"]], pr_paths[earlier["number"]])
            if shared:
                dependencies.append(earlier["number"])
                dependency_reasons.append(
                    f"#{earlier['number']} first; shared code area " + ", ".join(shared[:3])
                )
        linked_card = card_by_id8.get(pr_id8(pr) or "")
        if linked_card is None and pr["number"] in best_card_for_pr:
            linked_card = best_card_for_pr[pr["number"]][1]
        related_context = []
        if linked_card:
            linked_cluster = cluster_for.get(linked_card["task_id"])
            related_context = [
                row for row in context_blockers
                if cluster_for.get(row["task_id"]) == linked_cluster
            ]
        entry = {
            "position": position,
            "pr_number": pr["number"],
            "title": pr.get("title") or "Untitled PR",
            "head": pr.get("headRefName"),
            "lane": next((label for label in pr.get("labels") or [] if label in BOT_LABELS), "bot"),
            "linked_task_id": linked_card.get("task_id") if linked_card else None,
            "depends_on_prs": dependencies,
            "dependency_reasons": dependency_reasons,
            "blockers": pr_blockers(pr),
            "context_dependencies": related_context,
        }
        merge_order.append(entry)
        prior.append(pr)

    release_blockers: list[dict[str, Any]] = []
    for entry in merge_order:
        hard_blockers = [
            blocker for blocker in entry["blockers"] if blocker != "checks pending"
        ]
        if hard_blockers or entry["context_dependencies"]:
            release_blockers.append({
                "pr_number": entry["pr_number"],
                "blockers": hard_blockers,
                "context_dependencies": entry["context_dependencies"],
            })

    plan = {
        "schema_version": 1,
        "plan_id": plan_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ready_prs_excluded": [{"pr_number": pr["number"], "title": pr.get("title")} for pr in ready_excluded],
        "work_order": work_order,
        "merge_order": merge_order,
        "context_blockers": context_blockers,
        "release_blockers": release_blockers,
    }
    enriched_cards.sort(key=lambda card: card["autopr_plan"]["work_position"])
    return plan, enriched_cards


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", required=True)
    parser.add_argument("--prs", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cards-output", required=True)
    args = parser.parse_args()
    with open(args.cards, encoding="utf-8") as handle:
        cards = json.load(handle)
    with open(args.prs, encoding="utf-8") as handle:
        prs = json.load(handle)
    if not isinstance(cards, list) or not isinstance(prs, list):
        raise SystemExit("cards and PR context must both be JSON arrays")
    plan, enriched = build_plan(cards, prs)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, separators=(",", ":"))
        handle.write("\n")
    with open(args.cards_output, "w", encoding="utf-8") as handle:
        json.dump(enriched, handle, separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
