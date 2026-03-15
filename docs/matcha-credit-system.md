Plan: Matcha Work Credit Billing System (Stripe)

Context

Matcha Work AI chat/document generation has no billing gates. Token usage is already tracked in mw_token_usage_events
but there's no credit balance, payment flow, or gating. Business admins need to purchase credits via Stripe; platform
admins can grant credits manually. When credits hit 0, AI operations are blocked.

Credit Model

1 credit = 1 AI call (regardless of token count). Simple and predictable for customers. Each send_message or stream
request deducts 1 credit after a successful Gemini response.

---

1.  Database Schema (new tables)

mw_credit_balances

One row per company. Tracks current balance.
id UUID PK, company_id UUID FK (unique), credits_remaining INTEGER,
total_credits_purchased INTEGER, total_credits_granted INTEGER,
updated_at TIMESTAMPTZ

mw_credit_transactions

Audit log for every credit change (immutable append-only).
id UUID PK, company_id UUID FK, transaction_type VARCHAR(20)
CHECK IN ('purchase', 'grant', 'deduction', 'refund', 'adjustment'),
credits_delta INTEGER, credits_after INTEGER,
description TEXT, reference_id UUID (stripe session or thread id),
created_by UUID FK users (nullable, for admin grants), created_at TIMESTAMPTZ

mw_stripe_sessions

Tracks Stripe Checkout Sessions awaiting fulfillment.
id UUID PK, company_id UUID FK, stripe_session_id VARCHAR UNIQUE,
credit_pack_id VARCHAR, credits_to_add INTEGER, amount_cents INTEGER,
status VARCHAR(20) CHECK IN ('pending', 'completed', 'expired'),
created_at TIMESTAMPTZ, fulfilled_at TIMESTAMPTZ

Migration file: server/alembic/versions/{hash}\_add_mw_billing_tables.py

- Add all 3 tables with idempotent DO $$ BEGIN ... END $$ pattern
- Backfill: Insert a balance row for every company with credits_remaining = 0

---

2.  New Files

server/app/matcha/services/billing_service.py

Core billing logic. Functions:

- get_credit_balance(company_id) -> dict — fetch current balance
- check_credits(company_id) -> bool — raises HTTP 402 if ≤ 0
- deduct_credit(conn, company_id, thread_id, user_id) — deducts 1 credit, inserts transaction (called within existing
  get_connection() context)
- grant_credits(company_id, credits, description, granted_by) — admin grant
- get_transaction_history(company_id, limit, offset) — paginated transaction log

server/app/core/services/stripe_service.py

Stripe SDK wrapper:

- create_checkout_session(company_id, pack_id, success_url, cancel_url) -> Session
- verify_webhook(payload, signature) -> Event
- get_session(session_id) -> Session

Credit packs defined as a dict constant (no DB table needed):
CREDIT_PACKS = {
"starter": {"credits": 100, "amount_cents": 2900, "label": "100 Credits"},
"pro": {"credits": 500, "amount_cents": 9900, "label": "500 Credits"},
"business": {"credits": 2000, "amount_cents": 29900, "label": "2,000 Credits"},
}

server/app/matcha/routes/billing.py

Business-facing billing endpoints. All protected by require_admin_or_client.

- GET /matcha-work/billing/balance — current credits, recent transactions
- GET /matcha-work/billing/packs — list available credit packs with prices
- POST /matcha-work/billing/checkout — create Stripe Checkout Session, return URL
- GET /matcha-work/billing/transactions — paginated transaction history

server/app/core/routes/stripe_webhook.py

Unauthenticated endpoint for Stripe:

- POST /webhooks/stripe — verifies signature, handles checkout.session.completed
  → Marks stripe session fulfilled, calls grant_credits() (or dedicated purchase function)

---

3.  Modified Files

server/app/matcha/routes/matcha_work.py

Two endpoints need credit check + deduction:

- POST /matcha-work/threads/{thread_id}/messages (send_message, line ~936)
- POST /matcha-work/threads/{thread_id}/messages/stream (stream, line ~1044)

Before calling ai_provider.generate(), call await billing_service.check_credits(company_id).
After successful response and log_token_usage_event(), call await billing_service.deduct_credit(...).

Also add require_feature("matcha_work") enforcement to all Matcha Work routes (currently only enforced on frontend).

