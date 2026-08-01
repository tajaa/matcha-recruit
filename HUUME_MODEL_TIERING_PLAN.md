# Huume/EMS model tiering: gemini-3.5-flash-lite where quality allows

## Context

Huume's agent loop runs **every** tier on `gemini-3.6-flash` ($1.50/$7.50 per 1M) — the tier system (`lite`/`standard`/`deep`) only varies thinking level, never model. The "lite" tier name is misleading: it's Flash-with-thinking-off, not Flash-Lite. Meanwhile EMS one-shots run on the older-gen `gemini-3.1-flash-lite`. Goal: use `gemini-3.5-flash-lite` where a cheap model suffices, keep 3.6-flash where quality matters — starting with EMS + the Huume harness.

## Tier boundary review (findings)

| Tier | When it fires (`routing.py:resolve_tier`) | Verdict |
|---|---|---|
| `lite` | Short confirm-shaped msg ("yes", "approve it", ≤8 words) AND something actually staged (`has_pending_confirmable`) | **→ flash-lite.** Confirm turns are structurally guarded: server re-verifies everything (`evaluate_huume_action`, `execute_plan_locked`, two-turn rule enforced via `pre_turn_plans` snapshot), staged-state block hands the model real ids. Worst failure = wrong tool call → server refusal → user retries; never a wrong write. Merlin precedent: 3.5-flash-lite runs Merlin's `lite` tier live (`cappe/services/merlin/catalog.py:234`), and its agentic score jumped Terminal-Bench 31%→54% vs prior lite gens. |
| `standard` | Fallback — everything ordinary/ambiguous | **Keep 3.6-flash.** Routing's own rule (from Merlin): "unsure lands in the middle, never the cheap tier". Standard turns include real tool-selection + final-answer composition over 31 registered tools. |
| `deep` | Any tool `intent_hints` match, analytical regex, or narrative-shaped (>280 chars / >2 newlines) | **Keep 3.6-flash** (thinking high/low). This is exactly where quality is paid for. |

## Per-tool assessment (30 tools + finish)

Tier is picked **per-turn before any tool call** (heuristic on message text), and can't switch models mid-turn — Gemini 3.x thinking models attach `thought_signature`s to responses that must return to the same model (see Merlin `agent.py:756`), so "which model calls this tool" = "which tier does the turn that reaches it land in". The audit therefore checks: is the tool set reachable from each tier safe at that tier's model?

**Tools reachable on `lite` (confirm) turns — all mechanical, flash-lite safe:**

| Tool | What the model must do | Guard |
|---|---|---|
| `execute_approved_steps` | echo `offer_id` from state block | `evaluate_plan_execution` + `execute_plan_locked`; wrong id → refusal |
| staged-action confirms (`send_offer`, `report_incident`, `open_er_case`, `assign_training`, `decide_pto_request`, `draft_disciplinary_action`, `decide_disciplinary_action`, `promote_ems_event` confirm leg) | match server-minted `confirm_id` / record id from state block | `evaluate_huume_action` re-verifies role/flags/id per call |
| `cancel_staged`, `finish` | trivial | `evaluate_cancel_plan` refuses executing/done |

Worst lite-tier failure = wrong tool/id → server refusal → user restates. Never a wrong write.

**Tools already forced to `deep` via `intent_hints` (6):** `find_discipline_candidates`, `list_pending_approvals`, `ask_er_copilot`, `promote_ems_event` (discovery leg), `ask_ir_copilot`, `run_incident_analysis`. These are the "which X need attention?" / analytical entry points — correctly on 3.6-flash + thinking. (`list_pending_approvals`/`promote_ems_event` are arguably over-provisioned at deep — simple list/stage relays — but conservative is fine; not touching.)

**Everything else lands `standard` (3.6-flash, default thinking) — correct, keep:**
- **Field-extraction stagers** — `draft_offer_letter` (structured fields only; letter body composed server-side), `build_onboarding_plan` (pure `offer_id` trigger; plan built by orchestrator service), `draft_discipline`. Extraction fidelity matters (salary, dates, names from conversation) and misses are caught at the staged-review step — but 3.6 standard is the right floor since these are also legal-record intake.
- **Embedded-Gemini relays** — `ask_legal_pilot`, `draft_handbook_content`, `check_incident_policy`, `generate_legal_packet`, `promote_handbook_drafts`, `open_legal_matter`. The heavy lifting is the tool's OWN internal Gemini call (each ~60-100s, own citation gates); the loop model only composes the question arg + relays. Citations survive structurally (`huume_result.citations` from tool results, not model-text parsing). Standard is enough; downgrading below it risks garbled question-args feeding the expensive embedded call.
- **Reads** — `lookup_context`, `show_record`, `check_offer_status`, `list_legal_matters`, `er_case_brief`. Flash-lite could handle a pure-lookup turn, but routing can't distinguish "simple lookup" from "ambiguous ask" without a Merlin-style classifier call, which Huume deliberately avoids (its loop already pays per-turn). **Deferred as optional phase 2** — a `light-read` heuristic would be a new misroute surface for marginal savings; the fallback-lands-in-the-middle rule stays.

