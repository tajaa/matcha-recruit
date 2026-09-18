# Cappe domain reselling — ops & go-live

Lets a Cappe tenant **search → buy** a domain (registered via Porkbun under our
account, resold at wholesale + a flat markup) or **connect** one they already own
(after DNS-TXT ownership verification). Either way the domain is then served
through a **CloudFront distribution tenant** with a CloudFront-managed
certificate — see "How a custom domain goes live". Code:

- `services/porkbun.py` — Porkbun v3 client (check / register / DNS).
- `services/stripe_connect.py` — `create_platform_checkout_session`, `refund`,
  `verify_platform_webhook` (domain charges hit OUR platform account, not Connect).
- `services/cloudfront_tenants.py` — distribution-tenant create / status / delete.
- `services/domain_register.py` — `finalize_domain_registration`,
  `provision_domain_edge` (claimed), `retry_domain_edge`.
- `routes/domains.py` — config / search / purchase / connect / verify / list /
  DNS / auto-renew / transfer-request (+cancel) / edge retry / webhook.
- `workers/tasks/cappe_edge_sync.py` — the only writer of `cappe_sites.custom_domain`.
- `cappe_domains` table — `zzzzcappe19`/`20`; edge columns + `transfer_requested`
  in `zzzzcappe31`.

The whole create surface is dark behind `CAPPE_CUSTOM_DOMAINS_ENABLED` until the
AWS side exists. Runbook: `docs/ops/CAPPE_CUSTOM_DOMAINS.md`.

## Money model
We are the **reseller / merchant of record**. The tenant pays us via Stripe; we
register under our funded Porkbun account and keep the margin. Domains register
under our account's default WHOIS-private contact (tenant can transfer out after
the ICANN 60-day lock). Charge happens **before** registration; a failed
registration auto-refunds (`finalize_domain_registration`).

## Go-live checklist

1. **Migrations** — `zzzzcappe31` applied dev → prod (`migrate-dev.sh`, then
   `migrate-prod.sh`).

2. **Porkbun account** — fund a balance, enable **API access**, generate keys:
   ```
   PORKBUN_API_KEY=pk1_...
   PORKBUN_SECRET_KEY=sk1_...
   CAPPE_DOMAIN_MARKUP_CENTS=800        # flat +$8/yr over wholesale (default)
   ```

3. **Stripe — PLATFORM webhook** (separate from the storefront Connect webhook):
   endpoint `https://<app>/api/cappe/domains/webhook`, events
   `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `checkout.session.async_payment_failed`. Signing secret →
   `CAPPE_PLATFORM_WEBHOOK_SECRET`. A domain is only registered once
   `payment_status` says the money cleared.

4. **Edge** — build the tenant distribution + connection group and set the
   `CAPPE_CF_*` env vars per `docs/ops/CAPPE_CUSTOM_DOMAINS.md`, ship
   `deploy/nginx/cappe-custom-domains.conf`, then flip
   `CAPPE_CUSTOM_DOMAINS_ENABLED=true` and enable the `cappe_edge_sync` scheduler row.

## How a custom domain goes live

```
register:  paid → registering → Porkbun register → active ─┐
connect:   pending → TXT verified ───────────────→ active ─┤
                                                            ▼
                     provision_domain_edge (claimed)  edge_status: none → provisioning
                     create_distribution_tenant       → pending_dns
                     DNS points at CAPPE_CF_ROUTING_ENDPOINT, certificate issues
                     cappe_edge_sync sees `live`      → live  + cappe_sites.custom_domain SET
```

- **`custom_domain` is written only by the sweeper, only at `live`.** Setting it at
  activation is what used to publish a host with no certificate.
- **Hostnames on the certificate.** CloudFront validates *every* name on a managed
  certificate, so one unpointed name blocks it forever. A registered domain gets
  apex + `www` (we set both records: `ALIAS` apex and `CNAME www` → the routing
  endpoint). A connected domain gets **exactly the host the tenant connected**
  (which may be a subdomain such as `shop.example.com`).
- **No dead ends.** `POST /domains/{id}/edge/retry` re-provisions a domain with no
  tenant (`none`/`failed`) and *replaces* a tenant whose certificate died
  (`failed` with a tenant); it never touches a healthy or still-validating one.
  The sweeper also adopts any `active` + `none` row (its background task died, or
  it predates the edge).
- **Teardown** happens on `expired` only, and on site delete (tenant ids are
  collected before the cascade removes the rows).

## AI booking edge policy

Manual booking remains available on canonical and verified custom domains, but
AI suggestions and their 30-minute host-only session cookie work only on the
canonical tenant host (`https://<subdomain>.<CAPPE_BASE_DOMAIN>`). Access links
are generated from the stored subdomain, never from request forwarding headers.

Before exposing the flow publicly, put `gummfit.com` and
`*.gummfit.com` behind the CloudFront/WAF setup documented in
`docs/ops/CAPPE_EDGE.md`. Custom domains ride the tenant distribution described above, behind the same
WAF and origin gate.

## Connect (BYO) verification
`POST /domains/connect` creates a **pending** claim + a token; the tenant adds a
`TXT` record at `_cappe-verify.<domain>` and calls `POST /domains/{id}/verify`,
which resolves the TXT, activates the row and starts edge provisioning. The UI
then shows the record to add (`ALIAS`/`ANAME` on a root domain, `CNAME` on a
subdomain → the routing endpoint). Uniqueness is a partial index over
`status='active'` rows, so an unverified claim can't block the real owner; a
concurrent activation is a 409.

## DNS management (registered domains)
`/domains/{id}/dns` (GET/POST/PUT/DELETE) proxies Porkbun's DNS API so tenants
edit A/CNAME/MX/TXT etc. in-app (email, Google verification…). Register-kind only
— connected domains' DNS lives at the tenant's own registrar (returns 400).

## Renewals (built — enable the scheduler)
The purchase checkout saves the card (Stripe Customer, off-session) →
`cappe_domains.stripe_customer_id`. Celery task `cappe.domain_renewals`
(`workers/tasks/cappe_domain_renewals.py`) charges the tenant retail within 14
days of expiry, bumps `expires_at +1yr`, and lapses non-payers (→ `expired` +
Porkbun auto-renew off). Idempotent: the +1yr bump exits the window; a Stripe
idempotency key (`cappe-renew-<id>-<expiry>`) dedupes retries within 24h.

**To turn on:** enable the `cappe_domain_renewals` row in Admin → Settings
(seeded off by `zzzzcappe31`, like every scheduled task).
Note: Porkbun's own account-level auto-renew keeps the registration alive (bills
us); this task recoups from the tenant and flips Porkbun auto-renew off when they
stop paying. `/domains/{id}/auto-renew` (PATCH) toggles it per domain.

## Transfer-out (built — manual auth-code step)
`/domains/{id}/transfer-request` enforces the 60-day ICANN lock, sets
`status='transfer_requested'` and logs it for an operator. **Porkbun exposes no
auth-code/EPP API**, so fulfillment is manual: retrieve the auth code + unlock in
the Porkbun dashboard and email it to the tenant.

While requested: DNS edits are frozen and the domain is **not renewed** (the
tenant said they are leaving), but the **site keeps serving** — a transfer takes
days and may never complete. `/transfer-request/cancel` puts the row back to
`active`. A request still open at `expires_at` lapses to `expired` in the
renewals task, which is what finally tears the edge tenant down.
