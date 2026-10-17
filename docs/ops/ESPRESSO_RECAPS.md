# Espresso web task recaps

## Behavior

An opted-in personal account can receive a private recap of an Assistant request,
its confirmation continuations and explicitly launched research/job searches.
Direct research rounds and new job-search execution generations also enroll.
The existing agent loop and its action permissions remain authoritative. Neither
rendering nor Retry executes source actions again.

The observer stores allowlisted outcome snapshots. Guarded public `view_page`
activity can add real Chromium JPEG windows; API work uses deterministic React
cards. Email bodies, raw tool arguments, BCC, attendees, login sessions and model
reasoning are not copied. Search result facts are bounded and labeled with their
recorded verification/pay status. Local calendar audits include selected title,
old/new times and a validated account timezone. Calendar previews retain ISO offsets;
v1 does not infer an IANA timezone when the source preview has none.

The library/player live at `/espresso/recaps` and `/espresso/recaps/:id`, with links
from task/search details and assistant results. Settings separates video creation
from recap email. The backend requires personal-company membership, owner identity,
an active account and retained sources on reads and asynchronous publication.
Playback uses five-minute signed private object URLs. Logout/account changes clear
client preference and player state. No public sharing endpoint is provided.

## Release configuration

Everything is disabled by default. Apply `recap01` (child of `agenttask05`) through
the approved [database workflow](DB_WORKFLOW.md) before enabling. This change does
not apply the migration, provision storage, deploy a worker or send test mail.
The migration creates six recap tables and adds `mw_job_searches.recap_generation`;
its downgrade removes recap records and that column, but cannot remove S3 objects.
Drain/tombstone artifacts and verify cleanup before a deliberate downgrade.

The API/default worker and media worker need matching release code and:

| Setting | Initial value / requirement |
|---|---|
| `ESPRESSO_RECAPS_ENABLED` | `false`; enable only after release gates |
| `ESPRESSO_RECAPS_ALLOWED_USERS` | Comma-separated explicit owner UUIDs |
| `ESPRESSO_RECAPS_CAPTURE_ENABLED` | `false`; enable separately after capture checks |
| `S3_PRIVATE_BUCKET` | Explicit private bucket; no ordinary/public-bucket fallback |
| User preferences | Creation and recap email each require explicit opt-in |
| `ESPRESSO_RECAPS_RENDER_BUNDLE` | `/app/recap-render` in the media image |

Build `server/Dockerfile.recaps` from the repository root using an immutable
`BACKEND_IMAGE` digest from the same release. It builds the separate Vite scene
bundle, adds Noto fonts and copies the release backend. The backend image must
contain the pinned Playwright Chromium, FFmpeg/libx264 and ffprobe.

Use `deploy/compose.recaps-worker.yml` on **separate compute**. Its initial envelope
is two CPUs, 2 GiB RAM, a 256 MiB `/tmp`, read-only root, no added capabilities and
one solo worker consuming only `espresso_recaps_render`. Do not add this service
to the existing application host. The queue worker supervises a separate process
for each render/cleanup job. Linux child-subreaper and pidfd support are required;
the OS deadline bounds threaded transfers as well as FFmpeg/Chromium. A surviving
descendant stops the worker container instead of allowing overlapping media jobs.

The restricted media environment sets `ESPRESSO_RECAPS_WORKER=1` and needs only
database/TLS, Redis broker, private-storage credentials and recap settings. Its
bootstrap does not require LIVE_API, AI, JWT, mail or calendar credentials. Do not
copy the application `.env` or user sessions. Delivery runs on the default worker;
the media worker rejects delivery tasks. IAM should restrict object access to
`espresso-recaps/`, including object version listing/deletion. Keep bucket public
access blocked. Configure short source-media lifecycle retention and a safety
lifecycle for final/orphaned objects, including noncurrent versions. Configure
automatic abort of incomplete multipart uploads so killed transfers cannot leave
unlisted upload parts indefinitely. Configure
private-bucket browser CORS for the actual Espresso origin and range playback.
Verify that this prefix is never exposed through a public CloudFront distribution.

## Lifecycle, budgets and recovery

- Bind sources in a savepoint before dispatch. The logical root is locked against
  child enrollment/finalization races. Phase evidence carries the original dispatch
  token and job generation/research round. Late workers cannot join a later cycle.
