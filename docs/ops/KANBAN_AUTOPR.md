# Kanban Autopr

`.github/workflows/kanban-autopr.yml` runs on the same self-hosted Mac runner as
`silent-error-autofix.yml` and `autopr-self-audit.yml`. `msandbox` is the authoritative
master switch. While it is ON, a local macOS LaunchAgent is the sole automatic
five-minute clock and dispatches only when no AutoPR lane is queued or active. A
production-error pass gets the next slot when its last completion is at least ten
minutes old; then a self-audit gets one when its last completion is at least six hours
old; otherwise Kanban advances.
GitHub's manual workflow dispatch remains the recovery path but also fails closed when
`msandbox` is OFF. There is deliberately no second GitHub cron:
a remote schedule can race the dispatcher's run-list check and leave a duplicate pending
run. The runner has one job slot, and the workflow concurrency group remains the final
overlap guard. The unit of work is one kanban card assigned to
`haley@oceaneca.com` sitting in `todo` or `changes_requested`, across four fixed
Espresso projects — WerkWerk, Beetlejuse, Gummfit, and MATCHA. It never scans the whole
board or every user's cards.

The board is the source of truth in both directions: a card drives a PR, and a PR drives
a card back. Ordinary AutoPR runs never merge or approve. The separate manual
`autopr-release-plan.yml` workflow can mark the plan's still-draft PRs ready and merge
them in the proposed order only after an operator supplies the exact live plan id; it
never bypasses branch protection or includes PRs that were already ready for review.

**Design constraint carried over from silent-error-autofix**: no model credential and no
Matcha credential goes into GitHub secrets. The runner is Finch's Mac running as Finch's
user; before each run the trusted bridge makes a temporary mode-600 copy of the Mac's
existing Codex `~/.codex/auth.json` and exposes that one file read-only in the dedicated
`matcha-kanban-autopr-sandbox` container. The Matcha bot credential lives in
`~/.config/matcha-autopr/env` (`chmod 600`, never committed). Codex itself never
receives that file or credential.

The existing `EC2_SSH_KEY` Actions secret is used only by the trusted harness. Before
each queue scan, `resolve-production-context.sh` resolves the active blue/green
backend/frontend containers through their ECR digests, recovers their immutable Git SHA
tags, reads the public frontend build number, and compares production's read-only
`alembic_version` set with the repository heads. A live SHA missing from or divergent
from `main`, an unreadable build number, or an unreadable schema state fails the run
closed. New frontend images expose the build/SHA in `/version.json`; the resolver keeps
a compiled-bundle fallback only for older images that predate the manifest. The key is
removed from the environment before Codex starts.

The post-deploy admin-update publisher reuses this same sealed bridge and sandbox
identity for a writing-only `gpt-5.6-luna`/high pass. It is dispatched by a completed
deploy rather than the five-minute card clock, but the one-slot Mac runner serializes
it with the other lanes. The model receives neither the SSH key nor database access;
trusted code validates its fixed JSON and owns the narrow changelog transaction. See
`docs/ops/ADMIN_UPDATES_AUTOPUBLISH.md`.

## Why per-project collaborator rows, not a company scope

The four projects span **two different `companies` rows** — WerkWerk/Beetlejuse/Gummfit
live under Haley's personal Espresso workspace (`is_personal=true`), MATCHA lives under a
separate personal/test workspace. A `client`-role user only gets same-company access via
`clients.company_id`, which can point at exactly one company — so a single `clients` row
cannot cover all four. Instead the seed pack (`scripts/seed/autopr_bot.py`) gives the bot
a `mw_project_collaborators` row on each of the four project ids directly.
`_verify_project_access` (`routes/matcha_work/_shared.py`) falls back to the collaborator
table whenever the same-company path doesn't match, so this works regardless of which
company owns which project — and continues to work if a project's owning company ever
changes.

## One-time setup

1. Run the seed pack (creates the bot user + the four collaborator rows):
   ```sh
   AUTOPR_BOT_PASSWORD=<pick a real password> ./scripts/seed-prod.sh scripts/seed/autopr_bot.py --dry-run
   AUTOPR_BOT_PASSWORD=<same password> ./scripts/seed-prod.sh scripts/seed/autopr_bot.py
   ```
   Undo: `./scripts/seed-prod.sh scripts/seed/autopr_bot.py --undo`.