server/app/matcha/routes/**init**.py

Register billing.py router under matcha_router with prefix /matcha-work/billing.

server/app/main.py

Register stripe_webhook.py router at /webhooks/stripe (no auth middleware).

server/app/config.py

Add to Settings dataclass:
stripe_secret_key: Optional[str] = None
stripe_webhook_secret: Optional[str] = None
stripe_success_url: str = "http://localhost:5174/matcha-work/billing?success=1"
stripe_cancel_url: str = "http://localhost:5174/matcha-work/billing?canceled=1"

server/app/core/routes/admin.py

Add admin endpoint:

- POST /admin/companies/{company_id}/credits — grant/adjust credits manually
  Body: { "credits": int, "description": str }. Protected by require_admin.

server/app/database.py

Add CREATE TABLE statements for all 3 new tables in init_db() (for fresh dev setup).

---

4.  Frontend Changes

New page: client/src/pages/MatchaWorkBilling.tsx

Route: /matcha-work/billing
Sections:

- Credit balance card — large number, "Buy More Credits" CTA
- Credit packs — 3 cards (Starter/Pro/Business) with price + credit count, buy button
- Transaction history — table with type, credits, date, description

Modified: client/src/api/client.ts

Add billing API calls:

- getBillingBalance() → GET /matcha-work/billing/balance
- getCreditPacks() → GET /matcha-work/billing/packs
- createCheckout(packId) → POST /matcha-work/billing/checkout → redirect to Stripe URL
- getTransactions(page) → GET /matcha-work/billing/transactions

Modified: client/src/App.tsx

Add route /matcha-work/billing → <MatchaWorkBilling> (protected, roles: admin+client).

Modified: client/src/components/Layout.tsx or nav

Add "Billing" link in Matcha Work nav section.

Modified: client/src/pages/MatchaWorkThread.tsx

Show low-credit warning banner when balance < 10. Handle 402 error gracefully with "Out of credits" message + link to
billing page.

---

5.  Stripe Setup

- Install stripe Python package: pip install stripe
- Add stripe to requirements
- Stripe products/prices created in Stripe Dashboard (no code-managed products)
- Use price_id from Stripe Dashboard in CREDIT_PACKS config, OR use ad-hoc price_data in Checkout Session (simpler,
  avoids Dashboard dependency)

---

6.  Error Response for Out-of-Credits

HTTP 402 Payment Required
{ "detail": "Insufficient credits. Purchase more credits to continue using Matcha Work.", "code":
"insufficient_credits", "credits_remaining": 0 }

---

7.  Key File Paths Summary

┌─────────────────────────────────────────────────────────┬───────────────────────────────────────────────────────┐
│ File │ Action │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/alembic/versions/{hash}\_add_mw_billing_tables.py │ CREATE │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/matcha/services/billing_service.py │ CREATE │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/core/services/stripe_service.py │ CREATE │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/matcha/routes/billing.py │ CREATE │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/core/routes/stripe_webhook.py │ CREATE │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/matcha/routes/matcha_work.py │ MODIFY (add credit check/deduct at lines ~936, ~1044) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/matcha/routes/**init**.py │ MODIFY (register billing router) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/main.py │ MODIFY (register webhook router) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/config.py │ MODIFY (add Stripe env vars) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/core/routes/admin.py │ MODIFY (add grant credits endpoint) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ server/app/database.py │ MODIFY (add tables to init_db) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ client/src/pages/MatchaWorkBilling.tsx │ CREATE │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ client/src/api/client.ts │ MODIFY (add billing API calls) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ client/src/App.tsx │ MODIFY (add billing route) │
├─────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ client/src/pages/MatchaWorkThread.tsx │ MODIFY (handle 402, low-credit banner) │
└─────────────────────────────────────────────────────────┴───────────────────────────────────────────────────────┘

---

8.  Verification

1.  Run DB migration: alembic upgrade head
1.  Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET in .env
1.  Run server: python3 run.py — confirm new routes load without errors
1.  Test balance endpoint: GET /matcha-work/billing/balance → returns { credits_remaining: 0 }
1.  Test gating: send a Matcha Work message → get 402
1.  Admin grant: POST /admin/companies/{id}/credits with credits=50 → balance updates
1.  Send message again → succeeds, balance drops to 49
1.  Test Stripe: use stripe listen --forward-to localhost:8001/webhooks/stripe, create checkout, complete with test card
1.  Confirm credits added after webhook fires
1.  Frontend: navigate to /matcha-work/billing, see balance, click buy pack → Stripe Checkout opens
