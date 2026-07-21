# compliance_service.py — sub-package split tracker

**Parent task:** [CLEANUP_PLAN.md](./CLEANUP_PLAN.md) **J6** — sub-package the two
mega-services. `handbook_service/` is done (commit `77ee996`). This doc tracks the second
and final one: `compliance_service.py`, the **last structural split in the whole cleanup**.

**Goal:** `server/app/core/services/compliance_service.py` (10,676 lines, 143 functions,
19 module consts, 0 classes) → a **package** at the same import path
`server/app/core/services/compliance_service/`. Pure code motion, **zero behavior change**,
**zero importer churn** (package keeps the module's name, re-exports every public symbol —
same trick as `handbook_service/`).

Why a folder: one 10.6k-line wall is unnavigable. Broken into ~12 concern-scoped files it
becomes followable, and each file is independently readable.

---

## Ground rules (do not violate)

1. **The `__init__.py` re-exports EVERY external name** (list below). A miss breaks a
   consumer — often at call time, not boot time. `import *` skips `_`-private names, so the
   re-exports are **explicit**.
2. **`__init__` must `import httpx`** — `tests/compliance/test_source_url_liveness.py`
   monkeypatches `cs.httpx.AsyncClient`. (Patching mutates the global `httpx`, so any
   submodule using it still sees the fake — but the attribute must exist on the package.)
3. **Convert relative imports to absolute** during emission. The old file lives at
   `core/services/`; nesting one level deeper shifts every `from .X`/`from ..X`/`from ...X`.
   Rule: `from .X` → `from app.core.services.X`, `from ..X` → `from app.core.X`,
   `from ...X` → `from app.X`. Package-internal cross-module imports use `from ._x import …`.
4. **Grep-to-zero safety net** after the split:
   `grep -rE "from \.\.?[a-z]" app/core/services/compliance_service/` must return ONLY
   package-internal `from ._<module>` lines. In-body relative imports resolve at call time;
   boot won't catch a wrong one — this grep is what proves none survive.
5. **No new feature flag, no schema change, no route change.** Route count must stay 1858.

---

## External surface — 87 names the `__init__` must re-export

Measured by AST-scanning all 42 app importers + test files. `import compliance_service; cs.X`
attribute-access and `monkeypatch.setattr("…compliance_service.X")` string patches both
resolve against the package `__init__`, so every name below must live on it.

**Functions (82):**
`_clamp_varchar_fields`, `_coerce_minimum_wage_rate_type`, `_compute_key_parts`,
`_compute_requirement_key`, `_create_alert`, `_decode_jsonb`, `_drop_no_rule_placeholders`,
`_filter_by_jurisdiction_priority`, `_filter_city_level_requirements`,
`_filter_requirements_for_company`, `_filter_with_preemption`, `_get_company_admin_contacts`,
`_get_company_canonical_industry`, `_get_company_industry_tags`, `_get_industry_profile`,
`_get_or_create_jurisdiction`, `_heartbeat_while`, `_is_no_rule_placeholder`,
`_jurisdiction_row_to_dict`, `_load_jurisdiction_requirements`, `_lookup_has_local_ordinance`,
`_missing_required_categories`, `_normalize_category`, `_normalize_requirement_categories`,
`_normalize_title_key`, `_project_chain_to_location`, `_refresh_repository_missing_categories`,
`_research_healthcare_requirements_for_jurisdiction`,
`_research_life_sciences_requirements_for_jurisdiction`,
`_research_medical_compliance_for_jurisdiction`,
`_research_oncology_requirements_for_jurisdiction`, `_resolve_industry`,
`_sync_requirements_to_location`, `_upsert_jurisdiction_legislation`,
`_upsert_jurisdiction_requirements`, `_upsert_requirements_additive`,
`admin_add_requirement_to_location`, `admin_add_requirements_to_location_batch`,
`codified_gate_sql`, `create_location`, `delete_location`, `determine_governing_requirement`,
`discover_specialization_categories`, `dismiss_alert`, `ensure_location_for_employee`,
`escalate_upcoming_deadlines`, `evaluate_trigger_conditions`, `format_corrections_for_prompt`,
`get_calendar_items`, `get_calibration_stats`, `get_check_log`, `get_company_alerts`,
`get_compliance_dashboard`, `get_compliance_summary`, `get_employee_impact_for_location`,
`get_facility_attributes`, `get_hierarchical_requirements`, `get_location`,
`get_location_counts`, `get_location_requirements`, `get_locations`, `get_pinned_requirements`,
`get_recent_corrections`, `get_specialization_completeness`, `get_upcoming_legislation`,
`is_codified_row`, `mark_alert_read`, `project_location_from_catalog`,
`record_verification_feedback`, `research_jurisdiction_repo_only`,
`research_specialization_for_jurisdiction`, `resolve_jurisdiction_stacks`,
`run_compliance_check_background`, `run_compliance_check_stream`,
`score_verification_confidence`, `search_company_requirements`, `set_requirement_pinned`,
`update_alert_action_plan`, `update_auto_check_settings`, `update_facility_attributes`,
`update_location`, `verify_location_ownership`

