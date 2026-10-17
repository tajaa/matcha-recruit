# Espresso web task recaps — mechanical technical plan

Status: implemented for review; rollout remains disabled. Operational steps and
validation limits are in [the recap runbook](../ops/ESPRESSO_RECAPS.md).

Prepared: 2026-10-17. Repository baseline: `d0b8e4d6eb1115d145c5d048913d9bf244651110`.
The implementation branch starts from main at `2faec1812bfd6338acf3c58bc76ddb88b34d7dda`.
Main added the Tasks web interface after planning; recap links now integrate with
that interface as well as Assistant and Job search. The original design below
records intent; the runbook records the shipped limits and remaining rollout gates.

## 1. Outcome and scope

An Espresso agentic request produces a private, concise video showing meaningful steps and their outcomes. A thirty-minute job should normally produce a 60–120 second recap. Short requests produce shorter recaps.

The release scope is personal Espresso's agentic system:

| Surface | Evidence shown |
|---|---|
| Job search | Criteria, discovery, screening, verified posting facts, ranking, drafted approaches |
| Apartment/research search | Constraints, listings checked, price/availability evidence, filtering, ranked results |
| Calendar management | Relevant availability, proposed changes, confirmed changes, outstanding confirmations |
| Email management | Selected-message counts, draft/organization actions, confirmed outcomes |

Delivery is Espresso web plus email to the requesting account. The agent may continue with the user's browser closed. Native macOS recording, project-board/AutoPR work, narration, public sharing, continuous whole-job recording, and an entire research Tasks web UI are outside this release.

The feature observes existing execution. It must never repeat an agent action, search, email send, calendar mutation, or booking to obtain footage. Existing consent, policy, allowance, and commit-mode decisions remain authoritative.

## 2. Decisions to implement

1. One recap belongs to one logical user request, including its confirmation continuations and explicitly launched child searches. Internal model calls and worker batches do not each create recaps.
2. Collect immutable, bounded event snapshots during execution. Use short footage from real browser activity where available; use rendered result cards for API work.
3. Use deterministic selection and captions. Initial rendering requires no additional model calls.
4. Assemble in a dedicated media worker on separate compute, with concurrency one initially. A separate queue alone does not isolate CPU or memory on the existing application host.
5. Export H.264 MP4, 1920×1080, 15 fps, silent, with `yuv420p`, square pixels, and `+faststart`. Verify actual encoder availability in the production image before choosing the final preset.
6. Target 60–120 seconds for long jobs; hard cap 120 seconds. Never pad a small action to meet a duration target.
7. Store source media and final artifacts privately. Email stable authenticated Espresso links, never a permanent public object URL.
8. Give recaps their own state machine, retry budget, retention, and email-delivery records. Media failures cannot make an already completed task fail.
9. Roll out behind a disabled server flag and explicit per-account opt-in. Video creation and recap email have separate preferences.
10. Scope all entry points to personal Espresso ownership, including direct API calls. Serving the shared `/work` route tree is not authorization.

## 3. Existing integration points and constraints

| Existing file | Current behavior and implication |
|---|---|
| [agent_runtime/runner.py](../../server/app/matcha/services/matcha_work/agent_runtime/runner.py) | Shared loop for assistant and search model phases. Read/draft steps and commit claims/resolutions already have distinct outcomes. Add optional observation; do not introduce a second agent loop. |
| [project_agent/store.py](../../server/app/matcha/services/matcha_work/project_agent/store.py) | `record_step`, `claim_step`, `resolve_step`, and `mark_run` persist agent outcomes. A commit is claimed before its external call. Preserve this ordering. |
| [agent_runtime/assistant.py](../../server/app/matcha/services/matcha_work/agent_runtime/assistant.py) | `_deliver` marks question/held-action runs `done`. Run status alone cannot close a recap. `receipt_view` supplies a starting point for safe action summaries, but is not itself a recap privacy filter. |
| [agent_runtime/chat_entry.py](../../server/app/matcha/services/matcha_work/agent_runtime/chat_entry.py), [prompts.py](../../server/app/matcha/services/matcha_work/agent_runtime/prompts.py) | Confirmation replies carry `resume_prompt_id`; open-ended question replies do not currently propagate that same field. Both paths need explicit recap lineage. |
| [agent_runtime/phase_run.py](../../server/app/matcha/services/matcha_work/agent_runtime/phase_run.py) | Every search model phase creates another run. Attach it to the source's active recap; do not create a new root. |
| [agent_runtime/chain.py](../../server/app/matcha/services/matcha_work/agent_runtime/chain.py) | Owns token-fenced claims, advancement, retries, and reconciliation. Phase batches can advance without changing phase names. Capture meaningful accepted outcomes, not every progress update. |
| [agent_tasks/orchestrator.py](../../server/app/matcha/services/matcha_work/agent_tasks/orchestrator.py), [service.py](../../server/app/matcha/services/matcha_work/agent_tasks/service.py) | Research has real rounds. `close_round` settles the current round once; `done` can include useful partial results. Deletion tombstones tasks and blanks their data. |
| [job_search/orchestrator.py](../../server/app/matcha/services/matcha_work/job_search/orchestrator.py), [service.py](../../server/app/matcha/services/matcha_work/job_search/service.py) | Job searches have no equivalent round counter. Widen/redraft can move a resting search back into a live state. Explicit execution generations are necessary. |
| [agent_tasks/job_tasks.py](../../server/app/matcha/services/matcha_work/agent_tasks/job_tasks.py) | A job-search Tasks pointer has stored status `done` even while the real search runs. Its `completed_at` is a one-time notification marker. Neither is the recap lifecycle. |
| [browser/session.py](../../server/app/matcha/services/matcha_work/browser/session.py), [abilities/screenshots.py](../../server/app/matcha/services/matcha_work/agent_runtime/abilities/screenshots.py) | Guarded Chromium sessions already exist. Current viewport is 1440×900; stored public page screenshots are reduced to at most 1200 px. New private capture must not silently reuse the public screenshot path or claim those images are native 1080p. |
| [agent_tasks/mail.py](../../server/app/matcha/services/matcha_work/agent_tasks/mail.py) | Research/job completion emails already exist. Research rounds under 60 seconds currently skip email. Integrate delivery ownership so recap-enabled searches do not get duplicate completion emails. |
| [email/client.py](../../server/app/core/services/email/client.py) | Existing sender returns a boolean and falls back from Gmail to MailerSend. It cannot establish exactly-once delivery or distinguish all ambiguous sends. Add an opt-in structured transport result for recap delivery. |
| [storage.py](../../server/app/core/services/storage.py) | Existing private helper falls back to the ordinary bucket, and uploads take complete byte strings. Recaps need an explicit private bucket check and bounded file-stream uploads. |
| [WorkRouteTree.tsx](../../client/src/work/routes/WorkRouteTree.tsx) | Web has Assistant and Job search; no general research Tasks page in this baseline. A dedicated recap route avoids coupling this work to a Tasks UI port. |
| [AgentCardMessage.tsx](../../client/src/work/components/channels/AgentCardMessage.tsx), [SearchDetail.tsx](../../client/src/work/pages/JobSearch/SearchDetail.tsx) | Existing places to expose recap preparation/playback. Add optional metadata, leaving current result contracts intact. |
| [server/Dockerfile](../../server/Dockerfile), [docker-compose.yml](../../docker-compose.yml) | Backend image includes FFmpeg and Playwright 1.62.0/Chromium. Agent worker has one slot and an 800 MB limit; comments describe a tightly sized application host. These are repository observations, not a live capacity audit. |

