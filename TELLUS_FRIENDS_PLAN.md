# Tell-Us Friends — social graph for iOS

## Context

Tell-Us has ~27 migrations of consumer surface (reviews, points, boards, follows, promo cards) and **zero consumer↔consumer edges**. Every social act today points at a *business*: you follow a brand, join its board, review its store. Two consumers who both use the app are invisible to each other except as a `display_name` string on the city leaderboard.

This adds the missing half: find and add friends, then see the places they review and the places they follow. It ships iOS-first (`platforms/ios/TellUs/`), but every endpoint lands on the shared backend (`server/app/tellus/`) so the web app (`client/tellus/`) can adopt it later without a rewrite.

**Decisions taken (locked):**
1. **Mutual friendship** — request → accept, symmetric once accepted. Not one-way follow.
2. **Discovery** — invite link/QR + a new unique `@handle` + derived suggestions. **No contacts sync.**
3. **Profile shows** — their published reviews, places they follow, points/level/badges, boards they've joined.
4. **v1 stops at** friends + profile + activity feed. **No** friend-to-friend DM, **no** friend badges on Discover.

**The one genuinely new privacy exposure:** reviews are already public on `/b/{slug}`, so a friend feed leaks nothing there. But *who you follow* and *which boards you joined* are private today. Both ship behind a visibility setting that defaults to `friends`, never `everyone`.

---

## Reconciled contract (backend and iOS designs disagreed — these win)

| Item | Decision |
|---|---|
| Visibility enum | `everyone` / `friends` / `private` — **not** `nobody`. It is the DB CHECK; iOS mirrors it. |
| Visibility columns | **Two**: `profile_visibility` (governs reviews+follows+boards as one unit) + `discoverable` (gates search/suggestions only). No per-section toggles. Points/badges reuse the existing `leaderboard_opt_in`. |
| Profile path | `GET /people/{account_id}` and `GET /people/by-handle/{handle}` — not `/friends/{id}/profile`. Profiles are viewable by non-friends when `profile_visibility='everyone'`. |
| Hidden vs empty | Hidden sections serialize as **`null`**, not `[]` with a `*_hidden` flag. Swift Optional arrays: `nil` → "Private", `[]` → "None yet". |
| Feed pagination | **Keyset cursor** (`?cursor=`), not offset. Offset over a live merged feed skips and duplicates rows. |
| Handle claim | Dedicated `POST /me/handle` (needs 409-on-taken + a change cooldown). **Not** folded into `PATCH /me`. |
| `POST /friends/requests` | Returns the created `TellusFriendRequest` (201), so iOS gets a `request_id` and "Cancel" works immediately. |
| `accept` returns | `TellusFriendSummary` (the person row), so the hub inserts the new friend without a refetch. |
| Badge poll | `GET /me/friend-requests/count` — cheap. Not a full list fetch. |
| Invite share URL | `/tellus/f/{token}`. `/i/` and `/p/` are taken. |
| Feed kinds in v1 | **Two only**: `review_published`, `place_followed`. The iOS enum is forward-tolerant for more. |

---

## Part 1 — Backend

### 1.1 Migration `server/alembic/versions/tellus_app_28_friends.py`

`revision = "tellus_app_28"`, `down_revision = "tellus_app_27"` (current tellus head), bare assignments. **No `op.create_table`** — every tellus migration is raw idempotent DDL via `op.execute`, and constraints go through `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$`. Model on `tellus_app_18_brand_follows.py` and `tellus_app_12_regulars_board.py`.

**No `CREATE EXTENSION`.** This repo has never run one outside `vector` (`zzzzcappe25_directory.py` says so explicitly). That rules out `citext` and `pg_trgm`, which drives two design consequences: handle uniqueness is a `lower(handle)` unique index, and search is **prefix-only**.

**`tellus_accounts` additions:**
```sql
handle TEXT                     -- stored ALREADY-LOWERCASED by a Pydantic validator
handle_set_at TIMESTAMPTZ       -- drives the 30-day change cooldown
avatar_url TEXT                 -- column now, upload endpoint deferred (see 1.2)
profile_visibility TEXT NOT NULL DEFAULT 'friends'
discoverable BOOLEAN NOT NULL DEFAULT TRUE
```
+ `ck_tellus_accounts_profile_visibility CHECK (profile_visibility IN ('everyone','friends','private'))`
+ `ck_tellus_accounts_handle_format CHECK (handle IS NULL OR handle ~ '^[a-z0-9_]{3,20}$')`

**Tables** (full DDL in §1.3):
- `tellus_friendships` — **two mirrored rows per friendship**, PK `(account_id, friend_account_id)`. Not a canonical `(lo,hi)` row: the feed and every `is_friend` check then resolve as a single composite-PK lookup instead of an `OR` predicate. Symmetry is enforced by exactly one writer + one deleter and pinned by a source-guard test.
- `tellus_friend_requests` — `status IN ('pending','accepted','declined','cancelled')`, plus `pair_lo`/`pair_hi` generated columns so `ux_tellus_friend_requests_pending (pair_lo, pair_hi) WHERE status='pending'` allows at most **one live request per pair in either direction**.
- `tellus_account_blocks` — PK `(blocker, blocked)`, stored directionally, **enforced symmetrically** (every read asks "did they block me?", hence `ix_tellus_account_blocks_blocked`).
- `tellus_abuse_reports` — ⚠️ **NOT** `tellus_reports`, which already means *reviews*. Unique partial index on `(reporter, subject) WHERE status IN ('open','reviewing')` — deliberately not keyed on `target_id`, since NULLs compare distinct under UNIQUE and would let one reporter file unlimited account-level reports.
- `tellus_friend_invites` — one live token per account (`ux_..._active (account_id) WHERE revoked_at IS NULL`), token from `secrets.token_urlsafe(16)` per `promo_service.py`.

