"""Multi-component sales depletion stays atomic with reviewed mappings."""

import asyncio

import pytest

from app.matcha.services.inventory import sales_commit
from app.matcha.services.inventory import sales_mappings


def _run(coro):
    return asyncio.run(coro)


class _Transaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.transaction_depth += 1

    async def __aexit__(self, *_args):
        self.conn.transaction_depth -= 1
        return False


class FakeConn:
    def __init__(self):
        self.executed = []
        self.transaction_depth = 0

    async def fetchrow(self, query, *_args):
        if 'INSERT INTO inventory_sales_imports' in query:
            return {'id': 'import-1'}
        if 'INSERT INTO inventory_sales_lines' in query:
            return {'id': 'sales-line-1'}
        raise AssertionError(f'unexpected fetchrow: {query}')

    async def fetchval(self, query, *_args):
        if 'FROM inventory_sales_imports' in query:
            return None
        return True

    async def execute(self, query, *args):
        self.executed.append((query, args))

    def transaction(self):
        return _Transaction(self)


def _recipe_line():
    return {
        'sold_name': 'Vanilla latte',
        'quantity': 3,
        'gross_sales': 18,
        'status': 'mapped',
        'components': [
            {'item_id': 'cup', 'quantity_per_sale': 1},
            {'item_id': 'milk', 'quantity_per_sale': 0.25},
            {'item_id': 'coffee', 'quantity_per_sale': 0.04},
            {'item_id': 'syrup', 'quantity_per_sale': 0.02},
        ],
        'new_mapping': {
            'kind': 'recipe',
            'components': [
                {'item_id': 'cup', 'quantity_per_sale': 1},
                {'item_id': 'milk', 'quantity_per_sale': 0.25},
                {'item_id': 'coffee', 'quantity_per_sale': 0.04},
                {'item_id': 'syrup', 'quantity_per_sale': 0.02},
            ],
        },
    }


def test_recipe_sales_deplete_each_component_and_save_mapping_in_commit_transaction(monkeypatch):
    conn = FakeConn()
    saved = []
    movement_calls = []

    async def validate_mapping(*_args, **_kwargs):
        return None

    async def upsert_mapping(conn, **kwargs):
        assert conn.transaction_depth == 1
        saved.append(kwargs)
        return {'id': 'mapping-latte', 'components': kwargs['components']}

    async def record_movements(_conn, **kwargs):
        movement_calls.append(kwargs)
        return []

    monkeypatch.setattr(sales_commit.sales_mappings, 'validate_mapping', validate_mapping)
    monkeypatch.setattr(sales_commit.sales_mappings, 'upsert_mapping', upsert_mapping)
    monkeypatch.setattr(sales_commit.movements_service, 'record_movements', record_movements)

    result = _run(sales_commit.commit_sales_import(
        conn, company_id='company-1', user_id='user-1', location_id=None,
        business_date='2026-08-25', source='upload', filename='sales.csv',
        gmail_message_id=None, lines=[_recipe_line()],
    ))

    assert result['items_affected'] == 4
    assert saved[0]['kind'] == 'recipe'
    assert movement_calls[0]['lines'] == [
        {'item_id': 'cup', 'quantity': 3.0, 'estimated': False},
        {'item_id': 'milk', 'quantity': 0.75, 'estimated': False},
        {'item_id': 'coffee', 'quantity': 0.12, 'estimated': False},
        {'item_id': 'syrup', 'quantity': 0.06, 'estimated': False},
    ]
    snapshots = [args for query, args in conn.executed if 'inventory_sales_line_components' in query]
    assert snapshots == [
        ('sales-line-1', 'cup', 1, None),
        ('sales-line-1', 'milk', 0.25, None),
        ('sales-line-1', 'coffee', 0.04, None),
        ('sales-line-1', 'syrup', 0.02, None),
    ]


