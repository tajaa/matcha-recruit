# Tellus General Business Messaging — Technical Implementation Plan

Status: implementation checkpoint. The schema, backend, frontend, tests, and
rollout notes below are the implementation contract for Comms.

## 1. Objective

Let a signed-in Tellus consumer find a claimed business, choose a location,
and start a text conversation that the business owner or an authorized inbox
team member can answer.

This extends the existing feedback DM system; it does not create a second chat
stack. Existing report-linked conversations continue to work unchanged from a
user's perspective.

Implementation note: the new public surface is namespaced under `/comms/*`;
legacy report-linked `/dm/*` routes remain backward-compatible.

Examples:

- “Are you open today? It’s a holiday.”
- “Do you have a table for five at 10pm?”
- “Do you have Doc Martens in size 11?”

## 2. Product decisions carried by this plan

1. **Messaging is asynchronous, not presence-backed live chat.** The active
   thread polls for new messages every five seconds. No WebSocket, online
   indicator, or guaranteed response time ships in v1.
2. **Consumers must have an active, email-verified Tellus account.** Anonymous
   messaging is out of scope.
3. **Only claimed businesses that explicitly enable general messaging can
   receive new general conversations.** Existing feedback DMs remain available
   regardless of this toggle.
4. **Core owner messaging is free.** A claimed business owner may read and
   answer general messages even when `plan_status != 'active'`. Additional
   inbox agents require an active plan. This makes messaging an acquisition
   surface instead of an empty consumer promise.
5. **A location is required when a brand has more than one store.** A single
   store is selected automatically. A store-less brand may receive a
   brand-level conversation with `store_id = NULL`.
6. **One open general conversation exists per consumer, brand, and store.** A
   new question reuses that open thread. After it is closed, the consumer may
   start another.
7. **Text only in v1.** No files, photos, payments, reservations, or inventory
   synchronization.
8. **Unclaimed/disabled businesses never receive a hidden message.** The UI
   explains that messaging is unavailable; an invitation/waitlist workflow is
   a later phase.

## 3. Existing system to reuse

- Backend route: `server/app/tellus/routes/dms.py`
  - one report-linked thread per identified report;
  - role-scoped thread access;
  - message history, unread tracking, consumer blocking;
  - in-app and email notifications;
  - burst/hourly rate limits.
- Schema: `tellus_dm_threads` and `tellus_dm_messages`, introduced by
  `server/alembic/versions/tellus_app_05_public_reviews_dms.py`.
- Consumer/business discovery: `server/app/tellus/routes/places.py` and
  `client/tellus/src/pages/Places.tsx`.
- Public business page: `server/app/tellus/routes/community.py` and
  `client/tellus/src/pages/PublicBrand.tsx`.
- Shared inbox UI: `client/tellus/src/pages/Messages.tsx` and
  `client/tellus/src/components/DmThreadPanel.tsx`.
- Team identity: `tellus_brand_members`, managed in
  `server/app/tellus/routes/board.py`.
- Notifications: `server/app/tellus/services/points_service.py:notify_account`
  plus `server/app/tellus/services/email.py:send_tellus_dm_email`.
- Admin oversight: `server/app/tellus/routes/admin/moderation.py`.

The existing table names and `/dm/*` routes remain canonical. Renaming them to
`conversations` would add a risky data/API migration without improving the
consumer experience.

## 4. Database migration

### 4.1 Revision placement

Create:

`server/alembic/versions/tellus_app_17_general_messaging.py`

Use:

```python
revision = "tellus_app_17"
down_revision = "oceanlab_app_03"
```

Verified migration graph note: Tellus and Oceanlab currently share an
interleaved chain (`tellus_app_15 -> oceanlab_app_01 -> tellus_app_16 ->
oceanlab_app_02 -> oceanlab_app_03`). `oceanlab_app_03` is the current head of
that chain. Do not point the new migration directly at `tellus_app_16` or it
will create an unintended sibling head.

### 4.2 Brand messaging opt-in

Add to `tellus_brands`:

```sql
ALTER TABLE tellus_brands
  ADD COLUMN messaging_enabled BOOLEAN NOT NULL DEFAULT FALSE;
```

