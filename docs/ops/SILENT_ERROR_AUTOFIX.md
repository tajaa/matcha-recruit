# Silent Error Autofix

`.github/workflows/silent-error-autofix.yml` runs from the same Mac-owned one-minute
LaunchAgent clock as Kanban AutoPR. GitHub's best-effort cron was removed after it left
multi-hour gaps. When no AutoPR workflow is active, the dispatcher gives this lane the
next slot if its last completed pass is at least ten minutes old; otherwise it advances
the six-hour AutoPR self-audit when due, then Kanban. The unit of work is one normalized incident from
`server_error_reports` or `client_error_reports`, not a log window. Server rows retain
their established stable keys; raw browser rows use a separate `client|` keyspace and
group by normalized message, route, frame, and component context.

The collector still looks back 24 hours. That is a recovery window, not the
schedule: selection dedupes against GitHub and the local attempt cache, prioritizes
`last_seen` so a fresh single occurrence cannot sit behind an older high-count error,
and a wide lookback catches incidents missed during runner downtime without
reinvestigating handled incidents on every pass.

Pipeline (`scripts/error-autofix/`):

1. **`reconcile.sh`** — before collection, compares each open `bot/err-*` draft with
   recent, later human-merged PRs that overlap its files. Codex Sol-medium must return a
   strict, high-confidence semantic-equivalence verdict before the bot labels and
   closes a draft as superseded. It appends the human merge timestamp so a post-deploy
   recurrence can re-enter the queue. This pass has no production credentials.
2. **`collect.sh`** — SSHes to the app EC2, `docker exec`s into the live backend
   container, and runs read-only `SELECT`s (enforced at the connection level, not by
   convention) against both reporting tables. Server rows are grouped by the existing
   date-and-value-free `stable_key`; client rows normalize asset hashes, line numbers,
   dynamic paths, and values before grouping. It excludes browser-extension, local,
   stale-chunk, and transport noise. A client API error is suppressed only when its
   request ID and normalized endpoint match a collected server incident. Free-text
   evidence is redacted after it leaves production; structural fields survive unchanged.
   Falls back to `scripts/collect-silent-error-evidence.sh` if the DB path fails.
3. **`select.sh`** — picks one incident GitHub hasn't already handled. Checks
   `gh pr list --head bot/err-<key> --state all`: open → skip; merged → skip unless a
   genuine recurrence is seen well after a deploy-grace window **and** — when the
   workflow resolved the deployed build from `https://hey-matcha.com/version.json`
   (`AUTOFIX_DEPLOYED_SHA`) — the merge commit is an ancestor of it (deploys are
   manual, so "merged" is not "live"; an undeployed fix used to be re-investigated
   every two hours until the next rollout and open a duplicate PR); closed-unmerged →
   skip for a 7-day cooldown, not forever. An open `autofix-nofix` issue suppresses its
   incident for 7 days after the bot last concluded "no safe fix" — the timestamp
   `publish.sh` stamps into the issue body, which it rewrites on every
   re-investigation. Deliberately not the issue's `updatedAt`: a human commenting
   "still broken" would otherwise extend the suppression another full week. Also caps total open
   `autofix`-labeled PRs; a failed count read is fatal, never "no cap". Attempt
   markers older than 7 days are pruned on every pass.
3b. **`verify-deployed-fixes.sh`** — right after collection, for every merged `autofix`
   PR whose merge commit is in the deployed build and whose 6-hour grace window has
   passed: fingerprint silent → `production-verified`; fingerprint recurred →
   `production-verification-failed` (and `select.sh` re-opens it). This is the only
   place that ever confirms a production error actually stopped.
   The grace window opens at the **deploy**, not the merge. `version.json` names
   the live SHA but not when it shipped, and deploys are manual, so the lane keeps
   a small ledger (`~/.cache/matcha-autofix/deployed-sha-first-seen.json`) of when
   it first saw each build live and scores from the earliest observed deploy that
   contained the merge. Without it a fix merged weeks before its rollout was failed
   by occurrences that all predate the deploy — and the label is permanent.
   Verdicts are also bounded by the evidence: the incident snapshot only covers
   `AUTOFIX_HOURS` (job-level env, shared with `collect.sh`), so the comment states
   the window and limit the "has not recurred" claim actually rests on.