Net: the tier boundaries are already correct per-tool. The change needed is making `lite`'s MODEL actually lite — no tool re-bucketing required, no new hints.

**Critical API gotcha** (documented in Merlin `catalog.py:208-215`): the 3.x generation dropped `thinking_budget` — passing `thinking_budget=0` is a **hard 400 INVALID_ARGUMENT on gemini-3.5-flash-lite**. Huume's `thinking_config("none")` returns `ThinkingConfig(thinking_budget=0)` today. The lite tier must switch to `thinking_level="minimal"` (the 3.x thinking-off equivalent).

**EMS** (`services/ems/`): `event_intake.classify_event` + `ask.py` share `FLASH_LITE_MODEL = "gemini-3.1-flash-lite"`. Bump to `gemini-3.5-flash-lite` per user directive. Note: price goes UP ($0.10/$0.40 → $0.30/$2.50) but perf is meaningfully better — same trade Merlin already made. `intent.py`/`categories.py`/`promote.py` make no model calls. `_ir_suggestions` rides `get_ir_analyzer()` (settings.analysis_model) — out of scope.

**Embedded skill Gemini calls — deliberately untouched**: `er_skill.py` (uses `settings.analysis_model`, shared with ER Copilot page by design), `discipline_policy_check.py` (`gemini-3-flash-preview`), legal/handbook pilot services. Each is a grounded/cited quality path.

## Changes

1. **`server/app/matcha/services/huume/routing.py`**
   - Add `FLASH_LITE = "gemini-3.5-flash-lite"` (public, next to `FLASH`).
   - `TIERS["lite"] = HuumeTier(FLASH_LITE, "minimal", FLASH_LITE, "minimal")` — model swap + thinking fix in one move.
   - Update module docstring + `thinking_config` docstring (note the `"none"`/budget-0 branch is now legacy — keep the branch, nothing routes to it, but removing invites drift with matcha_work_ai's mapping it mirrors).

2. **`server/app/matcha/services/huume/agent.py:55-57`** — update the stale comment ("every tier's planner/executor model is routing.FLASH today"); `_MODEL = routing.FLASH` alias itself stays (still the standard/deep model, still the pricing-test anchor).

3. **`server/app/matcha/services/ems/event_intake.py:47`** — `FLASH_LITE_MODEL = "gemini-3.5-flash-lite"`. (`ask.py` imports this constant — one edit covers both.)

4. **`server/app/matcha/services/billing/model_pricing.py`** — add `"gemini-3.5-flash-lite": {0.30 / 2.50}` row matching `ai_usage.PRICING`'s existing `("gemini", "gemini-3.5-flash-lite"): (0.30, 2.50)` — without it every lite-tier Huume turn falls to `DEFAULT_PRICING` ($0.50/$3.00, overbilled ~60%), the exact bug class this file's 3.6-flash comment warns about. Keep the 3.1-flash-lite row (already-logged usage rows still carry it). Billing stays correct because lite tier is model-homogeneous and `agent.py:1288` stamps `total_usage["model"] = tier.planner_model`.

5. **Tests**
   - `tests/huume/test_usage_accounting.py` — add flash-lite parity test mirroring `test_rate_matches_admin_ledger` (MODEL_PRICING row == ai_usage.PRICING row for `gemini-3.5-flash-lite`), + assert `routing.FLASH_LITE in MODEL_PRICING`.
   - `tests/huume/test_huume_routing.py` — assert lite tier's planner/executor model is `FLASH_LITE` and its thinking is a `thinking_level` (never `thinking_budget`), pinning the 400-on-flash-lite gotcha; standard/deep still on `FLASH`.

## Verification

- `cd server && python3 -m pytest tests/huume/ tests/ems/ -q` (routing, usage accounting, ems skill tests).
- Manual smoke on dev (`dev-remote.sh` already running): in a Huume thread, stage an action (`send_offer` draft), reply "yes" → confirm logs show `gemini-3.5-flash-lite` call succeeding (no 400), staged action executes. Then an analytical ask ("which incidents need disciplinary action?") → still routes deep on 3.6-flash.
- EMS: `@huume <event>` in a dev channel → event classifies (not fallback `uncategorized`), pill posts.

## Not in scope (explicit)

- `standard`/`deep` tier models — stay 3.6-flash.
- ER/discipline/legal/handbook embedded calls — own model choices, separate discussion.
- Prod deploy — code + commit only; no env changes needed (models are code literals, no env override exists).