Schema sources inspected: `espressoagent01`, `agentcard01`, `agentrt01`, `mwjobs01`, `agenttask01`, and `agenttask05`; request models: `models/matcha_work/agent_tasks.py` and `job_search.py`. Existing run/step outcomes, source ownership, round semantics, and tombstones must remain compatible.

## 4. Logical identity and completion

### 4.1 Roots and source bindings

Create root identity from server-owned records only:

| Entry | Stable root key |
|---|---|
| Standalone private assistant request | `assistant:<initial_run_uuid>` |
| Research task started directly | `task_round:<round_uuid>` |
| Job search started directly | `job_search:<search_uuid>:<generation>` |

Enforce uniqueness on `(company_id, owner_user_id, root_key)`. Never accept a root key, owner, recap ID, source generation, or S3 key from model arguments or ordinary client create bodies.

Pass an optional, trusted recap scope through `RunContext` and internal task/search creation calls. Scope includes recap ID, owner/company, source ID/generation, and the current execution token. Older callers default to no scope.

At task/search creation, bind the new source before dispatching its worker. `abilities/tasks._start` and `_follow_up`, intake-form submission, and direct REST creation must all reach the same binding helper. Task intake uses the originating prompt/run to recover lineage even when it creates a task without a new assistant run.

`phase_run._insert_run` attaches the new model run to the already-bound search source. A root assistant that launches a child search can finish its conversational response while the recap remains collecting.

If one request launches several searches, all are sources of one recap. If it also performs an email/calendar action, that evidence stays in the same recap. New unrelated chat messages create new roots; do not group by conversation alone.

### 4.2 Job-search execution generations

Add `mw_job_searches.recap_generation INTEGER NOT NULL DEFAULT 0 CHECK (recap_generation >= 0)` as an additive migration. Zero means legacy/untracked.

- Allocate the first positive generation when an enabled new search starts.
- Increment under the existing source-row lock when an accepted user operation restarts a resting search (`widen`, `requeue_approach`, and any alternate restart discovered during implementation).
- Retries, worker restarts, batches, and token changes retain the generation.
- A duplicate operation refused by current domain guards allocates nothing.
- A pure weight rerank without a live execution cycle produces an action event in its invoking assistant recap, or no automatic recap when invoked directly in v1.
- Record generation with every source binding and capture request. An older worker cannot attach evidence to the newer generation.

Do not reuse the Tasks pointer's `completed_at` or change its existing one-time notification meaning. New generation recaps use their own delivery identity.

### 4.3 Continuations and terminal rules

Derive completion from persisted semantic outcomes:

| Situation | Recap behavior |
|---|---|
| Assistant result with no live child work | Eligible for finalization |
| Assistant question or held action | Wait for the referenced prompt; no render or completion email |
| Confirmed/open-ended reply | Attach new run to the original recap through the claimed prompt |
| User declines confirmation | Record declined action; close that source without labeling it successful |
| Child search still running | Continue collecting |
| Research waiting for input | Wait; do not settle its open round |
| Source completes with partial findings | Render useful findings and an explicit partial-result notice |
| Failed source with no useful evidence | Skip automatic video; preserve ordinary failure notification |
| Cancelled source | Stop capture; show completed actions/results only if useful, with cancellation label |
| Source deleted | Revoke and delete the entire containing recap in v1; its manifest may include that source's private data |

No logical request completes until all its bound sources are terminal and no linked prompt is open. Mirror existing prompt expiration; apply a seven-day recap waiting cap without cancelling underlying tasks. Finalization freezes an immutable manifest. A new follow-up after closure receives a new root/version.

## 5. Event and snapshot contracts

Add a versioned, Pydantic-validated `RecapEventV1`. Its JSON representation is also the worker transport contract:

```json
{
  "schema_version": 1,
  "recap_id": "uuid",
  "source_id": "uuid",
  "event_key": "step:<run_uuid>:<seq>:resolved",
  "kind": "action_resolved",
  "occurred_at": "2026-10-17T19:00:00Z",
  "phase": "email.organize",
  "source_order": 1,
  "step_order": 4,
  "outcome": "confirmed",
  "title": "Archived selected messages",
  "facts": [{"label": "Messages", "value": "12"}],
  "artifact_ids": [],
  "source_refs": [{"kind": "agent_step", "id": "uuid"}]
}
```

Event kinds: `request`, `phase_completed`, `action_resolved`, `question_opened`, `question_resolved`, `result`, `warning`.
Outcomes: `observed`, `drafted`, `confirmed`, `dry_run`, `held`, `declined`, `failed`, `unknown`, `partial`, `cancelled`.

Rules:

- Tool step `ok` alone is not evidence of a live commit: dry runs also produce `ok`. Snapshot the resolved mode and receipt outcome before reducing it for presentation.
- Persist step/phase IDs, source generation, and fencing token separately from display fields. Worker payloads carry identifiers, not email bodies or complete manifests.
- Step event keys use persisted run ID/sequence/outcome revision. Phase keys use source generation plus the accepted dispatch token; the same phase can have several accepted batches.
- Unique `(recap_id, event_key)` makes repeated observation a no-op. Never dedupe real repeated work solely by phase name or timestamp.
- Order by causal source/phase ordering and persisted step sequence, with occurrence time and ID as stable tie-breakers. Parallel sources are labeled; do not invent a sequential dependency between them.
- An old generation/token can upload a temporary asset but cannot attach it to an accepted event or publish a result.
- Preserve numeric units, currency, evidence status, timezone, and actual action outcome. Display calendar time using the saved IANA timezone; retain UTC instants.
- No model transcript, hidden reasoning, arbitrary HTML, tool argument dump, credential, raw email body, or unrelated calendar event enters the snapshot.
- Bound each event to 16 KiB UTF-8 after serialization; title 160 characters, at most six facts of 300 characters, at most two media references. Measure byte limits after encoding, not with character counts. Truncate display text at grapheme boundaries and show an ellipsis.
- Keep at most 128 detailed events / 1 MiB of event JSON per recap, reserving space for final results and warnings. Coalesce additional repetitive events into bounded counters. Never displace a consequential failed/unknown action with a decorative scene.

The immutable render manifest contains schema/template versions, scene order, selected snapshot values, source timestamps, media checksums, and output settings. Hash its canonical serialization. Store no signed URLs in it.

### 5.1 Adapters

