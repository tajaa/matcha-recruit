# EMS conversational clarification — @huume asks follow-up questions

Follow-up to `EMS_PLAN.md`. Documents the implemented design — function names, file paths,
and control flow below match the code as built, not just the original design pass.

## Context

EMS intake (`EMS_PLAN.md`, branch `matcha/event-management-system`) is one-shot:
`@huume <narrative>` → classify → log → confirm. A vague report ("something happened with
Jenna") can't be properly categorized from one message. Goal: when the classifier needs more
info, Huume's in-channel confirmation doubles as a **follow-up question**; the reporter (or any
channel member) answers by **replying to that system message**, and the answer refines the
event in place.

User-confirmed decisions:
- **Log first, then ask** — event row written immediately (documentation-survives invariant);
  unanswered question leaves a logged-but-thin event the admin can still edit.
- **Full reply UI** — the werk client had NO reply support before this: reply threading was
  backend-complete (DB column, WS parse, `reply_preview` on every broadcast/REST fetch) but the
  client never sent `reply_to_id` nor rendered previews. Built general reply support; the
  clarify answer is one use of it.
- Correlation: `reply_to_id` → the question's system-message id. Deterministic, no
  next-message-wins heuristics. Cap **2 rounds** per event. Any channel member may answer
  (audit-logged).

---

## Server

### S1. Schema — `ems01` amended in place (not a new migration)

`ems01` was committed but applied to **no** database — same precedent as huume's keyed-plan
reshape ("unreleased feature, no back-compat needed"), so amending it in place rather than
shipping `ems02` was safe. Both `server/alembic/versions/ems01_event_management.py` (inside the
`CREATE TABLE ems_events` block + a new index statement) and
`server/app/database/bootstrap/ems.py` (mirror) gained:

```sql
-- new columns in ems_events, after token_usage:
clarify_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
clarification_rounds SMALLINT NOT NULL DEFAULT 0,
```
```sql
-- new statement after uniq_ems_events_message:
-- clarify_message_id IS NOT NULL <=> a Huume follow-up question is outstanding.
-- UNIQUE partial index = the atomic-claim lookup key when a reply arrives
-- (_bg_ems_clarify's UPDATE ... WHERE clarify_message_id = $reply_uuid).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_ems_events_clarify
    ON ems_events(clarify_message_id) WHERE clarify_message_id IS NOT NULL;
```

Migration docstring updated to explain the clarify columns and the amend-in-place rationale.
`downgrade()` already drops the whole table — no change needed. **Still unapplied to any
database without explicit user approval.**

### S2. `server/app/matcha/services/ems/event_intake.py`

**S2a. Prompt** — `_build_classify_prompt`'s JSON contract gained two fields:

```
'"needs_clarification": bool (true ONLY if the category is genuinely ambiguous '
"or a critical detail for the chosen category is missing — e.g. a safety event "
"with no who/injury, a behavioral event with no who. Never ask about routine "
"operational/equipment notes), "
'"clarify_question": str|null (ONE short question that would resolve it, '
"asked directly to the reporter; null when needs_clarification is false)}"
```

**S2b. Parse** — `_parse_model_json` adds, after `incident_reasoning`:

```python
clarify_question = str(data.get("clarify_question") or "").strip()[:300] or None
needs_clarification = bool(data.get("needs_clarification")) and clarify_question is not None
```

Both keys land in the returned dict. Empty/missing question forces `needs_clarification=False`
— a model that says "true" but gives nothing to ask is not a real clarification request, and
would otherwise render a bare "❓ " in the confirmation.

**S2c. `_FALLBACK_CLASSIFICATION`** gained:

```python
"needs_clarification": False,   # never ask a question during a Gemini outage
"clarify_question": None,
"model_ok": False,
```

**S2d. `classify_event`** sets `model_ok = True` only on the successful-parse path:

```python
classified = {**_FALLBACK_CLASSIFICATION, **_parse_model_json(resp.text), "model_ok": True}
```

`persist_event` reads only its named keys, so it's unaffected by the new ones.

**S2e. New pure helpers** (module level, after `_confirmation_text`):

```python
_MAX_CLARIFY_ROUNDS = 2

def compose_refinement_content(narrative: str, question: str, answer: str) -> str:
    """Combined text re-fed through classify_event when a clarify answer
    arrives — reuses the full prompt/parse/IR-suggestion/fallback path
    rather than a bespoke merge-in-place."""
    return f"{narrative}\n\n[Huume asked]: {question}\n[Reply]: {answer}"

def should_ask_again(classified: dict, rounds: int) -> bool:
    """Ask another follow-up? rounds is the count BEFORE this answer
    (apply_refinement increments it), so rounds=0 means "no question asked
    yet" and rounds=_MAX_CLARIFY_ROUNDS-1 is the last round allowed to ask
    again."""
    return bool(classified.get("needs_clarification")) and rounds < _MAX_CLARIFY_ROUNDS

def question_text(confirmation: str, question: str) -> str:
    """Append a follow-up question to a Huume confirmation/update message.
    Public (not `_`-prefixed) — channels_ws.py calls it directly."""
    return f"{confirmation}\n❓ {question} — reply to this message to add details."
```

