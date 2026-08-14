# Matcha Ops Implementation Plan

## Product Boundary

Matcha Work and Matcha Ops are separate product surfaces with granular feature
flags underneath them.

| Surface | Parent flag | Scope |
| --- | --- | --- |
| Matcha Work | `matcha_work` | Projects, private project discussion chat, threads, tasks, documents, recruiting, workspace AI, Huume thread mode |
| Matcha Ops | `matcha_ops` | Company channels, calls, Events/EMS, protocols, inventory, scheduling, schedule intelligence, channel-based automation |
| Personal Werk | Existing personal rules | Personal workspace and community/paid channels |
| Werk Lite | Existing compatibility surface | Retained initially; requires both `matcha_ops` and `matcha_work` |

Work-only companies retain private project discussion chat. They do not receive
standalone company channels, Ops automation, Events, inventory, or scheduling.

Existing non-personal tenants receive `matcha_ops` only when they already have
an Ops child feature or an existing non-project business channel. Future Work
only products remain Work-only.

## 1. Feature Foundation

### Files

- `server/app/core/feature_flags.py`
- `server/app/matcha/dependencies.py`
- `server/app/core/services/company_features.py` (new)
- `server/app/core/routes/admin/companies.py`
- `server/app/core/routes/admin/_shared.py`
- `server/app/core/services/platform_settings.py`
- `client/src/data/featureCatalog.ts`
- `client/src/data/productNavCatalog.ts`

Add default-off flags:

```python
"matcha_ops": False,
"matcha_ops_calls_all_members": False,
```

Update dependencies:

```python
FEATURE_REQUIRES = {
    "huume": ("matcha_work",),
    "huume_code": ("matcha_work",),
    "ems": ("matcha_ops",),
    "inventory": ("matcha_ops",),
    "inventory_voice": ("inventory",),
    "employee_schedule": ("matcha_ops",),
    "schedule_intelligence": ("matcha_ops", "employee_schedule"),
    "matcha_ops_calls_all_members": ("matcha_ops",),
    "werk_lite": ("matcha_ops", "matcha_work"),
}
```

`huume` continues to mean Huume inside Matcha Work threads. Channel
automation remains controlled by EMS, inventory, and scheduling flags.

Add an atomic feature writer:

```python
@dataclass(frozen=True)
class CompanyFeatureUpdateResult:
    stored_features: dict[str, bool]
    effective_features: dict[str, bool]


async def update_company_features(
    conn,
    *,
    company_id: UUID,
    updates: Mapping[str, bool],
    actor_user_id: UUID | None,
    source: Literal[
        "admin_toggle",
        "tier_change",
        "product_sync",
        "stripe_webhook",
        "migration_backfill",
    ],
) -> CompanyFeatureUpdateResult:
    ...
```

The service must:

- Lock the company row.
- Preserve raw stored features instead of materializing tier overlays.
- Validate beta restrictions.
- Validate the final combined dependency state.
- Allow parent and children to change atomically.
- Record feature provenance/audit rows.
- Replace the duplicated write logic in `toggle_company_feature()`.

Add:

```python
def require_all_features(*feature_names: str):
    ...
```

The dependency should resolve the company and feature set once instead of
stacking multiple `require_feature()` calls.

Add `matcha_ops` to `KNOWN_PLATFORM_ITEMS` and platform visibility defaults.

## 2. Channel Classification

### Files

- `server/alembic/versions/<revision>_matcha_ops_boundary.py` (new)
- `server/app/database/bootstrap/misc_tail.py`
- `server/app/werk/services/channel_access.py` (new)
- `server/app/werk/routes/channels.py`
- `server/app/werk/routes/channels_ws.py`
- `server/app/matcha/services/matcha_work/project_service/collaborators.py`

Add a scope column to `channels`:

```sql
channel_scope TEXT NOT NULL
CHECK (channel_scope IN (
    'operations',
    'project_discussion',
    'community'
))
```

Classification rules:

- `project_discussion`: referenced by `mw_projects.project_data->>'discussion_channel_id'`.
- `community`: owned by a personal company.
- `operations`: remaining non-personal company channels.

All future project discussion channel writers explicitly set
`project_discussion`. Normal business channel creation explicitly sets
`operations`.

Add centralized access policy:

```python
class ChannelScope(str, Enum):
    OPERATIONS = "operations"
    PROJECT_DISCUSSION = "project_discussion"
    COMMUNITY = "community"


class ChannelCapability(str, Enum):
    CHAT = "chat"
    CALL = "call"
    AUTOMATION = "automation"
    MANAGE = "manage"


@dataclass(frozen=True)
class ChannelAccess:
    channel_id: UUID
    company_id: UUID
    scope: ChannelScope
    features: Mapping[str, bool]
    is_member: bool
    member_role: str | None
    is_platform_admin: bool


async def load_channel_access(
    conn,
    *,
    channel_id: UUID,
    user_id: UUID,
    user_role: str,
) -> ChannelAccess:
    ...


def assert_channel_capability(
    access: ChannelAccess,
    capability: ChannelCapability,
) -> None:
    ...
```

Policy:

| Channel scope | Chat | Calls | EMS/inventory/scheduling |
| --- | --- | --- | --- |
| Operations | `matcha_ops` | `matcha_ops` | `matcha_ops` plus domain flag |
| Project discussion | `matcha_work` | Not included | Never |
| Community | Existing personal/paid rules | Existing rules | Never |

Entitlement is evaluated against the channel owner's company, not an external
member's home company.

## 3. Channel Route Gates

### Files

- `server/app/werk/routes/channels.py`
- `server/app/werk/routes/channels_ws.py`
- `server/app/werk/routes/channel_actions.py`
- `server/app/werk/routes/channel_calls.py`
- `server/app/werk/routes/channel_broadcasts.py`

Update channel listing:

```python
async def list_channels(
    archived: bool = Query(False),
    scope: ChannelScope | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ChannelSummary]:
    ...
```

Behavior:

- `/ops` requests `scope=operations`.
- `/werk` requests `scope=community`.
- Project discussion is accessed through its project, not the standalone channel browser.
- Responses exclude scopes the user is not entitled to access.

Apply `ChannelCapability.CHAT` to authenticated channel detail, history,
upload, reaction, membership, invite, moderation, and management handlers.

Apply `ChannelCapability.CALL` to calls and authenticated broadcasts.

Keep feature-neutral:

- `GET /channels/categories`
- `GET /channels/invite-info/{code}`
- `POST /channels/invite/{code}/accept`
- LiveKit and Stripe webhooks

Invite redemption resolves the target channel first and applies the target
company's entitlement.

### WebSocket behavior

In `channel_websocket()`:

- Keep handshake authentication feature-neutral.
- Check `CHAT` when joining a room.
- Recheck `CHAT` for every message so entitlement revocation takes effect.
- Never run Ops automation in `project_discussion` or `community` channels.
- Require `operations` plus the corresponding domain flag before EMS, inventory,
  or schedule dispatch.
- Only expose call state when `CALL` is allowed.

Update the automation predicates:

- `_ems_row_allowed()` requires `channel_scope='operations'`, `matcha_ops`, and `ems`.
- `_inventory_row_allowed()` requires `channel_scope='operations'`, `matcha_ops`, and `inventory`.
- `_schedule_company_features()` returns unavailable without `matcha_ops`.
- `_bg_dispatch_huume_mention()` never sends project discussion messages to EMS.
- `_bg_maybe_dispatch_huume_code()` uses `channel_scope='project_discussion'`.

## 4. Ops Permissions

Current `WorkCapability` contains Events permissions. Move Ops authorization
out of Matcha Work while preserving current access levels.

### Files

- `server/app/matcha/services/ops/permissions.py` (new)
- `server/app/matcha/routes/ops_permissions.py` (new)
- `server/app/core/routes/auth/profile.py`
- `server/app/matcha/routes/ems.py`
- `server/app/werk/routes/channel_actions.py`
- `server/app/werk/routes/channels_ws.py`
- `client/src/types/dashboard.ts`
- `client/src/work/utils/eventsPermissions.ts`

Signatures:

```python
class OpsCapability(str, Enum):
    EVENT_CONFIRM_OWN = "events.confirm_own"
    EVENT_REVIEW = "events.review"
    EVENT_RESOLVE = "events.resolve"
    EVENT_PROMOTE = "events.promote"
    EVENT_ASSIGN = "events.assign"
    SENSITIVE_RECORD_READ = "records.view_sensitive"
    ACTION_PROPOSE = "actions.propose"
    ACTION_APPROVE = "actions.approve"
    ACTION_EXECUTE = "actions.execute"
    PERMISSIONS_MANAGE = "permissions.manage"


async def resolve_ops_access(
    conn,
    *,
    user: CurrentUser,
    company_id: UUID,
) -> OpsAccess:
    ...
```