| Adapter | Allowed material | Source of truth |
|---|---|---|
| Research | Brief constraints, verified/unconfirmed fact labels, counts, ranked top picks, selected listing photos/page captures | Accepted phase outputs, round summary, validated item views |
| Jobs | Search criteria, posting-derived pay with disclosure status, screened/ranked counts, top jobs, approach status | Search/lead views and accepted phase outcomes |
| Calendar | Selected event title, relevant time window, timezone, requested change, confirmed receipt | Calendar tool outputs and resolved step/receipt |
| Email | Counts, explicitly selected subject/sender where relevant, draft/label/archive/send status | Tool-specific allowlisted outputs and resolved step/receipt |

Email bodies, BCC lists, complete recipient lists, attachments, résumés, and unrelated event descriptions are excluded from default recap material. Never copy `receipt_view` or audit JSON wholesale: they can contain more than the video needs. Keep accurate labels for drafts, dry runs, partial work, and unknown outcomes.

## 6. Proposed persistence

Create one additive Alembic revision after inspecting the current migration graph. Do not preselect a stale `down_revision`. No backfill of historic footage or old requests.

### 6.1 `mw_agent_recap_preferences`

- `(company_id, user_id)` primary key; owner foreign keys.
- `enabled BOOLEAN NOT NULL DEFAULT FALSE`, `email_enabled BOOLEAN NOT NULL DEFAULT FALSE`.
- `settings_version`, `updated_at`.
- Missing row means disabled. Enabling affects new requests only. Disabling stops collection/rendering of unfinished recaps; prior completed recaps remain until explicit deletion/expiry.

### 6.2 `mw_agent_recaps`

- `id UUID` primary key; `company_id`, `owner_user_id`, `root_key`, `origin_channel_id`, `origin_message_id`.
- `state` with the state-machine values below; `outcome`; bounded `title`.
- `snapshot_version`, `template_version`, `manifest JSONB`, `manifest_sha256`.
- `render_attempts`, `render_token`, `lease_until`, `next_attempt_at`, `last_error_code`.
- `manual_retry_request_id` nullable UUID, set once; `manual_retry_requested_at`. One explicit retry grant is allowed after the automatic budget, for at most four render attempts over the recap's lifetime. Retain the request ID so a repeated HTTP request cannot grant another attempt.
- `capture_windows_reserved`, `capture_bytes_reserved`, and `capture_bytes_stored`, updated under the recap-row lock. Pending event capture tokens own reservations; expiry releases abandoned reservations.
- `output_manifest JSONB` containing only validated private object keys, checksum, MIME type, duration, dimensions, bytes, and chapter offsets.
- `created_at`, `updated_at`, `source_completed_at`, `finalize_after`, `ready_at`, `expires_at`, `deleted_at`.
- Unique `(company_id, owner_user_id, root_key)`; owner listing index; partial indexes for pending retries, collecting/waiting reconciliation, and expiry.
- All byte/duration/count values nonnegative; status/manifest combinations checked where practical. JSON budgets validated in application code and with database byte-size constraints.

### 6.3 `mw_agent_recap_sources`

- `id`, `recap_id`, `kind`, `role`, `generation`, `source_order`, `semantic_state`.
- Typed nullable foreign keys: `run_id`, `task_round_id`, `job_search_id`. Exactly one is populated; `kind` must agree. Use partial unique indexes per source type, including generation for job searches.
- `role`: `root`, `continuation`, `phase`, `child`; `semantic_state`: `live`, `waiting`, `terminal`.
- `completion_mail_owner`: `legacy`, `recap`, `none`, assigned once. New job generations can have a recap without changing the job pointer's original notification marker.
- Source IDs are bound only after checking user/company equality. Phase runs and source-level rows may both bind to the same recap.
- Source-row deletion cascades its bindings; source deletion services must first tombstone affected recaps and persist cleanup work. An orphan sweep is the backstop, not the primary privacy mechanism.

### 6.4 `mw_agent_recap_events`

- `id`, `recap_id`, `source_id`, `event_key`, `kind`, `outcome`, `phase`, ordering fields, `occurred_at`, bounded `snapshot JSONB`.
- `capture_token`, `asset_manifest JSONB` (at most two assets), `capture_state`: `none`, `pending`, `ready`, `missing`.
- Asset entries contain generated ID/key, content type, dimensions/duration, byte count, checksum, and upload timestamp. No arbitrary remote URL or path.
- Unique `(recap_id, event_key)`; ordered-read index; pending-capture index.
- Resolved event payloads are immutable. A correction creates a new revision that explicitly supersedes an earlier event; a frozen video does not silently change.

### 6.5 `mw_agent_recap_deliveries`

- `id`, `recap_id`, `purpose='completion'`, `state`, `not_before`, `deadline_at`.
- States: `pending`, `sending`, `retry_wait`, `sent`, `unknown`, `suppressed`, `failed`. Only a definite non-delivery can move to `retry_wait`; an expired `sending` lease becomes `unknown`.
- `template_version`, bounded frozen summary payload, `attempts`, `claim_token`, `lease_until`.
- `provider`, `provider_message_id`, `sent_at`, `last_error_code`.
- Unique `(recap_id, purpose)`; due-delivery index.
- Recipient is resolved from the owner's current account at send time; never from task content. Capture the actual recipient only in the existing restricted delivery/audit path.

### 6.6 `mw_agent_recap_cleanup_jobs`

- `id`, `bucket`, generated `prefix`, `not_before`, `state`, `attempts`, `next_attempt_at`, `last_error_code`.
- Independent of a cascading recap FK, so account/source removal cannot erase the only deletion instruction.
- Unique `(bucket, prefix)`; due-job index. Cleanup is idempotent, handles missing objects, and never accepts client-supplied prefixes.
- Events/deliveries cascade with recap metadata after cleanup policy permits. S3 lifecycle and orphan-prefix inventory cover deletion of an entire account/company when database cascades occur outside normal services.

## 7. Durable observation without changing task success

Implement optional recap helpers using `connection_or_direct()` / caller-provided connections. No database pool assumptions in workers.

1. On request/source creation, decide eligibility and establish the root/binding inside the source transaction, before worker dispatch. If initial root registration fails, roll back its savepoint, leave the source on the legacy delivery path, and continue the authorized task. For a child/continuation of an existing root, a binding failure must also fence that root as `skipped` with reason `source_binding_failed` before the child is dispatched; never leave an apparently complete parent video eligible to publish. Persist this fallback in the source transaction. If that transaction cannot commit, use existing source-creation recovery rather than dispatching untracked work. Existing root-owned deliveries remain with their coordinator; the unbound child uses legacy delivery. This exceptional fallback can produce separate ordinary summaries and must be observable.
2. Where a source transaction commits an accepted state change, record the minimal sanitized event in the same transaction using a bounded savepoint. No rendering, upload, network call, or large result scan belongs inside the transaction.
3. In `store.resolve_step`, retain authoritative external-action outcome persistence before optional recap work. An observation failure must never cause a provider action to be executed again.
4. Extend `ChainSpec` with an optional accepted-outcome observation hook, default `None`. Only the owner whose dispatch token successfully advances can contribute a phase event. Keep terminal notification/network work outside any newly introduced snapshot transaction.
5. Apply the same terminal handling to explicit cancel, stale-run failure, prompt expiry, manual redraft/widen, and deletion paths, not only happy-path `_stopped`.
6. Persist a pending render/delivery row before publishing to Celery. Database state is the durable queue of work; a periodic reconciler repairs lost broker publication.
7. Reconciliation can recover step outcomes from persisted steps and source terminal state. It cannot recreate missing historical browser frames or reconstruct an old phase from mutable current rows. Mark missing evidence, use a clearly final-state snapshot, or omit the scene.

