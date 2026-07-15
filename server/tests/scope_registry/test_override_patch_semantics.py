"""override_classification is a PATCH — an unsent field keeps its stored value.

Two fields are load-bearing here, and defaulting either to None is a silent
scope change rather than an edit:

  jurisdiction_scope  — None WIDENS a narrowed classification to whole-index reach.
  entity_condition    — None turns a CONDITIONAL obligation into a universal one.

The entity_condition case is the sharper one. `validate_proposal` REJECTS
`conditional` without a valid condition, so an editor that can't re-supply the
trigger cannot save a conditional item at all — and the tempting workaround
(flip the disposition to universal_in_domain just to get a regulation_key
stored) wipes the trigger and serves e.g. the PSM standard to every company.
That is precisely the over-scope the §9 acceptance test exists to prevent.
"""
import json
from uuid import uuid4

import pytest

from app.core.services.scope_registry.classify import override_classification

PSM = {"type": "attribute", "key": "psm_covered_chemicals",
       "operator": "eq", "value": True}
SCOPE = {"level": "county", "names": ["Los Angeles"]}


class FakeConn:
    """Enough of asyncpg for override_classification: the stored row, the RKD
    keyset, and a record of what the upsert was handed."""

    def __init__(self, stored):
        self.stored = stored
        self.upserted = None

    async def fetchrow(self, sql, *args):
        if "jurisdiction_scope, entity_condition" in sql:
            # asyncpg hands JSONB back as a str on this pool.
            return {
                "jurisdiction_scope": json.dumps(self.stored["jurisdiction_scope"])
                if self.stored["jurisdiction_scope"] else None,
                "entity_condition": json.dumps(self.stored["entity_condition"])
                if self.stored["entity_condition"] else None,
            }
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetch(self, sql, *args):
        if "regulation_key_definitions" in sql:
            return [{"key": "process_safety_management", "category_slug": "workplace_safety"}]
        return []  # the propagation UPDATE ... RETURNING

    async def fetchval(self, sql, *args):
        if "authority_index_items" in sql:
            return 1  # the item exists
        return None

    async def execute(self, sql, *args):
        # Only the classification upsert — later statements (the unclassified
        # recount) would otherwise clobber the capture.
        if "INSERT INTO authority_item_classifications" in sql:
            self.upserted = (sql, args)

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Tx()


@pytest.fixture(autouse=True)
def _no_strata(monkeypatch):
    """recompute_strata is a DB pass we don't exercise here."""
    import app.core.services.scope_registry.strata as strata

    async def _noop(conn):
        return {"strata": 0, "items": 0, "keys": 0}

    monkeypatch.setattr(strata, "recompute_strata", _noop)


def _upserted(conn, field):
    """The value handed to _upsert_classification for `field`."""
    # _upsert_classification passes entity_condition / jurisdiction_scope as
    # json strings; args order is fixed by its INSERT.
    sql, args = conn.upserted
    idx = {"entity_condition": 4, "jurisdiction_scope": 12}[field]
    raw = args[idx]
    return json.loads(raw) if isinstance(raw, str) else raw


@pytest.mark.asyncio
async def test_unsent_entity_condition_is_preserved_not_wiped():
    """The whole point: re-key a conditional item without re-supplying its
    trigger. Before the fix this either 400'd (conditional + no condition) or —
    via the universal_in_domain workaround — silently universalized it."""
    conn = FakeConn({"entity_condition": PSM, "jurisdiction_scope": None})

    await override_classification(
        conn, uuid4(),
        # No entity_condition in the proposal — the editor has no trigger UI.
        {"disposition": "conditional",
         "regulation_key": "process_safety_management",
         "category_slug": "workplace_safety"},
        uuid4(),
    )

    assert _upserted(conn, "entity_condition") == PSM


@pytest.mark.asyncio
async def test_unsent_jurisdiction_scope_is_preserved_not_widened():
    conn = FakeConn({"entity_condition": None, "jurisdiction_scope": SCOPE})

    await override_classification(
        conn, uuid4(), {"disposition": "universal_in_domain"}, uuid4(),
    )

    assert _upserted(conn, "jurisdiction_scope") == SCOPE


@pytest.mark.asyncio
async def test_an_explicit_null_still_clears():
    """PATCH-preserve must not become impossible-to-clear."""
    conn = FakeConn({"entity_condition": PSM, "jurisdiction_scope": SCOPE})

    await override_classification(
        conn, uuid4(),
        {"disposition": "universal_in_domain",
         "entity_condition": None, "jurisdiction_scope": None},
        uuid4(),
    )

    assert _upserted(conn, "entity_condition") is None
    assert _upserted(conn, "jurisdiction_scope") is None
