# Tell-Us Comms — iOS Integration Plan

Status: planning only. This document describes the native SwiftUI work to add
Comms to `platforms/ios/TellUs`; it does not change the server contract or
implement the feature.

The shared backend, migration, and Tell-Us web implementation are already
merged. The canonical server behavior is documented in
[`COMMS_IMPLEMENTATION.md`](./COMMS_IMPLEMENTATION.md).

## 1. Goal and scope

Bring the existing Comms capability to the native Tell-Us iOS app:

- A signed-in, verified consumer can find an enabled business, choose a store
  and topic, and send a question.
- Consumers can read, reply to, close, or block their conversations.
- Business owners and authorized inbox agents can read, reply, take, assign,
  and close conversations.
- Existing feedback-linked DMs continue to work in the same unified inbox.

This is native SwiftUI work only. Do not add a second database schema, a second
messaging backend, WebSockets, push notifications, attachments, reservations,
or inventory integrations.

## 2. Decisions carried into iOS

1. Reuse `/comms/*` for the unified list, history, sends, lifecycle, and
   inbox-agent flows. Keep the legacy feedback-DM start endpoint only for a
   brand initiating a feedback conversation.
2. Keep feedback DMs and general questions in one native inbox. Thread `kind`
   controls copy and controls, rather than separate tabs or services.
3. Add a native Comms sheet from an enabled Places search result. iOS has no
   native public business-page view today; “See reviews” remains a web handoff
   while “Message” opens the native Comms composer.
4. Do not expose an inbox agent’s identity to consumers. Render every brand
   reply as a business reply.
5. Poll an open thread every five seconds and its visible inbox every 15
   seconds. Pause timers whenever the scene is inactive/backgrounded.
6. A brand owner with an inactive plan can still use Comms, per the backend
   policy. Do not route an owner away from Comms merely because the normal
   brand dashboard is behind `BillingWallView`.
7. A consumer-typed inbox agent keeps their consumer Messages and receives a
   separate Business Inbox entry. If they manage more than one active inbox,
   require a business selection before loading threads.

## 3. Current iOS gaps

| Area | Current implementation | Required change |
| --- | --- | --- |
| DM model | `DmThread.report_id` is required and has feedback-only fields | Decode general threads, workflow state, store/topic, assignment, and `viewer_role`. |
| DM service | `DmService` calls legacy `/dm/*` only | Add the `/comms/*` contract and cursor polling. |
| Places | Claimed results open `/tellus/b/{slug}` in a browser | Expose a native Message action for `messaging_enabled` results. |
| Business discovery | No native public-brand model | Fetch `/b/{slug}` only for the Comms sheet’s stores and availability. |
| Inbox | One feedback-DM list | Add consumer/business scopes, filters, agent selection, lifecycle controls, and polling. |
| Team/settings | No inbox permission or opt-in properties | Add the Comms toggle and team inbox access toggle. |
| Billing wall | Unpaid owner is blocked from all brand tabs | Provide a Comms-inbox route without exposing the paid dashboard. |
| Notifications | `dm_message` has an icon but no Comms route; `dm_assignment` is unknown | Add Comms notification handling and in-app thread navigation. |

## 4. Model and service layer

### 4.1 Extend existing models

Update `platforms/ios/TellUs/Models/DmModels.swift`.

- Add string-backed, forward-compatible `DmKind`, `DmTopic`, and `DmStatus`
  types. Unknown values must decode safely rather than break the inbox.
- Change `DmThread.report_id` to `String?`.
- Add `kind`, `topic`, `status`, `store_id`, `store_name`, `store_city`,
  `assigned_member_id`, `assigned_member_name`, `viewer_role`,
  `first_brand_response_at`, and `closed_at`.
- Add `client_message_id` to the send request. UUIDs are strings in Swift and
  use `UUID().uuidString` when composing.
- Add `CommsStartRequest`, `CommsStartResponse`, `InboxBrand`,
  `MessagingStore`, and a simple `{ enabled: Bool }` request type.

Compatibility: decode backend fields defensively. The app may encounter older
feedback-DM data during staged deployment, while all new `/comms/threads`
responses should provide the expanded shape.

Update the existing parity fixtures in
`platforms/ios/TellUs/Tests/ParityModelDecodeTests.swift` accordingly.

### 4.2 Extend discovery and brand-admin models

Update these files:

- `Models/PlaceModels.swift`: add `messaging_enabled` to `PlaceSearchResult`.
- Add a `PublicBrandPage` response model containing `slug`, `brand_name`,
  `claimed`, `messaging_enabled`, and `[MessagingStore]`. Keep it deliberately
  narrower than a full review-page model because Comms only needs availability
  and location context.
- `Models/BrandAdminModels.swift`: add `messaging_enabled` to `Brand` and
  `can_manage_inbox` to `BrandTeamMember`.

### 4.3 Evolve `DmService`

Keep the existing singleton in `Services/DmService.swift` to minimize call-site
churn, but make it the unified Comms transport:

- `threads(brandId:kind:status:assigned:limit:offset:)` → `GET /comms/threads`
- `messages(threadId:after:)` → `GET /comms/threads/{id}/messages`
- `send(threadId:body:clientMessageId:)` → `POST /comms/threads/{id}/messages`
- `start(slug:request:)` → `POST /comms/brands/{slug}/threads`
- `inboxBrands()` → `GET /comms/inbox-brands`
- `take`, `assign`, `close`, `block`, and `unblock` → matching `/comms` routes
- `setMessagingEnabled` and `setTeamInboxAccess` → matching `/comms` routes

Build all query strings with `URLComponents` / `URLQueryItem`, not interpolation,
so brand IDs, filters, and message cursor IDs are encoded consistently.

Preserve a clearly named legacy method for opening a feedback conversation:
`openFeedbackThread(reportId:firstBody:clientMessageId:)`. It must send the
required first message body to `POST /feedback/{report_id}/dm`; the current
no-body `openFromReport` call needs correcting as part of this work. Once
opened, load/send the thread through the unified `/comms` methods.

### 4.4 Add `PublicBrandService`

Create `Services/PublicBrandService.swift` with:

```swift
func brand(slug: String) async throws -> PublicBrandPage
```

It calls `GET /b/{slug}` using the existing authenticated `APIClient` path.
The native Comms sheet uses this response to verify the business is still
claimed/enabled and to load the full store list; search results alone do not
contain stores.

## 5. View-model design

### 5.1 `CommsComposerViewModel`

Create `ViewModels/CommsComposerViewModel.swift`.

State:

- `brand`, `selectedStoreID`, `topic`, `body`
- `isLoading`, `isSending`, `error`
- `clientMessageID`, retained across a retry and reset only when the compose
  content changes or a send succeeds

Behavior:

- Fetch `PublicBrandPage` on presentation.
- Refuse the compose form for unclaimed or disabled businesses and show the
  server-compatible unavailable message.
- Preselect the only store. Require an explicit store for multiple locations.
- On success return the created/reused `DmThread` so the caller navigates to
  `DmThreadView`.
- Surface structured `messaging_unavailable`, 409, 422, and rate-limit errors
  as actionable localized copy.

### 5.2 Upgrade `DmThreadsViewModel`

Replace its feedback-only `load()` with a scope-aware inbox model:

```swift
enum InboxScope {
    case consumer
    case business(brandID: String?)
}
```

Add state for:

- `inboxBrands`, `selectedBrandID`
- `kind`, `status`, and `assigned` filters
- loading/polling task ownership

Rules:

- Consumer scope calls `/comms/threads` without `brand_id`.
- A true brand owner may omit `brand_id`.
- An inbox agent selects a brand; auto-select only when exactly one active
  inbox is returned.
- Poll the list every 15 seconds only while the view is onscreen and the app is
  active. Cancel the task on disappearance.

### 5.3 Upgrade `DmThreadViewModel`

Use `thread.viewer_role`, not `AppState.account.account_type`, for bubble and
action authorization. This is essential for consumer-typed inbox agents.

Add:

- `loadInitial()` and `pollDelta()` using `after=messages.last?.id`
- a five-second task cancelled for inactive scenes, closed threads, or view
  disappearance
- `take()`, `assign(memberID:)`, and `close()`
- `canCompose` derived from `blocked == false && status != .closed`
- idempotent send UUID retention while a draft is unchanged
- notification clearing for both `dm_message` and `dm_assignment`

Do not poll by fetching the entire thread history repeatedly. Append only
deduplicated delta messages by ID.

### 5.4 Settings and team view models

- Extend `BrandSettingsViewModel` to update `messaging_enabled` through the
  Comms route. Show it in `BrandSettingsView`.
- Extend `BoardManageViewModel` with `setInboxAccess(memberID:enabled:)`.
  Update the local `BrandTeamMember` after a successful response.
- Keep the UI owner-only. If an owner enables a non-owner inbox member while
  the plan is inactive, display the backend 402 explanation instead of routing
  the entire app to billing.

## 6. SwiftUI and navigation work

### 6.1 Consumer discovery and compose

Update `Views/Consumer/Places/PlacesView.swift`.

- Rename the framing from review-only to “Find a business.”
- When `PlaceSearchResult.messaging_enabled` is true, add a borderless
  `Message` action next to `See reviews`.
- Present `CommsComposerSheet(slug:)`. The sheet loads `PublicBrandPage`, then
  presents location picker, topic picker, freeform text, and the explicit
  no-reservation/no-guarantee note.
- After success, dismiss the sheet and navigate to the returned thread.
- Keep unclaimed Google suggestions as Add & Review only.

The native app has no logged-out Places surface today, so no iOS login-return
URL work is needed in this phase. Authentication remains enforced by the
backend.

### 6.2 Unified Messages UI

Refactor `Views/Shared/Messages/MessagesListView.swift` and
`DmThreadView.swift` rather than adding duplicate screens.

Consumer inbox:

- Rename title/copy to Comms.
- Show Question versus Feedback, topic, store, waiting/closed state, unread
  count, and deep-opened selected thread.

Business inbox:

- Show kind/status filters plus Mine and Unassigned assignment filters.
- Show location/topic and assignee for brand-role viewers.
- Let agents take an unassigned general thread.
- Let a true owner choose an inbox-enabled team member or clear assignment.
- Let either authorized party close a thread.

Do not render `assigned_member_name` or `assigned_member_id` on a consumer
thread, even if a malformed response contains it.

### 6.3 Tab and billing-wall routing

Update these files:

- `Views/Consumer/More/MoreView.swift`: retain `Messages` for the consumer
  inbox and conditionally add `Business Inbox` when `AppState.inboxBrands`
  contains an active inbox.
- `App/AppState.swift`: fetch `DmService.inboxBrands()` for consumer accounts
  after routing, alongside the existing board-moderation lookup. Clear them on
  logout. Do not treat this list as a brand-account requirement.
- `Views/Brand/BrandTabView.swift`: rename the existing Messages tab to
  `Comms` and pass business scope explicitly.
- `Views/Brand/BillingWallView.swift`: add a `Comms inbox` action that presents
  `MessagesListView(scope: .business(brandID: nil))` in a `NavigationStack`.
  This preserves the owner’s free Comms access without reopening other paid
  dashboard surfaces.

### 6.4 Brand controls and notifications

- `Views/Brand/Settings/BrandSettingsView.swift`: add an “Accept Comms
  questions” toggle.
- `Views/Brand/BoardManage/TeamView.swift`: for owners, add an “Inbox access”
  toggle to non-owner members. It is separate from board moderation access.
- `Views/Shared/NotificationsView.swift`: recognize `dm_assignment` and make
  `dm_message` / `dm_assignment` rows navigate to the relevant thread when a
  valid `reference_id` is present. Consumer versus business destination is
  determined from `DmThread.viewer_role` after loading the thread.

## 7. Regression handling

Before changing routes, add a small compose flow for the existing “Message
reporter” control in
`Views/Brand/Feedback/ReportDetailView.swift`. The backend feedback-open route
requires a first message body, so the button must present a sheet/input rather
than issue a bodyless request. This protects the existing feedback-DM feature
while Comms moves the normal inbox to `/comms/threads`.

Keep `MyReviewDetailView`’s `dm_thread_id` navigation working by resolving the
thread from the unified list. If the thread no longer exists or is inaccessible,
show a normal unavailable state rather than an empty conversation.

## 8. Tests and verification

### Unit tests

Add XCTest coverage in `platforms/ios/TellUs/Tests` for:

1. General and feedback `DmThread` decoding, including nullable `report_id`.
2. Consumer payloads with no assignee identity.
3. `PlaceSearchResult.messaging_enabled` decoding.
4. `PublicBrandPage` and multi-store response decoding.
5. Start/send request encoding, including one retained UUID across a retry.
6. One-store auto-selection and multi-store validation in composer helpers.
7. Business-inbox selection rules for zero, one, and multiple inbox brands.
8. Closed/blocked threads disabling the composer.
9. General versus feedback card copy and business-role action availability.
10. Cursor/delta deduplication and polling cancellation behavior.
11. `Brand.messaging_enabled` and `BrandTeamMember.can_manage_inbox` decoding.
12. Legacy feedback-open request includes its required first body.

Make polling and service calls testable by injecting a small protocol into the
Comms view models or by isolating state-transition helpers as pure functions;
do not make XCTest wait on real five- or fifteen-second timers.

### Manual simulator checklist

1. Consumer: search enabled, disabled, unclaimed, one-store, and multi-store
   businesses.
2. Consumer: start/retry a question, receive a business reply, close, block,
   unblock, and verify no compose field after close/block.
3. Owner: enable/disable Comms, respond while paid and unpaid, and assign/take
   a general conversation.
4. Consumer-typed inbox agent: retain consumer Messages, see Business Inbox,
   select among multiple businesses, and never see consumer email.
5. Owner: enable/disable a team member’s inbox permission; verify inactive-plan
   402 behavior.
6. Feedback regression: message an identified reporter from a report and use
   the same resulting thread from both inboxes.
7. Background/foreground: verify no polling while inactive and a safe delta
   refresh on return.

### Build gates

Run from `platforms/ios/TellUs`:

```bash
make generate
make test
make build
```

Then run the existing backend and web Comms suites before release, since iOS
uses the shared API contract.

## 9. Suggested implementation sequence

1. Add API-parity models, fixtures, and service methods with no UI behavior.
2. Refactor the unified thread/list view models and preserve feedback-DM
   behavior, including the required first-message fix.
3. Build the Places-driven native composer and consumer inbox flow.
4. Build business inbox selection, take/assign/close controls, and polling.
5. Add settings/team controls, unpaid-owner billing-wall access, and
   notification routing.
6. Complete tests, simulator QA, and a TestFlight-focused regression pass.

No server migration is required for this branch; the iOS work consumes the
already-merged Comms API.