def test_unmapped_sibling_does_not_save_reviewed_recipe(monkeypatch):
    conn = FakeConn()
    saved = []

    async def validate_mapping(*_args, **_kwargs):
        return None

    async def upsert_mapping(*_args, **_kwargs):
        saved.append(True)
        return {'id': 'mapping-latte', 'components': []}

    monkeypatch.setattr(sales_commit.sales_mappings, 'validate_mapping', validate_mapping)
    monkeypatch.setattr(sales_commit.sales_mappings, 'upsert_mapping', upsert_mapping)

    result = _run(sales_commit.commit_sales_import(
        conn, company_id='company-1', user_id='user-1', location_id=None,
        business_date='2026-08-25', source='upload', filename='sales.csv',
        gmail_message_id=None,
        lines=[_recipe_line(), {'sold_name': 'Unknown drink', 'quantity': 1, 'status': 'unmapped'}],
    ))

    assert result['unmapped'] == 1
    assert saved == []


def test_recipe_mapping_rejects_duplicate_stock_components():
    try:
        _run(sales_mappings.validate_mapping(
            None, company_id='company-1', location_id=None, kind='recipe',
            components=[
                {'item_id': 'milk', 'quantity_per_sale': 0.25},
                {'item_id': 'milk', 'quantity_per_sale': 0.1},
            ],
        ))
    except ValueError as exc:
        assert str(exc) == 'mapping components must use distinct inventory items'
    else:
        raise AssertionError('duplicate recipe components must be rejected')


def test_foreign_mapping_id_is_rejected_without_persisting_it():
    class ForeignMappingConn(FakeConn):
        async def fetchval(self, query, *args):
            if 'FROM inventory_sales_mappings' in query:
                return False
            return await super().fetchval(query, *args)

    conn = ForeignMappingConn()
    result = _run(sales_commit.commit_sales_import(
        conn, company_id='company-1', user_id='user-1', location_id=None,
        business_date='2026-08-25', source='upload', filename='sales.csv',
        gmail_message_id=None,
        lines=[{
            'sold_name': 'Vanilla latte', 'quantity': 1, 'mapping_id': 'foreign-mapping',
            'components': [{'item_id': 'attacker-supplied', 'quantity_per_sale': 1}],
        }],
    ))

    assert result['errors'] == [{'row': 1, 'item': 'Vanilla latte', 'error': 'sales mapping not found'}]
    sales_line_args = next(args for query, args in conn.executed if 'INSERT INTO inventory_sales_lines' in query)
    assert sales_line_args[6] is None


def test_committed_period_error_does_not_offer_an_impossible_override():
    class CommittedPeriodConn(FakeConn):
        async def fetchval(self, query, *args):
            if "status='committed'" in query:
                return 'committed-import'
            return await super().fetchval(query, *args)

    with pytest.raises(
        sales_commit.DuplicateSalesPeriodError,
        match=r'^Sales for 2026-08-25 have already been committed\.$',
    ):
        _run(sales_commit.commit_sales_import(
            CommittedPeriodConn(),
            company_id='company-1', user_id='user-1', location_id=None,
            business_date='2026-08-25', source='upload', filename='sales.csv',
            gmail_message_id=None, lines=[_recipe_line()],
        ))


@pytest.mark.parametrize('include_status', [True, False])
def test_all_ignored_sales_discard_the_import_without_checking_the_committed_period(
    monkeypatch, include_status,
):
    class DuplicatePeriodConn(FakeConn):
        async def fetchval(self, query, *args):
            if "status='committed'" in query:
                raise AssertionError('all-ignored reviews must not check the committed period')
            return await super().fetchval(query, *args)

    conn = DuplicatePeriodConn()
    saved = []
    movement_calls = []

    async def validate_mapping(*_args, **_kwargs):
        return None

    async def upsert_mapping(*_args, **kwargs):
        saved.append(kwargs)
        return {'id': 'ignored-mapping', 'components': []}

    async def record_movements(*_args, **_kwargs):
        movement_calls.append(True)

    monkeypatch.setattr(sales_commit.sales_mappings, 'validate_mapping', validate_mapping)
    monkeypatch.setattr(sales_commit.sales_mappings, 'upsert_mapping', upsert_mapping)
    monkeypatch.setattr(sales_commit.movements_service, 'record_movements', record_movements)

    line = {
        'sold_name': 'Vanilla latte', 'quantity': 1,
        'new_mapping': {'kind': 'ignore', 'components': []},
    }
    if include_status:
        line['status'] = 'ignored'

    result = _run(sales_commit.commit_sales_import(
        conn, company_id='company-1', user_id='user-1', location_id=None,
        business_date='2026-08-25', source='upload', filename='sales.csv',
        gmail_message_id=None,
        lines=[line],
    ))

    assert result['unmapped'] == 0
    assert saved[0]['kind'] == 'ignore'
    assert movement_calls == []
    status_update = next(args for query, args in conn.executed if 'SET status=$2' in query)
    assert status_update[1] == 'discarded'


