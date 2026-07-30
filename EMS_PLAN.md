# EMS — Event Management System (@huume in channels)

## Context

Companies need one place to log "events" — anything requiring documentation. Frontline users type `@huume <what happened>` in a werk channel; AI classifies + structures it into an event record; HR admins review all events in an Events tab in the /work surface and can **promote** an event into a real IR incident via existing IR infrastructure.

Decisions (user-confirmed):
- **Auto-log immediately**; Huume posts persisted confirmation back into channel.
- **Promotion HR-admin-confirmed only** — AI never auto-creates incidents (repo invariant, same as `ir_voice_intake`).
- **Events tab in /work surface** (+ werk-lite).
- **Six categories** (user-specified): behavioral, safety, operational, equipment, property, guest_experience.

Architecture verdicts (verified by exploration):
- **No Huume agent loop reuse** — `run_huume_turn` (`services/huume/agent.py:347`) + `huume_runs` hard-require `mw_threads`. Mirror one-shot draft→promote of `services/matcha_work/ticket_draft_service.py` instead.
- **IR reuse**: `IRAnalyzer.categorize_incident` / `assess_severity` (`services/ir/ir_analysis.py:759/:843`, narrative-only) for suggestions; `create_incident_core` (`services/ir/ir_incident_create.py:21`) for promotion.
- **Boundary**: trigger + system-message insert/broadcast live werk-side (`channels_ws.py`), lazy in-function import of matcha EMS service (allowed werk→matcha.services edge). Matcha never imports werk WS manager anew.
- `channel_messages.sender_id` NOT NULL, no system-message concept → migration required.
- Chain bonus: promoted `behavioral` event lands as IR incident (IR scope covers behavioral) → existing `discipline_from_incident` Huume skill / `discipline_policy_sweep` apply downstream. Zero new discipline code.

---

## Step 1 — Feature flag

**`server/app/core/feature_flags.py`**: add `"ems": False` to `DEFAULT_COMPANY_FEATURES`. NOT in `FEATURE_REQUIRES` (route gates make it inert without `matcha_work`; see ir_copilot row for FEATURE_REQUIRES pitfalls). NOT bundled, admin-toggle.

**Root `CLAUDE.md`**: flag-table row. Must note: no hard-stop classifier on event narratives (documentation content is exactly what the record exists to capture — `_HANDOFF_ACTIONS` reasoning); promotion additionally requires `incidents`.

## Step 2 — Migration `ems01`

**`server/alembic/versions/ems01_event_management.py`** (+ bootstrap mirror: edit `channel_messages` DDL in `server/app/database/bootstrap/misc_tail.py:70-105`, new tables in new `server/app/database/bootstrap/ems.py` wired into `bootstrap/__init__.py:init_db`):

```sql
ALTER TABLE channel_messages ALTER COLUMN sender_id DROP NOT NULL;
ALTER TABLE channel_messages ADD COLUMN message_type VARCHAR(20) NOT NULL DEFAULT 'user';

CREATE TABLE ems_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
  message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
  reporter_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  title VARCHAR(300),
  category VARCHAR(50) NOT NULL DEFAULT 'uncategorized',
  severity_hint VARCHAR(20),
  doc JSONB NOT NULL DEFAULT '{}',
  narrative TEXT NOT NULL,
  incident_recommendation BOOLEAN NOT NULL DEFAULT false,
  incident_reasoning TEXT,
  suggested_incident_type VARCHAR(50),
  suggested_severity VARCHAR(20),
  status VARCHAR(20) NOT NULL DEFAULT 'logged'
    CHECK (status IN ('logged','promoted','dismissed')),
  incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL,
  promoted_by UUID, promoted_at TIMESTAMPTZ,
  dismissed_by UUID, dismissed_at TIMESTAMPTZ,
  token_usage JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ems_events_company ON ems_events(company_id, created_at DESC);
-- replay idempotency belt (DB half; is_new_message gate is the app half)
CREATE UNIQUE INDEX uniq_ems_events_message ON ems_events(message_id) WHERE message_id IS NOT NULL;

CREATE TABLE ems_event_audit_log (          -- mirrors ir_audit_log shape
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID NOT NULL REFERENCES ems_events(id) ON DELETE CASCADE,
  user_id UUID, action VARCHAR(50) NOT NULL, details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Safety notes (write into migration docstring): partial unique index `(sender_id, client_message_id) WHERE client_message_id IS NOT NULL` unaffected — system messages insert both NULL, skip index entirely. `downgrade()`: drop tables/column; restoring `sender_id NOT NULL` must first `DELETE FROM channel_messages WHERE sender_id IS NULL`. Set-based, per `server/CLAUDE.md` migration rules. **Not applied without explicit user approval.**

## Step 3 — Werk-side guards + broadcast

**`server/app/werk/routes/channels_ws.py`**:
- Reply-preview JOIN at :837 → `LEFT JOIN users u`, `COALESCE(c.name, ..., u.email, 'Huume') AS sender_name`.
- Message-INSERT RETURNING (:793) + broadcast payload (:870): add `message_type`; `"sender_id": str(row["sender_id"]) if row["sender_id"] else None`.
- New module-level sibling of `broadcast_message_deleted` (:495):

```python
async def broadcast_system_message(channel_id: str, message: dict) -> None:
    """Fan out a system (Huume) message to a channel room. Callable from
    background tasks — no WebSocket/user context required."""
    await manager._broadcast_to_room(channel_id, {"type": "message", **message})