**S2f. New `apply_refinement`** (async, DB-only — sibling of `persist_event`):

```python
_REFINEMENT_RETURNING = """
    RETURNING id, company_id, channel_id, message_id, reporter_user_id,
              title, category, severity_hint, doc, narrative,
              incident_recommendation, incident_reasoning,
              suggested_incident_type, suggested_severity,
              status, clarification_rounds, created_at, updated_at
"""

async def apply_refinement(
    conn, *, event_id: UUID, company_id: UUID, answer: str,
    classified: dict, answered_by: UUID,
) -> Optional[dict]:
    """Fold a clarify answer into a still-logged event.

    Always appends the answer to `narrative` — documentation survives even
    when classification fails. The classification fields (title/category/
    severity_hint/doc/incident_*) are rewritten ONLY when
    classified["model_ok"] — a Gemini failure during refinement must not
    downgrade an already-classified event back to 'uncategorized'.

    Guarded WHERE status = 'logged': a promoted/dismissed event is never
    rewritten. Returns the updated row (post-increment clarification_rounds)
    or None on that guard miss — the caller treats None as "ignore, the
    event moved on since the question was asked."
    """
```

Two static SQL variants (`model_ok=True` sets the classification columns; `model_ok=False`
touches only `narrative`/`clarification_rounds`/`updated_at`) — never dynamic assembly, for the
same reason `routes/ems.py`'s `update_event` moved off value-sniffing. Appended text:
`"\n\nFollow-up: " + answer[:_MAX_NARRATIVE_CHARS]`. Then an audit INSERT
(`action='clarified'`, `details={"category": ..., "model_ok": ...}`).

### S3. `server/app/werk/routes/channels_ws.py`

**Shared helpers** (new, used by both intake and clarify):

```python
def _system_message_payload(channel_id_str: str, sys_row) -> dict:
    """The 17-key WS broadcast shape for an EMS/Huume system message —
    factored out so _bg_ems_intake and _bg_ems_clarify don't each carry a
    copy."""

async def _insert_system_message(conn, channel_id_str: str, content: str):
    """INSERT one message_type='system' channel_messages row."""

async def _ems_company_gate(conn, channel_id_str: str):
    """Company/is_personal/`ems`-flag lookup keyed on a channel — what
    _bg_ems_intake has to work with. Returns company_id or None."""

async def _ems_flag_enabled(conn, company_id) -> bool:
    """Same check keyed on a company_id already in hand — what
    _bg_ems_clarify has after its atomic claim, so it doesn't need a second
    channel join."""
```

**S3a. Intake asks** — `_bg_ems_intake`'s second connection block, after `persist_event`
returns a real row:

```python
ask = classified.get("needs_clarification") and classified.get("clarify_question")
message_text = question_text(confirmation, classified["clarify_question"]) if ask else confirmation
sys_row = await _insert_system_message(conn, channel_id_str, message_text)
if ask:
    # Arm the pending question: a reply to THIS system message is the
    # answer _bg_ems_clarify is waiting for.
    await conn.execute(
        "UPDATE ems_events SET clarify_message_id = $1 WHERE id = $2",
        sys_row["id"], event_row["id"],
    )
```

**S3b. Reply validation** (security fix, in scope — replies became user-reachable with this
change). The WS send path never validated `reply_to_id`: a crafted payload could quote any
message UUID in any tenant (the `rp` reply-preview query is unscoped, so its content would leak
into the broadcast), and a nonexistent UUID would hit the `reply_to_id` FK and raise past the
INSERT with no `except`, killing the WS receive loop. Fixed where `reply_uuid` is parsed, right
before the message INSERT:

```python
if reply_uuid:
    reply_target_ok = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM channel_messages WHERE id = $1 AND channel_id = $2)",
        reply_uuid, ch_uuid,
    )
    if not reply_target_ok:
        reply_uuid = None  # cross-channel or bogus target: drop silently
```

**S3c. Answer trigger** — sibling of the `@huume` trigger, fires off the DB-returned
`row["reply_to_id"]` (post-validation), not the raw parsed `reply_uuid`:

```python
if is_new_message and row["reply_to_id"]:
    _spawn_bg(_bg_ems_clarify(
        str(ch_uuid), str(row["reply_to_id"]), str(user.id), row["content"],
    ))
```

Independent of the `@huume` trigger — intake fires on mention, clarify fires on reply-to-
question. A message doing both is pathological; `uniq_ems_events_message` and the clarify claim
UPDATE keep both idempotent regardless.

