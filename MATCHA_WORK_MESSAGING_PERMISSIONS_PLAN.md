# Matcha Work Messaging and Permissions — Technical Implementation Plan

## 1. Product terminology

Keep existing URLs, API routes, database names, and internal `mw_threads` terminology stable. Change user-facing language to:

| Current concept | User-facing name | Scope |
| --- | --- | --- |
| `/work/channels` | **Channels** | Team communication |
| `/work` and `/work/:threadId` | **Huume Workspaces** | Agent-assisted work |
| Conversation inside either surface | **Chat** | User-facing transcript |
| Internal `mw_threads` record | **Thread** | Internal/API term |
| EMS record | **Event** | Reviewed operational record |
| Huume executable work | **Task** or **Action** | Agentic execution |

The core behavior change is that an ordinary channel message creates an **event draft**, not a final event. Huume asks for confirmation first. OSHA/severe reports remain the explicit immediate-log exception.

## 2. Company-scoped permission model

Authorization must resolve against the company that owns the thread, event, or task—not only the caller's home company. This prevents an external collaborator with a global `client` role from inheriting the target company's execution privileges.

| Level | Capabilities |
| --- | --- |
| Guest | Communicate in explicitly shared resources |
| Member | Propose Huume actions; confirm/reject own event drafts |
| Reviewer | Member + review drafts; complete/no-action events; view sensitive event details |
| Operator | Reviewer + promote events; approve and execute Huume tasks |
| Admin | Operator + manage Work permissions |

Default resolution:

- Platform admin → Admin
- Explicit company grant → granted level
- Company owner → Admin
- Same-company `client` → Operator, preserving current behavior
- Same-company employee → Member
- External collaborator without a target-company grant → Guest

### Database

Add `mw_work_permissions` in:

- `server/app/database/bootstrap/matcha_work.py`
- A new Alembic revision under `server/alembic/versions/`

```sql
CREATE TABLE mw_work_permissions (
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level VARCHAR NOT NULL
        CHECK (level IN ('member', 'reviewer', 'operator', 'admin')),
    granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, user_id)
);
```

### Server contracts

New file: `server/app/matcha/services/matcha_work/work_permissions.py`

```python
WorkAccessLevel = Literal[
    "guest", "member", "reviewer", "operator", "admin"
]


class WorkCapability(str, Enum):
    EVENT_CONFIRM_OWN = "events.confirm_own"
    EVENT_REVIEW = "events.review"
    EVENT_RESOLVE = "events.resolve"
    EVENT_PROMOTE = "events.promote"
    SENSITIVE_RECORD_READ = "records.view_sensitive"
    ACTION_PROPOSE = "actions.propose"
    ACTION_APPROVE = "actions.approve"
    ACTION_EXECUTE = "actions.execute"
    PERMISSIONS_MANAGE = "permissions.manage"


@dataclass(frozen=True)
class WorkAccess:
    company_id: UUID
    user_id: UUID
    level: WorkAccessLevel
    capabilities: frozenset[WorkCapability]
    source: Literal[
        "platform_admin",
        "explicit",
        "company_owner",
        "client_default",
        "employee_default",
        "external_default",
    ]


async def resolve_work_access(
    conn,
    *,
    user: CurrentUser,
    company_id: UUID,
) -> WorkAccess: ...


def capability_allowed(
    access: WorkAccess,
    capability: WorkCapability,
) -> bool: ...


def assert_work_capability(
    access: WorkAccess,
    capability: WorkCapability,
) -> None: ...
```

### Permission management endpoints

New file: `server/app/matcha/routes/matcha_work/permissions.py`

```http
GET    /api/matcha-work/permissions
PUT    /api/matcha-work/permissions/{user_id}
DELETE /api/matcha-work/permissions/{user_id}
```

Only `permissions.manage` may mutate grants.

Expose home-company access through `/auth/me`:

```ts
interface WorkAccessResponse {
  level: 'guest' | 'member' | 'reviewer' | 'operator' | 'admin'
  capabilities: string[]
}
```

Update:

- `server/app/core/routes/auth/profile.py`
- `client/src/types/dashboard.ts`
- `client/src/hooks/useMe.ts`

Resource responses must still return target-specific `allowed_actions`; `/auth/me` alone is not sufficient for shared resources.