```

**`server/app/werk/routes/channels.py`**:
- Sender JOINs at :165 and :2557 → LEFT JOIN + COALESCE `'Huume'`.
- `message_type` in message-list SELECTs.
- Edit (:1375) / delete (:1311) / react (:1428): after fetching the message row —

```python
if msg_row["message_type"] == "system":
    raise HTTPException(status_code=403, detail="System messages cannot be modified")
```

## Step 4 — Intake trigger (`channels_ws.py`)

After mention parse (:864-868), next to the existing `_spawn_bg(_bg_sync_channel_attachments(...))` idiom (:826):

```python
# EMS: "@huume ..." logs an event. Gated on is_new_message — an ON CONFLICT
# cmid-retry replay must not double-log (unique(message_id) is the DB belt).
# resolve_mentions drops the unresolved "huume" handle, so no mention
# email/notification noise from the trigger itself.
if is_new_message and "huume" in mention_handles:
    _spawn_bg(_bg_ems_intake(str(ch_uuid), str(row["id"]), str(user.id), row["content"]))
```

```python
async def _bg_ems_intake(channel_id: str, message_id: str,
                         reporter_user_id: str, content: str) -> None:
    """Fire-and-forget EMS event intake. Own connection, top-level except —
    must NEVER affect message-send latency or success."""
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """SELECT ch.company_id, comp.is_personal,
                          comp.enabled_features, comp.signup_source
                   FROM channels ch JOIN companies comp ON comp.id = ch.company_id
                   WHERE ch.id = $1""", UUID(channel_id))
            if not row or row["is_personal"]:
                return                      # personal /work companies excluded
            from app.core.feature_flags import merge_company_features
            merged = merge_company_features(row["enabled_features"], row["signup_source"])
            if not merged.get("ems"):
                return
            try:
                await check_rate_limit(str(row["company_id"]), "ems_event", 30, 3600)
            except HTTPException:
                return                      # over limit: skip silently, message already sent
            # werk → matcha.services: lazy in-function import (boundary rule)
            from app.matcha.services.ems.event_intake import create_event_from_message
            event_row, confirmation = await create_event_from_message(
                conn, company_id=row["company_id"], channel_id=UUID(channel_id),
                message_id=UUID(message_id), reporter_user_id=UUID(reporter_user_id),
                content=content)
            if event_row is None:           # dedupe hit
                return
            sys_row = await conn.fetchrow(
                """INSERT INTO channel_messages (channel_id, sender_id, content, message_type)
                   VALUES ($1, NULL, $2, 'system')
                   RETURNING id, channel_id, content, message_type, created_at""",
                UUID(channel_id), confirmation)
        await broadcast_system_message(channel_id, {
            "id": str(sys_row["id"]), "channel_id": channel_id, "sender_id": None,
            "sender_name": "Huume", "content": sys_row["content"],
            "message_type": "system", "attachments": [],
            "created_at": sys_row["created_at"].isoformat()})
    except Exception:
        logger.exception("EMS intake failed for message %s", message_id)
