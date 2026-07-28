> **Status (verified 2026-07-26): IMPLEMENTED and MERGED.** All 10 phases confirmed present
> by symbol in the current tree — P0 `huume_mode` on both response models
> (`models/matcha_work.py:412,446`) plus its guard test, P1 types + `utils/huumeState.ts`,
> P2–P9 components/props/toasts. Shipped via PR #71 (`dda54d1`, `79b574f`), merged to `main`
> 2026-07-26; commits confirmed ancestors of HEAD. The original note below said the work sat
> on an unmerged branch — that is stale. Kept for history.

**Status: Implemented** (all 10 phases below landed on `claude/huume-chat-pilot-features-oh99pg`).

# Huume Agent UI Improvements — matcha-work web thread (technical plan)

## Context

The Huume agentic harness (backend) is solid, but the matcha-work thread UI barely surfaces it. Exploration found one **blocking bug** and a pile of state the backend already produces that the UI throws away. Goal: meaningful UI improvements for working with Huume — strictly **extending** (new optional props/fields/components, widened gates); nothing removed, no existing behavior changed.

Findings driving this plan:
- **Bug:** `huume_mode` missing from `ThreadListItem` + `ThreadDetailResponse` (`server/app/matcha/models/matcha_work.py:399-411, 425-446` — the other 8 mode columns are declared). Pydantic v2 `extra="ignore"` silently drops it → on reload the Huume pill shows OFF, list badge never renders, `showHuumePanel` (reads `thread?.huume_mode`) is false so `HuumePlanCard` never mounts. Turn dispatch still works (backend reads the DB row) — only the UI lies.
- The confirm-first gate (`current_state.huume_action`) has **zero UI** — user must type "confirm" in chat.
- Step frames + `metadata.huume_steps` carry `args`/`result` (≤4KB each, from the harness work in `d8833d1`) — TS `HuumeStep` drops them.
- REST plan-execute posts an assistant summary message (`metadata.huume_event: "plan_executed"`, `huume.py:129-133`) that is never broadcast → invisible until reload. Offer accept/decline broadcasts a message live (no `exclude_user`) but never refreshes `current_state` → offer chip stale.
- `huume_legal` / `huume_handbook` invisible; huume empty state shows irrelevant HR-Chat prompts; huume thread with nothing staged shows no panel (HuumePlanCard's empty state at lines 191-199 is dead code).

User decisions: **full package**; Confirm/Cancel **auto-send** the chat message (still a separate user turn — backend two-turn envelope holds).

**Deferred:** stop/abort button (client abort doesn't stop the server turn; sender's SSE is the only delivery channel), live usage-frame display, mobile mode pills, `huume_runs` read endpoint.

## Verified wiring facts (rely on these; all read from source)

- `handleSend(overrideContent?: string, slideIndex?: number)` — `useThreadController.ts:139`; guards `if (!threadId || !content || streaming || togglingMode) return`.
- `useThreadCollaboration(threadId, setMessages)` — `useThreadCollaboration.ts:7-10`; connect effect deps `[threadId]` only → new callback param must go through a ref.
- `RightPanels.tsx:127,131`: AgentPanel + PDF iframe each suppressed by `!showHuumePanel` — widening the gate needs a `(!pdfUrl && !agentMode)` clause or huume threads with nothing staged lose the offer-letter PDF.
- Refetch precedent: `RightPanels.tsx:104` (ResumeBatchPanel/LanguageTutor blocks): `getThread(threadId!).then(t => { setThread(t); setMessages(t.messages ?? []) })`.
- Routes verified: `/app/employees/:employeeId` (`AppRoutes.tsx:74`, FeatureGate `employees`), `/app/legal-pilot`, `/app/handbook-pilot`.
- `useToast` import: `import { useToast } from '../../../components/ui'` → `toast(msg, 'success'|'error'|'info')` (repo memory: this exact API, not an object arg).
- Plan 400 details are plain prose (multi-candidate list interpolated into the sentence, `actions.py:284-289`) — display verbatim, never parse.
- Offer accept/decline broadcast does NOT exclude the sender → WS-triggered refetch reaches the thread owner.
- `OfferChip` (HuumePlanCard.tsx:60-75) checks `offer.status === 'rejected'` for declined — backend writes the offer row's own status; keep as-is.
- `MWCreateResponse` in types.ts already has `huume_mode: boolean` — only the two *backend* models are missing it.
- Client has vitest (`npm run test:run`), co-located `*.test.ts(x)` convention (`client/src/api/sse.test.ts`, `client/src/work/api/baseSocket.test.ts`).
- `MWStreamEvent` already includes `{ type: 'step'; data: HuumeStep }` and `keepalive`.

---

## Phase 0 — Backend fix (prerequisite)

### `server/app/matcha/models/matcha_work.py`

Add one line to each model, after `hr_pilot_mode: bool = False`:

```python
class ThreadListItem(BaseModel):           # ~line 408
    ...
    hr_pilot_mode: bool = False
    huume_mode: bool = False               # ← add

class ThreadDetailResponse(BaseModel):     # ~line 440
    ...
    hr_pilot_mode: bool = False
    huume_mode: bool = False               # ← add
```

Comment to include (one line above each, or a shared note on the first): `# Every THREAD_MODES column must be declared here — Pydantic v2 extra="ignore" silently drops undeclared fields (huume_mode was invisible to the client until 2026-07). Guarded by tests/matcha_work/test_thread_response_mode_fields.py.`

### New test: `server/tests/matcha_work/test_thread_response_mode_fields.py`

Pure, no DB/Gemini. Registry-driven so the *next* mode can't repeat the bug:

```python
"""Guard: every ThreadMode column is declared on the thread response models.

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_thread_response_mode_fields.py -q

The serializers spread `**{m.column: ...}` from THREAD_MODES; Pydantic v2's
default extra="ignore" silently drops any column the model doesn't declare.
huume_mode shipped undeclared and the client could never see the mode after
a reload — this test makes that failure loud for the next mode too.
"""
from app.matcha.models.matcha_work import ThreadDetailResponse, ThreadListItem
from app.matcha.services.matcha_work.matcha_work_modes import THREAD_MODES


def test_all_mode_columns_on_list_item():
    missing = [m.column for m in THREAD_MODES if m.column not in ThreadListItem.model_fields]
    assert missing == []


def test_all_mode_columns_on_detail_response():
    missing = [m.column for m in THREAD_MODES if m.column not in ThreadDetailResponse.model_fields]
    assert missing == []


def test_mode_columns_default_false():
    # A missing column in an old row must deserialize as off, never error.
    for model in (ThreadListItem, ThreadDetailResponse):
        for m in THREAD_MODES:
            assert model.model_fields[m.column].default is False
```

Edge cases: none at runtime — `bool = False` default means rows predating any mode column deserialize fine; the change also surfaces `huume_mode` in PATCH/mode-toggle/pin responses (clients ignore unknown fields; safe).

---

## Phase 1 — Client types + typed accessor

### `client/src/work/types.ts` (Huume section, ~l.491; all additive)

```ts
export interface HuumeStep {
  seq: number
  tool: string
  kind: 'read' | 'staged' | 'write' | 'finish'
  label: string
  status: 'ok' | 'rejected' | 'error' | 'skipped'
  detail?: string
  /** Tool-call input/output, capped server-side at ~4KB each (agent.py
   * _cap_payload — oversized values arrive as {_truncated, preview}).
   * Absent on messages persisted before the harness started recording them. */
  args?: unknown
  result?: unknown
}
```

`MWMessageMetadata` — add after `huume_run_id?: string`:

```ts
  /** Backend-authored Huume lifecycle notices (offer accept/decline routes,
   * REST plan-execute). Unknown future values must render as a plain bubble. */
  huume_event?: 'offer_accepted' | 'offer_declined' | 'plan_executed'
  offer_id?: string
```

New types after `HuumePlans`:

```ts
export interface HuumeActionSendOffer {
  type: 'send_offer'
  offer_id: string
  status: 'proposed' | 'sent' | 'failed' | 'cancelled'
}

export interface HuumeActionDiscipline {
  type: 'discipline_draft'
  status: 'proposed' | 'filed' | 'failed' | 'cancelled'
  confirm_id: string
  employee_name?: string
  infraction_type?: string
  severity?: string
  occurrence_dates?: string[]
  description?: string
  expected_improvement?: string
}

/** `current_state.huume_action` — the single staged confirm-first action.
 * Confirm/cancel are chat-only tools; the UI's buttons send the literal
 * words through the normal message path (a separate user turn, so the
 * backend's structural two-turn rule is untouched). */
export type HuumeAction = HuumeActionSendOffer | HuumeActionDiscipline

export interface HuumeLegal { matter_id: string; title?: string | null }

export interface HuumeHandbook {
  session_id: string
  pending_drafts: { draft_id: string; kind?: string; title?: string }[]
}
```

### New file: `client/src/work/utils/huumeState.ts`

```ts
import type { HuumeAction, HuumeHandbook, HuumeLegal, HuumeOffer, HuumePlans } from '../types'

export interface HuumeState {
  plans: HuumePlans
  offer?: HuumeOffer
  action?: HuumeAction
  legal?: HuumeLegal
  handbook?: HuumeHandbook
}

/** The one place `current_state`'s untyped Huume keys are cast. The server
 * owns these shapes (services/huume/ writes them); absent keys mean the
 * feature simply hasn't been used in this thread. */
export function getHuumeState(state: Record<string, unknown> | null | undefined): HuumeState {
  if (!state) return { plans: {} }
  return {
    plans: (state.huume_plans as HuumePlans | undefined) ?? {},
    offer: state.huume_offer as HuumeOffer | undefined,
    action: state.huume_action as HuumeAction | undefined,
    legal: state.huume_legal as HuumeLegal | undefined,
    handbook: state.huume_handbook as HuumeHandbook | undefined,
  }
}

/** True when anything Huume-related is staged/tracked in this thread. */
export function hasHuumeContent(h: HuumeState): boolean {
  return Object.keys(h.plans).length > 0 || !!h.offer || !!h.action || !!h.legal
    || !!(h.handbook && h.handbook.pending_drafts?.length)
}
```

Refactors (pure, values identical): `HuumePlanCard.tsx:185-186` and `MatchaWorkThread.tsx:28` use `getHuumeState`.

### New test: `client/src/work/utils/huumeState.test.ts` (vitest)

Cases:
- `getHuumeState(null)` / `(undefined)` → `{ plans: {} }`, every optional undefined.
- `getHuumeState({})` → same.
- Full state round-trips each key.
- `hasHuumeContent`: empty → false; plans-only → true; action-only → true; legal-only → true; `handbook: { session_id, pending_drafts: [] }` → **false** (no drafts = nothing to show); handbook with 1 draft → true.

---

## Phase 2 — Panel gate widening

### `client/src/work/pages/MatchaWorkThread.tsx` (replace lines 28-29)

```ts
import { getHuumeState, hasHuumeContent } from './work/utils/huumeState'   // (correct relative path: '../utils/huumeState' from pages/, verify at edit time)

const huume = getHuumeState(thread?.current_state)
// Panel shows whenever huume content exists. With huume mode on but nothing
// staged, it shows only if it wouldn't displace the PDF preview / AgentPanel
// (RightPanels suppresses both behind showHuumePanel) — that keeps the
// offer-letter PDF visible in a huume thread with no staged content.
const showHuumePanel = !!(thread?.huume_mode && thread?.current_state
  && (hasHuumeContent(huume) || (!pdfUrl && !agentMode)))
```

`huume` is also used by Phase 3's banner — compute once here, pass down.

Edge cases:
- huume thread + `task_type==='offer_letter'` (pdfUrl set) + nothing staged → PDF still renders (regression test c in smoke matrix).
- huume thread + agentMode on + nothing staged → AgentPanel still renders.
- huume + project task_type: pre-existing quirk (both panels render inside `md:contents`) — unchanged by this plan; do not "fix" silently.
- `hasRightPanel` (l.30) picks up the widened gate automatically — mobile chat/panel toggle now works for bare huume threads.

---

## Phase 3 — Staged-action card (Confirm/Cancel)

### New file: `client/src/work/components/panels/HuumeActionCard.tsx`

```ts
import { AlertTriangle, CheckCircle2, FileSignature, ShieldAlert } from 'lucide-react'
import type { HuumeAction } from '../../types'

interface HuumeActionCardProps {
  action: HuumeAction
  lightMode?: boolean
  /** Disables Confirm/Cancel while a turn is streaming — the backend would
   * queue the message anyway, but the staged state may be about to change. */
  streaming?: boolean
  /** Sends the literal chat text through the thread's normal send path.
   * Confirm/cancel are chat-only tools by design (actions.evaluate_huume_action):
   * the click still produces a separate user turn, so the backend's
   * structural two-turn confirm rule is fully preserved. No REST twin exists. */
  onSendChat?: (text: string) => void
  /** 'panel' = full card inside HuumePlanCard; 'banner' = slim strip between
   * ChatMessages and ChatComposer (the mobile-reachable surface). */
  variant?: 'panel' | 'banner'
}

export default function HuumeActionCard({ action, lightMode, streaming, onSendChat, variant = 'panel' }: HuumeActionCardProps)
```

Render logic:

| `action.status` | Render |
|---|---|
| `proposed` | Orange-accented card/strip (Huume's mode color): header "Awaiting your confirmation"; body per type (below); buttons **Confirm** (emerald solid, `onClick={() => onSendChat?.('confirm')}`) + **Cancel** (bordered, `onClick={() => onSendChat?.('cancel')}`), both `disabled={streaming || !onSendChat}` |
| `sent` / `filed` | Compact emerald chip: `CheckCircle2` + "Offer sent" / "Write-up filed" (panel variant only; banner renders `null`) |
| `failed` | Red notice: `AlertTriangle` + "The last action failed — ask Huume what happened." |
| `cancelled` | `null` |

Body per type:
- `send_offer`: `FileSignature` icon, "Ready to send the offer for signature." + `offer_id` in `text-[10px]` mono (the OfferChip nearby carries the human context).
- `discipline_draft`: `ShieldAlert` icon, definition rows — `employee_name`, `infraction_type` + `severity ?? 'moderate'`, `occurrence_dates?.join(', ')`, `description` (`line-clamp-3`), `expected_improvement` if present. Missing fields render as "—", never crash (fields optional in type).

Type-narrowing edge case: unknown `action.type` (future action types) → render generic "An action is staged — reply in chat to confirm or cancel." with the same buttons; never `null` (silent-invisible staged action is the failure mode this card exists to fix). Implement via `switch (action.type)` with a default branch, not exhaustive narrowing.

Clearing: no local state — the card is pure over `action`; `onComplete` replaces `current_state` wholesale and the card re-renders/disappears.

### Banner mount — `MatchaWorkThread.tsx`, between `<ChatMessages>` and `<ChatComposer>` (after l.71)

```tsx
{thread?.huume_mode && huume.action?.status === 'proposed' && (
  <HuumeActionCard
    action={huume.action}
    variant="banner"
    lightMode={lm}
    streaming={streaming}
    onSendChat={(t) => c.handleSend(t)}
  />
)}
```

Note `handleSend` no-ops while `streaming || togglingMode` (l.141) — the disabled state mirrors truth.

### Theme — `MatchaWorkThread/theme.ts`

Add two keys to `ThreadTheme` + both palettes (banner variant consumes them via a new optional `th?: ThreadTheme` prop or plain lightMode ternaries — prefer theme keys per file's own convention):

```ts
  huumeCardBg: string      // project: 'bg-[#2a2211] border-[#5a4a22]' ; light: 'bg-orange-50 border-orange-200' ; dark: 'bg-orange-950/30 border-orange-900/50'
  huumeCardText: string    // project: 'text-[#ce9178]' ; light: 'text-orange-800' ; dark: 'text-orange-200'
```

(Exact hex tuned at implementation; requirement: readable in all three palettes — project editor, zinc light, zinc dark.)

**As-implemented note:** `HuumeActionCard` ended up self-contained with its own lightMode ternaries (matching `HuumePlanCard`'s existing pattern) rather than consuming `ThreadTheme` keys — no `theme.ts` change was needed in practice.

---

## Phase 4 — Huume panel restructure (extend `HuumePlanCard`)

### `client/src/work/components/panels/HuumePlanCard.tsx`

Props — all new ones optional (no call-site break):

```ts
interface HuumePlanCardProps {
  state: Record<string, unknown>
  threadId: string
  lightMode?: boolean
  onStateUpdate: (offerId: string, plan: HuumePlan) => void
  streaming?: boolean                       // NEW — gates buttons during a turn
  onSendChat?: (text: string) => void       // NEW — powers HuumeActionCard
  onExecuted?: () => void                   // NEW — full thread refetch after execute
}
```

Main component uses `getHuumeState(state)`. New section order:

1. Header ("Huume" label) + `OfferChip` — existing.
2. `{action && <HuumeActionCard action={action} variant="panel" lightMode={lightMode} streaming={streaming} onSendChat={onSendChat} />}`
3. Pilot chips row (new small block):
   ```tsx
   {legal && (
     <Link to="/app/legal-pilot" className={…amber chip…}>
       <Scale size={12} /> Legal matter: {legal.title ?? legal.matter_id}
     </Link>
   )}
   {handbook && handbook.pending_drafts?.length > 0 && (
     <Link to="/app/handbook-pilot" className={…zinc chip…}>
       <BookOpen size={12} /> Handbook: {handbook.pending_drafts.length} pending draft{s}
     </Link>
   )}
   ```
   Plain `react-router-dom` `Link`s to matcha routes — allowed (work→matcha route navigation isn't a module import; no boundary-rule entry needed). Comment: `// Deep links into the pilot pages — FeatureGate on those routes handles a company that lost the flag.`
4. Existing `PlanSection`s (unchanged structure; Phase 6 polish).
5. Empty state — condition becomes `!hasHuumeContent(huume)` (previously `planEntries.length === 0 && !offer`; now also false when only an action/legal/handbook chip exists).

### `client/src/work/pages/MatchaWorkThread/RightPanels.tsx`

Destructure additions from `c`: `handleSend` (already exports). Huume block becomes:

```tsx
{showHuumePanel && (
  <HuumePlanCard
    state={thread!.current_state}
    threadId={threadId!}
    lightMode={lightMode}
    streaming={streaming}
    onSendChat={(text) => handleSend(text)}
    onStateUpdate={(offerId, plan) => { /* existing merge unchanged */ }}
    onExecuted={() => {
      // The REST execute posts an assistant summary message
      // (metadata.huume_event = plan_executed) but does NOT broadcast it —
      // full refetch is how it appears without a reload. Safe to replace
      // `messages` because execute is disabled while streaming (Phase 6).
      getThread(threadId!).then(t => { setThread(t); setMessages(t.messages ?? []) }).catch(() => {})
    }}
  />
)}
```

Edge case: `onExecuted` refetch failing silently (`.catch(() => {})`) leaves the summary invisible until reload — acceptable; `lastSummary` inline text already shows the result.

---

## Phase 5 — Expandable step timeline

### `client/src/work/components/panels/HuumeStepTimeline.tsx`

```ts
import { useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronRight, XCircle, Clock, FileSearch, Bot } from 'lucide-react'

function PayloadBlock({ label, value, lightMode }: { label: 'args' | 'result'; value: unknown; lightMode?: boolean }) {
  // JSON.stringify can throw on circular refs (shouldn't occur — payloads are
  // JSON-parsed from SSE — but a metadata edit must never crash the bubble).
  let text: string
  try { text = JSON.stringify(value, null, 2) ?? String(value) } catch { text = String(value) }
  return (
    <div>
      <span className="text-[9px] uppercase tracking-wide opacity-60">{label}</span>
      <pre className={`text-[10px] font-mono whitespace-pre-wrap break-all max-h-40 overflow-auto rounded p-1.5 mt-0.5 ${
        lightMode ? 'bg-zinc-100 text-zinc-700' : 'bg-zinc-900/70 text-zinc-300'
      }`}>{text}</pre>
    </div>
  )
}
```

Main component changes:
- `const [expanded, setExpanded] = useState<Set<number>>(new Set())` keyed by `s.seq`.
- `const expandable = s.args != null || s.result != null` per row.
- Expandable rows: wrap the existing row content in `<button type="button" onClick={toggle(s.seq)} className="w-full text-left …">`, append `ChevronRight`/`ChevronDown` size 10 after the label. Non-expandable rows keep the current `<div>` — **byte-identical rendering for all pre-existing persisted messages** (they have no args/result).
- Expanded body under the row, inside the same bordered box: `{s.args != null && <PayloadBlock label="args" …/>}{s.result != null && <PayloadBlock label="result" …/>}`.

Edge cases:
- Truncated payloads arrive as `{_truncated: true, preview: "…"}` — render as-is (the preview string is the content); no special casing needed, but a code comment should note the shape.
- `args: {}` (finish steps record empty args) — `{} != null` → expandable showing `{}`; acceptable and truthful.
- Live streaming bubble: `pendingHuumeSteps` accumulates → component re-renders with more rows; `expanded` (keyed by seq) survives appends. On turn completion the pending array clears and the persisted copy renders in `MessageBubble` — expansion state intentionally resets (different component instance).
- `key={s.seq}` uniqueness: seq is per-run monotonic (`_StepRecorder`); unchanged.

---

## Phase 6 — Plan card polish (all in `HuumePlanCard.tsx`)

### `PlanSection` — signature gains `streaming?: boolean; onExecuted?: () => void`

```ts
function PlanSection({ offerId, plan, threadId, lightMode, onStateUpdate, streaming, onExecuted }: {
  offerId: string; plan: HuumePlan; threadId: string; lightMode?: boolean
  onStateUpdate: (offerId: string, plan: HuumePlan) => void
  streaming?: boolean; onExecuted?: () => void
})
```

- **Progress header**: `const doneCount = plan.steps.filter(s => s.status === 'done').length` → under the Status line: `{doneCount}/{plan.steps.length}` + a 1px track: `<div className="h-px bg-zinc-700/50 …"><div className="h-px bg-emerald-500" style={{ width: \`${plan.steps.length ? (doneCount / plan.steps.length) * 100 : 0}%\` }} /></div>`. Edge case: `plan.steps.length === 0` → 0% (guard the division).
- **Candidate subtitle**: append `plan.employee.position_title` after the name line when present.
- **Buttons**: add `|| streaming` to all three `disabled` expressions (l.150, 158, 167). Comment: `// Also disabled mid-turn: the model can mutate this plan via its own execute_approved_steps tool while streaming; the advisory lock makes a race safe server-side, but the UI shouldn't invite it — and it guarantees onExecuted's full message refetch can't clobber an in-flight optimistic message.`
- **`handleExecute`** success path (after `setLastSummary(summary)`): `onExecuted?.()`.
- **`StepRow`** — replace the bare "Done" caption (l.52-54):
  ```tsx
  {step.status === 'done' && step.record_id && (
    step.key === 'create_employee' ? (
      <Link to={`/app/employees/${step.record_id}`} className="text-[10px] text-emerald-500 hover:text-emerald-400">
        View employee record →
      </Link>
    ) : (
      <div className={`text-[10px] ${muted}`}>Done</div>
    )
  )}
  ```
  Only `create_employee` gets a link — other `record_id`s (portal invite, training records…) have no canonical detail page; keep "Done". `Link` needs `import { Link } from 'react-router-dom'`.

Edge cases:
- Multi-candidate: sections already stack with per-section state; the progress header now visually separates them. Nothing else needed.
- `plan.status === 'executing'` while user has panel open: buttons disabled by existing conditions (`proposedSteps.length === 0` / `!hasApproved` may still allow — the `busy` guard only covers local ops). Acceptable: server refuses invalid transitions; error string shows verbatim.

---

## Phase 7 — huume_event notices + live state refresh

### `client/src/work/components/panels/MessageBubble.tsx`

Above `{markdownContent}` in the assistant branch (~l.110), purely additive:

```tsx
{m.metadata?.huume_event && HUUME_EVENT_STRIP[m.metadata.huume_event] && (() => {
  const ev = HUUME_EVENT_STRIP[m.metadata.huume_event]!
  const Icon = ev.icon
  return (
    <div className={`not-prose mb-2 flex items-center gap-1.5 text-[11px] font-medium px-2 py-1 rounded border w-fit ${lm ? ev.light : ev.dark}`}>
      <Icon size={12} /> {ev.label}
    </div>
  )
})()}
```

Module-level map (outside the component; keeps `React.memo` semantics — metadata is immutable per message):

```ts
const HUUME_EVENT_STRIP: Record<string, { icon: typeof FileText; label: string; light: string; dark: string }> = {
  offer_accepted: { icon: FileSignature, label: 'Offer accepted',  light: 'bg-emerald-50 text-emerald-700 border-emerald-300', dark: 'bg-emerald-950/40 text-emerald-300 border-emerald-800' },
  offer_declined: { icon: FileSignature, label: 'Offer declined',  light: 'bg-amber-50 text-amber-700 border-amber-300',       dark: 'bg-amber-950/40 text-amber-300 border-amber-800' },
  plan_executed:  { icon: PlayCircle,    label: 'Onboarding steps executed', light: 'bg-zinc-100 text-zinc-600 border-zinc-300', dark: 'bg-zinc-800/40 text-zinc-400 border-zinc-700' },
}
```

Edge cases: unknown `huume_event` value → map miss → no strip (forward-compatible). `not-prose` needed — bubble is inside Tailwind `prose`. Project-thread palette: use `lm` (already `isProjectThread ? false : lightMode` in scope) → dark variants apply; acceptable.

### `client/src/work/pages/MatchaWorkThread/useThreadCollaboration.ts`

```ts
export function useThreadCollaboration(
  threadId: string | undefined,
  setMessages: React.Dispatch<React.SetStateAction<MWMessage[]>>,
  /** Fired when a pushed message carries metadata.huume_event (offer
   * accepted/declined, plan executed) — the push only appends the message;
   * current_state (offer chip, plan statuses) needs a refetch to follow. */
  onHuumeEvent?: () => void,
) {
  ...
  // Ref, not a dep: the connect effect runs on [threadId] only; capturing the
  // callback directly would freeze its first render's closure.
  const onHuumeEventRef = useRef(onHuumeEvent)
  onHuumeEventRef.current = onHuumeEvent

  sock.onNewMessage = (newMessages) => {
    setMessages(/* existing dedup merge, unchanged */)
    if (newMessages.some(m => m.metadata?.huume_event)) onHuumeEventRef.current?.()
  }
```

### `client/src/work/pages/MatchaWorkThread/useThreadController.ts`

```ts
/** Refetch current_state/version only — merge, don't replace: keeps local
 * title edits and never touches `messages` (the WS frame already appended
 * the new message; replacing messages here could drop an optimistic temp). */
const refreshThreadState = useCallback(() => {
  if (!threadId) return
  getThread(threadId)
    .then(t => setThread(prev => prev ? { ...prev, current_state: t.current_state, version: t.version } : t))
    .catch(() => {})
}, [threadId])

const { onlineUsers, typingUsers, threadSocketRef, lastTypingSentRef } =
  useThreadCollaboration(threadId, setMessages, refreshThreadState)
```

Hoisting note: `useThreadCollaboration` is currently called at l.51, before any function declarations — `refreshThreadState` (a `useCallback`) must be defined **above** l.51. Move the `refreshUsage`-style block up or relocate the collaboration call — either is fine; do not convert existing function declarations to consts.

Export `refreshThreadState` from the controller return object (future callers; harmless).

Edge cases / race notes (put as a code comment at `refreshThreadState`):
- Refetch racing an in-flight turn's `onComplete`: both write backend truth to `current_state`; last-writer-wins is acceptable (post-turn `complete` re-reads state server-side and is the fresher of the two in the common ordering).
- Candidate declines: same path (`huume_event: offer_declined`) → chip flips to Declined live.

---

## Phase 8 — Huume empty-state skills

### `client/src/work/pages/MatchaWorkThread/constants.ts`

```ts
import { …existing…, Bot, CalendarClock, ShieldAlert } from 'lucide-react'

// Shown in the empty-state grid when the thread has huume_mode on. Same
// field shape as HR_SKILLS (SkillGrid unions the lists). Prompts map to
// Huume's registry tools; "Open a legal matter" is deliberately omitted —
// it hard-requires legal_defense, while these degrade to a polite refusal.
export const HUUME_SKILLS = [
  { id: 'huume_offer',      icon: FileCheck,     label: 'Draft an offer',   desc: 'Offer letter → signature link', prompt: 'Draft an offer letter for ', requiresCompany: true },
  { id: 'huume_status',     icon: MessageSquare, label: 'Offer status',     desc: 'Where are my offers?', prompt: 'What is the status of the offers in this thread?', requiresCompany: true },
  { id: 'huume_plan',       icon: Users,         label: 'Onboarding plan',  desc: 'Stage the full new-hire plan', prompt: 'Build the onboarding plan for the accepted offer', requiresCompany: true },
  { id: 'huume_whos_out',   icon: CalendarClock, label: "Who's out",        desc: 'PTO & leave this week', prompt: "Who's out on PTO or leave this week?", requiresCompany: true },
  { id: 'huume_writeup',    icon: ShieldAlert,   label: 'Write-up',         desc: 'Stage a discipline draft', prompt: 'Draft a discipline write-up for ', requiresCompany: true },
  { id: 'huume_handbook',   icon: BookOpen,      label: 'Handbook draft',   desc: 'Draft a policy via Handbook Pilot', prompt: 'Draft a handbook policy about ', requiresCompany: true },
] as const
```

### `client/src/work/pages/MatchaWorkThread/SkillGrid.tsx`

```ts
interface SkillGridProps {
  isIndividual: boolean
  isProject: boolean
  lightMode: boolean
  th: ThreadTheme
  huumeMode: boolean          // NEW
  setInput: (v: string) => void
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  setShowTutorSetup: (v: boolean) => void
  setTutorDismissed: (v: boolean) => void
}
```

List selection (l.24): `(huumeMode && !isIndividual ? HUUME_SKILLS : isIndividual ? PERSONAL_SKILLS : HR_SKILLS)`. The `.filter((s) => !s.requiresCompany || !isIndividual)` and the `'dropHint' in skill` / `skill.id === 'language_tutor'` branches must typecheck over the widened union — HUUME_SKILLS entries have no `dropHint` and none is `language_tutor`, so behavior is unchanged; confirmed clean with tsc.

### `client/src/work/pages/MatchaWorkThread/ChatMessages.tsx`

Add `thread` to the destructure from `c` (l.17-20); pass `huumeMode={!!thread?.huume_mode}` at the `<SkillGrid>` call (l.36-ish).

Edge cases: huume + individual user → impossible in practice (mode pills hidden for individuals, `huume` feature is company-scoped), and the ternary falls back to PERSONAL_SKILLS anyway. Empty-state only renders when `messages.length === 0` — unchanged.

---

## Phase 9 — Toasts

### `client/src/work/pages/MatchaWorkThread/useThreadController.ts`

```ts
import { useToast } from '../../../components/ui'
…
const { toast } = useToast()
…
} catch (e) {
  // A silently-failed toggle leaves the user believing the mode is on
  // while the backend answers without it.   ← keep existing comment
  console.error(`Failed to toggle ${mode} mode`, e)
  toast(`Couldn't toggle ${mode} mode`, 'error')          // NEW
}
```

### `HuumePlanCard.tsx` `PlanSection`

- `handleApprove` success: `toast(\`${count} step${count !== 1 ? 's' : ''} approved\`, 'success')` — count computed before the await (state may refresh under it).
- `handleExecute` success: `toast('Onboarding steps executed', 'success')`.
- Errors: unchanged — inline `<p className="text-[11px] text-red-500">` persists next to the buttons (toasts vanish; plan 400 prose needs to stay readable).

---

## Ordering & commit strategy

0 → 1 → 2 → {3+4 together} → 5 / 6 / 7 / 8 / 9 (5, 8, 9 fully independent; 6 needs 4's props; 7 needs 1's metadata types). Each phase leaves the app shippable.

## Test matrix

### Backend (pytest, pure, no DB)
- `server/tests/matcha_work/test_thread_response_mode_fields.py` — 3 tests (Phase 0, above). **Passing.**
- Regression: `cd server && ./venv/bin/python -m pytest tests/huume tests/matcha_work -q` — **433 passed, 6 pre-existing failures** (`test_blog_pdf_export.py`, documented in `routes/matcha_work/CLAUDE.md`, unrelated to this work).

### Client (vitest, co-located)
- `client/src/work/utils/huumeState.test.ts` — 9 cases (Phase 1, above). **Passing.**
- Run: `cd client && npx vitest run src/work/utils/huumeState.test.ts` (or full `npm run test:run`).

### Typecheck
- `cd client && npx tsc -p tsconfig.app.json --noEmit` — **clean.** (the `-p` form; bare `tsc --noEmit` checks nothing).

### Manual smoke (dev stack `./scripts/dev-remote.sh`; reserved email domains only — `@example.com` / `*.test`) — not yet run, do before merge
a. Toggle Huume on → **reload** → pill stays ON; thread list shows orange Huume badge. (Proves Phase 0; failed on main before this branch.)
b. Fresh huume thread, no messages → Huume skill grid renders (not HR_SKILLS); right panel shows HuumePlanCard empty state.
c. Huume thread with `task_type='offer_letter'` (PDF present) + nothing staged → PDF iframe still renders (gate clause). Toggle agentMode on in a bare huume thread → AgentPanel renders.
d. Ask Huume to send an offer → orange staged card in panel + banner above composer → click **Confirm** → turn runs, offer sends, chip flips to "Sent — awaiting response", card clears. Click-path check: **Cancel** on a fresh stage → agent voids it, card clears.
e. Build plan → approve-selected via checkboxes → toast; execute → toast + `n/m` progress fills + summary assistant message (with "Onboarding steps executed" strip) appears **without reload**; `create_employee` row shows "View employee record →" resolving to `/app/employees/{id}`.
f. Second browser: accept the offer at `/offer/:token` typing a name → first browser: emerald "Offer accepted" strip arrives live AND OfferChip flips to Accepted without reload (Phase 7 refetch). Repeat with decline → amber strip, chip → Declined.
g. Expand a step row in the live streaming bubble and in a persisted message → args/result JSON blocks, `max-h-40` scroll; a pre-harness thread's steps render exactly as before (no chevrons).
h. Kill the network mid mode-toggle → error toast appears.
i. Theme sweep: light mode, dark mode, project-thread (dark editor palette) — action card, event strips, timeline payload blocks readable in all three.

## Risks

- **Gate interplay** (highest): the `(!pdfUrl && !agentMode)` clause is load-bearing — smoke c covers it.
- `onExecuted` replaces `messages` wholesale — only safe with Phase 6's `streaming` disable; landed together.
- WS refetch vs in-flight `onComplete`: both backend truth, last-writer-wins; comment in code, no lock needed.
- Never parse plan 400 detail strings (candidate lists are prose-interpolated).
- `useThreadCollaboration` call-order: `refreshThreadState` declared before the hook call — plain reordering, no behavioral change.
