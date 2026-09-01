#!/usr/bin/env python3
"""Build a production-bounded changelog drafting plan from merged PR metadata."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_PR_ID_RE = re.compile(r"^pr-(\d+)-")
_IGNORED_PREFIXES = (
    ".github/",
    "docs/",
    "scripts/",
    "server/tests/",
    "client/src/test/",
    "client/src/tests/",
    "platforms/",
    "agent-ui/",
)
_IGNORED_EXACT = {"CLAUDE.md", "AGENTS.md", "README.md"}
_MERGE_CURSOR_OVERLAP = timedelta(hours=24)


class CollectionError(RuntimeError):
    """The deployed boundary could not be established safely."""


def slugify(title: str, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    if len(slug) <= max_len:
        return slug
    truncated = slug[:max_len]
    if "-" in truncated:
        truncated = truncated.rsplit("-", 1)[0]
    return truncated.strip("-")


def entry_id(pr_number: int, title: str) -> str:
    return f"pr-{pr_number}-{slugify(title)}"


def products_for_files(files: list[str]) -> set[str]:
    """Return changelog products represented by production application paths."""
    products: set[str] = set()
    for path in files:
        if path.startswith(_IGNORED_PREFIXES) or path in _IGNORED_EXACT or path.endswith(".md"):
            continue
        if path.startswith(("server/app/tellus/", "client/tellus/")):
            products.add("tellus")
        elif path.startswith(("server/app/", "client/src/", "client/public/")):
            products.add("matcha")
    return products


def components_for_files(files: list[str]) -> set[str]:
    """Return live EC2 image components that must contain a PR before publication."""
    components: set[str] = set()
    for path in files:
        if path.startswith(_IGNORED_PREFIXES) or path in _IGNORED_EXACT or path.endswith(".md"):
            continue
        if path.startswith("server/"):
            components.add("backend")
        elif path.startswith("client/"):
            components.add("frontend")
    return components


def _revision_for_path(repo_root: Path, relative_path: str) -> str | None:
    if not relative_path.startswith("server/alembic/versions/") or not relative_path.endswith(".py"):
        return None
    path = repo_root / relative_path
    if not path.is_file():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "revision" for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    if not ancestor or not descendant:
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _max_pr_from_ids(state: dict[str, Any]) -> int | None:
    numbers: list[int] = []
    for ids in (state.get("existing") or {}).values():
        for value in ids or []:
            match = _PR_ID_RE.match(str(value))
            if match:
                numbers.append(int(match.group(1)))
    return max(numbers) if numbers else None


def _existing_pr_numbers(state: dict[str, Any], product: str) -> set[int]:
    numbers: set[int] = set()
    for value in (state.get("existing") or {}).get(product, []):
        match = _PR_ID_RE.match(str(value))
        if match:
            numbers.add(int(match.group(1)))
    return numbers


def _merge_oid(pr: dict[str, Any]) -> str:
    merge_commit = pr.get("mergeCommit") or {}
    if isinstance(merge_commit, dict):
        return str(merge_commit.get("oid") or "")
    return ""


def _file_paths(pr: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for item in pr.get("files") or []:
        if isinstance(item, dict) and item.get("path"):
            paths.append(str(item["path"]))
        elif isinstance(item, str):
            paths.append(item)
    return paths


def _timestamp(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollectionError(f"invalid {field} timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_plan(
    *,
    production_context: dict[str, Any],
    production_state: dict[str, Any],
    merged_prs: list[dict[str, Any]],
    deployment: dict[str, Any],
    repo_root: Path,
    since_pr: int | None = None,
) -> dict[str, Any]:
    stored = production_state.get("last_pr_number")
    inferred = _max_pr_from_ids(production_state)
    if since_pr is None:
        since_pr = int(stored) if stored is not None else inferred
    if since_pr is None:
        raise CollectionError(
            "production has no changelog watermark or PR-derived update id; "
            "run the workflow manually once with since_pr"
        )

    containers = production_context.get("containers") or {}
    live_shas = {
        "backend": str((containers.get("backend") or {}).get("git_sha") or ""),
        "frontend": str((containers.get("frontend") or {}).get("git_sha") or ""),
    }
    if not all(live_shas.values()):
        raise CollectionError("production context is missing active backend/frontend SHAs")

    deployed_at = str(deployment.get("deployed_at") or production_context.get("checked_at") or "")
    deployment_date = _timestamp(deployed_at, field="deployment").date().isoformat()

    state_updated_at_raw = production_state.get("updated_at")
    state_updated_at = (
        _timestamp(state_updated_at_raw, field="production state")
        if state_updated_at_raw
        else None
    )
    overlap_start = state_updated_at - _MERGE_CURSOR_OVERLAP if state_updated_at else None

    pending_migrations = set((production_context.get("database") or {}).get("pending_migrations") or [])
    existing_by_product = {
        product: _existing_pr_numbers(production_state, product)
        for product in ("matcha", "tellus")
    }

    candidates: list[dict[str, Any]] = []
    automatic_skips: list[dict[str, Any]] = []
    deferred: dict[str, Any] | None = None
    target_watermark = since_pr
    processed_any = False

    ordered = sorted(
        (
            pr
            for pr in merged_prs
            if int(pr.get("number") or 0) > since_pr
            or (
                overlap_start is not None
                and _timestamp(pr.get("mergedAt"), field="PR merge") > overlap_start
            )
        ),
        key=lambda pr: (_timestamp(pr.get("mergedAt"), field="PR merge"), int(pr["number"])),
    )
    for pr in ordered:
        number = int(pr["number"])
        title = str(pr.get("title") or "").strip()
        files = _file_paths(pr)
        components = components_for_files(files)
        products = products_for_files(files)

        if not components or not products:
            automatic_skips.append({
                "sourcePr": number,
                "reason": "No deployed Matcha or Tell-Us application surface changed.",
            })
            target_watermark = max(target_watermark, number)
            processed_any = True
            continue

        merge_oid = _merge_oid(pr)
        missing_components = [
            component
            for component in sorted(components)
            if not _is_ancestor(repo_root, merge_oid, live_shas[component])
        ]
        if missing_components:
            deferred = {
                "sourcePr": number,
                "reason": "PR is not present in every required active production image.",
                "missingComponents": missing_components,
            }
            break

        touched_pending = sorted({
            revision
            for path in files
            if (revision := _revision_for_path(repo_root, path)) in pending_migrations
        })
        if touched_pending:
            deferred = {
                "sourcePr": number,
                "reason": "PR depends on a migration that production has not applied.",
                "pendingMigrations": touched_pending,
            }
            break

        missing_products = [
            product for product in sorted(products)
            if number not in existing_by_product[product]
        ]
        if missing_products:
            candidates.append({
                "sourcePr": number,
                "id": entry_id(number, title),
                "date": deployment_date,
                "title": title,
                "body": str(pr.get("body") or "")[:6000],
                "url": str(pr.get("url") or ""),
                "mergedAt": str(pr.get("mergedAt") or ""),
                "mergeOid": merge_oid,
                "requiredComponents": sorted(components),
                "products": missing_products,
                "files": files[:200],
            })
        target_watermark = max(target_watermark, number)
        processed_any = True

    # A partial publication could move the numeric watermark beyond a blocked,
    # lower-number PR. Keep the entire batch pending until every selected PR is
    # confirmed in production; the next run will safely reconsider the batch.
    can_publish = processed_any and deferred is None
    if not can_publish:
        target_watermark = since_pr

    units = [
        {
            "sourcePr": candidate["sourcePr"],
            "product": product,
            "id": candidate["id"],
            "date": candidate["date"],
        }
        for candidate in candidates
        for product in candidate["products"]
    ]

    return {
        "schemaVersion": 1,
        "sourceWatermark": since_pr,
        "sourceStateUpdatedAt": state_updated_at_raw,
        "mergeCursorOverlapHours": int(_MERGE_CURSOR_OVERLAP.total_seconds() / 3600),
        "targetWatermark": target_watermark,
        "hasWork": can_publish,
        "needsDraft": can_publish and bool(units),
        "deployment": deployment,
        "production": {
            "buildNumber": production_context.get("build_number"),
            "liveShas": live_shas,
            "databaseStatus": (production_context.get("database") or {}).get("status"),
        },
        "candidates": candidates,
        "units": units,
        "automaticSkips": automatic_skips,
        "deferred": deferred,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-context", required=True, type=Path)
    parser.add_argument("--production-state", required=True, type=Path)
    parser.add_argument("--merged-prs", required=True, type=Path)
    parser.add_argument("--deployment", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--since-pr", type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        plan = build_plan(
            production_context=json.loads(args.production_context.read_text(encoding="utf-8")),
            production_state=json.loads(args.production_state.read_text(encoding="utf-8")),
            merged_prs=json.loads(args.merged_prs.read_text(encoding="utf-8")),
            deployment=json.loads(args.deployment.read_text(encoding="utf-8")),
            repo_root=args.repo_root.resolve(),
            since_pr=args.since_pr,
        )
    except (CollectionError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
