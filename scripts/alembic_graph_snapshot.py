#!/usr/bin/env python3
"""Read an Alembic revision graph without importing Alembic.

The Kanban autopr runner intentionally does not install the backend virtualenv.
Migration metadata is static Python assignment data, so parsing it with the
standard library is enough to identify repository heads and revisions and to
compare them with the current production heads.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Revision:
    revision: str
    parents: tuple[str, ...]
    down_revision: tuple[str, ...]
    summary: str


def _assignment_values(tree: ast.Module) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in tree.body:
        name: str | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name, value = target.id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        if name in {"revision", "down_revision", "depends_on"} and value is not None:
            values[name] = ast.literal_eval(value)
    return values


def _validate_entrypoints(tree: ast.Module, *, path: Path) -> None:
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted({"upgrade", "downgrade"} - functions)
    if missing:
        raise ValueError(
            f"{path}: missing migration entrypoint(s): {', '.join(missing)}"
        )


def _as_revisions(value: object, *, field: str, path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise ValueError(f"{path}: {field} must be None, a string, or a sequence of strings")


def load_graph(
    versions_dir: Path,
    *,
    exclude: frozenset[Path] = frozenset(),
    require_nonempty: bool = True,
) -> dict[str, Revision]:
    """Read the revision graph.

    Deliberately lenient about anything that is not graph structure: this runs
    on the trusted path (``resolve-production-context.sh``) over migrations a
    human already merged, and a hand-written data migration with no
    ``downgrade()`` must never take the whole AutoPR run down. Validation of a
    *drafted* migration lives in :func:`check_drafts`.
    """
    graph: dict[str, Revision] = {}
    for path in sorted(versions_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        if path.resolve() in exclude:
            continue
        # Migration docstrings may contain SQL regex examples such as ``\d``.
        # They are harmless metadata here but newer Python versions warn while
        # parsing them; keep stderr clean because the shell treats any parser
        # diagnostics as a failed/invalid JSON snapshot.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        values = _assignment_values(tree)
        revision = values.get("revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{path}: missing literal revision id")
        if revision in graph:
            raise ValueError(f"duplicate revision id {revision}: {path}")
        parents = _as_revisions(values.get("down_revision"), field="down_revision", path=path)
        dependencies = _as_revisions(values.get("depends_on"), field="depends_on", path=path)
        summary = (ast.get_docstring(tree) or "").strip().splitlines()
        graph[revision] = Revision(
            revision=revision,
            parents=tuple(dict.fromkeys((*parents, *dependencies))),
            down_revision=parents,
            summary=summary[0] if summary else "",
        )

    if not graph and require_nonempty:
        raise ValueError(f"no Alembic revisions found in {versions_dir}")
    missing = sorted(
        {parent for item in graph.values() for parent in item.parents} - set(graph)
    )
    if missing:
        raise ValueError(f"migration graph references missing revisions: {', '.join(missing)}")
    return graph


def heads(graph: dict[str, Revision]) -> list[str]:
    referenced = {parent for item in graph.values() for parent in item.parents}
    return sorted(set(graph) - referenced)


def topological_order(graph: dict[str, Revision]) -> list[str]:
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(revision: str) -> None:
        if revision in visited:
            return
        if revision in visiting:
            raise ValueError(f"cycle detected at revision {revision}")
        visiting.add(revision)
        for parent in sorted(graph[revision].parents):
            visit(parent)
        visiting.remove(revision)
        visited.add(revision)
        ordered.append(revision)

    for revision in sorted(graph):
        visit(revision)
    return ordered


def ancestor_closure(graph: dict[str, Revision], current: list[str]) -> set[str]:
    applied: set[str] = set()

    def include(revision: str) -> None:
        if revision in applied or revision not in graph:
            return
        applied.add(revision)
        for parent in graph[revision].parents:
            include(parent)

    for revision in current:
        include(revision)
    return applied


def snapshot(versions_dir: Path, current: list[str]) -> dict[str, object]:
    graph = load_graph(versions_dir)
    order = topological_order(graph)
    applied = ancestor_closure(graph, current)
    pending = [
        f"{revision}  {graph[revision].summary}".rstrip()
        for revision in order
        if revision not in applied
    ]
    return {
        "heads": heads(graph),
        "revisions": sorted(graph),
        "pending": pending,
        "unknown_current": sorted(set(current) - set(graph)),
    }


def check_drafts(versions_dir: Path, drafts: list[Path]) -> list[str]:
    """Validate migration files a bot drafted, returning one message per problem.

    Everything here is a rule the trusted publisher enforces on bot output only.
    It is deliberately stricter than :func:`load_graph`: a draft must be a real
    version file that extends exactly one current head, so a merged PR can never
    silently fork the graph or add a second base.
    """
    errors: list[str] = []
    resolved_dir = versions_dir.resolve()
    draft_revisions: dict[Path, str] = {}
    for draft in drafts:
        path = draft.resolve()
        if path.parent != resolved_dir:
            errors.append(f"{draft}: is not a file in {versions_dir}")
            continue
        if path.name == "__init__.py":
            errors.append(f"{draft}: is not a migration version file")
            continue
        if not path.is_file():
            errors.append(f"{draft}: does not exist")
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(draft))
        except SyntaxError as exc:
            errors.append(f"{draft}: is not valid Python: {exc}")
            continue
        try:
            _validate_entrypoints(tree, path=draft)
        except ValueError as exc:
            errors.append(str(exc))
        revision = _assignment_values(tree).get("revision")
        if not isinstance(revision, str) or not revision:
            errors.append(f"{draft}: missing literal revision id")
            continue
        draft_revisions[path] = revision
    if errors:
        return errors

    excluded = frozenset(draft_revisions)
    try:
        base = load_graph(versions_dir, exclude=excluded, require_nonempty=False)
        full = load_graph(versions_dir)
    except ValueError as exc:
        return [str(exc)]

    base_heads = set(heads(base))
    new_revisions = set(full) - set(base)
    for path, revision in sorted(draft_revisions.items()):
        if revision not in new_revisions:
            errors.append(
                f"{path.name}: revision {revision} is already present on the base graph"
            )
    if errors:
        return errors

    for path, revision in sorted(draft_revisions.items()):
        parents = full[revision].down_revision
        if not parents:
            errors.append(
                f"{path.name}: down_revision is None \u2014 a draft may not add a new base"
            )
            continue
        for parent in parents:
            if parent not in base_heads and parent not in new_revisions:
                errors.append(
                    f"{path.name}: down_revision {parent} is not a current head "
                    f"({', '.join(sorted(base_heads)) or 'none'})"
                )
    if errors:
        return errors

    if len(heads(full)) != len(base_heads):
        errors.append(
            f"drafts change the head count {len(base_heads)} \u2192 {len(heads(full))}; "
            "each draft must extend exactly one current head"
        )
    try:
        topological_order(full)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-drafts",
        action="store_true",
        help="validate the named version files as bot-drafted migrations",
    )
    parser.add_argument("versions_dir", type=Path)
    parser.add_argument("current", nargs="*")
    args = parser.parse_args()
    if args.check_drafts:
        if not args.current:
            parser.error("--check-drafts needs at least one version file")
        errors = check_drafts(args.versions_dir, [Path(item) for item in args.current])
        for error in errors:
            print(error, file=sys.stderr)
        return 1 if errors else 0
    print(json.dumps(snapshot(args.versions_dir, args.current), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
