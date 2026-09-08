"""No test may infer "a database exists" from DATABASE_URL.

~40 modules `os.environ.setdefault("DATABASE_URL", "postgresql://test:test@…")`
at import so `app.config` can load, so the variable is always set in a
full-suite run. Five modules gated themselves on it being non-empty, skipped
correctly when run alone, and in a whole-suite run dialled a database that does
not exist — 29 errors locally, and in CI `FATAL: password authentication failed
for user "test"`, because there a Postgres really is listening on 5432.

That is invisible until the suite is run as a whole, which is exactly what
started happening on 2026-09-08. This guard keeps it visible.

    cd server && ./venv/bin/python -m pytest tests/_helpers/test_db_guard.py -q
"""

import ast
import os
from pathlib import Path

import pytest

from tests._helpers.db import (
    OPT_IN_ENV,
    PLACEHOLDER_URL,
    db_tests_enabled,
    real_database_url,
    requires_real_db,
)

TESTS_ROOT = Path(__file__).resolve().parents[1]
# This file names the pattern in prose and in assertions; the helper defines it.
_EXEMPT = {"tests/_helpers/db.py", "tests/_helpers/test_db_guard.py"}


def _module_paths() -> list[Path]:
    return sorted(p for p in TESTS_ROOT.rglob("*.py") if "__pycache__" not in str(p))


def _reads_database_url(tree: ast.AST) -> bool:
    """True if the module reads os.environ["DATABASE_URL"] / .get(...) — i.e.
    takes the variable as evidence rather than fabricating it via setdefault."""
    for node in ast.walk(tree):
        # os.environ.get("DATABASE_URL", ...) — setdefault is fine, it is how
        # modules make app.config importable and never implies a real database.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and any(
                isinstance(a, ast.Constant) and a.value == "DATABASE_URL"
                for a in node.args
            )
        ):
            return True
        # os.environ["DATABASE_URL"]
        if isinstance(node, ast.Subscript):
            sl = node.slice
            if isinstance(sl, ast.Constant) and sl.value == "DATABASE_URL":
                return True
    return False


def test_no_module_infers_a_database_from_the_env_var():
    """One test, not one per module: 600+ parametrised cases for a single
    invariant bury the suite count and say nothing extra. The failure lists
    every offender at once."""
    offenders = []
    for path in _module_paths():
        rel = str(path.relative_to(TESTS_ROOT.parent))
        if rel in _EXEMPT:
            continue
        if _reads_database_url(ast.parse(path.read_text(encoding="utf-8"))):
            offenders.append(rel)

    assert not offenders, (
        "these modules read DATABASE_URL directly: "
        + ", ".join(offenders)
        + f". In a full-suite run that variable is always set — other modules "
        f"setdefault it to {PLACEHOLDER_URL!r} — so a guard built on it does not "
        f"skip, and the test dials a database that isn't there. Use "
        f"tests._helpers.db.requires_real_db() and real_database_url() instead."
    )


class TestTheHelperItself:
    def test_opt_in_is_off_by_default_in_this_run(self):
        # The whole point: a normal `pytest tests` must not connect anywhere.
        # If someone exports RUN_DB_TESTS=1 in their shell this is a real skip,
        # not a failure.
        if os.getenv(OPT_IN_ENV) == "1":
            pytest.skip(f"{OPT_IN_ENV}=1 is set in this environment")
        assert db_tests_enabled() is False

    def test_placeholder_url_is_not_treated_as_a_database(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", PLACEHOLDER_URL)
        assert real_database_url() == ""

    def test_a_genuine_url_passes_through(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://matcha:pw@127.0.0.1:5432/matcha")
        assert real_database_url() == "postgresql://matcha:pw@127.0.0.1:5432/matcha"

    def test_absent_url_is_empty(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert real_database_url() == ""

    def test_the_mark_skips_when_not_opted_in(self, monkeypatch):
        monkeypatch.delenv(OPT_IN_ENV, raising=False)
        assert requires_real_db().args[0] is True  # skipif condition
