"""Celery task: renew Cappe domains by charging the tenant's saved card.

Domains we register via Porkbun are 1-year. Porkbun's own account-level
auto-renew keeps the registration alive (billing US); this task's job is to
RECOUP from the tenant before expiry, and to lapse + stop Porkbun auto-renew for
domains nobody is paying us for.

Gated on `scheduler_settings.task_key = 'cappe_domain_renewals'`.

What changed in the 2026-10 payments review, and why:

* **The charge names its card.** It used to pass only the Stripe customer id.
  A PaymentIntent does not fall back to "the customer's card", so every renewal
  failed. The payment method id saved at purchase is used; rows from before it
  was saved fall back to the customer's most recent card.
* **A refused card is not an outage.** Any Stripe error past expiry used to
  expire the domain and switch the registrar's auto-renew off. Now only a
  refusal of the CARD (or having no card) counts against the tenant; an API
  error, a bad key or a timeout is ours, changes nothing, and is retried.
* **The tenant is told, once, and has a way to fix it.** A failed renewal sends
  one email per cycle with a link to pay by hand (`POST /domains/{id}/renew`).
  The domain lapses only after expiry plus `_LAPSE_GRACE_DAYS`, with a second
  email when it does.
* **Nothing is skipped for ever.** A domain with no saved card, or with
  auto-renew off, used to be passed over on every run and stay `active` past
  its expiry indefinitely. Both now get the reminder and lapse on schedule.

Idempotent: a successful charge bumps expires_at +1yr (out of the window); a
refused one is retried at most every `_RETRY_EVERY_DAYS`; the Stripe
idempotency key (domain + expiry + day) makes an hourly worker restart replay
the day's attempt rather than make another.
"""

import asyncio
import logging

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled

logger = logging.getLogger(__name__)

# Start attempting renewal this many days before expiry (the dunning window).
_RENEW_WINDOW_DAYS = 14
# A refused card is retried on this cadence, not hourly: card networks penalise
# merchants who hammer a declining card.
_RETRY_EVERY_DAYS = 3
# How long past expiry an auto-renewing domain keeps serving while the tenant
# sorts out payment.
_LAPSE_GRACE_DAYS = 7

REASON_DECLINED = "the card on file was declined."
REASON_NO_CARD = "there is no card on file for it."
REASON_AUTO_RENEW_OFF = "auto-renew is switched off."


def plan_for(row) -> str:
    """What to do with one domain in the renewal window. Pure.

    'charge'  try the saved card now.
    'wait'    a refused card was tried recently; not yet time to retry.
    'remind'  auto-renew is off: nothing to charge, tell the tenant it expires.
    'lapse'   out of time — expire it.
    'skip'    no price on file; nothing can be charged (logged, left alone).
    """
    if not row["auto_renew"]:
        return "lapse" if row["past_due"] else "remind"
    if not row["retail_cents"]:
        return "skip"
    if row["recently_attempted"]:
        # Already refused within the retry window. Out of grace → stop here.
        return "lapse" if row["past_grace"] else "wait"
    return "charge"


async def _exec(sql: str, *args) -> None:
    conn = await get_db_connection()
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _notify_once(row, reason: str) -> None:
    """Email the tenant about a renewal that is not going to happen on its own
    — once per cycle (`renewal_notified_at` is cleared when the domain renews)."""
    if row["notified"] or not row["account_email"]:
        return
    from app.cappe.services.email import dashboard_url, send_cappe_domain_renewal_problem_email

    try:
        await send_cappe_domain_renewal_problem_email(
            row["account_email"], row["account_name"], row["domain"], row["expires_on"],
            reason, dashboard_url(f"/sites/{row['site_id']}"),
        )
    except Exception:  # noqa: BLE001 — an email failure must not stop the sweep
        logger.exception("[Cappe Renewals] %s: renewal notice failed to send", row["domain"])
        return
    await _exec(
        "UPDATE cappe_domains SET renewal_notified_at = NOW(), updated_at = NOW() WHERE id = $1",
        row["id"],
    )


async def _record_failure(row, reason: str) -> None:
    await _exec(
        "UPDATE cappe_domains SET renewal_attempted_at = NOW(), "
        "renewal_failed_at = COALESCE(renewal_failed_at, NOW()), renewal_error = $2, "
        "updated_at = NOW() WHERE id = $1",
        row["id"], reason,
    )


