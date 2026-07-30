# Merlin Setup Concierge (Cappe)

## Context

New Cappe signups finish the 2-step wizard and land on the site dashboard (`CappeSiteEditor.tsx`) facing a manual `SetupGuide` checklist. Meanwhile Merlin — the AI builder — is locked inside the page editor, strictly page-scoped, with no reach into anything the checklist asks for (products, newsletter, promos, pages). Goal: a site-scoped Merlin concierge on the dashboard that greets the new user by name ("Hey {name}, let's set up your website — where should we start?") and conversationally sets up site features, personalized by `account_type` (solo creator vs business).

**Decided (by user):**
- **Hybrid confirm-first writes** — server-row actions (create page, add blocks, create product, booking type, promo) are STAGED proposals the user approves, then the server executes. Same plan-then-approve philosophy as matcha's Huume, reimplemented minimally in cappe (parallel-stack rule: no matcha imports).
- **Surface** — chat panel on the CappeSiteEditor dashboard, driving the existing `SetupGuide`/readiness.
- **Free plan gets full agent-loop access** on this surface (setup drives activation); own rate limit ~20/hr.

**Key architecture facts (verified):**
- Merlin conversations: `cappe_merlin_conversations.page_id` is NOT NULL today; page-scoped queries (`store.py:list_conversations` WHERE page_id=$1) + the page-mismatch 404 in `routes/merlin.py` naturally exclude NULL-page rows → site-scoped rows can't leak into the page editor.
- The page agent loop (`services/merlin/agent.py:run_merlin_agent`) is snapshot/screenshot-coupled → setup agent is a **sibling loop**, not a parameterization. Same for `_prepare_turn` → a parallel smaller preamble; `route_tier`/`AGENT_TIERS` untouched.
- Backend already has everything: products (`routes/shop.py`, `require_fulfillment` gate), newsletter subscribers/campaigns (`routes/newsletter.py`), bookings (`routes/bookings.py`, `CappeBookingTypeCreate`), promos (`meta_config.promos`, rendered `services/render/page.py:_promos`), page presets (client `data/cappePagePresets.ts`), readiness (`services/readiness.py:compute_readiness`), entitlements (`services/entitlements.py:resolve_entitlements`, `is_premium_plan` via `services/design_gate.py`).
- Promos have NO server-side write gate today (client-only premium hiding) — concierge's `set_promo` gate is first server enforcement.
- SSE client helper exists: `client/src/cappe/sse.ts:postCappeSSE`. Registry-as-data pattern to copy: `services/merlin/ops.py:MERLIN_OPS` (validate + prompt_shape + prompt_rules per entry).

## Phase 0 — drive-by premium drift fix (independent)
- `client/src/cappe/pages/site/PageEditor/DesignPrimitives.tsx:7-10` — `usePremium()` add `'creator'` (server `design_gate.PREMIUM_PLANS` already has it).
- `client/src/cappe/pages/site/PageEditor/FieldInputs.tsx:149` — same inline check.

## Phase 1 — schema + store

**New migration `server/alembic/versions/zzzzcappe27_merlin_setup_concierge.py`** (revises zzzzcappe26, additive):
```sql
ALTER TABLE cappe_merlin_conversations ALTER COLUMN page_id DROP NOT NULL;
ALTER TABLE cappe_merlin_conversations ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'page';
ALTER TABLE cappe_merlin_conversations ADD COLUMN IF NOT EXISTS staged_actions JSONB;
CREATE INDEX IF NOT EXISTS idx_cappe_merlin_convos_site_kind
  ON cappe_merlin_conversations(site_id, kind, updated_at DESC);
ALTER TABLE cappe_merlin_conversations ADD CONSTRAINT ck_cappe_merlin_convo_scope
  CHECK (kind <> 'page' OR page_id IS NOT NULL);
```
Downgrade: delete NULL-page rows, drop constraint/index/columns, restore NOT NULL. Author only — **never auto-apply** (repo rule); user runs `./scripts/migrate-dev.sh`.

**`server/app/cappe/services/merlin/store.py`:**
- `create_conversation`: `page_id: Optional[UUID]`, new `kind: str = "page"` param.
- New `list_site_setup_conversations(conn, site_id, account_id)` (kind='setup').
- `get_owned_conversation`: SELECT adds `kind, staged_actions`.
- New `mutate_staged_actions(conn, conversation_id, fn)` — `SELECT ... FOR UPDATE` inside `conn.transaction()`, decode JSONB, apply fn, write back. Cap ~10 pending (prune oldest proposed).

