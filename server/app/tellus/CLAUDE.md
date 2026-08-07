# Tell-Us backend

Rewards-for-feedback app. Own product, mirrors Cappe's shape — not a matcha tenant. See root `CLAUDE.md`'s "Repo layout — products map" for where this fits; this file covers specifics of `server/app/tellus/`.

## Identity & boundary

- Own identity model: `tellus_accounts` (consumer + brand), JWT `scope=tellus`. Not `users`/`companies`.
- Mounted at `/api/tellus`.
- **Import rule**: `tellus/` imports only from `app/core/*`, with **one documented exception** — `tellus/services/geo.py` reuses `matcha.services.property.property_cat.geocode` (single US Census geocoder; keep that function's signature stable, since tellus depends on it). Verified 2026-07-27: `tellus → matcha` is exactly that 1 edge. Don't add a second without updating the root CLAUDE.md count.

## Layout

- `routes/` — `auth.py`, `billing.py`, `community.py` (public brand review page, `/b/{slug}`), `dms.py` (brand↔reporter DMs, any identified feedback — not review-scoped), `feedback.py`, `gamification.py`, `grants.py`, `links.py`, `marketplace.py`, `my_reviews.py` (consumer "My Reviews"), `public_intake.py`, `rewards.py`, `_shared.py`
- `routes/admin/` — internal admin package (see "Internal admin management" below), gated by `require_tellus_admin` at the router level in every sub-router
- `services/` — `auth.py`, `email.py`, `feedback_service.py`, `geo.py` (the matcha import lives here), `google_places.py` (Google Places API (New) client — autocomplete + place details, server-proxied), `marketplace_service.py`, `points_service.py`, `admin_audit.py`
- `models/tellus.py` — Pydantic shapes; `models/admin.py` — internal admin request/response shapes

## Internal admin management

`routes/admin/` (package, split 2026-08-06 from a single `admin.py` that started as just the changelog) — 27 endpoints across 6 sub-routers, every one gated by `require_tellus_admin` (`TELLUS_ADMIN_EMAILS` allowlist, fail-closed when empty — `dependencies.py:_is_tellus_admin`). Pinned by a gate-sweep test (`tests/tellus/test_admin_management.py::TestAdminGateSweep`) that walks `routes/admin/router.routes` and asserts the dependency on every one, so a future sub-router can't ship ungated.

- **`accounts.py`** — list/search/detail, suspend/unsuspend (`tellus_accounts.status`, CHECK'd to `active|suspended` since `tellus_app_08`, previously never written after INSERT), force sign-out (`tokens_valid_after = NOW()`, same write self-logout uses), verify-email, password-reset link mint (Tell-Us had no reset flow before — `tellus_password_reset_tokens` + public `POST /auth/reset-password` consume in `routes/auth.py`, 1h expiry, single-use, revokes all sessions), manual points adjust.
- **`brands.py`** — list/search/detail, plan comp/cancel (`tellus_brands.plan_status` — previously writable ONLY by the Stripe webhook; these endpoints never call Stripe, cancel-with-a-live-subscription returns a `stripe_warning` instead of touching Stripe), assign-owner (first-ever writer of `tellus_brands.claimed_at`, which existed since `tellus_app_06` but was dead schema — flips a consumer account to `account_type='brand'` if needed).
- **`moderation.py`** — cross-brand review moderation queue (the gap `feedback.py`'s own docstring flags: brand-side moderation of its own reviews can look like suppressing a review it doesn't like) + DM thread oversight (view messages read-only, block/unblock — admin unblock can override a consumer's own block, no `blocked_by` column to distinguish who set it).
- **`economy.py`** — config editors for `tellus_earning_rules` (had no UI before this), `tellus_badge_definitions`, `tellus_reward_listings` (force activate/deactivate).
- **`audit.py`** + **`services/admin_audit.py`** — `tellus_admin_audit` table, `record_admin_action()` called inside the SAME transaction as every mutation above (so an audit row never exists for a rolled-back write). asyncpg returns the `detail` JSONB column as a raw string without a registered codec — always decode via `routes/admin/_shared.py:decode_audit_rows()` before constructing `TellusAdminAuditEntry`, never inline (a 500 from skipping this is how the accounts/brands detail endpoints broke during manual verification — fixed, but easy to reintroduce on a new endpoint). Frontend viewer: `client/tellus/src/pages/admin/Audit.tsx` (filters on action/target_type/target_id); the same-shaped rows on `AccountDetail.tsx`/`BrandDetail.tsx` render through the shared `pages/admin/AuditList.tsx`.
- **`services/points_service.py:adjust_points`/`compute_adjustment`** — manual credit/clawback, `reason='adjustment'` (declared in the ledger CHECK since `tellus_app_01`, unused until this). Unlike `redeem`, a clawback reduces `lifetime_points` too (floored at 0), so `level` can drop; badges are never revoked. Overdraw raises `AdjustError` (409) unless the caller passes `clamp=True`.
- **Ledger idempotency is `ON CONFLICT ... DO NOTHING RETURNING id`, not a caught `UniqueViolationError`.** Both `award_points` and `adjust_points` insert into `tellus_points_ledger` under the partial unique index `ux_tellus_ledger_idem` (`account_id, reason, reference_id` WHERE `reference_id IS NOT NULL`, `tellus_app_01`). `adjust_points` is routinely called inside an already-open transaction (`routes/admin/accounts.py`'s `points-adjust` endpoint), which makes its own `conn.transaction()` a SAVEPOINT — a caught `UniqueViolationError` there leaves the savepoint aborted and the whole request 500s instead of returning `adjusted: false`. `adjust_points` also pre-checks the ledger before taking the `FOR UPDATE` balance lock, so a replayed `idempotency_key` never touches it. If you add another ledger-writing path, follow this shape, not the exception-catching one.

Full design + endpoint-by-endpoint SQL: `TELLUS_ADMIN_MGMT_PLAN.md` at the repo root.

## Places / reviews on unclaimed businesses

- **Invariant: every unclaimed brand (`tellus_brands.owner_account_id IS NULL`) has an
  active `tellus_links` row.** The only write path into `tellus_reports` is
  `POST /i/{token}` (`routes/public_intake.py`), keyed solely on a link token — an
  unclaimed brand with no active link is permanently un-reviewable. Enforced by
  `routes/places.py:ensure_community_link()` (mints the always-on "Community feedback"
  link + `tellus_link_history` row when none is active). Every code path that creates,
  exposes, or un-claims a brand calls it: `create_place`'s dedupe branch (a
  `POST /places` hit on an existing brand whose link got revoked), the fresh-insert
  path, and `routes/admin/brands.py:unassign_owner`. Add a call there if you add
  another such path.
- **Google Places autocomplete** (`services/google_places.py`) — server-proxied
  (`GOOGLE_MAPS_API_KEY` never reaches the browser); unset ⇒ every function returns
  `None`/`[]` and the add-a-place form silently degrades to manual free-text entry, no
  errors surfaced anywhere. `GET /places/autocomplete` is Redis-cached 5 min per
  normalized query and rate-limited same as the rest of `places.py`.
- **Dedupe order in `create_place`**: `google_place_id` match first
  (`ux_tellus_brands_google_place_id`, a partial unique index — NULLs exempt), then the
  pre-existing name+city advisory-lock match, then a fresh insert. Google Place Details
  are always re-resolved **server-side** from the `place_id` — the client-submitted
  name/city are only the fallback when that lookup fails, never trusted directly for a
  `google_place_id` submission (a squatter could otherwise pair a real place_id with a
  fake name).
- **ToS note (decided)**: `place_id` is stored indefinitely (Google explicitly permits
  this); resolved name/address/lat/lng are stored as part of the consumer's own
  submission despite Google's 30-day cache guidance for raw autocomplete results —
  accepted, these are facts the user selected, not a cached search index.
- **Self-serve claim** (`routes/community.py:claim_brand`, `POST /b/{slug}/claim`) —
  "Is this your business?" on the public page. Mirrors admin `assign_owner`
  (`routes/admin/brands.py`) minus the admin gate/audit: links `owner_account_id` +
  `claimed_at`, flips `account_type` consumer→brand if needed, same one-brand-per-
  account guard (`require_tellus_account`'s `LEFT JOIN tellus_brands` assumes it holds).
  **Does not touch `plan_status`** — a claimed `consumer_added` brand stays `'pending'`,
  so `require_paid_brand` keeps 402ing every dashboard surface until the caller runs the
  existing Stripe checkout (`routes/billing.py`). Payment is the verification bar, not
  identity proof; admin `unassign_owner` is the recourse for a bad-faith claim.
- **`tellus_reports.publish_at` may only ever move earlier, never later.** The 48h hold
  (`services/feedback_service.py:create_report`) exists so a brand can't delay or
  suppress a review; the only UPDATE site is `routes/feedback.py:publish_review_now`
  (`POST /feedback/{id}/publish-now`, guarded by the pure `can_publish_now` helper —
  held + still in the future only). Anything that could push `publish_at` later would
  reopen the suppression hole the hold closed — don't add one.

## Frontend pairing

Paired frontend is a separate Vite app at `client/tellus/` (React 19), served by the same nginx at `/tellus/`. No dedicated CLAUDE.md there yet — see root CLAUDE.md's repo-layout table.

## Cross-cutting rules

DB safety rules, test-data email domain rules, and deploy rules are in root `CLAUDE.md` — they apply here unchanged, not restated.
