# Tenant Sync Review Findings (2026-07-24)

`/code-review high` on the test-tenant bidirectional dev↔prod sync branch (`matcha/dev-prod-sync-deploy` vs `main`). Verified against live dev DB; `server/tests/tenant_sync/` (48 tests) passed.

Status column tracks fix state — update as addressed.

All 13 fixed 2026-07-24. `server/tests/tenant_sync/` (50 tests, +2 new for #6) pass; `tsc -p tsconfig.app.json --noEmit` clean. **#2 needs a manual step**: migration `compupdat01` is authored but not applied — run `./scripts/migrate-dev.sh` then `./scripts/migrate-prod.sh` to actually close that finding.

## High

### 1. `scripts/sql/anonymize_dev.sql:31` (block 6, L150-176) — scrubbed secrets flow back TO prod
**Status:** fixed — block 6/7 UPDATEs now exempt `_test_companies`-owned rows (direct `company_id`/`org_id` where present, joined where not: `password_reset_tokens` via user_id, `ir_investigation_interviews` via incident_id). Header comment corrected. Tables with no company-scoping column at all (`gusto_webhook_tokens`, `beta_invitations`, `project_outreach`) are unreachable by the sync's FK walk regardless, so left as-is.

Block 6 does not exempt `is_test` companies. Header claims "the next sync run converges them" — wrong direction; sync converges prod *toward* dev, not the reverse.

Sequence: `refresh-dev-from-prod.sh` clones prod→dev and scrubs → dev now differs from prod only by the scrub → next deploy's `sync-test-tenants.sh --auto` pushes those deltas to live prod. Concretely, prod's demo tenant gets:
- `companies.report_email_token = NULL` (breaks the live `/report/:token` poster link)
- randomized `employee_invitations.token`
- `stripe_subscription_id = 'sub_dev_…'` / `mw_stripe_sessions.stripe_session_id = 'cs_dev_…'`
- `external_identities.external_user_id = NULL`
- `employees.hris_id = NULL`

**Fix:** exempt block 6 for `_test_companies` too, or exclude those tables/columns from the merge engine.

### 2. `scripts/sync_tenants.py:189` — `companies` has no `updated_at`, LWW merge degenerates to "dev always wins"
**Status:** fixed, not yet applied — new migration `server/alembic/versions/compupdat01_add_companies_updated_at.py` adds `companies.updated_at` + a scoped `BEFORE UPDATE` trigger (companies-only; no other table in the repo uses a DB trigger for this, chosen specifically so no admin-route callsite can forget to set it, unlike every other `updated_at` column here). `sync_tenants.py` needed no code change — `decide_row`/`merge_plan` already key off `"updated_at" in cols` generically. **Run `./scripts/migrate-dev.sh` then `./scripts/migrate-prod.sh` to close this.**

Confirmed on dev: `information_schema` returns `is_test` but no `updated_at` for `companies`. Every difference on the company row hits the `has_updated_at=False` branch → `update → prod`. Any prod-side admin edit to a test tenant (`enabled_features`, `status`, `industry`, and `is_test` itself) is silently reverted on the next deploy — including *unmarking* a tenant as test on prod, which never sticks. Defeats the "edit on EITHER side, this converges both" premise for the one table that gates everything.

### 3. `server/app/core/routes/admin/_shared.py:240` — deploy-ordering hazard
**Status:** fixed — `_BUSINESS_REGISTRATION_SELECT` (constant) replaced with `_business_registration_select(conn)` (async), which checks `information_schema.columns` once (process-lifetime cache, mirrors `_get_required_categories`' pattern) and renders `comp.is_test` or a literal `FALSE AS is_test` accordingly. `_row_to_registration`'s `row.get("is_test")` is now genuinely reachable instead of dead defensive code. Both callers in `invites.py` updated.

`_BUSINESS_REGISTRATION_SELECT` now hard-selects `comp.is_test`, while `_row_to_registration` (line 541) uses `row.get("is_test") or False` as if the column might be absent. The defensive `.get()` is unreachable — the SQL fails first. Deploying this backend before `migrate-prod.sh` applies `testacct01` 500s `/admin/business-registrations` (list *and* detail, both callers in `invites.py`). Exactly the `UndefinedColumnError` drift class CLAUDE.md warns about.

## Medium-High

### 4. `scripts/refresh-dev-from-prod.sh:141` — `--require-push` does not cover the failure it exists to prevent
**Status:** fixed — `sync-test-tenants.sh` now fails (`exit 3`) when `--require-push` is combined with a merge-engine exit 2 (drift/warnings, possibly empty output files), instead of quietly falling through to "Nothing to push to prod." Covers both drift paths in `run_sync` (the early `companies`-drift return and the no-tenant-ids return), since both surface as exit 2.

Hardens only three shell skip paths (lock/dev-down/tunnel). If `sync_tenants.py` legitimately produces an *empty* `sync_to_prod.sql` — `companies` schema-drifted (exit 2, the state right now: dev has `is_test`, prod doesn't) or no `is_test` rows on either side (exit 0) — the wrapper logs "Nothing to push to prod" and exits 0. The refresh then proceeds to clone prod over dev, destroying the dev-only test-tenant edits the guard was added to protect.

### 5. `scripts/sync-test-tenants.sh:173` — only engine exit `1` treated as failure
**Status:** fixed — condition inverted to `[[ "$ENGINE_EXIT" != "0" && "$ENGINE_EXIT" != "2" ]]`, so 137/130/any other crash exit now fails loudly instead of silently reusing stale `sync_to_prod.sql` from a previous run.

## Medium

### 6. `scripts/sync_tenants.py:210` / `:276` — undo file can delete pre-existing prod rows
**Status:** fixed — `emit_undo_for` takes a `descended` flag; for an ascended row with no reachable preimage it now emits a `--` comment explaining why it's skipping, instead of a `DELETE`. Descended rows are unaffected (their reachability is equivalent to real DB presence, since both sides walk the same tenant-owned FK graph). Two new tests (`test_undo_for_ascended_insert_skips_delete_when_not_reachable`, `test_undo_for_ascended_update_still_restores_preimage`).

Ascended rows are emitted as untargeted `ON CONFLICT DO NOTHING`, and `target_preimage` is `None` whenever the row is absent from the target *snapshot* — not the target *DB*. A `users` row reachable from dev's tenant walk but not from prod's (e.g. prod's `ir_incidents.assigned_to` was cleared) inserts as a no-op, yet `emit_undo_for` emits `DELETE FROM "users" WHERE "id" = …`. Running the archived undo then deletes a live prod user the sync never created — contradicting the "correct even when the row already existed" comment.

### 7. `scripts/seed-prod.sh:157` — GUARD 2 (bounce-storm guard) weakened by the new `lit()`
**Status:** fixed — replaced the naive `sed 's/--.*$//'` with `strip_sql_comments_outside_literals()` (a small embedded `python3` pass that walks single-quoted literals and only treats `--` as a comment-start outside of them). `$STRIPPED` (GUARD 2) and `$STRIPPED_NOLIT` (GUARDs 1/1b) both derive from it now. Verified against the exact repro: `E'reported 3--4 times...'` no longer eats the trailing `witness@realdomain.com` on the same line.

GUARDs 1/1b moved to `STRIPPED_NOLIT`, but GUARD 2 still scans `STRIPPED`, which is only comment-stripped. Now that `lit()` collapses multi-line prose into single-line `E''` strings, a literal `--` anywhere in a narrative field (e.g. an incident description "reported 3--4 times") truncates the *entire remainder of the row* for the email scan, hiding a later `@realdomain.com` witness email. Pre-`lit()`-change, multi-line values pushed later columns onto separate physical lines and limited the blast radius.

### 8. `server/app/core/routes/admin/companies.py:556` — `is_test` has no server-side guard
**Status:** fixed — `update_company_admin` now 400s setting `is_test=true` when the company has an active `mw_subscriptions` row (real Stripe money — the unambiguous "currently paying" signal; doesn't false-positive on invoiced bespoke/Pro contracts, which have no subscription row). Every `is_test` flip is logged (`logger.info`, admin id + company id). Frontend `window.confirm` copy now names the anonymization carve-out, and the catch block surfaces the real backend error (`ApiError.message`) instead of a generic toast.

### 9. `scripts/sync-test-tenants.sh:224` — `admin_updates` export doesn't receive the resolved dev DSN
**Status:** fixed — `export-dev-data.py` call now passes `--dsn "$DEV_URL"`, the same resolved DSN the merge engine used.

The wrapper carefully resolves `DEV_URL` from `$DATABASE_URL` / `server/.env` and passes it to `sync_tenants.py`, but `export-dev-data.py` is invoked without `--dsn`, so it falls back to `$DEV_DATABASE_URL` (usually unset) then to the hardcoded `postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha`. If the operator's dev DSN differs (different db name/port), the changelog is read from a *different database* than the merge engine just diffed — and pushed to prod.

## Low

### 10. `scripts/sync_tenants.py:456` — undo pre-images are email-normalized
**Status:** fixed — raw (pre-scrub) copies of both snapshots (`dev_snap_raw`/`prod_snap_raw`) are captured before `normalize_emails` mutates them, and `target_preimage` now comes from the raw copy via a `raw_row()` lookup. `source_row` (the value actually written to target) is intentionally left on the normalized/scrubbed value — a real-looking email must never land on prod (GUARD 2). Keys are stable across raw/normalized snapshots since `normalize_emails` only replaces `RowSnap.row`, never the dict key.

`normalize_emails` rewrites both snapshots in place *before* `merge_plan`, so `p.prod_row` (used as the undo pre-image) holds scrubbed addresses. Restoring from the archived undo writes `local+domain@example.com` rather than what prod actually had.

### 11. `scripts/sync-test-tenants.sh:226` — `admin_updates already in sync` is dead code
**Status:** fixed (edge case) — `POST_HOOKS[table]` in `export-dev-data.py` is now gated on `text_rows` being non-empty. Note: `--table admin_updates --mode update` re-applies every current row on every run by design (dev is treated as source of truth for this changelog, not diffed), so "already in sync" is realistically only reachable when the table is genuinely empty — which is also the only case where it's actually true. Not a behavior change to the always-push design, just removes the one case where the message was provably wrong.

### 12. `scripts/sync_tenants.py:158` — `parse_ts` can raise on mixed timestamp types
**Status:** fixed — the `dev_ts != prod_ts` / `dev_ts > prod_ts` comparisons in `decide_row` are wrapped in `try/except TypeError`, falling back to the existing "tied or unusable — dev wins, WARN" path instead of crashing the whole sync mid-plan.

Drift detection compares column *names* only. If one side's `updated_at` is `timestamptz` and the other `timestamp` (a plausible outcome of two hand-applied migrations), `parse_ts` yields one aware and one naive datetime and `dev_ts > prod_ts` raises an uncaught `TypeError`, aborting the whole sync mid-plan.

### 13. `scripts/seed-prod.sh:68` — `-h` output truncated
**Status:** fixed — range updated to `sed -n '2,41p'`. Verified `./scripts/seed-prod.sh -h` now prints the full "Guardrails" section.

## Verified as correct (no action needed)

- `lit()` E-string escaping order and `sed "s/'[^']*'/''/g"` literal stripping handle doubled quotes correctly
- `_test_companies` temp table survives the `COMMIT` for the post-txn leak check
- `testacct01` is a clean single-child migration head
- `CompanyProfileUpdate` + `exclude_none=True` correctly propagates `is_test: false`
- `api.patch` / `useToast` signatures match repo conventions
- No global `updated_at` triggers exist, so the LWW ping-pong risk is limited to finding #2's static case