**`server/app/cappe/models/merlin.py`:** `CappeMerlinSetupRequest` (conversation_id?, message 1..2000, fallback history ≤20 — no blocks/theme/attachments), `CappeSetupActionEntry` (id, type, summary, payload, status `proposed|executed|dismissed|blocked`, result, created_at, executed_at), `CappeSetupActionResult` (action, message, readiness). Conversation models gain `kind`; detail gains `staged_actions`.

## Phase 2 — action registry (pure core)

**New `server/app/cappe/services/merlin/setup_actions.py`:**
- `SetupActionSpec` frozen dataclass: name, `validate(payload, ctx)`, `gate(entitlements, plan) -> Optional[str]`, `execute(conn, site, account, payload)`, `summary(payload)`, `prompt_shape`, `prompt_rules` — MERLIN_OPS registry-as-data pattern so prompt/validator can't drift.
- `SETUP_ACTIONS` v1:
  - `create_page` — title + optional preset `about|contact|services|shop` (server-side `SETUP_PAGE_PRESETS` mirroring `cappePagePresets.ts`, composed from `section_presets.py` where shapes match) + optional blocks. Execute mirrors `routes/pages.py:create_page` (slug derive, UNIQUE(site_id,slug) → `-2` suffix, sort_order max+1, status draft).
  - `add_blocks` — page_id + blocks appended to `content.blocks`, validated against `catalog.BLOCK_TYPES`/`BLOCK_FIELDS`. Covers newsletter-signup block, store block, booking block. Execute re-reads content at execute time; module docstring marks this the sanctioned exception to client-state-is-truth (dashboard has no open editor).
  - `create_product` — CappeProductCreate subset (no option groups v1); gate `require_fulfillment`; execute reuses shop.py INSERT + `refresh_site_search`.
  - `create_booking_type` — CappeBookingTypeCreate subset.
  - `set_promo` — read-modify-write `meta_config.promos` bar|popup (shape from `PromosPanel.tsx` / `_promos`); gate `is_premium_plan`.
- `evaluate_setup_action(action, *, entitlements, plan, account_type, this_turn_staged) -> Verdict` — **pure, DB-free**. Huume envelope: confirm-first (same-turn staged refused), per-type validation, gate.
- `execute_setup_action(conn, site, account, entry)` — re-resolves entitlements, re-runs evaluate (authoritative), executes, all in one transaction row-locking the conversation; flips entry to `executed` with result ids. Idempotent: any status ≠ `proposed` refuses (409 REST / refusal payload tool-path). Gate failure at execute → entry `blocked` + human message, never raw 403 to panel.

**Entitlement UX rule:** gates run at STAGE time (early, phrased as guidance — creator asking digital download → "your plan sells sessions and services; want a booking session instead?"; free asking promo → upgrade chip) AND execute time (authoritative).

**New `server/tests/cappe/test_merlin_setup_actions.py`** (DB-free): payload validation per type, gate matrix (creator+digital blocked w/ alternative; free+set_promo blocked; business ok; free+physical product ok), confirm-first refusal, idempotency verdicts.

## Phase 3 — context, agent loop, routes

**New `server/app/cappe/services/merlin/setup_context.py`:**
- `build_setup_context(conn, site, account)` — account name/account_type/plan; entitlements summary; `compute_readiness` items; page inventory (id/title/slug + block-type list per page); products (count + up to 10 rows); booking-type count; subscriber count; promos state; staged actions.
- `build_setup_prompt(context)` — pure/testable. `_SETUP_INSTRUCTIONS` persona + confirm-first rules (always stage never claim executed; one action per stage call; after execution suggest next readiness gap; entitlement lack → plain statement + nearest allowed alternative) + registry-generated action shapes/rules + account_type guidance block.

**New `server/app/cappe/services/merlin/setup_agent.py`:**
- `run_setup_agent(...)` — sibling of `run_merlin_agent`: same contents management, thought_signature echo, parallel-call handling, RateLimitExceeded passthrough, never-raises, force-finish on bounds. No screenshots/images/working-copy. Bounds: 6 model calls / 90s wall / 60s per call. Model = `MODEL_TIERS["regular"]` hard-pinned (no `route_tier`, free included). `GeminiRateLimiter().check_limit("cappe_merlin", "agent")` per call.
- Tools: `stage_action(type, payload_json)` (validate+gate → append proposed entry via `mutate_staged_actions` → `staged_action` SSE frame; gate failure returns `{blocked: reason}` to model, nothing staged), `execute_staged_action(action_id)` (chat-confirm path; refuses same-turn ids + non-proposed), `finish(message, links_json?)` — links target whitelist `shop|subscribers|campaigns|bookings|settings|design|pages|page:<id>|billing|publish`.
- `stream_setup_turn(...)` — sibling of `agent_stream.stream_agent_turn`: frames `status|step|staged_action|error|result` + `[DONE]`; shielded disconnect-safe persistence of assistant message; step kinds grow `staged`/`executed`. Authoritative staged state = conversation row (reload rebuilds cards).

