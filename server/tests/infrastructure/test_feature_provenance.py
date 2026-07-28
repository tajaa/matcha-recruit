"""record_feature_changes + feature_provenance — DB-free via a fake connection
that captures writes and serves canned reads, following the FakeConn pattern
in test_audit_log.py.
"""
import json
from datetime import datetime, timezone

import pytest

from app.core.services.feature_provenance import (
    feature_provenance,
    load_active_packs,
    record_feature_changes,
    resolve_addons,
    resolve_plan,
)


class FakeConn:
    def __init__(self, fetch_results=None):
        self.executemany_calls = []
        self.execute_calls = []
        # Queue of results returned by successive conn.fetch(...) calls, in order.
        self._fetch_results = list(fetch_results or [])

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))

    async def executemany(self, sql, rows):
        self.executemany_calls.append((sql, list(rows)))

    async def fetch(self, sql, *args):
        if not self._fetch_results:
            return []
        return self._fetch_results.pop(0)


# ── record_feature_changes ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_records_only_changed_keys():
    conn = FakeConn()
    await record_feature_changes(
        conn, "company-1",
        {"handbooks": True, "training": False, "incidents": False},
        {"handbooks": True, "training": True, "incidents": True},
        source="admin_toggle", actor_user_id="user-1",
    )
    assert len(conn.executemany_calls) == 1
    _, rows = conn.executemany_calls[0]
    changed_features = {r[1] for r in rows}
    assert changed_features == {"training", "incidents"}
    for row in rows:
        assert row[0] == "company-1"
        assert row[4] == "admin_toggle"
        assert row[5] == "user-1"


@pytest.mark.asyncio
async def test_noop_when_nothing_changed():
    conn = FakeConn()
    await record_feature_changes(
        conn, "company-1", {"handbooks": True}, {"handbooks": True}, source="admin_toggle",
    )
    assert conn.executemany_calls == []


@pytest.mark.asyncio
async def test_unknown_source_is_rejected_without_raising():
    conn = FakeConn()
    # Must never raise — a bad source string can't be allowed to fail the
    # enabled_features write it's supposed to be observing.
    await record_feature_changes(
        conn, "company-1", {"handbooks": False}, {"handbooks": True}, source="not_a_real_source",
    )
    assert conn.executemany_calls == []


@pytest.mark.asyncio
async def test_never_raises_on_internal_error():
    class ExplodingConn(FakeConn):
        async def executemany(self, sql, rows):
            raise RuntimeError("db is down")

    conn = ExplodingConn()
    # Must not raise despite the underlying insert failing.
    await record_feature_changes(
        conn, "company-1", {"handbooks": False}, {"handbooks": True}, source="admin_toggle",
    )


# ── feature_provenance ───────────────────────────────────────────────────────


def _audit_row(feature, source, created_at, actor_user_id=None):
    return {"feature": feature, "source": source, "actor_user_id": actor_user_id, "created_at": created_at}


@pytest.mark.asyncio
async def test_tier_forced_takes_precedence():
    company_row = {
        "id": "co-1",
        "enabled_features": json.dumps({}),
        "signup_source": "matcha_lite",
    }
    # matcha_lite forces handbooks/employees True via TIER_REQUIRED_FEATURES —
    # no subscriptions, no audit rows needed to explain it.
    conn = FakeConn(fetch_results=[[]])  # audit rows only (no active_packs fetch needed)
    result = await feature_provenance(conn, company_row, products_by_slug={}, active_packs=[])
    assert result["handbooks"]["bucket"] == "tier_forced"
    assert result["handbooks"]["detail"] == "matcha_lite"


@pytest.mark.asyncio
async def test_addon_bucket_from_active_subscription():
    company_row = {
        "id": "co-1",
        "enabled_features": json.dumps({"ir_voice_intake": True, "incidents": True}),
        "signup_source": "matcha_lite",
    }
    conn = FakeConn(fetch_results=[[]])
    result = await feature_provenance(
        conn, company_row, products_by_slug={},
        active_packs=["matcha_lite_addon_voice_intake"],
    )
    assert result["ir_voice_intake"]["bucket"] == "addon"


