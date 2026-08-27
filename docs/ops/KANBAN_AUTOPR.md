# Kanban Autopr

`.github/workflows/kanban-autopr.yml` is scheduled every 5 minutes on the same
self-hosted Mac runner as `silent-error-autofix.yml`. The runner has one job slot, so a
long coding job can delay the next start; the workflow concurrency group collapses
queued ticks and prevents overlap. The unit of work is one kanban card assigned to
`haley@oceaneca.com` sitting in `todo` or `changes_requested`, across four fixed
Espresso projects — WerkWerk, Beetlejuse, Gummfit, and MATCHA. It never scans the whole
board or every user's cards.

The board is the source of truth in both directions: a card drives a PR, and a PR drives
a card back. The bot never merges and never approves.

**Design constraint carried over from silent-error-autofix**: no model credential and no
Matcha credential goes into GitHub secrets. The runner is Finch's Mac running as Finch's
user; OpenCode uses that user's profile, and the Matcha bot credential lives in
`~/.config/matcha-autopr/env` (`chmod 600`, never committed).

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
   ```
   Scheduled GitHub runs fail closed if `MATCHA_API_URL` points at localhost or
   if any of the four project ids is missing. This prevents a production PR from
   being linked to a dev-only card.
3. Install the checkout hook in the real clone: `./scripts/kanban-autopr/install-hooks.sh`.
4. Upgrade the repo's GitHub webhook to also deliver `pull_request` (idempotent — safe to
   re-run against an already-installed hook): call the existing
   `POST /matcha-work/projects/{id}/github/install-webhook` admin endpoint, or re-run
   whatever originally installed it. `install_repo_webhook` now PATCHes an existing
   hook's event list up to `["push", "pull_request"]` instead of no-op'ing on a URL match.
5. `gh workflow run kanban-autopr.yml` once by hand before relying on the cron schedule.

## Pipeline (`scripts/kanban-autopr/`)

1. **`collect.sh`** — one `GET /projects/{id}/bundle` per project in `MATCHA_PROJECT_IDS`
   (there is no company-wide list endpoint the bot can use — its access is per-project
   collaborator rows, not one company scope). Filters to cards assigned to
   `MATCHA_ASSIGNEE_EMAIL` in `todo`/`changes_requested`, joins each card's `element_id`
   against the bundle's `elements` array to attach `repo_paths` (prompt-only scoping, not
   a gate).
2. **`select.sh`** — picks one card GitHub hasn't already handled. Branch key is
   `bot/task-<id8>` (first 8 hex of the task UUID). Ranks `changes_requested` before
   `todo` (rework is better-specified — it has a written `review_note` — and unblocks a
   PR already in flight), then oldest `last_moved_at` first. For `todo`, any PR at all on
   the branch (open/closed/merged) means skip — the branch name is a stable 1:1 mapping
   to the task, so a second run would collide. For `changes_requested`, an **open** PR on
   the branch is the *target* to push to (`mode: rework`); no open PR means a human moved
   it there by hand, so it's treated like a fresh `todo` card. A durable no-spec ledger
   lives on the card itself (`progress_note` prefixed `[autopr:no-spec <date>]`) rather
   than a GitHub issue — it's the thing that stops an unscopable card being re-run every
   five minutes forever, it's visible to the human who owns the card, and it clears itself
   the moment `last_moved_at` advances past the marker date. A failed attempt cools down
   for 15 minutes, so five-minute ticks can work other cards instead of repeatedly
   starving the queue on one broken task. Caps at 3 open `autopr` PRs.
3. **`investigate.sh`** — both modes receive a single context bundle containing the card,
   every checklist round, full task history/discussion, and task-file metadata. Up to 12
   attachments (25 MB total), prioritized to the current round, are downloaded by the
   trusted harness and attached locally; the model never needs board or storage network
   access. `todo` mode implements the card; `rework` mode additionally receives the
   existing PR's reviews/comments and addresses the latest `review_note`, rejection
   events, discussion, and screenshots without re-litigating accepted earlier rounds.
   Both require a
   report with `### Summary` / `### Changes` / `### Blast radius` / `### Confidence`.
   Bails to the no-spec path on `Confidence: none`, no diff, or more than 25 changed
   files — a card that sprawls needed a human to scope it.
4. **`verify.sh`** — there isn't one; this reuses `scripts/error-autofix/verify.sh`
   unmodified. It already diffs baseline-vs-branch TypeScript diagnostics via
   `tsc -p tsconfig.app.json --noEmit` (the non-bare form — bare `tsc --noEmit` checks
   nothing, see root CLAUDE.md), so no separate frontend step was needed.
5. **`publish.sh`** — same three-layer path guard as error-autofix (denylist, allowlist
   restricted to `server/(app|tests)/*.py` and `client/src/*.{ts,tsx}`, plus the
   `client.ts` telemetry-suppression guard), with `client/src/generated/` denylisted
   explicitly since a kanban card is far more likely to touch client code than an error
   fix is. A card that genuinely needs a migration or infra change cannot be auto-PR'd —
   that's the intended outcome; it takes the no-spec path and says why. PR title is
   prefixed from the card's `category` (`feat:`/`fix:`/else `chore:`). PR body carries
   two machine trailers other steps depend on:
   ```html
   <!-- matcha-task: <full task uuid> -->
   <!-- matcha-project: <full project uuid> -->
   ```
   `todo` → `gh pr create --draft`, label `autopr` (+ `needs-work` on new failures), then
   PATCH the card's `pr_url`/`pr_number` and move it to `in_progress`. `rework` → push to
   the existing branch, `gh pr edit` to refresh the body + add `autopr-rework`, then PATCH
   to `in_progress` (this is the one transition `project_task_service` deliberately
   suppresses the notification email for — it already knows this is a rework resume, not
   a fresh start). No diff → PATCH `progress_note` to the no-spec marker; no branch, no
   PR, no GitHub issue.

## Card ↔ PR linkage (`mw_tasks.pr_url` / `pr_number`)

Additive migration `taskpr0001`. Plumbed through the board SELECT
(`project_task_service.py`), the PATCH whitelist (`routes/matcha_work/tasks.py`), the
client types (`client/src/work/types.ts`), and a PR pill on the kanban card
(`KanbanCard.tsx`, next to the churn chip) linking out to `pr_url`.

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

Task resolution, in order: the `<!-- matcha-task: <uuid> -->` trailer in the PR body;
else the `bot/task-<id8>` / `task/<id8>-...` head-branch prefix matched against
`mw_tasks.id` with hyphens stripped (same regex the `post-checkout` hook uses — this is
what lets a human's own hand-made branch work too, not just bot-authored PRs). Column
moves are a no-op unless the card is currently in the listed source column; metadata is
written only when it changed. Redelivery is therefore idempotent, and a webhook replay
can never drag a card backwards:

| action | from | to | also |
|---|---|---|---|
| `opened`, `reopened` | `todo` | `in_progress` | write `pr_url`, `pr_number` |
| `closed` with `merged == true` | `todo`, `in_progress`, `changes_requested` | `review` | prepend `from auto setup` without discarding an existing note; refresh `pr_url`/`pr_number` |
| `closed` with `merged == true` | `review` | `review` | add the same origin note and PR link; never move the card backwards |
| `closed` with `merged == false` | — | — | no move |
| anything else | — | — | ignore |

`review → done` stays manual through `POST /tasks/{id}/approve` — a merge is not an
approval.

It never deploys or auto-merges. A human reads the PR body and decides.
