# Agentic Merlin — Cappe Page Editor AI Overhaul

## Context

Merlin (Cappe's AI chat page editor on gummfit.com) is today a **single-shot structured completion**: chat message + full block/theme snapshot → one Gemini call → validated op list → client applies. It never sees the rendered page (root cause of the two 2026-07-21 bad-restyle incidents), has no tool use, no iteration, no server-side conversation storage (localStorage only), no chat image upload, and a bland 320px panel. Model tiers (lite/regular/max) only swap model + thinking_level.

Goal: make Merlin a real agent — a function-calling loop that applies ops virtually, renders + screenshots its own work (playwright already in requirements; render service already produces standalone HTML from unsaved state), critiques visually, and revises — plus persisted conversations, chat image upload (place / style-reference / gen-conditioning), inline native image generation the model can see and retry, auto model routing, and a better panel UI.

**User decisions locked in:** full tool loop (premium tiers only, Lite stays single-shot) · multiple named conversations per page · Auto tier default with manual override · all three chat-image uses.

**Key verified facts:**
- Loop template exists in-repo: `server/app/matcha/services/research_browse_service.py` + `server/app/workers/tasks/research_browse.py` (Gemini function_declarations + screenshots as `Part.from_bytes` + function responses).
- `render_site_html` (`server/app/cappe/services/render.py`) renders full HTML from unsaved snapshot (same call as `POST /sites/{id}/preview`).
- SSE client parser exists at `client/src/api/sse.ts` but is matcha-token-bound — cappe needs its own copy (boundary rule).
- **`server/Dockerfile` does NOT run `playwright install chromium`** — browser binaries must be added to the image (verified missing; ~300MB).
- Image gen: `core/services/image_gen.py`, `IMAGE_MODEL="gemini-3.1-flash-image-preview"`, S3 `cappe/gen`, daily quota 3 free / 30 paid.
- Tiers (`services/merlin_catalog.py`): lite=gemini-3.5-flash-lite/minimal/45s · regular=gemini-3.6-flash/low/45s · max=gemini-3.6-flash/high/90s.
- AI ledger (`ai_usage_log`) auto-captures every wrapped genai call — no extra wiring.
- Existing tests: `server/tests/cappe/test_merlin_turn.py`, `test_merlin_ops_registry.py`, `test_merlin_validation.py`.

**Contracts to preserve:** client-state-is-truth (server NEVER writes `cappe_pages`/`cappe_sites`; agent works on the request snapshot, final ops return to client → `applyMerlinOps` → one undo step → user Saves) · `validate_ops` stays the single op gate · never-raises (only `RateLimitExceeded` → 429; everything else degrades) · free-tier stays cheap.

---

## Phase 1 — Server-persisted conversations + panel overhaul

**Migration** `server/alembic/versions/zzzzcappe22_merlin_conversations.py` (revises `zzzzcappe21`, raw-SQL style):

- `cappe_merlin_conversations`: id, account_id FK cappe_accounts CASCADE, site_id FK, page_id FK cappe_pages CASCADE, title VARCHAR(120) DEFAULT 'New conversation', created_at, updated_at. Index `(page_id, updated_at DESC)`.
- `cappe_merlin_messages`: id, conversation_id FK CASCADE, role CHECK ('user','assistant'), content TEXT, results JSONB (op chips), steps JSONB (Phase-2 agent trace), attachments JSONB (Phase-4), tier VARCHAR(16), created_at. Index `(conversation_id, created_at)`.
- Real downgrade (two DROPs). Never auto-apply — user runs migrate scripts.

**Server** (`server/app/cappe/routes/merlin.py` + `models/cappe.py`):
- CRUD: `GET /sites/{site_id}/pages/{page_id}/merlin/conversations` (list), `GET/PATCH/DELETE /merlin/conversations/{id}`, `POST .../conversations`. All ownership-checked (`get_owned_site` + conversation→account check).
- `CappeMerlinChatRequest` gains `conversation_id: Optional[UUID]`; chat route persists user+assistant rows, bumps updated_at; absent id → auto-create titled from first ~60 chars, return `conversation_id` in `CappeMerlinChatResponse`. When conversation_id present, server loads last-10-turn history itself (client `history` field kept as fallback one release).

**Client:**
- `useMerlin.ts`: conversation state (list/create/rename/delete/switch) replaces localStorage transcript. Keep live-snapshot ref, navigation guards, one-undo-per-turn, TIER_KEY.
- `MerlinPanel.tsx`: conversation header (dropdown list + new/rename/delete), markdown bubbles (`react-markdown` + `remark-gfm` — already client deps), drag-resize left edge (min 320 / max 560, persisted `cappe:merlin-width`; `index.tsx` `reservedRight` must read the live width, not hardcoded 320).

**Tests:** `server/tests/cappe/test_merlin_conversations.py` — ownership isolation, auto-create-on-chat, cascade. `npx tsc -p tsconfig.app.json --noEmit`.

---

## Phase 2 — Agentic tool loop with SSE (Regular/Max)

**Endpoint:** `POST /sites/{site_id}/merlin/agent` → SSE `StreamingResponse`. Premium + tier∈{regular,max} runs the loop; otherwise falls through server-side to the single-shot path and emits its result as one `result` frame (client has one code path).

**SSE frames** (`data:{json}\n\n`, end `data:[DONE]`):
- `{type:'status', message}` — "Rendering preview…"
- `{type:'step', kind:'ops'|'screenshot'|'critique'|'image', label, results?, image_url?}` — persisted as `steps` JSONB
- `{type:'result', data:{message, ops, rejected, tier, conversation_id, steps}}`
- `{type:'error', message}`

**New `server/app/cappe/services/merlin_apply.py`** — server-side port of the client's `merlinOps.ts` apply-fold: `apply_ops(blocks, theme, ops) -> (blocks, theme, results, temp_id_map)`. Applies validated ops to a **virtual working copy of the request snapshot** — never DB. Parity guard: shared JSON fixture (snapshot, ops, expected) asserted by both `server/tests/cappe/test_merlin_apply.py` and a client-side test mirror in `merlinOps.test.ts`.

**New `server/app/cappe/services/merlin_agent.py`** — the loop, modeled on `research_browse_service.py`. Function declarations:
1. `apply_ops(ops)` — `validate_ops` (existing gate) → `merlin_apply.apply_ops` on working copy; function response = per-op ok/reject reasons; valid ops append to the turn's ordered op log.
2. `render_screenshot(viewport: 'desktop'|'mobile')` — `render_site_html` on working copy → playwright screenshot → PNG as image Part to the model + uploaded to S3 `cappe/merlin-shots/{site_id}/` for the panel step frame.
3. `inspect_block(block_id)` — full-fidelity block JSON (base prompt is noise-stripped).
4. `finish(message)` — end loop.
5. (Phase 4 adds `generate_image`.)

System prompt = existing `_build_prompt` fragments + loop instructions (apply → screenshot to verify → critique own screenshot → revise → finish). Bounds: regular = 6 model calls / 3 screenshots / 120s; max = 10 / 5 / 240s. Bound-hit → force-finish with op log so far. Errors degrade to `error` frame + validated ops so far (never-raises preserved).

**Result:** ordered validated op log → client applies via existing `applyMerlinOps` → one `onApply` → one undo step. Server still never writes pages.

**New `server/app/cappe/services/browser_pool.py`:** lazy process-wide chromium singleton + `asyncio.Semaphore(2)`, fresh context per shot, recycle browser every 50 shots or on error. Inline (not Celery): interactive SSE turn, srcDoc-local HTML renders in ~200–600ms, singleton amortizes launch. Graceful degrade: chromium missing → `render_screenshot` returns error function-response, model proceeds without vision.

**Dockerfile:** add `RUN playwright install --with-deps chromium` (or install-deps split) to `server/Dockerfile` — verified currently absent. ~300MB image growth; flag to user at deploy time.

**Rate limits:** new redis counter `cappe_merlin_agent` (20/hr paid) on top of the existing per-turn one; `GeminiRateLimiter.check_limit`/`record_call` around every model call inside the loop. Ledger free (auto-wrapped client).

**Client:**
- New `client/src/cappe/sse.ts` (cappe copy of consumeSSE/postSSE) + `cappeStreamHeaders()` in `cappe/api.ts` (proactive token refresh before stream — streams can't replay 401).
- `useMerlin.ts`: regular/max/auto → agent endpoint; live steps accumulate on placeholder assistant message; AbortController on page navigation.
- `MerlinPanel.tsx`: agent step timeline in assistant bubble (icon per kind, expandable screenshot thumbnails), streaming status line.

**Tests:** `test_merlin_agent.py` — scripted mock Gemini tool-call sequence; op-log accumulation, bounds, rejection feedback, force-finish, SSE shapes. `test_merlin_apply.py` parity fixtures. Skip-if-no-chromium browser_pool integration test.

---

## Phase 3 — "Auto" model routing

- New `server/app/cappe/services/merlin_router.py`: `route_tier(message, has_selected_block, history_tail)` — one gemini-3.5-flash-lite call (minimal thinking, JSON out `{"complexity":"trivial"|"standard"|"complex"}`, 6s timeout) → lite/regular/max. Heuristic pre-filter skips the call for obvious cases (<6 words + selected block → lite). Failure → regular. Free plans never call it (`resolve_model_tier` clamps auto→lite first).
- `model_tier` becomes `Literal["auto","lite","regular","max"] = "auto"`; response gains `routed: bool`.
- Client always hits `/merlin/agent` on auto; **server** routes (loop vs inline single-shot). `MERLIN_TIERS` gains Auto as first/default; panel badges resolved tier per message ("Auto → Max").
- Tests: `test_merlin_router.py` — clamps, heuristic skips, fallback, premium gating.

---

## Phase 4 — Chat images + inline generation

- **Upload:** reuse `POST /sites/{id}/upload` (5MB raster) from panel attach button. Chat/agent requests gain `attachments: list[{url, mime}]` (max 4), persisted on message row.
- **Server:** fetch attachment bytes from S3 (size-capped, S3-host-allowlisted — never arbitrary URLs), append as `Part.from_bytes` + caption Part. Model infers intent: place (`set_field` with URL) or style-reference (design ops from pixels). Downscale attachments + screenshots to ≤1280px before sending.
- **Conditioning:** `image_gen.generate_image` gains `reference_images: list[bytes]|None` (additive). Agent tool 5: `generate_image(prompt, aspect, block, field, attachment_index?)` — executes inline against the shared daily quota (refactor uploads.py quota increment into shared service fn), returns URL as function response **plus image bytes as Part so the model sees its output and can retry**, appends `set_field` to op log. Agent-path results contain no `generate_image` ops (already resolved — client `runImageOps` split skipped); Lite single-shot keeps today's client-side execution.
- **Client:** attach button + thumbnails above textarea (reuse `cappeApi.upload` like `FieldInputs.tsx`); attachments render in user bubbles.
- **Tests:** conditioning unit test (mocked genai), agent quota-exhaustion, attachment allowlist.

---

## Sequencing

1 → 2 → 3 → 4. Each phase independently shippable. No new feature flag — premium gating via existing `is_premium_plan` clamps.

## Verification (end-to-end)

- Per phase: `cd server && python3 -m pytest tests/cappe/ -q` + `cd client && npx tsc -p tsconfig.app.json --noEmit`.
- Phase 1: migrate dev (`./scripts/migrate-dev.sh`, user runs), create/rename/resume conversations across reloads on :5174.
- Phase 2: local run — ask Merlin (Max) "make the hero look premium" on a dark-theme test site; watch step timeline show screenshot + critique; verify ops apply + single undo; verify Lite still single-shot. Verify graceful degrade with chromium absent.
- Phase 3: short message + selection routes lite; "redesign this page" routes max; badge shows routing.
- Phase 4: attach photo → "use as hero image"; attach moodboard → "match this style"; "generate a variation of this photo" → conditioned gen; quota exhaustion returns clean error.
- Deploy note: Dockerfile chromium layer + prod migration (`./scripts/migrate-prod.sh`) are user-run gates.
