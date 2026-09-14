# Products — full mechanics

Moved verbatim from root `CLAUDE.md`'s Products section. Root keeps the signup/tier/sidebar/routes/billing table and a one-line-per-product summary.

### Free — resources hub
- Marketing/upgrade landing for self-serve signups. No paid features.
- All `enabled_features` off; gated by `<RequireBusinessAccount>` (`client/src/components/`).
- Backend: `server/app/core/routes/resources/`. Public landing pages + business-gated tools (templates, state guides, calculators, audit, glossary, job descriptions).
- Free→paid path: `<UpgradeUpsellCard>` ("Talk to sales") posts to `/api/resources/upgrade/inquiry`.

### Matcha-lite — paid IR + HR records (entry tier)
- Stripe-purchasable, headcount-based (max 300 employees).
- Checkout: `POST /resources/checkout/lite` (`server/app/core/routes/resources/checkout.py`). Stripe webhook `checkout.session.completed` flips `enabled_features.incidents=true` — until then `MatchaLitePendingSidebar` shows the Subscribe CTA.
- Once paid: `incidents` + `employees` + `handbooks` (handbook **generation**) on; `IrSidebar` exposes incidents, risk insights, OSHA, handbooks, employees, company. **No** handbook audit, training, discipline, or credentialing — those moved up to **Matcha-X** (the `matcha_lite` tier overlay force-asserts `training`/`discipline` off). See the tier-bundle note under Feature Flags.
- Backend routers: `ir_incidents_router` (`/ir/incidents/*`), `ir_onboarding_router` (`/ir-onboarding/*`) in `server/app/matcha/routes/__init__.py`.
- Onboarding: `client/src/components/ir/onboarding/IrOnboardingWizard.tsx`; completion stamps `companies.ir_onboarding_completed_at`.
- Legacy `pages/auth/IrSignup.tsx` (`tier='ir_only'`, `signup_source='ir_only_self_serve'`) still wired at `/ir/signup` for private beta — also lands on `IrSidebar`.

### Matcha Compliance — standalone self-serve compliance product
- Self-serve, Stripe-purchasable product that grants the **full** `compliance` feature and nothing else. Modeled on Matcha-lite/Matcha-X: signup page → pending sidebar → Stripe checkout → webhook flips a flag → active sidebar.
- Signup: `pages/auth/ComplianceSignup.tsx` at `/compliance/signup` (`tier='matcha_compliance'`, `signup_source='matcha_compliance'`); collects headcount **+ jurisdiction count**.
- Checkout: `POST /resources/checkout/compliance` (`server/app/core/routes/resources/checkout.py`). Pricing = headcount component + per-jurisdiction surcharge (`matcha_compliance_price_cents`, `stripe_service.py` — placeholder, see TODO). Stripe webhook `checkout.session.completed` (`type='matcha_compliance'`) flips `enabled_features.compliance=true`; until then `CompliancePendingSidebar` shows the Subscribe CTA.
- Once paid: `ComplianceSidebar` (Compliance, Compliance Calendar, Company, Compliance Setup); `/app/compliance` renders the full `ComplianceFull` view (not the lite taste — `compliance` is true).
- Onboarding **reuses** `MatchaXOnboardingWizard` at `/compliance/onboarding` (locations → policies → people → build).
- Jurisdiction count persists in `company_handbook_profiles.compliance_jurisdiction_count` (migration `compljuris01`); surfaced on `/auth/me` as `profile.jurisdiction_count`.

### Matcha — full bespoke platform
- Companies created with `signup_source='bespoke'` (default) by admins post-sales call, or via `BetaRegister.tsx` invite tokens.
- Sidebar: `ClientSidebar` (Dashboard, Company, HR Ops, Compliance, Communication, Safety, AI groups).
- Routes: `/app/*` registered in `client/src/routes/AppRoutes.tsx`.
- Backend: everything under `server/app/matcha/` plus `server/app/core/`.
- Per-company access via `companies.enabled_features` JSONB. When a user URL-hops to a feature they don't have, `<FeatureGate>` (`client/src/components/shared/FeatureGate.tsx`) renders `<UpgradeUpsellCard>` instead of a 403.

### Matcha-work — collaborative AI workspace
**Naming convention**: the **web** workspace surface (this section) is referred to as **matcha-work**; the **macOS desktop** workspace is referred to as **Espresso** (formerly "Werk" — renamed to avoid confusion with matcha-work; `platforms/desktop/Espresso/`). Both share the same backend (`server/app/matcha/routes/matcha_work/` package) and `mw_*` tables — only the client differs. When asked to ship a feature, confirm which surface is meant before editing files.

