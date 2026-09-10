# Scheduling legality reads the codified compliance catalog (CA + NY seeded, nothing hardcoded)

## Context

Po Coffee Co's NY location shows *"Legality NOT verified for NY — Matcha has no researched scheduling thresholds"*. Verified in dev + prod (read-only):

1. `schedule_compliance._SCHEDULING_RULES` hardcodes `US` + `CA` in Python; CA works only because of that table.
2. The scheduler's other inputs (`schedule_rule_extractions`, `schedule_break_rule_sets`) are **0 rows in prod**; NY has 1 codified catalog row (a federal § 207 restatement), nothing for N.Y. Lab. Law § 162.
3. `jurisdiction_rule_status` never consults the structured break store, so NY could never flip to verified.

Direction (user): the **codified compliance catalog (`jurisdiction_requirements`) is the single source of truth** for compliance data — scheduling and every future feature query it, never a per-feature copy or a code table. Seed CA + NY (+ federal) scheduling rows now; later changes are catalog updates (the codified `source_url` is the real source), and the scheduler does nothing but query. Per-organization applicability confirmation (round 1) stays.

## Design

```
jurisdiction_requirements (codified: statute_citation + citation_verified_at + citation_item_id, source_url,
  effective_date, last_verified_at, applicable_industries, metadata.schedule_rule = {break_periods, thresholds})
        │  direct query, jurisdiction chain walk (city → county → state → US), codified gate
        ▼
scheduler readers: resolve_break_rules (meal/rest timing) · _catalog_thresholds (OT / min-rest / minor caps)
        ▼
coverage model per domain (meal_break / overtime / rest) with provenance → jurisdiction sentence → compliance_status
```

Retired from the query path: `_SCHEDULING_RULES`, `is_curated_state`, `schedule_rule_extractions` reads, `schedule_break_rule_sets` reads. Those two tables and the Gemini extraction service stay on disk (no DROP DDL) but nothing runtime reads them; the admin Schedule Rules tab becomes a read-only view of what the catalog says.

### Catalog contract — `metadata.schedule_rule` (validated on seed + on read)
```json
{"break_periods": {"meal_periods": [...], "rest_periods": [...]},        // exact payload schema of _rules_from_payload
 "thresholds": {"weekly_ot_hours": 40, "daily_ot_hours": null, ...}}     // keys ⊆ RULE_KEYS; null = "law imposes no such limit" (NO_CAP)
```
Row-level fields carry provenance: `statute_citation`, `source_url`, `effective_date`, `expiration_date`, `last_verified_at`, `citation_verified_at`. A key absent from every row on the chain = "not researched" (never silently clear). Industry scoping = `applicable_industries` (`{}`/NULL = general; e.g. `{manufacturing}`), matched against `LocationReadiness.industry_code`. Nearest jurisdiction on the chain wins per `requirement_key`; federal rows (`US` jurisdiction) are the baseline.

## A. Migration — `server/alembic/versions/empsched24_catalog_schedule_rules.py` (down `empsched23`)

```sql
-- confirmations key on the catalog scope instead of a rule-set row
ALTER TABLE company_schedule_break_rule_confirmations
  ALTER COLUMN rule_set_id DROP NOT NULL,
  ADD COLUMN IF NOT EXISTS source_key TEXT,             -- 'catalog:<jurisdiction_id>:<industry|general>'
  DROP CONSTRAINT company_schedule_break_rule_confirmations_unique,
  ADD CONSTRAINT company_schedule_break_rule_confirmations_source_check
    CHECK ((rule_set_id IS NOT NULL) <> (source_key IS NOT NULL));
CREATE UNIQUE INDEX company_schedule_break_rule_confirmations_source_unique
  ON company_schedule_break_rule_confirmations (company_id, location_id, source_key, context_hash)
  WHERE source_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jr_schedule_rule_block
  ON jurisdiction_requirements (jurisdiction_id, category) WHERE metadata ? 'schedule_rule';
```
Downgrade drops the index/column/check and restores the old unique. Prod DDL only via `./scripts/migrate-prod.sh` after the user's go-ahead.

