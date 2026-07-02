# Matcha-Tellus ("Tell Us") — Technical Plan

**Status:** Proposed · **Date:** 2026-07-02

A new **separate product**: a public "Tell Us" feedback channel where store customers /
visitors report experiences at a physical location — good *or* bad. Examples: "we were
treated badly", "we were treated well", "the AC wasn't on", "there was a messy spill",
"someone fell at the store — here's a video".

It generalizes the existing Matcha-lite anonymous IR intake (QR code / public link →
`/report/:token`, `/intake/:token`) to a **customer** audience, with **positive feedback
as a first-class concept** and **photo/video attachments** (net-new capability).

---

## 1. Positioning & product decisions

| Decision | Choice |
|---|---|
| **Data model** | New dedicated `tellus_*` tables (positive feedback doesn't fit the IR "incident" model). Safety reports can optionally be *promoted* into a real IR incident when the company also has IR. |
| **Pricing** | Per-location / per-store Stripe subscription (a store-feedback product scales by number of stores, not headcount). |
| **Media** | Photo **and** video, size-capped, private S3 bucket + presigned upload/playback. |
| **Scope** | Standalone self-serve product **and** an embeddable `/app/tellus` surface inside full-Matcha companies. |

Identity: `signup_source='matcha_tellus'`, feature flag `tellus` (Stripe-flipped paid gate,
exactly like `incidents`/`compliance`). Scaffolding mirrors **Matcha Compliance** end-to-end
(signup page → pending sidebar → Stripe checkout → webhook flips the flag → active sidebar).

Key differences from IR intake that drive the design:
- **Public/customer reporters**, not employees — anonymous, with *optional* contact for follow-up.
- **Sentiment axis** (positive / neutral / negative) + a **customer-experience taxonomy**
  (service, cleanliness, facilities, safety, compliment, other), instead of IR severity/type.
- **Media attachments** — no existing public intake path accepts files today; this is net-new.

---

## 2. Data model — Alembic migration `tellus01`

Model the link tables on the existing reusable `ir_report_links` / `ir_report_link_history`
pattern (rotate / revoke / expire / max_uses / history). Tellus needs the **reusable**
per-location link semantics, not the single-use `companies.report_email_token`.

### `tellus_reports` — one row per submission
```
id UUID PK
company_id           UUID -> companies
location_id          UUID -> business_locations (nullable)
report_number        VARCHAR UNIQUE
category             CHECK IN (service, cleanliness, facilities, safety, compliment, other)
sentiment            CHECK IN (positive, neutral, negative)
title                VARCHAR
description          TEXT
occurred_at          TIMESTAMP
reporter_name        VARCHAR (nullable — anonymous by default)
reporter_contact     TEXT/JSONB (nullable — optional follow-up)
status               CHECK IN (new, reviewing, resolved, archived) DEFAULT 'new'
ai_summary           TEXT           -- Gemini summary
ai_category          VARCHAR        -- AI suggestion, distinct from confirmed category
ai_sentiment         VARCHAR        -- AI suggestion
promoted_incident_id UUID -> ir_incidents (nullable — set when escalated to IR)
category_data        JSONB
created_at, updated_at, resolved_at
```
RLS keyed on `company_id` (mirror `ir_incidents`); public writes use `get_connection(tenant_id=...)`.

### `tellus_report_media` — attachments (net-new)
Anonymous uploader => **no `uploaded_by` FK** (differs from `ir_incident_documents`).
```
id UUID PK
report_id        UUID -> tellus_reports ON DELETE CASCADE
media_type       CHECK IN (photo, video)
storage_path     VARCHAR      -- private-bucket key / s3:// URI
mime_type        VARCHAR
file_size        BIGINT
original_filename VARCHAR
created_at
```

### `tellus_links` — reusable per-location QR links (copy `ir_report_links`)
```
id, company_id, location_id, token VARCHAR UNIQUE,
is_active BOOL, revoked_at, use_count INT, max_uses INT, expires_at,
created_by, created_at, UNIQUE(company_id, location_id)
```

### `tellus_link_history` — rotation/revocation trail (copy `ir_report_link_history`)

### `companies.tellus_location_count INT`
Store count chosen at signup; used for per-location pricing and surfaced on `/auth/me` profile.
(Alternative: a small `tellus_profiles` row, matching how Compliance stores
`compliance_jurisdiction_count`.)

Add matching bootstrap blocks to `server/app/database.py:init_db()` for parity (reference only —
schema evolution goes through Alembic). **Do not auto-run `alembic upgrade`** — prod DDL needs
explicit user approval (see root `CLAUDE.md` production-safety list). Apply to **dev only** via
`./scripts/migrate-dev.sh`.

---

## 3. Public intake — extend `server/app/matcha/routes/inbound_email.py`

Reuse the file's existing public-intake conventions: honeypot (`company_name` must be empty),
per-IP in-memory rate limit (`_is_rate_limited`), `_parse_occurred_at`, `_build_public_link`
(honors `X-Forwarded-Proto/Host`), `_derive_title`, and the **tenant-scoped connection**
(`get_connection(tenant_id=company_id)`) so INSERTs pass RLS.

New endpoints (bare paths, mounted top-level under `/api` like `/report`, `/intake`):

- **`GET /tellus/{token}`** — validate link (active, not expired, `tellus` feature on) ->
  `{valid, location_label, categories, media_enabled}` so the form shows errors early.
- **`POST /tellus/{token}`** — body: `category`, `sentiment`, `description` (min length),
  `occurred_at` (free text), optional `reporter_name` + `reporter_contact`, honeypot. Resolves
  company from token, checks link usability (adapt IR's `_check_link_usable`: revoked/expired/
  max_uses -> 410), INSERTs into `tellus_reports`, bumps `use_count` (reusable — **not** burned),
  fires a notification background task.
- **Media upload (net-new, two-step presigned — video is too big for the JSON body):**
  - **`POST /tellus/{token}/media/presign`** — validate MIME (photo: png/jpg/jpeg/gif/webp;
    video: mp4/quicktime/webm) + declared size against caps (e.g. photo <= 15 MB, video <= 200 MB)
    -> return a **presigned S3 PUT URL** into the private bucket + object key. Layered rate limits
    copied from the voice `_voice_parse_budget` template (per-IP burst/hourly, per-link, per-company).
  - Client PUTs bytes directly to S3, then submits the report with the returned keys; the server
    HEAD-verifies each key exists before inserting `tellus_report_media` rows.
  - Add `get_presigned_upload_url(...)` to `server/app/core/services/storage.py` next to the existing
    `upload_private_file` / `get_presigned_download_url`. Business playback uses
    `get_presigned_download_url`.
  - WARNING **reuse note:** `ir_incidents/documents.py:62` calls `storage.upload_file` positionally so
    `content_type` lands in the `prefix` slot — a latent bug. Call storage helpers with **keyword args**.

---

## 4. Business-side router — `server/app/matcha/routes/tellus.py`

Scaffold with the repo's `/new-router` pattern (asyncpg, tenant isolation via
`get_client_company_id`, audit log, Pydantic models under `app/matcha/models/`).