2. Write `~/.config/matcha-autopr/env` (`chmod 600`), never committed:
   ```sh
   MATCHA_API_URL=https://hey-matcha.com/api
   MATCHA_BOT_EMAIL=support@hey-matcha.com
   MATCHA_BOT_PASSWORD=<the same password from step 1>
   MATCHA_PROJECT_IDS=7f728636-3219-4d83-9df3-a4682e3242de,fade10b4-36ff-4c60-af59-5cc6058285ab,84823d21-c752-4abd-9696-4c93c8b3c21e,8b924347-d6e4-4000-8e7d-ca8f46f76fba
   MATCHA_ASSIGNEE_EMAIL=haley@oceaneca.com
   # Optional: approved is_test tenant used only by the trusted reproduction harness.
   AUTOPR_TEST_TENANT_EMAIL=<test tenant owner email>
   AUTOPR_TEST_TENANT_PASSWORD=<test tenant password>
   ```
   Scheduled GitHub runs fail closed if `MATCHA_API_URL` points at localhost or
   if any of the four project ids is missing. This prevents a production PR from
   being linked to a dev-only card. If test-tenant replay is configured, install
   its trusted runner browser once with
   `server/venv/bin/python -m playwright install chromium`. The credentials,
   cookies, headers, and response bodies never enter msandbox; only a screenshot
   and bounded same-origin status signals do.
3. Install the checkout hook in the real clone: `./scripts/kanban-autopr/install-hooks.sh`.
4. Upgrade the repo's GitHub webhook to also deliver `pull_request` (idempotent — safe to
   re-run against an already-installed hook): call the existing
   `POST /matcha-work/projects/{id}/github/install-webhook` admin endpoint, or re-run
   whatever originally installed it. `install_repo_webhook` now PATCHes an existing
   hook's event list up to `["push", "pull_request"]` instead of no-op'ing on a URL match.
5. Ensure the host Codex CLI is authenticated with the intended ChatGPT account
   (`codex login status`). Do **not** add an API key for the
   sandbox: each run securely reuses only the host auth file.
6. Install the local timer: `./scripts/kanban-autopr/install-launch-agent.sh`. Installation
   alone leaves autonomous work OFF. Its JSONL log is
   `~/Library/Logs/matcha-kanban-autopr-dispatch.log`.
7. Run `msandbox` or `msandbox start`. This starts the primary sandbox, enables and kicks
   the timer, creates the `matcha-autopr` host tmux dashboard, and prints a mandatory
   health/activity summary. Open it with
   `tmux attach -t matcha-autopr`; detach with `Ctrl-b d`. `msandbox stop` removes the
   authorization gate before unloading the timer and stopping both sandbox containers,
   but refuses while an agent or AutoPR workflow is active. `msandbox stop --force` is
   the explicit interruption override. Do not add a GitHub cron alongside it.

## Local tmux dashboard

While the `msandbox` master switch is ON, the LaunchAgent recreates the read-only
`matcha-autopr` session on its next five-minute tick if the session is missing. Detaching
the dashboard does not stop work; `msandbox stop` does. A session name alone is not
considered healthy: if any of the four panes is dead or missing, the helper replaces the
whole observer session. Autonomous model startup fails closed until all four panes are
live. The overview owns the full-height left side; the right side stacks live agent work,
active PR detail, and automation health. This keeps the operational answer readable from
across a room while retaining drill-down detail in the same tmux window.

The LaunchAgent does not execute the repo-backed `msandbox` symlink directly:
macOS can deny background agents access to `~/Documents` even when Terminal has
access. Instead, the dispatcher evaluates the same fail-closed master predicate
from launchd-safe locations: the `autopr-enabled` marker created only by
`msandbox`, plus a running Docker Compose `matcha-agent-sandbox` workspace.
The workflow repeats the complete `msandbox autopr-ready` check before starting
Codex. Docker Desktop's CLI path (`/usr/local/bin`) is explicit in the plist.