4. **`investigate.sh`** — one sandboxed `codex exec` with
   `gpt-5.6-sol` and medium reasoning in a disposable tracked-files-only clone,
   with evidence copied into the clone and enumerated in a bounded prompt. It must produce
   a markdown report with four required headings (Root cause / Fix / Blast radius /
   Confidence) plus a shell-validated JSON decision. The decision independently scores
   confidence and classifies criticality as red/orange/yellow. **The model never
   reports test results** — that's the next script's job, and anything it writes about
   tests there is discarded. The CLI is ephemeral, ignores user config, and receives no
   GitHub, production, or Matcha credentials.
5. **Cross-lane scope check** — `scripts/autopr-scope/check-open-prs.sh` captures the
   uncommitted proposal with a temporary Git index, prefilters open PRs targeting
   `main` by changed-file overlap, and suppresses publication only for an exact stable
   patch-id match. Broader overlaps are untrusted public input, so they are never
   executed by a model; the draft still publishes with `possible-duplicate` for human
   review. An exact-match owner PR gets a
   `covers-prod-error` label and an idempotent
   `<!-- matcha-autofix-coverage-error: <key> -->` comment; `select.sh` enumerates those
   comments directly as its durable ledger. Uncertain comparisons still publish and are
   labeled `possible-duplicate`.
6. **`verify.sh`** — runs the same backend checks against `main` and the branch and
   diffs *failing test node IDs* rather than counts. For client changes, it shares the
   runner's existing `client/node_modules` with the baseline worktree, compares
   TypeScript diagnostics, and runs changed or colocated Vitest files against both
   trees. Missing verification dependencies label a draft `needs-work`; they never
   trigger an unpinned install in the scheduled workflow.
7. **`write-commit-subject.sh`** — uses Codex Luna-medium for the bounded commit
   subject after verification. Trusted shell enforces the `fix:` prefix, one-line
   72-character limit, and rejects any repository edit from this writing-only pass.
8. **`publish.sh`** — opens a draft PR with a body assembled from the incident +
   report + verification table (endpoint, occurrence count, admin link, traceback,
   correlated log lines). The PR title, labels, and durable body trailers carry the same
   `🔴` / `🟠` / `🟡` criticality and C0–100 confidence presentation as Kanban
   AutoPR. If the model made no diff, opens or replaces a tracking issue
   body instead of silently doing nothing. Replacing the original placeholder body is
   essential: placeholders stay retryable after a failed run, while finalized no-fix
   reports stop queue starvation. A successful draft closes its matching no-fix issue.
9. **`notify-review-ready.sh`** — after a reviewable PR exists, uses the trusted SSH
   harness to call the live backend's already-configured Gmail/MailerSend transport and
   emails `aaron@hey-matcha.com` with the production error, triage, and PR link. A
   durable PR comment makes delivery idempotent; the next pass retries any opted-in open
   PR whose send failed after publication.

It never deploys or auto-merges. A human reads the PR body and decides.

## One-time setup

1. Register the GitHub Actions self-hosted runner on this Mac with labels
   `self-hosted`, `macOS`, `opencode`, run as Finch's logged-in user. `opencode` is the
   legacy runner-registration label and does not select the execution engine.
2. Ensure `codex login status` succeeds for that runner user and the installed Codex CLI
   supports `gpt-5.6-sol` and `gpt-5.6-luna`.
3. Keep repository secret `EC2_SSH_KEY` configured — used only for the read-only DB
   query and, as a fallback, log collection.
4. Add repository variables `PROD_HEALTH_URL` / `PROD_API_HEALTH_URL` for the fallback
   path's health probes. Empty skips them.
5. Install/reinstall `scripts/kanban-autopr/install-launch-agent.sh`; that one local
   timer owns all three AutoPR lanes. Use `workflow_dispatch` once to verify connectivity.
