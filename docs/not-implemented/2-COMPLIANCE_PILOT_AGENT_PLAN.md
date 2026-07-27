# Agentic Compliance Pilot — Huume-style loop in the Compliance Studio

> **Status (verified 2026-07-26): NOT IMPLEMENTED.** `server/app/core/services/compliance_pilot.py`
> is still one flat ~34KB file — no `compliance_pilot/` package, and no
> `compilot02_agent_confirm` migration exists. Build order: zero conflicts with any other
> pending plan (writes nothing under `server/app/matcha/`; Huume is a read-only structural
> template), self-contained, best leverage-per-effort — can start any time.

## Context

The admin Compliance Studio "Pilot" (`server/app/core/services/compliance_pilot.py` + `admin_tools/admin_compliance_pilot.py`) is single-shot: one Gemini JSON turn per message, mode-locked sessions (research/ask/check_sources/scope), corpus pre-built from a coordinate-guessing heuristic, and the model never sees what its own research runs produced. It has zero access to the Gen-2 scope registry (backlog, readiness, authority status). Per COMPLIANCE_SYSTEM.md: the codification engine is correct but **starved on authoring throughput**.

This converts the Pilot into an agentic bounded tool-calling loop — structurally copied from Huume (`server/app/matcha/services/huume/agent.py`), which itself copied Merlin — so an admin can **scope → find → codify** in one conversation: read coverage/backlog/readiness mid-turn, stage research/check-sources/approve actions confirm-first, and follow through on results. Huume stays byte-untouched (core can't import matcha; fresh core loop was user-approved). Ledger integration ships in the same PR (kills the documented double-spend `NOTE(fast-follow)` in `_run_research`).

**User-approved decisions**: fresh core loop; stage + approve in chat (all writes confirm-first, two-turn, structural); heavy work stays detached; one migration; test via dev-remote.sh; commit on current branch (`claude/compliance-system-overview-bvotdv`, docs PR merged), no Claude attribution in commits.

## Phase 0 — Migration

`server/alembic/versions/compilot02_agent_confirm.py`, `down_revision = "trainmap01"` (**re-verify tip of the compilot01→…→trainmap01 lineage at authoring**; repo has 17 permanent heads by design, `migrate-dev.sh` runs `upgrade heads`):
- Drop/re-add `compliance_pilot_actions_status_check` widened to `('proposed','running','done','failed','superseded','cancelled')`.
- Add `confirmed_at TIMESTAMPTZ`, `confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL`.
- `downgrade()`: remap new statuses → 'failed' before narrowing the CHECK.
- `uq_compilot_action_running` (partial, WHERE status='running') untouched.
- Commit migration BEFORE applying anywhere; then ask user, run `./scripts/migrate-dev.sh` (dev only — prod is user's later step).

## Phase 1 — Package conversion (zero behavior change)

`git mv` `compliance_pilot.py` → `compliance_pilot/core.py`. **Rewrite every relative import absolute** (`from .change_context…` at :38 + function-local `.compliance_rag`, `.embedding_service`, `.scope_registry.jurisdiction_chain`, `.vertical_coverage`, `.compliance_service`, `.compliance_evals.authority` — single dot now resolves to the subpackage; this is the matcha_work-split gotcha). `__init__.py` re-exports the route's exact surface: `PILOT_TEMPLATES, MODEL, template_catalog, get_template, build_ask_corpus, build_scope_snapshot, run_chat_turn, resolve_proposal, default_categories, run_action, _codify_gate` (underscore name explicit). Sole importer is the route (module-level `as cp` + function-local `_codify_gate` at :415); no tests import it. Boot server to verify.

## Phase 2 — Pure modules

- `compliance_pilot/actions.py` — verdict dataclass (mirror `huume/actions.py:70` HuumeVerdict: kind proceed|stage|refuse, message, ok property); `evaluate_confirm(action_row, pre_turn_proposed_ids)` (refuse non-proposed; refuse ids staged THIS turn — structural two-turn); `evaluate_stage_approve(from_action_row, ids)` (ids omitted → gate_ok subset of `result.staged_rows`; explicit ids validated ⊆ staged_ids); `supersede_targets(actions)` pure (single-slot: staging supersedes older proposed rows, huume's documented model); arg coercion.
- `compliance_pilot/prompt.py` — `build_system_prompt`: two-generation map distilled from COMPLIANCE_SYSTEM.md (Gen1 research→pending rows→approve activates+codifies; Gen2 registry **federal+CA only**; codified trio; `_codify_gate` reason vocabulary verbatim; never invent rates/citations; cite only tool-returned cids; single-slot + two-turn rules). `build_state_block(actions)`: proposed/running/recent w/ real ids, params, gate counts; explicit nothing-staged line (huume `prompt.py:20` idiom). Tools text generated from registry — never hand-duplicated.
- `compliance_pilot/tools.py` — frozen dataclass + `types.FunctionDeclaration` registry (mirror `huume/tools.py`). **Reads**: `coverage_snapshot(state,city?,industry?)` (core.build_scope_snapshot + ledger cell statuses via SELECT on `jurisdiction_vertical_coverage`); `search_catalog(query,state?,city?)` (build_ask_corpus, returns `req:` cids as `citation_records`); `list_actions`/`action_status`; `uncodified_backlog(state,city?)` (`scope_registry/codify.py:346 chain_uncodified(conn, state=, city=, labor_only=False)` — **default True would empty vertical worklists**; deterministic note appended when state≠CA and zero state-level items: "registry corpus is federal+CA — absence ≠ compliant"); `readiness(state,city?,industry)` (`compliance_evals/runner.py:415 onboarding_readiness`, `depth='core'` only if `industry_keysets.has_core(canonical)` else 'full' — raises ValueError otherwise); `authority_status()` (denormalized cols off `authority_indexes`, per `scope_registry.py:92`). **Staged**: `stage_research` (validate via existing `resolve_proposal`, INSERT status='proposed', supersede siblings, **echo action_id in tool response** so the model can name it on the confirm turn); `stage_check_sources`; `stage_approve(from_action_id, ids?)`. Plus `confirm_action(action_id)`, `cancel_action(action_id)`, `finish(message)`.

## Phase 3 — Service lifts (approve → runner → confirm order)

- `compliance_pilot/approve.py` — lift route `:405-553` into `approve_from_action(from_action_id, ids, actor_id, *, existing_action_id=None)`: `research_review.approve_staged` (opens own conn; returns activated/codified/uncodified/results/snap_targets) → per-row `_codify_gate` → `codify_from_requirement` mint (own tx per row) → ONE `reconcile_codifications` per (state,city) → stamped verdict readback. `existing_action_id` None = INSERT done-row (legacy route), set = UPDATE the proposed row running→done (confirm path; no duplicate approve rows). Move `_embed_bg`/`_snapshot_bg` here; return snap_targets/jurisdiction_ids so route uses BackgroundTasks and the detached runner just awaits them. **No ledger writes here.**
- `core.py` changes — `run_action` gains `'approve'` branch (calls approve_from_action w/ existing_action_id, then awaits embed/snapshot). Move the strong-ref `_BG_TASKS` registry + a `launch_action_task(action_id, actor_id)` helper into the package (route imports it; tools importing the route would cycle). `_run_research` ledger stamping: after research, stamp **covered/empty at research time, failed for failed** (established invariant — fill docstring `vertical_coverage.py:593`, Pipeline reject flips covered→failed `research.py:1276`, `compliance/summary.py:335` already compensates for staged-covered; covered-at-approve would leave pending cells verdict-less → sweep re-spends). Only `result["categories"]` + `result["failed"]` get stamps — skipped categories get none; `{"skipped": True}` early-return stamps nothing. Split tags: general categories (industry_tag IS NULL) under `GENERAL_TAG='general'`, industry cats under `params["industry_tag"]`; nodes from `resolve_jurisdiction_chain(...)["ids"]`; add `r.jurisdiction_id` to the staged-row SELECT (:603) for per-(node,category) counts; use `vertical_coverage._mark(...)`, same conn, try/except non-fatal; **never stamp in_progress** (wedge risk — reclaim is sweep-only). Delete the NOTE(fast-follow). Add `'agent'` template to PILOT_TEMPLATES (not in `_PROPOSAL_MODES`; starters spanning old modes).
- `compliance_pilot/confirm.py` — `confirm_and_launch(action_id, actor_id)`: stale reclaim (same 2h SQL) → research ceiling (`_MAX_CONCURRENT_RESEARCH=2`, research kind only) → CAS flip proposed→running with **`started_at=NOW()`** (else 2h reclaim instantly kills a late confirm), `confirmed_at=NOW(), confirmed_by` → catch `asyncpg.UniqueViolationError` → 409/refusal → launch task immediately (no awaits between flip and launch). `cancel_action`: CAS proposed→cancelled. Approve confirms also run **detached** via the run_action branch — never inline in the loop (wall-clock tool cancel mid-mint would strand activated-but-unreconciled rows).

## Phase 4 — Loop

`compliance_pilot/agent.py` — structural copy of `huume/agent.py` minus images/attachments/state_updates/plans: 8 calls / 240s / 60s per call, 15s heartbeat wait loop, sole-finish rule (`is_sole_finish`), `_cap_payload`/`_json_safe`/StepRecorder, `GeminiRateLimiter().check_limit/record_call("compliance_pilot","agent")` (global budget shared w/ research — loop re-raises `RateLimitExceeded` by contract), `feature_scope("core.compliance_pilot.loop")`, model `gemini-3.6-flash`. Turn-start `pre_turn_proposed_ids` snapshot; `turn_citations` accumulated from tool `citation_records` (**no `validate_citations` — citations are DB-sourced, never model-generated**; `_parse_json` not needed — native function calling). Tools open own short-lived conns (pool max 10; never hold one across the turn). Final frame `agent_result` {message, steps, citations, proposal_action_ids, token_usage, model_calls, error?}; never raises except RateLimitExceeded.

## Phase 5 — Route (`admin_compliance_pilot.py`)

- Chat endpoint branches on `session.mode == 'agent'`: short conn block loads history/actions + persists user msg → stream agent frames → catch RateLimitExceeded → friendly error frame → persist assistant msg metadata `{steps, citation_records, proposal_action_ids}` under **`asyncio.shield`** (client abort cancels the generator; tools already staged rows) → bump updated_at. Legacy modes: existing path untouched.
- `POST /actions/{id}/confirm` + `POST /actions/{id}/cancel` → same service fns (404/409 mapping). Button + chat funnel through one executor.
- Legacy `POST /sessions/{id}/actions` (direct running) + `/approve` (thin wrapper over approve.py w/ BackgroundTasks) keep working.
- Optionally add confirmed_at/by to `_load_actions`/`get_action` SELECTs.

## Phase 6 — Frontend

- `client/src/api/sse.ts` — optional `onStep?` in `ChatHandlers` + branch in `streamPilotChat` (~:220); other consumers untouched.
- `client/src/api/admin/compliancePilot.ts` — `PilotMode` + 'agent'; `ActionStatus` + proposed/cancelled/superseded; `PilotStep`; `MessageMeta` {steps?, citation_records?, proposal_action_ids?}; `confirmAction`/`cancelAction`; `streamPilotChat` opts pass-through (currently drops opts — AbortController has nothing to attach to otherwise).
- `client/src/components/ui/StepTimeline.tsx` — **copy** of `work/components/panels/HuumeStepTimeline.tsx` with local Step type + header-label prop (client/CLAUDE.md forbids admin importing work/; cappe precedent is parallel impl). work/ byte-untouched.
- `pilot/Console.tsx` — pendingSteps accumulator (reset on send/turn-end; live render inside status bubble; persisted render from `metadata.steps` — reconciliation drops live msgs on role+content match, so persistence is load-bearing); **`citation_records` render branch** (old `citations` is {point,cited_ids} shape — same key would render garbage); ProposedActionCard (Confirm/Cancel → REST, refetch); ActionCard branches for proposed/cancelled/superseded (anything non-running/failed currently falls into done-rendering and would break); abortRef + Stop via `components/pilot/usePilotChat.ts:29-50` idiom.
- `pilot/PilotTab.tsx` — `MODE_ICON['agent']` (Record<PilotMode,…> typecheck breaks without it); creation UI: agent primary, legacy templates de-emphasized.

## Phase 7 — Tests + verification

- `server/tests/compliance_pilot/` — pure, no DB/no Gemini (conftest genai stub exists), mirroring `tests/huume/test_huume_actions.py` style: two-turn snapshot exclusion, confirm-of-non-proposed refused, gate_ok-only approve default, supersede targets, state-block rendering (real ids + nothing-staged line), backlog federal-note determinism, arg coercion.
- Verify: commit migration → (ask user) `./scripts/migrate-dev.sh` → `./scripts/dev-remote.sh` (backend :8001, frontend :5174 tmux — never pkill by port pattern) → curl SSE agent session end-to-end: scope → stage_research → confirm → poll → stage_approve → confirm → codified verdicts; UI pass in Studio Pilot tab → `cd client && npx tsc -p tsconfig.app.json --noEmit` → `./venv/bin/python -m pytest tests/compliance_pilot tests/huume tests/scope_registry tests/compliance_evals -q`.
- Commits: incremental per phase, clean messages, no attribution. Scope ends at commit (+ PR if asked).

## Key reference files

- `server/app/core/services/compliance_pilot.py` (→ core.py) — templates, corpus builders, `_codify_gate`, `run_action`/`_run_research`
- `server/app/core/routes/admin_tools/admin_compliance_pilot.py` — route, approve body to lift, `_BG_TASKS`, stale reclaim
- `server/app/matcha/services/huume/agent.py` / `tools.py` / `prompt.py` / `actions.py` — structural template (loop, registry, state block, evaluators)
- `server/app/core/services/scope_registry/codify.py:346` chain_uncodified; `compliance_evals/runner.py:415` onboarding_readiness; `research_review.py:28` approve_staged; `vertical_coverage.py` `_mark`/GENERAL_TAG/general_coverage_map
- `client/src/pages/admin/studio/pilot/Console.tsx`, `PilotTab.tsx`, `client/src/api/admin/compliancePilot.ts`, `client/src/api/sse.ts`, `client/src/work/components/panels/HuumeStepTimeline.tsx`