- **operations overview (Pacific time)** — a glanceable control board with the current
  workflow phase and elapsed time, active card/branch, the exact card `select.sh` would
  choose next, queue entries classified as feedback/rework/Todo/waiting/held, open PR age,
  open-to-merge duration for recently merged bot PRs, and recent workflow duration. Every
  timestamp displayed to the operator is Pacific time. GitHub and board responses are
  cached as last-known-good snapshots: a transient source failure is shown as `STALE` or
  `DEGRADED`, never as an empty queue. Selector failures are also explicit instead of being
  rendered as “none eligible.” The selector call uses `AUTOPR_SELECT_READ_ONLY=true`, so a
  refresh cannot create a cooldown marker or consume a card.
- **active PR detail** — the active `bot/task-*` branch and cached card title before
  publication, followed by its PR number, draft state, labels, checks, URL, changed files,
  and a bounded live diff summary after GitHub publication. It reads the dedicated Actions
  runner worktree and never displays the ticket prompt or credential-bearing process
  arguments.
- **live agent detail** — current Actions run/step, dedicated msandbox identity,
  plus the real model terminal
  stream while it investigates, reads files, edits code, and verifies the task. The
  trusted harness tees that output to the mode-600 local file
  `~/Library/Logs/matcha-kanban-autopr-live.log`; GitHub does not expose live step stdout.
  Model credentials remain stripped, and the display adds common token and PEM redaction.
  This pane appends instead of redrawing, so earlier work remains in tmux's 100,000-line
  history across subsequent runs while the master session stays up. Scroll with the mouse
  or trackpad, or enter copy mode with `Ctrl-b [`.
- **automation health** — LaunchAgent state, self-hosted runner presence, recent
  structured dispatch/skip/error events, and the dedicated worker's real Docker state.
  A container stuck in `created`, `exited`, or another non-running state is shown as
  blocked rather than healthy.

The overview and PR metadata refresh every 60 seconds. The local model stream still
appends new output every 2 seconds, but its remote workflow status refreshes every 60;
health refreshes from local state every 15 seconds. The overview, PR pane, live-work pane,
and dispatcher share one mode-600 GitHub run snapshot with a 60-second TTL. Its refresh is
one unfiltered run-list request that is classified locally, rather than each pane resolving
and polling four workflow names independently. A dispatch uses one direct workflow API
POST. Override those intervals with
`AUTOPR_DASHBOARD_REFRESH_SECONDS`, `AUTOPR_PR_REFRESH_SECONDS`,
`AUTOPR_WORK_REFRESH_SECONDS`, `AUTOPR_WORK_STATUS_REFRESH_SECONDS`, and
`AUTOPR_HEALTH_REFRESH_SECONDS` before creating the session if needed. The shared GitHub
TTL is `AUTOPR_GITHUB_SNAPSHOT_TTL_SECONDS`; do not lower it without accounting for every
observer pane. Override `AUTOPR_RUNNER_WORKTREE` only if the Actions runner is moved.

The self-audit implementation and its sealed model allowlist are documented in
`docs/ops/AGENT_SANDBOX.md`. Manual recovery commands are `msandbox audit` and
`msandbox audit --draft`; they use the same workflow rather than creating a
second scheduler.

## Pipeline (`scripts/kanban-autopr/`)

1. **Production freshness** — the trusted local runner records the exact active frontend
   build plus backend/frontend SHAs and production migration heads. Once a card is
   selected it also attaches bounded, redacted recent error reports and error-level
   backend/worker/nginx log signals. Codex receives those files and a commit list
   between each live image and the checked-out branch, but never SSH or database
   credentials. This lets it tell a new code bug from an already-merged-but-not-deployed
   fix or an unapplied migration. It may diagnose migration drift. The path guard allows
   it to author a migration version only after a trusted `draft_pr` instruction and
   always forbids applying a migration.
2. **`collect.sh`** — one `GET /projects/{id}/bundle` per project in `MATCHA_PROJECT_IDS`
   (there is no company-wide list endpoint the bot can use — its access is per-project
   collaborator rows, not one company scope). Filters to cards assigned to
   `MATCHA_ASSIGNEE_EMAIL` in `todo`/`changes_requested`, plus system-linked
   `in_progress` cards awaiting owner-PR reconciliation, joins each card's `element_id`
   against the bundle's `elements` array to attach `repo_paths` (prompt-only scoping, not
   a gate).
