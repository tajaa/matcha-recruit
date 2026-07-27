# `server/app/matcha` — refactor round 2

> **Status (verified 2026-07-26): NOT IMPLEMENTED.** Stage 0's quota-bug fix is still
> unfixed — `matcha_work_document/_tokens.py:101` still reads `from . import
> entitlements_service`. Build order: do Stage 0 immediately (live billing bug); the rest
> of this doc should land before `4-HUUME_CODE_PLAN.md`, which adds files inside its
> Stage 3/6 blast radius. See `docs/implemented/` for round 1, which shipped.

## Context

Round 1 (committed `3b7bc84` + `57a6d2c`) split three monoliths into packages and grouped `routes/` + `services/` into domain subdirs. That reorg fixed *file size* but left four things behind, found by a fresh survey of the 155k-line package:

1. **A live billing bug.** `matcha_work_document/_tokens.py:101` does `from . import entitlements_service` — that package has no such module (it lives in `services/billing/`). Reorg fallout: the sibling call in `matcha_work_ai.py:726` was updated to `from ..billing import …`, this one wasn't. It's inside `except Exception`, so it fails silently on **every** call, and the fallback `(_DEFAULT_TOKEN_LIMIT, _DEFAULT_WINDOW_HOURS) = (25_000, 12)` is byte-identical to `PLAN_QUOTAS[PLAN_FREE]`. Any user without an explicit `mw_token_quotas` row gets the free quota regardless of plan: **Lite loses 100k→25k, Pro/Business lose 500k→25k**. Fails closed, so no security leak — but paid users are being under-served today.

2. **A layering inversion, 18 sites.** `services/` reaches back into `routes/` through lazy in-body imports used purely to dodge circular imports. Every core domain operation the services *and Celery workers* depend on is defined in a route-layer `_shared.py`. This is also why the biggest "route" files aren't route files at all — `ir_incidents/_shared.py` is 1,476 lines with **0 routes**, `matcha_work/ai_turn.py` is 1,391 lines with **0 routes**.

3. **Accidental shared utilities.** Five service files import `_PDF_CSS`/`_esc`/`_fmt_dt` — private names — out of `claims_readiness.py`, an IR/ER claims module that became the repo's de-facto PDF stylesheet. `_genai()` has **6 copies**. Eleven non-legal modules import `validate_citations` out of `legal_defense/`. There is no `services/_shared/`, so cycles route *through* domain packages to reach leaf helpers (31 lazy in-body service imports, 5 documented cycles).

4. **`models/` never got the reorg** (0 subdirs, 28 flat files, empty `__init__.py`) while 198 Pydantic models leaked into `routes/`, with real name collisions. And the docs now actively mislead: root `CLAUDE.md` has 28 stale `services/` paths, `routes/CLAUDE.md` is ~2× off on its own scale numbers and lists a file that no longer exists.

**Outcome wanted:** the routes layer holds routes; services hold logic; workers and services import services, never routes; docs match reality. Zero URL-surface change, zero behavior change (except the quota bug fix).

**Delivery:** one ordered series of small verified commits on the current branch (`docs/huume-ai-usage-plan`). Each stage below is independently committable and independently revertable.

---

## Stage 0 — the quota bug (1 line, do first)

`server/app/matcha/services/matcha_work/matcha_work_document/_tokens.py:101`

```python
-            from . import entitlements_service
+            from app.matcha.services.billing import entitlements_service
```

Absolute, matching `matcha_work_ai.py:726`'s intent (a 3-dot relative would also work but reads wrong from a nested package). While here: the `except Exception` treats a permanent `ImportError` as "transient resolver error" — narrow the log message, keep fail-closed semantics.

**Verify:** `python -c "from app.matcha.services.billing import entitlements_service; print(entitlements_service.PLAN_QUOTAS)"`, then confirm a Pro user's `GET /matcha-work/entitlements` reports 500k rather than 25k on dev.

Commit alone. Do not bundle — this is a user-facing fix and wants its own revertable commit.

---

## Stage 1 — delete dead code (zero risk, all verified 0 importers)

