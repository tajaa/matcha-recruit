"""Fail-closed expiry, waste digest, and guarded par worker sweeps."""
import asyncio
import logging
from datetime import date, timedelta

from app.core.feature_flags import merge_company_features
from app.matcha.services.inventory import forecast_store
from app.matcha.services.inventory.waste import lots, par_store, rollup
from app.matcha.services.huume_code.chat import post_as_huume
from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled, scheduler_settings_row

logger = logging.getLogger(__name__)

async def _companies(conn, limit):
    rows = await conn.fetch("SELECT id, enabled_features, signup_source FROM companies WHERE deleted_at IS NULL ORDER BY id LIMIT $1", limit)
    return [row for row in rows if (lambda f: f.get('matcha_ops') and f.get('inventory') and f.get('inventory_waste'))(merge_company_features(row['enabled_features'], row['signup_source']))]

async def _channel(conn, company_id, location_id):
    return await conn.fetchval("SELECT id FROM channels WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM $2 ORDER BY created_at LIMIT 1", company_id, location_id)

async def _claim(conn, company_id, location_id, kind):
    return await conn.fetchval("""INSERT INTO inventory_waste_alert_deliveries (company_id,location_id,alert_date,alert_kind)
        VALUES ($1,$2,CURRENT_DATE,$3) ON CONFLICT DO NOTHING RETURNING id""", company_id, location_id, kind)

async def _run_expiry():
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, 'inventory_expiry_sweep', default=False): return {'disabled': True}
        setting = await scheduler_settings_row(conn, 'inventory_expiry_sweep')
        sent = 0
        for company in await _companies(conn, int((setting or {}).get('max_per_cycle', 200))):
            rows = await lots.expiring_lots(conn, company_id=company['id'], location_id=None, within_days=3)
            by_location = {}
            for row in rows: by_location.setdefault(row['location_id'], []).append(row)
            for location_id, group in by_location.items():
                channel_id = await _channel(conn, company['id'], location_id)
                if channel_id and await _claim(conn, company['id'], location_id, 'expiring'):
                    await post_as_huume(company['id'], channel_id, f"📦 {len(group)} lot(s) expire within 3 days: " + ', '.join(str(x['name']) for x in group[:5]))
                    sent += 1
        return {'sent': sent}
    finally: await conn.close()

async def _run_digest():
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, 'inventory_waste_digest', default=False): return {'disabled': True}
        sent = 0
        for company in await _companies(conn, 200):
            result = await rollup.waste_rollup(conn, company_id=company['id'], location_id=None, start=date.today()-timedelta(days=7), end=date.today(), group_by='item')
            channel_id = await _channel(conn, company['id'], None)
            if channel_id and result['total_units'] and await _claim(conn, company['id'], None, 'waste_spike'):
                pct = f" ({result['waste_pct_of_revenue']:.1%} of revenue)" if result['waste_pct_of_revenue'] is not None else ''
                await post_as_huume(company['id'], channel_id, f"📦 Weekly waste: {result['total_units']} units{pct}.")
                sent += 1
        return {'sent': sent}
    finally: await conn.close()

async def _run_par():
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, 'inventory_par_sweep', default=False): return {'disabled': True}
        applied = 0
        for company in await _companies(conn, 200):
            run = await forecast_store.create_run(conn, company_id=company['id'], user_id=None, location_id=None, forecast_start=date.today(), overrides=[])
            result = await par_store.apply_par_recommendations(conn, company_id=company['id'], run_id=run['id'], user_id=None, mode='auto')
            applied += result['applied']
        return {'applied': applied}
    finally: await conn.close()

@celery_app.task(bind=True, max_retries=3)
def run_inventory_expiry_sweep(self): return asyncio.run(_run_expiry())
@celery_app.task(bind=True, max_retries=3)
def run_inventory_waste_digest(self): return asyncio.run(_run_digest())
@celery_app.task(bind=True, max_retries=3)
def run_inventory_par_sweep(self): return asyncio.run(_run_par())
