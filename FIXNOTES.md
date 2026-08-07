# Phase 1 review — fix notes

Reviewed against `PROJECT.md` Phase 1 scope (branch `docs/project-plan`, commit `c878ea3`). Overall the
implementation is faithful to spec: data model matches field-by-field including FK ondelete behavior and
`Numeric` precisions, the `tracks` DEFERRABLE INITIALLY DEFERRED unique constraint exists in both the model
and the migration, `alembic upgrade head` is exercised by `conftest.py` so model/migration drift fails tests,
ISRC/UPC services correctly implement row locking + year rollover + GTIN check digit + SKIP LOCKED, and the
concurrency tests (threads racing the same recording/release) are solid. Items below are real gaps or bugs
found during review.

## F1 — Test-suite year time bomb

`app/tests/factories.py` defaults `year_digits="26"`; `test_isrc.py` asserts hardcoded `"QZABC2600001"` /
`"QZABC2600002"` codes, and `make_release(complete=True)` stamps `QZABC26...` ISRCs onto fixture recordings.
`assign_isrc` rolls the year over on wall-clock time, so on 2027-01-01 these assertions start failing even
though the code under test is correct. Fix: derive the year from `datetime.now(timezone.utc)` in factories/tests,
matching the pattern already used in `test_year_rollover_resets_designation`.

## F2 — CI never runs on this branch

`.github/workflows/ci.yml` triggers on `push: branches: [main]` and `pull_request` only. `docs/project-plan`
was pushed directly with no PR opened, so none of these 10 commits have run through CI. Open a PR against
`main` (or add the branch to the push trigger) so `ruff` / `pytest` / `tsc` actually execute.

## F3 — `add_upcs` silently swallows already-present codes

`app/services/upc.py::add_upcs`: a valid code that's already in the `upc_codes` table is neither counted in
`added` nor put in `rejected` — pasting a batch that's mostly duplicates returns `{added: 0, rejected: []}`
with no signal to the user that anything happened. Add a `skipped`/`duplicates` count to `UpcAddResult` and
surface it in the Settings UI.

## F4 — `PATCH /releases/{id}` allows arbitrary status jumps

`app/schemas/release.py::ReleaseUpdate` exposes `status`, so a single PATCH can jump `draft -> released`
today. PROJECT.md's API table doesn't list `status` as PATCHable, and the gated status machine is explicitly
Phase 3 scope. Drop `status` from `ReleaseUpdate` now; reintroduce it behind the Phase 3 validator-gated
transition endpoint.

## F5 — `GET /upcs` has no response_model

`app/routers/codes.py::list_upcs` returns a hand-built dict with no `response_model`, so `openapi-typescript`
(the `gen:api` step PROJECT.md calls for) emits `unknown` for it. Add a `UpcListResponse` schema.

## F6 — Token gate has no invalid-token feedback

`client/src/App.tsx`'s `TokenGate` stores whatever string is typed; the first 401 from any call clears the
token and does `window.location.reload()`, so a bad token just silently bounces back to the same screen.
Probe one cheap authed endpoint before persisting the token and show an inline error on failure.

## Accepted deviations (no action needed)

- Track reorder is up/down buttons, not drag-and-drop — fine for v1.
- Deleting a release leaves its UPC row `assigned` with `release_id = NULL` (burned until a manual
  `/upcs/{id}/unassign`) — deliberate, covered by `test_delete_release_survives_assigned_upc`.
- Client CI installs with `npm ci --legacy-peer-deps`, papering over a recharts/react-19 peer conflict —
  revisit when recharts publishes a react-19-compatible major.