```

## Step 5 — Matcha service `server/app/matcha/services/ems/`

**`categories.py`** — pure, DB-free:

```python
@dataclass(frozen=True)
class EmsCategory:
    key: str
    label: str
    doc_sections: tuple[str, ...]   # section keys the extractor fills in doc JSONB
    example: str                    # few-shot line for the classify prompt

CATEGORIES: dict[str, EmsCategory] = {  # user-specified six
    "behavioral":       (..., ("who", "what_happened", "prior_context"),
                         "I asked Jenna to bin the frozen hot dogs. It took her 1 hour and when I asked why it took so long she rolled her eyes at me."),
    "safety":           (..., ("who", "where", "injury", "witnesses"),
                         "Julia slipped in the back of house."),
    "operational":      (..., ("process", "change", "impact"),
                         "We implemented the new coconut oil for popping and we are getting less volume from this system."),
    "equipment":        (..., ("asset", "issue", "since_when", "impact"),
                         "The ice machine is empty, it hasn't made new ice since yesterday."),
    "property":         (..., ("location", "condition", "risk"),
                         "I noticed what appears to be black mold in the corner of the back stock room."),
    "guest_experience": (..., ("situation", "resolution_offered", "outcome"),
                         "A guest brought back his pizza saying it did not taste good... threw the pizza on the ground."),
}
FALLBACK_KEY = "uncategorized"

def normalize_category(raw: str | None) -> str:
    """Unknown/missing model output → FALLBACK_KEY, never a raw model string."""

def prompt_block() -> str:
    """Render the six categories + examples as the classify prompt's few-shot block."""
```

`incident_recommendation` stays AI-judged per event, NOT hardcoded per category (mold `property` or thrown-pizza `guest_experience` can warrant an incident; empty ice machine can't). All sections extracted include free-text `people_mentioned` — no roster FK resolution in v1.

**`event_intake.py`** — mirror `ticket_draft_service.py` self-contained client (`:33`, `FLASH_LITE_MODEL = "gemini-3.1-flash-lite"` `:28`):

```python
_CONTEXT_MESSAGES = 15

async def create_event_from_message(
    conn, *, company_id: UUID, channel_id: UUID, message_id: UUID,
    reporter_user_id: UUID, content: str,
) -> tuple[dict | None, str]:
    """One-shot classify+extract → INSERT ems_events + audit row.
    Returns (event_row | None-on-dedupe, confirmation_text).
    Gemini failure still inserts: category='uncategorized', doc={},
    narrative=raw content — documentation must survive AI outage."""

async def _fetch_channel_context(conn, channel_id: UUID, before: UUID) -> list[dict]:
    # last _CONTEXT_MESSAGES non-deleted messages before the trigger, oldest-first

def _build_classify_prompt(content: str, context: list[dict]) -> str:
    # JSON-mode; embeds categories.prompt_block(); asks for
    # {title, category, severity_hint, doc, incident_recommendation, incident_reasoning}

def _parse_model_json(raw: str) -> dict:
    # strict key whitelist, normalize_category(), clamp title to 300 chars

async def _ir_suggestions(title: str, narrative: str) -> dict:
    """Best-effort, never raises. get_ir_analyzer().categorize_incident(title, narrative)
    then assess_severity(title, narrative, suggested_type) — pattern:
    routes/ir_incidents/_shared.py:505. Returns {} on any failure."""

def _confirmation_text(event_row: dict) -> str:
    # e.g. "📋 Logged Behavioral event EV-1234 — visible to HR admins in Events."
```

INSERT uses `ON CONFLICT (message_id) WHERE message_id IS NOT NULL DO NOTHING` + audit row `action='created'`.

**`promote.py`** — verdict envelope mirrors `services/huume/actions.py:141` (pure evaluate + async execute):

```python
@dataclass(frozen=True)
class PromoteVerdict:
    kind: Literal["proceed", "refuse"]
    reason: str | None = None
    http_status: int = 403           # 409 for wrong-status refusals

def evaluate_promote(*, role: str, features: dict, event_status: str) -> PromoteVerdict:
    # order: role ∉ {client, admin} → 403; not features.get("ems") → 403;
    # not features.get("incidents") → 403; event_status != 'logged' → 409