- **Link management** (copy `ir_incidents/anonymous_reporting.py`): `GET/POST /tellus/links`,
  `DELETE /tellus/links/{id}` (soft-revoke), `GET /tellus/links/{id}/history`. QR rendered
  **client-side** (`qrcode.react` `QRCodeSVG`) — no server QR endpoint, matching IR.
- **Report triage**: `GET /tellus/reports` (filter by location / category / sentiment / status),
  `GET /tellus/reports/{id}`, `PATCH` status, presigned media-playback URLs.
- **`POST /tellus/reports/{id}/promote`** — create an `ir_incidents` row from a safety report and
  set `promoted_incident_id`. Only when the company also has `incidents`; reuse `create_incident_core`
  from `ir_incidents/_shared.py`.
- **AI (optional)** — a Gemini sentiment/category/summary pass reusing the analyzer-singleton
  pattern (`get_ir_analyzer` style); writes `ai_summary` / `ai_sentiment` / `ai_category`.
- **Notifications** — `send_tellus_notifications_task` modeled on `send_ir_notifications_task`.

Mount in `server/app/matcha/routes/__init__.py` with
`dependencies=[Depends(require_feature("tellus"))]`. Add a `tellus.py` row to `routes/CLAUDE.md`.

---

## 5. Feature flag — `server/app/core/feature_flags.py`

- Add `"tellus": False` to `DEFAULT_COMPANY_FEATURES` (paid Stripe-flipped gate, like `incidents`/`compliance`).
- Add `TIER_REQUIRED_FEATURES["matcha_tellus"] = {}` overlay for any always-on bundle extras —
  but **NOT** `tellus` itself. Keeping the paid gate out of the overlay is what makes
  `isMatchaTellusPending` fire before payment (same rule as `compliance`).
- Add the CLAUDE.md flag-table row. (`/add-feature-flag` skill automates the flag half.)

---

## 6. Standalone product wiring (mirror Matcha Compliance)

### Backend
- **`server/app/core/routes/auth.py`** `register_business`: add `is_matcha_tellus = request.tier == "matcha_tellus"`
  -> `signup_source='matcha_tellus'`, initial `enabled_features` all-false (`tellus` off until webhook,
  unless broker/invite comped); persist `tellus_location_count`. Add `"matcha_tellus"` to the
  referral/invite tier whitelists and the pricing/headcount block.
- **`server/app/core/services/stripe_service.py`**: `create_matcha_tellus_checkout(...)` — **per-location**
  `price_data` (base + per-location x count), `metadata.type="matcha_tellus"` on session **and**
  `subscription_data`.
- **`server/app/core/routes/resources.py`**: `POST /checkout/tellus` (mirror `/checkout/compliance`;
  read stored `tellus_location_count`, verify `signup_source`).
- **`server/app/core/routes/stripe_webhook.py`**: add `"matcha_tellus" -> "tellus"` to **both** the
  activation `type->feature` map **and** the cancellation `pack_id->feature` map (keep in sync).
