# Cappe domain reselling — ops & go-live

Lets a Cappe tenant **search → buy** a domain (registered via Porkbun under our
account, resold at wholesale + a flat markup) or **connect** one they already own
(after DNS-TXT ownership verification). Code:

- `services/porkbun.py` — Porkbun v3 client (check / register / DNS).
- `services/stripe_connect.py` — `create_platform_checkout_session`, `refund`,
  `verify_platform_webhook` (domain charges hit OUR platform account, not Connect).
- `routes/domains.py` — search / purchase / connect / verify / list / webhook / `tls/authorize`.
- `cappe_domains` table — migration `zzzzcappe19` (**UNAPPLIED**).

## Money model
We are the **reseller / merchant of record**. The tenant pays us via Stripe; we
register under our funded Porkbun account and keep the margin. Domains register
under our account's default WHOIS-private contact (tenant can transfer out after
the ICANN 60-day lock). Charge happens **before** registration; a failed
registration auto-refunds (`finalize_domain_registration`).

## Go-live checklist

1. **Migration** — apply `zzzzcappe19` dev → prod (`migrate-dev.sh`, then
   `migrate-prod.sh` + `--legacy`). Backend 500s on `cappe_domains` until then.

2. **Porkbun account** — fund a balance, enable **API access** in account
   settings, generate API + secret keys. Set:
   ```
   PORKBUN_API_KEY=pk1_...
   PORKBUN_SECRET_KEY=sk1_...
   CAPPE_DOMAIN_MARKUP_CENTS=800        # flat +$8/yr over wholesale (default)
   CAPPE_DOMAIN_TARGET_IP=54.177.107.107  # app EIP the apex A-record points at
   ```
   `checkDomain` is rate-limited — the search fans out to a few TLDs, tolerant of
   per-TLD failures.

3. **Stripe — PLATFORM webhook** (separate from the storefront Connect webhook):
   add an endpoint → `https://<app>/api/cappe/domains/webhook`, event
   `checkout.session.completed`. Copy its signing secret to:
   ```
   CAPPE_PLATFORM_WEBHOOK_SECRET=whsec_...
   ```

4. **TLS — Caddy on-demand** (custom domains can't use the `*.gummfit.com`
   wildcard; each needs its own cert). Put Caddy on :443 for non-app hosts; it
   issues Let's Encrypt certs on first request, gated by our ask-endpoint so only
   domains we serve get certs:
   ```caddyfile
   {
     on_demand_tls {
       ask https://127.0.0.1:8002/api/cappe/tls/authorize
     }
   }
   :443 {
     tls { on_demand }
     reverse_proxy 127.0.0.1:<frontend-or-backend>
   }
   ```
   `GET /api/cappe/tls/authorize?domain=<host>` returns 200 only for an active
   custom domain (registered or verified-connect), 404 otherwise — this is the
   abuse gate against LE issuance for arbitrary hostnames.

5. **DNS** — registered domains: `point_at_app` sets apex A → `CAPPE_DOMAIN_TARGET_IP`
   and `www` CNAME → apex automatically. Connected domains: the tenant points
   their own A record at us (shown in the connect UI), then completes the TXT
   verification.

## Connect (BYO) verification
`POST /domains/connect` creates a **pending** claim + a token; the tenant adds a
`TXT` record at `_cappe-verify.<domain>` and calls `POST /domains/{id}/verify`,
which resolves the TXT and only then activates + writes `cappe_sites.custom_domain`.
Uniqueness is a partial index over `status='active'` rows, so an unverified claim
can't block the real owner.

## TODO — renewals (Phase 2, not built)
Domains are 1-year. Current code sets `expires_at` but does **not** auto-renew.
To add:
1. Save the card at purchase — create a Stripe **Customer** + `setup_future_usage`
   on the checkout so renewals can charge off-session.
2. Daily cron (gate via a scheduler row like the matcha workers): find
   `cappe_domains` where `status='active' AND auto_renew AND expires_at < now()+30d`,
   charge the customer (retail), and renew at Porkbun. On a failed charge, dun /
   let lapse → `expired`. (Confirm Porkbun's renew endpoint first — it wasn't in
   the client lib surface checked during the build; account-level auto-renew may
   be the interim path.)
