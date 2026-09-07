#!/usr/bin/env python3
"""Offline Alembic revision-graph queries with no dependency on the alembic package.

Reads ``revision`` / ``down_revision`` out of server/alembic/versions/*.py with
``ast`` so it runs anywhere python3 exists — the GitHub deploy runner and the
laptop both call it before touching prod, and neither has the server venv.

  alembic_graph.py heads [--versions DIR]
      One head revision id per line.

  alembic_graph.py pending [--versions DIR] <current_rev> [<current_rev> ...]
      Revisions not in the ancestor-closure of the given database heads, one
      "<rev>  <first docstring line>" per line, base-first. Empty output means
      the database is at every head.
"""

from __future__ import annotations

import argparse
import ast
import sys
import warnings
from pathlib import Path

# Migration docstrings occasionally carry psql-style "\d table" — ast.parse
# warns about the escape; that is noise here, not a graph problem.
warnings.filterwarnings("ignore", category=SyntaxWarning)

DEFAULT_VERSIONS = Path(__file__).resolve().parent.parent / "server" / "alembic" / "versions"


class Revision:
    __slots__ = ("id", "down", "doc", "path")

    def __init__(self, id: str, down: tuple[str, ...], doc: str, path: Path):
        self.id = id
        self.down = down
        self.doc = doc
        self.path = path


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def load_graph(versions: Path) -> dict[str, Revision]:
    graph: dict[str, Revision] = {}
    for path in sorted(versions.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise SystemExit(f"{path}: {exc}") from exc
        rev = down = None
        for node in tree.body:
            # Older files: `revision = "x"`; newer alembic templates annotate:
            # `revision: str = "x"` / `down_revision: Union[str, None] = ...`.
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
            else:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "revision":
                    rev = _literal(node.value)
                elif target.id == "down_revision":
                    down = _literal(node.value)
        if not isinstance(rev, str):
            continue
        if down is None:
            downs: tuple[str, ...] = ()
        elif isinstance(down, str):
            downs = (down,)
        else:
            downs = tuple(d for d in down if isinstance(d, str))
        if rev in graph:
            raise SystemExit(f"duplicate revision id {rev!r}: {graph[rev].path} and {path}")
        graph[rev] = Revision(rev, downs, (ast.get_docstring(tree) or "").strip(), path)
    if not graph:
        raise SystemExit(f"no migrations found under {versions}")
    return graph


def heads(graph: dict[str, Revision]) -> list[str]:
    referenced = {d for r in graph.values() for d in r.down}
    return sorted(r for r in graph if r not in referenced)


def closure(graph: dict[str, Revision], starts: list[str]) -> set[str]:
    seen: set[str] = set()
    stack = [s for s in starts if s in graph]
    unknown = [s for s in starts if s not in graph]
    if unknown:
        raise SystemExit(
            "database is at revision(s) not present in this checkout: "
            + ", ".join(unknown)
            + " — pull/checkout the branch that owns them before deploying"
        )
    while stack:
        rev = stack.pop()
        if rev in seen:
            continue
        seen.add(rev)
        stack.extend(d for d in graph[rev].down if d in graph)
    return seen


def topological(graph: dict[str, Revision]) -> list[str]:
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(rev: str) -> None:
        if state.get(rev) == 2:
            return
        if state.get(rev) == 1:
            raise SystemExit(f"cycle in alembic graph at {rev}")
        state[rev] = 1
        for d in graph[rev].down:
            if d in graph:
                visit(d)
        state[rev] = 2
        order.append(rev)

    for rev in sorted(graph):
        visit(rev)
    return order


def pending(graph: dict[str, Revision], current: list[str]) -> list[Revision]:
    applied = closure(graph, current)
    return [graph[r] for r in topological(graph) if r not in applied]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("heads", "pending"))
    parser.add_argument("current", nargs="*", help="revision ids the database is currently at")
    parser.add_argument("--versions", type=Path, default=DEFAULT_VERSIONS)
    args = parser.parse_args(argv)

    graph = load_graph(args.versions)
    if args.command == "heads":
        for h in heads(graph):
            print(h)
        return 0

    for rev in pending(graph, [c for c in args.current if c]):
        summary = rev.doc.splitlines()[0] if rev.doc else ""
        print(f"{rev.id}  {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