Add `ops_permissions` and `ops_permission_audit_log` tables. Backfill explicit
levels from `mw_work_permissions` so current event authority is preserved.

`GET /auth/me` gains:

```ts
ops_access?: {
  level: 'guest' | 'member' | 'reviewer' | 'operator' | 'admin'
  capabilities: string[]
  source?: string
}
```

EMS and channel automation switch to `ops_access`. Work AI retains
`work_access`.

## 5. Matcha Ops Customer Surface

### New files

- `client/src/ops/routes/OpsRoutes.tsx`
- `client/src/ops/layout/OpsLayout.tsx`
- `client/src/ops/components/OpsSidebar.tsx`
- `client/src/ops/pages/OpsHome.tsx`

### Updated files

- `client/src/App.tsx`
- `client/src/work/routes/WorkRouteTree.tsx`
- `client/src/work/routes/WorkSurfaceContext.ts`
- `client/src/work/components/shell/WorkSidebar.tsx`
- `client/src/work/components/shell/WorkSidebar/useSidebarData.ts`
- `client/src/components/sidebars/ClientSidebar.tsx`
- `client/src/routes/AppRoutes.tsx`
- `client/src/utils/usageTracker.ts`

Add `/ops/*` routes:

```text
/ops
/ops/channels
/ops/channels/join/:code
/ops/channels/:channelId
/ops/events
/ops/events/:eventId
/ops/protocol
/ops/inventory
/ops/inventory/audit
/ops/inventory/:itemId
/ops/schedule
/ops/schedule-intelligence
/ops/access
```

Business `/work` removes standalone channel browsing/creation, Events,
protocol, inventory, and Ops channel calls. Project discussion remains inside
`ProjectView`.

Personal `/werk` retains community channels.

Legacy redirects:

- `/work/events*` -> `/ops/events*`
- `/work/inventory*` -> `/ops/inventory*`
- `/app/employee-schedule` -> `/ops/schedule`
- `/app/schedule-intelligence` -> `/ops/schedule-intelligence`
- Operations `/work/channels/:id` links -> `/ops/channels/:id`
- Project discussion links -> `/work/projects/:projectId?tab=chat`

Update notifications, emails, payment links, and event action links currently
hardcoded to `/work/channels` or `/work/events`.

Werk Lite remains functional during this work and requires both parents.
Consolidating or removing it is a separate follow-up.

## 6. Admin Matcha Ops Management

The first admin version manages **entitlements and health**, not direct event,
inventory, schedule, or channel record editing.

### New files

- `server/app/core/routes/admin/matcha_ops.py`
- `server/app/core/services/matcha_ops_admin.py`
- `server/app/core/models/admin_ops.py`
- `client/src/api/admin/matchaOps.ts`
- `client/src/pages/admin/MatchaOps.tsx`

### Updated files

- `server/app/core/routes/admin/__init__.py`
- `client/src/routes/AdminRoutes.tsx`
- `client/src/components/sidebars/AdminSidebar.tsx`

Routes:

```text
GET   /api/admin/matcha-ops/overview
GET   /api/admin/matcha-ops/companies
GET   /api/admin/matcha-ops/companies/{company_id}
PATCH /api/admin/matcha-ops/companies/{company_id}/features
```

Service signatures:

```python
async def get_ops_overview(conn) -> OpsOverview:
    ...


async def list_ops_companies(
    conn,
    *,
    query: str | None = None,
    enabled: bool | None = None,
    needs_attention: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OpsCompanySummary], int]:
    ...


async def get_ops_company_detail(
    conn,
    *,
    company_id: UUID,
) -> OpsCompanyDetail | None:
    ...


async def update_ops_company_features(
    conn,
    *,
    company_id: UUID,
    updates: MatchaOpsFeaturePatch,
    actor_user_id: UUID,
) -> OpsCompanyDetail:
    ...
```

Admin page contents:

- Enabled company count.
- Channel count by scope.
- Open Events count.
- Low-stock and open-order counts.
- Upcoming shifts and pending schedule requests.
- Searchable company list.
- Parent and child entitlement controls.
- Atomic enable/disable behavior with dependency warnings.
- Stored versus effective feature state.
- Feature provenance.
- Health warnings for invalid or incomplete configurations.
- Links to `/admin/companies/:companyId`.