This applies only to **general** conversations. Report-linked feedback DMs do
not consult this flag.

### 4.3 Inbox permission on existing team memberships

Add:

```sql
ALTER TABLE tellus_brand_members
  ADD COLUMN can_manage_inbox BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE tellus_brand_members
SET can_manage_inbox = TRUE
WHERE role = 'owner';
```

Owner writers already have an invariant requiring a corresponding owner member
row. Every future owner-row insertion must set or inherit
`can_manage_inbox = TRUE`.

Do not turn every existing board moderator into an inbox agent. Board
moderation does not imply access to private customer conversations.

### 4.4 Evolve `tellus_dm_threads` in place

Add columns:

```sql
ALTER TABLE tellus_dm_threads ALTER COLUMN report_id DROP NOT NULL;

ALTER TABLE tellus_dm_threads
  ADD COLUMN kind TEXT NOT NULL DEFAULT 'feedback',
  ADD COLUMN store_id UUID REFERENCES tellus_stores(id) ON DELETE SET NULL,
  ADD COLUMN topic TEXT,
  ADD COLUMN status TEXT,
  ADD COLUMN assigned_member_id UUID
    REFERENCES tellus_brand_members(id) ON DELETE SET NULL,
  ADD COLUMN first_brand_response_at TIMESTAMPTZ,
  ADD COLUMN closed_at TIMESTAMPTZ,
  ADD COLUMN closed_by_account_id UUID
    REFERENCES tellus_accounts(id) ON DELETE SET NULL;
```

Backfill store context on existing feedback threads:

```sql
UPDATE tellus_dm_threads t
SET store_id = r.store_id
FROM tellus_reports r
WHERE r.id = t.report_id AND t.store_id IS NULL;
```

Backfill workflow state from the latest existing message:

```sql
UPDATE tellus_dm_threads t
SET status = CASE
  WHEN (
    SELECT m.sender_role
    FROM tellus_dm_messages m
    WHERE m.thread_id = t.id
    ORDER BY m.created_at DESC, m.id DESC
    LIMIT 1
  ) = 'consumer' THEN 'waiting_brand'
  ELSE 'waiting_consumer'
END;

ALTER TABLE tellus_dm_threads ALTER COLUMN status SET NOT NULL;
```

Add constraints idempotently with `DO $$ BEGIN ... EXCEPTION WHEN
duplicate_object THEN NULL; END $$`:

```sql
CHECK (kind IN ('feedback', 'general'))
CHECK (status IN ('waiting_brand', 'waiting_consumer', 'closed'))
CHECK (topic IS NULL OR topic IN
  ('hours', 'availability', 'inventory', 'order', 'service',
   'accessibility', 'other'))
CHECK (
  (kind = 'feedback' AND report_id IS NOT NULL) OR
  (kind = 'general' AND report_id IS NULL)
)
CHECK (
  (status = 'closed' AND closed_at IS NOT NULL) OR
  (status <> 'closed' AND closed_at IS NULL)
)
```

Keep the existing `UNIQUE(report_id)`. PostgreSQL permits multiple NULLs, so
it still enforces one feedback thread per report while allowing general
threads.

Add two partial unique indexes to enforce one open general thread per scope:

```sql
CREATE UNIQUE INDEX ux_tellus_dm_general_open_store
ON tellus_dm_threads (brand_id, consumer_account_id, store_id)
WHERE kind = 'general' AND status <> 'closed' AND store_id IS NOT NULL;

CREATE UNIQUE INDEX ux_tellus_dm_general_open_brand
ON tellus_dm_threads (brand_id, consumer_account_id)
WHERE kind = 'general' AND status <> 'closed' AND store_id IS NULL;
```

Add list indexes:

```sql
CREATE INDEX ix_tellus_dm_threads_brand_status
ON tellus_dm_threads (brand_id, status, last_message_at DESC);

CREATE INDEX ix_tellus_dm_threads_assignee
ON tellus_dm_threads (assigned_member_id, status, last_message_at DESC)
WHERE assigned_member_id IS NOT NULL;
```

### 4.5 Message retry idempotency

Add a client-generated UUID to messages:

```sql
ALTER TABLE tellus_dm_messages
  ADD COLUMN client_message_id UUID;

CREATE UNIQUE INDEX ux_tellus_dm_message_client_id
ON tellus_dm_messages (sender_account_id, client_message_id)
WHERE client_message_id IS NOT NULL;
```

Existing rows remain NULL. New clients generate one UUID per compose action and
reuse it on a network retry. Notifications and thread state updates happen only
when the message INSERT returns a new row.

### 4.6 Downgrade order

Drop new indexes and constraints first, then new columns. Restore
`report_id NOT NULL` only after deleting any `kind='general'` rows in the
downgrade. The downgrade is intentionally data-destructive for general
conversations and must say so in its migration docstring.

## 5. Backend structure

### 5.1 New service module

Create `server/app/tellus/services/messaging_service.py` so `routes/dms.py`
does not absorb authorization, notification fan-out, and state-machine logic.

Functions:

```python
async def resolve_inbox_brand(conn, account: TellusAccount, brand_id: UUID) -> dict:
    """Owner or can_manage_inbox member; enforce plan rule for non-owners."""

async def get_thread_access(
    conn, thread_id: UUID, account: TellusAccount,
) -> tuple[dict, Literal["brand", "consumer"]]:
    """404 on no access; do not branch only on account.account_type."""

async def serialize_thread(conn, row, viewer_role: str) -> TellusDmThread:
    """Materialize store, topic, assignee, status, and unread fields."""

async def notify_inbox_team(conn, thread: dict, title: str, body: str) -> list[dict]:
    """Insert in-app notifications and return email recipients."""

def next_status(sender_role: str) -> Literal["waiting_brand", "waiting_consumer"]:
    """Pure transition used by both initial and follow-up sends."""
```

Authorization must be membership-based, not `account_type`-based. A consumer
account may also be an inbox agent for a business. If the same account attempts
to start a consumer conversation with a brand whose inbox it manages, return
409 rather than letting it become both sides of one thread.

Owner policy:

- `tellus_brands.owner_account_id == account.id` always grants inbox access;
- the owner member row remains the normal path, but retain the owner fallback
  used by the board service;
- a non-owner member needs `can_manage_inbox = TRUE` and the brand's plan must
  be active.

### 5.2 Pydantic models

Update `server/app/tellus/models/tellus.py`:

```python
DmKind = Literal["feedback", "general"]
DmTopic = Literal[
    "hours", "availability", "inventory", "order", "service",
    "accessibility", "other",
]
DmStatus = Literal["waiting_brand", "waiting_consumer", "closed"]

class TellusDmStart(BaseModel):
    store_id: Optional[UUID] = None
    topic: DmTopic = "other"
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID

class TellusDmSend(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID

class TellusDmStartResponse(BaseModel):
    thread: TellusDmThread
    message: TellusDmMessage

class TellusDmAssign(BaseModel):
    member_id: Optional[UUID] = None  # NULL = unassign; owner-only
```

Extend `TellusDmThread`:

- `report_id: Optional[UUID]`
- `kind: DmKind`
- `topic: Optional[DmTopic]`
- `status: DmStatus`
- `store_id`, `store_name`, `store_city` nullable
- `assigned_member_id`, `assigned_member_name` nullable
- `viewer_role: DmSenderRole`
- `first_brand_response_at`, `closed_at` nullable

`viewer_role` replaces frontend inference from the signed-in account's global
account type, which is wrong for consumer-typed inbox agents.

Add to `TellusPublicBrandPage`:

```python
messaging_enabled: bool = False
stores: list[TellusMessagingStore] = Field(default_factory=list)
```

`TellusMessagingStore` contains `id`, `name`, `address`, `city`, and `state`.
The public response exposes no internal team information.

Extend `TellusBrandTeamMember` with `can_manage_inbox: bool`.

### 5.3 Consumer starts a general conversation

Add to `server/app/tellus/routes/dms.py`:

```text
POST /dm/brands/{slug}/threads
dependency: require_consumer
body: TellusDmStart
response: TellusDmStartResponse
```

Validation order:

1. Existing burst/hourly per-account message limits.
2. Additional new-thread limit: 10/day/account and 3/day/account/brand.
3. Fetch brand by slug.
4. Require `owner_account_id IS NOT NULL` and `messaging_enabled = TRUE`;
   otherwise return structured 409:
   `{"code": "messaging_unavailable", "message": "..."}`.
