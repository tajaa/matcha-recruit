"""feature_beta — admin DB override on top of the BETA_FEATURES code
constant. DB-free via a fake connection (same pattern as test_audit_log.py /
test_feature_provenance.py).
"""
import pytest

from app.core.services.feature_beta import load_beta_features, set_beta_status


class FakeConn:
    def __init__(self, table_exists=True, override_rows=None):
        self._table_exists = table_exists
        self._override_rows = override_rows or []
        self.execute_calls = []

    async def fetchval(self, sql, *args):
        return 1 if self._table_exists else None

    async def fetch(self, sql, *args):
        return self._override_rows

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))


@pytest.fixture(autouse=True)
def _reset_table_exists_cache(monkeypatch):
    # The module caches table-existence for the process lifetime — reset it
    # per test so one test's FakeConn(table_exists=False) doesn't leak into
    # the next test's assertions.
    import app.core.services.feature_beta as feature_beta
    monkeypatch.setattr(feature_beta, "_table_exists_cache", None)


@pytest.mark.asyncio
async def test_no_overrides_returns_code_constant(monkeypatch):
    monkeypatch.setattr("app.core.services.feature_beta.BETA_FEATURES", frozenset({"huume"}))
    conn = FakeConn(override_rows=[])
    result = await load_beta_features(conn)
    assert result == frozenset({"huume"})


@pytest.mark.asyncio
async def test_override_true_adds_a_feature_not_in_code_constant(monkeypatch):
    monkeypatch.setattr("app.core.services.feature_beta.BETA_FEATURES", frozenset())
    conn = FakeConn(override_rows=[{"feature_key": "property", "is_beta": True}])
    result = await load_beta_features(conn)
    assert result == frozenset({"property"})


@pytest.mark.asyncio
async def test_override_false_removes_a_code_beta_feature(monkeypatch):
    monkeypatch.setattr("app.core.services.feature_beta.BETA_FEATURES", frozenset({"huume"}))
    conn = FakeConn(override_rows=[{"feature_key": "huume", "is_beta": False}])
    result = await load_beta_features(conn)
    assert result == frozenset()


@pytest.mark.asyncio
async def test_missing_table_falls_back_to_code_constant(monkeypatch):
    # The deploy-ahead-of-migration case — must not 500 or silently disable
    # the gate, just skip the override layer.
    monkeypatch.setattr("app.core.services.feature_beta.BETA_FEATURES", frozenset({"huume"}))
    conn = FakeConn(table_exists=False)
    result = await load_beta_features(conn)
    assert result == frozenset({"huume"})


@pytest.mark.asyncio
async def test_set_beta_status_rejects_unknown_feature():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await set_beta_status(conn, "not_a_real_feature", True)
    assert conn.execute_calls == []


@pytest.mark.asyncio
async def test_set_beta_status_writes_upsert():
    conn = FakeConn()
    await set_beta_status(conn, "huume", False, actor_user_id="user-1")
    assert len(conn.execute_calls) == 1
    _, args = conn.execute_calls[0]
    assert args == ("huume", False, "user-1")