3. **`reconcile-merged-cards.sh`** — repairs a missed `pull_request` webhook before
   selection. A Changes Requested card whose linked `bot/task-<id8>` PR is already
   merged is moved to Review and removed from that run's candidate snapshot. A
   matching defensive check in `select.sh` skips the card if the repair write fails,
   so a delayed webhook can never produce a duplicate PR.
4. **`collect-pr-context.sh` + `plan.py`** — reads bounded bodies, changed paths,
   comments, reviews, labels, and checks for every open Kanban/autofix/self-audit bot PR.
   The planner combines those with the complete eligible `todo` + `changes_requested`
   snapshot, links work by stable task/PR ids, project element, code area, and topic,
   then keeps related tickets contiguous. It writes one deterministic plan id, ticket
   work order, related-work evidence, and proposed merge order. GitHub PRs already
   marked ready for review (`isDraft=false`) are explicitly listed as excluded and do
   not receive a merge position. PR comments are untrusted planning evidence, never
   executable instructions.
5. **`select.sh`** — picks one planned card GitHub hasn't already handled. Branch key is
   `bot/task-<id8>` (first 8 hex of the task UUID). A pending decision-bound additional
   context event is highest priority, followed by related rework and planned Todo work;
   the plan keeps each related cluster together. Without a plan it safely falls back to
   reconsideration, Changes Requested, then Todo. Rework is better-specified —
   it has a written `review_note` — and unblocks a PR already in flight. For `todo`, any PR at all on
   the branch (open/closed/merged) means skip — the branch name is a stable 1:1 mapping
   to the task, so a second run would collide. For `changes_requested`, an **open** PR on
   the branch is the *target* to push to (`mode: rework`); no open PR means a human moved
   it there by hand, so it's treated like a fresh `todo` card. A durable no-spec ledger
   lives on the card itself (`progress_note` contains `[autopr:no-spec <date>]`) rather
   than a GitHub issue — it's the thing that stops an unscopable card being re-run every
   every minute forever, it's visible to the human who owns the card, and it clears itself
   the moment `last_moved_at` advances past the marker date. The ticket's **Add additional
   context** action—or a direct reply to Espresso's decision-bound project-chat
   request—writes an `autopr_additional_context` history event bound to the exact
   current no-spec/awaiting-answers note. That event makes the card eligible once without deleting audit
   history or pretending the card moved; a later AutoPR outcome replaces the note and
   therefore consumes the signal. New context submitted after an earlier failed-attempt
   marker can bypass that old cooldown once. A failed attempt otherwise cools down
   for 15 minutes, so five-minute ticks can work other cards instead of repeatedly
   starving the queue on one broken task. Caps at 10 open implementation
   `autopr` PRs (question-only drafts use their separate cap).
6. **`investigate.sh`** — the trusted host builds one context bundle containing the card,
   every checklist round, full task history/discussion, and task-file metadata. Up to 12
   attachments (25 MB total), prioritized to the current round, are downloaded by the
   trusted harness and attached locally; the model never needs board or storage network
   access. `todo` mode implements the card; `rework` mode additionally receives the
   existing PR's reviews/comments and addresses the latest `review_note`, rejection
   events, discussion, and screenshots without re-litigating accepted earlier rounds.
   It then calls `run-codex-sandboxed.sh`, which clones only tracked files into a
   dedicated msandbox workspace, removes the clone's remote, mounts an empty AWS
   directory, gives Codex only a read-only copy of its existing auth file, and strips
   GitHub/Matcha/SSH credentials. Codex runs `gpt-5.6-sol` with medium reasoning and broad permissions
   inside that disposable clone, while the trusted harness copies back only its patch,
   report, and decision. Both modes require a report with `### Summary` / `### Changes` / `### Blast radius` /
   `### Confidence` plus a shell-validated JSON triage decision. The card also contains
   the plan's related tickets and open bot PRs, including bounded comment/review excerpts,
   so the agent must choose prerequisite/build-on/separate boundaries in queue context.
   Additional-context events are untrusted but escalated evidence: the agent must trace
   the newly described uncovered scenario and cannot repeat `already_fixed` merely
   because a generic patch exists. A clear affirmative work command in that exact
   decision-bound reply—such as `you can work on this` or `you need to draft this PR`—
   becomes trusted `draft_pr` policy even without a magic prefix. `--draft-pr` remains
   the explicit form. Negated commands do not activate it. The policy mechanically
   rejects both `already_fixed` and `migration_required`: when needed, the draft may
   author only `server/alembic/versions/*.py` for human review and must never apply it.
   `--trust-still-broken` (including the matching
   natural-language form) accepts that the described scenario fails, while
   `--test-route=/app/...` asks the trusted browser to reproduce it in the approved test
   tenant. The coding model never receives those credentials. It must inspect correlated
   production errors/log signals and any test replay before asking for an exact route,
   role, reproduction steps, and screenshot. Missing product intent
   or evidence produces a question-only draft PR, not a no-spec marker. The card remains
   in `changes_requested` until a new human comment or review arrives on that PR; the
   next local cycle then updates the same draft. Without a trusted draft directive,
   no-spec remains available for already-fixed work, migrations, policy boundaries,
   and external dependencies.