## 7. Migration and Backfill

The migration will:

1. Add and classify `channels.channel_scope`.
2. Add the channel scope index.
3. Add `ops_permissions` and its audit table.
4. Add `matcha_ops=true` only for non-personal companies with an Ops child flag or at least one `operations` channel.
5. Add `matcha_ops` to custom product definitions containing an Ops child.
6. Add it to broker preconfigured features containing an Ops child.
7. Add `matcha_ops` to platform visible features.
8. Add `migration_backfill` to feature-audit source validation.
9. Record feature-audit rows for changed companies.
10. Update fresh-database bootstrap definitions.

Relevant existing tables:

- `companies.enabled_features`
- `channels`
- `channel_members`
- `channel_messages`
- `mw_projects`
- `mw_work_permissions`
- `ems_events`
- `inventory_items`
- `inventory_orders`
- `schedule_shifts`
- `schedule_requests`

The backfill is set-based and must use the normal migration workflow. No live
database mutation is part of implementation or automated tests.

## 8. Tests

### Backend files

- `server/tests/infrastructure/test_feature_flags.py`
- `server/tests/werk/test_channel_access.py` (new)
- `server/tests/werk/test_channel_route_gates.py` (new)
- `server/tests/channels_ws/test_channel_access_gates.py` (new)
- `server/tests/ops/test_permissions.py` (new)
- `server/tests/admin/test_matcha_ops_admin.py` (new)

Cases:

- Work-only and Ops-only configurations are valid.
- Ops child flags require `matcha_ops`.
- Schedule Intelligence requires scheduling.
- Atomic parent-plus-child updates succeed.
- Disabling the parent with enabled children fails.
- Work-only project discussion chat succeeds.
- Work-only Operations channel access fails.
- Project discussions never trigger EMS, inventory, or scheduling.
- Access uses the channel owner's entitlement.
- WebSocket authorization is rechecked after revocation.
- Public invite and webhook endpoints remain accessible.
- Ops permissions do not depend on Matcha Work.
- Admin aggregates are tenant-scoped.
- Admin feature update rolls back on dependency failure.

### Frontend files

- `client/src/data/featureCatalog.test.ts`
- `client/src/ops/routes/OpsRoutes.test.tsx` (new)
- `client/src/pages/admin/MatchaOps.test.tsx` (new)
- `client/src/work/utils/eventsPermissions.test.ts` (new)

Cases:

- Work-only navigation has no Ops or standalone Channels entry.
- Ops-only navigation has Ops but no Matcha Work entry.
- Project discussion remains reachable from a Work project.
- Each Ops child route has its domain gate.
- Legacy URLs redirect correctly.
- Admin parent disable sends an atomic child-disable request.
- Admin warnings render for invalid stored states.

### Verification commands

```bash
cd server && ./venv/bin/python -m pytest tests/infrastructure/test_feature_flags.py tests/werk tests/channels_ws tests/ops tests/admin/test_matcha_ops_admin.py -q
cd client && npm run test:run
cd client && npx tsc -p tsconfig.app.json --noEmit
```

## Implementation Order

1. Add feature flags, dependency tests, and the atomic feature service.
2. Add channel scope migration and access-policy unit tests.
3. Gate backend channel REST/WebSocket and Ops automation.
4. Split Ops permissions from Work permissions.
5. Add `/ops` routes, layout, sidebar, and legacy redirects.
6. Add `/admin/matcha-ops` API and management page.
7. Add the existing-tenant backfill and product/broker composition updates.
8. Run focused backend/frontend tests and TypeScript verification.

## Risks

1. Project discussions use generic channel tables, so a blanket Ops gate would
   break Work-only projects. `channel_scope` is required to avoid that.
2. Open WebSockets can survive a feature flip. Rechecking every room action
   prevents new writes; an optional later enhancement can evict revoked rooms.
3. Current `WorkCapability` mixes Work AI and Ops event authority. Leaving it
   unchanged would make an Ops-only product depend on Matcha Work permissions.
4. Existing notification and payment links hardcode `/work/channels` and
   `/work/events`; all generated links need a scope-aware destination.
5. Active Ops migration criteria must be applied narrowly so ordinary Work
   tenants do not unexpectedly receive the Ops product.
