"""Celery task: sweep tracked certificates of insurance for upcoming/lapsed expiry.

Scheduler-gated (``scheduler_settings.task_key = 'coi_expiry'``) + per-company
paid gate (``enabled_features->>'coi_tracking'``). Refreshes each cert's status
and emails the company admin about certificates expiring within the window or
already expired. `coi_tracking` is a paid flag in no tier overlay, so the stored
enabled_features value is the merged value — safe to filter in SQL.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled


async def _dispatch_coi_expiry() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "coi_expiry"):
            print("[COI Expiry] Scheduler disabled, skipping.")
            return {"checked": 0}

        # Refresh stored status from expiry_date, then collect the ones to alert on.
        rows = await conn.fetch(
            """
            SELECT cert.id, cert.company_id, cert.holder_name, cert.carrier, cert.expiry_date
            FROM company_certificates cert
            JOIN companies c ON c.id = cert.company_id
            WHERE COALESCE((c.enabled_features->>'coi_tracking')::boolean, false)
              AND cert.expiry_date IS NOT NULL
              AND cert.expiry_date <= CURRENT_DATE + INTERVAL '30 days'
            ORDER BY cert.expiry_date ASC
            """,
        )
        # Keep stored status in sync (expiring/expired) so the dashboard is right
        # even between page loads.
        await conn.execute(
            """
            UPDATE company_certificates SET
                status = CASE
                    WHEN expiry_date < CURRENT_DATE THEN 'expired'
                    WHEN expiry_date <= CURRENT_DATE + INTERVAL '30 days' THEN 'expiring'
                    ELSE 'active' END,
                updated_at = NOW()
            WHERE expiry_date IS NOT NULL
            """,
        )
    finally:
        await conn.close()

    alerted = 0
    for row in rows:
        try:
            await _send_expiry_alert(str(row["company_id"]), row)
            alerted += 1
        except Exception as e:
            print(f"[COI Expiry] Alert failed for cert {row['id']}: {e}")
    return {"checked": len(rows), "alerted": alerted}


async def _send_expiry_alert(company_id: str, cert) -> None:
    from app.core.services.email import get_email_service

    conn = await get_db_connection()
    try:
        admin = await conn.fetchrow(
            """
            SELECT u.email
            FROM users u JOIN clients cl ON cl.user_id = u.id
            WHERE u.role = 'client' AND cl.company_id = $1
            ORDER BY u.created_at ASC LIMIT 1
            """,
            company_id,
        )
    finally:
        await conn.close()
    if not admin or not admin["email"]:
        return
    holder = cert["holder_name"] or cert["carrier"] or "a vendor"
    expiry = cert["expiry_date"].isoformat() if cert["expiry_date"] else "soon"
    subject = f"Certificate of insurance expiring: {holder}"
    html_content = (f"<p>A tracked certificate of insurance (<b>{holder}</b>, carrier "
                    f"{cert['carrier'] or 'unknown'}) expires <b>{expiry}</b>.</p>"
                    f"<p>Request an updated certificate to avoid a coverage gap.</p>")
    email = get_email_service()
    await email.send_email(to_email=admin["email"], to_name=None, subject=subject,
                           html_content=html_content)


@celery_app.task(name="coi_expiry.run_coi_expiry_sweep", bind=True, max_retries=1)
def run_coi_expiry_sweep(self):
    """Sweep certificates for upcoming/lapsed expiry and alert company admins."""
    try:
        result = asyncio.run(_dispatch_coi_expiry())
        print(f"[COI Expiry] Completed: {result}")
        return result
    except Exception as e:
        print(f"[COI Expiry] Task failed: {e}")
        raise self.retry(exc=e, countdown=120)