7. **Cross-lane scope check** — for a fresh implementation patch, the shared
   `scripts/autopr-scope/check-open-prs.sh` checks older open PRs before verification
   or publication. Only an exact stable patch-id match suppresses the new PR; broader
   file-overlapping patches are untrusted public input and are surfaced with a
   `possible-duplicate` label for human review rather than executed by a model. The
   existing owner PR receives a `covers-kanban-task` label and exact task comment, while
   the card stores that PR's URL/number and a visible `ALREADY SCOPED` note.
   Closed-unmerged owners make the card eligible again; merged owners move every linked
   card to Review through the webhook or reconciliation pass.
8. **`verify.sh`** — there isn't one; this reuses `scripts/error-autofix/verify.sh`
   unmodified. It already diffs baseline-vs-branch TypeScript diagnostics via
   `tsc -p tsconfig.app.json --noEmit` (the non-bare form — bare `tsc --noEmit` checks
   nothing, see root CLAUDE.md), so no separate frontend step was needed.
9. **`write-publication-copy.sh`** — runs a separate writing-only Codex pass with
   `gpt-5.6-luna` and medium reasoning. It produces only a conventional commit subject
   and a short card note. Trusted shell validates the exact JSON schema, category prefix,
   one-line/length limits, and rejects any repository diff. For blocked/no-PR outcomes,
   the note explains the actual missing decision or safety boundary instead of repeating
   the status label.
10. **`publish.sh`** — same three-layer path guard as error-autofix (denylist, allowlist
   restricted to `server/(app|tests)/*.py`, `client/src/*.{ts,tsx}`, and
   `platforms/desktop/Espresso/Espresso/**/*.swift`, plus the
   `client.ts` telemetry-suppression guard), with `client/src/generated/` denylisted
   explicitly since a kanban card is far more likely to touch client code than an error
   fix is. Trusted `draft_pr` policy adds one narrow allowlist entry for
   `server/alembic/versions/*.py`; Alembic environment/configuration files remain denied,
   and the workflow never applies migrations. Without that policy a migration still
   takes the no-spec path and says why. PR titles begin
   with `🔴`, `🟠`, or `🟡` plus a computed confidence score so the default `gh pr list`
   is triaged visually. Question drafts also carry `autopr-awaiting-input`; those drafts
   do not consume the ten-PR implementation cap. PR body carries
   production baseline trailers as well as the task/project linkage:
   ```html
   <!-- matcha-task: <full task uuid> -->
   <!-- matcha-project: <full project uuid> -->
   <!-- matcha-production-build: <frontend build number> -->
   <!-- matcha-production-backend-sha: <active backend image SHA> -->
   <!-- matcha-production-frontend-sha: <active frontend image SHA> -->
   <!-- matcha-autopr-criticality: red|orange|yellow -->
   <!-- matcha-autopr-confidence-score: 0-100 -->
   <!-- matcha-autopr-note-state: awaiting_answers|ready_for_review|no_safe_action -->
   <!-- matcha-production-verification: <validated base64 JSON> -->
   ```
   `implementation` → `gh pr create --draft`, label `autopr` (+ `needs-work` on new
   failures), then PATCH the card's `pr_url`/`pr_number` and move it to `in_progress`.
   `questions_only` creates a no-product-change draft PR, applies
   `autopr-awaiting-input`, and leaves the card in `changes_requested` with a visible
   note such as `🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 550 · prod
   c5d3a49 · PR #295 · 🟡 C42 · note: Needs the canonical term before labels can be
   updated safely.`. `rework` updates the existing branch and PR;
   once there are no remaining blocking questions it returns the card to `in_progress`
   (this is the one transition `project_task_service` deliberately
   suppresses the notification email for — it already knows this is a rework resume, not
   a fresh start). A fresh `no_safe_action` PATCHes `progress_note` with a visible
   `🤖 AUTO SETUP · NO PR: …` state plus the durable no-spec marker
   without creating a branch, PR, or GitHub issue. During rework it updates the existing
   PR's title, body, and triage labels before writing the durable no-spec card note, so the
   prior round cannot remain visible as the current decision. When a run was triggered
   by additional context, the publisher also posts a threaded outcome reply to that
   history event and a decision-bound bell/push notification to its author: PR
   drafted/updated, questions still needed, or the no-safe-action decision still
   applies. Notification delivery is required so consuming the event cannot be silent.
   Awaiting-input and `already_fixed` outcomes also post one idempotent Espresso
   message into the project's discussion channel. It starts with the existing
   `⟦ticket:<id>|<title>|<column>⟧` token, so the ticket is clickable in Espresso.
   Replying directly to that message attaches the reply to the exact still-current
   AutoPR decision and acknowledges the escalation in chat; attached screenshots are
   copied onto the ticket so the next sandbox run can inspect them. A stale reply cannot
   reopen a newer decision.

