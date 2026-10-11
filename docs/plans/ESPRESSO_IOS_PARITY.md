# Espresso iOS parity plan

Draft: October 10, 2026. Source baseline: `main` at `8730b85547fc28acb0e4626f575f257dc06084bd`.

## Direction

Make Espresso on iPhone and iPad a complete way to start work, respond to decisions, follow progress, and use the results. The first release prioritizes **both project agents and the personal Espresso assistant**, as requested. Broader desktop capability parity follows in independently shippable phases.

Keep the existing native iOS application and shared Swift core. Adapt the interaction to a phone and iPad. Keep durable execution on the existing backend/workers and AutoPR runner. Treat remote control of the Mac's bundled Codex runtime as a separate engineering project.

This is a product and implementation plan, not an implementation or a release certification. Findings below describe checked-in source; installed apps and deployed backend versions were not compared. No database migration is specified by this plan. Complete the affected schema/model audit before designing any new query, persistence contract, or migration.

## What exists today

The iOS app is `platforms/desktop/Espresso/WerkiOS/`, target/scheme `WerkiOS` inside `Matcha.xcodeproj`. The Mac target is `Matcha`. The iOS target supports iPhone and iPad with an iOS 17 deployment target; its display name is still **Werk**.

| Capability | Current iOS source | Planned outcome |
|---|---|---|
| Authentication, session restore, networking | Shared services; native login/session lifecycle | Retain and harden foreground/account-switch recovery |
| Channels and DMs | Native lists, chat, replies, reactions, attachments | Preserve; add rich agent messages and links into work |
| Calls and broadcasts | Native views and shared LiveKit services | Verify existing workflows on devices; close gaps later |
| Project access | Project list explicitly filters to `collab` | Expose each supported project type with an appropriate destination |
| Project workspace | Overview, discussion, horizontal board, file links, read-only notes | Touch-friendly task work, uploads/previews, editing and collaboration |
| Ticket detail | Description, priority, column selection, subtask toggles | Create/edit, attachments, notes, history/rounds, review, agent controls |
| AutoPR coding/research/email work | Shared task APIs/models contain controls; iOS ticket UI does not expose them | Queue, hold/unqueue, provide context, read reports/PR links, review results |
| Server agent cards | Models/services already in iOS target | Create/run, inspect result rounds, request revisions, rerun when allowed |
| Private Espresso assistant | Shared ability/message types and service calls; no native entry screen | Full conversation, abilities, questions, confirmations, progress and receipts |
| AI document threads | Shared models/services/view models; no top-level iOS UI | Conversations, generated documents, versions, relevant exports |
| Journals | Shared models/service; no iOS journal UI | Read/write, organization, collaboration; advanced formats in a later phase |
| Email, Calendar, Productivity | Desktop workspaces; no corresponding iOS surfaces | Mobile equivalents, including links from assistant results |
| Home, People, archive, pins, settings | Narrower navigation/account surface | Cross-work activity, directory, organization, server-resolved entitlements |
| Mac windows, split panes, keyboard workflows | Desktop-specific | NavigationStack and sheets on iPhone; adaptive split navigation on iPad |
| Bundled “Research with Codex” | Mac-local process and account-scoped credentials | View published artifacts on iOS first; remote execution needs a separate design |

Important reuse already exists: the actual iOS Sources phase includes `AgentRunModels.swift`, `AssistantModels.swift`, `ChannelModels.swift`, `ChannelsWebSocket.swift`, `ChannelChatViewModel.swift`, and task/project services. However, the `add_ios_target.rb` shared-file list omits some of those newer entries. Re-running that generator without reconciliation can regress membership. The actual iOS Resources phase is empty, and the scheme has no testables. These are foundation tasks, not reasons to start another app.

## Mobile experience

Use five primary destinations, with the final labels validated in the first design pass:

| Destination | Purpose |
|---|---|
| **Activity** | Needs your attention, running work, and recent results; default landing page |
| **Espresso** | Private assistant conversation, New request, abilities and connection status |
| **Projects** | Project list, tasks, discussion, files; create or describe work |
| **Chat** | Channels and direct messages, with calls/broadcasts retained |
| **More** | Threads, Journals, Email, Calendar, To-dos, People, archive and settings as they ship |

An activity item opens its authoritative conversation, ticket or result. Show the project/conversation and execution location where it matters. A phone losing its connection changes the connection indicator, not the recorded outcome of a server job. A genuinely complete cross-project Activity feed is new read-side work; a feed derived from only recently opened projects must be labeled as such during development and is not full parity.

On iPhone, task details use a readable vertical layout with an action bar and expandable details. Replace the six-segment project picker with a compact section menu or suitable tabs. Keep horizontal kanban optional and offer a list. On iPad, use a sidebar plus list/detail layout and keyboard support. Include Dynamic Type, VoiceOver, dark mode and comfortable touch targets from the first milestone.

Three critical journeys:

1. **Project work:** describe/create a ticket → review its draft → start an eligible agent/AutoPR run → follow status → open report or PR → add context, request changes, or approve the ticket result.
2. **Personal assistant:** ask Espresso → see progress → answer a question or review a held action → see the resulting answer/receipt → open its email, calendar event, source or artifact.
3. **Away from the app:** start on Mac or phone → background/terminate iOS → receive a meaningful alert → authenticate if needed → reopen the exact item with current server state.

Ticket approval must remain distinct from GitHub PR approval, merge and deployment. Likewise, assistant confirmation, staged outreach Send, and a ticket's review decision need separate labels and server operations.

## Delivery sequence

### Phase 0 — Establish a reliable shared baseline

Deliverables:

- Build the current iOS and Mac targets, capture existing failures, and freeze a capability checklist against the current Mac UI.
- Reconcile real Xcode membership with the generator; include required assets/resources and add an iOS test target. Preserve the existing bundle identity, keychain/session identity and push topic while updating user-visible branding to Espresso.
- Add an `espresso-ios` build entry to `scripts/xcode-build.sh` and an iOS simulator gate to CI. Today, the `espresso` entry builds only the Mac scheme.
- Read server entitlements (`plan`, `features`, `workspace`, quotas) for new agent surfaces rather than deriving access from iOS's legacy `isPlusActive` boolean. Preserve server authority and distinguish unknown/unavailable entitlement data from a confirmed denial.
- Define typed navigation targets for assistant conversation/run/prompt, project/task/result, and later thread/journal/email/event. Retain pending destinations through login and reject inaccessible or wrong-account targets.
- Audit the complete affected models/schema and producer/consumer paths before adding Activity queries. Determine the minimum bounded, authorized read interface for cross-project work and pending decisions; preserve personal versus collaborator visibility.

Exit: both targets build; iOS tests execute; returning users keep their account identity; eligible and ineligible account fixtures produce the correct navigation/actions. Asset presence and push provisioning are explicitly checked.

### Phase 1 — Complete agent workflows in the foreground

**Personal assistant**

- Add a native Espresso screen using the existing private-channel endpoint and channel transport. Use the existing backend eligibility rule: the assistant belongs to eligible personal Espresso workspaces, not all business workspaces. Subscription plan names do not override workspace eligibility.
- Render `agent_progress`, `agent_result`, `agent_receipt` and `agent_card_prompt`, plus the existing agent-card result/receipt forms. Reuse shared decoding and lifecycle logic; keep AppKit out of iOS presentation.
- Implement questions and frozen-action previews with owner, expiry and resolution states. Send quick replies as replies to the exact prompt message, as the desktop does.
- Add abilities/disclosures, enable/disable actions, Google connection/reconnection, quota states, and explicit dry-run receipts. Provide a usable route for any required setup before exposing an acting capability as ready.
- Add a typed wrapper for assistant run detail. Do not reuse the card-run decoder unchanged: card runs expect fields such as `round`, while assistant run detail returns a different shape and v2 result.

