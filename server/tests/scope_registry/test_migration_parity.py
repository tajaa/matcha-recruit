"""The scoperg01 seed must mirror scope_registry/categories.py exactly.

The migration hardcodes a SQL snapshot of the code taxonomy (a migration must
not import app code — its meaning is frozen at authoring time). This test is
what keeps the two from drifting: add a category to one and not the other and
it fails.
"""
import re
from pathlib import Path

from app.core.services.scope_registry.categories import CATEGORIES

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "scoperg01_scope_registry.py"
)

# One tuple per seeded row: ('slug', 'label', parent, ...)
_ROW_RE = re.compile(r"\(\s*'([a-z_]+)',\s*'[^']*',\s*(NULL|'([a-z_]+)'),")


def _seeded_rows():
    src = _MIGRATION.read_text()
    seed_block = src.split("INSERT INTO business_categories", 1)[1]
    seed_block = seed_block.split("ON CONFLICT", 1)[0]
    return {
        m.group(1): (m.group(3) if m.group(2) != "NULL" else None)
        for m in _ROW_RE.finditer(seed_block)
    }


def test_migration_seeds_exactly_the_code_taxonomy():
    seeded = _seeded_rows()
    assert set(seeded) == set(CATEGORIES), (
        f"only in migration: {set(seeded) - set(CATEGORIES)}; "
        f"only in code: {set(CATEGORIES) - set(seeded)}"
    )


def test_migration_parents_match_code():
    seeded = _seeded_rows()
    for slug, parent in seeded.items():
        assert parent == CATEGORIES[slug].parent, slug


def test_migration_seeds_parents_before_children():
    seeded = list(_seeded_rows())  # dict preserves insertion = file order
    for i, slug in enumerate(seeded):
        parent = CATEGORIES[slug].parent
        if parent is not None:
            assert seeded.index(parent) < i, (
                f"{slug} seeded before its parent {parent} — the self-FK will reject it"
            )