- **Pricing**: add a `product_code='matcha_tellus'` pricing row + a per-location `compute_*` helper
  (the Lite table is headcount-based; per-location needs its own component). Surface via
  `useMatchaLitePricing('matcha_tellus')`.

### Frontend
- **`client/src/utils/tier.ts`**: `isMatchaTellus` / `isMatchaTellusPending` (signup_source + `!tellus`
  for pending — the invariant used by every product).
- **`client/src/components/ir-only/TellusSidebar.tsx`**: active sidebar via `SidebarShell`
  (Reports, QR Links, Locations, Company). Copy `ComplianceSidebar.tsx`.
- **`client/src/components/TenantSidebar.tsx`**: inline `TellusPendingSidebar` (Subscribe CTA ->
  `/checkout/tellus`, `useMatchaLitePricing('matcha_tellus')`) + two dispatch branches —
  **pending checked before active**.
- **`client/src/pages/auth/TellusSignup.tsx`**: signup page (copy `ComplianceSignup.tsx`,
  `tier:'matcha_tellus'`, collects `location_count` instead of jurisdiction count).
- **`client/src/App.tsx`**: lazy-import + routes `/tellus/signup`, `/tellus/onboarding`
  (reuse an existing wizard or a minimal one), `/tellus` marketing page, and the **public**
  `/t/:token` report page.

---

## 7. Embeddable surface (full-Matcha companies)

- **`client/src/components/ClientSidebar.tsx`**: add a nav entry rendered on `hasFeature('tellus')`
  -> `/app/tellus`.
- **`client/src/pages/app/Tellus.tsx`**: reports dashboard + QR-link manager, wrapped in
  `<FeatureGate flag="tellus">`. The same backend router serves both surfaces.

---

## 8. Public report page — `client/src/pages/shared/TellusReport.tsx`

Copy `client/src/pages/shared/AnonymousReport.tsx` structure (validating / form / submitting /
submitted stages, honeypot field, `${VITE_API_URL ?? '/api'}` bare `fetch`). Adds:
- Category picker + positive/negative **sentiment** toggle.
- A **media upload** control (`components/ui/FileUpload.tsx`) that calls `/tellus/{token}/media/presign`
  then PUTs to S3 with a progress bar.

Admin QR panel reuses `qrcode.react` `QRCodeSVG` like `IRAnonymousReportingPanel.tsx`.

---

## 9. Suggested phasing

1. Migration + `tellus_*` tables + feature flag.
2. Public intake (`/tellus/{token}` GET/POST) + business router + report dashboard (text only).
3. Media (presign endpoint + storage helper + upload UI + playback).
4. Standalone product wiring (signup, tier, sidebars, checkout, webhook, pricing).
5. Embeddable `/app/tellus` + AI sentiment + IR promotion.

---

## 10. Critical files

- **Data/intake:** `server/alembic/versions/tellus01_*.py`, `server/app/database.py`,
  `server/app/matcha/routes/inbound_email.py`, `server/app/core/services/storage.py`
- **Business router:** `server/app/matcha/routes/tellus.py`, `server/app/matcha/routes/__init__.py`;
  reuse `server/app/matcha/routes/ir_incidents/_shared.py` (`create_incident_core`) &
  `.../anonymous_reporting.py` (link mgmt)
- **Product wiring:** `server/app/core/feature_flags.py`, `server/app/core/routes/auth.py`,
  `server/app/core/routes/resources.py`, `server/app/core/services/stripe_service.py`,
  `server/app/core/routes/stripe_webhook.py`
- **Frontend:** `client/src/utils/tier.ts`, `client/src/components/TenantSidebar.tsx`,
  `client/src/components/ir-only/TellusSidebar.tsx`, `client/src/components/ClientSidebar.tsx`,
  `client/src/pages/auth/TellusSignup.tsx`, `client/src/pages/shared/TellusReport.tsx`,
  `client/src/pages/app/Tellus.tsx`, `client/src/App.tsx`

---

## 11. Verification

- **Migration:** apply on **dev only** (`./scripts/migrate-dev.sh`) after user approval; confirm
  `alembic_version` and the `tellus_*` tables exist. Never touch prod DDL without explicit approval.
- **Public intake e2e:** mint a link in the business panel -> open `/t/:token` -> submit a text report
  -> confirm a `tellus_reports` row appears in the dashboard. Attach a photo and a video -> confirm
  `tellus_report_media` rows + presigned playback works.
- **Product flip:** register via `/tellus/signup` -> confirm `TellusPendingSidebar` (tellus off) ->
  run Stripe test checkout -> webhook flips `tellus=true` -> `TellusSidebar` appears.
- **Embedded:** on a full-Matcha company toggle `tellus` on -> `/app/tellus` renders behind `<FeatureGate>`.
- **Promotion:** submit a `safety` report on a company with `incidents` -> promote -> confirm the
  `ir_incidents` row and `promoted_incident_id` linkage.
- **Backend checks:** `cd server && ./venv/bin/python -m pytest tests/ -q` for anything added; the
  post-edit hook runs `py_compile` automatically. Use only RFC 2606 reserved test-data domains.