5. Reject a caller who owns or manages that inbox.
6. Validate `store_id` belongs to the brand.
7. If more than one store exists and no store was supplied, return 422.
8. Within one transaction, insert/reuse the open thread using the matching
   partial unique index, lock it `FOR UPDATE`, and insert the first message
   idempotently.
9. Set `status='waiting_brand'`, update `last_message_at`, and notify inbox
   recipients only if the message insert won.

Use `INSERT ... ON CONFLICT ... DO UPDATE RETURNING`, not a caught
`UniqueViolationError`, because the route is inside a transaction.

### 5.4 List threads

Extend the existing endpoint:

```text
GET /dm/threads
query: brand_id?, kind?, status?, assigned=(any|unassigned|mine), limit, offset
```

Behavior:

- Consumer view without `brand_id`: threads where
  `consumer_account_id = account.id`.
- Inbox view with `brand_id`: resolve owner/inbox membership first.
- A true brand owner may omit `brand_id`; use `account.brand_id`.
- A consumer-typed inbox agent must provide `brand_id` when they manage more
  than one inbox.
- Preserve default newest-first order.
- Batch/materialize rows; never issue one store/assignee query per thread.

The response includes both feedback and general conversations. The UI can
filter, but there remains one unified inbox.

### 5.5 Fetch and poll messages

Extend:

```text
GET /dm/threads/{thread_id}/messages?after={message_id}
```

Without `after`, preserve the current latest-200 behavior. With `after`, find
the anchor's `(created_at, id)` within that same thread and return newer rows
ordered ascending, capped at 200. A foreign/missing anchor is a scoped 404.

Opening/fetching continues to mark the other role's messages read. Polling an
empty delta is therefore cheap and idempotent.

### 5.6 Send a follow-up message

Keep:

```text
POST /dm/threads/{thread_id}/messages
```

Change the implementation:

1. Resolve thread access through `messaging_service.get_thread_access`.
2. Lock the thread `FOR UPDATE`.
3. Reject blocked or closed threads with 409/403.
4. Insert by `(sender_account_id, client_message_id)` with
   `ON CONFLICT DO NOTHING RETURNING *`.
5. On a replay, return the previously inserted message and perform no state or
   notification write.
6. On a new consumer message, set `status='waiting_brand'`.
7. On a new brand message, set `status='waiting_consumer'` and
   `first_brand_response_at=COALESCE(first_brand_response_at, NOW())` for
   general threads.
8. Update `last_message_at` and notify the opposite side after the transaction.

Notifications continue using `kind='dm_message'` and
`reference_type='dm_thread'`, so existing navigation behavior remains valid.
Change copy from “about your feedback” to general thread-aware text.

### 5.7 Assignment and lifecycle endpoints

Add:

```text
POST /dm/threads/{thread_id}/take
```

Inbox agent only. CAS assignment:

```sql
UPDATE tellus_dm_threads
SET assigned_member_id = $caller_member_id
WHERE id = $thread_id
  AND brand_id = $brand_id
  AND status <> 'closed'
  AND (assigned_member_id IS NULL OR assigned_member_id = $caller_member_id)
RETURNING *;
```

Return 409 when another agent already owns it.

Add owner-only assignment:

```text
PATCH /dm/threads/{thread_id}/assignment
body: {member_id: UUID | null}
```

Validate that the member belongs to the thread's brand and has
`can_manage_inbox=TRUE`.

Add either-party close:

```text
POST /dm/threads/{thread_id}/close
```

CAS `status <> 'closed'`, stamp `closed_at` and `closed_by_account_id`. Closing
does not block either party and does not delete history. A closed thread is
readable but not writable.

Keep the existing consumer block/unblock endpoints in v1. Brand-wide customer
blocking and user-report queues are a follow-up; brands can close a thread and
rate limits prevent immediate message flooding.

### 5.8 Inbox brand discovery

Add:

```text
GET /dm/inbox-brands
dependency: require_tellus_account
```