| Target | Evidence |
|---|---|
| 17 dead `from app.matcha.services.billing import billing_service as mw_billing_service` in `core/routes/admin/**` | 18 files import it; only `admin/companies.py:152` calls it (2 hits). Other 17 have exactly 1 hit = the import line. 9 in `admin/`, 8 in `admin/jurisdictions/`. Header block replicated during the admin split. |
| `server/app/dependencies.py` (49 ln) | Self-labelled `DEPRECATED` shim; repo-wide grep for `app.dependencies` → 0 hits. (The 30 `from ..dependencies import` hits resolve to `matcha`/`cappe`/`tellus` siblings.) |
| `server/app/matcha/workers/` | Entire package is 2 empty `__init__.py` files. 0 importers. Real matcha tasks live in `app/workers/tasks/` (23 of them import `app.matcha.*`). |
| `routes/__init__.py:26-27` `project_ws_router`, `thread_ws_router` | Imported, never mounted, absent from `__all__`. `main.py:555-559` mounts them by module path. |
| `routes/__init__.py` `__all__` (30 names) | Labelled "backwards compatibility"; nothing outside the file imports any of them. |

Cuts `core → matcha` edges from 50 files to ~33 with zero behavior change.

**Verify:** `python -c "from app.main import app; print(len(app.routes))"` unchanged (1957 baseline).

---

## Stage 2 — `services/_shared/` leaf package (breaks 2 cycles outright)

New leaf package that imports nothing from `services/` — that property is what dissolves the cycles.

```
services/_shared/
├── pdf.py         _PDF_CSS, _esc, _fmt_dt      ← from claims_readiness.py
├── citations.py   validate_citations, _parse_json  ← re-homed from pilots/legal_defense
├── gemini.py      _genai, is_model_unavailable_error ← from precedent_common.py + 6 copies
└── text.py        _hum, _slug
```

Evidence: 5 files import private PDF chrome out of `claims_readiness.py` (`broker/broker_pilot.py:37`, `pilots/analysis_pilot.py:37`, `pilots/legal_defense/{_shared.py:7,details.py:7,packet.py:15}`); `_genai` defined 6× (`broker_pilot`, `ask_hr`, `analysis_pilot`, `handbook_pilot`, `legal_defense/_shared`, `discipline/discipline_ai`); `_hum` 4×, `_corpus_text` 5×, `_history_text` 4×, `_build_prompt` 4×; 11 non-legal modules import `validate_citations`; `is_model_unavailable_error` has 4 implementations and `_parse_json_response` has 9.

Keep `legal_defense.validate_citations` as a thin re-export so the 11 existing call sites and 6 test files stay untouched in this stage; migrate them in Stage 6.

Cycles this kills: `broker ⇄ pilots` (`broker_pilot.py:38` is a **module-level** import of `pilots.legal_defense`) and `scheduling → discipline → pilots → scheduling`. Defuses part of `broker ⇄ insurance`.

Leave alone, deliberately: `notification_service.py` (19 cross-app importers, root is correct), `signature_provider.py` (infrastructure, 2 importers), `insurance/bls_injury_rates_2024.py` (generated file, 2 consumers — JSON would add a load path and lose import-time type errors for nothing).

---

## Stage 3 — the layering fix: move core domain ops out of `routes/`

The headline. Ten symbols defined in the routes layer that `services/` and `app/workers/` already depend on via lazy in-body imports. Moving them makes every one of those a normal top-level import.

