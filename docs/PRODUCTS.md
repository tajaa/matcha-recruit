# Products — full mechanics

Moved verbatim from root `CLAUDE.md`'s Products section. Root keeps the signup/tier/sidebar/routes/billing table and a one-line-per-product summary.

### Pricing — `/admin/pricing`
One admin page (`client/src/pages/admin/Pricing.tsx`) for every price we are still testing:
- **Incident reporting** (Matcha Lite, Lite Essentials) and **Espresso** (Lite, Pro): rows of `matcha_lite_pricing`, edited through `PUT /api/admin/matcha-lite-pricing?product_code=…` (history in `matcha_lite_pricing_history`). The same form also lives under Signup Links → Pricing, which keeps Compliance, the Lite add-ons and Tell-Us.
- **Scheduling** (and any other published, Stripe-billed product-builder product): `product_definitions.price_cents`, edited through the price-only `PUT /api/admin/products/{id}/price` (snapshots to `product_definition_history`; refuses free / contact-sales products).

How a price reaches Stripe:
- **No stored Stripe Prices.** Every checkout session builds an inline `price_data` from the row when the session is created, so an admin save is what the next checkout charges. Nothing is synced or archived in Stripe.
- **Existing subscribers keep the amount they signed up at.** Nothing reprices a live subscription.
- **`espresso_lite` / `espresso_pro` are flat** (`FLAT_PRODUCT_CODES`): one unit, no headcount. The admin PUT pins `block_size`, `min_headcount` and `max_headcount` to 1. With no row, the code fallback is the launch price ($9 / $20), so they need no seed migration.
- **Every buyer-facing price reads the same row:**
  - The Espresso paywalls (web `PaywallModal`, macOS `PaywallSheet`) read `GET /api/matcha-work/billing/plans`.
  - The scheduling landing page's "Start now" band and value estimate read `GET /api/products/schedule-comm` (`pages/landing/scheduling/useSchedulingPrice.ts`). Its three Basic/Pro/Autopilot cards are still marked as proposed.
  - The Lite signup reads `GET /api/resources/matcha-lite/pricing`.
- **Not on the page:** Matcha-X (`stripe_service.matcha_x_price_cents`) and the business token subscription (`stripe_service` literal 4000) are still hardcoded.

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
**Naming convention**: the shared web workspace has the business **matcha-work** surface at `/work` and the personal **Espresso** surface at `/espresso`; the **macOS desktop** workspace is also **Espresso** (formerly "Werk"; `platforms/desktop/Espresso/`). All surfaces share the same backend (`server/app/matcha/routes/matcha_work/` package) and `mw_*` tables. When asked to ship a feature, confirm which surface is meant before editing files.

- Web surfaces: `client/src/work/pages/*` + `client/src/work/layout/WorkLayout.tsx`. Mounted at `/work/*` for business users and `/espresso/*` for personal users in `App.tsx`; legacy `/werk/*` links redirect to `/espresso/*`.
- Backend: `server/app/matcha/routes/matcha_work/` (package, split 2026-07-03), `server/app/matcha/services/matcha_work/project_service/`. Tables prefixed `mw_*`.
- macOS desktop client (**Espresso**): `platforms/desktop/Espresso/` (SwiftUI). Xcode project name is still `Matcha.xcodeproj` and bundle ID `com.ahnimal.matcha` — App Store identity is unchanged; only the working directory and conceptual product name differ. `AppState.isPlusActive` from `Subscription.isPersonalPlus` controls Plus features.
- **Personal mode**: user `role='individual'`. Signup via `BetaRegister.tsx` (`/auth/beta?token=…`) → redirected to `/espresso`. Stripe sub Lite (`matcha_work_lite`) or Pro (`matcha_work_personal`), priced by the `espresso_lite` / `espresso_pro` rows of `matcha_lite_pricing` (see §Pricing), via `POST /api/matcha-work/billing/checkout/personal` (`server/app/matcha/routes/work/billing.py`).
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
- **First-account setup** (`onboarding_kind`, migration `sconboard01`): a product may name a setup wizard the tenant must finish before the product opens. `'sc'` is the only kind — the Matcha S&C wizard (`components/sc/onboarding/ScOnboardingWizard.tsx` → `/sc/onboarding`, `services/sc_onboarding.py`), which collects company size + NAICS and optional locations/employees, then writes them in **one transaction** (nothing exists until the final review is approved). The four steps are Company → Locations → Employees → Review; jobs and certificate rules can be configured from the schedule after setup. Mechanics worth knowing before touching it:
  - Selecting `'sc'` in the builder requires `employees` + `employee_schedule` + `credential_templates`, and the router mounts the same three as a `require_all_features` gate. The kind is **locked after the first signup** (`signup_source='product:<slug>'` tenant count > 0).
  - Completion stamps `companies.sc_onboarding_completed_at`; `RequireScOnboardingComplete` (wired in `App.tsx` around `/app/*`, `/ops/*` and `/work/*` — **not** inside one route tree, or `/ops/schedule` stays reachable) bounces an activated, unfinished tenant back to `/sc/onboarding`.
  - Signup owns `companies.industry` (controlled `INDUSTRY_OPTIONS` vocabulary); the wizard deliberately does not re-ask or overwrite it.
  - **The CSVs are parsed on the server**, not in the browser: `POST /sc-onboarding/csv/{locations|employees}` validates and hands the rows back without writing anything, so the wizard keeps its "nothing exists until the review is approved" contract while the RULES live once, in `services/employees/roster_csv.py`, beside the ones `employees/bulk_upload.py` applies (email shape, work-state normalization — full state names included — source-line accounting). The expected headers ride on `GET /sc-onboarding/status` so the UI renders the parser's own columns.
  - **Employee `job_title` → job is the assignment key**, not a catalog lookup: the wizard automatically submits one job per distinct roster title, with no certificate requirements, and shows the names in the final review. Replacing or clearing the roster also replaces or clears its derived jobs. A matched employee lands in `schedule_job_employees`; the server still refuses unmatched titles or names already in the company's `schedule_jobs`. Skipping employees permits an empty jobs list; the 500-job cap matches the roster's 500-row cap. The API continues to accept explicit job/certificate configurations from older clients.
  - Certificates become **tenant-owned** credential types: the `credential_types` row is an opaque FK target labelled `'Tenant credential'` per `credcustom01`, the customer's wording lives in `company_credential_types`, and a configured allowlist gets the new type added so `replace_job_credential_requirements` doesn't refuse it.
  - Stripe's `success_url` points at `/sc/onboarding`, which can beat the activating webhook — the wizard polls a bounded number of 403s ("Finishing activation…") instead of dead-ending.
  - Products with `matcha_ops` + `inventory` + `sales_intake` finish setup at `/ops/schedule/editor?setup=sales`. Notifications explains missing sales, offers the existing Square connection flow or store-bound nightly-email registration, and distinguishes configuration from received data. Finch remains the HRIS/payroll integration. Other products retain the normal schedule handoff.
