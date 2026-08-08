# oceanlab — Phase 1 fix plan

Review of Phase 1 ("skeleton + schema") implementation against `PROJECT.md`. Three parallel audits covered server models/routers/migrations, services/tests, and client. Overall verdict: implementation is close to spec — 30 backend tests pass, `tsc --noEmit` clean, no model/migration drift — but the audits surfaced real bugs, spec discrepancies, and coverage gaps below. Items are prioritized P1 (fix before Phase 2) → P4 (polish/hardening).

## P1 — Real bugs, fix before Phase 2

### Server — concurrency / correctness

- **FIX-1** `server/app/services/isrc.py:37` — recording row not locked in `assign_isrc`. Two concurrent calls on the same recording both pass the `isrc is not None` check, each burns a designation, one leaks permanently. Fix: `db.get(Recording, id, with_for_update=True)`.
- **FIX-2** `server/app/services/upc.py:77` — same shape in `assign_upc`; release row unlocked. `SKIP LOCKED` hands each concurrent thread a different pool code, both mark their row assigned, one orphaned (a paid $30 GS1 code lost). Fix: `with_for_update=True`.
- **FIX-3** `server/app/services/upc.py:86` — "oldest available" `order_by(created_at)` has no tiebreaker; codes added in one batch share a transaction timestamp → non-deterministic FIFO. Add `, UpcCode.code`.
- **FIX-4** `server/app/routers/recordings.py:89` — bare `IsrcError` catch maps `Exhausted` to 422; spec requires 500. Also the "recording not found" `IsrcError` should be 404. Catch subclasses explicitly before the base class.
- **FIX-5** `server/app/routers/codes.py:17-24` — `_get_or_create_config` races (get → insert → commit inside a GET handler); concurrent first request on empty table → `IntegrityError` → 500. Use `INSERT … ON CONFLICT DO NOTHING`.

### Server — unhandled `IntegrityError` → 500

Each needs: catch, rollback, map to 409/422 with an accurate message, plus a regression test.