def test_all_ignored_discarded_pos_batch_is_idempotent():
    class DiscardedIgnoredBatchConn(FakeConn):
        async def fetchrow(self, query, *args):
            if 'connection_id=$2' in query:
                return {
                    'id': 'import-1', 'status': 'discarded',
                    'location_id': None, 'business_date': '2026-08-25',
                }
            return await super().fetchrow(query, *args)

        async def fetchval(self, query, *args):
            if 'FROM inventory_sales_lines' in query:
                return True
            return await super().fetchval(query, *args)

    result = _run(sales_commit.commit_sales_import(
        DiscardedIgnoredBatchConn(),
        company_id='company-1', user_id=None, location_id=None,
        business_date='2026-08-25', source='square', filename='square:batch-1',
        gmail_message_id=None,
        lines=[{'sold_name': 'Gift card', 'quantity': 1, 'status': 'ignored'}],
        connection_id='connection-1', external_batch_id='batch-1',
    ))

    assert result['import_id'] == 'import-1'
    assert result['duplicate'] is True


def test_manually_discarded_nonignored_import_still_refuses_commit():
    class DiscardedMappedImportConn(FakeConn):
        async def fetchrow(self, query, *args):
            if 'FROM inventory_sales_imports WHERE id=$1' in query:
                return {
                    'id': 'import-1', 'status': 'discarded', 'location_id': None,
                    'business_date': '2026-08-25', 'source': 'upload',
                    'connection_id': None, 'external_batch_id': None,
                }
            return await super().fetchrow(query, *args)

        async def fetchval(self, query, *args):
            if 'FROM inventory_sales_lines' in query:
                return False
            return await super().fetchval(query, *args)

    with pytest.raises(ValueError, match='Sales import was already discarded'):
        _run(sales_commit.commit_sales_import(
            DiscardedMappedImportConn(),
            company_id='company-1', user_id='user-1', location_id=None,
            business_date='2026-08-25', source='upload', filename='sales.csv',
            gmail_message_id=None,
            lines=[_recipe_line()], import_id='import-1',
        ))


def test_period_constraint_race_returns_duplicate_error_and_removes_new_draft(monkeypatch):
    class PeriodConflict(Exception):
        constraint_name = 'uniq_inventory_sales_imports_period'

    class RaceConn(FakeConn):
        async def execute(self, query, *args):
            if 'SET status=$2' in query:
                raise PeriodConflict()
            await super().execute(query, *args)

    async def record_movements(*_args, **_kwargs):
        return []

    monkeypatch.setattr(sales_commit, 'UniqueViolationError', PeriodConflict)
    monkeypatch.setattr(sales_commit.movements_service, 'record_movements', record_movements)
    conn = RaceConn()

    with pytest.raises(
        sales_commit.DuplicateSalesPeriodError,
        match=r'^Sales for 2026-08-25 have already been committed\.$',
    ):
        _run(sales_commit.commit_sales_import(
            conn, company_id='company-1', user_id='user-1', location_id=None,
            business_date='2026-08-25', source='upload', filename='sales.csv',
            gmail_message_id=None,
            lines=[{
                'sold_name': 'Vanilla latte', 'quantity': 1, 'status': 'mapped',
                'components': [{'item_id': 'cup', 'quantity_per_sale': 1}],
            }],
        ))

    assert any('DELETE FROM inventory_sales_imports' in query for query, _args in conn.executed)
