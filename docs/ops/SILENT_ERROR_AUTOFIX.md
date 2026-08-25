# Silent Error Autofix

`.github/workflows/silent-error-autofix.yml` runs every 10 minutes on this Mac's self-hosted
GitHub Actions runner. The unit of work is **one row (grouped by stable key) in
`server_error_reports`**, not a log window — that's the fix for the original problem,
where five PRs (#242-#247) were opened for two bugs because the whole 20-minute log
window was hashed as one "incident".

The collector still looks back 24 hours. That is a recovery window, not the
schedule: selection dedupes against GitHub and the local attempt cache, so a wide
lookback catches incidents missed during runner downtime without reinvestigating
handled incidents every 10 minutes.

Pipeline (`scripts/error-autofix/`):

1. **`collect.sh`** — SSHes to the app EC2, `docker exec`s into the live backend
   container, and runs a read-only `SELECT` (enforced at the connection level, not by
   convention) against `server_error_reports`. Groups rows by a date-and-value-free
   `stable_key` (`_query.py:stable_key`) so the same bug spanning UTC-day boundaries, or
   carrying different bound values, collapses into one incident. Redacts free-text
   fields only (`message`, `traceback`, `request_path`) — structural fields
   (`stable_key`, `error_id`, `occurrences`, timestamps) are left alone. Falls back to
   the older `scripts/collect-silent-error-evidence.sh` log-grep if the DB path fails.
2. **`select.sh`** — picks one incident GitHub hasn't already handled. Checks
   `gh pr list --head bot/err-<key> --state all`: open → skip; merged → skip unless a
   genuine recurrence is seen well after a deploy-grace window; closed-unmerged → skip
   for a 7-day cooldown, not forever. Also caps total open `autofix`-labeled PRs.
3. **`investigate.sh`** — one `opencode run`, evidence attached as a file (not
   interpolated into the prompt), that must produce a markdown report with four
   required headings (Root cause / Fix / Blast radius / Confidence). **The model never
   reports test results** — that's the next script's job, and anything it writes about
   tests there is discarded. `--` terminates the repeated `--file` option before the
   prompt; without it OpenCode interprets the prompt itself as another attachment.
4. **`verify.sh`** — runs the same checks against `main` and the branch and diffs
   *failing test node IDs* (not counts), so a pre-existing failure never counts against
   the PR. Uses the dev venv (`server/venv`) as the interpreter rather than building a
   fresh one — `requirements.txt` pins with `>=`, so hashing it wouldn't actually pin
   anything, and neither `pytest` nor `pytest-asyncio` are in it.
5. **`publish.sh`** — opens a draft PR with a body assembled from the incident +
   report + verification table (endpoint, occurrence count, admin link, traceback,
   correlated log lines). If the model made no diff, opens/updates a tracking issue
   instead of silently doing nothing.

It never deploys or auto-merges. A human reads the PR body and decides.

## One-time setup

1. Register the GitHub Actions self-hosted runner on this Mac with labels
   `self-hosted`, `macOS`, `opencode`, run as Finch's logged-in user (its
   OpenCode/OpenAI auth and `server/venv` live under that user).
2. Ensure `opencode models openai` lists `openai/gpt-5.6-luna` for that runner user.
3. Keep repository secret `EC2_SSH_KEY` configured — used only for the read-only DB
   query and, as a fallback, log collection.
4. Add repository variables `PROD_HEALTH_URL` / `PROD_API_HEALTH_URL` for the fallback
   path's health probes. Empty skips them.
5. Enable the workflow under Actions; `workflow_dispatch` once to verify connectivity.
6. `server/venv` on this Mac must have `pytest` and `pytest-asyncio` installed
   alongside the app's own requirements (`verify.sh` reuses this venv rather than
   building one, so it needs to already work): `server/venv/bin/pip install pytest
   pytest-asyncio`.

## Guardrails

- The model receives redacted evidence only, attached as a file — never interpolated
  into the prompt string — and only the traceback frames under this app's own source
  tree, capped to 25 lines. The prod SSH key is deleted **before** the model step runs.
- The model cannot change `.github/`, `deploy/`, `scripts/`, migrations, dependencies,
  lockfiles, or env files (denylist, unchanged from the original workflow — this is
  what stops the bot rewriting its own harness). `publish.sh` additionally **requires**
  every staged path to match `server/(app|tests)/*.py` (allowlist) — strictly stronger,
  and it closes paths the denylist never named (`CLAUDE.md`, `docs/`, `client/`,
  `.claude/`, ...).
- `kind`/`exception_type` denylist in `_query.py` skips infra errors (connection resets,
  timeouts, pool exhaustion) that a code diff can't fix — investigating them just burns
  a run on a PR that can't be right.
- `WHERE resolved_at IS NULL` doubles as the human "stop bothering me" switch: the only
  writer of `resolved_at` is a person clicking Resolve in `/admin/server-errors` —
  nothing in the deploy path resolves anything automatically.
- Failures fail loud where it matters (SSH/DB unreachable, path guard tripped, PR push
  failed, or an incomplete model investigation) and degrade gracefully where it doesn't
  (no incidents found, verification toolchain missing → PR still opens, labeled
  `needs-work`, with an explicit "checks did not run" banner — never a silently blank
  table).

## Known gap

Bot-opened PRs get **zero** GitHub-hosted CI checks — a PR opened with the default
`GITHUB_TOKEN` doesn't trigger `pull_request` workflows, and `ci.yml` has no `push:`
trigger. `verify.sh`'s inline table is the substitute, and it's more thorough than
`ci.yml` anyway (which runs no backend tests) — but there's no green checkmark in the
PR UI. Revisit with a PAT/GitHub App token only if that visual signal turns out to
matter more than the extra secret it costs.