async def _lapse(row) -> None:
    """Expire a domain nobody is paying for, stop the registrar billing us for
    it, and tell the tenant. `expired` is what makes the edge sweeper tear the
    CloudFront tenant down."""
    from app.cappe.services.email import dashboard_url, send_cappe_domain_lapsed_email
    from app.core.services.porkbun import PorkbunError, get_porkbun

    await _exec(
        "UPDATE cappe_domains SET status = 'expired', updated_at = NOW() "
        "WHERE id = $1 AND status = 'active'",
        row["id"],
    )
    try:
        await get_porkbun().set_auto_renew(row["domain"], False)
    except PorkbunError as exc:
        logger.warning(
            "[Cappe Renewals] %s: lapsed, but Porkbun auto-renew could not be switched off: %s",
            row["domain"], exc,
        )
    if row["account_email"]:
        try:
            await send_cappe_domain_lapsed_email(
                row["account_email"], row["account_name"], row["domain"],
                dashboard_url(f"/sites/{row['site_id']}"),
            )
        except Exception:  # noqa: BLE001
            logger.exception("[Cappe Renewals] %s: lapse notice failed to send", row["domain"])
    logger.warning("[Cappe Renewals] %s: lapsed (unrenewed past expiry).", row["domain"])


async def _charge(cs, row) -> str:
    """Try to collect one renewal. Returns 'renewed', 'refused' (the card or
    its absence — the tenant's to fix) or 'error' (ours; nothing recorded)."""
    from app.cappe.services.stripe_connect import CappeStripeCardError, CappeStripeError

    payment_method = row["stripe_payment_method_id"]
    try:
        if not payment_method and row["stripe_customer_id"]:
            payment_method = await cs.saved_card_for_customer(row["stripe_customer_id"])
        if not row["stripe_customer_id"] or not payment_method:
            await _record_failure(row, REASON_NO_CARD)
            await _notify_once(row, REASON_NO_CARD)
            return "refused"
        await cs.charge_off_session(
            customer_id=row["stripe_customer_id"],
            payment_method_id=payment_method,
            amount_cents=int(row["retail_cents"]),
            currency="usd",
            metadata={"type": "cappe_domain_renewal", "domain_id": str(row["id"])},
            idempotency_key=f"cappe-renew-{row['id']}-{row['expiry_key']}-{row['today_key']}",
        )
    except CappeStripeCardError as exc:
        logger.warning("[Cappe Renewals] %s: card refused: %s", row["domain"], exc)
        await _record_failure(row, REASON_DECLINED)
        await _notify_once(row, REASON_DECLINED)
        return "refused"
    except CappeStripeError as exc:
        # Not the tenant's fault and not evidence they won't pay.
        logger.error("[Cappe Renewals] %s: could not attempt the charge: %s", row["domain"], exc)
        return "error"

    await _exec(
        "UPDATE cappe_domains SET expires_at = GREATEST(expires_at, NOW()) + INTERVAL '1 year', "
        "stripe_payment_method_id = $2, renewal_attempted_at = NOW(), renewal_failed_at = NULL, "
        "renewal_notified_at = NULL, renewal_error = NULL, updated_at = NOW() WHERE id = $1",
        row["id"], payment_method,
    )
    return "renewed"