| Symbol | Currently in | Move to | Consumers today |
|---|---|---|---|
| `create_incident_core` (194 ln) + people-index + notifications + OSHA case rows | `routes/ir_incidents/_shared.py` (1,476 ln, **0 routes**) | `services/ir/ir_incident_create.py`, `ir_people_index.py`, `ir_notifications.py`, `ir_osha_cases.py` | `pilots/hr_pilot_actions.py`, `huume/hr_ops_skill.py` |
| `build_osha_emergency_alert_card`, `build_treatment_query_card`, `build_osha_recordable_query_card`, `build_log_root_cause_query_card` | same file | `services/ir/ir_cards.py` | `services/ir/ir_flow.py` ×3, `services/ir/ir_ai_orchestrator.py` ×4 — **the services layer lazily importing its own routes** |
| `compute_wc_metrics`, `compute_behavioral_friction` | `routes/ir_incidents/analytics.py:316` | `services/ir/ir_wc_metrics.py` | `broker/risk_index.py`, `broker/submission_readiness.py`, `routes/broker/{portfolio,submission}.py`, workers `broker_risk_alerts.py` + `broker_milestones.py` |
| `create_case_core` | `routes/er_copilot/_shared.py:43` | `services/er/er_case_create.py` | `pilots/hr_pilot_actions.py`, `huume/hr_ops_skill.py` |
| `decide_pto_request_core`, `_send_invitation_with_conn`, `_STATE_NAME_TO_CODE` | `routes/employees/_shared.py:658/258/42` | `services/employees/` (new subdir) | `huume/hr_ops_skill.py`, `huume/onboarding_skill.py`, `matcha_work/matcha_work_node.py` |
| `_generate_offer_letter_html` (273 ln), `_send_candidate_range_email` | `routes/employee_lifecycle/offer_letters.py:1292/472` | `services/offer_letters/document.py` (new) | `matcha_work_document/pdf.py` (a documented 2-way lazy pair — this ends it), `huume/onboarding_skill.py` |
| `broadcast_task_event` | `routes/work/project_ws.py:662` | `services/matcha_work/task_events.py` | `matcha_work/project_task_service.py` |

**Contract to preserve exactly:** `routes/ir_incidents/__init__.py:85-104` re-exports 15 `_shared` symbols + 2 `analytics` + 2 `copilot` symbols, consumed by `routes/intake/inbound_email.py:26` (13 of them) and 4 broker/worker modules. Keep the `__init__.py` re-export block, repointed at the new service modules — no call site changes in this stage.

Ordering within the stage: `_shared.py` first (it is the cycle source), then `analytics.py`, then the rest. Each is its own commit.

**Verify per commit:** app boot route count unchanged; `grep -rn "app.matcha.routes" app/matcha/services/ | wc -l` drops from 18 toward 0; `python -m pytest tests/ir_incidents/ tests/er_copilot/ tests/employees/ -q` against a pre-recorded baseline.

---

## Stage 4 — straggler moves (pure `git mv`, zero external importers)

Root `routes/` goes 12 files → 6. Grouping-folder convention per `routes/CLAUDE.md:51-63`: the folder `__init__.py` re-exports under the historical `*_router` name, so the mount block in `routes/__init__.py` is unchanged.

- `broker_chat_company.py` (254/11) → `broker/chat_company.py` — it is a **route-for-route mirror** of `broker/chat.py`, same 11 paths, same `services/broker/broker_chat_service.py`; two halves of one feature split across the folder boundary.
- `portal_ask_hr.py` (311/5) → `employee_portal/ask_hr.py`
- `schedule_intelligence.py` (108/5) → `employee_schedule/intelligence.py`
- `wc_rates_admin.py` (180/6) → `insurance/wc_rates_admin.py`
- `billing.py` (580/11) → `work/billing.py`; also drop its double-applied `require_feature("matcha_work")` (declared at `billing.py:27` *and* re-applied at the mount, `routes/__init__.py:239`)
- `productivity.py` (159/9) → `work/productivity.py`

Only external importer of any root straggler is `tests/help_assistant/test_help_assistant.py` → `help_assistant.py`, which stays flat.

