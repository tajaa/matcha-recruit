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

async def _claim(conn, company_id, location_id, kind, *, recipient_email=None, channel_id=None):
    return await conn.fetchval("""INSERT INTO inventory_waste_alert_deliveries (company_id,location_id,alert_date,alert_kind,recipient_email,channel_id)
        VALUES ($1,$2,CURRENT_DATE,$3,$4,$5) ON CONFLICT DO NOTHING RETURNING id""", company_id, location_id, kind, recipient_email, channel_id)

async def _notify(conn, *, company_id, location_id, kind, content):
    """Channel first; email the first active admin when a store has no channel."""
    channel_id = await _channel(conn, company_id, location_id)
    email = None
    if not channel_id:
        email = await conn.fetchval("""SELECT u.email FROM clients c JOIN users u ON u.id=c.user_id
            WHERE c.company_id=$1 AND u.is_active=TRUE ORDER BY u.created_at, u.id LIMIT 1""", company_id)
    delivery_id = await _claim(conn, company_id, location_id, kind, recipient_email=email, channel_id=channel_id)
    if not delivery_id:
        return False
    delivered = False
    try:
        if channel_id:
            await post_as_huume(company_id, channel_id, content)
            delivered = True
        elif email:
            from app.core.services.email.client import get_email_service
            delivered = await get_email_service().send_email(to_email=email, to_name=None, subject='Inventory waste alert', html_content=content)
        return delivered
    except Exception:
        logger.exception("inventory waste alert delivery failed", extra={"company_id": str(company_id), "kind": kind})
        return False
    finally:
        # A transient failure must not consume today's dedupe slot.
        if not delivered:
            await conn.execute("DELETE FROM inventory_waste_alert_deliveries WHERE id=$1", delivery_id)

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
                if await _notify(conn, company_id=company['id'], location_id=location_id, kind='expiring', content=f"📦 {len(group)} lot(s) expire within 3 days: " + ', '.join(str(x['name']) for x in group[:5])):
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
            pct = f" ({result['waste_pct_of_revenue']:.1%} of revenue)" if result['waste_pct_of_revenue'] is not None else ''
            if result['total_units'] and await _notify(conn, company_id=company['id'], location_id=None, kind='waste_spike', content=f"📦 Weekly waste: {result['total_units']} units{pct}."):
                sent += 1
        return {'sent': sent}
    finally: await conn.close()

async def _run_par():
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, 'inventory_par_sweep', default=False): return {'disabled': True}
        applied = 0
        for company in await _companies(conn, 200):
            settings = await forecast_store.get_settings(conn, company['id'], None)
            if not settings['par_auto_apply']:
                continue
            run = await forecast_store.create_run(conn, company_id=company['id'], user_id=None, location_id=None, forecast_start=date.today(), overrides=[])
            result = await par_store.apply_par_recommendations(conn, company_id=company['id'], run_id=run['id'], user_id=None, mode='auto')
            applied += result['applied']
            if result['applied']:
                await _notify(conn, company_id=company['id'], location_id=None, kind='par_applied', content=f"📦 Predictive par updated {result['applied']} item(s).")
        return {'applied': applied}
    finally: await conn.close()

@celery_app.task(bind=True, max_retries=3)
def run_inventory_expiry_sweep(self): return asyncio.run(_run_expiry())
@celery_app.task(bind=True, max_retries=3)
def run_inventory_waste_digest(self): return asyncio.run(_run_digest())
@celery_app.task(bind=True, max_retries=3)
def run_inventory_par_sweep(self): return asyncio.run(_run_par())