Important limit: media observation is best effort. Existing task/audit durability is authoritative; the recap must explicitly tolerate incomplete visual coverage rather than block the agent or fabricate evidence.

### Required hook coverage

| File/function family | Planned change |
|---|---|
| `agent_runtime/enqueue.enqueue`, `chat_entry.start_run/_answer_prompt`, `prompts` | Create root; carry server-validated continuation lineage for both confirmations and open questions; handle declined/expired prompts. |
| `agent_runtime/context.RunContext`, `phase_run.RunOwner/_insert_run` | Optional recap scope; attach phase runs to existing sources. |
| `agent_runtime/runner.run_tool/commit/post_receipt`, `project_agent/store` | Allowlisted step and receipt snapshots; preserve existing external-action claim/resolve behavior. |
| `agent_runtime/assistant._deliver/report_failure`, `workers/tasks/assistant` | Semantic result/question/held/failure completion; persisted fallback recovery. |
| `agent_runtime/abilities/tasks`, `agent_tasks/enqueue/intake` | Attach child task/round before dispatch, including form-based starts and follow-ups. |
| `agent_tasks/orchestrator/service`, `research/phases/model_phases` | Phase/final snapshots; exact round closure; partial/cancel/delete paths. |
| `job_search/enqueue/orchestrator/service/phases/model_phases/discovery` | Generation lifecycle and accepted phase snapshots; widen/redraft/cancel/delete paths. |
| `agent_tasks/job_tasks` | Separate recap delivery from the pointer's original notification marker. |
| `abilities/calendar`, `abilities/apple_calendar`, `abilities/email` | Typed safe display snapshots of actual outcomes; no new permissions or commits. |
| `browser/session`, `abilities/screenshots`, `workers/tasks/assistant.view_page` | Optional bounded private capture scope, transported through the browser-worker boundary. |

Before editing shared signatures, search and read all consumers, including agent cards and other task owners; optional parameters preserve unmodified callers.

## 8. Browser capture implementation

### 8.1 First spike and selected approach

Use the existing Playwright Chromium page plus a small capture adapter. Verify `Page.startScreencast`/`Page.stopScreencast` against the repository's pinned Chromium, including frame acknowledgement and failure behavior. These are Chromium-specific DevTools capabilities, so feature-detect them.

The first implementation candidate captures bounded JPEG frame sequences using that API and uploads a small clip package. If unavailable, fall back to screenshot checkpoints; do not enable continuous `recordVideo` for the whole job. This fallback still produces a valid recap and must be described as snapshots in its scene metadata.

### 8.2 Capture windows and limits

- Begin immediately before a known meaningful browser action; end after the visible result is available or the window cap is reached.
- Maximum eight seconds/window, ten windows/recap, eight captured frames/second. Output encoding can duplicate frames to reach the standard 15 fps.
- No rolling prebuffer in v1. An unexpected completion cannot produce footage from before capture started; use its result screenshot.
- Capture cannot extend the browser operation's existing deadline. Do not keep a browser open just to make footage longer or launch another browser for an API-only step.
- Bound frame queue to 16 entries; drop excess frames and acknowledge them promptly. Bound source-media bytes to 128 MiB/recap and local job workspace to 256 MiB. Reserve budgets atomically before capture; unused reservations are released.
- Preserve existing navigation/egress, WebRTC, redirect, and download guards. Do not relax the shared browser proxy to render internal recap pages.
- Authenticated email/calendar screens are not captured in v1. Their visuals come from allowlisted cards. Public browser windows are captured only on the approved page/action, never login, payment, or unrelated pages.
- Do not globally change the shared 1440×900 viewport. Native 1080p scene cards frame source footage with aspect-ratio preservation. Improve source capture resolution only if the spike proves it is needed and safe for video-enabled contexts.
- Store source timestamps and actual frame intervals. Fill gaps only inside a selected short scene; never expand a ten-minute idle period into ten minutes of duplicate frames.
- Stop/close capture in `finally`; kill owned subprocess groups on timeouts; release bounded resources even if Chromium crashes.

### 8.3 Upload and attachment

Reserve a generated asset key under the recap's staging prefix before upload. Stream the local file to private S3, verify size/checksum, then attach it with a compare-and-set on recap/source generation and capture token. Upload success followed by a database failure leaves a discoverable orphan for cleanup. A stale/deleted source never becomes publishable merely because its upload completed.

The existing public `images.store_image` path remains for its existing product purpose; private recap captures use the new recap storage adapter.

## 9. Storyboard and rendering

### 9.1 Deterministic storyboard

Input: frozen event/snapshot manifest. Output: at most twelve scenes with explicit durations, captions, provenance, and media IDs.

Priority: request → useful stage outcomes → consequential action results/warnings → final result. Merge repeated discovery/enrichment batches into counts and a representative captured example. Include all consequential unknown/failed actions in a summary scene if separate scenes would exceed the cap.

Use approximately 4 seconds for the request, 4–10 seconds per selected intermediate scene, and 15–20 seconds for final results. Use fewer scenes for short jobs. Preserve reading time by removing low-priority scenes before speeding up text. Keep chronological progression within each source and label parallel work.

Show actual task elapsed time separately from video duration. Mark saved screenshots, captured browser footage, and result cards accurately; a rendered card is a visualization of an outcome, not footage of a click.

### 9.2 Scene renderer

Add a small standalone React render entry under `client/src/work/recaps/render/`, plus `client/recap-render.html` and a dedicated Vite build config. Reuse Espresso visual tokens and pure display formatting where appropriate; do not import live pages, auth state, or network-fetching components.

Expose a typed scene input and a readiness signal after fonts/images settle. Render text through React's ordinary escaping. Include an explicit neutral rendering theme, bounded layout, and fallback for long/Unicode text. Bundle licensed fonts covering expected scripts; test emoji and missing glyph behavior.

Package `dist-recap` with the backend code in a new media-worker image built from the same release. The ordinary backend image currently does not contain this frontend artifact. A digest/version mismatch is a rendering failure, not permission to use arbitrary latest assets.

The renderer serves its static bundle on loopback inside the media worker. Chromium may load that bundle and staged local assets only. It receives validated scene JSON; it has no user login, Google credentials, live application session, or arbitrary navigation target. This isolated trusted renderer is separate from the public web-browsing subsystem.

