# Tell-Us backend

Rewards-for-feedback app. Own product, mirrors Cappe's shape — not a matcha tenant. See root `CLAUDE.md`'s "Repo layout — products map" for where this fits; this file covers specifics of `server/app/tellus/`.

## Identity & boundary

- Own identity model: `tellus_accounts` (consumer + brand), JWT `scope=tellus`. Not `users`/`companies`.
- Mounted at `/api/tellus`.
- **Import rule**: `tellus/` imports only from `app/core/*`, with **one documented exception** — `tellus/services/geo.py` reuses `matcha.services.property.property_cat.geocode` (single US Census geocoder; keep that function's signature stable, since tellus depends on it). Verified 2026-07-27: `tellus → matcha` is exactly that 1 edge. Don't add a second without updating the root CLAUDE.md count.

## Layout

- `routes/` — `auth.py`, `billing.py`, `board.py` (Regulars board — see "Regulars board" below), `community.py` (public brand review page, `/b/{slug}`), `dms.py` (brand↔reporter DMs, any identified feedback — not review-scoped), `feedback.py`, `gamification.py`, `grants.py`, `likes.py`, `links.py`, `marketplace.py`, `my_reviews.py` (consumer "My Reviews"), `places.py`, `promo.py` (brand campaign/scanner CRUD + consumer card reads — see "Promo campaigns" below), `promo_public.py` (token-auth claim + scanner redeem, no bearer), `public_intake.py`, `rewards.py`, `_shared.py`
- `routes/admin/` — internal admin package (see "Internal admin management" below), gated by `require_tellus_admin` at the router level in every sub-router
- `services/` — `auth.py`, `board_service.py` (Regulars board shared logic), `email.py`, `feedback_service.py`, `geo.py` (the matcha import lives here), `google_places.py` (Google Places API (New) client — autocomplete + place details, server-proxied), `likes_service.py`, `marketplace_service.py`, `points_service.py`, `promo_service.py` (promo campaigns / QR reward cards), `admin_audit.py`
- `models/tellus.py` — Pydantic shapes; `models/admin.py` — internal admin request/response shapes; `models/promo.py` — promo campaign/card/scanner shapes
- **Managed S3 objects**: `_shared.py:is_managed_object(url, prefix)` / `delete_managed_object(url)` are the shared "only delete what we uploaded" pair (a legacy free-text URL may point somewhere we don't own). Used by `links.py` (`/tellus/logos/`) and `promo.py` (`/tellus/promo/`) — add the prefix constant next to your route, don't re-privatize the helpers.

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

## Regulars board

Per-brand channel (`routes/board.py`, `services/board_service.py`, `tellus_app_12`/`tellus_app_13` migrations) — brand posts updates/deals/events/questions, approved consumer members reply (pre-moderated), a brand can add a consumer-typed team moderator.

- **Every `owner_account_id` writer must also insert a `tellus_brand_members` owner row.** Call sites patched for this in the same PR: brand signup (`routes/auth.py`), `routes/admin/brands.py:assign_owner`, `routes/admin/claims.py:approve_claim`, plus a one-time backfill in `tellus_app_12`. Both `board_service.py:resolve_moderated_brand` and `routes/board.py:get_board` carry an explicit owner-fallback (`member row missing → role='owner'` / `viewer_is_mod = ... or brand.owner_account_id == account.id`) for a row that slips through anyway — don't remove either fallback, and don't treat it as license to skip the INSERT at a new ownership-flip call site.
- **One brand per owner** — partial unique index on `tellus_brands.owner_account_id` (`tellus_app_12`). `routes/board.py:resolve_moderated_brand`'s LEFT JOIN over `tellus_brand_members` depends on this staying true.
- **`tellus_reward_listings.visibility='board'`** excludes a listing from the city marketplace; redeemable only by an approved member of an active (`is_active`), non-paused-plan (`plan_status='active'`) board (`services/points_service.py:redeem_points`) — the same three-way gate `create_post`'s deal-listing check and the public `has_board` flag use, so a lapsed/paused brand goes fully dark on redemption too, not just on new posts.
- **Boards are born paused.** `board_service.py:ensure_board` (called from GET endpoints too, since a page view lazily creates the row) inserts `is_active=FALSE` — a mere view must never flip the public `/b/{slug}` join CTA on. The owner explicitly publishes via `PATCH /board/manage {is_active: true}`.
- **Reply transitions**: `board_service.py:can_reply_transition` (pure, `held→approved`/`held→rejected`/`approved→removed` only) is THE matrix for the three brand-moderator routes (`approve_reply`/`reject_reply`/`remove_reply`) — each fetches current status and checks the predicate before its UPDATE. The admin force path (`routes/admin/moderation.py:admin_force_reply_status`) deliberately bypasses it — it can move `rejected`/`removed`→`approved` to overturn a bad brand call, which the matrix forbids by design; it still can't double-award points, since `approve_reply_and_award`'s `ON CONFLICT DO NOTHING` ledger insert is idempotent either way.
- **Membership statuses**: `pending`/`approved` are guarded by partial unique indexes + the savepoint-then-INSERT pattern in `request_join` (a genuine UniqueViolationError race falls back to a 409, never a 500 on the aborted outer txn). `declined`/`removed` permanently block a fresh `POST /b/{slug}/board/join` (409 "The brand has declined this request.") — don't loosen this without a product decision, it's what stops re-request spam on the moderator team's notifications. `left`/`cancelled` (self-service via `POST /me/board-memberships/{id}/cancel`) do NOT block — the account chose to leave, it may rejoin.
- **Notification fan-out** (`services/board_service.py:notify_board_members`/`notify_board_team`) is `INSERT INTO tellus_notifications (...) SELECT ... FROM ...` — inside an INSERT...SELECT, asyncpg/Postgres can fail to infer parameter types from the SELECT's target list alone, so every text parameter is explicitly cast (`$2::text` etc.). Don't drop the casts "to simplify" — that reintroduces `could not determine data type of parameter $2` on every join/reply/post notification.

## Google sign-in

`POST /auth/google` (`routes/auth.py`, `tellus_app_14`) — verifies an ID token via the shared `app/core/services/google_identity.py:verify_google_id_token` (also used by matcha core's `/api/auth/google`; audience allowlist is `settings.google_allowed_audiences`, fails closed when empty), then either links `google_sub` onto an existing account matched by email or creates a new one.

- **Google-created accounts are always `account_type='consumer'`** — a brand needs `brand_name`/`location_count`/Stripe, none of which a Google token carries. An *existing* brand account still links and signs in normally.
- **`password_hash IS NULL` is the Google-only marker** — deliberately not a random unusable hash (unlike matcha core's version). `login()` checks this before attempting `verify_password_async` and returns a distinguishable 401 ("uses Google sign-in") rather than 500ing on `None.encode(...)`. Never backfill a real hash onto a Google-only row without also clearing `google_sub`, or the account becomes reachable by both paths with divergent state.
- **Every new-account insert path must also write `tellus_points_balances`** — same invariant `signup()`'s consumer branch follows (`routes/auth.py:150-154`).
- Linking sets `email_verified_at = COALESCE(email_verified_at, NOW())` — Google has already proven control of the address, so this also clears a stuck unverified password signup. **If the matched account was never verified, linking also nulls `password_hash` and bumps `tokens_valid_after`** — an unverified password was never proven to belong to that address, so an attacker who pre-registered someone else's email could otherwise log in by password the moment the real owner's Google proof lands. An already-verified account's password is left untouched.

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
  (`GOOGLE_MAPS_API_KEY` never reaches the browser). `autocomplete()` returns `None` when
  unset/failed vs `[]` for a genuine zero-result search — `GET /places/autocomplete` only
  `cache_set`s the latter (5 min, Redis, per normalized query), so a transient Google
  outage doesn't poison the cache; either way the add-a-place form silently degrades to
  manual free-text entry, no errors surfaced to the user. Both `autocomplete()` and
  `place_details()` accept a Places API (New) `sessionToken` (`?st=` query param → route →
  service) so one autocomplete-then-select flow bills as one session, not a call per
  keystroke plus a separate Details call.
- **Dedupe order in `create_place`**: the advisory lock
  (`pg_advisory_xact_lock(hashtextextended(lower(name)||'|'||lower(city)))`) is acquired
  **before** any dedupe SELECT, then `google_place_id` match first
  (`ux_tellus_brands_google_place_id`, a partial unique index — NULLs exempt), then the
  pre-existing name+city match, then a fresh insert. Google Place Details are always
  re-resolved **server-side** from the `place_id` — `verified_place_id` (Google's own echo
  from `place_details()`) is the ONLY place_id ever written to `tellus_brands`/
  `tellus_stores`; a client-submitted `google_place_id` that fails to resolve is discarded,
  never persisted anywhere — a squatter cannot pair a real place_id with a fake name/brand
  by racing a Google outage.
- **ToS note (decided)**: `place_id` is stored indefinitely (Google explicitly permits
  this); resolved name/address/lat/lng are stored as part of the consumer's own
  submission despite Google's 30-day cache guidance for raw autocomplete results —
  accepted, these are facts the user selected, not a cached search index.
- **Self-serve claim, approval queue** (`routes/community.py:claim_brand`,
  `POST /b/{slug}/claim`) — "Is this your business?" on the public page. Files a
  **PENDING** row in `tellus_brand_claims` (partial-unique on `brand_id`/`account_id`
  WHERE `status='pending'` — one pending claim per brand and per account, race-safe at
  the DB) and does **not** touch `owner_account_id`/`account_type`. An admin must
  approve via `routes/admin/claims.py:approve_claim` before ownership actually flips —
  that endpoint re-checks eligibility (brand still unowned, claimant still brandless) and
  auto-rejects if it drifted, then runs the same ownership-flip logic `assign_owner`
  (`routes/admin/brands.py`) always has. `POST /admin/claims/{id}/reject` declines with an
  optional `decision_note` (claimant-visible via `GET /me/claim`). Every decision writes
  `tellus_admin_audit` (`brand.claim_requested`/`claim_approve`/`claim_reject`) and
  notifies the claimant. **Does not touch `plan_status`** — an approved `consumer_added`
  brand stays `'pending'`, so `require_paid_brand` keeps 402ing every dashboard surface
  until the caller runs the existing Stripe checkout (`routes/billing.py`). Self-serve
  undo: `GET /me/claim` (latest non-cancelled claim) + `POST /me/claim/cancel` — cancels a
  pending claim outright, or reverses an approved-but-unpaid one (mirrors
  `unassign_owner`); an approved+paid claim requires support. `unassign_owner` itself also
  cancels any dangling `approved` claim row on the brand it unassigns, so `GET /me/claim`
  never shows a ghost approval for an account that no longer owns anything.
- **`tellus_reports.publish_at` may only ever move earlier, never later.** The 48h hold
  (`services/feedback_service.py:create_report`) exists so a brand can't delay or
  suppress a review; the only UPDATE site is `routes/feedback.py:publish_review_now`
  (`POST /feedback/{id}/publish-now`, guarded by the pure `can_publish_now` helper —
  held + still in the future only). Anything that could push `publish_at` later would
  reopen the suppression hole the hold closed — don't add one. Every early publish also
  stamps `published_early_at`/`published_early_by` (distinct from `publish_at` itself) so
  an early publish stays distinguishable from a normal hold expiry in a later dispute —
  the reviewer's edit window (`my_reviews.py:update_my_review` permits edits while held)
  was cut short by brand action, not by time.
- **Public rating is a rolling 12-month window** (`routes/community.py:public_brand_page`) —
  `review_count`/`avg_rating` only ever aggregate reviews published in the last 12 months, so
  old reviews stop permanently haunting a business. The default review list (`scope=recent`,
  the default query param) matches that window; `scope=older` returns everything before it,
  with its own `older_count`-driven pagination — the public page renders this behind a "Show
  N older reviews" toggle, never mixed into the headline rating. `routes/places.py:search_places`
  applies the same 12-month cutoff to its `review_count` subquery so search-result counts match
  the brand page. The brand's own dashboard (`feedback.py`) is intentionally unfiltered — brands
  always see full history, only the public-facing rating rolls.
- **Brand logo is upload-only** — `POST /brand/logo` (`routes/links.py`, multipart, PNG/JPEG/WebP,
  2MB cap) writes to the **public** S3 bucket via `storage.upload_file` (CloudFront URL), because
  `logo_url` renders on the unauthenticated `/b/{slug}` page where a presigned/private URL would
  rot. `TellusBrandUpdate` no longer accepts `logo_url` — the old free-text field routinely pointed
  at URLs that didn't render; this is the only writer now.
- **Reward expiry is per-listing** — `tellus_reward_listings.expiry_days` (default 30, `tellus_app_11`)
  is stamped onto `tellus_redemptions.expires_at` at redeem time (`services/points_service.py:
  redeem_points`). Status is derived at read time via `services/marketplace_service.py:
  effective_redemption_status` (same pattern as `effective_review_state`) — an `'issued'` row past
  its `expires_at` reads as `'expired'` with no cron involved; terminal states (`redeemed`/
  `cancelled`) never flip. The brand's counter-verification endpoint
  (`routes/marketplace.py:verify_redemption`) 409s on an attempt to mark an expired code
  `'redeemed'`.

## Likes

Pure counter on four targets — `tellus_board_posts`, `tellus_board_replies`, `tellus_reports`
(published reviews), `tellus_reward_listings`. **No points, no notifications, no earning rule.**
`routes/likes.py` + `services/likes_service.py` + migration `tellus_app_15_likes.py`.

- **Strictly disjoint from the brand heart.** `tellus_reports.hearted_at/hearted_by`
  (`feedback.py`, `require_paid_brand`) is a *brand* acknowledging a review — one bit on the row.
  A like is a *consumer* action in its own table. Brands are 403'd from liking reports and
  listings precisely so the two can't blur; `TellusReport` therefore carries `like_count` but
  deliberately **no** `liked_by_me`. A test pins that `routes/likes.py` never mentions `hearted_*`.
- **Four nullable FK columns, not polymorphic `(target_type, target_id)`.** `delete_own_reply`
  (`board.py`) **hard-deletes** a held reply, and Tell-Us has no orphan-sweep cron — a polymorphic
  table would silently accumulate orphaned likes. All four FKs plus `account_id` are
  `ON DELETE CASCADE`, so there is no cleanup code anywhere. A `CHECK
  (num_nonnulls(...) = 1)` keeps exactly one target set. Don't "simplify" this to polymorphic.
- **`ON CONFLICT DO NOTHING` with no inference spec** — the four unique indexes are *partial*
  (`WHERE <col> IS NOT NULL`), which an explicit `ON CONFLICT (col, account_id)` fails to match.
  Never catch `UniqueViolationError` here instead (same reason as the ledger-idempotency note above).
- **The count is a second statement inside the same transaction, never a data-modifying CTE.**
  `WITH ins AS (INSERT … RETURNING 1) SELECT COUNT(*) …` shares one snapshot with the CTE and
  returns a count **stale by one**. Both facts are pinned by source-guard tests.
- **Unlike is self-scoped and pause-exempt.** `DELETE … WHERE account_id = $1 AND <col> = $2` can
  only touch the caller's own row, so it does no target authorization at all — and it deliberately
  skips the paused-board 409 that `like` gets, or a like would get trapped on content that later
  went paused/invisible. Unliking something never liked is a 200 no-op, not a 404.
- **Reads count at query time** (`COUNT(*)` subqueries / one batched `hydrate_likes` per page),
  matching the existing `approved_reply_count` pattern — no denormalized `like_count` column, no
  triggers. `hydrate_likes`' column name comes from the module-level `_TARGET_COLUMNS` dict,
  never a request value; the `LikeTargetType` `Literal` on the path param makes an unknown target
  a 422 before any code runs.
- `community.py`'s public `/b/{slug}` is unauthenticated but needs `liked_by_me`, so it uses
  `dependencies.optional_consumer_account_id` (hoisted out of `public_intake.py`, which still
  uses it). On the web the page fetches via `tellusMaybeAuthGet`, **not** `tellusPublicGet` —
  the latter never attaches the bearer, so `liked_by_me` would always read false.

## Promo campaigns / QR reward cards

A brand mints a campaign with a global claim cap (`tellus_promo_campaigns`), a consumer scanning
the flyer QR claims exactly one single-use card (`tellus_promo_cards`), and staff redeem it at the
counter through a per-store device token (`tellus_scanner_devices`). Migration `tellus_app_16`.
Routers: `promo.py` (brand CRUD + `/me/promo-cards`), `promo_public.py` (`/p/{claim_token}`,
`/scan/{device_token}`). Web surfaces: `pages/Claim.tsx`, `pages/Scan.tsx`,
`pages/consumer/CardView.tsx`. The Konva flyer designer (`design_json`) is authored but has no UI
yet — `TELLUS_PROMO_CAMPAIGNS_PLAN.md` §6 is the spec.

- **Deliberately separate from the points economy.** Free cards never touch
  `tellus_points_ledger`/`tellus_points_balances`. `claim_count` is a monotone *issuance* counter —
  expiry and cancellation never decrement it (unlike `reclaim_expired_redemptions`' quantity
  restore, which would be wrong here: a claimed-then-expired card still consumed a print run).
- **Claim ordering is load-bearing.** In `claim_card` the card INSERT (`ON CONFLICT DO NOTHING`)
  happens *before* the cap UPDATE, and the cap UPDATE's WHERE re-checks status/window/`claim_count`
  under the campaign row's lock — so a raced dedup never double-counts the cap, and a cap miss
  rolls the card insert back through the enclosing transaction. The lock is `FOR UPDATE OF c`, not
  bare `FOR UPDATE`: the query joins `tellus_brands` for `plan_status`, and locking that row would
  serialize every campaign belonging to the same brand.
- **Redeem is one UPDATE carrying every predicate** (issued, unexpired, right brand, campaign not
  cancelled). The second scanner to reach an already-redeemed card blocks on the row lock, then
  fails the predicate — double-redeem is structurally impossible, not merely unlikely. The
  diagnostic re-query that follows is scoped to the scanner's own `brand_id` and returns the same
  404 as an unknown token, so a scanner can't probe for another brand's card tokens.
- **Idempotency is a pre-check (SELECT before INSERT), never a caught `UniqueViolationError`** —
  same rule as `points_service.adjust_points`; these run inside an already-open transaction where a
  caught error leaves the enclosing SAVEPOINT aborted.
- **`plan_status='active'` is checked on BOTH claim and redeem.** It originally guarded only
  `resolve_scanner`, so a lapsed brand kept issuing cards that 410'd at the counter — every card
  issued after the lapse was dead paper. `claim_reason` now returns `brand_inactive` (ordered right
  after `cancelled`, which is the more specific fact) and both `resolve_claim_preview` and
  `claim_card` join `tellus_brands` for it. An *already-claimed* card still replays fine — that
  early return sits above the `claim_reason` call on purpose.
- **`design_json` is `json.dumps`/`json.loads`'d at the callsite.** No asyncpg JSON codec is
  registered on this pool, so binding a dict to the JSONB param raises `DataError` and reading the
  column back yields a *string*, not an object. `save_design` takes pre-serialized text and binds
  `$3::jsonb`; `get_campaign_design` decodes. Exactly the trap `tellus_admin_audit.detail` has —
  see `routes/admin/_shared.py:decode_audit_rows`. Don't "fix" this by registering a pool-level
  codec: every existing JSONB reader in this app assumes the raw-string behaviour and would
  double-decode.
- **`update_campaign` builds its SET clause from `model_fields_set`**, not `COALESCE` — under
  COALESCE an explicit `{"ends_at": null}` was silently ignored, so a date could never be cleared
  once set. Column names come from the module-level `_PATCH_COLUMNS` whitelist, never request text
  (same guard shape as `likes_service`'s `_TARGET_COLUMNS`); `_NULLABLE_PATCH_COLUMNS` is what
  distinguishes "clear it" from "no-op" for the NOT NULL columns. A cancelled campaign is
  un-editable (pre-check *and* `status <> 'cancelled'` in the WHERE) — otherwise its already-
  invalidated cards would render freshly-edited `reward_text`, which `_CARD_SELECT_SQL` reads live
  off the campaign row.
- **`upload_flyer` verifies ownership BEFORE writing to S3.** It used to upload first, so a 404 on
  a foreign `campaign_id` left an orphaned object in the *public* bucket with nothing ever deleting
  it — loopable. The ownership pre-check gets its own short connection (never hold a pool
  connection across the S3 round-trip), and a late `set_flyer_url` failure deletes the object it
  just uploaded.
- **Claim rate limits are deliberately loose.** `max_claims` (up to 10,000) plus the
  `ux_tellus_promo_cards_one_per_account` unique index are the real ceilings; the limiter only
  stops a stampede. The per-IP hourly cap is 100, not 20, because the flyer's whole point is a
  shared-WiFi/CGNAT crowd — a cafe, an event — claiming from one egress IP.

## Frontend pairing

Paired frontend is a separate Vite app at `client/tellus/` (React 19), served by the same nginx at `/tellus/`. No dedicated CLAUDE.md there yet — see root CLAUDE.md's repo-layout table.

`ApiError` (`client/tellus/src/api/tellusClient.ts`) carries `.status`, `.code?` and `.detail?`,
populated from the backend's structured `{detail: {code, message, ...extra}}` body — the public
helpers (`tellusPublicGet`/`Post`, `tellusMaybeAuthGet`/`Post`) throw it too, not a bare `Error`.
`Scan.tsx` depends on this to tell `already_redeemed` (and its `redeemed_at`/`redeemed_store_name`
extras) apart from `expired`/`cancelled`/`not_found`; a `.message` string can't be pattern-matched.

## Cross-cutting rules

DB safety rules, test-data email domain rules, and deploy rules are in root `CLAUDE.md` — they apply here unchanged, not restated.