**Project agents**

- Upgrade mobile ticket detail with task creation/editing, AI draft review, notes, attachments, checklist, review history/rounds and result preview.
- Add supported AutoPR controls: Run now, Hold/Unqueue, additional context, and model/effort selection where offered. Show watched-board/capability restrictions and queued/claimed/held/blocked states.
- Add server-agent card creation/results/rerun, source links and requests for revision. Preserve the distinction between a server agent card and an AutoPR research/coding/email ticket.
- Add ticket Approve and Request changes through their dedicated endpoints; add staged outreach with full draft review and the server's `retryable`/`closable` controls.
- Make task links in chat navigable, and make reports, images, PDFs and Markdown readable in the app with share/export where appropriate. Open PR links through a safe browser route.

Exit: each of the first two critical journeys works on iPhone and iPad. Work initiated on Mac is visible and actionable on iOS under the same permissions; the reverse is also true. Unknown result blocks preserve the rest of the answer, and unknown action payloads do not become actionable buttons.

### Phase 2 — Make it dependable when the phone is away

- Implement the scoped Activity read interface agreed in Phase 0, including pagination and explicit source/status distinctions. Reuse existing task/history/run/prompt records; do not invent one universal persisted job state merely to drive a screen.
- Reconcile on foreground, reconnect and push tap: refresh authoritative history, prompt status and active-run detail before restoring actionable controls. Avoid one poll per task or loading every project bundle for the dashboard.
- Preserve ordinary text drafts and run/request identifiers across interruption. Do not automatically replay an approval, external send, or uncertain create after a network timeout. Recover the recorded outcome first; reuse existing idempotency keys where supported.
- Verify and fill notification producers for needs-input, held decisions, results and failures. Existing APNs registration and socket events do not by themselves prove agent alerts are delivered. Send minimal identifiers, deduplicate events and respect privacy/preferences.
- Support cold-start push routing, expired sessions, revoked project access, account switching and denied notification permission. Keep decision-making inside the authenticated app for the first release.
- Stop foreground polling when inactive; leave the durable agent job on its execution host. Test actual device suspension and termination.

Exit: start on one device, lock or terminate the phone, respond from another device, and reopen without duplicate work or stale actionable approvals. Results remain discoverable with notifications disabled. The Activity list includes all authorized work within its documented scope.

**First release milestone: Phases 0–2.** Both requested agent families must pass the foreground and recovery journeys before calling the release complete.

### Phase 3 — Bring everyday desktop work to mobile

- AI Threads: list/create, chat, server-provided model choices, supported attachments, generated content, version history and exports.
- Email: connect, browse, reply, AI actions, create a ticket from email, and review calendar suggestions.
- Calendar and Productivity: agenda first on iPhone, event CRUD, dated to-dos, then week/month views and Google calendar visibility. Preserve IANA timezone, all-day/date-only and DST semantics.
- Journals: browse, organize, create/edit entries, basic formatting, collaboration and search.
- Projects: expose remaining types with intentional destinations; add file upload/preview/organization and collaborator management.
- Home/People, notifications, archive/pins, account/appearance settings and entitlement/quota visibility.

Exit: a desktop-created thread, journal, email-derived task, event and to-do can be continued on iOS and reflected back on Mac. A supported assistant result always has a working mobile destination.

### Phase 4 — Close advanced workflow gaps

Complete a per-action checklist for presentation/blog/recruiting/discipline and general/collab projects, richer document/journal editing, comments, revisions, screenplay/novel workflows, and exports. Validate channel discovery/member administration, call and broadcast behavior, and accessibility/device performance against desktop capabilities. Prioritize advanced layout on iPad while keeping core actions usable on iPhone.

Exit: every desktop capability is recorded as implemented on iOS, adapted for mobile, or explicitly deferred with a reason and acceptance criteria. Reconcile this inventory at each release so new Mac features do not silently widen the gap.

