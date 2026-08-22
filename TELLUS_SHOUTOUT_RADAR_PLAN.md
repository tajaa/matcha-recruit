# Tell-Us — Brand Shoutout Radar

## Context

PR #229 shipped `tellus_loyalty_social_submissions` — consumer-initiated: poster pastes their own
post URL, brand approves, `award_event(event_key="social_post")` credits loyalty points. Brand-side
review UI was never built (dead API bindings in `client/tellus/src/api/loyalty.ts:40-45`).

This feature is the inverse: **find people already shouting the brand out, and buy their next
coffee.** Daily Gemini-grounded scan → brand-facing digest → approve → single-use store-bound
reward link → business pastes it into their own DM/comment reply → poster installs the app, signs
up, redeems at the counter. Detection is lead-gen; the link is the acquisition hook.

Two independently-designed halves (scan/detection, offer/claim) are reconciled below into one
buildable spec. Nothing in either half is built yet.

## Locked decisions

| Question | Decision |
|---|---|
| Detection | Gemini Google-Search grounding only. Provider seam for SerpAPI/IG Graph later. |
| Delivery | Copy-link, business pastes manually. No DM automation. |
| Claim gate | One-time link, app install + signup — **gated behind a setting, default OFF** (see App Store constraint). |
| Approval | Business approves every mention. Nothing auto-awards. |
| First PR | Backend + web brand UI. iOS consumer claim path is MVP (see below — it's cheap and it's the point). iOS brand-side inbox is phase 2. |
| PR #229 queue | Folded into the same page, as a clearly separate "Customer submissions" section (different reward mechanism — points vs. offer link — never merged into one list). |

### App Store constraint — load-bearing

