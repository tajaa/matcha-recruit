# Expand Government API Coverage — Realistic Scope

## Context

Current state: 94 API rows (all federal/US jurisdiction, 14 categories). 1,258 state-level + 586 city-level rows from Gemini. **89% of data is state/city-specific enacted law** — no API provides "California requires 40 hours paid sick leave" or "San Francisco minimum wage is $18.67" in structured form. APIs cannot replace Gemini for state/city data.

**What APIs CAN do:**
- Provide **authoritative federal baseline** (eCFR) -> ~150 new tier_1 rows across all 40 categories
- Fix **quality issues** in existing Federal Register data (mismatched categories, no pagination)
- Add **enforcement signals** per state (DOL) -> what's actually being enforced
- Add **legislative tracking** (OpenStates) -> bills in progress, early warning of changes
- Let Gemini focus on **state/city interpretation** instead of duplicating federal facts

**What APIs CANNOT do:**
- Replace state-specific enacted employment law (leave policies, sick leave accrual, meal break rules, etc.)
- Replace city-level ordinances
- Replace healthcare-specific state licensing requirements

---

## Phase 1: Package structure + shared infra

Create `server/app/core/services/government_apis/` package, extract from `federal_sources.py`:

```
government_apis/
  __init__.py
  _base.py               # Shared: semaphore, retry, requirement builder, dedup
  federal_register.py    # Extracted + fixed FR logic
  ecfr.py                # NEW: eCFR API (no key needed)
  dol_enforcement.py     # NEW: DOL WHD/OSHA enforcement
  openstates.py          # NEW: State bill tracking (needs free key)
  cms.py                 # Extracted CMS logic
  congress.py            # Extracted Congress.gov logic
  orchestrator.py        # Main entry, replaces fetch_federal_sources()
```

`_base.py` extracts `_SEMAPHORE`, `_TIMEOUT`, `_get_with_retry()` and adds:
- `build_requirement_dict()` -- standardized requirement shape
- `dedup_by_key(reqs, key_fn)` -- replaces fragile `title[:100]` dedup

`federal_sources.py` becomes thin backward-compat wrapper.

---

## Phase 2: Add `cfr_parts` to category registry

**File:** `server/app/core/compliance_registry.py`

Add `cfr_parts` list to each entry in `CATEGORY_FEDERAL_REGISTER_AGENCIES`. Key ones:

| Category | CFR Parts |
|----------|-----------|
| minimum_wage | 29 CFR 516, 531, 780 |
| overtime | 29 CFR 541, 778, 785 |
| leave | 29 CFR 825 (FMLA) |
| workplace_safety | 29 CFR 1903, 1904, 1910 |
| anti_discrimination | 29 CFR 1600-1608 |
| hipaa_privacy | 45 CFR 160, 164 |
| billing_integrity | 42 CFR 1001, 1003 |
| pharmacy_drugs | 21 CFR 1301-1321 |
| clinical_safety | 42 CFR 482-485 |

---

## Phase 3: eCFR API integration (biggest win, no key needed)

**File:** `server/app/core/services/government_apis/ecfr.py`

**API:** `https://www.ecfr.gov/api/versioner/v1/` -- free, no key

For each category's `cfr_titles` + `cfr_parts`:
1. Fetch structure -> part heading + section headings
2. Fetch amendments (last 365 days) -> flag recently changed parts
3. Build requirement with `regulation_key` like `"29_cfr_541"` (maximally stable -- `_compute_requirement_key` already prefers it, line 2773)
4. Upsert with `source_tier="tier_1_government"`, `research_source="official_api"`

**This gives us ~150 tier_1 rows across all 40 categories at federal level.** These serve as the authoritative federal baseline that state/city Gemini research builds on.

---

## Phase 4: Fix existing Federal Register

**File:** `server/app/core/services/government_apis/federal_register.py`

1. **Per-category fetch with keyword filter** -- stops DOJ immigration docs mapping to "antitrust"
2. **Pagination** -- follow `next_page_url`, up to 200 docs per category
3. **Dedup by `document_number`** -- stable FR doc ID instead of `title[:100]`

---

## ~~Phase 5: DOL enforcement data~~ DROPPED

**Status:** NOT VIABLE. `enforcedata.dol.gov` is a React/Drupal SPA with no public JSON API.
All endpoints return HTML. The old `data.dol.gov` and `developer.dol.gov` APIs are dead/redirecting.
Would require scraping, not API calls. Not worth the fragility.

---

## Phase 6: OpenStates for legislative tracking

**File:** `server/app/core/services/government_apis/openstates.py`

**API:** `https://v3.openstates.org/bills` -- free key, 6 req/min

Tracks state bills in progress for labor categories. Creates rows like:
- `"[State Bill] CA SB-1234 - Fair Scheduling Act: Status: In Committee"`
- `source_tier="tier_2_official_secondary"` (aggregator of official data)
- Runs as background task (slow rate limit)

**Early warning for legislative changes**, not enacted law.

---

## Phase 7: Orchestrator + routes

**File:** `server/app/core/services/government_apis/orchestrator.py`

Routes by jurisdiction type:
- **Federal** (state="US"): eCFR + Federal Register + CMS + Congress.gov
- **State** (city='', state!='US'): DOL enforcement + OpenStates
- **City**: inherits state-level