async def promote_event(
    conn, *, company_id: UUID, event: dict, overrides: "PromoteRequest",
    actor_user_id: UUID, actor_email: str | None,
) -> tuple[dict, list]:
    """One transaction: create_incident_core(...) → UPDATE ems_events SET
    status='promoted', incident_id, promoted_by/at → audit rows on BOTH
    ems_event_audit_log and (via core) ir side.
    Returns (incident_row, bg_tasks) — caller runs bg_tasks post-commit."""
    # create_incident_core(conn, company_id, description=_render_description(event),
    #   occurred_at=overrides.occurred_at or event["created_at"],
    #   reported_by_name=<reporter display name>,
    #   title=overrides.title or event["title"],
    #   incident_type=overrides.incident_type or event["suggested_incident_type"],
    #   severity=overrides.severity or event["suggested_severity"],
    #   witnesses=overrides.witnesses,      # admin-kept names from doc
    #   created_by=actor_user_id, actor_user_id=..., actor_email=...,
    #   index_people=True)   # attributed intake (reporter known, admin-reviewed)
    #                        # — mirrors /intake/:token, NOT the anonymous path

def _render_description(event: dict) -> str:
    # narrative + doc sections rendered as labeled lines; provenance footer
    # "Logged via @huume in channel <name> by <reporter> on <date>"
```

## Step 6 — Models + router

**`server/app/matcha/models/ems.py`**:

```python
class EmsEventOut(BaseModel):
    id, channel_id, channel_name, title, category, severity_hint, doc, narrative,
    incident_recommendation, incident_reasoning, suggested_incident_type,
    suggested_severity, status, incident_id, reporter_name, created_at, updated_at

class EmsEventUpdate(BaseModel):          # true PATCH via model_fields_set (repo idiom)
    title: str | None = None
    category: str | None = None           # validated against categories registry
    doc: dict | None = None
    dismissed: bool | None = None         # True → status='dismissed' + dismissed_by/at

class PromoteRequest(BaseModel):
    title: str | None = None
    incident_type: str | None = None
    severity: str | None = None
    occurred_at: datetime | None = None
    location: str | None = None
    witnesses: list[str] | None = None
```

**`server/app/matcha/routes/ems.py`** — `router = APIRouter(prefix="/ems", tags=["ems"])`:

```python
@router.get("/events")            # -> {"events": [EmsEventOut], "total": int}
async def list_events(status: str | None = None, category: str | None = None,
                      channel_id: UUID | None = None, limit: int = 50, offset: int = 0,
                      current_user=Depends(require_admin_or_client)): ...
@router.get("/events/{event_id}")     # 404 outside caller's company
@router.put("/events/{event_id}")     # EmsEventUpdate; PUT (api client has no .patch)
@router.post("/events/{event_id}/promote")   # evaluate_promote → promote_event; bg_tasks post-commit
```

Every query `WHERE company_id = $1` with company derived from `current_user` (never client-supplied). Mount in `server/app/matcha/routes/__init__.py`:

```python
api_router.include_router(ems.router, dependencies=[Depends(require_feature("ems"))])
```

## Step 7 — Frontend (`client/src/work/`)

**`api/events.ts`** (mirror `api/inbox.ts`; `import { api } from '../../api/client'`):

```ts
export interface EmsEvent { id: string; channel_id: string | null; channel_name?: string;
  title: string | null; category: string; severity_hint: string | null;
  doc: Record<string, unknown>; narrative: string;
  incident_recommendation: boolean; incident_reasoning: string | null;
  suggested_incident_type: string | null; suggested_severity: string | null;
  status: 'logged' | 'promoted' | 'dismissed'; incident_id: string | null;
  reporter_name: string | null; created_at: string; }

export const listEvents = (f: {status?: string; category?: string; channel_id?: string}) =>
  api.get<{events: EmsEvent[]; total: number}>(`/ems/events?${qs(f)}`);
export const getEvent = (id: string) => api.get<EmsEvent>(`/ems/events/${id}`);
export const updateEvent = (id: string, body: Partial<...>) => api.put(...);
export const promoteEvent = (id: string, overrides: PromoteOverrides) =>
  api.post<{incident_id: string}>(`/ems/events/${id}/promote`, overrides);