**The one new index on an existing table:**
```sql
CREATE INDEX IF NOT EXISTS ix_tellus_reports_author_published
  ON tellus_reports (reporter_account_id, publish_at DESC)
  WHERE review_state = 'held' AND moderation_status = 'visible';
```
Existing `ix_tellus_reports_public` is `(brand_id, publish_at DESC)` — wrong leading column for an author-ordered feed; `ix_tellus_reports_reporter` has no sort key and degenerates to a heap fetch + sort. `publish_at <= NOW()` cannot go in the predicate (not immutable) and stays in the WHERE.

**No new index on `tellus_brand_follows`** — `ix_tellus_brand_follows_consumer_created` from `tellus_app_18` is already the exact shape the feed's follow branch wants. Say so in the docstring so nobody adds a duplicate.

**Earning rule seed:**
```sql
INSERT INTO tellus_earning_rules (event_key, points, daily_cap, cooldown_seconds, is_active)
VALUES ('friend_added', 10, 50, NULL, TRUE) ON CONFLICT (event_key) DO NOTHING;
```
No engine change needed. Both sides awarded with `reason='earn_engagement'`, `reference_id = pair_key(a,b)` (**sorted UUID pair**) so unfriend → re-friend replays into `ux_tellus_ledger_idem` and awards nothing.

**Verify at author time:** generated columns need an immutable expression. Use the `CASE WHEN a < b THEN a ELSE b END` form, **not** `LEAST()/GREATEST()` on uuid (historically rejected). If `CASE` is also rejected on the target server, fall back to two plain columns written by the app + a source-guard test.

### 1.2 Privacy model — two columns, one truth table

| Surface | `private` | `friends` (default) | `everyone` |
|---|---|---|---|
| Reviews (author page) | self | self + friends | self + any signed-in consumer |
| Places they follow | self | self + friends | self + any signed-in consumer |
| Boards they've joined | self | self + friends | self + any signed-in consumer |
| Points / level / badges | governed by the **existing** `leaderboard_opt_in`, intersected with the row above |
| Handle, name, avatar, friend **count** | always visible to anyone who can resolve the profile |
| Friend **list** | never exposed in v1 |

Reasoning worth keeping:
- **`private` does not retract reviews from `/b/{slug}`.** It only governs the *aggregated author page*, which is the new thing (N scattered reviews → a behavioural profile). Retracting from the brand page would be the review-suppression mechanism the product deliberately refuses (`publish_at` may only ever move earlier). **Document this asymmetry or it reads as a bug.**
- **Points reuse `leaderboard_opt_in`** — someone who opted out of the city leaderboard already said "don't show my score to strangers". A second, differently-worded points toggle produces contradictory states.
- **`discoverable` is separate from the enum** because "public profile, findable only by invite link" is a real harassment-mitigation state. It gates search + suggestions only; `profile_visibility='private'` implies not-discoverable regardless.
- **Avatars: column now, initials in v1, upload endpoint deferred.** Tell-Us has zero image moderation; shipping avatar upload means the abuse queue immediately needs an image path. The column now avoids a second migration later.

`PATCH /me` (`routes/auth.py:421-434`, `TellusProfileUpdate` at `models/tellus.py:122-124`) gains `profile_visibility` + `discoverable`. Both are NOT NULL with defaults, so COALESCE's known "can't clear a field" limitation does not apply here — note it so nobody "fixes" it into `model_fields_set`.

### 1.3 Handle rules

- **Charset** `^[a-z0-9_]{3,20}$`. ASCII-only kills unicode-confusable impersonation for free. No dots or hyphens (hyphen collides with the `Member-xxxx` fallback shape).
- **Stored already-lowercased** by a Pydantic validator (`.strip().lower()` before the regex), so the DB never sees mixed case. No separate display-casing column — `Finch` vs `finch` is an impersonation vector.
- **Reserved** — a module-level `frozenset`: `admin, administrator, api, anonymous, billing, help, me, mod, moderator, null, official, root, security, staff, support, system, team, tellus, tellus_team, undefined, www, you`. Plus two **prefix** rules: anything starting `tellus` (product squatting), and anything starting `member` — **critical**, because `routes/gamification.py:57-65` renders nameless accounts as `Member-{id[:4]}`; without this rule someone claims `member_a1b2` and impersonates another account's anonymous fallback everywhere.
- **Optional.** Existing accounts have none and there is no sane backfill; auto-generating `user_a1b2c3` would burn the good names. Handle-less accounts remain fully friendable via invite link and suggestions, and remain `display_name`-prefix-searchable. iOS prompts to claim on first open of the Friends hub.
- **Changeable, max once per 30 days** against `handle_set_at`; 429 with a `retry_after_days` extra in the structured `{detail:{code,message,...}}` body (iOS `APIError.httpDetail` and web `ApiError.code` both read this). Old handles are not reserved after release in v1 — accepted risk, mitigated by the 30-day natural cooldown.
- `handle_set_at` is exposed on `TellusAccount` so iOS can render "You can change this again in N days".

**Search SQL — prefix-only, both branches indexed:**
```sql
WHERE a.account_type = 'consumer' AND a.status = 'active'
  AND a.discoverable AND a.profile_visibility <> 'private' AND a.id <> $1
  AND (a.handle LIKE $2 || '%' OR lower(a.display_name) LIKE $2 || '%')
  AND NOT EXISTS (<blocks, both directions>)
ORDER BY (a.handle = $2) DESC, length(COALESCE(a.handle, a.display_name)), a.created_at
```
`$2 = escape_like(q.strip().lower())` (`routes/_shared.py:75`). **`len(q) >= 2` is a 422.** Both indexes use `text_pattern_ops` — a default-collation btree will not serve `LIKE 'q%'` outside a C-locale DB. The `OR` resolves as a BitmapOr. `discoverable = false` hides you **even from an exact-handle search**; the invite link is the escape hatch — say so in the docstring so it doesn't get "fixed". Substring search is a v2 migration adding `pg_trgm` + a GIN index; do not smuggle it into `tellus_app_28`.

### 1.4 Endpoints — `server/app/tellus/routes/friends.py`

Bare `APIRouter()`, no prefix, full paths per decorator. **Every route uses `require_verified_consumer`** (the follow/Comms precedent) — there is no unauthenticated person surface at all in v1, which removes the scraping surface entirely.

