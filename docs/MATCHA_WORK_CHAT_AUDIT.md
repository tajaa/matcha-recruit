# Audit — matcha-work Compliance/Payer chat

## Context

`/work/:threadId` lets companies ask grounded questions about payer coverage (Medicare NCD/LCD) and multi-jurisdiction employment compliance. Three thread-level boolean modes (`node_mode`, `compliance_mode`, `payer_mode`) select context builders; a fourth pill ("Agent") is frontend-only with no server counterpart.

We audited the whole path — chat-turn route, context builders, RAG retrieval, AI provider, frontend — for correctness bugs and inefficiencies. Every CRITICAL and most HIGH findings below were re-verified by reading the source directly, not taken on a subagent's word.

The system works, but it has three classes of real defect: **money leaks** (expensive turns billed at ~$0), **wrong-answer paths** (Medicaid answered with Medicare policy; a 500-employee company told it has 50), and **a dead-but-reachable endpoint** whose auth/quota behavior diverges from the live one.

Note: root `CLAUDE.md` still describes `routes/matcha_work.py` as "8,902 lines (cohesive — not a split candidate)". It was split into a 17-file package on 2026-07-03. Worth fixing while we're here.

---

## Findings

### CRITICAL

**C1 — Payer turns are billed at ~$0.** `matcha_work_ai.py:1164` — the payer branch returns `AIResponse(assistant_reply=reply, structured_update=None)` with **no `token_usage`**. `messaging.py:990` then falls back to `estimated_usage`, which `estimate_usage` (`matcha_work_ai.py:1433`) builds with `completion_tokens=None` and `_get_model(self.settings)` — the *default flash* model, not the Pro model the payer branch actually called. Payer mode is the most expensive combo in the system (Pro + Google Search grounding) and it bills the input-only estimate at flash prices. Same shape on all three JSON-salvage fallbacks (`:1292`, `:1327`, `:1341`) and on image generation (`:1116`, whose model isn't in `MODEL_PRICING` at all → `DEFAULT_PRICING`).

**C2 — `POST /threads/{id}/messages` + `payer_mode` = guaranteed 500, after billing.** `messaging.py:303` binds `user_msg` to the saved message row; `messaging.py:418` rebinds it to `body.content or ""` (a `str`) inside the payer branch, unconditionally, before the `if _api_key and user_msg:` guard. `messaging.py:575` then calls `_row_to_message(user_msg)`, whose first line is `row.get("metadata")` (`_shared.py:25`) → `AttributeError` on a str. The AI call has already run, both messages are persisted, and tokens are deducted (`:565`) before the crash. A retrying client double-charges. The streaming handler is immune — it uses locals and never touches `user_msg`.

**C3 — No pgvector index. Every RAG query is a sequential scan.** Zero `ivfflat`/`hnsw` anywhere in `app/` or `alembic/` (verified by grep). The only indexes on `compliance_embeddings` (`database.py:3105`, `:3109`) and `payer_policy_embeddings` (`:3188`) are btrees on `jurisdiction_id`/`category`/`payer_name`. So `ORDER BY embedding <=> $1::vector` (`compliance_rag.py:117`, `payer_policy_rag.py:77`) computes cosine distance against every row on every message. The operator, the `LIMIT`, and the SQL-side similarity threshold are all correct — none of it helps without an index. Latency grows linearly with the corpus, forever.

**C4 — Node mode reports a 50-row sample as the company total.** `matcha_work_node.py:45-51` fetches employees with `LIMIT 50`; `:123` emits `f"Total active: {len(employees)}"` and `:125-129` compute the by-department and by-state breakdowns over those same 50 rows. All of it is injected under a header that reads *"You have access to the company's real internal data below… Do NOT fabricate."* (`:98-102`). A 500-employee company is authoritatively told it has 50 employees. Policies (20), handbooks (10), ER cases (20), IR incidents (20) are likewise capped with no "showing N of M" marker.

### HIGH

**H1 — The non-streaming endpoint bypasses the token quota entirely.** `check_token_quota` has exactly one callsite: `messaging.py:642`, in the streaming handler. The non-streaming handler only calls `token_budget_service.check_token_budget` (`:292`). A user who is 429'd on `/messages/stream` can generate without limit on `/messages`. No client calls `/messages` today (web and desktop both use `/messages/stream` — verified), but it is mounted and auth'd with `require_admin_or_client`, so any token holder can hit it directly.

**H2 — The two handlers disagree about whose company a thread belongs to.** Non-streaming: `company_id = await get_client_company_id(current_user)` (`:277`). Streaming: `company_id = thread["company_id"]` (`:629`, with a comment explaining collaborators may belong to another company or none). For a cross-company thread collaborator, the non-streaming path builds node/compliance context from the *caller's* company and injects it into the *thread owner's* shared thread, then bills the caller. Same endpoint, opposite tenancy model.

**H3 — Client cancel leaks the model call and skips all accounting.** `_ai_task = asyncio.create_task(...)` at `messaging.py:880`, awaited at `:898`, **never cancelled** — there is no `finally`, no `.cancel()`, no `request.is_disconnected()` check. On disconnect Starlette cancels the generator, `CancelledError` re-raises past `:1059`, and the `log_token_usage_event` / `deduct_tokens` at `:999-1021` never run. The Gemini call continues to completion in the background. Every "stop" click is a fully-paid, entirely-unbilled turn.

**H4 — The prompt cache never hits; it creates a new Gemini cache every message.** `messaging.py:391/396/399/404` append live-web, node, compliance, and **question-specific RAG** context into `ctx`, which is passed as `company_context=ctx` (`:451`, `:881`) into `static_prompt = MATCHA_WORK_STATIC_PROMPT_TEMPLATE.format(company_context=…)` (`matcha_work_ai.py:1519`). The cache key is `md5(static_prompt)` (`:981`). RAG context varies with every user message, so the "static" hash changes every turn. In compliance mode, caching is a strict net loss — `caches.create` cost and latency on every message, zero reuse.

**H5 — Medi-Cal and `medicaid_other` are searched as Medicare.** `payer_policy_rag.py:152` — `if p_lower in ("medicare", "medi_cal", "medicaid_other"): normalized.append("Medicare")`. A California location contracted with Medi-Cal gets Medicare coverage and prior-auth rules returned as its policy basis. Two distinct programs, conflated, on a clinical-billing question.

**H6 — A location with no `payer_contracts` silently searches all payers.** `payer_policy_rag.py:122` leaves `payer_names = None`, and `search_policies` then omits the `payer_name = ANY(...)` filter entirely. A company contracted only with Aetna, whose location row lacks `facility_attributes->'payer_contracts'`, gets Medicare/Cigna/UHC policies injected as if in-network. Fails open, not closed.

**H7 — The compliance RAG industry filter drops every untagged requirement.** `compliance_rag.py:102` — `AND ce.applicable_industries && $idx::text[]`. Array overlap against a NULL column yields NULL → row excluded. Any company with an `industry` set silently loses all baseline/universal requirements embedded without an industry tag — potentially federal law — from semantic search.

**H8 — Frontend: `streaming` never resets on thread switch, permanently disabling the input.** `MatchaWorkThread.tsx:159-176` — the load effect doesn't reset `streaming`, and the cleanup calls `abortRef.current?.abort()` with no reason; `matchaWork.ts:1051` treats a reason-less abort as user-initiated and fires neither `onComplete` nor `onError`. Send in thread A, click thread B mid-stream → B mounts with `streaming=true` stuck. Disabled input and a permanent "Thinking…" until full reload. Same class: a stream that ends without a `complete`/`error` event (`matchaWork.ts:1005-1047`) hangs the spinner.

**H9 — `javascript:` href XSS via model- and RAG-sourced URLs.** `MessageBubble.tsx:195` (`href={s.source_url}`) and `ComplianceDecisionTree.tsx:148` (`href={data.sourceUrl}`) render untrusted URLs raw. A `sanitizeHref` that rejects `javascript:`/`data:`/`vbscript:` already exists at `markdownToHtml.ts:18` and is not applied at either site. Payer `source_url` values come from Gemini research and CMS scraping — the ingest-side validation is UNCONFIRMED, so treat the raw href as live.

**H10 — N+1 over jurisdictions, with no dedup.** `matcha_work_node.py:252` calls `resolve_jurisdiction_stack` inside the per-location loop; each call runs the recursive CTE at `compliance_service.py:8463`. The screenshot's 8 jurisdictions = 8 round trips. Two locations in the same city run the byte-identical query twice. Collapsible to one `jurisdiction_id = ANY($1)`.

**H11 — The context cache is process-local, never invalidated, unbounded, and unlocked.** `matcha_work_node.py:29-33` — module-level dicts keyed on `str(company_id)`. Under blue-green or multiple workers each process holds its own copy. Editing a `jurisdiction_requirement` is invisible for up to 120s per process (nothing clears on write). Entries are TTL-checked on read but never evicted. No lock, so two concurrent turns for one company both miss and both rebuild.

**H12 — An over-budget deduction is rejected, swallowed, and the usage is never recorded.** `token_budget_service.py:117` raises when `free+sub < total_tokens`; `messaging.py:566` and `:1018` catch `HTTPException` and only `logger.warning`. The transaction rolls back, so `free_tokens_used` never advances. A company sitting just under its limit — 100 tokens left, 5,000 per turn — passes `check_token_budget` (100 > 0), generates, fails the deduction, and repeats forever. Unlimited free full-quality answers.

### MEDIUM

- **M1** — "Flash Lite 3.1" is a silent no-op. `constants.ts:2` sends `gemini-3.1-flash-lite-preview`; `SUPPORTED_MODELS` (`matcha_work_ai.py:712`) contains `gemini-3.1-flash-lite`. `_get_model` sees an unsupported override and falls through to the plan default. The user's selection is dropped without error.
- **M2** — Compliance context has no size cap. All active `business_locations` (no LIMIT), 30 categories each with unbounded `all_levels`, plus an entirely uncapped legacy-requirements fallback (`matcha_work_node.py:298-337`). 40 locations → tens of thousands of tokens per turn, on top of node context and a separate RAG block. The RAG builders enforce a char budget; the primary builder does not.
- **M3** — Compliance mode retrieves twice: `build_compliance_context` dumps the full resolved requirement set, then `_get_rag_context` re-embeds the question and semantic-searches the same `jurisdiction_requirements`, appending a second block. Extra embedding hop + a full seq scan (C3) every turn.
- **M4** — Mode-toggle/send race. `handleModeToggle` (`MatchaWorkThread.tsx:462`) POSTs then sets state; `handleSend` sends no mode flags because the backend reads persisted thread state. Toggle Compliance then immediately send → the send can land first, answered without compliance context. The `catch {}` at `:470` hides a failed toggle entirely.
- **M5** — The two handlers' context-building blocks are near-identical copies (`messaging.py:393-435` vs `:799-859`) and have *already drifted*: streaming lacks the live-web pre-pass and the anti-hallucination scrub; non-streaming lacks image attachments (`:327` builds role/content only), the WS broadcast, and the quota check. Every fix applied to one silently misses the other.
- **M6** — The evidence status line is reverse-engineered from prose. `messaging.py:808-819` does `ctx.count("Decision path:")`, `ctx.count("FACILITY PROFILE")`, `ctx.count("[trigger:")` against a string another module formats. `[trigger:` appears at both category and level scope, so the trigger count is inflated. Any wording change in `matcha_work_node.py` silently yields "0 categories across 0 locations". `compliance_result.reasoning_chains` already holds these counts structurally.
- **M7** — The model is instructed at length to emit inline SVG charts (`matcha_work_ai.py:525-556`), but `MessageBubble.tsx:3,43` uses `react-markdown` without `rehype-raw`, so the SVG renders as escaped source text. (Do **not** fix by adding `rehype-raw` — that missing plugin is what currently blocks raw-HTML XSS from model output.)
- **M8** — ~18–22 discrete `get_connection()` acquisitions per node+compliance turn, several redundant: `ai_turn.py:600` and `:578` run the identical `SELECT … FROM mw_projects WHERE id=$1` twice per turn; `_get_affected_employees` and `_detect_compliance_gaps` run sequentially on separate connections.
- **M9** — `EmbeddingService` (a `google.genai` Client) is constructed per request at `messaging.py:58/421/843`, against `server/CLAUDE.md`'s "cache the model handle; don't instantiate per request."
- **M10** — Check-then-deduct TOCTOU: budget is read at turn start, deducted at turn end. Ten concurrent sends all pass the initial check. No reservation, no advisory lock.

### LOW

- `ceiling` precedence returns the *most general* (federal) row (`compliance_service.py:8584`), contradicting the "state caps local" semantics the prompt asserts (`matcha_work_node.py:218`); adjacent dead `else sorted_rows[0]` branch is unreachable.
- Precedence-rule selection is "last specific rule wins" with no tie-break (`compliance_service.py:8557`) — order-dependent when two specific rules cover one category.
- Attribute comparisons (`compliance_service.py:8422`) can `TypeError` on a str-vs-numeric trigger and fail the entire turn's compliance context, unguarded at the callsite.
- `classify_thinking_level` computes `"high"` for payer mode (`matcha_work_ai.py:843`) but the payer branch never passes `thinking_config`. Dead.
- `_get_or_create_cache` is unsynchronized (`matcha_work_ai.py:990`); concurrent first-messages create duplicate caches, one leaking until TTL.
- Compliance evidence panels are hidden when the model omits `referenced_categories` (`MessageBubble.tsx:12,141`) — pure model-trust, no server backstop.
- `healthcare_specialties` is fetched and never used (`compliance_rag.py:194`); the `<=>` distance is computed twice per query, in both `WHERE` and `ORDER BY`.
- `asyncio.create_task` results not retained (`messaging.py:572,777,968,1047`) — the loop holds only a weak reference; a compaction or collaborator broadcast can be GC'd.
- `_row_to_message` on the "Agent" pill: no backend flag exists at all.

---

## Recommended remediation order

**Tier 1 — money and correctness, no schema change, all localized.**
1. Payer branch returns real usage (`matcha_work_ai.py:1164`): capture `response.usage_metadata` via the existing `_extract_usage_metadata` and pass the *clamped* `model`. Same for the three JSON-salvage returns and image generation.
2. Fix `estimate_usage`'s model so fallbacks don't bill flash for Pro work (`matcha_work_ai.py:1433`).
3. Cancel `_ai_task` in a `finally` on the streaming path; log+deduct usage on the cancel path (`messaging.py:880-898`).
4. Stop swallowing the failed deduction (`messaging.py:566`, `:1018`) — clamp to zero-remaining and record, or fail the turn.
5. `payer_policy_rag.py:152` — stop mapping Medicaid to Medicare. `:122` — fail closed when a company has no payer contracts.
6. `matcha_work_node.py:123` — emit a real `COUNT(*)` and mark truncated lists as "showing 50 of N".
7. `compliance_rag.py:102` — `(applicable_industries IS NULL OR applicable_industries && $n)`.
8. Apply the existing `sanitizeHref` at `MessageBubble.tsx:195` and `ComplianceDecisionTree.tsx:148`.
9. Reset `streaming` on thread change and on reader-`done` without a terminal event (`MatchaWorkThread.tsx:159`, `matchaWork.ts:1005`).
10. `constants.ts:2` — `gemini-3.1-flash-lite-preview` → `gemini-3.1-flash-lite`.

**Tier 2 — the divergent endpoint.** No client calls `POST /threads/{id}/messages`. Recommend **deleting it** rather than fixing C2/H1/H2/M5 four times over. If it must stay, it needs the quota check, the thread-scoped `company_id`, the `user_msg` rebind fixed, and image attachments — at which point it is the streaming handler minus SSE, and the duplication should be collapsed into one shared turn function.

**Tier 3 — performance. Requires a migration (prod DDL → explicit approval per `CLAUDE.md`).**
- `CREATE INDEX … USING hnsw (embedding vector_cosine_ops)` on `compliance_embeddings` and `payer_policy_embeddings`. Build `CONCURRENTLY`; this is the single highest-leverage change in the audit.
- Collapse the jurisdiction N+1 into one `= ANY($1)` query, dedup by `jurisdiction_id`.
- Move the context cache to Redis (already in the stack) with write-invalidation on requirement edit, or accept process-local and add an `asyncio.Lock` + size bound.
- Cap compliance context, and drop the redundant second retrieval (M3).

**Tier 4 — hygiene.** Replace the substring-counting status line with `reasoning_chains` counts. Singleton the `EmbeddingService`. Dedup the `mw_projects` fetch. Update root `CLAUDE.md`'s stale `matcha_work.py` line.

---

## Verification

Backend is already running on `:8001` under `dev-remote.sh` (frontend `:5174`) — do not `pkill` by port pattern, track any throwaway process by PID.

- **C1/H3 (billing):** send a payer-mode message, then `SELECT model, prompt_tokens, completion_tokens, cost_dollars FROM mw_token_usage_events ORDER BY created_at DESC LIMIT 1` against the **dev** DB (`:5432`). Pre-fix: flash model, null completion, ~$0.0001. Post-fix: pro model, real completion count. Then click stop mid-stream and confirm a row still lands.
- **C2:** `curl -X POST /api/matcha-work/threads/<payer-mode-thread>/messages` with a bearer token. Pre-fix: 500 with `AttributeError`. Post-fix: 404/410 (deleted) or 200.
- **C3:** `EXPLAIN ANALYZE` the `compliance_rag` query before and after the index — expect `Seq Scan` → `Index Scan using …_hnsw`.
- **C4:** seed >50 employees on a dev company, enable node mode, ask "how many employees do we have?" Pre-fix: "50".
- **H5/H6:** set one dev location's `facility_attributes->payer_contracts` to `["medi_cal"]`, ask a coverage question, confirm returned `payer_sources[].payer_name` is not `Medicare`. Then null the contracts out and confirm the search no longer returns other payers.
- **H8:** send in thread A, click thread B mid-stream, confirm B's composer is enabled.
- **H9:** insert a dev `payer_medical_policies` row with `source_url = 'javascript:alert(1)'`, confirm the rendered anchor has no href.
- Regression: `cd server && ./venv/bin/python -m pytest tests/matcha_work/ -q` — expect the documented baseline of 12 failed / 126 passed / 8 skipped, unchanged.

---

## Supplement (2026-07-09) — remediation status + engine findings from the node-system deep-dive

### Status

All CRITICAL/HIGH/MEDIUM findings above are **fixed** on `claude/map-newest-commit-scope-s2avft`, with two deliberate exceptions:
- **M10** (check-then-deduct TOCTOU) — deferred; the H12 clamp bounds over-run to one turn per concurrent request. A reservation pattern can come later.
- **Tier 2** resolved by **deletion**: `POST /threads/{id}/messages` is gone (zero callers verified across web, Werk Swift, and tests). C2/H1/H2/M5 died with it. Route count 204 → 203.

Tier 3's HNSW migration is **authored, not applied**: `server/alembic/versions/hnswvec01_hnsw_vector_indexes.py`. Apply via `./scripts/migrate-dev.sh` → `./scripts/migrate-prod.sh` (CONCURRENTLY; non-transactional — check for INVALID indexes if a build is interrupted).

### Engine findings beyond the original audit (all fixed)

- **Ceiling picked the wrong row.** `determine_governing_requirement`'s ceiling branch took `sorted_rows[-1]` — the most *general* row in the chain (federal, if present) — not the rule's higher jurisdiction. Root cause: the CTE didn't even propagate `higher_jurisdiction_id`. Now propagated; ceiling resolves to the rule's jurisdiction with the old behavior as fallback. The adjacent `else sorted_rows[0]` was dead (unreachable) and is removed.
- **Precedence LEFT JOIN fanout.** Two active rules matching one category duplicated every requirement row in it — `all_levels` carried duplicates, the single-level render path was defeated, trigger counts inflated. Requirement rows are now deduped by id while every (row × rule) pairing still competes for rule selection; specific rules tie-break by most-local `lower_jurisdiction_id`.
- **Trigger `TypeError` killed whole turns.** A string facility attribute vs a numeric trigger (`"120" >= 100`) raised through an unguarded chain and killed the SSE stream mid-turn (compounding with H8's stuck spinner). Comparisons now coerce and degrade to not-matched with a warning; the compliance/node context builders are guarded in the stream so failures degrade to a status notice.
- **Fail-open on malformed triggers** (unknown op/type → True) is *retained* for the v2 passthrough predicates and documented here rather than flipped — silently deactivating requirements is a data-owner decision, not a code fix.
- **Roster sample was nondeterministic.** The old `LIMIT 50` had no `ORDER BY` — the by-state breakdown was computed over a planner-dependent sample, so "do we have employees in Colorado?" could flip between cache expiries. Aggregates now come from a full-roster GROUPING SETS query; the name listing is ordered and labeled as a sample.

### Combined-mode extensions shipped alongside the fix

**Node × Compliance**
- **NC1 — deterministic threshold engine**: federal headcount thresholds (Title VII 15, ADEA/COBRA 20, FMLA/ACA 50, EEO-1/WARN 100) computed in code from the real roster and injected as a `FEDERAL HEADCOUNT THRESHOLDS` block + `threshold_status` metadata (chips in `MessageBubble`). `employee_count`/`employee_count_state` are also injected into `facility_attributes` (setdefault — explicit attrs win) so data-authored jurisdiction triggers can gate on headcount deterministically.
- **NC2 — remote-state coverage**: the compliance jurisdiction set is now locations ∪ `DISTINCT work_state`. States with employees but no business location get a state-level stack labeled "Remote — ST (N remote employees)"; previously those employees' state obligations were structurally invisible.
- **NC3 — pre-turn counts**: per-location and per-state employee counts render inside each facility profile, so the model reasons *from* true numbers instead of a post-hoc, model-gated metadata card.
- **NC4 — gap detection upgrade**: policy *content* (first 2KB) is matched as well as titles; gap cards deep-link to Handbook Pilot (`/app/handbook-pilot?draft=<category>`).

**Node × Payer** (previously zero interaction)
- **NP1 — payer × staff grounding**: per-location payer contracts × headcount × role mix, injected into the payer system prompt (payer turns bypass the generic company context, so it rides `payer_context`).
- **NP2 — credential risk**: expired/expiring-≤90d licenses grouped by location render as a `CREDENTIAL RISK` block. Feature-detected by data presence in `employee_credentials`, not flag-gated.
- **NP3 — fail-closed notes**: no contracts → explicit "no payer contracts configured" context; contracts with no matching corpus → "no policy data found for <payers>; answers are not grounded" (never silently searching all payers, never substituting Medicare for Medicaid).
- **NP4 — staff-under-cited-payers**: post-turn metadata (`payer_affected_staff`) counting staff at locations contracted with the payers the answer actually cited; chips in `MessageBubble`.

### Verification notes (container)

- New unit tests: `server/tests/compliance/test_engine_and_node_fixes.py` (13 tests — ceiling, fanout dedupe, trigger coercion, payer normalization, threshold engine). All pass.
- `pytest tests/matcha_work/` failure set is **byte-identical before vs after** the change (this container's baseline differs from the venv's documented 12F/126P/8S for environment reasons — missing native deps — but the stash/unstash diff is empty, i.e. zero regressions).
- `npx tsc --noEmit` clean.
- The DB-dependent checks in the Verification section above (EXPLAIN ANALYZE, payer-mode billing rows, >50-employee headcount answers) remain user-side — run them against dev after applying `hnswvec01`.

### Post-implementation code review (2026-07-09, same branch)

An 8-angle review of the branch diff surfaced 10 findings; 7 are fixed in the follow-up commit:

1. **Gap-detection over-match** — single-word keywords ("safety", "wage") vs 2KB of policy body suppressed real gaps. Now: single-word keywords match titles only; multi-word phrases may match content heads.
2. **Remote-state casing/format** — `business_locations.state` is free-entry while `work_state` is code-normalized; `'Ca'`/`'california'` locations made their state look remote. Now normalized via `_norm_state` (codes uppercased, full names mapped through the shared `_STATE_NAME_TO_CODE`).
3. **Cancel-window gap** — the billing finalizer only covered disconnects during generation; a disconnect during apply/persist/PDF-render still skipped billing. The whole post-AI phase is now covered.
4. **Duplicated accounting** — the finalizer and happy path each had a copy of cost→log→deduct; both now call one `_record_turn_usage(operation=…)`.
5. **Zero-staff payer chips** — `HAVING COUNT(e.id) > 0`.
6. **Orphaned live-web pre-pass** — `needs_live_web_context`/`fetch_live_web_context` (only caller was the deleted handler) removed. If live grounding is wanted on the streaming path, it's a deliberate future feature, not a revival of this code.
7. **Unbounded `_build_locks`** — now capped (512) with unlocked-entry eviction.

**Open decisions deliberately NOT changed** (flagged for the owner):
- **Conditional second RAG pass** — the primary dump is trigger-filtered and active-only; the per-question vector search was neither. Skipping it when the dump isn't truncated (per M3) drops retrieval of trigger-non-matching / non-active rows for the common case. If that matters, re-enable unconditionally or pass `statuses=["active"]` + drop the trigger filter difference knowingly.
- **FMLA-50 dual encoding** — `FEDERAL_HEADCOUNT_THRESHOLDS` (matcha_work_node) and `leave_eligibility_service.py:116` independently hardcode the FMLA 50 threshold. A shared employment-law constants module would prevent drift.
- **Derived counts in facility_attributes** — `employee_count`/`employee_count_state` are injected via `setdefault` for trigger evaluation and the mutated dict is persisted into reasoning-chain metadata, blurring user-set vs derived. Cleaner: separate derived dict merged only at evaluation time.