## 3. Confirmation before event creation

### Database

Add `ems_event_drafts` in:

- `server/app/database/bootstrap/ems.py`
- The new EMS Alembic revision

```sql
CREATE TABLE ems_event_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id),
    channel_id UUID NOT NULL REFERENCES channels(id),
    source_message_id UUID NOT NULL REFERENCES channel_messages(id),
    confirmation_message_id UUID REFERENCES channel_messages(id),
    reporter_user_id UUID REFERENCES users(id),
    location_id UUID REFERENCES locations(id),
    narrative TEXT NOT NULL,
    classified JSONB NOT NULL,
    urgency VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'rejected', 'expired')),
    event_id UUID REFERENCES ems_events(id),
    decided_by UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_message_id)
);
```

The source-message uniqueness preserves current transport-level duplicate protection.

### Event-draft service

New file: `server/app/matcha/services/ems/event_drafts.py`

```python
@dataclass(frozen=True)
class DraftDecisionResult:
    draft: dict
    event: dict | None
    changed: bool


async def create_event_draft(
    conn,
    *,
    company_id: UUID,
    channel_id: UUID,
    source_message_id: UUID,
    reporter_user_id: UUID,
    narrative: str,
    classified: dict,
    location_id: UUID | None = None,
) -> dict: ...


async def confirm_event_draft(
    conn,
    *,
    draft_id: UUID,
    actor_user_id: UUID,
    access: WorkAccess,
) -> DraftDecisionResult: ...


async def reject_event_draft(
    conn,
    *,
    draft_id: UUID,
    actor_user_id: UUID,
    access: WorkAccess,
    reason: str | None = None,
) -> DraftDecisionResult: ...


def may_decide_event_draft(
    *,
    reporter_user_id: UUID,
    actor_user_id: UUID,
    access: WorkAccess,
) -> bool: ...
```

Confirmation must lock the draft row with `FOR UPDATE`, insert the final event, update the draft, and create the audit record in one transaction.

### EMS routes

Extend `server/app/matcha/routes/ems.py`:

```http
GET  /api/ems/event-drafts/{draft_id}
POST /api/ems/event-drafts/{draft_id}/confirm
POST /api/ems/event-drafts/{draft_id}/reject
```

These endpoints should use authenticated-user access plus `WorkAccess`, not only the existing `require_admin_or_client` dependency, because employees may confirm their own drafts.

### Channel ingestion changes

Update `server/app/werk/routes/channels_ws.py`:

```python
async def _insert_system_message(
    conn,
    channel_id: str,
    content: str,
    *,
    metadata: dict | None = None,
): ...


async def _bg_event_draft_reply(
    *,
    channel_id: UUID,
    reply_to_message_id: UUID,
    actor_user_id: UUID,
    content: str,
) -> bool: ...
```

Dispatch behavior:

1. Classify the message.
2. `ASK`, schedule, and inventory intents continue through their existing paths.
3. OSHA/severe classifications call `persist_event()` immediately.
4. Other `LOG` classifications call `create_event_draft()`.
5. Huume posts a confirmation card with **Add event** and **Not an event**.
6. Reply fallbacks such as “add it” and “not an event” remain supported for older clients.

A model outage should create a conservative draft rather than silently create a final event. Urgent deterministic classifications continue to auto-log.

## 4. Event resolution

Preserve `dismissed` in storage for compatibility, but label it **No action** in the UI. Add `completed`.

Extend `ems_events` with:

```sql
resolved_by UUID REFERENCES users(id),
resolved_at TIMESTAMPTZ,
resolution_note TEXT,
resolution_code VARCHAR
    CHECK (resolution_code IN (
        'handled', 'not_event', 'duplicate', 'informational'
    )),
duplicate_of_event_id UUID REFERENCES ems_events(id)
```

New file: `server/app/matcha/services/ems/resolution.py`

```python
EventResolution = Literal["completed", "no_action"]


async def resolve_event(
    conn,
    *,
    company_id: UUID,
    event_id: UUID,
    actor_user_id: UUID,
    access: WorkAccess,
    resolution: EventResolution,
    note: str | None = None,
    resolution_code: str | None = None,
    duplicate_of_event_id: UUID | None = None,
) -> dict: ...
```

Add:

```http
POST /api/ems/events/{event_id}/resolve
```

Only `events.resolve` may resolve. Promotion requires `events.promote`. Atomic updates must require current status `logged`; a simultaneous promote/resolve returns `409 Conflict`.

Keep accepting the legacy `{ "dismissed": true }` update during client migration, but remove its use from new UI code.

## 5. Huume Workspace enforcement

Add `work_access` to `TurnContext` in `server/app/matcha/services/matcha_work/turn_pipeline.py`.

Change `run_huume_turn()` in `server/app/matcha/services/huume/agent.py`:

```python
async def run_huume_turn(
    *,
    thread_id: UUID,
    company_id: UUID,
    user_id: UUID | None,
    work_access: WorkAccess,
    history: list[dict[str, Any]],
    current_state: dict[str, Any],
    company_name: str,
    ...
) -> AsyncIterator[dict[str, Any]]: ...
```

Replace raw role checks in `server/app/matcha/services/huume/actions.py`:

```python
def evaluate_huume_action(
    *,
    staged_action: Any,
    features: dict[str, Any],
    capabilities: Collection[WorkCapability],
    thread_huume_mode: bool,
    this_turn_staged_new: bool,
) -> HuumeVerdict: ...


def evaluate_plan_execution(
    *,
    capabilities: Collection[WorkCapability],
    features: dict[str, Any],
) -> str | None: ...


def evaluate_pilot_tool(
    *,
    tool: str,
    capabilities: Collection[WorkCapability],
    features: dict[str, Any],
) -> str | None: ...
```

Extend `HuumeTool` in `server/app/matcha/services/huume/tools.py`:

```python
@dataclass(frozen=True)
class HuumeTool:
    name: str
    kind: str
    declaration: types.FunctionDeclaration
    required_capability: WorkCapability | None = None
    discovery: bool = False
    intent_hints: tuple[str, ...] = ()
```

Authorization is checked both when staging an action and immediately before execution. Permission removal between “draft” and “confirm” must be respected.

Update `server/app/matcha/routes/matcha_work/huume.py`:

- Plan approval → `actions.approve`
- Plan execution → `actions.execute`
- Sensitive record reads → `records.view_sensitive`
- Resolve access using `thread["company_id"]`

## 6. Surface actions in Channels

Add optional metadata to `channel_messages` in:

- `server/app/database/bootstrap/misc_tail.py`
- A new Alembic revision

```sql
ALTER TABLE channel_messages
ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
```

Example:

```json
{
  "action": {
    "kind": "event_draft",
    "id": "uuid"
  }
}
```

Update:

- `server/app/werk/routes/channels.py`
- `server/app/werk/routes/channels_ws.py`
- `client/src/work/api/channels.ts`
- `platforms/desktop/Espresso/Espresso/Models/ChannelModels.swift`

Add:

```http
GET /api/channels/{channel_id}/actions?status=open
```

```ts
interface ChannelAction {
  id: string
  kind:
    | 'event_draft'
    | 'event'
    | 'project_task'
    | 'schedule_proposal'
    | 'inventory_order'
  title: string
  summary: string
  status: string
  source_message_id: string | null
  allowed_actions: string[]
  href: string | null
  created_at: string
}
```

New web files:

- `client/src/work/api/channelActions.ts`
- `client/src/work/components/channels/actions/ChannelActionsDrawer.tsx`
- `client/src/work/components/channels/actions/ChannelActionCard.tsx`
- `client/src/work/components/channels/actions/useChannelActions.ts`

Wire them into:

- `client/src/work/pages/ChannelView/ChannelHeader.tsx`
- `client/src/work/pages/ChannelView/ChannelViewScreen.tsx`
- `client/src/work/pages/ChannelView/MessageList.tsx`

Add a WebSocket notification:

```json
{
  "type": "channel_action_updated",
  "channel_id": "uuid",
  "action": {
    "kind": "event_draft",
    "id": "uuid",
    "status": "confirmed"
  }
}
```

The drawer refetches after this notification. Domain tables remain authoritative; message metadata is only a typed pointer.

## 7. UI terminology and permission management

Update user-facing strings in:

- `client/src/work/components/shell/WorkSidebar/ChatsSection.tsx`
- `client/src/work/pages/MatchaWorkList.tsx`
- `client/src/work/routes/WorkRouteTree.tsx`
- `client/src/work/pages/EventsHub.tsx`
- `client/src/work/components/events/EventDetail.tsx`
- `client/src/work/utils/eventsPermissions.ts`

Add:

- `client/src/work/pages/WorkPermissionsPage.tsx`
- `client/src/work/api/workPermissions.ts`
- `/work/settings/permissions`, visible only with `permissions.manage`

Desktop labels:

- `platforms/desktop/Espresso/Espresso/App/ContentView.swift`
- `platforms/desktop/Espresso/Espresso/App/ContentViewSidebars.swift`
- `platforms/desktop/Espresso/Espresso/Services/SidebarSectionOrderStore.swift`

## 8. Test plan

### Permissions

New `server/tests/matcha_work/test_work_permissions.py`:

- Owner resolves to Admin.
- Same-company client resolves to Operator.
- Employee resolves to Member.
- Explicit grant overrides defaults.
- External collaborator resolves to Guest.
- Target-company grant enables execution.
- Caller-company grant does not grant access in another company.
- Platform-admin override is audited.

### Huume authorization

Extend `server/tests/huume/test_huume_actions.py`:

- Member can stage but cannot execute.
- Reviewer can resolve events but cannot execute plans.
- Operator can approve and execute.
- Permission is rechecked on the confirmation turn.
- Downgrading an Operator blocks a previously staged action.
- REST and chat execution have identical authorization.
- External collaborators can communicate but cannot read sensitive records or execute.

### Event drafts

New `server/tests/ems/test_event_drafts.py`:

- Nonurgent `LOG` creates one draft and zero final events.
- Reporter can confirm their own draft.
- Unrelated Member receives 403.
- Reviewer can decide another user’s draft.
- Reject creates no event.
- Duplicate confirmation cannot create a second event.
- Concurrent confirm/reject has one winning result.
- Expired draft cannot be confirmed.
- Message replay does not create another draft.
- Reply text resolves the correct draft.
- Model outage creates a draft.
- OSHA/severe classification immediately creates an event.
- Schedule, inventory, and `ASK` intents never create drafts.

### Event resolution

New `server/tests/ems/test_event_resolution.py`:

- Reviewer completes an event.
- Reviewer marks an event no-action.
- Member receives 403.
- Promote/resolve race returns 409 for the loser.
- Duplicate target must be same-company and cannot be self-referential.
- Audit includes actor, old status, new status, and note.

### Channel actions

New `server/tests/werk/test_channel_actions.py`:

- Channel membership is required.
- Reporter sees their own draft.
- Member cannot see another user’s sensitive event draft.
- Reviewer sees reviewable events.
- Metadata round-trips through REST and WebSocket.
- Missing metadata from older rows decodes as `{}`.
- Confirming a draft emits `channel_action_updated`.

### Client

Add Vitest coverage for:

- Capability-to-button mapping.
- Event confirmation card loading, success, 403, and 409 states.
- Complete/No action controls.
- Action drawer filtering and counts.
- New terminology.
- Messages without metadata rendering normally.

## 9. Delivery sequence

1. Add migrations, bootstrap schemas, permission resolver, and additive response fields.
2. Apply company-scoped checks to Huume REST and chat paths.
3. Add event drafts, confirmation endpoints, resolution endpoints, and audit behavior.
4. Add structured channel metadata and action aggregation.
5. Ship web action cards, drawer, permissions page, and terminology.
6. Ship Espresso decoding, action affordances, and terminology.
7. Remove legacy `dismissed: true` client usage after both clients migrate.

Before creating migrations, inspect the repository’s current Alembic heads and use the verified `down_revision`; do not assume a head value in advance. Existing URLs and internal database names remain stable, making this an additive migration.

## 10. Acceptance criteria

- A normal channel message never creates a final event without confirmation.
- An urgent OSHA/severe message still creates an event immediately.
- A Member cannot complete/no-action another user’s event.
- A non-Operator cannot execute a Huume task or plan.
- Cross-company collaborators can communicate but cannot inherit the target company’s privileges.
- Channel action cards and the Events hub reflect the same authoritative state.
- Web and Espresso clients remain compatible with messages that lack action metadata.
- Every permission-sensitive mutation is checked server-side and audited.