Return every brand the account owns or can manage, with `brand_id`, `name`,
`slug`, `role`, `can_manage_inbox`, and `plan_status`. This is the frontend
bootstrap for consumer-typed inbox agents.

### 5.9 Messaging settings/team permissions

Update `server/app/tellus/routes/links.py` or create the more focused
`server/app/tellus/routes/messaging_settings.py` and register it in
`routes/__init__.py`.

Recommended endpoints:

```text
PATCH /brand/messaging
body: {enabled: bool}
owner only; no active-plan requirement

PATCH /board/team/{member_id}/inbox
body: {enabled: bool}
owner only; active plan required when enabling a non-owner
```

Although the team table is currently managed in `board.py`, the inbox toggle
is not a board concern. Prefer moving generic team CRUD into a new
`routes/team.py` in the same change if that can be done without altering URLs;
otherwise keep the existing endpoints and document the temporary ownership.

Every owner creation path (`auth.py`, admin owner assignment, claim approval)
must continue creating an owner membership whose inbox permission is true.

### 5.10 Public business page and Places response

Update `server/app/tellus/routes/community.py:public_brand_page`:

- fetch every store for the brand, ordered by creation;
- return `messaging_enabled = claimed AND b.messaging_enabled`;
- do not expose the toggle for an unclaimed brand as enabled;
- add the store list to `TellusPublicBrandPage`.

Update `TellusPlaceSearchResult` and `places.py:search_places` with
`messaging_enabled`. This avoids rendering a Message CTA that must be corrected
after navigating.

No message endpoint accepts a raw brand UUID from the public client; start by
slug, then resolve ownership/store scope server-side.

### 5.11 Admin oversight compatibility

Update `server/app/tellus/models/admin.py` and
`server/app/tellus/routes/admin/moderation.py`:

- make admin DM `report_id` nullable;
- include `kind`, `topic`, `status`, store name, and assignee name;
- change joins to the report table from inner to left joins wherever present;
- add filters for `kind` and `status`;
- preserve read-only message inspection and block/unblock audit actions.

Do not expose general message content anywhere public or in business analytics.

## 6. Notification fan-out

Consumer -> business:

- insert in-app notifications for the owner and all eligible
  `can_manage_inbox` members;
- exclude the consumer if they happen to appear in the membership set
  (the start endpoint already rejects this, but keep defense in depth);
- email the owner and eligible inbox agents after the DB transaction;
- use one set-based `INSERT ... SELECT`, with explicit `$n::text` casts as
  required by the existing Tellus notification convention.

Business -> consumer:

- retain one in-app notification and one best-effort email;
- title: business name;
- body: “You have a new reply to your question.”;
- CTA: `/messages?thread={thread_id}`.

Assignment changes notify only the newly assigned agent, not the consumer.

## 7. Frontend implementation

### 7.1 API types

Update `client/tellus/src/api/types.ts` to mirror every backend model:

- optional `report_id`;
- `kind`, `topic`, `status`, store and assignment fields;
- `viewer_role`;
- `DmStartResponse`;
- `MessagingStore`;
- `messaging_enabled` on public brand/search results;
- `can_manage_inbox` on `BrandTeamMember`.

The client must generate `crypto.randomUUID()` once per send attempt and retain
it until that attempt succeeds or the composer content changes.

### 7.2 Public brand composer

Create:

`client/tellus/src/components/BusinessMessageComposer.tsx`

Wire it into `client/tellus/src/pages/PublicBrand.tsx`.

Behavior:

- Claimed + messaging enabled + signed-in consumer: **Message** button opens
  the inline composer.
- Logged out: Message sends the user to
  `/login?returnTo=/b/{slug}?message=1`.
- Brand account: no consumer Message CTA.
- Unclaimed: “Messaging will be available when this business claims its page.”
- Claimed but disabled: no composer; “This business isn’t accepting messages
  on Tellus.”
- Multi-store: require a location selector.
- Single store: preselect it.
- Topic chips plus freeform body.
- Success navigates to `/messages?thread={thread_id}`.

Do not describe it as “live” or show an online indicator.

### 7.3 Places search

Update `client/tellus/src/pages/Places.tsx`:

- change the page framing from “Find a place to review” to “Find a business”;
- retain Review/Feedback actions;
- for a result with `messaging_enabled`, add a Message link to
  `/b/{slug}?message=1`;
