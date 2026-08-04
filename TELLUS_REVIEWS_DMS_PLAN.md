# Tell-Us: Public Reviews (48h hold) + Brand↔Reviewer DMs

Status: **built on `tellus/dms`, migration NOT yet applied to any DB.** Code is in, `tsc -b` clean, backend imports clean, 19/19 pure-function tests pass. Manual E2E (Step 6 below) still needs a human to run after applying `tellus_app_05`.

## Context

Tell-Us today is a private feedback pipe: consumer submits via link token → brand reads it in the dashboard → points flow. This feature turns it into a brand community: some feedback becomes a **public review** that goes live after a fixed **48-hour hold**, during which the brand can **heart** it (free acknowledgment), **DM** the reviewer to fix a bad experience, **gift** points (existing grants flow, unchanged), or post a single **public reply**. Published reviews appear on a new public brand page at `/tellus/b/{slug}`.

Locked product decisions:
- Submitter toggle "post as public review", **default ON**; public review **requires a logged-in consumer** — anonymous submissions are forced private server-side regardless of the toggle.
- **1–5 star rating** required for public reviews (sentiment/category stay for analytics).
- **Fixed 48h clock**, `publish_at = created_at + 48h`, publication is **lazy/derived at read time** — no cron, no worker.
- **Reviewer control only**: edit/withdraw anytime (held or published). Brand can never block/delay publication. Gifting stays decoupled from withdrawal.
- DM: at most one thread per report, brand initiates, consumer replies or blocks. Brand sees `display_name` only, never email.
- Notifications reuse `tellus_notifications` (`kind` is unconstrained TEXT). No `review_published` notification — lazy publication has no event moment to fire it from. DM email ping never echoes UGC (existing email rule).
- No WebSockets — REST + refetch/poll. No new deps.

## Migration — `tellus_app_05` (NOT YET APPLIED)

`server/alembic/versions/tellus_app_05_public_reviews_dms.py`, `down_revision="tellus_app_04"`. Set-based only, real `downgrade()`.

**Key decision — `review_state` stores only `'held' | 'withdrawn'`; `'published'` is derived** (`review_state='held' AND publish_at <= NOW()`). Lazy publication has no write moment; excluding `'published'` from the CHECK makes stored-vs-derived drift structurally impossible. `review_state IS NULL` ⟺ private feedback — no separate `is_public_review` boolean.

- `tellus_reports` gains: `rating SMALLINT` (CHECK 1–5), `review_state TEXT` (CHECK `held`/`withdrawn`), `publish_at TIMESTAMPTZ` (CHECK paired 1:1 with `review_state`), `hearted_at`/`hearted_by`, `brand_public_reply`/`brand_public_reply_at`. Partial index `ix_tellus_reports_public (brand_id, publish_at DESC) WHERE review_state='held'`.
- `tellus_brands.slug` — added NOT NULL + UNIQUE via a two-pass set-based backfill (slugify name → dedupe first-order collisions by rank suffix → dedupe any remaining collision with a UUID-slice suffix). Unique index creation is the terminal assert — a leftover duplicate fails the whole revision under rehearsal.
- New tables `tellus_dm_threads` (UNIQUE `report_id` — one thread per report) and `tellus_dm_messages` (`sender_role` CHECK `brand`/`consumer`, `read_at` for unread counts).