async def _dispatch_cappe_domain_renewals() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "cappe_domain_renewals", default=False):
            print("[Cappe Renewals] Scheduler disabled, skipping.")
            return {"renewed": 0, "skipped": True}

        # A domain with a transfer-out request is deliberately NOT renewed (the
        # tenant said they are leaving, and charging them another year would be
        # wrong), but it also keeps serving until the registration really ends.
        # Once it is past expiry it is gone either way — transferred or lapsed —
        # so it becomes `expired`, which is what tells the edge sweeper to tear
        # the CloudFront tenant down.
        lapsed_transfers = await conn.fetch(
            "UPDATE cappe_domains SET status = 'expired', updated_at = NOW() "
            "WHERE status = 'transfer_requested' AND expires_at IS NOT NULL AND expires_at < NOW() "
            "RETURNING domain, kind"
        )
        # Nobody is paying us for a transfer-requested domain, so Porkbun must
        # not keep renewing it on our account. Switched off as soon as it enters
        # the renewal window — waiting for expiry is too late, Porkbun renews
        # BEFORE the expiry date — and again on lapse. Idempotent at Porkbun;
        # /transfer-request/cancel turns it back on.
        leaving = await conn.fetch(
            """SELECT domain FROM cappe_domains
                WHERE kind = 'register' AND status = 'transfer_requested'
                  AND expires_at IS NOT NULL
                  AND expires_at < NOW() + ($1 || ' days')::interval""",
            str(_RENEW_WINDOW_DAYS),
        )

        # Every active registered domain in the window — including the ones
        # with auto-renew off or no saved card, which the old `AND auto_renew`
        # filter (and a `continue`) left active for ever.
        rows = await conn.fetch(
            """SELECT d.id, d.domain, d.site_id, d.retail_cents, d.auto_renew,
                      d.stripe_customer_id, d.stripe_payment_method_id,
                      (d.expires_at < NOW()) AS past_due,
                      (d.expires_at < NOW() - ($2 || ' days')::interval) AS past_grace,
                      (d.renewal_attempted_at IS NOT NULL
                       AND d.renewal_attempted_at > NOW() - ($3 || ' days')::interval) AS recently_attempted,
                      (d.renewal_notified_at IS NOT NULL) AS notified,
                      to_char(d.expires_at, 'YYYY-MM-DD') AS expiry_key,
                      to_char(NOW(), 'YYYYMMDD') AS today_key,
                      to_char(d.expires_at, 'FMMonth FMDD, YYYY') AS expires_on,
                      a.email AS account_email, a.name AS account_name
                 FROM cappe_domains d
                 JOIN cappe_accounts a ON a.id = d.account_id
                WHERE d.kind = 'register' AND d.status = 'active'
                  AND d.expires_at IS NOT NULL
                  AND d.expires_at < NOW() + ($1 || ' days')::interval
                ORDER BY d.expires_at ASC""",
            str(_RENEW_WINDOW_DAYS), str(_LAPSE_GRACE_DAYS), str(_RETRY_EVERY_DAYS),
        )
    finally:
        await conn.close()

    from app.cappe.services.stripe_connect import get_cappe_stripe
    from app.core.services.porkbun import PorkbunError, get_porkbun

    stop_billing = {r["domain"] for r in leaving}
    stop_billing |= {r["domain"] for r in lapsed_transfers if r["kind"] == "register"}
    for domain in sorted(stop_billing):
        try:
            await get_porkbun().set_auto_renew(domain, False)
        except PorkbunError as exc:
            logger.warning(
                "[Cappe Renewals] %s: could not switch Porkbun auto-renew off: %s", domain, exc
            )

    renewed = failed = errors = reminded = 0
    lapsed = len(lapsed_transfers)
    if not rows:
        return {"renewed": 0, "failed": 0, "lapsed": lapsed}

    cs = get_cappe_stripe()
    for r in rows:
        try:
            plan = plan_for(r)
            if plan == "skip":
                logger.error(
                    "[Cappe Renewals] %s: no renewal price on file — cannot charge; fix the row.",
                    r["domain"],
                )
            elif plan == "remind":
                if not r["notified"]:
                    # Auto-renew is the tenant's choice, so the registrar must
                    # not renew on our account either (a manual renewal last
                    # year switches it back on — see the platform webhook).
                    try:
                        await get_porkbun().set_auto_renew(r["domain"], False)
                    except PorkbunError as exc:
                        logger.warning(
                            "[Cappe Renewals] %s: could not switch Porkbun auto-renew off: %s",
                            r["domain"], exc,
                        )
                    await _notify_once(r, REASON_AUTO_RENEW_OFF)
                    reminded += 1
            elif plan == "lapse":
                await _lapse(r)
                lapsed += 1
            elif plan == "charge":
                outcome = await _charge(cs, r)
                if outcome == "renewed":
                    renewed += 1
                    print(f"[Cappe Renewals] {r['domain']}: renewed +1yr.")
                elif outcome == "refused":
                    failed += 1
                    if r["past_grace"]:
                        await _lapse(r)
                        lapsed += 1
                else:
                    errors += 1
        except Exception:  # noqa: BLE001 — one domain must not stop the rest
            logger.exception("[Cappe Renewals] %s: renewal handling failed", r["domain"])
            errors += 1

    print(
        f"[Cappe Renewals] renewed={renewed} failed={failed} lapsed={lapsed} "
        f"reminded={reminded} errors={errors}"
    )
    return {
        "renewed": renewed, "failed": failed, "lapsed": lapsed,
        "reminded": reminded, "errors": errors,
    }


@celery_app.task(name="cappe.domain_renewals", bind=True, max_retries=1)
def run_cappe_domain_renewals(self):
    """Charge tenants for domains nearing expiry; lapse non-payers."""
    try:
        return asyncio.run(_dispatch_cappe_domain_renewals())
    except Exception as e:
        logger.exception("[Cappe Renewals] Task failed")
        raise self.retry(exc=e, countdown=300)