## Work/merge plan and explicit release

The tmux overview shows the live plan id, clustered ticket work order, and merge order
for open **draft** bot PRs. Each merge row includes earlier overlapping PR dependencies,
blocking labels/checks/reviews, and related tickets still waiting for or processing
additional context. Ready-for-review PRs stay visible in the ordinary PR list but are
never put in this merge plan.

When the dashboard says the release is unblocked, the operator may run its printed
command (or dispatch the same workflow from Actions):

```sh
gh workflow run autopr-release-plan.yml -f plan_id=<exact-live-plan-id>
```

The trusted Mac rebuilds the plan from the live board and all open bot PRs. A stale id,
new comment/update, context contingency, `autopr-awaiting-input`, `needs-work`,
`possible-duplicate`, failed check, requested change, or unmerged predecessor
stops the release. Pending checks are shown in the plan but the released workflow waits
for them. Each merge position is pinned to the PR head commit captured by the plan;
any later push stops the release, and GitHub receives the same commit as an atomic merge
precondition. For each surviving draft, `release-plan.sh` marks it ready, waits for
GitHub to report it clean, squash-merges without `--admin`, verifies `MERGED`, and only
then evaluates the next PR against the new main. It never queues all PRs for unordered
auto-merge. If a check, timeout, or merge attempt fails after the ready transition, the
script restores the still-open PR to draft so a later authoritative plan can include it.

## Post-deploy production proof

Every implementation decision carries a reviewed production verification plan. A safe,
unauthenticated, read-only public behavior may specify up to five exact HTTP status/body
assertions. Authenticated, stateful, or visual behavior must specify a manual checklist;
it cannot claim automatic success.

After a successful blue/green swap, `update-ec2.sh` dispatches
`post-deploy-fix-verification.yml`. `verify-production-fixes.sh` considers a merged
AutoPR only when its merge commit is an ancestor of the deployed source SHA and the
required backend/frontend target is live. Passing automatic assertions add
`production-verified`; a failed assertion adds `production-verification-failed` and
does not mark the issue fixed. A failed result is terminal for automatic deploy checks:
later deploys skip it until an operator resolves the cause and removes the failure label
to request a fresh check. Manual plans add `production-verification-needed` and
post the exact checklist to the PR. The dashboard shows these states beside recently
merged Kanban PRs; error-autofix and self-audit lanes do not claim a production-check
state they never emit. After performing a manual checklist, record the observed result through
`record-production-verification.yml` (PR number, passed/failed, and bounded evidence);
it requires the outstanding manual-gate label and leaves an actor/run-linked PR audit
comment before replacing the label. Merge alone, or merge-to-main before deployment,
is never proof.

## Card ↔ PR linkage (`mw_tasks.pr_url` / `pr_number`)

Additive migration `taskpr0001`. Plumbed through the board SELECT
(`project_task_service.py`), the PATCH whitelist (`routes/matcha_work/tasks.py`), the
client types (`client/src/work/types.ts`), and a PR pill on the kanban card
(`KanbanCard.tsx`, next to the churn chip) linking out to `pr_url`.