### Separate track — Phone control of Mac-local Codex

The Mac currently launches a bundled helper and stores its managed credentials in a Mac-local per-user namespace. No remote-control service was established in this planning inspection.

First ship iOS access to research reports already published into shared projects. If running that exact Mac runtime from iOS is required, design device pairing, authenticated command delivery, capability advertisement, host availability, durable job identity, permission revocation, result/event transport and crash recovery. Keep credentials on the execution host. A Mac that is offline/asleep must not appear ready to execute.

Estimate and validate this separately after the existing local integration's release limitations are resolved. Server-agent and AutoPR support must not depend on this track.

## Existing contracts and additional work

| Workflow | Existing contract to reuse | Additional mobile/backend work |
|---|---|---|
| Open assistant | `POST /matcha-work/assistant/channel` | Native entry and eligibility/empty/error states |
| Assistant abilities | `GET /assistant/abilities`, `PUT/DELETE /assistant/abilities/{key}` under `/matcha-work` | Disclosure/settings UI, Google return path |
| Assistant run detail | `GET /matcha-work/assistant/runs/{run_id}` | Distinct Swift detail model/service; recovery fetch |
| Prompt answer | Normal channel reply to prompt; `agent_card_prompt_updated` | Correct reply binding, preview, expired/resolved/owner states |
| Live progress | `agent_run_progress` and persisted history overlay | Native rendering and refresh after missed events |
| Agent-card results/rerun | `GET/POST /matcha-work/projects/{p}/tasks/{t}/agent-runs` | Task result view and eligible rerun controls |
| Ticket drafting | `POST /projects/{p}/tasks/agent-draft`, GET by run id; existing one-shot fallback | Expose durable request/run identity outside an uninterrupted polling function |
| Ticket review | Dedicated `/approve` and `/reject` task operations | Focused action sheets and current-state refresh |
| AutoPR | Existing `/autopr/run-now`, `/autopr/unqueue`, context and staged-action APIs | Native controls, exact status wording, reports/PR presentation |
| Activity and pending decisions | Records exist across several surfaces; inspected assistant router offers individual-run detail | New or extended authorized, bounded read aggregation after the schema/contract audit |
| Cancellation | Backend-specific; no general assistant cancel endpoint in inspected router | Do not show a universal Stop button. Specify cooperative cancellation separately if required |
| Push | iOS registration, delegate and project/channel/DM routing exist | Agent event delivery verification/additions; run/prompt routing and recovery |

Keep approval behavior aligned with each backend. The personal assistant's policy may allow already-authorized grounded actions without a new prompt; only held actions should require its confirmation UI. Staged outreach still requires approval of each exact draft. AutoPR Hold prevents future pickup and can coexist with an older run finishing. An uncertain external action remains uncertain until reconciled; it is not a safe automatic retry.