Render cards to PNG frames; combine those with captured clips in FFmpeg. Normalize input frame rate, timestamps, dimensions, pixel format, and sample aspect ratio. Re-encode once into the final H.264 MP4; do not rely on stream-copy concatenation across mixed media.

### 9.3 Output validation

Use `ffprobe` to verify video stream, codec, 1920×1080 dimensions, duration ≤120 seconds, frame rate, and decodability. Generate a private poster, chapter JSON, and readable text transcript from the same manifest. Run a decode check before publication.

Initial encoding candidate: software H.264, `veryfast`, CRF 23, max rate 4 Mbps, buffer 8 Mbps, 15 fps, `yuv420p`, `+faststart`. Confirm support and quality in the spike; these are proposed settings, not measured capacity claims.

Final file limit: 64 MiB. Permit one lower-bitrate encode within the same overall render deadline if the first exceeds it; otherwise fail the recap with `output_too_large`. No silent resolution downgrade. At 2–4 Mbps, a two-minute video is approximately 30–60 MB before small container overhead; quality and actual sizes require measurement.

Invoke FFmpeg with an argument array, not a shell. Use generated local paths and a fixed filter graph. No untrusted URLs, captions, filenames, or expressions are interpolated into command text. Apply CPU/thread, memory, disk, and wall-clock limits. Reap subprocesses on every exit path.

## 10. Recap state machine and worker protocol

```text
collecting <-> waiting
collecting/waiting -> queued       sources terminal, manifest frozen
collecting/waiting -> skipped      no useful work, opt-out, cap, waiting expiry
queued/rendering -> skipped        opt-out, invalidated lineage; fence active token
queued -> rendering               atomic lease/token claim
rendering -> ready                verified artifacts published by current token
rendering -> queued               safe retry with backoff
rendering -> failed               attempts exhausted or permanent error
failed -> queued                  explicit bounded retry, original assets available
ready -> expired                  retention elapsed
any non-deleted state -> deleted  authorized deletion or source removal
```

All reads deny access to deleted/expired media. Deletion wins against render completion. `skipped` has a structured reason; `failed` never changes the source task outcome.

Planned tasks in `workers/tasks/recaps.py`:

| Task | Queue / behavior |
|---|---|
| `recaps.render(recap_id)` | Dedicated `espresso_recaps_render`; one slot; identifiers only |
| `recaps.reconcile` | Default queue; lightweight sweep every 60 seconds |
| `recaps.deliver(delivery_id)` | Default queue; short claims, bounded email I/O outside DB transactions |
| `recaps.cleanup(cleanup_id)` | Dedicated media queue; bounded S3 deletion batches |

Protocol:

1. Reconciler selects due rows with short `FOR UPDATE SKIP LOCKED` transactions; publishes identifiers after commit. Duplicate publications are harmless.
2. Render claim atomically checks `queued`, due time, enabled settings, active owner, retained sources, and artifact availability; sets a fresh token and six-minute lease.
3. Worker stages inputs locally, renders, validates, uploads immutable output keys under that token, then conditionally publishes `ready` only if token/state/ownership still match.
4. Renew the lease every 30 seconds. Soft render limit 240 seconds, hard limit 300; lease exceeds the hard limit. Verify child-process termination and object cleanup on hard kills.
5. Retry transient render/storage failures at 30 seconds and 120 seconds, maximum three automatic attempts. Permanent validation/schema failures stop immediately. One explicit user retry can grant one additional attempt after a recoverable failure, subject to retained assets and a repaired dependency; it receives no further automatic retry. Check/set the persisted request ID and increment the lifetime attempt count under the row lock. Retry never reruns the source agent.
6. Reconciler resets expired render leases only after the old task's hard deadline has passed. Old workers remain fenced even if they return late.
7. Finalization allows up to 30 seconds for pending capture uploads; then freezes available assets and marks omissions. Late assets are cleaned up, not appended to a published video.
8. On publication, update recap metadata for polling and use existing notification/chat-fanout infrastructure where appropriate. Notification failure does not unpublish ready media.

The repository has no Celery beat. Implement the 60-second sweep using the existing self-rescheduling/DB-claim pattern, initialized only by the default worker. A sweeper claim/lease prevents restart-created copies from duplicating work. An auxiliary media worker must not dispatch unrelated default-queue schedulers.

## 11. Storage, access, and retention

Require `S3_PRIVATE_BUCKET` explicitly for this feature. If absent, video generation is unavailable; do not inherit the public/general-bucket fallback. Verify bucket public-access blocking and encryption during operator-approved rollout.

Generated prefix layout:

```text
espresso-recaps/<company_uuid>/<owner_uuid>/<recap_uuid>/
  source/<event_uuid>/<capture_token>/...
  renders/<render_token>/video.mp4
  renders/<render_token>/poster.webp
  renders/<render_token>/chapters.json
  renders/<render_token>/transcript.json
```

- Use multipart/file-object uploads where needed, bounded concurrency, and streamed downloads to disk. Never load all clips or the final video into one Python byte string.
- Direct authorized S3 playback is sufficient for v1. Configure MIME types, inline disposition, byte-range playback, and origin-limited CORS as needed. No adaptive streaming service is required for two-minute clips.
- Playback API verifies current account activity, personal workspace, user/company ownership, retained source access, and recap state, then issues five-minute object URLs. Signed URLs are bearer access until expiry; do not claim immediate revocation of a URL already issued.
- Player refreshes a URL before expiry or once after an authorization-related playback failure, preserving playhead. Re-check authorization on refresh; stop on logout/403/404.
- Keep source media seven days from upload; final media thirty days from `ready_at`. A ready recap remains playable after source expiry. Render retries requiring expired assets return a clear 409 and never recapture the task.
- Deletion immediately tombstones access and persists a prefix cleanup job in the same transaction. Delete known versions where bucket versioning applies; lifecycle rules must also cover noncurrent versions and incomplete multipart uploads.
- Periodic inventory removes unreferenced render attempts/staging prefixes older than a grace period. Never remove prefixes belonging to an active capture/render lease.
- Turning off an ability stops further capture for that ability; it does not imply deletion of past results. Turning off recap creation cancels unfinished recaps; explicit recap/source/account deletion removes retained artifacts.
- Logs contain IDs, state, durations, and error codes, not email contents, event details, signed URLs, provider tokens, or snapshot JSON.

## 12. REST and web contracts

New authenticated router: `server/app/matcha/routes/matcha_work/recaps.py`, included by the existing package aggregator. Apply the personal-workspace dependency in addition to the package gate; filter both company and owner. Another owner's identifier returns 404.

| Endpoint under `/api/matcha-work` | Contract |
|---|---|
| `GET /recaps/preferences` | Effective creation/email settings and availability reason |
| `PUT /recaps/preferences` | Strict bounded booleans; explicit opt-in; disabling schedules unfinished cancellation |
| `GET /recaps` | Owner-only cursor listing, limit 1–50; optional validated source filters |
| `POST /recaps/statuses` | At most 50 UUIDs; return minimal owner-visible states for visible cards; inaccessible IDs are omitted |
| `GET /recaps/{id}` | State, outcome, title, durations, timestamps, chapters, transcript, source links, retry eligibility; no storage keys |
| `POST /recaps/{id}/playback` | Short-lived video/poster URLs plus expiry; only ready retained recaps |
| `POST /recaps/{id}/retry` | UUID request key; failed/eligible only; one manual grant per recap; repeats of the stored key return the existing grant/current status; a different key after consumption returns 409 |
| `DELETE /recaps/{id}` | Idempotent access revocation and durable cleanup scheduling |

