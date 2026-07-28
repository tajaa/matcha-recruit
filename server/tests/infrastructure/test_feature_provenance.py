"""record_feature_changes + feature_provenance — DB-free via a fake connection
that captures writes and serves canned reads, following the FakeConn pattern
in test_audit_log.py.
"""
import json
from datetime import datetime, timezone

import pytest

from app.core.services.feature_provenance import feature_provenance, record_feature_changes


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
    conn = FakeConn(fetch_results=[[], []])  # mw_subscriptions rows, audit rows
    result = await feature_provenance(conn, company_row, products_by_slug={})
    assert result["handbooks"]["bucket"] == "tier_forced"
    assert result["handbooks"]["detail"] == "matcha_lite"


@pytest.mark.asyncio
async def test_addon_bucket_from_active_subscription():
    company_row = {
        "id": "co-1",
        "enabled_features": json.dumps({"ir_voice_intake": True, "incidents": True}),
        "signup_source": "matcha_lite",
    }
    conn = FakeConn(fetch_results=[
        [{"pack_id": "matcha_lite_addon_voice_intake", "status": "active"}],
        [],
    ])
    result = await feature_provenance(conn, company_row, products_by_slug={})
    assert result["ir_voice_intake"]["bucket"] == "addon"


@pytest.mark.asyncio
async def test_paid_gate_bucket():
    company_row = {
        "id": "co-1",
        "enabled_features": json.dumps({"incidents": True}),
        "signup_source": "matcha_lite",
    }
    conn = FakeConn(fetch_results=[[], []])
    result = await feature_provenance(conn, company_row, products_by_slug={})
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
        [],
        [_audit_row("policies", "admin_toggle", now, actor_user_id="user-9")],
    ])
    result = await feature_provenance(conn, company_row, products_by_slug={})
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
    conn = FakeConn(fetch_results=[[], []])  # no subs, no audit rows
    result = await feature_provenance(conn, company_row, products_by_slug={})
    assert result["policies"]["bucket"] == "unknown"
    assert result["policies"]["detail"] is None