iOS app is **TestFlight-only**; no public listing URL exists anywhere in the repo, `Landing.tsx` has
no download link. Install gate ships behind `tellus_shoutout_configs`-level setting, default off:
claim falls back to the existing web-signup bounce (`Claim.tsx`'s `returnTo` pattern) until the
listing is live. AASA/entitlements/universal-links still get built now (cheap, and needed the moment
the listing goes live) — see §5.

## Reconciliation notes (read before building)

Two planning agents designed the two halves independently and used different names/capabilities.
This is the merged, authoritative naming:

- **Migration order**: `tellus_app_31` = scan/detection tables (owns `tellus_shoutout_mentions`).
  `tellus_app_32` = offer tables (`down_revision = "tellus_app_31"`), because its FK targets
  `tellus_shoutout_mentions(id)` and must come after.
- **Mention table name**: `tellus_shoutout_mentions` (not `tellus_social_mentions` — that name was
  a placeholder in the offer-half brief, not a real design).
- **Capability**: `require_brand_capability("promos.manage")` everywhere in this feature (config,
  mentions, offers) — it already exists in `BrandCapability` / `ROLE_CAPABILITIES`
  (`server/app/tellus/models/access.py:23`, `client/tellus/src/api/types.ts:12`), granted to
  owner/admin/location_manager. No capability-list changes needed. (One planner proposed reusing
  `rewards.manage` instead — don't; `promos.manage` is the semantically correct one and needs zero
  schema/list edits either way, so there's no tradeoff to weigh.)
- **Status vocabulary on `tellus_shoutout_mentions.status`**: `pending | approved | rejected | expired`.
  Offer minting sets it to `approved` (not a separate `offer_sent` value — keep one status enum, the
  offer row itself is what tracks `sent/claimed/revoked`).
- **Column contract into the offer half**: `decided_at`, `decided_by`, `offer_id`. Pin these before
  either side starts coding — it's the one hard interface between the two PRs.

## Verified groundwork

- Brand pages `client/tellus/src/pages/brand/`; nav is a flat `BRAND_NAV` array in `Layout.tsx`
  (~line 100), no tabs; brand-scoped pages needing `account.brand_id` in the path (Loyalty, and now
  Shoutouts) are spliced in at runtime.
- `require_brand_capability(capability, paid=True)` — `server/app/tellus/dependencies.py:211`; `paid=True` 402s a lapsed brand.
- Locations = `tellus_stores`, hard-deleted on removal (`routes/links.py:321`) — any FK to a store
  must be `ON DELETE SET NULL`, never `RESTRICT`/CASCADE. `ux_tellus_stores_id_brand ON (id, brand_id)`
  exists for composite-FK ownership proofs.
- No brand social-handle column exists anywhere — net-new storage (`tellus_shoutout_handles`).
- `canonicalize_social_url(platform, raw_url)` (`loyalty_service.py:130`) — HTTPS + per-platform host
  allowlist. Every URL surfaced by this feature goes through it.
- Promo/claim machinery (`tellus_promo_campaigns`/`tellus_promo_cards`/`tellus_scanner_devices`,
  migration `tellus_app_16`, service `promo_service.py`) is the right thing to build the offer on top
  of — see §4. Radius/geo checks are gated strictly on `campaign_type == 'location'`
  (`promo_service.py:439,585,639,690`), so a `campaign_type='shoutout'` campaign with `store_id` set
  gets store binding with **no** proximity requirement — correct, the poster claims from home.
  `ux_tellus_promo_cards_one_per_account` (one card per account per campaign) is why offers must be
  **per-mention campaigns**, not one shared campaign.
- iOS consumer claim path **already exists in full**: `ClaimSheet.swift` + `PromoClaimViewModel.swift`
  + `PromoService.swift` + `CardDetailView.swift`, wired through `DeepLinkRoute` and
  `AppState.deferredDeepLink` (which already replays a route once the user reaches `.consumer` post-
  signup — exactly the "tapped link while logged out" case). This is the single biggest reuse win and
  is why iOS consumer support is MVP, not phase 2.
- iOS `project.pbxproj` is **generated by XcodeGen**, not hand-edited — `project.yml` globs whole
  source directories. New files: drop under `Models/`/`Services/`/`ViewModels/`/`Views/`, run
  `make generate`, commit the regenerated pbxproj. Entitlements are the one exception (authored files,
  `project.yml` explicitly avoids overwriting them so the APNs key survives).
- A live latent bug, unrelated but touched by this feature's "fold PR #229 in" decision:
  `loyalty_service.py:756`'s `submit_social_post` uses `ON CONFLICT (brand_id, canonical_url) DO NOTHING`
  against an index that migration `tellus_app_30` (authored, unapplied) makes **partial**
  (`WHERE status <> 'withdrawn'`). Postgres can't infer a partial index without a matching predicate
  in the ON CONFLICT clause → `42P10` on every submission once `tellus_app_30` lands. **Fix: drop the
  inference spec entirely** — bare `ON CONFLICT DO NOTHING` (same fix `likes_service` already uses,
  and it's the only unique constraint on that table besides the PK, so it's unambiguous). One-line
  change, ships in this PR since we're activating that endpoint's UI for the first time.

---

## Part A — Detection (backend)

### Schema — `tellus_app_31_shoutout_radar.py`

Four tables, `down_revision = "tellus_app_30"`:

- **`tellus_shoutout_handles`** — `brand_id, platform, handle` (no leading `@`, lowercased),
  `is_active`. `UNIQUE (brand_id, platform, handle)`.
- **`tellus_shoutout_configs`** (1:1, PK `brand_id`) — `is_enabled`, `brand_terms TEXT[]`,
  `exclude_terms TEXT[]`, `default_store_id` (FK `(id,brand_id)→tellus_stores`, `ON DELETE SET NULL`),
  `offer_title`, `offer_terms`, `offer_expiry_days`, `min_confidence`, `lookback_days`,
  `last_scanned_at`, `next_scan_after`, `consecutive_failures`. `CHECK (NOT is_enabled OR
  (default_store_id IS NOT NULL AND offer_title IS NOT NULL))` — can't arm a money-spending scan
  with nowhere to bind the reward.
- **`tellus_shoutout_scan_runs`** — per-run bookkeeping: `status`, `trigger`, counters
  (`gemini_calls`, `grounding_uris`, `grounding_resolved`, `candidates_returned`, `urls_rejected`,
  `mentions_new`, `mentions_duplicate`), `error`. `UNIQUE (brand_id) WHERE status='running'` — makes
  concurrent runs for one brand structurally impossible; a crashed worker leaves a wedged row, so the
  worker reclaims stale `running` rows older than 1h on every cycle.
- **`tellus_shoutout_mentions`** — the queue. `brand_id`, `platform`, `post_url`, `canonical_url`,
  `url_fingerprint CHAR(64)` (sha256 over a *stricter-than-canonical* key so `/p/`, `/reel/`,
  `?img_index=`, `twitter.com`/`x.com`, `youtu.be`/`/watch?v=` all collapse to one row), `author_handle`,
  `excerpt`, `confidence SMALLINT`, `matched_terms TEXT[]`, `corroborated BOOLEAN`, `grounding_uri`,
  `url_verify_status`, `raw_payload JSONB` (json.dumps at callsite, `$n::jsonb` bind — no codec
  registered on this pool), `status` (`pending|approved|rejected|expired`), `decided_at`, `decided_by`,
  `offer_id`, `offer_store_id`, `consumer_submission_id` (cross-reference to
  `tellus_loyalty_social_submissions`, no behavioral coupling — just "a customer already claimed
  points for this post" context). **`UNIQUE (brand_id, url_fingerprint)`, non-partial** — the dedupe
  key. Re-detection is a two-statement upsert (`INSERT … ON CONFLICT DO NOTHING RETURNING id`, else
  `UPDATE … SET seen_count=seen_count+1, confidence=GREATEST(...)` with **no `status` in the SET
  list**) — this is what guarantees a rejected/approved mention never reappears on tomorrow's scan.

Seed `scheduler_settings` row `tellus_shoutout_scan`, `enabled=false`.

### Scan service — `server/app/tellus/services/shoutout/`

`provider.py` (a `MentionProvider` Protocol + `GeminiGroundingProvider` — the SerpAPI/IG-Graph seam),
`prompt.py`, `grounding.py` (URL resolution), `scan_service.py`, `review_service.py`, `config_service.py`.

**Gemini call** — canonical shape from `legal_research.py:544-560`: `get_rate_limiter().check_limit()`
once before the loop → `get_genai_client().aio.models.generate_content(model=GEMINI_FLASH, tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.0)` under `asyncio.wait_for(timeout=90)` →
`record_call()` in a `finally:` (flyer_ai discipline — a timed-out call is still billed). No
`response_mime_type`/`response_schema` — the API rejects structured output combined with the search
tool, which is why every grounded caller in this repo asks for JSON in-prompt instead. Guard
`response.text is None` (safety-blocked/pure-tool-call turns).

Two calls per brand per day max: one over handles, one over brand terms + city/state disambiguation.

**Anti-hallucination gate — the part that must not be skipped.** Nothing in this repo currently reads
`response.candidates[0].grounding_metadata` (zero hits, verified) — every existing grounded caller
trusts model-emitted URLs in JSON, which hallucinates. For a feature whose entire output is "here is
a real post URL," that's unacceptable. Three-stage funnel:

1. Read real grounding-chunk URIs from `grounding_metadata.grounding_chunks[].web.uri` (`getattr(...,
   None) or []` at every hop — untyped SDK surface, one `AttributeError` here kills a brand's run).
2. Resolve the one-hop redirect (`follow_redirects=False`, read the `Location` header — never fetch
   the actual Instagram/TikTok page, which would either login-wall or get the scanner blocked).
3. **Keep a model-emitted candidate only if its canonicalized URL's fingerprint matches something
   Google Search actually returned in this same response.** Anything else — including a fallback path
   that promotes a bare grounding chunk when `mentions` comes back empty — is capped at confidence ≤40
   (below the default `min_confidence=60`) rather than trusted.

Confidence scoring is a pure function: hard zero if the post is the brand's own handle (checked
locally, never trusted from the model — the #1 false-positive class); +20 only if a `matched` term is
actually a substring of the excerpt (the model *asserting* a match isn't evidence); + recency, +
corroboration, + a capped fraction of the model's self-reported confidence.

**Spend caps, layered** (`@worker_ready` re-fires every ~15min with no celery-beat, so without these
the scan runs ~96×/day): `scheduler_settings.enabled=false` seed → `scheduler_enabled(..., default=False)`
re-check in the task → atomic global `last_run_at` claim (6h interval) → atomic per-brand
`next_scan_after` claim (20h interval, backing off on `consecutive_failures`) → `max_per_cycle` brand
cap → hard per-cycle Gemini-call budget → per-brand call cap → the global `GeminiRateLimiter` ceiling.
`due_brand_ids` also filters `plan_status='active'` so a lapsed brand stops costing money the day it
lapses.

**Expected recall — state it plainly, design the API around it.** Google's index of Instagram/TikTok
posts is thin by the platforms' own choice; X and YouTube index well. A brand may see 0–2 Instagram
hits a week even with real activity. Consequences baked into the design, not left as a surprise:
`ShoutoutConfigOut.platform_coverage: dict[platform, "good"|"partial"|"poor"]` labels this at
*setup* time; the run-history endpoint exposes the four-stage counters so an empty queue reads as "14
successful runs, 0 candidates" (a real, explainable answer) instead of looking like a broken feature;
and this is positioned as *additive* to the PR #229 consumer-submission queue, not a replacement.

### Worker — `server/app/workers/tasks/tellus_shoutout_scan.py`

Tell-Us's first Celery task (it has zero today). Four registration edits: add to `include=[...]` in
`celery_app.py`; add `("tellus_shoutout_scan", "app.workers.tasks.tellus_shoutout_scan",
"run_tellus_shoutout_scan")` to `_SCHEDULED_TASKS`; the migration's `scheduler_settings` seed row;
the task module. Shape copied from `coi_expiry.py` (async `_dispatch` + thin sync `@celery_app.task`
wrapper, `max_retries=0` — a retry re-spends Gemini on possibly-half-done work; the next daily cycle
picks up what this one dropped, same reasoning as `vertical_coverage_sweep`). Workers are pool-free —
`get_db_connection()` per brand, never held across the ~180s of Gemini + HTTP work for one brand. One
brand's exception is caught, logged to its scan run, and the cycle continues.

### Endpoints — `server/app/tellus/routes/shoutouts.py`

All `Depends(require_brand_capability("promos.manage"))`. Config CRUD (`GET/PUT
.../shoutouts/config`, `POST .../config/enable`), queue (`GET .../shoutouts/mentions`, `POST
.../mentions/{id}/approve` → the seam into Part B, `POST .../mentions/{id}/reject`), run history
(`GET .../shoutouts/runs`). No brand-facing "scan now" button in MVP — unmetered spend risk on a
grounded model; an admin-only debug endpoint (`POST /admin/shoutouts/{brand_id}/scan`, gated by the
existing `require_tellus_admin` router-level dependency, audited) is the only manual trigger.

**The handoff seam, exactly:** `approve_mention` in `review_service.py` — after locking the pending
mention row `FOR UPDATE`, it calls one function it doesn't own:

```python
async def mint_offer(conn, *, brand_id, store_id, mention_id, title, terms,
                     expiry_days, client_request_id, created_by) -> dict:
    """Returns {"id","claim_token","claim_url","store_id","title","expires_at","status"}.
    MUST be idempotent on (brand_id, client_request_id). MUST NOT open its own
    conn.transaction() — it runs inside the caller's, which is a SAVEPOINT."""
```

If that module isn't present, `approve_mention` returns a clean `503 offers_unavailable` — Part A is
independently testable and mergeable before Part B lands.

---

## Part B — Offer, claim, and client surfaces

### Data model — one campaign per offer, not a standalone table

`tellus_promo_campaigns` gets a third `campaign_type` value, `'shoutout'` (CHECK widened via
DROP+ADD, not a rewrite — table's tiny). A new `tellus_shoutout_offers` lifecycle table
(`tellus_app_32`, `down_revision = "tellus_app_31"`) sits alongside it: `brand_id`, `mention_id` (FK
→ `tellus_shoutout_mentions`), `campaign_id`, `store_id` (`ON DELETE SET NULL` — stores are
hard-deleted), `offer_token` (pasted-link entropy, `secrets.token_urlsafe(12)`), `short_code` (8-char
Crockford base32 minus `ILOU`, the type-it-in fallback — defended by rate limits + single-use, not
secrecy), `reward_text`, `status` (`sent|claimed|revoked`), `claim_expires_at`,
`claimed_account_id/at`, `card_token`, `created_by`. `UNIQUE (mention_id) WHERE status <> 'revoked'`
— one live offer per mention, re-sendable after revoke.

**Why per-mention campaigns, not a shared one or a standalone claim table:** the entire card
wallet/redeem/scanner stack is keyed on `tellus_promo_cards.campaign_id NOT NULL` end-to-end (web
CardView, iOS CardDetailView, `/scan/{device_token}` redeem, `_CARD_SELECT_SQL`) — reusing it costs
one extra campaign row and buys back single-use (`max_claims=1`), claim window (`ends_at`), revoke
(`promo_service.cancel_campaign`, already a hardened one-way door), lapsed-brand checks on both
claim and redeem, and card expiry, all with **zero changes to `promo_service.py`'s core
transactions.** A shared campaign is ruled out by `ux_tellus_promo_cards_one_per_account` — it would
cap a repeat shouter at one free coffee ever.

`promo_service.list_campaigns` gets one added filter, `campaign_type <> 'shoutout'`, so offers don't
flood the brand's real Campaigns page.

**Store binding is enforced at redeem**, not just recorded: `redeem_card`'s UPDATE WHERE gains `AND
(campaign_type <> 'shoutout' OR store_id IS NULL OR store_id = $scanner_store)`; `map_redeem_failure`
gains a `wrong_store` branch, placed *below* the existing redeemed/cancelled/expired checks and gated
strictly to `campaign_type='shoutout'` so a location-campaign's legitimate cross-store redeem doesn't
regress. `store_id IS NULL` degrades gracefully to brand-wide if the store was later deleted.

### Endpoints

Brand side, appended pattern to `shoutouts.py`: `POST .../mentions/{id}/offer` (mint, called from
`approve_mention`'s seam — same endpoint conceptually, the "approve" IS "send offer"), `GET
.../shoutouts/offers`, `POST .../offers/{id}/revoke`.

Public side, appended to `promo_public.py` (already scoped as "token-auth claim, no bearer" — this
belongs there): `GET /o/{offer_token}` (preview, `optional_consumer_account_id`), `POST
/o/{offer_token}/claim` (`require_consumer` — the 401 here is what drives the signup bounce), `POST
/o/code/{short_code}/claim`. Rate limits tighter than the flyer's `/p/{token}` (120/60 shared-WiFi
crowd reasoning doesn't apply — a shoutout link is one person): 5/60 + 30/3600 per IP on claim,
3/60 + 20/3600 per IP on code-claim (the guessable surface). Inherits `promo_service.claim_card`'s
transaction **unchanged** — card-insert-before-cap-update, `FOR UPDATE OF c`, idempotent replay —
just resolves `campaign_id` from the offer/code first.

### Install-then-claim flow — honest design, no magic

**Link**: `https://hey-matcha.com/tellus/o/{offer_token}`, minted server-side via a new
`tellus_web_url()` helper hoisted out of `services/email.py`'s existing `_base_url()` (don't derive it
client-side from `window.location.origin` — a brand on `www.` or localhost would paste a broken link).

**Landing page** (`client/tellus/src/pages/Offer.tsx`, public route `/o/:token`, no auth, no
`<Layout>`): designed for **in-app browsers**, since Instagram/TikTok open links in their own WebView
and mostly ignore Universal Links — the page must be self-sufficient, never a redirector. Primary CTA
is an App Store button (falls back to TestFlight link until public); below it, the short code in
monospace with a copy button and "after signup, tap Redeem a code and paste this"; a real `<a href>`
(not JS nav) for "already have the app, tap here"; QR code for desktop; Android gets an honest
"iPhone-only right now."

**Deferred deep linking — the actually-hard part, answered honestly:** a Safari tap → App Store →
install → first launch carries zero payload on iOS. No solution exists without a paid attribution SDK
(excluded by requirement) or an App Clip (its own AASA block, separate target — not worth it here).
MVP ships three non-magic paths: **(1) short code**, deterministic, entered via `PasteButton` (not an
auto clipboard read — that triggers an iOS 16+ permission prompt) right after signup or anytime via
Consumer → More → "Redeem a reward code"; **(2) re-tap the same link post-install**, which silently
works because `AppState.deferredDeepLink` already replays the held route once the user reaches
`.consumer` — this is free, it already exists; **(3) localStorage stash + "resume your offer"** on a
same-browser return visit, weak but three lines. Email capture (auto-attach on verified-email match)
is flagged explicitly as phase 2, not MVP — it puts an email wall in front of the App Store button,
which is exactly where an acquisition funnel leaks.

**AASA**: `client/public/.well-known/apple-app-site-association` (extensionless JSON, checked in),
served at the apex `hey-matcha.com/.well-known/...` — same host serves `/api` and `/tellus/`, so one
file covers both; nginx needs an explicit `location =` block forcing `application/json` (no
extensionless mime mapping exists otherwise) and the Dockerfile must be checked to actually copy the
dot-directory into the built image. **Real risk, not hypothetical**: hey-matcha.com sits behind
CloudFront + an origin-gate snippet — if that blocks `/.well-known/*` from Apple's CDN specifically,
Universal Links silently never work with no error anywhere. Verify with `curl` from outside AWS before
calling this done.

**Entitlement**: `com.apple.developer.associated-domains: ["applinks:hey-matcha.com",
"applinks:www.hey-matcha.com"]` in both `TellUs.entitlements` and `TellUs-Release.entitlements` (direct
edits — the one exception to XcodeGen ownership). **Blocking prerequisite**: enable Associated Domains
on the `com.beetlejuse.app` App ID in the Apple Developer portal and regenerate the pinned
`Beetlejuse_App_Store.mobileprovision` — Release signing is `Manual` against that file, so a stale
profile fails `make release-dry` with a capability mismatch.

**iOS handling**: `.onContinueUserActivity(NSUserActivityTypeBrowsingWeb)` in `TellUsApp.swift`
alongside the existing Google Sign-In `.onOpenURL`; `DeepLinkRoute` gets a `.shoutoutOffer(token:)`
case and a pure `parse(url:)`; `AppState` gets `handleUniversalLink(_:)` which reuses the existing
push-notification route-presentation logic (extracted into `present(_:)`) — and therefore
automatically gets the deferred-deep-link replay for free. New: `OfferClaimSheet` (near-clone of
`ClaimSheet`, adds store name), `RedeemCodeView` (paste-button + text field), one `ShoutoutOfferViewModel`.

### Web surfaces

`client/tellus/src/pages/brand/Shoutouts.tsx`, route `/brand/:brandId/shoutouts`, gated
`<BusinessCapabilityProtected capability="promos.manage">`, spliced into `BRAND_NAV` next to Loyalty
(needs `brand_id` in path, same as that entry). Three `<Card>` sections copying `RepliesSection`'s
shape from `Board.tsx:172-204` (per-row `busyId`, scoped refetch, `<Chip>` counts):

1. **Detected mentions** — platform/handle/excerpt/link, *Send offer* (opens a modal: store select,
   reward text, expiry) / *Dismiss*.
2. **Offers sent** — the claim link + copy button + short code + optional QR (copying `CampaignCard`
   in `Campaigns.tsx:112+`), status chip, *Revoke*.
3. **Customer submissions** — finally wires the dead PR #229 `loyaltyApi.listSocialQueue` /
   `approveSocial` / `rejectSocial`. Kept visually distinct from section 1 — approving here awards
   loyalty points, approving a mention mints an offer link; different mechanisms, must never be
   presented as the same action.

New `client/tellus/src/api/socialMentions.ts` (`socialMentionsApi` const object, the `api/loyalty.ts`
convention), types appended to the flat `api/types.ts`. `Claim.tsx` is untouched; `Offer.tsx` is new
and separate since its UX (no claim button, App Store CTA instead) is fundamentally different.

---

## Tests

Backend, `server/tests/tellus/`:
- `test_shoutout_fingerprint.py` — URL variants collapsing to one fingerprint (pure).
- `test_shoutout_grounding.py` — the hallucination gate: a model URL absent from resolved grounding
  chunks is dropped and counted in `urls_rejected`; missing-attribute SDK shapes don't raise;
  `response.text is None` is guarded.
- `test_shoutout_scoring.py` — brand's-own-handle scores zero; excerpt-must-contain-matched-term.
- `test_shoutout_service.py` — reseen-mention update never touches `status`; `next_scan_after` is
  stamped before any provider call (a failed scan still burns the interval); no caught
  `UniqueViolationError` anywhere in the package.
- `test_shoutout_routes.py` — every route requires `promos.manage`; every input model
  `extra="forbid"`; `approve` requires a `client_request_id`.
- `test_shoutout_worker.py` — task module is in `celery_app.conf.include`; scheduler gate defaults
  closed; one brand's failure doesn't abort the cycle; zero retries.
- `test_shoutout_offers.py` — minted campaign has `max_claims=1`/`campaign_type='shoutout'`/non-null
  `store_id`/non-null `ends_at`; `list_campaigns` excludes `shoutout` rows; `map_redeem_failure`'s
  `wrong_store` branch fires only for shoutout campaigns and sits below the pre-existing branches.
- Amend `test_loyalty_service.py`: source guard pinning `submit_social_post`'s bare `ON CONFLICT DO
  NOTHING` (the drive-by fix).

iOS, `platforms/ios/TellUs/Tests/` (XCTest): `DeepLinkURLParsingTests` (offer/promo/friend paths,
`/api/*` rejected, unknown paths → nil), `ShoutoutOfferModelDecodeTests`, `RedeemCodeNormalizationTests`.

`client/tellus/` has no test infrastructure (no vitest/jest) — web verification is typecheck + build
+ manual script, not automated tests. Don't add a test runner in this PR.

## Verification

```bash
# backend
cd server && ./venv/bin/python -m pytest tests/tellus/ -q
cd server && ./venv/bin/alembic heads                     # must print exactly one head
MIGRATE_REHEARSAL=1 DATABASE_URL=<dev> ./venv/bin/alembic upgrade heads   # rehearse, then rolls back

# web
cd client/tellus && npx tsc -b && npm run build
ls -la dist/.well-known/apple-app-site-association         # proves the dot-dir actually got copied

# iOS
cd platforms/ios/TellUs && make generate && make build && make test && make release-dry

# universal link, post-deploy
curl -sSI https://hey-matcha.com/.well-known/apple-app-site-association   # 200, application/json, no redirect
```

Manual end-to-end on localhost (`./scripts/dev-remote.sh` — frontend already runs on :5174, never
`pkill -f "vite --port"`, track your own throwaway process by PID):

1. Paid brand + store → `/brand/:id/shoutouts` → add a handle → trigger admin scan → confirm rows
   appear and every `post_url` actually opens in a browser (the recall/precision read).
2. *Send offer* → copy `/o/{token}` link.
3. Open in a private window, sign up fresh, land on the app-install page (web-fallback mode) or
   simulator-open the link and claim through the app.
4. Redeem at `/scan/{device_token}` bound to the offer's store; confirm a second scanner on a
   *different* store 409s `wrong_store`.
5. Re-run the scan; confirm the offered/dismissed posts don't reappear.
6. Confirm the shoutout campaign is absent from `/brand/campaigns` and fired zero follower-push
   notifications.

Never run `alembic upgrade` against prod directly — `./scripts/migrate-prod.sh` only, explicit
approval required.

## Risks

1. **Recall is the actual product bet**, not an engineering detail — Instagram/TikTok may return
   near-zero for months since Google's index of them is shallow by platform design. Mitigated by
   `platform_coverage` labeling at setup time and run-history counters making an empty queue
   explainable rather than silent; the honest escalation path if this matters is IG Graph mention
   webhooks (requires the brand to connect a Business account) — the provider seam exists for it.
2. **Claim links are off-brand.** `hey-matcha.com/tellus/o/...` is a different company's domain in
   the poster's first impression of the product. Worth a real domain (Cappe already has its own
   apex) before this reaches real customers.
3. **AASA behind CloudFront/origin-gate** could silently break Universal Links with zero error
   surfaced anywhere — verify with `curl` from outside AWS, not just from the office network.
4. **Provisioning-profile drift** the moment Associated Domains is added to the App ID — `make
   release-dry` before merge is the check, not optional.
5. **Negative mentions.** The scan surfaces complaints as readily as praise — this is exactly why
   auto-send was rejected in favor of manual approval; don't weaken that later for convenience.
6. **In-app-browser Universal Link unreliability** is the reason the landing page is designed as
   self-sufficient rather than a redirector — don't "simplify" it into a bare redirect later.
7. **Fraud surface**: a `location_manager` with `promos.manage` can mint offers to friends. Cheap
   mitigation already in the DDL (`created_by` rendered as "sent by" in the offers list) — not an
   audit table, `tellus_admin_audit` is admin-scope only.

## Cut list, if this needs to be smaller

Drop, in order: iOS brand-side inbox (already deferred); the QR code on the brand's offer card (link
is pasted into a DM, not printed); the `X-TellUs-Client` app-only header gate (spoofable, and forces
an iOS change for a UI-only funnel concern); `open_count`/`first_opened_at` analytics; folding in the
PR #229 queue (ship it as a fast follow-up instead — same page, one more Card); the term-search
Gemini call (handles-only halves detection cost and is higher-precision anyway); config knobs for
`exclude_terms`/`min_confidence`/`lookback_days` (ship as constants). Do not cut: the grounding-chunk
corroboration gate, the `url_fingerprint` unique index, the atomic `next_scan_after` claim, or
`enabled=false` in the scheduler seed — those four are the difference between a feature and an
incident.