Register `/preferences` and `/statuses` before `/{id}`. Response models live in `models/matcha_work/recaps.py`; use explicit enums, sizes, UUIDs, version fields, timezone-aware ISO timestamps, and `extra='forbid'` for input bodies. Source references are generated/validated server-side.

Web work:

- New `pages/Recap.tsx`, `pages/Recaps.tsx`, `components/recaps/RecapPlayer.tsx`, `RecapStatus.tsx`, `RecapPreferences.tsx`, and `hooks/useRecap.ts`.
- New `api/matchaWork/recaps.ts`; add types to the work-owned type surface, not page exports. Use the existing API helper and `useMe`.
- Mount `/espresso/recaps` and `/espresso/recaps/:recapId` through `WorkRouteTree`'s Espresso surface condition. Use surface-aware base paths and literal route ordering before the catch-all `:threadId` route.
- Add optional `recap_id` to eligible final result/task-card metadata; render the badge in `AgentCardMessage`. Add latest-recap linkage to job-search detail, with the source generation so a new search pass does not overwrite the old link.
- Because general research-task cards may not have a complete web renderer, the recap library and direct email URL must work independently. Add only the minimal link/fallback for such messages; a full research task UI is not a dependency.
- Poll one visible recap every five seconds while queued/rendering, then back off to fifteen seconds after one minute. Stop on terminal state, unmount, hidden document, or account change. Avoid one poller per historical chat message: fetch recap statuses in the owner listing/batched lookup path for visible cards.
- Player provides keyboard controls, captions/visible step labels, a readable transcript, chapters, duration, preparation/error/expiry states, and a source link. Never autoplay.
- Use optional metadata and ordinary fallback text so older macOS clients can ignore the feature. No new mandatory field in existing result blocks; no Swift changes in this release.

Example safe recap status payload:

```json
{
  "schema_version": 1,
  "id": "uuid",
  "state": "ready",
  "outcome": "complete",
  "title": "Apartment search recap",
  "duration_ms": 89000,
  "elapsed_ms": 1800000,
  "expires_at": "2026-11-16T19:00:00Z",
  "chapters": [{"label": "Best matches", "start_ms": 69000}],
  "can_retry": false
}
```

## 13. Email ownership and delivery

### 13.1 One coordinated completion message

Keep in-app task completion immediate. For recap-enabled search sources, reserve `completion_mail_owner='recap'` and create the durable delivery record before suppressing the existing `mail.round_finished` / `mail.search_finished` send. If registration fails before this ownership decision commits, existing mail remains responsible.

Freeze the normal result-email data at source completion using existing composition logic. Multiple child searches in one logical request contribute bounded child summaries to one root delivery. Only the root delivery sends; child sources cannot also send their legacy completion message.

Delivery becomes due when the video is ready, or 120 seconds after logical completion, whichever comes first:

- Ready: one combined summary plus “Watch recap” linking to the Espresso page.
- Still rendering at deadline: one summary plus “View recap” linking to the preparing page.
- Permanently failed/skipped: normal result summary; omit a misleading watch button.
- Video becomes ready after deadline email: update in-app status; do not send a second automatic email.
- Standalone calendar/email request: send one concise completion/recap message under the same deadline rule when recap email is enabled.
- Existing quick-research email suppression remains for ordinary search summaries. A short calendar/email operation with a meaningful recap can email when the user enabled recap email. Ordinary chat with no useful agentic work produces neither video nor recap email.

Disabling recap email suppresses the additional standalone-action notification and leaves existing search result-email eligibility intact. Disabling creation after delivery ownership was assigned resolves the durable row to a normal summary, rather than reviving a second legacy sender. A missing/unreadable delivery row is a reconciliation problem; never blindly invoke both send paths.

### 13.2 Transport and retries

Add a new opt-in structured send method in the core email service, preserving existing boolean callers. Return `sent(provider, message_id)`, `not_sent_retryable`, `not_sent_permanent`, `unknown`, or `suppressed`.

Use existing sender identities and reserved-domain guards. A transport may switch providers only after a definite non-delivery result. A timeout after request transmission is `unknown`; do not immediately fall back or resend. Where the provider supports a documented idempotency mechanism, use the delivery UUID; an ordinary Message-ID alone is not a deduplication guarantee.

Claim delivery with a token before the network call; persist the result afterward. Crash after provider acceptance but before persistence becomes `unknown` on lease expiry. Retain the provider receipt if available and expose an operator reconciliation path. V1 prefers a possibly missed email over an automatic duplicate after an ambiguous send; the video remains available in Espresso. Exactly-once external email delivery is not promised.

Bound definite non-delivery retries to three dispatch attempts with 30-second/120-second backoff. Give each dispatch a 90-second lease and a 60-second hard task deadline; fit any sequential provider calls within that deadline. Revalidate owner/preferences on every attempt. The grace timestamp controls when delivery becomes due; broker/sweeper delay is measured separately and is not a guaranteed email-arrival time.

Resolve the current `users.email`, active/suspended state, and email preference immediately before send. Send to the account owner only, never an address from the source email, calendar attendees, agent output, or request body. Email uses a generic branded thumbnail/button; private poster URLs are not embedded in email where link scanners could fetch them.

## 14. Planned file changes

### New files/packages

```text
docs/plans/ESPRESSO_TASK_RECAPS_TECHNICAL_PLAN.md       this plan
server/alembic/versions/<revision>_agent_recaps.py    additive schema, version chosen at implementation
server/app/matcha/models/matcha_work/recaps.py        API contracts
server/app/matcha/routes/matcha_work/recaps.py        authenticated API
server/app/matcha/services/matcha_work/recaps/
  __init__.py
  contracts.py                                     event/manifest validation
  scope.py                                         logical roots, lineage, eligibility
  store.py                                         fenced persistence and claims
  observe.py                                       optional bounded observation hooks
  adapters/{research,jobs,calendar,email}.py          safe typed snapshots
  capture.py                                       bounded Chromium capture
  storyboard.py                                    pure deterministic editing
  render.py                                        isolated renderer + FFmpeg
  storage.py                                       private streamed artifacts
  service.py                                       owner reads, retry, delete
  delivery.py                                      root completion ownership/email composition
  reconcile.py                                     recovery, expiry, orphan cleanup
server/app/workers/tasks/recaps.py                   worker entry points
server/Dockerfile.recaps                            media image, exact backend + render bundle
deploy/compose.recaps-worker.yml                    separate media host/container deployment
client/src/work/api/matchaWork/recaps.ts
client/src/work/pages/{Recap,Recaps}.tsx
client/src/work/components/recaps/*
client/src/work/hooks/useRecap.ts
client/src/work/recaps/render/*                      pure scene app
client/recap-render.html
client/vite.recap.config.ts
server/tests/recaps/*
docs/ops/ESPRESSO_RECAPS.md                          rollout/recovery/runbook after implementation
```