**Module consts (2):** `MATCHA_X_LITE_CATEGORIES`, `VALID_RATE_TYPES`

**Pass-through registry aliases (3):** `HEALTHCARE_CATEGORIES`, `ONCOLOGY_CATEGORIES`,
`REQUIRED_LABOR_CATEGORIES` — these are re-exported from `..compliance_registry` at the top
of today's file (`LABOR_CATEGORIES as REQUIRED_LABOR_CATEGORIES`), and consumers import them
FROM compliance_service, so `__init__` must keep re-exporting them.

> Note: `resolve_jurisdiction_stack` (singular) is imported internally but the external
> surface uses `resolve_jurisdiction_stacks` (plural). Both live in `_hierarchy.py`; both
> get re-exported to be safe.

---

## Module map (bottom → top; a near-DAG after the 4 back-edge moves below)

Cross-group call edges were measured, not guessed. The layering (each module only imports
from ones above it in this table) holds after four reclassifications, noted in **bold**.

| ✅ | Module | Funcs | ~Lines | Contents |
|---|---|---|---|---|
| [x] | `_shared.py` | 6 | ~90 | `logger`, `parse_date`, **`_heartbeat_while`** (moved down out of checks), `_as_jsonb`, `_decode_jsonb`, `_parse_jsonb_list`; consts `JURISDICTION_PRIORITY`, `VALID_LEGISLATION_STATUSES`, `MATERIAL_CHANGE_THRESHOLDS`, `MAX_VERIFICATIONS_PER_CHECK`, `HEARTBEAT_INTERVAL` |
| [x] | `_normalize.py` | 23 | ~405 | title/category/rate-type/value normalization, material-change detectors, wage pickers, `normalize_and_hash` (+`hashlib`/`unicodedata`), `_clamp_varchar_fields`, `_validate_source_urls`; consts `_CATEGORY_ALIASES`, `_CODE_TO_STATE_NAME`, `VALID_RATE_TYPES`, `_TITLE_CANONICAL_MAP`, `_MIN_WAGE_*`, `_VARCHAR_100_FIELDS`, `_INDUSTRY_SPECIFIC_RATE_TYPES` |
| [x] | `_industry.py` | 7 | ~171 | `_resolve_industry`, `_get_company_canonical_industry`, `_get_company_industry_tags`, `_looks_healthcare/oncology_specific`, `_requirement_applicable_industries`, `_get_industry_profile`; consts `_HEALTHCARE/_ONCOLOGY_TEXT_MARKERS`, `_INDUSTRY_RESEARCH_CONTEXT` |
| [x] | `_verification.py` | 7 | ~297 | `score_verification_confidence(_with_reputation)`, `update_source_reputation`, `record_verification_feedback`, `get_calibration_stats`, `get_recent_corrections`, `format_corrections_for_prompt` |
| [x] | `_jurisdictions.py` | 23 | ~730 | jurisdiction get/create/resolve chain, county/state ids, zip/city resolution (`_CITY_ALIAS_FALLBACKS`), row→dict, load requirements/legislation, freshness, `_is_no_rule_placeholder`, parent fills — **minus `_project_chain_to_location`** (→ `_hierarchy`) |
| [x] | `_hierarchy.py` | 14 | ~940 | preemption/priority filters, `is_codified_row`, `codified_gate_sql`, `evaluate_trigger_conditions`/`_eval_condition`, `resolve_jurisdiction_stack(s)`, `determine_governing_requirement`, `_compute_triggered_by`, `_collect_activations`, **`_project_chain_to_location`**, `_filter_requirements_for_company` — **minus `get_hierarchical_requirements`/`search_company_requirements`** (→ `_checks`) |
| [x] | `_catalog_writes.py` | 13 | ~992 | all `_upsert_*` (routed/additive/legacy), `_insert_catalog_requirement`, `_upsert_requirement`/`_update_requirement`/`_snapshot_to_history`, `_refresh_catalog_links`, key computation (`_resolve_regulation_key`, `_compute_key_parts`, `_compute_requirement_key`) |
| [x] | `_alerts.py` | 19 | ~920 | check-log open/close, `_create_alert` + email senders, change notifications (`_get_company_admin_contacts`, `_notify_company_admins_of_compliance_changes`), `_log_policy_change`/`_log_verification_outcome`, `process_upcoming_legislation`, `escalate_upcoming_deadlines`, alerts CRUD, `get_calendar_items`, `get_upcoming_legislation` |
| [x] | `_research.py` | 7 | ~984 | 4 vertical research runners (healthcare/oncology/life-sciences/medical), `_fill_from_state_fallback`, `_refresh_repository_missing_categories`, `research_jurisdiction_repo_only` |
| [x] | `_specialization.py` | 3 | ~378 | `discover_specialization_categories`, `research_specialization_for_jurisdiction`, `get_specialization_completeness`; const `MATCHA_X_LITE_CATEGORIES` |
| [x] | `_locations.py` | 14 | ~1,141 | location CRUD, `ensure_location_for_employee`, `verify_location_ownership`, facility attrs, `_sync_requirements_to_location`, `project_location_from_catalog`, `admin_add_requirement(s)_to_location*` — **one lazy import**: `run_compliance_check_background` inside `ensure_location_for_employee` (only surviving cycle → in-function `from ._checks import …`) |
| [x] | `_checks.py` | 13 | ~3,180 | the coupled top: `run_compliance_check_stream` (1,241), `run_compliance_check_background` (756), `get_compliance_summary`, `get_compliance_dashboard` (357), `get_employee_impact_for_location`, `get_location_requirements`, **`get_hierarchical_requirements`**, **`search_company_requirements`**, `update_auto_check_settings`, `get_check_log`, `set_requirement_pinned`, `get_pinned_requirements` |
| [x] | `__init__.py` | — | ~160 | docstring, `import httpx`, re-export all 87 external names + `resolve_jurisdiction_stack`, `__all__` |