**S3d. `_bg_ems_clarify`** — sibling of `_bg_ems_intake`, same two-connection discipline (never
holds a pooled connection across the refinement Gemini calls):

1. **Conn #1** — atomic claim (first reply to a question wins; an ordinary reply misses and
   returns immediately, before any company/flag/rate-limit work):
   ```sql
   UPDATE ems_events SET clarify_message_id = NULL
   WHERE clarify_message_id = $1 AND status = 'logged'
   RETURNING id, company_id, narrative, clarification_rounds
   ```
   Then `_ems_flag_enabled(conn, company_id)` (re-checks the flag wasn't disabled between
   question and answer) and `check_rate_limit(company_id, "ems_event", 30, 3600)` — refinement
   Gemini spend counts against the same 30/hr budget as intake.
   **Rate-limited path** (self-contained inside this same connection): fold the answer in
   deterministically via `apply_refinement(conn, ..., classified={"model_ok": False}, ...)`, post
   a "Updated … — thanks." confirmation, broadcast, return. No Gemini call, no new question —
   documentation still lands.
   Otherwise: fetch the question's own text (`SELECT content FROM channel_messages WHERE id =
   $reply_to`) and `gather_intake_context(conn, channel_id, reply_to)`; close the connection.
2. **No connection held**: `classified = await classify_event(compose_refinement_content(
   claimed["narrative"], question, content), context)`.
3. **Conn #2**: `updated = await apply_refinement(conn, ...)`; `None` (promote/dismiss race) is
   silently ignored. Otherwise:
   ```python
   ask_again = should_ask_again(classified, claimed["clarification_rounds"])
   text = (question_text("📋 Updated the event.", classified["clarify_question"]) if ask_again
           else f"📋 Updated **{categories.category_label(updated['category'])}** event — thanks.")
   sys_row = await _insert_system_message(conn, channel_id_str, text)
   if ask_again:
       await conn.execute(
           "UPDATE ems_events SET clarify_message_id = $1 WHERE id = $2",
           sys_row["id"], updated["id"],
       )
   ```
   `should_ask_again` reads `claimed["clarification_rounds"]` — the pre-increment count from the
   claim, matching its own "rounds is the count BEFORE this answer" contract — not the
   post-increment value on `updated`. Broadcast via the shared `_system_message_payload`.

### S4. `server/app/matcha/routes/ems.py` + `models/ems.py` — expose "awaiting reply"

- `_EVENT_SELECT` gains `ev.clarify_message_id IS NOT NULL AS awaiting_reply,
  ev.clarification_rounds`.
- `EmsEventOut` gains `awaiting_reply: bool = False`, `clarification_rounds: int = 0`. (The
  message id itself never leaves the server.)

## Client

### C1. `client/src/work/api/channels.ts` — types only

```ts
export interface ReplyPreview {
  id: string
  sender_name: string
  content: string
  attachments?: ChannelAttachment[]
}
// on ChannelMessage:
reply_to_id?: string | null
reply_preview?: ReplyPreview | null
```

Wire data already carried both on every REST fetch and WS broadcast before this change — only
the type was missing. Also `client/src/work/api/events.ts`: `awaiting_reply: boolean` and
`clarification_rounds: number` on `EmsEvent`.

### C2. `client/src/work/api/channelSocket.ts` — `sendMessage` gains `replyToId`

```ts
sendMessage(channelId: string, content: string, attachments?: ChannelAttachment[],
            clientMessageId?: string, replyToId?: string) {
  this.send({
    type: 'message', channel_id: channelId, content,
    ...(attachments?.length ? { attachments } : {}),
    ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
    ...(replyToId ? { reply_to_id: replyToId } : {}),
  })
}
```

### C3. `client/src/work/pages/ChannelView/useChannelView.ts`

- New state: `const [replyTo, setReplyTo] = useState<ChannelMessage | null>(null)`.
- `handleSend`'s optimistic row gains `reply_to_id` and a locally-built `reply_preview` (name
  falls back to `'Huume'` when `replyTo.message_type === 'system'`); `sendMessage(...,
  replyTo?.id)`; `setReplyTo(null)` alongside `setInput('')`.
- New `handleReply(msg)`: `setReplyTo(msg); inputTextareaRef.current?.focus()`.
- Hook return object gains `replyTo`, `setReplyTo`, `handleReply`.

### C4. `client/src/work/pages/ChannelView/ChannelViewScreen.tsx`

Destructures the three new hook values; passes `onReply={handleReply}` to `<MessageList>`, and
`replyTo={replyTo}` + `onClearReply={() => setReplyTo(null)}` to `<MessageComposer>`.

### C5. `client/src/work/pages/ChannelView/MessageList.tsx`

- New prop `onReply: (msg: ChannelMessage) => void`.
- **System pill**: this branch returns early with no `group` wrapper and no action rail — it
  gained its own always-visible (not hover-revealed) `Reply` button, hidden while
  `msg.pending`. This is how a Huume clarification question gets answered. `whitespace-pre-wrap`
  added to the pill text so a multi-line question (confirmation + `❓ …`) renders on its own
  line instead of collapsing.
- **Normal rows**: `Reply` button added beside the existing delete button, same
  `opacity-0 group-hover:opacity-100` idiom, visible to everyone (not gated on `canDelete`),
  hidden on deleted messages.
- **`ReplyPreviewStub`**: small quoted block rendered above message content when
  `msg.reply_preview` is set — attribution to `'Huume'` is free, since the server-side
  `_MSG_NAME_EXPR` COALESCE already falls back to it for `sender_id IS NULL`.

### C6. `client/src/work/pages/ChannelView/MessageComposer.tsx`

New props `replyTo: ChannelMessage | null`, `onClearReply: () => void`; a "Replying to
&lt;name&gt;: &lt;excerpt&gt;" chip with a clear button, rendered above the pending-files strip.

### C7. `client/src/work/components/events/EventDetail.tsx`

When `event.status === 'logged' && event.awaiting_reply`: a small hint banner —
"Huume asked a follow-up in the channel — awaiting reply."

## Tests — `server/tests/ems/test_event_intake_parsing.py` (extended)

| Test | Asserts |
|---|---|
| `TestParseModelJson::test_clarify_fields_roundtrip` | `needs_clarification: true, clarify_question: "Who was involved?"` survives parse |
| `TestParseModelJson::test_empty_question_forces_no_clarification` | `needs_clarification: true, clarify_question: ""` → parsed `needs_clarification is False`, question `None` |
| `TestParseModelJson::test_question_capped_at_300` | 500-char question → `len(...) == 300` |
| `TestClassifyEvent::test_gemini_failure_returns_fallback_shape` (extended) | outage → `needs_clarification is False`, `model_ok is False` |
| `TestClassifyEvent::test_success_sets_model_ok` | fake client returns valid JSON → `model_ok is True` |
| `TestRefinementHelpers::test_compose_refinement_content` | narrative, `[Huume asked]: Q`, `[Reply]: A` appear in order |
| `TestRefinementHelpers::test_should_ask_again_cap` (parametrized) | `(True,0)`→True, `(True,1)`→True, `(True,2)`→False, `(False,0)`→False |
| `TestRefinementHelpers::test_question_text_appends_prompt` | confirmation + question + "reply to this message" all present |
| `TestApplyRefinement::test_updates_classification_when_model_ok` | `_RefinementFakeConn` update branch: `category` set, narrative contains `Follow-up:` |
| `TestApplyRefinement::test_append_only_when_model_failed` | `model_ok=False` → issued SQL has no `category =`; narrative still appended |
| `TestApplyRefinement::test_none_when_event_not_logged` | UPDATE guard miss → `apply_refinement` returns `None`, no audit row |

New `_RefinementFakeConn` test double (distinct from the existing `_FakeConn`) fakes both
`apply_refinement` SQL variants, distinguished by shape (`"category = $5" in query`), and echoes
call args back into a RETURNING-shaped dict. Patches land on `event_intake` itself (the
defining-module rule) — no facade re-export involved.

Result: **46 passed** (33 pre-existing + 13 new) in `tests/ems/`.

## Verification

1. `cd server && python3 -m pytest tests/ems/ -q` — 46 passed.
2. `python3 -m py_compile` on every touched `.py` (the post-edit hook also runs this per file).
3. `cd client && npx tsc -p tsconfig.app.json --noEmit` — clean (never the bare
   `npx tsc --noEmit`, which checks nothing).
4. Manual (dev, `matcha_work`+`ems` on — not yet performed, needs a running dev instance):
   - `@huume something happened with Jenna` → event logs immediately AND the pill asks a
     follow-up question.
   - Reply via the new reply UI → `/work/events` shows updated category/doc, narrative has
     `Follow-up: …`, `awaiting_reply` clears; the live system "Updated" pill appears without a
     refresh.
   - A second vague answer → at most one more question (cap 2), then a final confirmation.
   - Ordinary reply to a normal (non-Huume) message → plain threaded reply with a quoted
     preview; no EMS side effects.
   - Reply to a question whose event was promoted/dismissed meanwhile → silently ignored.
   - Kill `GEMINI_API_KEY`, answer a pending question → narrative appended, category unchanged,
     no new question asked; fresh `@huume` intakes still log as `uncategorized` with no question.
   - Crafted WS payload naming a foreign-channel `reply_to_id` → message sends with no preview
     (target dropped server-side), WS loop survives.
5. Amended `ems01` stays unapplied to any database pending explicit user approval; rehearse via
   `migrate-dev.sh` once approved.
