# Huume × Pilots — Technical Plan

> **Status (verified 2026-07-26): IMPLEMENTED and MERGED.** All deliverables confirmed by
> symbol: 6 tools registered (`tools.py:268-339`), 6 handlers (`agent.py:601-695`),
> `evaluate_pilot_tool` + `filter_promotable_drafts`, the shared lifts
> (`legal_defense/matters.py`, `handbook_pilot.persist_turn`/`promote_drafts`/`unpaid_x_reason`),
> `_WALL_CLOCK_SECONDS = 240.0`, and `tests/huume/test_huume_pilot_tools.py`. Shipped via
> PR #71 (`78c8de3`), **merged** to `main` 2026-07-26 — the "PR #71, unmerged" note below is
> stale. Kept for history.

**Feature:** Legal Pilot + Handbook Pilot capabilities inside Huume chat ("@huume let's …") in matcha-work, replacing the need to open the dedicated pilot UIs for conversational work.

**Status note:** this plan is implemented on branch `claude/huume-chat-pilot-features-oh99pg` (PR #71, unmerged). Each section cites where. Review the plan; anything you reject gets amended in (or dropped from) the PR before merge.

---

## 1. Context & goal

- **Huume today** (`server/app/matcha/services/huume/`): a bounded Gemini tool-calling loop (8 model calls / wall-clock cap, confirm-first envelope, `step` SSE frames) dispatched for every message in a thread whose `huume_mode` column is on. One skill: end-to-end new-hire onboarding.
- **Legal Pilot** (`legal_defense` flag): matters + grounded evidence chat + attorney packet, at `/app/legal-pilot`.
- **Handbook Pilot** (`handbook_pilot` flag): sessions + grounded drafting + draft promotion, at `/app/handbook-pilot`.
- **Goal:** both pilots usable conversationally in a Huume thread, the way HR Pilot and Huume's onboarding skill already live in matcha-work.

**Key finding that shapes everything:** there is no literal `@huume` mention parser anywhere — "@huume" is the thread-mode toggle. So the feature is *new tools in Huume's registry*, not a new dispatch path. Also, both pilot services are already library-grade (take `conn` + plain dicts, no HTTP coupling); only matter/session persistence and draft promotion lived in route files.

## 2. Architecture decision

**Chat mode operates on the SAME tables the pilot UIs use.** No parallel store, no new tables, no migration.

- A matter opened/discussed in chat ↔ visible with full transcript on the Legal Pilot page.
- Drafts proposed in chat ↔ editable on the Handbook Pilot page; promotion from either surface is consistent (`promoted_ref` idempotency already handles re-promotes).
- Each Huume thread lazily owns **one** `handbook_pilot_sessions` row; the active legal matter and the session + pending-draft ids ride `mw_threads.current_state` (`huume_legal`, `huume_handbook`) so the model can echo real ids on later turns — same idiom as `huume_plans`.

Rejected alternative: nesting the pilots as a "thread mode" context block. The pilots need multi-step tool behavior (open → ask → export; draft → review → promote), which is exactly what the agent loop provides and what a single-shot context injection cannot.

## 3. New tools (6) — `services/huume/tools.py`

| Tool | Kind | Gate | Does |
|---|---|---|---|
| `list_legal_matters` | read | `legal_defense` | Tenant-scoped matter list (id/title/type/status/deadline/packet_count) |
| `open_legal_matter` | write | `legal_defense` | INSERT `legal_matters` (status `active`), audit-logged `via: huume` + thread id |
| `ask_legal_pilot` | write | `legal_defense` | Full grounded turn: `gather_evidence` → `run_chat_turn` (citation-gated) → persist BOTH sides to `legal_matter_messages` |
| `generate_legal_packet` | write | `legal_defense` | Latest-memo rule → `gather_evidence(apply_theory=False)` → `build_defense_packet` → S3 upload + `legal_matter_packets` rows. Downloads stay on the pilot page. No research attach in v1 (page-only action) |
| `draft_handbook_content` | write | `handbook_pilot` | Ensure thread session → grounding → compliance floor (outside conn — deadlock rule) → full-text corpus → `run_chat_turn` → persist turn + draft rows |
| `promote_handbook_drafts` | write | `handbook_pilot` | Promote named/all pending drafts via shared promote logic; two-turn guard (below) |

Backed by two new skill modules mirroring `onboarding_skill.py`: `services/huume/legal_skill.py`, `services/huume/handbook_skill.py`. Matter resolution for ask/packet: explicit `matter_id` → thread's active matter → sole open matter → refusal naming candidates (mirrors `resolve_plan_offer_id`'s no-guessing shape).

## 4. Safety envelope (mirrors the routes, not the skill engine)

The skill engine gates nothing itself, so every route-level guard is re-asserted on the chat path:

- **Pure verdict** `actions.evaluate_pilot_tool(tool, role, features)` — role ∈ {client, admin} (= `require_admin_or_client`), then `huume` + `matcha_work` + the pilot's own flag (= the router mount gate). Flag-off is a plain refusal the model relays, not an error (three-state idiom).
- **Unpaid-Matcha-X gate** re-applied on handbook drafting/promotion (`hp.unpaid_x_reason`, lifted from the route's `_assert_paid`).
- **Rate limit shared, not doubled**: chat drafting uses the same `handbook_pilot_chat` 40/hr per-company key as the UI.
- **Two-turn rule extends to promotion**: `actions.filter_promotable_drafts(requested, created_this_turn)` refuses explicit ids drafted this turn; "promote all" excludes them skill-side (`exclude_ids`) and refuses outright if nothing else is pending. Structural, not prompt-dependent — mirrors `built_this_turn` for onboarding plans.
- Every write audit-logged into the pilots' own audit tables with `via: huume` + `thread_id` (ip NULL — headless caller).

Deliberate scoping: promotion creates only **draft**-status handbooks/policies (non-terminal records → tool kind `write`, not `staged`), so the heavier `huume_action` staged machinery is not extended. Packet generation is an internal artifact (no outward send) → `write`, prompt-restricted to explicit asks.

## 5. Citations end-to-end

Pilot answers are only trustworthy because of the `validate_citations` gate; the chat hop must not lose that.

- Skills return resolved citation records (cid/ref/summary/when/source/source_label) for every id that survived the pilots' own gate.
- The agent accumulates them across the turn → `huume_result.citations` / `dropped_citations`.
- `_run_huume_dispatch` stores them on the assistant message `metadata` under the **same keys HR Pilot uses** — `MessageBubble` already renders `metadata.citations` via `CitationSources`/`numberCitations`, so numbered, verifiable sources render with **zero client changes**.
- System prompt instructs the model to keep bracketed `[cid]` markers verbatim when relaying evidence points.

## 6. Loop & prompt changes

- `agent.py`: 6 handlers in `call_tool`; envelope check first; `_WALL_CLOCK_SECONDS` 150 → 240 (pilot tools embed their own 90s-capped Gemini call — 150s could force-finish before the model reports a result it already paid for; the bound still kills runaway loops).
- `prompt.py`: state block renders active matter + pending drafts **with ids**; new "Legal & Handbook Pilot" section — organizer-not-advocate (no liability opinions), relay intake requests instead of presenting them as analysis, drafts-are-proposals language, two-turn promote rule, honest groundedness reporting.
- Frontend: only the Huume toggle tooltip text (`work/components/panels/constants.ts`). Step timeline and plan card work unchanged.

## 7. Shared-service lifts (routes delegate; endpoint behavior unchanged)

Per the "no helpers in routes when a service exists" rule, logic both surfaces need moved down:

- **New** `services/pilots/legal_defense/matters.py`: `load_matter` / `load_messages` / `latest_memo` (the "prefer newest turn with a non-empty evidence_map" rule is real logic worth one home) / `audit_matter`. `safe_name` → `packet.py`. Route keeps thin 404-raising wrappers.
- `services/pilots/handbook_pilot.py` gains `persist_turn` (was the route's `_persist` closure), `promote_drafts` (was ~70 inline route lines; partial-success stays first-class), `unpaid_x_reason` (was `_assert_paid`).

## 8. Out of scope (v1) — candidates for a follow-up

- External case-law research from chat (`/matters/{id}/research`) — stays a page action.
- In-chat packet download links — files land on the matter; page handles downloads.
- Draft **editing** from chat — page-only (promote/discard from chat is enough).
- Live `step`-frame rendering in the web client (pre-existing gap: frames are parsed and dropped; timeline renders post-hoc from metadata).
- Binding a chat thread to a pilot session/matter created in the UI by name.

## 9. Testing & verification

- **New** `server/tests/huume/test_huume_pilot_tools.py` (pure, no DB/Gemini): envelope refusals per role/flag, two-turn promote guard, state-block rendering, registry/prompt coverage, citation resolver.
- Suites: `pytest tests/huume/ tests/legal_defense/ tests/handbook_pilot/` → **322 passed**. `tests/matcha_work/` failures are pre-existing (verified identical with changes stashed). Client `tsc -p tsconfig.app.json --noEmit` clean.
- Manual smoke (needs dev DB + Gemini key, per repo test-data rules): toggle Huume on a thread → "open a legal matter for a mock EEOC charge" → ask a question → verify transcript on `/app/legal-pilot`; "draft a PTO policy" → verify draft on `/app/handbook-pilot` → promote next turn → verify draft policy exists.

## 10. Risks

- **Latency**: an `ask_legal_pilot` turn ≈ one pilot-page chat turn (same calls) + 2 cheap loop calls. No keepalive frames exist on the Huume SSE path (pre-existing); the pilot routes already sustain 90s gaps in prod, and each pilot tool call is preceded by a status frame.
- **`gather_evidence` cost**: same per-turn cost the pilot page pays; the 5-min law cache blunts repeats. (The lightweight `legal` thread-mode context that deliberately avoids `gather_evidence` is unchanged — this is a different, explicit-invocation path.)
- **State clobber**: `huume_legal`/`huume_handbook` flow through turn-end `state_updates` merge (single-pointer keys, not the plan-style concurrent structure) — acceptable; plans keep their locked path.

---

*Once you've reviewed: approve → PR #71 is the implementation (amendable per your notes); reject parts → I revise the PR; prefer plan-first strictly → close PR #71 and we restart from the approved plan.*