The pull-request webhook resolves the primary card from a task trailer or task-shaped
branch, then unions every card carrying the exact persisted `pr_number`. The latter
supports cross-lane and multi-card ownership where one error-bot or human PR owns several
Kanban tasks; the existing repository and four-project allowlists still apply before any
card mutation.

## `post-checkout` hook (checkout → in_progress)

`scripts/kanban-autopr/hooks/post-checkout`, installed via `install-hooks.sh` as a
symlink into `.git/hooks/post-checkout` in the real clone (never `core.hooksPath` — that
would silently disable every other hook in the repo). Checking out a branch matching
`^(bot/task|task)-?/?([0-9a-f]{8})` — which covers both bot branches and a hand-made
`task/<id8>-...` branch, and `gh pr checkout <n>` (which names the local branch after the
PR head, so it matches the same regex with no special-casing) — backgrounds a
`curl --max-time 5` that logs in as the bot, finds the task by `id8` across the four
configured projects, and PATCHes `todo → in_progress` **only if** the card is currently in
`todo`. That guard is what makes it safe: checking out a branch whose card is already in
`review` or `done` does nothing, so the hook can never drag a card backwards. The hook
always `exit 0`s — it must never fail or slow down a checkout.

## `pull_request` webhook (`routes/matcha_work/github.py`)

Same public, HMAC-verified endpoint the push handler already uses
(`POST /matcha-work/public/github/webhook`). `install_repo_webhook` is shared by every
company that connects its own repo for commit-scanning — `GITHUB_WEBHOOK_SECRET` is one
global value across all of them, and turning on `WEBHOOK_EVENTS` upgrades every one of
those hooks to send `pull_request`, not just this repo's. Two independent boundaries
close that off before resolution ever runs:

- **Repo scope** — `payload.repository.full_name` must equal `_KANBAN_AUTOPR_REPO`
  (`KANBAN_AUTOPR_REPO` env, defaults to `tajaa/matcha-recruit`). A PR opened against any
  other connected customer repo is ignored outright.
- **Project allowlist** — the resolved task's `project_id` must be one of
  `_KANBAN_AUTOPR_PROJECT_IDS` (kept in sync with `scripts/seed/autopr_bot.py`'s
  `PROJECTS` list). Even a legitimate PR in this repo can't move a card outside the four
  target projects.

Primary task resolution, in order: the `<!-- matcha-task: <uuid> -->` trailer in the PR
body; else the `bot/task-<id8>` / `task/<id8>-...` head-branch prefix matched against
`mw_tasks.id` with hyphens stripped (same regex the `post-checkout` hook uses — this is
what lets a human's own hand-made branch work too, not just bot-authored PRs). Every
additional card whose persisted `pr_number` matches is included and deduplicated before
the transition. Column moves are a no-op unless the card is currently in the listed source
column; metadata is written only when it changed. Redelivery is therefore idempotent, and
a webhook replay can never drag a card backwards:

| action | from | to | also |
|---|---|---|---|
| `opened`, `reopened` | `todo` | `in_progress` | write `pr_url`, `pr_number` |
| `closed` with `merged == true` | `todo`, `in_progress`, `changes_requested` | `review` | write the visible `🤖 AUTO SETUP · MERGED: READY FOR REVIEW · build … · prod … · PR #…` note; reconstruct production plus current criticality/confidence from PR trailers if the original card PATCH failed; refresh `pr_url`/`pr_number` |
| `closed` with `merged == true` | `review` | `review` | add/recover the same origin/build note and PR link; never move the card backwards |
| `closed` with `merged == false` | — | — | no move |
| anything else | — | — | ignore |

`review → done` stays manual through `POST /tasks/{id}/approve` — a merge is not an
approval. AutoPR never deploys. The only merge mutation is the separately dispatched,
exact-plan-id release described above.

The persistent runner may check out a local `bot/task-*` branch while assembling
the PR. Its always-run finalizer switches a clean task checkout back to `main`
after publication. It refuses to erase dirty state. Human/agent work may likewise
use temporary worktrees for isolation, but the exact temporary worktree is removed
immediately after its PR is submitted; submitted PR branches are never left checked
out in a worktree.