## B. Backend

### B1. New `server/app/core/services/compliance_service/_schedule_rules.py` — the shared catalog read (reusable by any feature)
```python
SCHEDULE_RULE_CATEGORIES = ("meal_breaks", "overtime", "scheduling_reporting", "minor_work_permit")

@dataclass(frozen=True)
class CatalogScheduleRow:  # one codified row carrying a schedule_rule block
    requirement_id: UUID; jurisdiction_id: UUID; depth: int; category: str; requirement_key: str
    statute_citation: str; source_url: str|None; effective_date: date|None; expiration_date: date|None
    last_verified_at: datetime|None; citation_verified_at: datetime|None
    applicable_industries: tuple[str, ...]; block: dict

async def fetch_schedule_rule_rows(conn, *, jurisdiction_id: UUID, industry_code: str|None, on: date,
                                   codified_only: bool = True) -> list[CatalogScheduleRow]
# WITH RECURSIVE chain (id, parent_id, depth) FROM jurisdictions WHERE id=$1 … ;
# SELECT … FROM jurisdiction_requirements jr JOIN chain c ON c.id=jr.jurisdiction_id
# WHERE jr.status='active' AND jr.category = ANY($2) AND jr.metadata ? 'schedule_rule'
#   AND (jr.effective_date IS NULL OR jr.effective_date <= $3) AND (jr.expiration_date IS NULL OR jr.expiration_date >= $3)
#   AND (jr.applicable_industries IS NULL OR jr.applicable_industries = '{}' OR $4 = ANY(jr.applicable_industries))
#   {codified_sql('jr')}
# ORDER BY c.depth ASC, (cardinality(jr.applicable_industries) > 0) DESC, jr.effective_date DESC NULLS LAST

def parse_schedule_rule_block(metadata: dict|str|None, citation: str) -> dict|None
# validate_break_rule_payload(block["break_periods"], citation); thresholds keys ⊆ RULE_KEYS with _RANGES bounds; ValueError on bad shape

def merge_thresholds(rows) -> dict            # nearest depth wins per key; None → NO_CAP; + "citations", "_meta"[key] = provenance
def merge_break_periods(rows) -> tuple[list[BreakRule], list[dict]]   # nearest depth wins per requirement_key; industry row beats general at same depth
def source_key(jurisdiction_id, industry_code) -> str   # 'catalog:<jid>:<industry|general>'
```
Also: `fetch_schedule_rule_rows(..., codified_only=False)` is what the coverage model uses to say *"row exists but is not codified yet"*.

### B2. `schedule_compliance.py`
- Delete `_SCHEDULING_RULES`, `is_curated_state`. Keep `NO_CAP`, `SCHEDULE_CATEGORIES`, `_EXTREME_SHIFT_HOURS`, every `check_*`, `evaluate_shift_for_employee`, `get_schedule_statutes`.
- `rules_for_state(state, db_rules=None)` → `rules_from_catalog(thresholds: dict|None) -> dict` (pure merge already done by B1; keeps `citations`/`_minor_block_grade`). Keep the old name as a thin alias for one release so `hr_pilot_corpus` and tests keep importing.
- `rules_summary(thresholds)` → `source ∈ catalog | unmapped`, drops `_`-prefixed keys, adds `provenance: {key: {citation, source_url, effective_date, last_verified_at}}`.
- Minor caps from the catalog are advisory unless the block sets `"block_grade": true` per key (replaces `schedule_rule_extractions.block_grade`).

