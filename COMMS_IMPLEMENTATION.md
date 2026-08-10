# Tell-Us Comms Implementation

## Scope

Comms adds asynchronous, text-based conversations between Tell-Us consumers and
claimed businesses. A consumer can search for a business, choose a location and
topic, ask a question, and receive replies from the business owner or an
authorized inbox team member.

The shared backend and Tell-Us web client are implemented. The native iOS client
is not part of this implementation yet; it still uses the legacy feedback DM
surface.

The detailed design and rollout plan is in
[`TELLUS_GENERAL_MESSAGING_IMPL_PLAN.md`](./TELLUS_GENERAL_MESSAGING_IMPL_PLAN.md).

## Product rules

- Messaging is asynchronous polling, not live presence or WebSockets.
- Consumers must be signed in and email verified.
- Only claimed businesses that enable Comms receive new conversations.
- Business owners can use Comms without an active paid plan.
- Additional inbox agents require an active plan and explicit permission.
- A multi-location business requires a location selection.
- One open general conversation exists per consumer, business, and location.
- Messages are plain text, capped at 4,000 characters, with no attachments.
- A conversation is not a reservation, purchase, or guarantee of availability.

## Backend

### Database

Migration `tellus_app_17` extends the existing DM tables:

- `tellus_brands.messaging_enabled`
- `tellus_brand_members.can_manage_inbox`
- Nullable `tellus_dm_threads.report_id`
- Thread kind, topic, status, store, assignment, close, and first-response fields
- Client message UUIDs with sender-scoped idempotency
- Partial unique indexes for one open general thread per business/location

Existing report-linked threads remain `kind='feedback'`. New conversations use
`kind='general'`. Downgrading intentionally deletes general conversations before
restoring the legacy `report_id` constraint.

### API

New routes are under `/api/tellus/comms`:

- `GET /inbox-brands`
- `POST /brands/{slug}/threads`
- `GET /threads`
- `GET /threads/{id}/messages?after={message_id}`
- `POST /threads/{id}/messages`
- `POST /threads/{id}/take`
- `PATCH /threads/{id}/assignment`
- `PATCH /team/{member_id}/inbox`
- `PATCH /brand/messaging`
- `POST /threads/{id}/close`
- `POST|DELETE /threads/{id}/block`

The old `/dm/*` and `/feedback/{report_id}/dm` routes remain for backward
compatibility with feedback conversations.

Authorization is membership-based: owners always have inbox access, while
non-owner members need `can_manage_inbox=true` and an active business plan.
Consumer-facing thread serialization redacts inbox-agent identity.

## Web client

- Public business pages expose a Message CTA and store/topic-aware composer.
- Places search exposes Message links for enabled businesses.
- `/messages` is the consumer Comms surface.
- `/brand/messages` is the owner/team inbox, including consumer-typed agents.
- Inbox filters support conversation kind and status.
- Inbox agents can take conversations; owners can assign them.
- Threads support close/block, idempotent sends, deep links, and five-second
  active-thread polling.
- Inbox lists poll every 15 seconds while visible.
- Brand settings and the inbox expose the Comms opt-in toggle.
- Admin DM oversight includes general/feedback filters, status, store, and
  assignee metadata.

## Notifications and abuse controls

- Consumer messages notify the owner and eligible inbox agents in-app and by
  email.
- Business replies notify the consumer in-app and by email.
- Assignment changes notify the newly assigned agent.
- Per-account burst/hourly limits apply to all sends.
- New threads are limited per account per day and per business per day.
- Foreign thread IDs, stores, assignments, and replayed client IDs are scoped
  and rejected safely.

## Verification

- Tell-Us backend tests: `294 passed`
- Tell-Us web production build: `npm run build` passed
- Working implementation commits:
  - `00edd7a feat(comms): add business messaging`
  - `41c759e fix(comms): harden messaging flows`
- Pull request: [#171](https://github.com/tajaa/matcha-recruit/pull/171)

## Follow-up: native iOS

The iOS app in `platforms/ios/TellUs` needs a dedicated follow-up:

1. Extend `DmModels.swift` for general thread fields and client IDs.
2. Add `/comms` methods to `DmService` or a dedicated `CommsService`.
3. Add public business discovery/composer UI.
4. Add consumer and business Comms inbox views with polling and assignment.
5. Add Comms opt-in and team-permission controls.
6. Add Swift model, service, view-model, and UI tests.