**New `server/app/cappe/routes/merlin_setup.py`** (mount in `routes/__init__.py` after merlin_router):
- `GET /sites/{site_id}/merlin/setup/conversations`
- `POST /sites/{site_id}/merlin/setup/agent` — `_prepare_setup_turn`: rate limit `check_rate_limit(account_id, "cappe_merlin_setup", 20, 3600)` → resolve-or-create conversation (kind='setup', page_id=None; named id must be owned + kind match + site match else 404) → load_history → add user message → build context → StreamingResponse.
- `POST /merlin/setup/conversations/{cid}/actions/{aid}/execute` — execute + append assistant "Done — created …" transcript message + return `{action, message, readiness}` (fresh `compute_readiness`).
- `POST /merlin/setup/conversations/{cid}/actions/{aid}/dismiss` — row-locked status flip.

**Tests:** `test_merlin_setup_agent.py` (fake genai client mirroring `test_merlin_agent.py`: stage frame, same-turn execute refused, prior-turn ok, links whitelist, bound force-finish); `test_merlin_setup_context.py` (prompt assembly from canned context).

## Phase 4 — frontend

**New `client/src/cappe/pages/CappeSiteEditor/useSetupMerlin.ts`** — small sibling of `useMerlin` (that hook is page-coupled; don't reuse). State: messages, sending, liveSteps, conversations, conversationId, stagedActions. `send()` via `postCappeSSE('/sites/{id}/merlin/setup/agent', ...)`; `approve/dismiss` → REST, update cards, fire `onSiteChanged(actionType, readiness)`; conversation open/new.

**New `client/src/cappe/pages/CappeSiteEditor/SetupMerlinPanel.tsx`** — docked drawer + floating launcher on dashboard. Renders:
- Canned client-side greeting (zero model calls): `Hey {firstName}, let's set up your website — where should we start?` — not persisted; resumed conversation shows real transcript.
- Suggested chips by `account_type` (const table): personal → "Sell a booking session", "Sell a digital download", "Make an about-me page", "Collect emails with a newsletter signup"; business → "Create a newsletter signup", "Add a promo banner", "Sell a product", "Make an about page". Chips send prefilled message.
- Staged-action cards: summary + payload highlights + Approve/Dismiss; executed → check + result link; blocked → upsell note + Upgrade link.
- `finish` link buttons (target→route map mirroring `SetupGuide.actionTo`; `publish` → existing publish handler).
- Auto-open when `location.state?.fromOnboarding` OR (site unpublished AND readiness not ready AND setup-conversation list empty).

**Edits:**
- `useCappeSiteEditor.ts` — expose `bumpSetupRefresh()` (SetupGuide refreshKey) + `reloadPages()`.
- `CappeSiteEditor.tsx` — mount panel with `onSiteChanged`/`onPublish`.
- `CappeOnboardingWizard.tsx:53` — single-location navigate adds `state: { fromOnboarding: true }`.
- `client/src/cappe/types.ts` — `CappeSetupAction`, `CappeSetupActionResult`, conversation `kind`.

## v1 scope cuts (explicit)
- Newsletter campaign compose/send via chat — deep-link `/campaigns` only; v1 = newsletter block + subscribers link.
- Multi-location awareness; page-content editing ops on dashboard (append-only add_blocks); no client op-vocabulary changes (merlin_apply_cases.json untouched); no attachments/image-gen in setup turns; no staged theme changes (deep-link design); no logo/domain actions; no product edit/delete.

## Verification
1. `cd server && python3 -m pytest tests/cappe/ -q` — new + existing merlin suites (esp. `test_merlin_conversations.py` after store signature change).
2. `cd client && npx tsc -p tsconfig.app.json --noEmit` (never bare `tsc --noEmit`).
3. Migration: author + rehearse on dev via `./scripts/migrate-dev.sh` (user runs; never auto-apply).
4. Manual (dev-remote, reserved test-domain signup): wizard → dashboard auto-open + greeting/chips → "Sell a product" → staged card → Approve → product exists, SetupGuide `offering` flips, next-step suggestion; creator asks digital download → in-chat refusal + booking alternative; free asks promo → upgrade chip; required readiness done → publish suggestion; reload → transcript/cards persist; page-editor Merlin unaffected.