6. `server/venv` on this Mac must have `pytest` and `pytest-asyncio` installed
   alongside the app's own requirements (`verify.sh` reuses this venv rather than
   building one, so it needs to already work): `server/venv/bin/pip install pytest
   pytest-asyncio`.

## Guardrails

- **Client `request_id` is attacker-controlled.** A browser incident's id comes from
  the free-form `context` dict of the unauthenticated `POST /api/client-errors`
  endpoint, and `fetch-correlated-log.sh` interpolates it into a shell command that
  runs on the production host. `_query.py` drops any id outside `[A-Za-z0-9-]{4,64}`
  and the fetch script refuses one again before `ssh` — never quote around it instead.
- **Model patches never reach `scripts/`, `.github/`, `deploy/`, `docker/`, compose
  files, Dockerfiles, `.env*`, `.claude/`, `.codex/`, or `secrets/`.** The sandbox
  bridge (`kanban-autopr/run-codex-sandboxed.sh`) rejects them at apply time, before
  any later workflow step executes a script out of the checkout. `publish.sh`'s
  denylist is the second gate, not the first.
- **Review-ready mail is sent only for markers the automation wrote.** `--reconcile`
  reads the `<!-- matcha-autofix-notify-review: … -->` marker from bot-authored PR
  bodies and `[bot]`/`matcha-*` comments only; a human pasting the marker cannot make
  the harness exec into the production container. The in-container snippet calls
  `load_settings()` first — without it every send died with `Settings not initialized`.
- **One Codex login, one backoff.** A `usage limit` exit inside any lane writes
  `~/Library/Caches/matcha-autopr-dashboard/dispatch/codex-usage-limit.json`
  (`kanban-autopr/codex-backoff.sh`); the Mac dispatcher launches no lane until the
  quoted "try again at" time (capped at 24 h, default 1 h when unparseable).

- The model receives redacted evidence only, attached as a file — never interpolated
  into the prompt string — and only the traceback frames under this app's own source
  tree, capped to 25 lines. The prod SSH key is deleted **before** the model step runs.
- The model cannot change `.github/`, `deploy/`, `scripts/`, migrations, dependencies,
  lockfiles, env files, generated client code, error reporters, error boundaries, or
  telemetry/notifier code. `publish.sh` additionally requires every staged path to be
  `server/app/**/*.py`, `server/tests/**/*.py`, or `client/src/**/*.ts(x)`. It rejects
  changes to the browser report-status policy even though `client.ts` is otherwise in
  the client allowlist.
- `kind`/`exception_type` denylist in `_query.py` skips infra errors (connection resets,
  timeouts, pool exhaustion) that a code diff can't fix — investigating them just burns
  a run on a PR that can't be right.
- `WHERE resolved_at IS NULL` doubles as the server-side human "stop bothering me"
  switch. Client reports have no resolved column, so their stable key plus the GitHub
  PR/no-fix lifecycle is the durable dedup ledger. Nothing in deployment resolves
  telemetry automatically.
- Failures fail loud where it matters (SSH/DB unreachable, path guard tripped, PR push
  failed, or an incomplete model investigation) and degrade gracefully where it doesn't
  (no incidents found, verification toolchain missing → PR still opens, labeled
  `needs-work`, with an explicit "checks did not run" banner — never a silently blank
  table).
- `AUTOPR_SCOPE_DEDUPE_MODE=off|observe|enforce` is the rollback switch. The workflows
  currently pin `enforce`; `observe` records an exact-match verdict in the job summary
  without suppressing a PR.

## Known gap

Bot-opened PRs get **zero** GitHub-hosted CI checks — a PR opened with the default
`GITHUB_TOKEN` doesn't trigger `pull_request` workflows, and `ci.yml` has no `push:`
trigger. `verify.sh`'s inline table is the substitute, and it's more thorough than
`ci.yml` anyway (which runs no backend tests) — but there's no green checkmark in the
PR UI. Revisit with a PAT/GitHub App token only if that visual signal turns out to
matter more than the extra secret it costs.
