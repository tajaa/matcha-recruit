# Cappe ↔ Matcha Feature Bridge

Lets a Cappe (gummfit) account use selected matcha features — starting with
**IR incidents** — without merging the two identity models. Shipped 2026-07
(migration `cappebridge01`).

## Architecture decision

Three options were considered; **parallel entitlement (broker-style)** won:

| Option | Verdict |
|---|---|
| **Parallel entitlement** — flags on `cappe_accounts`, cappe-native gate | ✅ Chosen. Follows the `brokers.plan` / `require_broker_pro` precedent for entitling a non-tenant identity. |
| Shadow company + token bridge — matcha routes accept cappe sessions | ❌ Couples the identity models; every matcha route becomes cappe-reachable. |
| Unified account — merge `cappe_accounts` into `users`/`companies` | ❌ Largest change, highest risk; revisit only if the products converge. |

Auth stays firewalled end to end: cappe tokens keep `scope=cappe`, matcha's
`get_current_user` keeps rejecting them, and no dual-scope token exists.

## The one deliberate exception: backing tenant rows

Matcha's data layer is hard-bound to its tenancy — `ir_incidents.company_id`
FKs `companies(id)` and sits under RLS; `created_by`/audit actors FK
`users(id)`. Rather than fork 12k lines of IR code into FK-less `cappe_ir_*`
tables, each cappe account that enables a matcha feature gets a **backing
tenant**, created lazily on first enable:

- 1 `companies` row — `signup_source='cappe'`, **`owner_id` NULL**
- 1 `users` row — role `client`, bridge email
  `cappe+<account_id>@bridge.matcha.invalid` (RFC 2606 reserved → the email
  guard hard-blocks any accidental send), random discarded password —
  **it can never authenticate**
- 1 `clients` row linking them, so `resolve_accessible_company_scope` resolves
  the tenant like any client and sets the RLS contextvar

These rows are plumbing, not identity. The bridged `CurrentUser` is only ever
minted server-side by `require_matcha_feature` after the cappe token +
entitlement checks pass.

**Invariant: backing companies stay out of admin/matcha company surfaces.**
Two guards enforce this: `owner_id IS NULL` (the business-registration lists +
`/admin/overview` filter `owner_id IS NOT NULL`) and an explicit
`signup_source IS DISTINCT FROM 'cappe'` filter on the company scans that don't
key off `owner_id` (`/admin/company-features`, `/admin/companies`, the
`/admin/notifications` registrations feed). Any **new** query that scans
`companies` must add the `signup_source` guard, or a cappe backing company —
and its directly-mutable `enabled_features` — leaks into that surface.

## Pieces

| Piece | Where |
|---|---|
| Migration | `server/alembic/versions/cappebridge01_cappe_matcha_bridge.py` — `cappe_accounts.matcha_features` JSONB + `matcha_company_id` + `matcha_user_id` |
| Bridge service | `server/app/cappe/services/matcha_bridge.py` — `MATCHA_BRIDGEABLE_FEATURES` whitelist, `ensure_backing_tenant`, `set_matcha_features`, `require_matcha_feature(flag)` gate |
| IR adapter router | `server/app/cappe/routes/ir.py` — `/api/cappe/ir/*`, thin wrappers calling the matcha `ir_incidents` handlers directly with the bridged `CurrentUser`; plus a cappe-owned `/ir/locations` surface (`business_locations` rows with `auto_check_enabled=false` so compliance workers never scan them) |
| Admin toggle | `PUT /api/admin/cappe/accounts/{id}/matcha-features` (`core/routes/admin.py`); roster endpoint now returns `matcha_features` |
| Entitlement surfacing | `CappeAccount.matcha_features` (via `require_cappe_account` → `/api/cappe/auth/me`) |
| Frontend | `client/src/api/cappeIr.ts`, `client/src/pages/cappe/incidents/*`, account-level routes in `CappeRoutes.tsx`, nav gated on `matcha_features.incidents` |

## Phase-1 scope (IR)

Mirrors the `matcha_lite_essentials` shape — the existing no-roster IR tier:
incident CRUD, corrective actions (CAPA), documents, `ir_people` no-roster
index, locations. **Excluded:** OSHA logs, employee-roster flows, copilot,
analytics, anonymous report links, exports — all phase-2 candidates via the
same wrapper pattern.

## Adding the next bridged feature

1. Add the flag to `MATCHA_BRIDGEABLE_FEATURES` in `matcha_bridge.py`.
2. Write an adapter router `server/app/cappe/routes/<feature>.py` wrapping the
   matcha handlers with `Depends(require_matcha_feature("<flag>"))` — `ir.py`
   is the template. Multi-segment static paths must register before
   `/{id}` catch-alls (same trap as `ir_incidents/CLAUDE.md` "Route ordering").
3. Mount it in `cappe/routes/__init__.py`.
4. Frontend: API module + pages + nav entry gated on
   `account.matcha_features.<flag>`.
5. Audit any matcha Celery worker that scans `companies`/related tables for
   how it treats `signup_source='cappe'` tenants (see below).

## Known interactions / watch-list

- **Workers**: backing companies mirror their granted flags onto
  `companies.enabled_features` (with `osha_logs`/`employees` force-asserted off
  — the essentials shape), so matcha-side workers treat them consistently.
  Anything new that scans companies should be checked against
  `signup_source='cappe'`.
- **Notifications go nowhere yet (phase-1 limitation).** All IR notification
  paths (`send_ir_notifications_task`, the `ir_deadline_alerts` worker) resolve
  recipients from the backing company's `clients`/`users` rows — which for a
  cappe tenant is only the unloginable bridge user on `@bridge.matcha.invalid`,
  hard-blocked by the reserved-domain email guard. So the real cappe owner is
  **not** emailed about new incidents or overdue CAPA. This fails silent (a log
  line, no bounce), not loud. Deferred, not "working": routing to
  `cappe_accounts.email` needs a bridge-aware recipient resolver
  (`_get_company_admin_contacts`), because putting the real email on the bridge
  `users` row would risk colliding with a real matcha `users.email` (the
  `ON CONFLICT (email)` path would then hijack an existing matcha identity —
  the `.invalid` address exists precisely to prevent that).
- **Cross-product import rule**: `cappe/routes/ir.py` imports from
  `app/matcha/*` — a documented exception to "cappe imports only from core"
  (the bridge is the point). Keep such imports confined to adapter routers +
  `matcha_bridge.py`; cappe's own business logic must stay matcha-free.
- **Disabling a flag** flips the gate to 403 immediately; backing rows and
  incident data are left intact (re-enable restores access).
- **Billing**: admin-toggled for now, exactly like matcha's admin-toggle
  flags. Phase 2: Stripe checkout on the cappe side (cappe already has
  Stripe), modeled on `matcha_lite_addon`.

## Deploy notes

- Run `./scripts/migrate-dev.sh` then (with approval) `./scripts/migrate-prod.sh`
  for `cappebridge01` **before** deploying — `require_cappe_account` now
  selects `matcha_features` and will 500 on a DB without the column.