@pytest.mark.asyncio
async def test_paid_gate_bucket():
    company_row = {
        "id": "co-1",
        "enabled_features": json.dumps({"incidents": True}),
        "signup_source": "matcha_lite",
    }
    conn = FakeConn(fetch_results=[[]])
    result = await feature_provenance(conn, company_row, products_by_slug={}, active_packs=[])
    assert result["incidents"]["bucket"] == "paid_gate"


@pytest.mark.asyncio
async def test_audit_bucket_when_nothing_else_explains_it():
    now = datetime.now(timezone.utc)
    company_row = {
        "id": "co-1",
        # `policies` is enabled but not part of matcha_lite's overlay/preset,
        # not an add-on, not a paid gate — only the audit log explains it.
        "enabled_features": json.dumps({"policies": True}),
        "signup_source": "matcha_lite",
    }
    conn = FakeConn(fetch_results=[
        [_audit_row("policies", "admin_toggle", now, actor_user_id="user-9")],
    ])
    result = await feature_provenance(conn, company_row, products_by_slug={}, active_packs=[])
    assert result["policies"]["bucket"] == "audit"
    assert result["policies"]["detail"]["source"] == "admin_toggle"
    assert result["policies"]["detail"]["actor_user_id"] == "user-9"


@pytest.mark.asyncio
async def test_unknown_bucket_when_nothing_explains_it():
    company_row = {
        "id": "co-1",
        "enabled_features": json.dumps({"policies": True}),
        "signup_source": "matcha_lite",
    }
    conn = FakeConn(fetch_results=[[]])  # no audit rows
    result = await feature_provenance(conn, company_row, products_by_slug={}, active_packs=[])
    assert result["policies"]["bucket"] == "unknown"
    assert result["policies"]["detail"] is None


# ── load_active_packs ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_active_packs_filters_inactive_and_null():
    conn = FakeConn(fetch_results=[[
        {"pack_id": "matcha_lite", "status": "active"},
        {"pack_id": "matcha_lite_addon_voice_intake", "status": "canceled"},
        {"pack_id": None, "status": "active"},
    ]])
    packs = await load_active_packs(conn, "co-1")
    assert packs == ["matcha_lite"]


# ── resolve_plan ──────────────────────────────────────────────────────────────


def test_resolve_plan_builtin_tier():
    plan = resolve_plan("matcha_x", products_by_slug={})
    assert plan == {"kind": "builtin", "slug": "matcha_x", "label": "Matcha-X"}


def test_resolve_plan_custom_product():
    class FakeProduct:
        name = "Safety Pro"
    plan = resolve_plan("product:safety-pro", products_by_slug={"safety-pro": FakeProduct()})
    assert plan == {"kind": "custom_product", "slug": "safety-pro", "label": "Safety Pro"}


def test_resolve_plan_custom_product_missing_row_falls_back_to_slug():
    # The product was deleted/renamed but the company's signup_source still
    # points at the old slug — don't crash, show the slug itself.
    plan = resolve_plan("product:gone-product", products_by_slug={})
    assert plan == {"kind": "custom_product", "slug": "gone-product", "label": "gone-product"}


def test_resolve_plan_unknown_signup_source():
    plan = resolve_plan("some_legacy_value", products_by_slug={})
    assert plan["kind"] == "unknown"


def test_resolve_plan_none_signup_source():
    plan = resolve_plan(None, products_by_slug={})
    assert plan["kind"] == "unknown"
    assert plan["label"] == "Unknown"


# ── resolve_addons ────────────────────────────────────────────────────────────


def test_resolve_addons_maps_active_packs_to_names():
    addons = resolve_addons(["matcha_lite_addon_voice_intake", "matcha_lite_addon_handbook_watch"])
    keys = {a["key"] for a in addons}
    assert keys == {"voice_intake", "handbook_watch"}
    assert all("name" in a and "feature" in a for a in addons)


def test_resolve_addons_ignores_non_addon_packs():
    assert resolve_addons(["matcha_lite", "product:safety-pro"]) == []


def test_resolve_addons_empty_list():
    assert resolve_addons([]) == []