- **FIX-6** `recordings.py:100-103` `PUT /splits` — duplicate `contributor_id` or unknown FK → 500.
- **FIX-7** `works.py:78-84` `PUT /writers` — duplicate `(contributor_id, role)` or unknown FK → 500.
- **FIX-8** `recordings.py:128-131` `PUT /works` — duplicate `work_ids` (add a `_no_duplicates` validator like `schemas/track.py:41`) or unknown `work_id` → 500.
- **FIX-9** `recordings.py:114-117` `PUT /credits` — unknown `contributor_id` → 500.
- **FIX-10** `recordings.py:40-45,57-65` `POST`/`PATCH /recordings` — bad `primary_artist_id` → 500; duplicate `isrc` via `PATCH` → 500.
- **FIX-11** `works.py:49-56` `PATCH /works/{id}` — duplicate ISWC → 500 (POST already handles this correctly; PATCH doesn't).
- **FIX-12** `releases.py:48-52,72-76` — every `IntegrityError` reported as `409 "Catalog number already exists"`, even when the actual violation is the UPC unique constraint or an FK on `primary_artist_id` (should be `422 Artist not found`). Pre-validate the artist (like `tracks.py:44` does for recordings) or inspect `e.orig.diag.constraint_name`.

### Server — API hygiene

- **FIX-13** All five list endpoints (`artists.py:18`, `contributors.py:18`, `works.py:18`, `recordings.py:30`, `releases.py:22`) — unbounded `limit`/`offset`. `?limit=-1` → 500, `?limit=1000000` → unbounded scan. Use `Query(ge=1, le=200)` / `Query(ge=0)`.

### Client

- **FIX-14** `client/src/api/hooks/index.ts:144-152` + `server/app/routers/tracks.py:122-131` — deleting a track leaves position gaps (e.g. `1,3`); nothing renumbers. Will trip the Phase-2 `T-GAP` validation rule the moment it exists. Fix server-side (compact positions on delete inside the deferred-constraint transaction) or have the client reorder after delete.
- **FIX-15** `client/src/pages/ReleaseDetailPage.tsx:14` (also `CatalogPage.tsx:144`, `TracksTab.tsx:25,47`, `SettingsPage`) — query errors are never rendered anywhere; a failed fetch is either an infinite "Loading…" or a silently empty list/table. Add `isError` handling wherever `useQuery` is consumed.
- **FIX-16** `client/src/pages/ReleaseDetailPage.tsx:69-75` — metadata form's `useEffect([release])` resets all inputs on every refetch, so each blur-save (which triggers an invalidate → refetch) clobbers in-progress edits in other fields. Depend on `release.id` (or use `key={release.id}` with uncontrolled inputs) instead of the whole object.

## P2 — Phase-1 exit criteria not met (client scope)

Spec's Phase-1 exit line: *"full catalog CRUD through UI; ISRC/UPC assign works…"*

- **FIX-17** No UI to create recordings, contributors, or works (`client/src/App.tsx:57-61` routes = Catalog/ReleaseDetail/Settings only). On a fresh DB you cannot add a single track without hitting the API directly — `TracksTab` can only pick from existing recordings. Largest gap. Minimum: recording create inline in `TracksTab` (mirror the artist inline-create at `CatalogPage.tsx:80-111`), plus simple contributor/work pages or inline creates.
- **FIX-18** `ReleaseDetailPage.tsx:99-156` — metadata form exposes 5 of ~14 editable `ReleaseUpdate` fields. Missing `c_line`, `p_line`, `territories`, `label_name`, `subgenre`, `original_release_date`, `notes`, `primary_artist_id`. `c_line`/`p_line`/`territories` are hard `error`-severity rules in the Phase-2 validator — Phase 2 is blocked without them in the form.
- **FIX-19** `CatalogPage.tsx:148-155` — table is missing the Artist column (spec: title, artist, type, status, UPC, date). `ReleaseRead` only exposes `primary_artist_id`, no name — needs a client-side map from `useArtists()` or a server-side join.
- **FIX-20** `client/src/api/types.gen.ts` has never been generated; hooks hand-roll interfaces that have already drifted from the server schemas (client `Release` type lacks `c_line`, `p_line`, `territories`, `subgenre`, etc.). Run `npm run gen:api` and adopt the generated types — this is exactly the drift the codegen step exists to prevent.
- **FIX-21** `SettingsPage` never shows UPC pool counts. `GET /upcs` already returns `{items, available, assigned}` and the client never calls it. `POST /upcs/{id}/unassign` (added in the review-fix commit) is also unreachable from the UI.

## P3 — Design gaps to settle before Phase 3/4 (cheap now, expensive later)

- **FIX-22** `server/app/models/delivery.py:47` — `DeliveryItem.track_id` has no `ondelete`. Once Phase-3 deliveries exist, a release becomes undeletable (FK blocks the CASCADE chain from `Release`). Set `ondelete="CASCADE"` now, while there's a single migration to edit.
- **FIX-23** `server/app/models/royalty.py:22` — `RoyaltyStatement.status` is a bare `String`, no enum/CHECK, unlike every other status column in the schema. Add a `StatementStatus` enum before Phase 4 starts writing it.
- **FIX-24** `ReleaseArtist` table exists (featured artists) but has no endpoint anywhere in the spec or code (e.g. `PUT /releases/{id}/artists`). Featured artists are unreachable via the API, yet the Phase-3 `manifest.csv` needs a `featured_artists` column. Add the endpoint before Phase 3.
- **FIX-25** Both client and server currently allow `status` to be set freely on a release (`ReleaseDetailPage.tsx:142-155`, `ReleaseUpdate` schema) — bypasses the Phase-3 status machine and packaging gate that doesn't exist yet. Decide now whether to restrict client-side or explicitly defer to Phase 3.
- **FIX-26** `server/app/services/upc.py:24-27` — `InvalidUpcFormat` is dead code (defined, never raised); the actual API contract returns `{added, rejected}` with 200. Either delete the unused exception class or use it — don't leave both.
- **FIX-27** `models/codes.py:31` — UPC `ondelete="SET NULL"` on release delete orphans codes as `assigned` with no reclamation path surfaced in the UI. Document the behavior and surface the unassign action in Settings (bundle with FIX-21).

## P4 — Tests, hardening, polish

- **FIX-28** Missing Phase-1 test coverage: splits/credits/writers PUT-replace (replace-all semantics + conflict paths — zero coverage on a shipped surface), UPC concurrency (would have caught FIX-2), `Exhausted` path, oldest-first UPC assignment (blocked on FIX-3), pagination bounds, release filters, `GET /upcs` counts, unassign endpoint, DELETE-409 for contributors/works (only artists is currently covered).
- **FIX-29** `server/app/deps.py:10` — token comparison uses `!=`; use `secrets.compare_digest` for timing-safety.
- **FIX-30** `server/alembic/env.py` — add `compare_type=True, compare_server_default=True` to `context.configure` so future autogenerate catches type/default drift.
- **FIX-31** `server/scripts/seed.py:28` — `.one_or_none()` on non-unique `title` → `MultipleResultsFound` if a second release shares the sample title; use `.first()` or key off `catalog_number` instead. Also prints success before `db.commit()`.
- **FIX-32** `server/app/models/codes.py:11` — `IsrcConfig` singleton (`id=1`) is unenforced; add `CheckConstraint("id = 1")`.
- **FIX-33** `server/app/config.py` — `storage_root` is a relative path, resolves against process CWD; the `/health` storage probe can report healthy while pointing at the wrong directory if uvicorn starts elsewhere. Anchor to the package dir or document the requirement.
- **FIX-34** `server/app/models/release.py:7` imports `app.config.settings` at model-import time, so the models package requires valid env vars just to import. Defer via `default=lambda: get_settings().label_name`.
- **FIX-35** Client polish batch:
  - query-key hygiene: `useAssignUpc` (`hooks/index.ts:171`) doesn't invalidate the catalog list key, so the UPC column goes stale; metadata-tab saves unintentionally refetch the tracks list via key-prefix nesting.
  - 401 handling: hard `window.location.reload()` + default `retry: 3` → multiple concurrent reloads on a bad token, no "wrong token" feedback at the gate.
  - artist/recording dropdowns capped at 50/200 items with no search wired in.
  - no debounce on catalog search (one request per keystroke).
  - ISRC prefix input in Settings isn't seeded from the current config value.
  - `MutationError` renders raw 422 JSON instead of a readable message.
  - `displayUpc` is currently a no-op.
  - `<dialog open>` is used non-modally (no backdrop/focus-trap/Esc) — should call `showModal()` via ref.
  - tsconfig is missing `strict: true` (code already passes `--strict`, just enable it so `npm run build` enforces it too).
- **FIX-36** Schema validation bounds worth adding cheaply: `share_pct` `ge=0, le=100`, `country`/`language` 2-char pattern, `ipi_number` 11-char, `iswc` `T\d{10}` pattern.
- **FIX-37** `conftest.py` nits: hand-maintained `TRUNCATE` list in the `db_real` teardown (currently survives only via CASCADE reach); savepoint-restart listener fires on any `after_transaction_end` including teardown's own close (harmless today, guard it per the canonical SQLAlchemy recipe); hardcoded test DB URL ignoring env.

## Notably good — no action needed

- Data model matches spec closely: constraints, `ondelete` behavior, the `DEFERRABLE INITIALLY DEFERRED` unique on `Track`, enum member lists, `Numeric` precisions all verified correct.
- Test schema is built via `alembic upgrade head` (not `create_all`), so model/migration drift fails tests — the right call, done in the review-fix commit.
- `db_real`/`client_real` fixture pair correctly exists to let `DEFERRABLE` constraints fire under real commits.
- GTIN check-digit math in `upc.py` is correct.
- All Phase 2–4 services/routers/tests are correctly absent from this phase — nothing over- or under-scoped there.

## Verification once fixes land

`uv run pytest -q` in `server/` should stay green with new regression tests for each P1 item; `npx tsc --noEmit` in `client/` should stay clean; manually exercise the Phase-1 exit flow end-to-end through the UI (create artist → release → recording → track → assign ISRC/UPC → edit full metadata) once FIX-17/18 land, since that flow currently can't be completed through the UI alone.
