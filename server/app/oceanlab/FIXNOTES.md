# Phase 1 review — fix notes

Reviewed against `PROJECT.md` Phase 1 scope (branch `docs/project-plan`, commit `c878ea3`). Overall the
implementation is faithful to spec: data model matches field-by-field including FK ondelete behavior and
`Numeric` precisions, the `tracks` DEFERRABLE INITIALLY DEFERRED unique constraint exists in both the model
and the migration, `alembic upgrade head` is exercised by `conftest.py` so model/migration drift fails tests,
ISRC/UPC services correctly implement row locking + year rollover + GTIN check digit + SKIP LOCKED, and the
concurrency tests (threads racing the same recording/release) are solid. Items below are real gaps or bugs
found during review.

## F1 — Test-suite year time bomb — FIXED

`app/tests/factories.py` defaults `year_digits="26"`; `test_isrc.py` asserts hardcoded `"QZABC2600001"` /
`"QZABC2600002"` codes, and `make_release(complete=True)` stamps `QZABC26...` ISRCs onto fixture recordings.
`assign_isrc` rolls the year over on wall-clock time, so on 2027-01-01 these assertions start failing even
though the code under test is correct. Fixed: year now derives from `datetime.now(timezone.utc)` via
`CURRENT_YEAR_2` in factories/tests, matching the pattern already used in `test_year_rollover_resets_designation`.

## F2 — CI never runs on this branch

`.github/workflows/ci.yml` triggers on `push: branches: [main]` and `pull_request` only. `docs/project-plan`
was pushed directly with no PR opened, so none of these commits have run through CI. Open a PR against
`main` (or add the branch to the push trigger) so `ruff` / `pytest` / `tsc` actually execute.

## F3 — `add_upcs` silently swallows already-present codes — FIXED

`app/services/upc.py::add_upcs`: a valid code that's already in the `upc_codes` table was neither counted in
`added` nor put in `rejected` — pasting a batch that's mostly duplicates returned `{added: 0, rejected: []}`
with no signal to the user that anything happened. Fixed: `add_upcs` now returns a `skipped` count, surfaced
in `UpcAddResult` and rendered in the Settings UI.

## F4 — `PATCH /releases/{id}` allows arbitrary status jumps — FIXED

`app/schemas/release.py::ReleaseUpdate` exposed `status`, so a single PATCH could jump `draft -> released`
today. PROJECT.md's API table doesn't list `status` as PATCHable, and the gated status machine is explicitly
Phase 3 scope. Fixed: `status` dropped from `ReleaseUpdate`; the client's editable status dropdown removed
(status is still shown, read-only, in the release header). Reintroduce both behind the Phase 3
validator-gated transition endpoint.

## F5 — `GET /upcs` has no response_model — FIXED

`app/routers/codes.py::list_upcs` returned a hand-built dict with no `response_model`, so `openapi-typescript`
(the `gen:api` step PROJECT.md calls for) emitted `unknown` for it. Fixed: added `UpcListResponse`/`UpcListItem`
schemas and wired them as the route's `response_model`.

## F6 — Token gate has no invalid-token feedback

`client/src/App.tsx`'s `TokenGate` stores whatever string is typed; the first 401 from any call clears the
token and does `window.location.reload()`, so a bad token just silently bounces back to the same screen.
Probe one cheap authed endpoint before persisting the token and show an inline error on failure.

## Second pass — FIXPLAN.md audit

A follow-up audit (`FIXPLAN.md`, not tracked in this repo) was run against an earlier commit and claimed 37
findings. Cross-checking it against the current head found roughly half already fixed by the commits between
that snapshot and now (recording/release row locking, the shared `IntegrityError` → HTTP translation in
`_errors.py`, pagination bounds, Settings UPC pool counts, `InvalidUpcFormat` dead code, constant-time token
compare) — those are stale, not re-applied. One claim (`Exhausted` should map to 500) contradicts
`PROJECT.md:225`, which specifies 422 — rejected. The following genuinely-real findings from that audit were
fixed in this pass:

- UPC assignment FIFO had no tiebreaker on `created_at` (codes added in one batch share a transaction
  timestamp) — added `UpcCode.code` as a secondary sort key.
- `alembic/env.py` was missing `compare_type=True, compare_server_default=True`, so future autogenerate
  wouldn't catch type/default drift — added to both offline and online `context.configure` calls.
- `scripts/seed.py` used `.one_or_none()` on non-unique `title` columns (`MultipleResultsFound` if a second
  release/artist ever shares a sample name) — switched to `.first()`.
- Schema-level validation was missing on several fields that only had DB-level column-length limits, so bad
  input surfaced as an ugly 500 (`DataError`) instead of a clean 422: `Artist.country` / `Recording.language` /
  `Work.language` (2-letter pattern), `Work.iswc` (`T\d{10}`), `Contributor.ipi_number` (9–11 digits),
  `MasterSplitIn.share_pct` / `WorkWriterIn.share_pct` / `publisher_share_pct` (0–100 bounds).
- `DeliveryItem.track_id` had no `ondelete`, which would make a release undeletable once Phase 3 deliveries
  exist (FK blocks the CASCADE chain from `Release`) — set to `CASCADE` in both the model and the (still
  unreleased, hand-edited) initial migration.
- `RoyaltyStatement.status` was a bare `String` with no constraint, unlike every other status column in the
  schema — added a `StatementStatus` enum (`uploaded|parsing|parsed|failed`, per `PROJECT.md:119`) with a
  CHECK constraint, matching the pattern used by every other enum-backed status column.
- `IsrcConfig`'s `id=1` singleton was unenforced at the DB level — added a `CheckConstraint("id = 1")`.
- `ReleaseDetailPage`'s metadata form reset all fields via `useEffect([release])`, so a blur-save (which
  triggers an invalidate → refetch) could clobber in-progress edits in other fields — removed the effect and
  keyed the form on `release.id` instead, so it only resets on navigating to a different release.
- `CatalogPage`'s table was missing the Artist column (spec: title, artist, type, status, UPC, date) — added,
  joined client-side from `useArtists()` since `ReleaseRead` only exposes `primary_artist_id`.
- No query surfaced `isError` anywhere in the client — added basic error states to the catalog list, release
  detail, tracks tab, and both Settings queries (ISRC config, UPC pool).
- `tsconfig.app.json` was missing `strict: true` even though the code already passed `tsc --strict` — enabled
  it so `npm run build` enforces it too (no code changes needed; it was already clean).

Left as documented follow-ups, not fixed in this pass (larger scope, deserve their own PRs):

- No UI to create recordings, contributors, or works — the largest Phase-1 exit-criterion gap (spec: "full
  catalog CRUD through UI").
- Metadata form exposes 5 of ~14 editable `ReleaseUpdate` fields; missing `c_line`/`p_line`/`territories` in
  particular block the Phase-2 validator.
- `client/src/api/types.gen.ts` has never been generated (`npm run gen:api`); hooks hand-roll interfaces that
  have already drifted from the server schemas.
- Deleting a track leaves position gaps (nothing renumbers) — will trip the Phase-2 `T-GAP` validation rule.
- `ReleaseArtist` (featured artists) has no endpoint anywhere, but the Phase-3 `manifest.csv` needs a
  `featured_artists` column.

## Accepted deviations (no action needed)

- Track reorder is up/down buttons, not drag-and-drop — fine for v1.
- Deleting a release leaves its UPC row `assigned` with `release_id = NULL` (burned until a manual
  `/upcs/{id}/unassign`) — deliberate, covered by `test_delete_release_survives_assigned_upc`.
- Client CI installs with `npm ci --legacy-peer-deps`, papering over a recharts/react-19 peer conflict —
  revisit when recharts publishes a react-19-compatible major.