**Back-edge resolutions (measured):**
- `_heartbeat_while` → `_shared` — kills `research → checks`.
- `_project_chain_to_location` → `_hierarchy` — kills `jurisdictions → hierarchy`.
- `get_hierarchical_requirements` + `search_company_requirements` → `_checks` — kills
  `hierarchy → checks`.
- `_locations.ensure_location_for_employee → _checks.run_compliance_check_background` — the
  one irreducible cycle; resolved with an **in-function** `from ._checks import
  run_compliance_check_background` (not module-level), so import order is fine.

Everything else already flows upward in table order.

---

## Verification checklist

- [x] `./venv/bin/python -m py_compile app/core/services/compliance_service/*.py`
- [x] Boot: `from app.main import app; len(app.routes)` **== 1858**
- [x] Surface: scripted `from app.core.services.compliance_service import <each of 87>` — all import
- [x] Grep-to-zero: `grep -rE "from \.\.?[a-z]" app/core/services/compliance_service/` → only `from ._<module>` lines
- [x] Monkeypatch tests green: `tests/test_er_compliance_grounding.py`, `tests/hris/test_locations_ingest.py`, `tests/compliance/test_source_url_liveness.py`
- [x] Broad pytest: `tests/compliance/` + matcha-x onboarding + vertical-coverage + scope-registry + hris. Any failure → prove pre-existing via `git worktree add /tmp/pre HEAD`
- [x] Update CLEANUP_PLAN.md STATUS: J6 complete → all structural splits done

---

## Progress log

- **2026-07-20** — doc created. Surface enumerated (87 names), module map + back-edges
  measured. Split not yet emitted.
- **2026-07-20** — **split DONE.** 12 modules + `__init__` emitted via the AST harness;
  10,676-line module → 13 files (largest `_checks.py` ~3.1k). Verified: py_compile clean;
  boot `len(app.routes) == 1858`; all 87 external names + `httpx` present on the package;
  grep-to-zero on relative imports (cross-module imports are fully absolute
  `from app.core.services.compliance_service._x import …`); the one lazy cycle edge
  (`_locations.ensure_location_for_employee → _checks.run_compliance_check_background`)
  imported in-function. 39 consumer/worker modules import clean. Tests: 3 monkeypatch files
  green + 373 `tests/compliance/` + 760 hris/scope/onboarding/evals pass; the 8 failures
  (7 in `test_compliance_schema_redesign.py`, 1 `test_build_dossier_full`) proven
  pre-existing on the monolith via `git worktree add HEAD`.