| Method | Path | Notes |
|---|---|---|
| GET | `/friends/handle-available?handle=` | `{available, reason}`, `reason ∈ format/reserved/taken`. RL 60/3600 — it's a handle-enumeration oracle. |
| POST | `/me/handle` | 409 taken, 429 in cooldown. RL 5/86400. |
| PATCH | `/me` *(existing)* | +`profile_visibility`, +`discoverable` |
| GET | `/friends/search?q=&limit=` | RL 60/60 |
| GET | `/friends/suggestions?limit=` | RL 60/3600 |
| POST | `/friends/requests` | Body `{account_id? \| handle?, source}`. **Auto-accepts a reciprocal pending request** (mutual intent = friends) and returns 200 + friendship instead of 201. RL 30/3600 |
| POST | `/friends/requests/{id}/accept` | Addressee only → `TellusFriendSummary` |
| POST | `/friends/requests/{id}/decline` | Addressee only, 204. Starts the 30-day cooldown |
| POST | `/friends/requests/{id}/cancel` | Requester only, 204. **No** cooldown |
| GET | `/me/friend-requests?direction=` | |
| GET | `/me/friend-requests/count` | The tab-badge poll |
| GET | `/me/friends?q=&limit=&offset=` | Envelope `{entries, total, next_offset}` |
| DELETE | `/me/friends/{account_id}` | 204; no-op when not friends (self-scoped deletes never 404 — the unlike precedent) |
| GET | `/people/{account_id}` · `/people/by-handle/{handle}` | Sections gated by `visible_sections()`; hidden → `null` |
| GET | `/people/{account_id}/reviews?cursor=` | |
| GET | `/me/feed?cursor=&limit=` | RL 300/3600 |
| POST | `/people/{account_id}/report` | 202. RL 10/3600 |
| GET | `/me/friend-invite` · POST `/me/friend-invite/rotate` | Mint-or-return, idempotent |
| GET | `/friends/invite/{token}` · POST `/friends/invite/{token}/redeem` | |
| GET/POST/DELETE | `/me/blocks` | |
| GET | `/leaderboard/friends` *(in `routes/gamification.py`)* | Existing leaderboard query + a `tellus_friendships` join, city filter dropped. **`leaderboard_opt_in` still honoured.** |

**Blocked-either-direction returns 404, never 403** — a 403 confirms the account exists.

**Anti-spam rule, deliberately softer than boards.** `board_service.request_join` treats `declined`/`removed` as a *permanent* block. For friends that's wrong: no brand/consumer asymmetry, declines happen by accident, no undo. Here: `declined` blocks for **30 days** from `decided_at`; `cancelled` never blocks; an account block blocks forever. **This divergence must be written into `server/app/tellus/CLAUDE.md`** beside the existing note, or someone will harmonize it away.

**Invite redeem = auto-friend, no accept step** — a QR at a table has to work in one tap. Consent comes from the *redeemer's* explicit confirm on the `GET` preview ("Add @finch?"). The link bypasses `discoverable` (the owner consented by sharing it) but **never** bypasses a block. Unknown/revoked/expired/exhausted/blocked all return the same **404** so the token isn't an existence oracle. `use_count` increments under the invite row's `FOR UPDATE` in the same transaction as the friendship insert.

