from decimal import Decimal
import asyncio

from app.matcha.services.inventory.waste.par import (
    par_drift_pct, recommend_par, should_auto_apply,
)
from app.matcha.services.inventory.waste.par_store import apply_par_recommendations, plan_par_recommendations


class _Transaction:
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return False


class _ParStoreConn:
    def __init__(self, history_inserted):
        self.history_inserted = history_inserted
        self.queries = []

    async def fetch(self, query, *_args):
        self.queries.append(query)
        return [{
            'item_id': 'item-1', 'status': 'ready', 'confidence': 'medium',
            'recommended_par': Decimal('13'), 'par_basis': 'demand',
            'shelf_cap_quantity': None, 'current_par': Decimal('10'), 'par_source': 'auto',
        }]

    async def fetchrow(self, query, *_args):
        self.queries.append(query)
        if 'SELECT par_max_drift_pct' in query:
            return {'par_max_drift_pct': Decimal('0.5')}
        if 'INSERT INTO inventory_par_history' in query:
            return {'id': 'history-1'} if self.history_inserted else None
        if 'UPDATE inventory_items' in query:
            return {'id': 'item-1'}
        raise AssertionError(query)

    def transaction(self): return _Transaction()


class _ParPreviewConn(_ParStoreConn):
    async def fetch(self, query, *_args):
        self.queries.append(query)
        return [{
            'item_id': 'item-1', 'name': 'Gloves', 'status': 'ready', 'confidence': 'medium',
            'recommended_par': Decimal('13'), 'par_basis': 'demand', 'shelf_cap_quantity': None,
            'current_par': Decimal('10'), 'par_source': 'auto', 'already_applied': None,
        }]


def test_par_equals_lead_plus_safety_without_shelf_life():
    result = recommend_par(lead_demand=Decimal("20"), safety_demand=Decimal("10"), daily_demand=[], lead_time_days=2)
    assert result["recommended_par"] == Decimal("30")
    assert result["par_basis"] == "demand" and result["shelf_cap"] is None


def test_shelf_life_caps_par_and_can_signal_structural_deficit():
    result = recommend_par(lead_demand=Decimal("20"), safety_demand=Decimal("10"), daily_demand=[Decimal("2")] * 8, lead_time_days=2, shelf_life_days=4)
    assert result["recommended_par"] == Decimal("8")
    assert result["par_basis"] == "structural_deficit"
    assert result["structural_deficit"] is True


def test_shelf_window_past_horizon_falls_back():
    result = recommend_par(lead_demand=Decimal("20"), safety_demand=Decimal("10"), daily_demand=[Decimal("2")] * 3, lead_time_days=10, shelf_life_days=2)
    assert result["shelf_cap"] == Decimal("4")


def test_unready_status_yields_no_par():
    assert recommend_par(lead_demand=Decimal("2"), safety_demand=Decimal("1"), daily_demand=[], lead_time_days=1, status="no_demand")["recommended_par"] is None


def test_drift_pct_and_auto_apply_guards():
    assert par_drift_pct(Decimal("10"), Decimal("13")) == Decimal("0.3")
    assert par_drift_pct(Decimal("0"), Decimal("13")) is None
    assert should_auto_apply(current_par=Decimal("10"), recommended_par=Decimal("13"), par_source="manual", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (False, "manual_par_pinned")
    assert should_auto_apply(current_par=Decimal("10"), recommended_par=Decimal("40"), par_source="auto", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (False, "drift_exceeds_bound")
    assert should_auto_apply(current_par=None, recommended_par=Decimal("13"), par_source="auto", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (True, "first_par")
    assert should_auto_apply(current_par=Decimal("10"), recommended_par=Decimal("13"), par_source="auto", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (True, "within_bound")


def test_par_replay_does_not_update_item_after_history_conflict():
    conn = _ParStoreConn(history_inserted=False)
    result = asyncio.run(apply_par_recommendations(
        conn, company_id='company-1', run_id='run-1', user_id=None, mode='auto',
    ))
    assert result['applied'] == 0
    assert result['skipped'] == [{'item_id': 'item-1', 'reason': 'already_applied'}]
    assert not any('UPDATE inventory_items' in query for query in conn.queries)


def test_par_update_happens_after_history_claim():
    conn = _ParStoreConn(history_inserted=True)
    result = asyncio.run(apply_par_recommendations(
        conn, company_id='company-1', run_id='run-1', user_id=None, mode='auto',
    ))
    assert result['applied'] == 1
    history_at = next(index for index, query in enumerate(conn.queries) if 'INSERT INTO inventory_par_history' in query)
    update_at = next(index for index, query in enumerate(conn.queries) if 'UPDATE inventory_items' in query)
    assert history_at < update_at


def test_par_preview_never_reaches_a_writer():
    conn = _ParPreviewConn(history_inserted=True)
    result = asyncio.run(plan_par_recommendations(conn, company_id='company-1', run_id='run-1', mode='manual'))
    assert result['would_apply'] == 1
    assert result['proposals'][0]['overridable'] is False
    assert not any('INSERT INTO inventory_par_history' in query or 'UPDATE inventory_items' in query for query in conn.queries)