Modified files are the hook table in §7 plus `app/config.py`, core `services/storage.py` only if a reusable streamed method is needed, core `services/email/client.py`/exports, `workers/celery_app.py`, route aggregator, `client/package.json`, `client/src/work/types.ts`, `WorkRouteTree.tsx`, `WorkSettings.tsx`, `WorkSidebar` and its collapsed rail for the recap library, `AgentCardMessage.tsx`, and job-search API/detail files. Update the applicable repo guides when implementation lands. Do not mix unrelated refactors into these changes.

## 15. Configuration and resource budgets

All names below are proposed new settings; implement both the settings declaration and environment loading consistently.

| Setting / budget | Initial value |
|---|---|
| `ESPRESSO_RECAPS_ENABLED` | `false` |
| `ESPRESSO_RECAPS_ALLOWED_USERS` | Empty allowlist during pilot; owners identified by UUID |
| `ESPRESSO_RECAPS_CAPTURE_ENABLED` | `false` independently of card-only recaps |
| `ESPRESSO_RECAPS_RENDER_QUEUE` | Explicit `espresso_recaps_render`; no default-queue fallback |
| `S3_PRIVATE_BUCKET` | Required existing private bucket setting |
| `ESPRESSO_RECAPS_TEMPLATE_VERSION` | Version packaged with the media image |
| `ESPRESSO_RECAPS_MAX_SECONDS` | 120 |
| `ESPRESSO_RECAPS_MAX_AUTO_PER_DAY` | 10 per owner, reserved atomically; requests beyond cap keep ordinary results |
| `ESPRESSO_RECAPS_SOURCE_DAYS` | 7 |
| `ESPRESSO_RECAPS_FINAL_DAYS` | 30 |
| `ESPRESSO_RECAPS_EMAIL_GRACE_SECONDS` | 120 |
| Media worker | One task, max two FFmpeg threads; initial benchmark container budget 2 vCPU / 2 GiB, not a capacity guarantee |
| Media job limits | 256 MiB scratch workspace, 128 MiB source media, 64 MiB final video |
| Capture | ≤10 windows, ≤8 seconds/window, ≤8 captured fps |
| Rendering | 240s soft / 300s hard / 360s lease; ≤3 automatic attempts plus one explicit manual attempt |
| Waiting / queued recovery | Waiting follows prompt expiry with 7-day cap; queued >1h is failed `render_queue_timeout` |

Worker environment includes only the database/broker/storage/render settings it needs; do not copy Gmail/Calendar credentials or an entire user session into it. Delivery stays in the existing service environment. Keep the broker/network private and use existing approved deployment access patterns.

Capture/renderer availability is separate from underlying task entitlements. If a dependency is missing, show recap unavailability and continue the task. Account limits and expiry are enforced in code/DB, not only UI controls.

## 16. Failure-boundary checklist

| Boundary / scenario | Required behavior |
|---|---|
| Recap registration fails before source dispatch | Source succeeds through ordinary path; legacy mail ownership retained |
| Child/continuation binding fails under an existing root | Atomically skip/fence the root before dispatch; ordinary notifications may fall back to separate summaries |
| Provider action succeeds; observation fails | Preserve confirmed source outcome; never repeat provider action |
| Source state commits; Celery publish fails | Durable row remains due; reconciler publishes later |
| Process dies while capture is active | Agent's existing recovery applies; media budget/resources reclaimed; missing clip can be omitted |
| Upload succeeds; event attachment fails | Deterministic staging prefix is swept; no public orphan |
| Phase repeats or token becomes stale | Unique event key/fencing prevents duplicate or wrong-generation evidence |
| Render completes after deletion or lease replacement | Conditional publication fails; its output is cleaned up |
| S3 unavailable | Retry bounded media work; task/result still usable; email grace fallback applies |
| Worker absent / malformed queue | No render on main queue; observable timeout and normal result delivery |
| Waiting confirmation / confirmation declined | No premature completed-action scene; explicit held/declined semantics |
| Unknown send/calendar outcome | Label unknown and preserve it in final summary; never infer success or replay |
| Later refine/widen runs during old video rendering | Old frozen snapshot remains stable; new source generation/root is separate |
| One source of a multi-source recap is deleted | Revoke whole recap and clean its artifacts |
| User/account loses access during render/send/playback | Recheck authority; suppress publication/delivery or revoke access as applicable |
| Email provider accepted but response/persistence lost | `unknown`; no blind resend or fallback |
| Raw clips expired before manual retry | Clear retry-unavailable response; no new task execution |
| Duplicate scheduler starts | Single DB sweep claim; bounded duplicate queue items remain harmless |
| Metadata cascaded by account deletion | Access gone immediately; independent cleanup/lifecycle/orphan inventory removes S3 objects |

## 17. Implementation sequence and exit gates

Each phase is a separate reviewable change. Flags stay off until the rollout gates pass.

### P0 — media feasibility and fixtures

- Create sanitized, synthetic fixtures for jobs, apartments, calendar changes, and email management using reserved test domains.
- Exercise the pinned Chromium start/stop capture API, fallback screenshots, scene rendering, and FFmpeg encoding on isolated local/ephemeral compute.
- Produce four sample videos; include one modeled thirty-minute timeline with real idle gaps omitted. Samples must be labeled demonstrations, not actual customer task recordings.
- Measure CPU, peak RSS, disk, file size, render seconds, capture latency, and text readability; compare source-task execution with capture enabled/disabled.
- Exit: representative videos readable at 1080p and mobile player size, no full-run recording, render within the 120-second email grace target on benchmark compute, and agreed resource limits. If missed, revise the limits before later phases; no capacity claim from configuration alone.

### P1 — schema, contracts, and disabled API foundation

- Add additive tables/job-generation field, settings, preference endpoints, scope resolution, event/manifest schemas, source ownership, and pure storyboard tests.
- Add optional hooks/signatures with no effect while disabled.
- Rehearse upgrade/downgrade in an explicitly approved disposable database; inspect constraints, indexes, lock behavior, and old-application compatibility.
- Exit: feature-off parity, schema graph valid, complete owner isolation and state-transition tests.

### P2 — recording and source lifecycle

- Bind direct/API/chat/form starts, search phases, assistant continuations, and all terminal/deletion paths.
- Add safe adapters for all four requested task categories, optional browser capture, immutable snapshots, and source budgets.
- Keep rendering/delivery disabled; inspect captured manifests in tests/fixtures.
- Exit: no premature closure, no new provider actions, no data from other owners, no duplicates after retries, no private material outside allowlists.

### P3 — media worker and artifact lifecycle