**Stay flat, deliberately:** `companies.py` (root-level domain), `risk_assessment.py` (839/15 but correctly thin over `services/risk_analytics/`'s 2,870 lines — this is the pattern everything else should look like), `ir_surveys.py`, `help_assistant.py`, `fractional_hr.py`.

Also in this stage: decide `work/notifications.py`'s missing gate explicitly. Its 6 routes are `get_current_user`-authed and user-scoped, so it isn't an access hole — but it is the only `/matcha-work/*` surface without `require_feature("matcha_work")`, and gating by omission should be a written choice either way.

---

## Stage 5 — route package splits

Applies `routes/CLAUDE.md:85-94`'s documented criteria and fresh-aggregator variant. Do these **after** Stage 3 — the layering fix removes ~1,100 lines from these files first, so several stop qualifying.

1. **`matcha_work/messaging.py` (1,605 / 1 route) + `ai_turn.py` (1,391 / 0 routes).** Best value/risk in the tree, and half-admitted already — `matcha_work/CLAUDE.md:22` describes `ai_turn.py` as "No routes." `_apply_ai_updates_and_operations` is **692 lines**, the longest function in `routes/`. `messaging.py` is a clean named pipeline (`TurnContext` → `_run_quota_gate` → `_prepare_attachments` → `_run_hard_stop_gates` 203 → `_run_huume_dispatch` 176 → `_inject_mode_contexts` 127 → `_generate_turn` → `_audit_and_persist` 204). → `services/matcha_work/turn_pipeline.py` + `ai_apply.py`, leaving a ~200-line route file.
2. **`ir_incidents/copilot.py` (2,384 / 5 routes)** — the only file meeting the documented ~2,000-line bar. `accept_copilot_card` 665 ln with a nested `event_stream` of 629 (line 1750); `_handle_quick_reply` 291, `_close_incident_via_copilot` 209, `_handle_text_input` 196. Extract the card/chain state machine → `services/ir/ir_copilot_flow.py` (next to the existing `ir_flow.py`), then `copilot/` package.
3. **`ir_incidents/osha.py` (1,627 / 16 routes)** — 4 disjoint groups with no shared state: 300/301 logs (~600), 300A (~350), ITA (~500, and `services/ir/ir_ita_submission.py` already exists), recordability (~140). → `osha/` package; `_osha_pdf.py` is the extraction precedent.
4. **`interviews.py` (1,579 / 14)** — mounted at `routes/__init__.py:96` with **no prefix and no gate**, the only router of 73 with neither, putting `/tutor/*` at the bare API root. Lines 102–844 are 8 `/tutor/*` routes; `matcha_work/tutor.py` (3 routes) writes the **same `interviews` table** — one product, two routers, two directories. Merge the tutor half into `matcha_work/tutor.py`; leave recruiting + the 477-line WS handler behind; give the mount a real prefix.

Cheap extractions alongside: `ir_incidents/crud.py:430-670` `_build_incident_report_html` → `_report_html.py` (mirrors `_osha_pdf.py`); `matcha_work/threads.py`'s `upload_thread_handbook` (335 ln) → the **already-existing** `services/matcha_work/matcha_work_handbook_upload.py`; delete the two zero-caller helpers in `employee_portal/_shared.py` that its own CLAUDE.md already flags.

---

## Stage 6 — service facade packages

Reuse the `matcha_work_document/` precedent exactly: package dir + `__init__.py` of pure `# noqa: F401` re-exports, callers untouched.

1. **`matcha_work/matcha_work_ai.py` (1,893, 23 callers)** — biggest readability win. ~370 lines (L185–557) are *raw prompt string literals* (`MATCHA_WORK_STATIC_PROMPT_TEMPLATE` alone is 280). `GeminiProvider` is 834 lines. → `_prompts.py`, `_fields.py`, `_images.py`, `_models.py`, `provider.py`, `compaction.py`, `task_draft.py`.
2. **`broker/broker_pilot.py` (1,811, 11 callers) + `pilots/handbook_pilot.py` (1,556, 15 callers)** — do together. The seams are already drawn as `# ---` banners (5 and 6 respectively), and handbook_pilot's docstrings label pure-vs-DB sections. Doing them as one change lands the shared pilot scaffolding (`_corpus_text`, `_history_text`, `_build_prompt`, the `{cid: {...}}` corpus contract) in `_shared/` once rather than twice — and gives `hr_pilot_corpus.py:46`'s cross-pilot import of handbook_pilot's *private* `_slug`/`_floor_records`/`build_corpus` a legitimate home.
3. **`pilots/hr_pilot_corpus.py` (1,305, 10 callers)** — trivial 2-way split on a perfect DB/pure fault line (banner at L624). Do immediately after #2.
4. **`matcha_work/project_task_service.py` (1,432)** — extract the 5 notification builders (~400 ln) → `project_task_notifications.py`; collapses 4 lazy `from .. import notification_service` re-imports to one. `update_project_task` (279 ln) needs real decomposition — **separate commit, don't bundle**.
5. **`risk_analytics/risk_assessment_service.py` (1,439, only 7 callers)** — lowest blast radius of the big files. → `risk_assessment/` with `dimensions/{compliance,incident,er,workforce,legislative}.py` + `cost_of_risk.py` (pure, independently testable) + `recommendations.py`. Fold its duplicate `_is_model_unavailable_error`/`_parse_json_response` into `_shared/gemini.py`.
6. **`services/claims_readiness.py`** — after Stage 2 takes the PDF chrome, ~180 lines of IR/ER packet logic remain; move into `ir/` with an `er/` shim.
7. **`matcha_work/project_service.py` (1,711, 13 callers)** — split by entity: project CRUD / sections+blog (~450) / **discipline projects** (L1236–1341 — a `discipline/` concern living in `matcha_work/`) / collaborators+channels (~370).

---

## Stage 7 — `models/` reorg

The last un-reorged layer. `models/__init__.py` is **0 bytes**, so there is no facade to preserve — this is pure `git mv` + import-path rewrite.

1. Mirror the `services/` subdir names: `models/{ir,er,broker,matcha_work,employees,insurance,pilots,…}/`.
2. Pilot with **`models/ir_incident.py` (1,059 ln)** — it already carries `# ====` banners mapping near-1:1 onto `routes/ir_incidents/`'s modules (Witness/incident-type → `crud`, `CorrectiveAction*` → `capa`, `Osha*` → `osha`, `*Analysis` → `ai_analysis`, Analytics/RiskMatrix → `analytics`, `IRPerson*` → `people`). The split is pre-drawn.
3. Pull the **198 route-inline models** in. Worst offenders: `integrations/provisioning/_models.py` (16), `billing.py` (11), `employee_lifecycle/training.py` (10), `onboarding/new_hire.py` (9), `employee_lifecycle/pre_termination.py` (9), `broker/brokers/_models.py` (9), `risk_assessment.py` (8). Note the two `_models.py` files — the last reorg created new model modules *inside* `routes/`, which is the drift to reverse.
4. Dedupe the real collisions into `models/pilots/`: **`ChatIn` ×4** (`models/analysis_pilot.py:78`, `routes/broker/pilot.py:69`, `routes/pilots/handbook.py:53`, `routes/pilots/legal_defense.py:102`), `SessionCreate`/`SessionUpdate` ×3 each, plus `EmployeeListResponse` ×2, `ManagerHotspot` ×2, `MarkReadRequest` ×2. Four pilot surfaces redefining the same chat-session triad is a missing shared base, not a coincidence.

**Watch out:** 4 test files use `spec_from_file_location` with hardcoded module strings (`"app.matcha.routes.employees"`, `"app.matcha.routes.er_copilot.crud"`, a bare `"routes"`). They break *silently* on any move. Fix them in Stage 4, before Stages 5–7 start moving things.

---

## Stage 8 — doc refresh (do last, describe the end state)

- **Root `CLAUDE.md`**: 28 stale `services/*.py` paths (all now in subdirs — e.g. `services/discipline_engine.py` → `discipline/`, `services/risk_index.py` → `broker/`, `services/training_assignment.py` → `training/`); `routes/inbound_email.py` ×3 → `routes/intake/`; `core/services/compliance_service.py` and `core/services/email.py` are now **directories**; `matcha/services/channels_service.py` no longer exists. Note the doc contradicts itself already — lines 52 and 509 give the correct `services/matcha_work/project_service.py` while line 303 gives the stale flat path. Directory-structure block omits `app/cappe/`, `app/tellus/`, `app/werk/` entirely and lists the now-deleted `app/dependencies.py`.
- **`routes/CLAUDE.md`**: header says "29 routers, ~39,000 lines"; measured **73 mounts, 75,908 lines, 1,102 route decorators**. Drop the phantom `broker/brokers.py` row (the file became `broker/brokers/`; the stale row sits directly above the real one — precisely the package-shadows-module trap the same doc warns about three paragraphs earlier).
- **`ir_incidents/CLAUDE.md`**: claims 61 routes, actual 87; missing rows for `broker_sharing.py`, `claims_readiness.py`, `voice.py`.
- **`server/CLAUDE.md`**: stale `tests/pre_termination/test_pre_termination.py`.
- **New rule to write down:** the `cappe`/`tellus` boundary rule (root `CLAUDE.md:90`) holds exactly as written — `cappe → matcha` is 0 violations, `tellus → matcha` is the 1 documented `geo.py` exception. But **`app/werk/` is a fourth backend app the rule never names**, and it reaches into matcha at 4 sites (`channels_ws.py` ×3, `channels.py:18`). Undocumented means nobody can distinguish an intentional edge from drift. State werk's allowed direction explicitly.
- Update this doc with a round-2 progress section mirroring round 1's format (round 1 doc now at `docs/implemented/REFACTOR_PLAN.md`).

**Deferred, with reasons:** `matcha/dependencies.py` is 576 lines and `resolve_accessible_company_scope` alone is ~245 of them (L67–311) — a tenant-resolution engine, not a FastAPI dependency, with 24 `core/` importers plus werk. Extracting it to `core/services/tenant_scope.py` would shrink the file 42%, give werk a legal import target, and dissolve most of the remaining `core → matcha` edge. It touches `core/` broadly, so it wants its own plan rather than a stage here.

---

## Verification

Per commit:
- `python3 -m py_compile` on every touched file (the post-edit hook does this automatically).
- Full boot: `cd server && python3 -c "from app.main import app; print(len(app.routes))"` — must stay **1957**.
- OpenAPI path set: `python3 -c "from app.main import app; import json; print(json.dumps(sorted(app.openapi()['paths'])))"` — byte-identical before/after for every stage except 4 (where `interviews` gains a prefix) and 5.
- Layering metric, the point of Stage 3: `grep -rn "app.matcha.routes" app/matcha/services/ | wc -l` — **18 → 0**. Same grep over `app/workers/` — **3 → 0**.

Per stage:
- `cd server && python3 -m pytest tests/ -q` against a baseline recorded **before** stage 0. Round 1 recorded 8 pre-existing failures (`test_blog_pdf_export.py`, `test_employees_google_workspace_onboarding.py`) + 2 pre-broken collection errors — re-record, don't assume the same set.
- New smoke tests mirroring round 1's pattern (`tests/*/test_router_split_smoke.py`): hardcoded route-table snapshot per split package, plus a facade `hasattr` sweep per service package.
- Stage 0 needs a real check, not just import success: on dev, a Pro-plan user's `GET /matcha-work/entitlements` must report a 500,000 token limit.

End-to-end on dev (`./scripts/dev-remote.sh` — note its frontend at `:5174` is usually already running; never `pkill -f "vite --port"`, it matches the user's own process):
`GET /dashboard/stats`, `GET /v1/portal/me`, IR copilot round-trip (Stage 5 #2), a matcha-work AI turn (Stage 5 #1), broker portfolio (exercises `compute_wc_metrics` after its move), an offer-letter PDF (exercises the ended 2-way lazy pair).

## Rollback

No migrations, no schema, no data. Every stage is `git revert` of one commit. The one class of failure that survives a green test run is a **missed re-export** — hence the hardcoded route-table snapshots and facade `hasattr` sweeps, which is how round 1 caught this class pre-merge.

## Critical files

- `services/matcha_work/matcha_work_document/_tokens.py` (Stage 0 — the bug)
- `routes/ir_incidents/_shared.py` (1,476 / 0 routes) + `routes/ir_incidents/__init__.py:85-104` (the 19-symbol re-export contract)
- `routes/matcha_work/{messaging,ai_turn}.py` (2,996 / 1 route)
- `routes/ir_incidents/{copilot,osha,analytics}.py`
- `routes/employees/_shared.py`, `routes/er_copilot/_shared.py`, `routes/employee_lifecycle/offer_letters.py`, `routes/work/project_ws.py` (Stage 3 sources)
- `services/claims_readiness.py`, `services/pilots/legal_defense/`, `services/precedent_common.py` (Stage 2 sources)
- `routes/__init__.py`, `routes/CLAUDE.md`, root `CLAUDE.md`, this doc