For OAuth, adapt the existing Google flow to a system authentication session with a supported app return path and server-side state validation. Audit the existing web callback before choosing callback routing. Apple documents [ASWebAuthenticationSession](https://developer.apple.com/documentation/authenticationservices/aswebauthenticationsession) for this purpose. For agent execution, design around suspension rather than a permanently connected phone: see Apple's [background execution guidance](https://developer.apple.com/documentation/uikit/extending-your-app-s-background-execution-time).

## Suggested implementation slices and validation

| Slice | Scope | Depends on |
|---|---|---|
| 1 | Baseline build, generator/membership/resources, branding, iOS test target and CI | — |
| 2 | Shared entitlements, typed navigation, platform-neutral agent presentation state | 1 |
| 3 | Personal assistant conversation, cards, abilities and OAuth/setup destinations | 2 |
| 4 | Project ticket control, agent/AutoPR workflows, artifact viewer and review actions | 2 |
| 5 | Activity aggregation, notifications, durable resume and cross-device reconciliation | 3, 4 |
| 6 | Device acceptance, performance/accessibility, distribution configuration and TestFlight candidate | 5 |

Keep these as independently reviewable changes; split a slice further where backend changes or signing/release configuration need separate validation. Estimate after Slice 1's builds and Phase 0's Activity/API inventory; calendar promises before those checks would be speculative.

Validation for implementation:

- Baseline iOS build: `xcodebuild -project platforms/desktop/Espresso/Matcha.xcodeproj -scheme WerkiOS -configuration Debug -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build`.
- Mac regression build: `./scripts/xcode-build.sh espresso build`. Run the new iOS tests on an installed concrete simulator once its test target exists.
- Shared decoding/state fixtures: all known result/prompt/receipt variants; v1/v2; missing or new fields; empty/large/Unicode content; expired prompts; unknown action types; terminal versus disconnected states.
- Backend changes: focused existing suites under `server/tests/agent_runtime/`, `server/tests/agent_card/`, `server/tests/project_agent/`, and the relevant AutoPR/push tests, plus tests for any new aggregation/notification path. No live database mutation tests or migrations during planning; follow repository validation rules when implementing.
- Device scenarios: iPhone and iPad; foreground/background/termination; missed and duplicate pushes; token expiry; lost response after a submit; conflicting decisions from Mac and iOS; revoked access/ability; account switch; quota exhaustion; missing Google connection; dry run; worker failure; offline runner; failed and uncertain outreach.
- First-release acceptance requires two complete demonstrations: an eligible project agent ticket from creation to reviewed result, and a personal-assistant request through a question/held action to its recorded outcome. Repeat recovery from an app kill in both, with external providers mocked or explicit test fixtures.

Planning checks completed: source/navigation/service/target inspection; Xcode 26.6 availability; `plutil -lint` passed for the project, iOS Info.plist and entitlements. Ruby's `xcodeproj` gem was unavailable in the system Ruby, so target membership was inspected read-only through `plutil` JSON instead. No simulator build, test suite, installed-app comparison, live API call, APNs delivery, device acceptance or release-signing validation was performed for this document.

## Source map

- iOS shell and session: `platforms/desktop/Espresso/WerkiOS/{WerkApp.swift,App/AppState.swift,Views/MainTabView.swift}`.
- Current project scope: `WerkiOS/ViewModels/ProjectsListViewModel.swift`, `WerkiOS/Views/Projects/CollabProjectView.swift` under that same Espresso project.
- Desktop capability entry points: `Espresso/App/DetailPanes.swift`, `Espresso/Views/MatchaWork/AssistantView.swift`, `Espresso/Views/MatchaWork/TaskViewer/`, and Email/Calendar/Productivity/Journals views.
- Shared contracts: `Espresso/Models/ChannelModels.swift`, `Espresso/Models/MatchaWork/{AgentRunModels,AssistantModels,ProjectTaskModels,BillingUsageModels}.swift`, `Espresso/Services/MatchaWorkService*.swift`.
- Runtime rules: `server/app/matcha/services/matcha_work/agent_runtime/CLAUDE.md`; endpoints in `server/app/matcha/routes/matcha_work/{assistant,agent_cards,project_agent_runs,tasks}.py`.
- AutoPR semantics: `apps/msandbox/docs/KANBAN_AUTOPR.md`; desktop task services and ticket action/review/outreach views.
- Mac-local execution: `platforms/desktop/Espresso/CodexRuntime/README.md` and `Espresso/Services/CodexResearchCoordinator.swift`.
- Build wiring: `platforms/desktop/Espresso/Matcha.xcodeproj/`, `platforms/desktop/Espresso/scripts/add_ios_target.rb`, `scripts/xcode-build.sh`, `.github/workflows/ci.yml`.

The pre-existing change to `platforms/desktop/Espresso/build/appstore/ExportOptions.plist` and untracked `oceaneca-plan.html` were left intact.