- Surface: `client/src/work/pages/*` + `client/src/work/layout/WorkLayout.tsx`. Mounted at `/work/*` in `App.tsx`.
- Backend: `server/app/matcha/routes/matcha_work/` (package, split 2026-07-03), `server/app/matcha/services/matcha_work/project_service/`. Tables prefixed `mw_*`.
- macOS desktop client (**Espresso**): `platforms/desktop/Espresso/` (SwiftUI). Xcode project name is still `Matcha.xcodeproj` and bundle ID `com.ahnimal.matcha` — App Store identity is unchanged; only the working directory and conceptual product name differ. `AppState.isPlusActive` from `Subscription.isPersonalPlus` controls Plus features.
- **Personal mode**: user `role='individual'`. Signup via `BetaRegister.tsx` (`/auth/beta?token=…`) → redirected to `/work`. Stripe sub `matcha_work_personal` ($20/mo) via `POST /api/checkout/personal` (`server/app/matcha/routes/work/billing.py`).
- **Business mode**: user `role='client'` inside a Matcha company. Token packs purchased via `POST /api/checkout`. Sidebar entry in `ClientSidebar.tsx` AI group → `/work`.
- Surfaces inside: projects, threads, channels (real-time WebSocket), inbox (DMs), people/connections, anonymous incident report intake.
- Stripe-gated sub-features: `paid_channel_creator`, `channel_job_postings` in `server/app/core/feature_flags.py`.

### Custom products — the admin product builder (`/admin/products`)

Everything above is a **hardcoded** product (~10 touchpoints each). **New** packages are data instead: an admin composes one at `/admin/products` (`pages/admin/Products.tsx`) and gets a live `/p/<slug>/signup` link.

- **Table** `product_definitions` (+ `product_definition_history`), migration `proddef01`. Service `core/services/product_definitions.py` — the whitelist (`ALLOWED_PRODUCT_FEATURES` = `DEFAULT_COMPANY_FEATURES` + `incidents`/`employees`) is the authorization boundary for what signup and billing may flip, exactly like `lite_addons.py`.
- **Tenants** get `signup_source = 'product:<slug>'` — namespaced, so it can never collide with a hardcoded source, and it's a no-op in the `TIER_REQUIRED_FEATURES` lookup.
- **Grants are MATERIALIZED**, not overlaid: `merge_company_features` is pure + sync and runs in the pool-free Celery workers, so a DB-consulting overlay would need a cache on the hot path of every request. Consequence: editing a live product does **not** retro-grant — `POST /admin/products/{id}/sync-tenants` re-materializes activated tenants (pending ones are skipped, or the product would be free).
- **Pricing**: per-seat / per-location / block / flat (Stripe) · free (activates at signup) · contact-sales (stays pending; admin runs `activate-tenant`). Per-location signup stores its billing quantity in `company_handbook_profiles.custom_product_location_count`, separately from the `business_locations` rows that do not exist yet at initial checkout.
- **Paid gate**: each priced product names one `gate_feature` (its `incidents`) — false while pending, flipped by the webhook, reset on `customer.subscription.deleted` (pack_id `product:<slug>`).
- **Frontend**: `/auth/me` carries `profile.product`; `TenantSidebar` dispatches to `tier-sidebars/ProductSidebar.tsx`, nav derived from `data/productNavCatalog.ts` (feature → route/icon/label — add one line there per new page).
- **First-account setup** (`onboarding_kind`, migration `sconboard01`): a product may name a setup wizard the tenant must finish before the product opens. `'sc'` is the only kind — the Matcha S&C wizard (`components/sc/onboarding/ScOnboardingWizard.tsx` → `/sc-onboarding`, `services/sc_onboarding.py`), which collects company size + NAICS, optional location/employee CSVs, and the job → mandatory-certificate matrix, then writes them in **one transaction** (nothing exists until the final review is approved). Mechanics worth knowing before touching it:
  - Selecting `'sc'` in the builder requires `employees` + `employee_schedule` + `credential_templates`, and the router mounts the same three as a `require_all_features` gate. The kind is **locked after the first signup** (`signup_source='product:<slug>'` tenant count > 0).
  - Completion stamps `companies.sc_onboarding_completed_at`; `RequireScOnboardingComplete` (wired in `App.tsx` around `/app/*`, `/ops/*` and `/work/*` — **not** inside one route tree, or `/ops/schedule` stays reachable) bounces an activated, unfinished tenant back to `/sc/onboarding`.
  - Signup owns `companies.industry` (controlled `INDUSTRY_OPTIONS` vocabulary); the wizard deliberately does not re-ask or overwrite it.
  - **The CSVs are parsed on the server**, not in the browser: `POST /sc-onboarding/csv/{locations|employees}` validates and hands the rows back without writing anything, so the wizard keeps its "nothing exists until the review is approved" contract while the RULES live once, in `services/employees/roster_csv.py`, beside the ones `employees/bulk_upload.py` applies (email shape, work-state normalization — full state names included — source-line accounting). The expected headers ride on `GET /sc-onboarding/status` so the UI renders the parser's own columns.
  - Certificates become **tenant-owned** credential types: the `credential_types` row is an opaque FK target labelled `'Tenant credential'` per `credcustom01`, the customer's wording lives in `company_credential_types`, and a configured allowlist gets the new type added so `replace_job_credential_requirements` doesn't refuse it.
  - Stripe's `success_url` points at `/sc/onboarding`, which can beat the activating webhook — the wizard polls a bounded number of 403s ("Finishing activation…") instead of dead-ending.
