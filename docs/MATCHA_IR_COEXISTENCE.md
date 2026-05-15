# Matcha IR — Coexistence with Existing Bespoke IR

Companion to `MATCHA_IR_PLAN.md`. Explains how the new self-serve IR-only product shares infrastructure with the existing platform-tied IR system without colliding.

## Two paths coexist on same tables

Diff only in **signup**, **layout**, and **billing**. Schema, routes, services, AI logic — all shared.

### Bespoke (existing)

- `register_business()` defaults to `status='pending'`, `signup_source='bespoke'`.
- Sales / CSM does manual approval, sets license, locations, CRM hooks, flips many `enabled_features`.
- Billing = enterprise contract + token packs (`mw_subscriptions`).
- Data lives in `ir_incidents` keyed by `company_id`.
- Layout = full platform sidebar.

### IR-only (new)

- `register_business(tier='ir_only')` auto-approves, writes `signup_source='ir_only_self_serve'`, sets `enabled_features={"incidents":true}` only.
- Self-serve Stripe checkout at signup.
- Billing = flat subscription (`ir_subscriptions`).
- Data lives in same `ir_incidents` keyed by `company_id`.
- Layout = slim `IrLayout` (Incidents / Employees / Settings / Billing).

Both write to **identical schema**. No fork, no parallel tables, no duplicated services.

## How they don't collide

| Concern | Resolution |
|---------|-----------|
| Schema | Single `ir_incidents`, `ir_documents`, `ir_audit_log`, `ir_investigation_interviews`, `osha_annual_summaries`. Partitioned by `company_id`. Both tiers query the same way. |
| Routes | All 39 IR endpoints use `require_admin_or_client`. Both tiers' admins have the `client` role. |
| Layout selection | `isIrOnlyTier(company)` requires `signup_source='ir_only_self_serve'` AND `enabled_features.incidents=true`. Both must match. Bespoke customers never get the slim layout regardless of flag shape. |
| Billing | Separate tables (`ir_subscriptions` vs `mw_subscriptions`). One company can theoretically hold both — webhook handlers don't conflict. |
| Bespoke onboarding (license, CRM, integrations) | Untouched. IR-only wizard skips it entirely. Bespoke customers continue through manual sales path. |
| AI services | `ir_analysis`, `ir_precedent`, `ir_consistency`, `ir_interview_questions` are pure incident logic — tier-agnostic. |
| ER copilot bridge | `er_copilot.py` reads `ir_incidents` by `company_id`. Only fires if `enabled_features.er_copilot=true`. Bespoke ✓, IR-only ✗ until upgrade. |
| Anonymous reporting | Token-based, per-company. Identical for both tiers. |
| OSHA logs | Per-company `osha_annual_summaries`. Identical for both tiers. |

## Disambiguation: signup_source

`companies.signup_source VARCHAR(32)` with values:

- `bespoke` — sales-led, full platform (default for all existing rows via backfill).
- `ir_only_self_serve` — Matcha IR self-serve signup.
- `personal` — matcha-work individual user.
- `invite` — joined via team invite link.
- `broker` — broker referral.

Layout selector keys off `signup_source` first, feature flags second. A bespoke customer who happens to be partially-provisioned with only `incidents=true` still gets the full sidebar because their `signup_source` is `bespoke`.

## Upgrade direction

### IR-only → full

- Self-serve: Stripe customer portal → flips additional flags (`er_copilot`, `compliance`, `policies`, etc.). Layout stays slim until CSM optionally promotes `signup_source` to `bespoke`.
- Sales-led: CSM manually flips flags + promotes `signup_source='bespoke'`. Cuts over to full sidebar immediately.
- Either way, all existing IR data is already accessible to ER copilot and compliance routes the moment those flags are on — no data migration.

### Bespoke → IR-only

- Not a v1 path. Manual downgrade if ever needed (CSM flips flags + writes `signup_source='ir_only_self_serve'`, optionally moves billing to `ir_subscriptions`).

## Bottom line

Existing bespoke IR untouched. New tier is **additive**:

- One new column on `companies` (`signup_source`).
- One new column on `employees` (`external_uid`).
- One new table (`ir_subscriptions`).
- One new layout component (`IrLayout`).
- New signup pages + onboarding wizard.

Both tiers populate the same incident table, hit the same AI services, and respect the same anonymous-reporting and OSHA flows. Only the front door, the sidebar, and the billing relationship differ.