**Apply via the normal path**: `./scripts/migrate-dev.sh` then, once verified, `./scripts/migrate-prod.sh` (per `server/CLAUDE.md`'s migration rules — never run alembic ad hoc).

## Backend (`server/app/tellus/`)

- **Models** (`models/tellus.py`): `ReviewState`/`DmSenderRole` literals; `TellusFeedbackSubmit` +`rating`/`post_as_review`; `TellusFeedbackSubmitResponse` +`public_review`/`publish_at`; `TellusReport` +`rating`/`review_state`(effective)/`publish_at`/`hearted_at`/`brand_public_reply(+_at)`/`is_identified`/`has_dm_thread` — stays reporter-redacted; `TellusAccount` +`brand_slug`; new `TellusBrandReplyUpdate`, `TellusMyReview(Update)`, `TellusPublicReview`, `TellusPublicBrandPage`, `TellusDmSend`, `TellusDmMessage`, `TellusDmThread`.
- **`routes/_shared.py`**: `effective_review_state(row)` (pure — held+past→published, else passthrough, missing column→None) and `slugify(name)` (Python mirror of the migration's SQL regex, used at brand signup); `serialize_report` extended with every new field plus a per-row `has_dm_thread` EXISTS check.
- **`services/feedback_service.py`**: `create_report` gains `rating`/`post_as_review` kwargs. `review_state`/`publish_at` are set **in the same INSERT statement** as `created_at`'s default, so the 48h clock is exact. Anonymous submitters are forced private no matter what the flag says.
- **`routes/auth.py`**: brand signup generates a slug via `slugify`; a collision retries once inside a nested `conn.transaction()` (a real Postgres SAVEPOINT — a plain `except` around the INSERT would otherwise leave the whole signup transaction aborted).
- **`dependencies.py`**: identity SELECT now returns `brand_slug`.
- **`services/email.py`**: new `send_tellus_dm_email` — "X sent you a message about your feedback" + CTA, no message body (matches the existing never-echo-UGC rule).
- **`routes/feedback.py`**: `POST`/`DELETE /feedback/{id}/heart` (idempotent, no points), `PUT`/`DELETE /feedback/{id}/reply` (409 on non-review), and `moderate()` now notifies the reporter when a public review is removed — flagged in the docstring as a brand-censorship path around the "never block publication" rule, mitigated (not solved) by making removal never silent.
- **`routes/dms.py`** (new): `POST /feedback/{id}/dm` (brand opens with first message, idempotent via `ON CONFLICT (report_id)`), `GET /dm/threads`, `GET /dm/threads/{id}/messages` (read-on-fetch), `POST /dm/threads/{id}/messages`, `POST`/`DELETE /dm/threads/{id}/block` (consumer only, silent to the brand). Rate-limited per account.
- **`routes/my_reviews.py`** (new): `GET /me/reviews`, `PATCH /me/reviews/{id}` (never touches `publish_at`), `POST /me/reviews/{id}/withdraw` (idempotent, no un-withdraw v1).
- **`routes/community.py`** (new): `GET /b/{slug}` — unauthenticated, rate-limited, published-only filter hits `ix_tellus_reports_public`, reviewer identity is `COALESCE(display_name, 'Tell-Us member')` and nothing else.
- All four routers registered in `routes/__init__.py`.

## Frontend (`client/tellus/`)

- `api/types.ts` / `api/tellusClient.ts`: new response types; added a `put` method to `tellusApi` (only `get`/`post`/`patch`/`delete` existed — the reply endpoint needed `PUT`).
- `pages/Intake.tsx`: star picker + "post as public review" toggle (default on), sign-in nudge for anonymous+toggle, client-side rating gate, 48h success copy.
- `pages/brand/Feedback.tsx`: countdown chip ("publishes in Xh" / "public review" / "withdrawn"), star display, heart button, public-reply inline composer, DM inline panel, header link to the brand's public page.
- `components/DmThreadPanel.tsx` (new, shared): the DM widget used by both the brand row and the consumer review card — inline-expansion, no modal primitive (none exists in this app).
- `pages/consumer/MyReviews.tsx` (new): review cards with state/edit/withdraw/messages, following the existing Rewards.tsx fetch-in-`useEffect` pattern.
- `pages/PublicBrand.tsx` (new): bare public page at `/tellus/b/:slug`, load-more pagination.
- `App.tsx` + `components/Layout.tsx`: new routes (`/b/:slug`, `/my-reviews`); nav array gets a "My reviews" entry and the old "My rewards" label is renamed to "Redemptions" to avoid collision (the nav array is mapped twice — desktop sidebar + mobile strip — so one edit covers both); notification bell polls `GET /notifications?unread_only=true` every 60s.
- Fixed a **pre-existing, unrelated** `tsc -b` error in `Layout.tsx` (the three nav arrays had no shared type, so `end` didn't typecheck across the ternary) — confirmed present on the unmodified file before this branch touched it; fixed with a shared `NavItem` type since it blocked a clean verification run.

## Verification done

- `cd client/tellus && npx tsc -b` — clean.
- `./venv/bin/python -c "import app.tellus.routes"` (plus every new/touched module individually) — clean.
- `py_compile` across every touched/new backend file — clean.
- `server/tests/tellus/test_review_state.py` (new, pure-function, no DB) — `effective_review_state` and `slugify` cases — 9 tests, plus the pre-existing 10 in `test_points_math.py` — **19/19 pass**.

## Still open (manual, human-run)

1. Apply `tellus_app_05` via `migrate-dev.sh` (then `migrate-prod.sh` later).
2. Two-browser E2E: submit as consumer (rating+toggle, anonymous fallback), brand heart/reply/DM, consumer edit/withdraw/block, force-publish a held review in dev DB and check the public page, confirm moderation-remove notifies the reviewer, confirm gifting still works on a withdrawn review, confirm DM rate limit (11th rapid send → 429).

**Out of scope v1**: un-withdraw, a `review_published` notification, slug editing, hold extensions, an admin review-of-moderation pass, WebSockets/live updates.