**Block is transactional and does four things at once:** insert the block row, delete **both** friendship rows, cancel pending requests in **either** direction, and leave `tellus_dm_threads.blocked_at` untouched (that's a different, thread-scoped mechanism — flag the collision for when friend DM lands).

### 1.5 The activity feed query

Two sources, **each independently limited before the merge** — that single fact is what keeps it bounded. Keyset on `(happened_at DESC, item_id DESC)`, not offset.

```sql
WITH friends AS (
    SELECT f.friend_account_id AS account_id
      FROM tellus_friendships f JOIN tellus_accounts a ON a.id = f.friend_account_id
     WHERE f.account_id = $1 AND a.status = 'active' AND a.account_type = 'consumer'
       AND NOT EXISTS (<blocks, both directions>)
),
reviews AS (
    SELECT 'review'::text AS kind, r.id AS item_id, r.reporter_account_id AS actor_id,
           r.publish_at AS happened_at, r.brand_id, r.rating, r.title, r.description AS body
      FROM tellus_reports r JOIN friends fr ON fr.account_id = r.reporter_account_id
     WHERE r.review_state = 'held' AND r.publish_at <= NOW() AND r.moderation_status = 'visible'
       AND r.publish_at >= NOW() - INTERVAL '90 days'
       AND ($2::timestamptz IS NULL OR (r.publish_at, r.id) < ($2::timestamptz, $3::uuid))
     ORDER BY r.publish_at DESC, r.id DESC LIMIT $4
),
follows AS (
    SELECT 'follow'::text, bf.brand_id, bf.consumer_account_id, bf.created_at, bf.brand_id,
           NULL::smallint, NULL::text, NULL::text
      FROM tellus_brand_follows bf
      JOIN friends fr ON fr.account_id = bf.consumer_account_id
      JOIN tellus_accounts fa ON fa.id = bf.consumer_account_id
     WHERE fa.profile_visibility <> 'private'
       AND bf.created_at >= NOW() - INTERVAL '90 days'
       AND ($2::timestamptz IS NULL OR (bf.created_at, bf.brand_id) < ($2::timestamptz, $3::uuid))
     ORDER BY bf.created_at DESC, bf.brand_id DESC LIMIT $4
)
SELECT * FROM (SELECT * FROM reviews UNION ALL SELECT * FROM follows) merged
 ORDER BY happened_at DESC, item_id DESC LIMIT $4
```
`$4 = limit + 1` — the extra row decides `has_more` without a COUNT.

- The three-clause public predicate is **copied verbatim** (it appears identically in `community.py`, `places.py`, `my_reviews.py`). A source-guard test pins all three clauses; dropping `moderation_status` would republish moderated-away reviews into every friend's feed.
- **Anonymous reviews are excluded structurally** — `reporter_account_id IS NULL` can never join `friends`. State this explicitly; it's the mechanism protecting anonymous feedback from de-anonymization.
- Indexes: `tellus_friendships` PK (friend set), `ix_tellus_account_blocks_blocked` + blocks PK (both block directions), **`ix_tellus_reports_author_published`** (new), `ix_tellus_brand_follows_consumer_created` (exists).
- **Known limitation, accepted and written down:** the two branches draw `item_id` from different domains (report id vs brand id), so the tiebreak isn't globally coherent *across* branches. Two events at the identical microsecond in different branches could theoretically skip or duplicate at a page boundary. Negligible at microsecond resolution with two independent writers.
- **Refactor trigger:** the moment a third activity source lands, this becomes a 5-way UNION with 5 sort merges. The right answer then is an append-only `tellus_activity_events (actor_account_id, kind, subject_type, subject_id, happened_at)` with one index. **Do not grow the UNION past three branches.**

**Hydration — 4 batched queries per page, constant in page size,** following `routes/my_reviews.py:_serialize_my_reviews` (lines 66-132) exactly. The feed query returns **bare ids only**; joining brands/media/likes inline multiplies rows (media is 1:N) and defeats the per-branch LIMIT.
1. Actors — `WHERE id = ANY($1::uuid[])`
2. Brands + primary store — the `LEFT JOIN LATERAL (... ORDER BY created_at LIMIT 1)` convention from `community.py:69-73`
3. Review media — `WHERE report_id = ANY($1::uuid[])`
4. `likes_service.hydrate_likes(conn, "report", ids, viewer_id)` — reused directly

Display name everywhere: `display_name or handle or f"Member-{str(id)[:4]}"` via one `display_name_for()` helper. **Never the email local-part** (`routes/gamification.py:57-65`).

### 1.6 `server/app/tellus/services/friends_service.py`

Split the way `board_service.py` splits: **pure predicates + shared multi-caller SQL in the service; HTTP status mapping, rate limits, and Pydantic construction in the router.**

Pure (no `conn`, directly unit-testable — the `can_reply_transition` analogue):
`HANDLE_RE`, `RESERVED_HANDLES`, `RESERVED_HANDLE_PREFIXES`, `normalize_handle`, `handle_rejection_reason`, `pair_key(a,b)` (THE ledger idempotency key), `can_request(latest_status, decided_at, now)` (the decline-cooldown matrix), **`visible_sections(*, is_self, is_friend, profile_visibility, leaderboard_opt_in) -> frozenset[str]`** (THE privacy truth table — one function, exhaustively tested, consulted by every profile/feed/leaderboard read; no route re-derives visibility inline), `encode_cursor`/`decode_cursor`, `display_name_for`.

Connection-taking: `friend_ids`, `relationship(conn, viewer, subject)` (one query, used by search + profile + request + redeem), `assert_not_blocked`, **`create_friendship`** (the only writer — both mirror rows `ON CONFLICT DO NOTHING`, both awards, both notifications, inside the caller's transaction), **`remove_friendship`** (the only deleter — one DELETE with the both-directions OR so the mirror can't be half-removed), `block_account`, `search_people`, `suggestions`, `activity_feed`, `hydrate_feed`, `profile_payload`, `mint_or_get_invite`, `redeem_invite`.

**Suggestions — all derived, no new tables:** friends-of-friends (2 hops, weight 3×mutuals) ∪ co-followers (≥2 shared brands, 2×) ∪ co-board-members (2×) ∪ same city (1×), `GROUP BY candidate ORDER BY SUM(weight) DESC`, with the same discoverable/block/already-friend/pending exclusions as search. Cache the id list in Redis 15 min per account (the `/places/autocomplete` `cache_set` precedent); hydrate fresh so a name change isn't stale.

### 1.7 Notifications + push

`tellus_notifications.kind` has **no CHECK** — new kinds need no migration. All three go through `points_service.notify_account(...)`, never a raw INSERT.

| kind | To | `reference_type` | `reference_id` |
|---|---|---|---|
| `friend_request` | addressee | `friend_request` | the **request** id |
| `friend_accepted` | requester | `account` | the **accepter's account** id |
| `friend_added` | invite owner | `account` | the **new friend's account** id |

`slug` carries the handle, `name` the display name, so the iOS destination screen has a title before the fetch lands. **That's the convention — write it into `tellus/CLAUDE.md`.**

⚠️ **`services/push.py:44-51 PUSH_KINDS` is a silent allowlist** — `schedule_push` returns without a word, a log, or an error for any kind not in it. Add all three, and update the enumerating comment above the set (it becomes wrong the moment friends lands).

**`friend_activity` deliberately does not exist.** A per-review fan-out to every friend would instantly be the loudest notification source in the app, and Tell-Us has no digest/batching infrastructure. The feed is **pull-only**. Write this down as a decision, not an omission.

### 1.8 Admin

**Extend `routes/admin/moderation.py`** — do not create a new sub-router. It already declares `APIRouter(dependencies=[Depends(require_tellus_admin)])`, is already wired into `routes/admin/__init__.py`, and is already swept by `TestAdminGateSweep`.

`GET /admin/abuse-reports`, `GET /admin/abuse-reports/{id}`, `PATCH /admin/abuse-reports/{id}`. Plus in `routes/admin/accounts.py`: `GET /admin/accounts/{id}/social` (read-only triage panel) and `POST /admin/accounts/{id}/clear-handle` (impersonation takedown).

Every mutation calls `record_admin_action(...)` **in the same transaction**. New actions: `abuse_report.review|action|dismiss`, `account.handle_clear`. **Two JSONB traps** (already broke the accounts/brands detail endpoints once): bind `detail` as pre-serialized text with `$3::jsonb`, and decode read-back audit rows through `routes/admin/_shared.py:decode_audit_rows()`.

### 1.9 Existing backend code that must **change**

| File | Change | Risk if missed |
|---|---|---|
| `services/push.py` (44-51) | 3 kinds + comment | **Silent** — zero pushes, no error, no log |
| `dependencies.py` (90-131) | `_load_account`'s SELECT **and** its `TellusAccount(...)` construction gain 5 columns | **Most likely miss.** The SELECT is an explicit column list (verified); every `Depends(require_*)` would return model defaults and `PATCH /me` would return a response contradicting the DB |
| `models/tellus.py` (76-124) | `TellusAccount` +5, `TellusProfileUpdate` +2, new Literals, ~12 new models | |
| `routes/auth.py` (421-434) | `PATCH /me` COALESCE UPDATE +2 params | Fields silently unwritable |
| `routes/__init__.py` (9-30, 60-65) | import + `include_router` under "Consumer-authenticated" | Every path 404s |
| `routes/gamification.py` | `/leaderboard/friends` | |
| `routes/admin/moderation.py`, `admin/accounts.py` | abuse queue + social panel | |
| `server/app/tellus/CLAUDE.md` | New "Friends" section; `routes/`+`services/` layout lists updated | Those lists are load-bearing docs |

### 1.10 Invariants in `tellus/CLAUDE.md` this risks violating

1. **`TellusPublicReview.reviewer_name` is "the ONLY identity field ever exposed publicly".** The feed needs `account_id`+`handle`+`avatar_url` on review rows — **do not extend `TellusPublicReview`**; add `TellusFriendFeedItem`/`TellusPersonSummary`. Extending it would start leaking account ids on the unauthenticated `/b/{slug}` page, a de-anonymization vector (`reporter_account_id` is nullable precisely because reviews can be anonymous).
2. **PII rule** — one `display_name_for()` helper, never the email local-part. The `member` reserved-prefix rule exists specifically to protect the `Member-xxxx` fallback from impersonation.
3. **Ledger idempotency is `ON CONFLICT DO NOTHING`, never a caught `UniqueViolationError`.** `create_friendship` awards two accounts inside one transaction; a caught unique violation there aborts the savepoint and 500s the request.
4. **`INSERT ... SELECT` needs explicit `$n::text` casts.** v1's notifications are single-row `notify_account` calls so it doesn't bite yet — it will the moment anything fans out.
5. **`tellus_reports.publish_at` may only move earlier.** Nothing in friends writes `tellus_reports`; assert that in review.
6. **Boards are born paused / the three-way gate.** "Boards they've joined" must filter `membership.status='approved' AND board.is_active AND brand.plan_status='active'` — the same gate `has_board` uses — or a profile leaks the existence of an unpublished or lapsed board.
7. **Board memberships block permanently on declined/removed; friends uses a 30-day cooldown.** Divergence must be documented.
8. **Import rule** — `friends_service.py` imports nothing from `matcha`; the documented `tellus → matcha` edge count stays at 1.

---

## Part 2 — iOS (`platforms/ios/TellUs/`)

**XcodeGen.** `project.yml` recursively globs `App/ Models/ Services/ ViewModels/ Views/ Resources/` and `Tests/`; `run.sh`/`Makefile` run `xcodegen generate` on every build. New files auto-add. **Never hand-edit `TellUs.xcodeproj/project.pbxproj`.** `project.yml` needs no change.

### 2.1 New files

**Models** — `Models/FriendModels.swift` (all shapes + a pure `enum FriendHandle` for normalize/validate/suggest).

**Services** — `Services/FriendsService.swift`, the `LikesService` singleton template (`static let shared`, `private let client = APIClient.shared`, `private init()`). ~18 methods. Query strings go through `PlacesService.queryString([URLQueryItem])`.

**ViewModels** — `Support/SectionLoadState.swift`, `Support/FriendsTab.swift`, `FriendsHubViewModel`, `FriendSearchViewModel`, `FriendProfileViewModel`, `FriendsFeedViewModel`, `FriendInviteViewModel`.

**Views/Consumer/Friends/** — `FriendsHubView`, `FriendsListSection`, `FriendRequestsSection`, `FriendFindSection`, `FriendRow`, `FriendProfileView`, `FriendActivityFeedView`, `FriendActivityRow`, `FriendInviteSheet`, `FriendInviteRedeemView`, `FriendReportSheet`.

**Views/Shared/** — `Avatar.swift`.

### 2.2 Generifying `TabLoadState` — a change to existing code with a zero-diff call-site guarantee

`TabLoadState` today is `phases: [BoardTab: LoadPhase]` and can't be reused. Extract the struct into `SectionLoadState<Tab: Hashable>` (bodies moved verbatim), keep `enum BoardTab` where it is, and add one line to `BoardTabLoadState.swift`:
```swift
typealias TabLoadState = SectionLoadState<BoardTab>
```
`BoardManageViewModel`, all five `Views/Brand/BoardManage/*.swift`, and **`Tests/BoardTabLoadStateTests.swift` compile untouched** — that unchanged test passing is the acceptance criterion for step 1.

### 2.3 Models — conventions that are not optional

- **snake_case property names verbatim, no `CodingKeys`, no `keyDecodingStrategy`.** Every file opens with a `// Mirrors server/app/tellus/models/tellus.py …` comment.
- Newer optional fields get a hand-written `init(from decoder:)` with `decodeIfPresent(...) ?? default` **plus an explicit memberwise init** (a custom `init(from:)` suppresses the synthesized one, and tests construct these directly).
- **`TellusAccount` is the exception** — verified never constructed in app or test code (`grep "TellusAccount("` → 0 hits), so its 5 new fields are plain Optionals on the synthesized decoder. No custom init, and the old-server case is free.
- `ProfileUpdate`'s new fields need **defaults** (`var profile_visibility: String? = nil`) so its one existing call site keeps compiling. Synthesized `Encodable` uses `encodeIfPresent`, so nil keys are omitted — which is what a PATCH needs.
- Open enums adopt `FallbackDecodable` with `case unknown` **last**: `FriendshipStatus` (none/pending_out/pending_in/friends/blocked/blocked_by), `FriendActivityKind`, `ProfileVisibility` (everyone/friends/**private**), `FriendReportReason`. `FriendRequestDirection` is closed, plain `Codable`. `ProfileVisibility` is `CaseIterable` for the settings Picker — **filter out `.unknown`**.
- `FriendProfile`'s four sections are **Optional arrays**: `nil` → "Private", `[]` → "None yet".
- `FriendSummary.status`/`request_id` are `var` so an optimistic send/accept flips a row in place (the `DiscoverEntry.followed` pattern). `display_name` decodes to `"Someone"` rather than throwing — a nulled name must not blank the whole list.

### 2.4 ViewModel patterns (all copied, none invented)

- `@MainActor @Observable final class`, `LoadableVM` + `withLoad { }`. Never `ObservableObject`.
- **Search** copies `DiscoverViewModel` exactly: `private var generation = 0` bumped per request and re-checked after every `await` to drop stale responses; `searchTask?.cancel()` + 450ms `Task.sleep` debounce; `query` with a `didSet` guard; `loadMore()` guarded on `nextOffset != nil && !isLoadingMore` and **swallowing errors silently** so a failed load-more never blanks the list. Gate at `>= 2` chars (empty query shows suggestions, not "nearby").
- **Optimistic mutation** copies `DiscoverViewModel.toggleFollow`: flip local state → call → on catch restore *at the original index* → `if !error.isCancellation { self.error = ... }`. A `busyIds: Set<String>` (not a Bool — two accepts can legitimately be in flight).
- **409 ordering is load-bearing.** On "request no longer pending", run the forced reload **before** setting `error` — `withLoad` nils `error` on success, and doing it the other way round swallows the message. This is a bug already fixed once in `BoardManageViewModel.run`.
- **Friend profile: one aggregate `GET /people/{id}`, not four parallel `async let`s.** Reasons: (a) the four `/me`-scoped endpoints don't exist in a viewer-scoped form, so fanning out means *more* backend surface; (b) per-section visibility depends on the viewer's friendship status, which only the server knows — a client fan-out leaks section existence through status codes; (c) `async let` under `withLoad` is all-or-nothing, and `RewardsHomeViewModel.load()` already demonstrates the flaw (one flaky call blanks all three sections). Mirror `status`/`requestId`/`friendCount` out of the immutable header for optimistic mutation, exactly as `BrandDetailViewModel` does with `followed`.

### 2.5 Screens

Every screen: `List` + `.listStyle(.insetGrouped)` + `.listRowBackground(TU.inkRaised)` + `.themedScreen()` + `.navigationTitle` + `.task { await vm.load() }` + `.refreshable` + `.overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }`. **`.searchable` is never used in this app** — search is a plain `TextField` in the first Section. Infinite scroll is per-row `.task { if x.id == vm.items.last?.id { await vm.loadMore() } }`.

**`FriendsHubView`** — segmented `Picker` + `switch vm.tab` inside `.themedContainer()`, `init(initialTab:highlightRequestId:)` with defaults so `FriendsHubView()` still works from `MoreView`.

> ⚠️ **Device-test the Picker.** `BoardManageView.swift:49-53` documents that a segmented Picker, an HStack of buttons, and a chip rail *each* shipped an on-device hit-testing bug, and both existing hubs now use a `List` of `NavigationLink`s instead. Mitigations baked in: plain `Text` tags (system-drawn, no custom label view), the Picker sits **outside** any `List`, and no `.contentShape`/`.buttonStyle`/`.onTapGesture` anywhere near it — the three causes that comment names. `themedContainer()`'s own doc comment sanctions exactly this arrangement. **If QA reproduces it on device, the fallback is mechanical**: swap to the `BoardManageView` index-`List` + a pushed `FriendsSectionScreen(tab:)`, every VM and section view unchanged.

- **`FriendsListSection`** — activity preview (3 rows + "See all") then friend rows, swipe-to-unfriend + `confirmationDialog` (the `MembersView` idiom). Feed preview degrades silently (`(try? await ...) ?? []`) — a feed outage must not fail the friends list.
- **`FriendRequestsSection`** — copies `JoinRequestsView`. Incoming (Accept/Decline) + Sent (Cancel). Highlight the deep-linked request with `.listRowBackground(TU.ember.opacity(0.15))` (the `LeaderboardView` `is_you` idiom). **Decline and Cancel get no confirmation** — both recoverable. Only Unfriend and Block do.
- **`FriendFindSection`** — `@`-prefixed TextField, results or (suggestions + invite rows) depending on `isSearching`.
- **`FriendProfileView`** — copies `BrandDetailView` structurally including the `_vm = State(initialValue:)` seeding init. Header (Avatar `.header`, name, `@handle`, `PointsPill`, `StatusChip`s for level/friends/mutual) + primary action button driven by `status`; then Reviews / Places they follow / Badges / Boards. **`BadgesGrid(badges:)` is reused unchanged.** Places use inline `AsyncImage` + `storefront` placeholder (the `DiscoverCard.swift:53` idiom) — **not** `AsyncMediaImage`, which is presigned-S3 review media only. Overflow `Menu` → Unfriend / Block / Report, two `confirmationDialog`s.
- **`FriendActivityRow`** — a pure `var headline: String?` computed from `kind`, returning **nil for `.unknown`**; the `ForEach` filters those out so a future server kind is invisible rather than broken.
- **`FriendInviteSheet`** — `QRCodeView` at 180×180 **on a white `RoundedRectangle`** (dark-on-dark won't scan), `ShareLink`, copy button. `.presentationDetents([.height(420)])`.
- **`ConsumerSettingsView`** — a "Handle" section (`@`-prefixed field + inline availability line + Claim) and a "Privacy" section (visibility Picker, "Let people find me by @handle" toggle, and `leaderboard_opt_in` **moved here from Profile**). Moving it changes which Save writes it — `savePrivacy` must send it and `saveProfile` must stop, or the two buttons fight.

**Handle-claim state machine** (`ConsumerSettingsViewModel`): normalize (strip typed `@`, lowercase, trim) → client-side `validate` → 450ms-debounced, generation-guarded `handleAvailable` call → `.available` / `.taken([suggestions])` / `.serverInvalid`. `POST /me/handle`'s 409 is authoritative and maps through a **pure static `handleState(forStatusCode:detail:handle:)`** so it's unit-testable. A 500 or nil must **not** render as `.taken` — a transient failure telling users their handle is taken is the bad outcome.

### 2.6 `Views/Shared/Avatar.swift`

No avatar component exists and consumers have no image in v1, so **the initials fallback is the primary path, not the error path** — it has to look deliberate.

```swift
struct Avatar: View {
    enum Size { case compact /*28*/, row /*40*/, header /*88*/ }
    // convenience inits: Avatar(_ person: FriendSummary, size:), Avatar(_ header:…), Avatar(_ account:…)
    nonisolated static func initials(from displayName: String?) -> String
    nonisolated static func paletteIndex(for accountId: String) -> Int
    nonisolated static let palette: [Color]   // 6 entries
}
```
- **`paletteIndex` must not use `String.hashValue`** — Swift's `Hasher` is seeded per process, so the same person would change colour every launch. Use FNV-1a over the id's UTF-8 bytes.
- `initials` is grapheme-cluster safe (an emoji name takes the first cluster, never a broken scalar); `nil`/empty/punctuation-only → `"?"`.
- Palette = 3 `TU` ember tokens + 3 low-saturation counterweights (blue/sage/orchid) so a friends list doesn't read as a wall of orange while staying inside the `TU` language. Render: `Circle` filled `tint.opacity(0.18)`, stroked `TU.hairline` (or `TU.ember` 2pt when ringed), initials in `tint`. With an `imageURL`, `AsyncImage` fills the circle **with the initials view as its `placeholder:`** so a slow or 404 image degrades to initials, never a gray box.

### 2.7 Deep links + inbound invites

`Models/DeepLinkRoute.swift` gains `.friendRequests(highlightRequestId:)`, `.friendProfile(accountId:name:)`, `.friendInvite(token:)`, with `id` prefixes and `parse` arms. **These must read only `reference_id` and `name`** — `schedule_push` (`push.py:264-272`) hard-codes its payload to six keys and anything else needs a backend change.

`App/RootView.swift`'s `DeepLinkDestinationView` switch is exhaustive, so it **will not compile** until updated. Add a **consumer-only guard** in `AppState`'s push observer — a brand account tapping a stray friend push must not land on a screen whose every endpoint 403s.

**Inbound invite links: use the paste/scan path for v1, not universal links.** There is no `onOpenURL` router at all today (`TellUsApp` hands every URL to `GIDSignIn`). Universal links would need an AASA file on hey-matcha.com, the `associated-domains` entitlement in **both** `.entitlements` files, **the capability enabled on the App ID and the "Beetlejuse App Store" provisioning profile re-generated** (Release is `CODE_SIGN_STYLE: Manual` with a pinned specifier, so a stale profile fails the *archive*, not the build), plus a deferred-URL replay path. That's a release-pipeline risk for a v1 feature.

Instead: `share_url` → the web page shows the invite + the raw token; in-app, "Have an invite code?" opens `FriendInviteRedeemView`, which takes a paste **or** a QR scan of the friend's sheet. Zero entitlement, zero signing risk, and the QR half ships fully native. `ScannedTarget` gains `.friendInvite`, parsed from `/f/{token}` **before** the `p`/`i` arms; the bare-token regex fallback **stays `.intake`** (the only kind ever printed without a URL — changing it breaks table tents).

> Note: `Views/Consumer/Scan/ScanView.swift` is currently **unreachable** — zero references anywhere. The parser change is future-proofing; the redeem screen hosts its own `QRScannerView`.

### 2.8 `MoreView` + badges

New first row of the existing first Section (above "My Reviews"), with a count capsule lifted verbatim from `BoardManageView`'s `BoardSectionRow` so the app's two count badges are identical. `AppState` gains `pendingFriendRequests`, filled from `GET /me/friend-requests/count` inside the existing 60s `startPolling()` loop and zeroed in `didLogout()`.

**Tab-bar badge: add it.** `.badge(appState.pendingFriendRequests)` on the More tab — `.badge(0)` renders nothing, so no conditional. This is the **first `.badge` in the app**, which creates an inconsistency the team should accept explicitly: friend requests get a bar badge while unread notifications (already counted in `appState.unreadCount`) don't. Either accept it, or add `.badge(appState.unreadCount)` to Home in the same commit.

### 2.9 Existing iOS code that must change

`Support/BoardTabLoadState.swift` (generified), `Models/AuthModels.swift` (+5/+4 fields), `ConsumerSettingsViewModel`+`View`, `MoreView`, `ConsumerTabView`, `AppState`, `DeepLinkRoute`+`RootView` (exhaustive switch — won't compile until updated), `ScanView` (`ScannedTarget` case — every exhaustive switch over it), `NotificationsView` (`icon(for:)` + NavigationLink arms), and the three test files below.

Reused unchanged: `BadgeItem`, `BadgesGrid`, `EmptyState`, `StatusChip`, `PointsPill`, `Formatters`, `ErrorBanner`, `QRCodeView`, `QRScannerView`, `EmberButtonStyle`, `themedScreen/Container/Row`, `LoadableVM.withLoad`, `PlacesService.queryString`.

---

## Part 3 — Tests

**Backend** (`server/tests/tellus/`). Repo rule: **never auto-run DB-mutating tests.**
- `test_friends_logic.py` — pure, CI-safe. Handle charset boundaries; **`member_a1b2` rejected** (the `Member-xxxx` impersonation vector) and `tellus_*` rejected; `pair_key(a,b) == pair_key(b,a)` and stable across process runs; the `can_request` truth table including day-29-blocked / day-31-allowed, with a docstring stating why this **diverges** from `board_service`'s permanent block; the full `visible_sections` matrix (3 visibilities × {self, friend, stranger} × `leaderboard_opt_in`); cursor round-trip where a malformed cursor returns `None` rather than raising (a bad cursor must be a 422, never a 500).
- `test_friends_guards.py` — source-guard, using the `_code_only()` comment/docstring-stripping helper from `tests/tellus/test_likes.py`. Pins: every `kind=` passed to `notify_account` is in `PUSH_KINDS` (**the exact drift this feature is most likely to introduce**, given `schedule_push` fails silently); `create_friendship` contains `earn_engagement`+`pair_key` and **not** `UniqueViolationError`; `remove_friendship` is one statement with both direction predicates; the feed SQL contains all three public-predicate clauses verbatim; the feed hydrator has `= ANY($` ≥4 times and no `conn.fetch` inside a `for`; `routes/friends.py` never mentions `email`; and a **friends gate sweep** walking `routes.friends.router.routes` asserting `require_verified_consumer` on every one (the `TestAdminGateSweep` pattern applied to a consumer router).
- `test_friends_models.py` — pure. Includes an assertion that `dependencies._load_account`'s **source** references each new column (the most likely omission: columns exist, model has them, loader silently returns defaults), and that `TellusPublicReview` still has no `reporter_account_id` field.
- `test_friends_db_manual.py` — env-var-guarded so it can never run in CI, reserved test domains only (`@example.com`/`@*.test`). Mirror symmetry after accept; double-accept idempotency; reciprocal-pending auto-accept; block cascading to friendship + both-direction pendings; **ledger idempotency across unfriend → re-friend** (points awarded exactly once); handle uniqueness under concurrent claim; feed keyset stability with a review publishing mid-pagination.

**iOS** (`Tests/`). XCTest only; **no network faking exists anywhere** (no mocks, no stubs, no URLProtocol, no service protocols — all hard singletons), so every case is a decode fixture or a pure state transition.
- `FriendModelDecodeTests.swift` — full decode; **`testFriendSummaryFromOldServerDecodes`** (three keys only, everything else defaults, no throw); `display_name: null` → `"Someone"`; `FriendProfile` with all four sections, with `null` sections, and header-only.
- `FriendHandleTests.swift` — normalize is idempotent; the validate boundary table.
- `AvatarTests.swift` — initials edge cases incl. emoji; `paletteIndex` **deterministic** and in range across 200 UUIDs; distributes across ≥4 of 6 slots.
- `FriendSearchStateTests.swift`, `FriendsHubStateTests.swift` — the pure `applying(...)` / `applyingAccept(...)` helpers, incl. unmatched-id → array unchanged.
- `FriendsTabLoadStateTests.swift` — proves the generic works for a second key type.
- `HandleCheckStateTests.swift` — 409 → `.taken`, 422 → `.serverInvalid`, **500/nil → not `.taken`**.
- Modified: `EnumFallbackTests.swift` (the mandatory three-way pattern — single value, round-trip, **and inside an array** — for each new open enum), `ParityModelDecodeTests.swift` (+`testTellusAccountFromOldServerDecodes`), `ScannedTargetTests.swift` (+`/f/` cases and a **regression guard that the bare-token fallback is still `.intake`**).

---

## Part 4 — Build sequence

**Backend** (each row a commit):
1. `feat(tellus): friends schema (tellus_app_28)` — migration + all Pydantic models + `TellusAccount`/`TellusProfileUpdate` + `test_friends_models.py`
2. `feat(tellus): friends_service pure helpers` — handle rules, `pair_key`, `can_request`, `visible_sections`, cursor codec + `test_friends_logic.py`
3. `feat(tellus): @handles and profile visibility` — `POST /me/handle`, availability, `PATCH /me`, **`dependencies._load_account`**, empty router wired into `routes/__init__.py`
4. `feat(tellus): friend request lifecycle` — request/accept/decline/cancel/list/count, notifications, **`PUSH_KINDS`**
5. `feat(tellus): friendships, points, blocks`
6. `feat(tellus): friend search and suggestions`
7. `feat(tellus): person profiles`
8. `feat(tellus): friend activity feed` + `test_friends_guards.py`
9. `feat(tellus): friend invite links`
10. `feat(tellus): abuse reports + admin queue`
11. `docs(tellus): friends section in CLAUDE.md` + `test_friends_db_manual.py`

**iOS** (after backend 1–5 are on dev):
1. Foundations — models, enums, `SectionLoadState` generification. **Acceptance: `BoardTabLoadStateTests.swift` passes with zero edits.**
2. `FriendsService` + `Avatar` + `AvatarTests`
3. Friends hub + `MoreView` row — **`make run` on a physical device to clear the segmented Picker**
4. Friend profile
5. Activity feed — kill the network mid-scroll, confirm the list does not blank
6. Invite + QR + redeem — scan one device's QR from another to confirm the light quiet zone
7. Settings — handle + privacy; claim the same handle from a second account, confirm the 409 renders **inline**, not in the banner
8. Deep links, counts, badges — real APNs test push (needs backend step 4 landed)

---

## Verification

**Backend, local:**
```bash
cd server && python3 -m pytest tests/tellus/ -v     # pure + guard tests only
./scripts/migrate-dev.sh                            # local matcha-postgres:5432
```
Then with `./scripts/dev-remote.sh` running (already up on :8001/:5174 — do **not** pkill by port pattern), exercise the flow with two reserved-domain consumer accounts: claim two handles, search one from the other, request → accept, verify `tellus_points_ledger` has exactly one `friend_added` row per account, unfriend → re-friend and verify **no** second award, then `GET /me/feed` after publishing a review with `publish_at` in the past.

Confirm the two silent-failure modes explicitly:
```bash
# 1. every notify_account kind reaches PUSH_KINDS
grep -n "kind=" server/app/tellus/services/friends_service.py
sed -n '44,55p' server/app/tellus/services/push.py
# 2. _load_account returns the new columns (not model defaults)
curl -s -H "Authorization: Bearer $TOKEN" localhost:8001/api/tellus/auth/me | jq '.handle, .profile_visibility, .discoverable'
```

**Migration to prod is a separate, explicitly-approved step** — author → `migrate-dev.sh` → test → `migrate-prod.sh` per `docs/ops/DB_WORKFLOW.md`. Never `alembic upgrade head` against RDS directly.

**iOS:**
```bash
cd platforms/ios/TellUs && make test && make build && make run
```
`make` runs `xcodegen generate` first. Device-only checks: the segmented Picker (step 3), QR scanning (step 6), APNs deep links on a cold launch incl. the deferred-replay path and a brand account correctly dropping a friend route (step 8).