- Build versioned render bundle/media image, implement private streaming storage, render claims, validation, output publication, recovery, expiry, and cleanup.
- Wire explicit render queue and lightweight reconciler using the existing scheduler pattern.
- Exit: worker-kill/upload/delete races pass; no default-worker Chromium/FFmpeg; samples pass playback validation.

### P4 — web experience

- Add recap library/player/preferences, status polling, result/card links, job-generation links, transcript, and accessibility states.
- Verify direct email deep links through login and personal-account authorization.
- Exit: production client build, frontend tests, Safari/Chrome playback/seek/expiry refresh, older metadata consumer compatibility.

### P5 — coordinated email delivery

- Implement completion ownership, grace-deadline delivery, snapshot-based summary composition, and structured transport outcomes.
- Preserve existing non-recap email behavior and reserved-domain guards.
- Exit: one normal completion email per logical request, correct owner, no duplicate child/legacy delivery, ambiguous sends handled without automatic resubmission.

### P6 — staged rollout and operations

- Roll out schema first, then compatible API/workers/render bundle and frontend with feature disabled.
- Configure explicit private storage, lifecycle, separate compute, queue, health checks, and dashboards through the existing approved ops workflow.
- Enable internal opt-in accounts, first card-only, then bounded real capture. Expand only after observing resource cost and recovery.
- Exit: end-to-end tests for all four categories, operational runbook, deletion drill, cost/latency measurements, and rollback exercised.

## 18. Validation plan

These commands are planned for implementation; none is a claim that implementation tests have run in this planning task.

### Automated checks

- `cd server && ./venv/bin/python -m pytest tests/recaps tests/agent_runtime tests/agent_tasks tests/job_search -q`
- `cd server && ./venv/bin/python -m pytest tests -q` after shared runtime/store/email changes, using the repository's safe unit-test configuration; do not enable live DB/provider integration implicitly.
- `cd client && npm run test:run -- src/work/components/recaps src/work/pages/Recap.test.tsx src/work/pages/Recaps.test.tsx src/work/components/channels/AgentCardMessage.test.tsx src/work/pages/WorkSettings.test.tsx`
- `cd client && npm run build` — existing production type/build gate.
- `cd client && npm run build:recaps` — proposed new script, required once added.
- `python3 scripts/alembic_graph.py heads` — static graph inspection; compare to the expected pre-change head set.
- `git diff --check`.

### Required focused tests

1. Direct, chat, and form-started sources; assistant result followed by a live child; multiple children; confirmation/open-question continuation; duplicate trigger delivery.
2. Research round boundaries; job initial/widen/redraft generations; batches sharing a phase name; stale dispatch tokens; retries and partial results.
3. Draft versus commit, dry run versus live, unknown versus failed, decline/expiry/cancel; no action handler called by rendering/retry.
4. Owner/company checks on every list/detail/playback/retry/delete/preferences path; account change during asynchronous work; personal-surface gating.
5. Snapshot immutability after later edits; byte-vs-character caps; emoji/combining sequences; long titles; timezone/DST and unknown enum rejection.
6. Capture bounds, frame backpressure, browser crash, absent screencast capability, incorrect redirects, no-frame and one-frame scenes, media spoofing, disk exhaustion.
7. Manifest order/duration caps; repeated stages; required warning inclusion; image/font failures; empty results; unsupported codecs; incompatible media sizes.
8. Crash before/after each database, broker, file, upload, publication, and send boundary listed in §16; stale worker publication rejected.
9. Missing private bucket/worker/template version; feature off; per-owner auto limit; opt-out; source and final expiry; object versions; orphan cleanup.
10. Email combined/grace/failed/late-ready behavior, child suppression, current owner address, reserved domains, known failure retries, ambiguous-send no retry.
11. Polling lifecycle, deep links, logout, URL refresh/seek preservation, unavailable/expired UI, keyboard controls, transcript, and optional-field compatibility.

Media smoke tests use generated local fixtures and mocked APIs. Use only reserved-domain test recipients. No real Gmail sends, calendar writes, customer browsing, or migrations on a live database are part of automatic validation. Database-mutating rehearsals require explicit approval and disposable infrastructure under repository rules.

### Performance acceptance

- A 30-minute synthetic event timeline yields a ≤120-second video without 30 minutes of recorded source media.
- Four category fixtures stay within source/output/disk budgets and the measured worker memory limit.
- Target p95 render time ≤120 seconds after manifest freeze on the chosen benchmark machine; queue delay is reported separately. This is a rollout target, not a guarantee about the present host.
- Capture adds no provider calls and does not extend existing per-browser deadlines. Target <5% task-duration overhead across representative workloads; report median/p95, absolute overhead, and missing-frame rate.
- Measure storage per recap, retention totals, bytes served per playback, and CPU-seconds per finished video before expanding the allowlist.

## 19. Observability, rollout, and rollback

Metrics: roots created/skipped, snapshot failures, missing/expired captures, frames dropped, source bytes, queue age, render wall time/CPU/RSS, attempts, output bytes/duration, publication failures, playback authorization failures, delivery states, cleanup backlog, and orphan bytes. Use task category as a bounded label, not user IDs or titles.

Correlate logs with recap/source/run/generation/render-token IDs. Alert on queued age >10 minutes, repeated template mismatch, expired render leases, cleanup backlog >24 hours, and unusual render failure rate. A queue timeout remains a terminal state even if an alert is missed.

Rollout order: schema → compatible code/image/bundle → private storage and separate media worker → disabled frontend → internal preference opt-in → card-only pilot → captured footage pilot → broader opt-in. Confirm actual host capacity, worker codecs, private bucket policy/versioning, and provider delivery semantics; repository comments do not prove live infrastructure state.

Rollback: disable new recap creation/capture, stop new render claims, preserve ready-video reads and cleanup, and resolve owned pending completion deliveries to ordinary summaries. Drain or fence active renders before removing workers. Keep additive tables/fields during code rollback so old application versions ignore them. Do not downgrade a production schema merely to turn off the feature.

## 20. Definition of done

- Job search, apartment/research, calendar, and email all produce truthful owner-scoped recaps from actual evidence.
- Async work continues while Espresso web is closed; waiting/continuations/retries do not create premature or duplicate videos.
- A thirty-minute representative task produces a readable one-to-two-minute result within measured resource budgets.
- Recap failures never repeat actions or invalidate successful tasks; partial and unknown outcomes remain explicit.
- Playback, signed-link refresh, coordinated email, opt-out, expiry, and deletion work end to end.
- All relevant production builds/tests and approved migration/media rehearsals pass; operational limits are measured, documented, and enforced.

## References

- [Playwright video lifecycle and sizing](https://playwright.dev/docs/videos).
- [Chromium Page protocol, including screencast methods](https://chromedevtools.github.io/devtools-protocol/tot/Page/). Validate against the pinned browser; tip-of-tree documentation is not a compatibility guarantee.
- [FFmpeg concatenation guidance](https://ffmpeg.org/faq.html) and [MP4/faststart documentation](https://ffmpeg.org/ffmpeg-formats.html).
- [S3 presigned URL behavior and expiry](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).