```

**`utils/eventsPermissions.ts`** (mirror `utils/channelPermissions.ts:29`):

```ts
export const canReviewEvents = (role?: string) => role === 'client' || role === 'admin';
```

**Pages/components**:
- `pages/EventsHub.tsx` — Inbox-style split pane (`pages/Inbox.tsx` precedent): left list (status/category filter chips à la `ChannelBrowse.tsx:50-67`), right detail.
- `components/events/EventList.tsx`, `EventDetail.tsx` (doc sections + recommendation banner + reasoning), `PromoteModal.tsx` (prefilled from `suggested_*` + `created_at`; type/severity options reused from `types/ir.ts` maps; hidden when `!hasFeature('incidents')` — banner stays).

**Wiring** (each is a small named edit):
- `routes/WorkRouteTree.tsx:29-48`: `<Route path="events" element={<EventsHub/>}/>` (covers /work + /werk).
- `routes/WerkLiteRoutes.tsx:50-75`: same route inside the werk_lite gate.
- Links via `useWorkBase()` from `routes/WorkSurfaceContext.ts` — never hardcode `/work`.
- Sidebar: key+default in `components/shell/WorkSidebar/useSectionState.ts:3/:7`; section render in `WorkSidebar.tsx:228-269` gated `canReviewEvents(role) && hasFeature('ems')`; icon in `CollapsedRail.tsx:48-112`; logged-count fetch in `useSidebarData.ts`; entry in `WerkLiteSidebar.tsx`.
- ChannelView: `message_type === 'system'` → centered Huume-styled row, no edit/delete/reply affordances (message renderer under `pages/ChannelView/`); WS payload type in `api/channelSocket.ts` gains `message_type?: string`, nullable `sender_id`.

## Step 8 — Tests

**`server/tests/ems/test_categories.py`** (pure):
- `test_category_keys_unique_and_sections_nonempty`
- `test_normalize_category_unknown_returns_fallback` (`"weather"` → `"uncategorized"`; `None` → fallback)
- `test_prompt_block_contains_all_six_examples`

**`server/tests/ems/test_promote_envelope.py`** (pure, DB-free):
- `test_refuses_employee_role` → refuse/403
- `test_refuses_without_ems_flag`, `test_refuses_without_incidents_flag` → refuse/403
- `test_refuses_promoted_and_dismissed_status` → refuse/409
- `test_proceeds_for_client_with_both_flags`

**`server/tests/ems/test_event_intake_parsing.py`** — patch genai client **on `event_intake` module itself** (patch-the-defining-module rule, `server/CLAUDE.md`):
- `test_parse_model_json_valid_payload`
- `test_unknown_category_normalized_to_fallback`
- `test_gemini_failure_inserts_fallback_shape` (category `uncategorized`, `narrative == raw content`)
- `test_confirmation_text_names_category`

**Werk-side**: extract trigger predicate if a pure seam is cheap; otherwise cover via manual verification below (route tests are DB-bound).

**Client**: `cd client && npx tsc -p tsconfig.app.json --noEmit` (the bare `npx tsc --noEmit` checks nothing).

Post-edit hook runs `py_compile` per file automatically.

## Key edge cases
- WS send latency unchanged: EMS work is post-broadcast, fire-and-forget, own connection.
- `ems` without `incidents`: intake + tab work; promote 403 / hidden.
- Personal (`is_personal`) companies excluded at trigger.
- Rate limit (30/hr/company) hit → skip silently; user message unaffected.
- System confirmation lags user message by seconds — reply-shaped, fine.
- Trigger needs word-boundary `@huume` (mentions regex `_MENTION_RE`, `services/matcha_work/mentions.py:25`).

## Verification (dev, manual)
1. Enable `matcha_work`+`ems` on non-personal dev company; leave `incidents` off.
2. As employee send "@huume Julia slipped in the back of house" → message instant; system confirmation ~5s; persists on refresh; second client sees both.
3. WS-replay same `client_message_id` → still one `ems_events` row.
4. As admin `/work/events` → event shows category `safety`, doc sections, recommendation banner; promote hidden. Enable `incidents` → promote with overrides → `ir_incidents` row exists, event `promoted`, audit rows both tables; re-promote → 409.
5. Employee opens `/work/events` → gated. Personal company `@huume` → nothing. Kill Gemini key → event logs as `uncategorized`. 31st mention/hr → skipped.
6. Edit/delete on system message → 403; reply-preview to it shows "Huume".
7. `cd server && python3 -m pytest tests/ems/ -q`; client tsc as above.
8. Migration: rehearse via `migrate-dev.sh` flow — **applied only with explicit user approval**.