**File:** `server/app/core/routes/admin.py`
- Existing endpoints delegate to orchestrator
- New `POST /admin/jurisdictions/batch-government-fetch` for state-level batch runs

---

## Files to modify/create

| File | Action |
|------|--------|
| `server/app/core/services/government_apis/__init__.py` | NEW |
| `server/app/core/services/government_apis/_base.py` | NEW |
| `server/app/core/services/government_apis/ecfr.py` | NEW ~200 lines |
| `server/app/core/services/government_apis/federal_register.py` | NEW -- extracted + fixed |
| ~~`server/app/core/services/government_apis/dol_enforcement.py`~~ | ~~DROPPED -- no public API~~ |
| `server/app/core/services/government_apis/openstates.py` | NEW ~200 lines |
| `server/app/core/services/government_apis/cms.py` | NEW -- extracted |
| `server/app/core/services/government_apis/congress.py` | NEW -- extracted |
| `server/app/core/services/government_apis/orchestrator.py` | NEW ~150 lines |
| `server/app/core/services/federal_sources.py` | MODIFY -- thin wrapper |
| `server/app/core/compliance_registry.py` | MODIFY -- add cfr_parts |
| `server/app/core/routes/admin.py` | MODIFY -- orchestrator + batch endpoint |
| `server/app/config.py` | MODIFY -- add OPENSTATES_API_KEY |

No schema changes needed.

---

## Implementation order

1. Phase 1 -- Package structure + _base.py
2. Phase 2 -- cfr_parts registry mappings
3. Phase 3 -- eCFR integration (biggest win, no key, confirmed working)
4. Phase 4 -- Federal Register fixes
5. Phase 7 -- Orchestrator + routes
6. Phase 6 -- OpenStates (last -- needs key registration, slowest)

---

## Expected impact

| Source | Current | After | What it adds |
|--------|---------|-------|--------------|
| eCFR | 0 | ~150 | Federal regulatory baseline for ALL 40 categories |
| Federal Register | 94 (14 cats) | ~200 (40 cats) | Better matching, pagination, no mismatches |
| ~~DOL Enforcement~~ | ~~0~~ | ~~DROPPED~~ | ~~No public JSON API~~ |
| OpenStates | 0 | ~200-400 | Legislative tracking (early warning) |
| CMS / Congress | ~10 | ~30 | Improved mapping quality |
| **Total API rows** | **~94** | **~700-1000** | |
| Gemini (state/city) | ~1,600 | ~1,600 | **Unchanged -- still needed for state/city enacted law** |

**Bottom line:** APIs can't replace Gemini for state/city data (89% of rows). But they provide the **authoritative federal floor**, **enforcement signals**, and **legislative early warning** that Gemini can't -- and upgrade ~700+ rows from tier_3 to tier_1/tier_2.

---

## API Testing Status

### eCFR API -- CONFIRMED WORKING
- **Base URL:** `https://www.ecfr.gov/api/versioner/v1/`
- **Key required:** No
- **Tested:** YES -- rich structured JSON confirmed for all target CFR titles
- **Endpoints (all confirmed working):**
  - `GET /structure/{date}/title-{N}.json?part={P}` -- Full TOC with parts, subparts, sections, headings, sizes, `received_on` dates
  - `GET /versions/title-{N}?part={P}` -- Historical amendment versions per section
  - `GET /titles` -- All 50 CFR titles with latest issue dates
  - Search API: `GET /api/search/v1/results?query={q}&per_page={n}` -- Full-text search across all CFR
- **Note:** Date param must be <= title's latest issue date (use `/titles` to get it)
- **Tested parts:** 29 CFR 541 (overtime), 825 (FMLA), 1604 (EEOC), 1910 (OSHA 23 subparts!), 45 CFR 164 (HIPAA 5 subparts), 42 CFR 482 (hospital CoP), 21 CFR 1301 (DEA pharmacy)

### Federal Register API (existing)
- **Base URL:** `https://www.federalregister.gov/api/v1/`
- **Key required:** No
- **Tested:** Already in production, but with quality issues
- **Fix needed:** Add `conditions[term]=` keyword filter, pagination, dedup by document_number

### DOL Enforcement Data -- DROPPED
- `enforcedata.dol.gov` is a React SPA with no public JSON API
- All endpoints return HTML. Old `data.dol.gov` and `developer.dol.gov` are dead.
- Not viable without scraping.

### OpenStates API
- **Base URL:** `https://v3.openstates.org/`
- **Key required:** Yes (free registration at openstates.org/account/profile/)
- **Tested:** Confirms key is required, returns clear error without one
- **Rate limit:** 6 requests/minute
- **Endpoint:** `GET /bills?jurisdiction={state}&q={keyword}&sort=updated_desc`

---

## Verification

1. eCFR fetch for US jurisdiction -> ~150 new tier_1 rows across 40 categories
2. Federal Register re-run -> no "antitrust" DOJ immigration mismatches
3. Data Quality tab -> significant tier_1 count increase
4. PolicyBrowserTab -> eCFR rows show emerald TierBadge
6. Gemini re-research -> API rows retain tier_1, not downgraded