- unclaimed Google suggestions remain Add & Review only—no fake message flow.

### 7.4 Unified Messages page

Refactor `client/tellus/src/pages/Messages.tsx` rather than creating a second
inbox.

Consumer view:

- thread type chip: “Question” or feedback state;
- business/store/topic context;
- waiting/closed state;
- deep-open `?thread=` support.

Business/inbox view:

- filters: New (`waiting_brand`), Mine, Unassigned, Closed;
- location and topic on cards;
- Take, Assign, and Close controls;
- consumer identity remains display name only, never email.

Use `thread.viewer_role`, not `account.account_type`, to decide message bubble
ownership and available controls.

### 7.5 Thread panel and polling

Refactor `client/tellus/src/components/DmThreadPanel.tsx`:

- accept a generic thread rather than requiring `reportId` semantics;
- keep feedback-thread opening from `BrandFeedback` working;
- poll the active thread every five seconds using `after={last_message_id}`;
- stop polling when the document is hidden, the thread closes, or the component
  unmounts;
- immediately append the idempotent send response;
- on reconnect, poll before permitting another send;
- retain consumer block/unblock behavior;
- disable compose for closed threads.

Poll thread lists every 15 seconds while the Messages page is visible. Do not
add a Tellus WebSocket in v1.

### 7.6 Team inbox access

Update `client/tellus/src/App.tsx` and `components/Layout.tsx`:

- `/brand/messages` must permit a consumer-typed inbox agent, analogous to the
  existing board moderator exception;
- bootstrap accessible inboxes with `GET /dm/inbox-brands`;
- show a **Business Inbox** navigation item when the account manages at least
  one inbox;
- require `brand_id` selection when the agent manages multiple brands;
- true unpaid brand owners may access `/brand/messages` even though other
  dashboard routes still redirect to billing.

Update the existing team section in `pages/brand/Board.tsx`, or move it into a
new general team/settings page, to expose the inbox-permission toggle.

## 8. Security and abuse controls

- Require verified consumer identity for start/send.
- Preserve account-level minute/hour message limits.
- Add per-brand and daily new-thread limits.
- Scope every thread fetch to consumer ownership or authorized brand
  membership; return 404 for foreign IDs.
- Validate store ownership on every start and assignment membership on every
  assignment.
- No HTML rendering; message bodies remain plain text.
- No attachments or external link previews.
- Keep a hard 4,000-character message limit.
- Do not expose consumer email to brands or inbox agents.
- Do not expose inbox-agent identity to consumers; messages appear from the
  business.
- Do not hold a pooled DB connection while sending email.
- Preserve admin visibility/audit for abuse investigations.
- Display a consumer-facing note that hours, inventory, prices, and availability
  may change and a message is not a reservation or purchase confirmation.

## 9. Test plan

### 9.1 Backend unit tests

Create `server/tests/tellus/test_general_messaging.py` with pure/fake-connection
coverage where possible:

1. `next_status('consumer') == 'waiting_brand'`.
2. `next_status('brand') == 'waiting_consumer'`.
3. Owner fallback grants inbox access even if the member row is missing.
4. Board moderator without `can_manage_inbox` is denied.
5. Enabled non-owner agent on an active plan is allowed.
6. Non-owner agent on a paused/pending plan is denied.
7. Consumer ownership and inbox membership both materialize the correct
   `viewer_role`.
8. A foreign thread remains a 404.
9. Multi-store start without `store_id` is 422.
10. A foreign `store_id` is 404/422 without leaking another brand.
11. Unclaimed and messaging-disabled brands return structured 409.
12. A team member cannot message their own managed brand as a consumer.
13. Duplicate `client_message_id` returns the existing row and emits no second
    notification/state update.
14. Consumer send transitions to `waiting_brand`.
15. First business reply stamps `first_brand_response_at` once.
16. Later business replies never overwrite the first-response timestamp.
17. Closed and blocked threads reject sends.
18. Take is CAS-safe; a second agent gets 409.
19. Owner assignment rejects a member from another brand.
20. Existing report-DM open/list/send/block behavior stays green with
    `kind='feedback'` and optional new fields.

