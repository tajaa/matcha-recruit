"""MANUAL, read-only DB integration checks for the gap-surface engine bridge.

Skipped by default (needs a live dev DB + the scope-registry tables). Run on dev
with the tunnels up (``./scripts/dev-remote.sh``):

    RUN_DB_GAP_TESTS=1 \
    GAP_TEST_STATE=CA GAP_TEST_INDUSTRY=healthcare \
    GAP_TEST_COMPANY_ID=<uuid> \
    ./venv/bin/python -m pytest tests/scope_registry/test_gap_surfaces_integration.py -q

These are strictly READ-ONLY — no seeding, no DDL, no mutation (root CLAUDE.md:
never auto-run DB-mutating tests). They assert response *shape* + the anti-
regression invariant, not exact counts (which depend on live classification).
All app imports are inside the tests so plain collection never pulls asyncpg.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_GAP_TESTS") != "1",
    reason="manual DB integration test — set RUN_DB_GAP_TESTS=1 on dev to run",
)


@pytest.mark.asyncio
async def test_chain_category_coverage_shape():
    from app.database import get_connection
    from app.core.services.scope_registry.gap_surfaces import (
        resolve_chain_category_coverage,
    )
    from app.core.routes.admin import _resolve_jurisdiction_chain  # type: ignore

    state = os.getenv("GAP_TEST_STATE", "CA")
    industry = os.getenv("GAP_TEST_INDUSTRY", "healthcare")
    async with get_connection() as conn:
        chain = await _resolve_jurisdiction_chain(conn, state.upper(), None)
        assert chain["state_found"], f"no jurisdiction row for {state}"
        cov = await resolve_chain_category_coverage(
            conn, chain_ids=chain["ids"], industry=industry,
        )
    assert set(cov) == {"registry_definitive", "by_category"}
    assert isinstance(cov["registry_definitive"], bool)
    for slug, cell in cov["by_category"].items():
        assert set(cell) == {"expected", "codified", "to_codify", "to_codify_keys"}
        # codified never exceeds expected; to_codify is the complement.
        assert cell["codified"] + cell["to_codify"] == cell["expected"]


@pytest.mark.asyncio
async def test_company_scope_shape_and_source():
    from app.database import get_connection
    from app.core.services.scope_registry.gap_surfaces import resolve_company_scope

    company_id = os.getenv("GAP_TEST_COMPANY_ID")
    if not company_id:
        pytest.skip("set GAP_TEST_COMPANY_ID to a real dev company uuid")
    from uuid import UUID

    industry = os.getenv("GAP_TEST_INDUSTRY", "healthcare")
    async with get_connection() as conn:
        # use_cache=False keeps this genuinely read-only — use_cache=True would
        # INSERT into scope_resolutions, violating this file's contract.
        agg = await resolve_company_scope(
            conn, UUID(company_id), industry=industry, use_cache=False,
        )
    assert agg["coverage_source"] in ("engine", "bank")
    assert 0 <= agg["coverage_pct"] <= 100
    assert agg["gate"]["engine"] + agg["gate"]["fallback"] == agg["gate"]["total"]
    assert agg["counts"]["locations"] + agg["counts"]["locations_failed"] == agg["gate"]["total"]
    # Engine verdict requires every coordinate resolved + definitive, none degraded.
    if agg["coverage_source"] == "engine":
        assert agg["gate"]["fallback"] == 0
        assert agg["counts"]["locations_failed"] == 0
        assert not agg["degraded"]
