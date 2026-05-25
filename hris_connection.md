Answers lock it. Finch. ATS = vapor → Merge breadth unused. Read-only now but write-back has real value
for your app (explained below). Cost shape = Finch managed connections matter for broker long-tail.

Write-back value for your app (you asked)

Today the Gusto link is pull-only and the webhook is inbound (Gusto → matcha). Write-back flips
direction: matcha → payroll. Three spots where your existing surfaces would gain:

- Onboarding → provision into payroll. You already provision Google Workspace + Slack on new-hire
  (provisioning.py, google_workspace_service.py). Add payroll: new hire finishes matcha onboarding → push
  employee record INTO Gusto. Kills double-entry. Big broker selling point — broker runs onboarding,
  employee lands in client's payroll automatically.
- Termination/status → payroll offboarding. You track employment_status (terminated/on_leave/suspended)

* discipline workflow. Write-back pushes termination → payroll triggers final-pay/offboarding. Closes
  the loop the inbound webhook only half-covers.

- Comp change → payroll. Pay-rate edits in matcha sync back instead of HR re-keying in Gusto.

Finch ships employment write-back (create/update employee). Merge's HRIS write is thin. Neither runs
actual payroll (tax/earnings) — you don't need that. So write-back ambition = another point for Finch,
not against.

Caveat both: write-back coverage varies by underlying provider; Gusto good, long-tail spottier.

Vendor Decision: Finch vs Merge for HRIS/Payroll Integration

Context

Matcha is being evaluated by brokerages as an offering for their clients. The app
already ships a direct Gusto + ADP HRIS integration (branch gusto-2), gated behind
the hris_import feature flag. The question is whether to standardize future HRIS/payroll
connectivity on a unified-API vendor — Finch (employment-only, lean data-at-rest, deep
payroll, write-back, managed/assisted connections for no-API systems) or Merge (broad
multi-category coverage, but store-and-sync — caches a copy of customer data on its servers).

This document records the recommendation, the codebase evidence behind it, and the
integration approach if/when we proceed. No code change is requested yet — this is a
decision artifact plus an implementation sketch.

---

Recommendation: Finch

Three strongest reasons, all grounded in this codebase:

1.  Scope is employment-only — Merge's breadth is dead weight.
    No CRM, accounting, or ticketing footprint anywhere (confirmed across docs, routes,
    deps). The single non-HR category Merge would add is ATS (Greenhouse/iCIMS) — and the
    user confirmed that's a sales-deck upsell line only (docs/sales/HEALTHCARE_PRICING.md
    "+$1.00 PEPM … Not built"), not committed work. File storage is Google-Workspace-only
    first-party provisioning, not a unified-API target. Paying for Merge's multi-category
    platform buys nothing we use.
2.  Brokerage security review punishes a third-party data-at-rest copy.
    Sold through brokers → every client triggers a security review. Current posture is
    already lean and defensible: Fernet field encryption (core/services/credential_crypto.py,
    secret_crypto.py), Postgres RLS tenant isolation (alembic/.../add_row_level_security.py),
    AWS Secrets Manager, S3 SSE-256, and no SSN/DOB/bank/direct-deposit collected at all.
    Merge's store-and-sync adds a third-party cache of client HR data — a new data-at-rest
    footprint to disclose and defend in every review. Finch's API-pass-through model keeps
    the at-rest surface lean, matching what we already tell brokers.
3.  Data need is shallow + read-only today, and Finch fits the broker long-tail.
    We store basic HRIS identity + a single pay_rate + FLSA pay_classification
    (alembic/.../add_employee_compensation_fields.py) — no earnings/tax/deduction
    breakdowns, no benefits/401k, no pay stubs. The broker channel = many small client
    companies, one connection each (brokers → broker_company_links → companies, 1:many).
    Those clients run long-tail/no-API payroll; Finch's managed/assisted connections
    cover that tail, and Finch's employment write-back unlocks future provisioning value
    (onboarding → create employee in payroll; termination → trigger offboarding; comp change
    → push back) that Merge's thin HRIS-write does not.

Biggest risk of choosing Finch

If ATS sync ever becomes real (Greenhouse/iCIMS), Finch can't cover it — we'd add a second
vendor or revisit Merge. User flagged ATS as sales-deck-only, so this risk is currently low,
but it's the one scenario that would have favored Merge's single-vendor breadth. Secondary:
Finch's connector count for obscure HRIS is narrower than Merge's, partially offset by
managed connections.

Still to confirm before signing (not blocking the direction)

- Pricing — both vendors, real quotes. Per-connection cost at many low-headcount broker
  connections is the cost risk. Confirm who pays (employer-pays vs we-pay) and the per-
  connection rate under the broker-reseller model. (User: "both equally" important.)
- Small-payroll coverage. Validate Finch managed-connection coverage against the actual
  payroll systems brokerage clients use (the long tail), since that's the channel's reality.

---

Integration Approach (when we proceed)

The codebase is already shaped for this — we extend the existing provisioning surface
rather than build new infrastructure.

Reuse what exists

- Schema: integration_connections (provider enum, encrypted secrets JSONB),
  external_identities, hris_sync_runs, provisioning_audit_logs — all in
  server/app/database.py (~line 4232+). Extend the provider CHECK constraint to include
  'finch' (needs Alembic migration → user approval required, per server/CLAUDE.md).
- OAuth state pattern: HMAC-signed, company_id-embedded, TTL-bounded state already
  built for Slack/Gusto in server/app/matcha/routes/provisioning.py
  (\_build_slack_oauth_state / Gusto OAuth at ~line 1629). Finch Connect uses the same
  authorization-code shape — clone the flow.
- Secret encryption: core/services/secret_crypto.py (encrypt_secret/decrypt_secret,
  enc:v1: prefix) for the Finch access token.
- Sync orchestrator: server/app/matcha/services/hris_sync_orchestrator.py
  (start_hris_sync, \_sync_single_employee, COALESCE-on-partial upsert) — reuse the
  upsert/normalize/audit pipeline; only the fetch+normalize source changes.
- Background jobs: Celery worker (server/app/workers/celery_app.py, @worker_ready
  dispatch, 15-min systemd restart) for periodic sync.
- Feature gate: hris_import flag already wraps every HRIS endpoint.

New code

- server/app/matcha/services/finch_service.py — Finch Python SDK wrapper mirroring
  GustoHRISService (fetch_workers, normalize_worker → existing employee field shape:
  identity, work_city/work_state, pay_rate, pay_classification).
- Finch Connect authorize + callback routes in provisioning.py, cloning the Gusto OAuth
  pair; store token via secret_crypto.
- Optional later: write-back methods (create/update employee) wired to onboarding completion
  and employment_status transitions — gate behind a new sub-flag; keep read-only as default.
- Celery task to dispatch periodic Finch syncs through the existing orchestrator.

Verification

- Dev: connect a Finch sandbox company via the Connect flow → run /hris/sync → assert
  rows upserted into employees + external_identities, and hris_sync_runs row records
  created/updated counts. Use Finch sandbox data only — never run sync-writes against
  production payroll.
- Confirm hris_import-gated endpoints 403 without the flag.
- For write-back (if built): test create/update against Finch sandbox exclusively; assert
  audit rows in provisioning_audit_logs.
- DDL (provider enum widening) is the only schema change — present the migration to the user
  for explicit approval before applying; do not run alembic upgrade autonomously.