Add source-guard tests for:

- every `/admin/*` route remains admin-gated;
- `report_id` joins in admin DM queries are left joins;
- new send paths use `ON CONFLICT`, not caught uniqueness exceptions;
- public models never include consumer email or inbox-member identity.

### 9.2 Frontend checks

- Logged-out Message preserves `returnTo` and reopens the composer.
- Claimed/enabled, claimed/disabled, and unclaimed CTAs render correctly.
- Store selection is automatic for one and required for many.
- Double-click/retry reuses one `client_message_id`.
- `?thread=` deep-link opens the correct thread.
- Polling starts/stops with visibility and unmount.
- Consumer-typed inbox agent sees Business Inbox but still retains their own
  consumer Messages.
- Closed threads render history with no composer.
- Existing feedback thread cards still show review-state urgency.

### 9.3 Migration rehearsal

Against a dev copy containing existing DM rows:

1. `alembic upgrade heads` succeeds.
2. Every existing thread has `kind='feedback'`, non-null `report_id`, and a
   derived non-null status.
3. Existing messages and unread counts are unchanged.
4. Two general threads with different stores are permitted.
5. A second open general thread for the same consumer/brand/store is rejected.
6. Closing the first permits creation of another.
7. `alembic downgrade oceanlab_app_03` is tested only on disposable data and
   confirms the documented deletion of general threads.

### 9.4 Manual end-to-end matrix

1. Consumer searches a claimed/enabled business, messages it, and lands in the
   thread.
2. Owner receives in-app/email notification and replies while unpaid.
3. Consumer receives the reply within the polling window and by email.
4. Paid brand enables a team agent; agent takes and answers the thread.
5. Two agents attempt Take simultaneously; one succeeds, one sees 409.
6. Consumer blocks a thread; owner/agent can read history but cannot reply.
7. Either side closes; history remains and a new conversation can be started.
8. Unclaimed and disabled businesses never create a thread/message row.
9. Existing feedback DM flow works from Feedback and My Reviews.
10. Admin can inspect/block a general thread whose `report_id` is NULL.

## 10. Delivery sequence

Suggested commits:

1. `feat(tellus): evolve DM conversation schema`
   - migration, models, service helpers, migration/unit tests.
2. `feat(tellus): add consumer business messaging API`
   - start/send/list/poll/close, idempotency, notifications, route tests.
3. `feat(tellus): add shared business inbox routing`
   - inbox permissions, agent discovery, take/assign, owner-free access.
4. `feat(tellus): add public message composer`
   - public brand/Places models and UI.
5. `feat(tellus): upgrade unified messages inbox`
   - filters, polling, assignment UI, deep links, regression verification.
6. `chore(tellus): extend admin messaging oversight`
   - nullable report support, filters, audit UI.

Deploy order:

1. Run migration.
2. Deploy additive backend changes with all existing DM endpoints compatible.
3. Deploy frontend.
4. Existing brands remain `messaging_enabled=FALSE` until they opt in.
5. Enable with a small set of test businesses, monitor response rates, spam,
   error reports, and notification volume.

## 11. Metrics to instrument after correctness

Do not block v1 on a full analytics system. Once the flow is stable, measure:

- composer opens -> first messages sent;
- enabled businesses receiving at least one question;
- first business response time;
- percentage answered within 15 minutes, 1 hour, and 24 hours;
- conversations closed without a business reply;
- block rate and rate-limit hits;
- location/topic distribution;
- business messaging opt-in and team-agent adoption.

Only after enough volume should Tellus display a public “Usually replies in…”
label. Never infer live presence from recent activity.

## 12. Explicitly out of scope

- WebSockets, typing indicators, read receipts exposed to the other party, or
  online presence.
- Anonymous/guest messages.
- Attachments, photos, voice notes, calls, or video.
- Reservation booking or payment collection in chat.
- Inventory/point-of-sale integration.
- AI-generated answers or autonomous business bots.
- Message editing/deletion.
- Business-wide consumer block lists and user-submitted moderation reports
  (admin thread blocking remains available).
- Delivering questions to unclaimed businesses or building the invitation
  waitlist.
- Public response-time badges before sufficient production data exists.