### B3. `shift_compliance.py`
- `_approved_db_rules(conn, state)` → `_catalog_thresholds(conn, company_id, location_id, on) -> tuple[dict|None, bool]` via B1 (`fetch_schedule_rule_rows` + `merge_thresholds`); 60 s cache keyed `(jurisdiction_id, industry_code, on)`; fetch failure → `(None, True)` (fail visible). Old name kept as alias for the route re-export in `routes/employee_schedule/_compliance.py:25`.
- `check_shift_compliance` uses it; the curated skip (`:492`) is deleted.
- `jurisdiction_rule_status(conn, company_id, location_id, shift_date=None) -> {state, status, coverage}` delegates to B5. Same module-level name stays imported by `week_builder`, `planning_inputs`, `schedule_chat` (tests monkeypatch those).
- Law panel `routes/employee_schedule/shifts.py:386-409` and `pilots/hr_pilot_corpus/fetch.py:441-464` call `_catalog_thresholds` (delete the corpus's inline copy of the extraction query).

### B4. `schedule_break_rule_store.py`
- `resolve_break_rules(...)` reads the catalog: `readiness` → `fetch_schedule_rule_rows` → `merge_break_periods`; `ResolvedBreakRules.source ∈ catalog | catalog_confirmation_required | catalog_rejected | unmapped | unavailable`; `rule_set_ids` → `(uuid5(NAMESPACE_URL, source_key),)` (stable, so `guidance_ruleset_hash` / stagger keep working); `expected_rules` + `_expected_rules_metadata` now carry `source_key`, `requirement_ids`, `citation`, `authority_url`, `effective_from = max(effective_date)`, `last_verified_at`.
- `_applicability_context_hash(... source_key, requirement_ids, rules)` replaces `rule_set_id`; `record_break_rule_applicability_decision(..., source_key, context_hash, decision, actor_user_id)`; confirmations written with `source_key` (rule_set_id NULL). Grandfathered rows (rule_set_id-based) are ignored on the new path (there are none in prod).
- Delete `_legacy_rules`, `_threshold`'s DB branch, `is_curated_state` use, the `schedule_break_rule_sets` query. An explicit `rest_periods: []` on the chosen meal row is the reviewed "no rest period" answer.
- `MAX_SHIFT_BREAK_MINUTES`, `_rules_from_payload`, `validate_break_rule_payload`, `lock_schedule_break_rule_guidance` unchanged.

### B5. New `server/app/matcha/services/scheduling/schedule_rule_coverage.py`
```python
DOMAINS = ("meal_break", "overtime", "rest")
DOMAIN_CATEGORY = {"meal_break": "meal_breaks", "overtime": "overtime", "rest": "scheduling_reporting"}
def domain_status(*, domain, resolved: ResolvedBreakRules|None, thresholds: dict|None,
                  uncodified: list[CatalogScheduleRow], industry_code) -> dict          # pure
async def resolve_rule_coverage(conn, company_id, location_id, shift_date=None) -> dict
# {"state", "jurisdiction_id", "industry_code", "status": catalog|partial|unmapped|unavailable,
#  "domains": {d: {"status": verified|missing|pending_confirmation|unavailable,
#                  "citation", "authority_url", "effective_from", "expires", "last_verified_at",
#                  "missing_reason": location_unmatched|catalog_unresearched|catalog_not_codified|
#                                    organization_rejected|None}}}
```
- `meal_break` ← `resolve_break_rules`: `catalog` → verified; `catalog_confirmation_required` → pending_confirmation; `catalog_rejected` → missing/organization_rejected; `unmapped` → missing (`catalog_not_codified` if an uncodified `meal_breaks` block row exists on the chain, else `catalog_unresearched`); `unavailable` → unavailable.
- `overtime` ← thresholds have `weekly_ot_hours` **and** `daily_ot_hours` determined (number or NO_CAP) from a state-or-lower row (federal alone → missing, reason names daily OT).
- `rest` ← the chosen meal row's block has a `rest_periods` key **and** `min_rest_between_shifts_hours` determined.
- Overall: all verified → `catalog`; some → `partial`; any unavailable → `unavailable`; else `unmapped`. Invariant: a tenant confirmation only lifts `pending_confirmation`; it never verifies research.

### B6. `schedule_review.py`
- `jurisdiction_message(info)` renders from `coverage.domains`:
  - `catalog`: *"Scheduling law for NY is on file — meal breaks: N.Y. Lab. Law § 162 (verified 2026-09-10); overtime: 12 NYCRR § 142-2.2 (verified …); rest: no statewide rest-period statute (verified …)."*
  - `partial`: verified clause + *"NOT verified — meal breaks: reviewed rules await your organization's applicability confirmation; rest: not in the compliance catalog yet."* + existing "Confirming means you've checked … yourself."
  - `unmapped` / `unavailable` sentences unchanged (tests pin them).
- `compliance_status_for`: `unavailable`→`unavailable`; status ≠ `catalog` → `unmapped`; else advisory/verified. `partial` is never `verified`. `coverage` flows through `build_review`, `build_week_draft_review`, `summarize_review`, `compact_review`.

### B7. `partial` wiring
`schedule_chat.py:1453, :2977` rank `{"unavailable":3,"unmapped":2,"partial":1,"catalog":0}`; `:1064` `rules_unmapped = status in ("unmapped","unavailable","partial")`; `_jurisdiction_lines` (`:3203`) early-return only on `"catalog"`; `week_builder.py:1342` finding kind `jurisdiction_partial`. `huume/prompt.py` unchanged (keys on `compliance_status`).

## C. Routes + client

- `routes/employee_schedule/shifts.py:241-302` body `{source_key, context_hash, decision}` (rule_set_id removed); audit entity `catalog_schedule_rule`.
- `routes/admin/schedule_rules.py`: `GET /schedule-rules/overview` and `GET /schedule-rules/{state}` return catalog-derived rows (`fetch_schedule_rule_rows(codified_only=False)` for the state jurisdiction: requirement_key, citation, source_url, verified flags, block); extract/approve/reject/bulk/block-grade endpoints return 410 with a message pointing to the catalog (extraction service left on disk, unmounted).
- `client/src/pages/admin/JurisdictionData/ScheduleRulesTab.tsx`: read-only table (state → rows → thresholds + rendered periods, codified badge, source link); remove extract/approve controls.
- `client/src/api/employees/employeeSchedule.ts:133-140` + `ShiftInspector.tsx:120-141`: send `source_key`; show `citation` + `authority_url` link + `effective_from` in the confirm card.
- Types `client/src/types/employeeSchedule.ts` `ScheduleJurisdiction = { state; status: 'catalog'|'partial'|'unmapped'|'unavailable'; message; coverage?: ScheduleRuleCoverage }`; mirror in `client/src/work/types.ts` (3 copies). Tones: `InputsRail.tsx:167` catalog emerald / partial amber + 3-line domain list under the sentence; `ScenariosStrip.tsx:38` add partial; `ScheduleLawPanel.tsx` `SOURCE_LABEL = {catalog, unmapped}` + provenance links; `reviewShape.ts` default stays `unmapped`.

## D. Seed data (catalog rows; data only; via `./scripts/seed-prod.sh <pack> --dev | --dry-run | apply | --undo`)

`scripts/seed/schedule_law_ca_us.sql` + `.undo.sql`, `scripts/seed/schedule_law_ny.sql` + `.undo.sql`. Pattern = `meal_break_timing.sql`: `INSERT … ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET metadata = COALESCE(jr.metadata,'{}') || EXCLUDED.metadata, statute_citation = COALESCE(jr.statute_citation, EXCLUDED.statute_citation), source_url = COALESCE(jr.source_url, EXCLUDED.source_url), effective_date = COALESCE(jr.effective_date, EXCLUDED.effective_date) WHERE jr.metadata->'schedule_rule' IS NULL` (fill-NULL-only; undo = `metadata - 'schedule_rule'` and delete rows the pack created). Category ids from `compliance_categories.slug`; `regulation_key` set so codification can bind.

**CA / US (moving the accurate code values; jurisdictions `565064eb-…8fccb`, US federal row):**
- CA `meal_breaks:meal_break` (Cal. Lab. Code § 512(a); Brinker (2012) 53 Cal.4th 1004; `leginfo.legislature.ca.gov … sectionNum=512`): meal_periods `[{ordinal 1, 30, trigger 300 gt, deadline_offset 300, waiver {allowed true, max_shift_minutes 360}}, {ordinal 2, 30, trigger 600, deadline 600}]`; rest_periods `[{10 paid, trigger 210, count_bands [{min_minutes 360,count 2},{600,3}], citation "Cal. Lab. Code § 226.7(b); IWC Wage Order § 12"}]`; thresholds `{meal_break_after_hours 5, meal_break_minutes 30, second_meal_after_hours 10, meal_break_earliest_after_hours null, meal_waiver_max_hours 6, min_rest_between_shifts_hours null}`.
- CA `overtime:daily_weekly_overtime` (§ 510): `{daily_ot_hours 8, daily_doubletime_hours 12, weekly_ot_hours 40}`.
- CA `minor_work_permit:hour_limits_16_17` (§ 1391, exists): `{minor_u16_day_hours 8, minor_16_17_day_hours 8, "block_grade": {…: true}}`.
- US `overtime:daily_weekly_overtime` (29 U.S.C. § 207(a), exists): `{weekly_ot_hours 40}`; US `minor_work_permit:child_labor_hours` (29 C.F.R. § 570.35, create): `{minor_u16_day_hours 8, minor_u16_week_hours 40, minor_16_17_day_hours null, minor_16_17_week_hours null, block_grade true}`.

**NY (research now against primary sources; jurisdiction `3de84785-1a3c-402b-ae44-1e6dca6f6104`, same id in dev + prod):**
1. `meal_breaks:meal_break` — N.Y. Lab. Law § 162(2)/(3)/(4), `https://www.nysenate.gov/legislation/laws/LAB/162`, NYSDOL meal-period guidelines (`dol.ny.gov`): meal_periods `[{ordinal 1, 30, trigger 360 gt, shift_spans_window 11:00–14:00, window 11:00–14:00, cite § 162(2)}, {ordinal 1, 45, trigger 360 gt, shift_start_window_from 13:00 before 06:00, recommend_midpoint, cite "§ 162(4); NYSDOL guideline permits ≥30 min absent hardship"}, {ordinal 2, 20, trigger 0 gte, shift_starts_before 11:00, shift_ends_after 19:00, window 17:00–19:00, cite § 162(3)}]`; rest_periods `[]` (no adult rest-period statute); thresholds `{meal_break_after_hours 6, meal_break_minutes 30, second_meal_after_hours null, meal_break_earliest_after_hours null}`.
2. `meal_breaks:meal_break_factory` — § 162(1)/(4), `applicable_industries='{manufacturing}'`, 60/60/20.
3. `overtime:daily_weekly_overtime` (exists, cited to § 207) — block `{weekly_ot_hours 40, daily_ot_hours null, daily_doubletime_hours null}`; `statute_citation`/`source_url` → 12 NYCRR § 142-2.2 / § 146-1.4 (fill-NULL-only; note if already set).
4. `scheduling_reporting:min_rest_between_shifts` — `{min_rest_between_shifts_hours null}`; description: NYC Admin. Code § 20-1231 clopening handled by `fair_workweek.py`.
5. `minor_work_permit:minor_hours` — N.Y. Lab. Law §§ 170–173 (non-school): `{minor_u16_day_hours 8, minor_u16_week_hours 40, minor_16_17_day_hours 8, minor_16_17_week_hours 48}`.
6. `jurisdiction_vertical_coverage (NY, 'general', category, 'covered')` for the 4 categories, `ON CONFLICT DO NOTHING`.

Golden fixtures `compliance_evals/fixtures/golden/us_ca.json`, `us_ny.json`, `us_federal.json` gain the numeric facts above, so the eval suite polices the catalog values from now on.

## E. Runbook

Dev: `./scripts/migrate-dev.sh` → both packs `--dev` → codify the NY rows (`POST /admin/jurisdictions/requirements/{id}/codify`, citation = row's `statute_citation`; CA/US rows are already codified) → add an NY location to Po Coffee Co in dev (mirrors prod) → open Schedule Pilot: rail shows *partial* ("await your organization's applicability confirmation") → confirm in ShiftInspector → *catalog*; TX location → *unmapped* with `catalog_unresearched`; CA locations still *catalog*.

Prod (each step waits for the user; exact commands handed over then): `./scripts/migrate-prod.sh` → `./scripts/seed-prod.sh scripts/seed/schedule_law_ca_us.sql --dry-run` → apply → same for `schedule_law_ny.sql` → codify the NY rows in Admin → Jurisdiction Data → deploy backend + frontend → Po Coffee Co NY location: confirm applicability. Order matters: seed + codify **before** the backend swap so CA never reads *unmapped* (old code ignores the new metadata).

Future updates = editing the codified catalog row (or the daily source re-verification writing it); the scheduler picks it up within the 60 s cache.

## F. Tests (`cd server && ./venv/bin/python -m pytest tests -q`; client `npx tsc -p tsconfig.app.json --noEmit` + vitest)

New
- `tests/core/test_catalog_schedule_rules.py` — `test_parse_block_validates_periods_and_thresholds`, `test_nearest_jurisdiction_wins_per_key`, `test_industry_row_beats_general_at_same_depth`, `test_null_threshold_is_no_cap`, `test_absent_key_is_not_researched`.
- `tests/employee_schedule/test_ny_schedule_law.py` — NY block from the seed pack → `evaluate_break_plan`: `test_noonday_meal_for_shift_containing_11_to_14`, `test_shift_ending_1330_owes_no_noonday_meal`, `test_night_shift_from_13_gets_45_min_at_midpoint`, `test_extra_20_min_between_17_and_19`, `test_factory_variant_60_minutes_for_manufacturing`, `test_stagger_places_ny_breaks_inside_windows`.
- `tests/employee_schedule/test_schedule_rule_coverage.py` — `test_tx_all_missing_is_unmapped_with_catalog_unresearched`, `test_uncodified_row_reads_catalog_not_codified`, `test_two_of_three_verified_is_partial`, `test_pending_confirmation_is_never_verified`, `test_fetch_failure_is_unavailable`, `test_no_rule_min_rest_counts_as_verified`, `test_ca_regression_from_catalog_rows`.
- `tests/seed_packs/test_schedule_law_ny_pack.py`, `test_schedule_law_ca_us_pack.py` — data-only, NY id literal, fill-NULL guards, every block passes `parse_schedule_rule_block`, `manufacturing` only on the factory row, undo present.
- `test_schedule_review.py` — `test_catalog_message_names_each_domain_source_and_date`, `test_partial_message_lists_missing_reasons_and_is_unmapped`.

Change/delete: `test_schedule_compliance.py` CA pins (`test_is_curated_state`, `test_db_rules_ignored_for_a_code_curated_state`, `test_curated_state_minor_caps_still_always_block`, `test_rules_summary_source_marker`); `test_schedule_rule_extraction.py` keeps pure-function tests, drops `CODE_CURATED_STATES`; `test_shift_compliance.py::_status` → coverage shape; `test_schedule_break_rule_store.py` FakeConn → catalog query (`test_approved_structured_rule_beats_legacy_fallback`, `test_ca_legacy_rule_is_adapted_until_structured_rows_exist`, extraction-fallback tests rewritten as catalog cases; applicability tests → `source_key`); `test_schedule_review.py` `"curated"` → `"catalog"`; `test_hr_pilot_corpus.py:879`; `test_break_rule_confirmations_migration.py`; client `ReviewPane.test.tsx`, `InputsRail.test.tsx` (+partial), `reviewShape.test.ts`, `ShiftInspector.breaks.test.tsx`, `ScheduleRulesTab` tests.

## G. Risks / flags
1. § 162(2) "extending over the noon day meal period" modeled as containment (start ≤ 11:00, end ≥ 14:00) per ticket wording; the scalar `meal_break_after_hours 6` still flags any >6 h NY shift with <30 min. Flag for counsel in the PR.
2. NY overtime row currently codified to § 207 — fill-NULL-only won't overwrite its citation; note in PR whether to re-codify against 12 NYCRR.
3. Codified gate needs NY rows codified in prod (admin clicks) before NY reads verified; the coverage sentence says `catalog_not_codified` until then, so nothing is silent.
4. Deploy before seed+codify → CA reads *unmapped* until data lands; runbook orders data first.