- Collect up to 128 event snapshots. Reserve final capacity and evict decorative
  events for consequential outcomes. At freeze, recover missing consequential
  action counts from authoritative step rows without discarding recorded details.
- Wait for every source and open prompt. Follow-up research closes its superseded
  recap source without changing domain round accounting. Stale internal phase runs
  stop blocking when their parent dispatch epoch advances.
- After source completion, allow 30 seconds for outstanding capture uploads. Freeze
  the manifest once. Select at most 12 scenes/120 seconds with a bounded transcript;
  preserve action warnings and result snapshots before decorative phases.
- Capture at most eight windows, each up to eight seconds/64 JPEGs/16 MiB. The total
  source package budget is 128 MiB, including uploaded-but-unattached packages.
  No continuous recording runs during a thirty-minute wait. CDP unavailability
  falls back to a bounded checkpoint; unavailable/revoked enrollment captures none.
- Render silent 1920×1080 H.264 at 15 fps, yuv420p, square pixels and faststart.
  Source public footage is upscaled from its bounded viewport; cards are native
  1080p. Validate the stream and decode the final file. Cap output at 64 MiB and
  scratch at 256 MiB. One lower-bitrate encode is allowed within the process deadline.
- The media process deadline is 240 seconds (cleanup 90); a render lease lasts six
  minutes. Three automatic attempts use bounded backoff. One persisted manual grant
  may retry the immutable manifest within seven days. Opt-out rejects that grant
  before consumption. A failed media job never changes the completed source task.
- The default worker self-reschedules a 60-second sweep, claimed through
  `scheduler_settings.espresso_recaps`. It repairs lost publications/expired leases,
  bounds queued rendering to one hour and ends uncompleted recap collection after
  seven days. Creation-off does not discard existing delivery ownership.
- Existing search completion summaries use durable recap ownership. One combined
  email includes the ready recap or a stable preparing link after 120 seconds.
  A late render sends no second email. Ordinary chat without useful evidence sends
  no standalone completion email. Ambiguous provider acceptance becomes `unknown`;
  do not blindly resend or fall back to a second provider. Definite failures have
  a separate bounded delivery budget.
- Final artifacts expire after thirty days; raw packages after seven days. Source
  deletion, account/source invalidation and explicit Delete tombstone publication
  immediately and enqueue independent cleanup. Already issued signed URLs remain
  usable for at most their five-minute lifetime. Cleanup removes bounded batches of
  object versions/delete markers/current objects until the prefix is empty. Durable
  cleanup instructions are written before upload, including for orphaned artifacts.

Monitor queued age, render attempts/lease expiry, failed/skipped/error codes,
delivery `unknown`, cleanup backlog/attempts and source-media bytes. Logs contain
IDs and error classes rather than captured content. If a pilot fails, disable
creation/capture flags first; preserve the recovery dispatcher and durable email
ownership while draining work. Never replay source actions to repair a recap.

## Validation and release gates

Default unit tests use fake persistence, storage and mail transports; they do not
apply schema or contact providers. Real local smoke tests are explicitly opt-in:

```sh
cd client
npm run build
npm run build:recaps
# In server/, using the installed test Python:
python -m pytest tests/recaps -q
RUN_RECAP_MEDIA_TESTS=1 python -m pytest tests/recaps/test_media.py -q
```

On the development Mac, four synthetic thirty-minute histories (jobs, apartments,
calendar, email) each produced a decoded 68-second 1080p MP4 of about 270 KB in
roughly three seconds. These are static-card demonstrations, not production
capacity measurements. A separate real Chromium test captures changing local
page frames and stitches/decodes the resulting media. No external account actions
are used by either test. Motion, text density and worker hardware affect size/time.

Before enabling any owner: rehearse migration upgrade/downgrade against a disposable
representative database through the approved workflow; build/run the Linux image;
verify hard termination with a stuck transfer/browser and scratch cleanup; exercise
real private S3 upload/range playback/version deletion/retention; test structured
mail outcomes using a designated test account; verify Chrome and Safari playback;
benchmark mixed footage at the configured CPU/RAM limits and check task latency.
Those checks require infrastructure and remain rollout gates, not validated claims
of this pull request. Never enable fleet-wide from the local fixture metrics.
