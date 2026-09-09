# msandbox + AutoPR + error-bot review — 2026-09

Review of the autonomous tooling around this repo: `msandbox` (the Docker agent
sandbox and its control plane), the Kanban AutoPR lane
(`scripts/kanban-autopr/`, `.github/workflows/kanban-autopr.yml`), the silent
error autofix lane (`scripts/error-autofix/`, `silent-error-autofix.yml`), the
AutoPR self-audit lane (`scripts/autopr-self-audit/`, `autopr-self-audit.yml`),
and the Espresso kanban they read/write through `mw_tasks` and the
`pull_request` webhook.

This is the durable record: what was measured, the ranked findings, what
**batch A** fixed (this document's PR), and the **batch B** backlog. Nothing in
batch A changes the trust model; every fix is a guard, a cache, a gate, or a
bug.

## What was measured (2026-09-07)

Sources: repo at `6af17c6`, GitHub PR search, Actions run history and job
logs, git log, the dispatch log on the Mac
(`~/Library/Logs/matcha-kanban-autopr-dispatch.log`), the installed LaunchAgents,
baseline runs of the contract tests, and three read-only code audits (msandbox,
kanban-autopr + Espresso sync, error bot). Every finding was re-checked in
source before ranking.

| Signal | Value |
|---|---|
| Commits in last 60 days touching msandbox/autopr/autofix/kanban | 103 of ~353 (29%) |
| Kanban AutoPR PRs (label `autopr`, since 2026-08-26) | 45 opened, 41 merged, 1 open |
| … labeled `needs-work` ("verification found a new test failure") | 27 of 45 (60%), yet 41 merged |
| Error-bot PRs (label `autofix`, since 2026-08-25) | 18 opened, 12 merged, 2 superseded |
| `kanban-autopr.yml` runs | 1334 total; last 100 all on 2026-09-06: median 36 s, 98/100 under 3 min, 93/99 inter-run gaps = 1.1 min |
| `silent-error-autofix.yml` runs | 289 total; ~30/day; median 48 s |
| `autopr-self-audit.yml` runs | 15 total, **15 failures**, one every ~6 h since 2026-08-31 |
| Dispatch log, 2026-09-06/07 | 148 × `dispatch kanban-pass`, 26 × error, 4 × self-audit, 84 × `skip active-autopr-workflow`; log file 7 MB, never rotated |
| Installed dispatcher (`~/.local/share/matcha-kanban-autopr/`) | dated 2026-08-31, differs from repo; scheduler plist `StartInterval` **60**, no request-watch plist installed |
| `~/.cache/matcha-autopr/attempts/` | 56 markers, never pruned |
| Baseline contract tests | kanban 130/130, dispatch 24/24, error-autofix 34/34 on this Mac (32/34 on the runner's Python: no asyncpg), self-audit pass, prod-verification pass |

Job-log spot checks:

- Self-audit run 34076697512 (2026-09-07): Codex `gpt-5.6-sol` starts, then
  `ERROR: You've hit your usage limit … try again at 5:31 AM`. Run
  33846163268 (2026-09-04): Codex produced the one-file fix (lazy-load asyncpg
  in `_query.py`) and the sealed `verify.sh` rejected it → discarded.
- Kanban run 34065927946 (2026-09-06 23:06): gate failed with `production
  backend SHA c7cce8c is not an ancestor of main`. `c7cce8c` **is** on
  `origin/main`.
- Kanban run 34021383686 (no-op, 35 s): checkout 5 s → 12 sequential `gh label
  create` 8 s → SSH to prod 5 s → 4 board bundle GETs → reconcile → plan →
  select → "Nothing to build". Twenty steps skipped. Dispatched again 66 s later.
- Error-bot run 34107465696 (2026-09-07 09:41): PR #451 opened, then
  `notify-review-ready.sh` crashed inside the production backend container:
  `RuntimeError: Settings not initialized. Call load_settings() first.`

## Findings, ranked

Status legend: **A** = fixed in batch A (this PR); **B** = backlog; **doc** =
documented only.

### P0 — security / trust boundary

**F1 (A). Shell injection on the prod app host from the unauthenticated
client-error endpoint.** `fetch-correlated-log.sh` sent an unquoted heredoc to
`ssh_prod` containing `grep -F "[rid=$request_id]"`. For client incidents
`request_id` is `context.get("request_id")` in `_query.py`; `context` is a
free-form dict accepted by `POST /api/client-errors` (auth optional, per-IP
rate limit only). `collect.sh` redacted message/traceback/path/company but not
`request_id`. Server-side ids are validated in `request_context.py`; client
ones were not. *Fix:* `_query.py` emits only ids matching
`^[A-Za-z0-9-]{4,64}$` (both surfaces; the raw id is still used for server↔client
correlation); `fetch-correlated-log.sh` re-validates and refuses before `ssh`.
Tests: `test_error_autofix.sh` (hostile id never reaches the ssh stub),
`test_error_autofix_query.py`.

**F2 (A, partial). Model-written scripts execute in the trusted job.**
`kanban-autopr.yml` snapshotted only `scripts/kanban-autopr` +
`scripts/error-autofix` into `$AUTOPR_CONTROL_ROOT`, but ran
`./scripts/autopr-scope/check-open-prs.sh` and
`./scripts/kanban-autopr/record-coverage.sh` from the workspace after the
model's patch had been applied there (`run-codex-sandboxed.sh` checked only
symlinks/gitlinks/file count; the `^scripts/` denylist lived in `publish.sh`,
which runs later). The error and self-audit lanes ran *every* post-model step
from the workspace. *Fix:* the bridge now rejects, at apply time, any patch
touching `.github/`, `deploy/`, `docker/`, `scripts/`, `.claude/`, `.codex/`,
`.githooks/`, `secrets/`, `opencode.jsonc`, compose files, Dockerfiles, `.env*`
(`AUTOPR_SANDBOX_PATH_DENY_RE`; the self-audit lane narrows it to
CI/deploy/secrets/capsule because repairing the harness is its job). The Kanban
archive now includes `scripts/autopr-scope` and the alembic graph helpers, and
the scope check + coverage recording run from the control root. *Left as-is,
documented:* `AUTOPR_MSANDBOX_BIN` still points at the workspace's
`agent-sandbox.sh` — it resolves compose files and the `msandbox` package from
its own location, so a snapshot copy would need the whole runtime tree. The
denylist is what protects it. Tests: `test_kanban_autopr.sh` (patch touching
`scripts/` refused before apply; self-audit narrowing works; workflow grep
contracts).

**New (A). Control-root archive lacked `scripts/alembic_graph_snapshot.py`.**
`lib.sh:autopr_migration_draft_errors` resolves `../alembic_graph_snapshot.py`
relative to itself, so from the control root every migration-drafting card got
`python3: can't open file …` captured as a migration error → the
`migration_draft_invalid` correction, then a publish refusal. Fixed by the wider
archive above. Worth confirming against the next migration card.

### P1 — loops that burn money or block work

**F3 (A). Self-audit: 15/15 failures, one Codex Sol run every 6 h, zero output,
and it exhausted the one ChatGPT quota all lanes share.** Root cause:
`_query.py` imported `asyncpg` at module scope; `test_error_autofix.sh` imports
`stable_key` with the runner's host Python, which lacks asyncpg → 2 failures →
`audit.sh` flags `contract_tests` as repo-repairable → Codex writes the
lazy-import fix → `verify.sh` re-runs the same host-Python test → still fails
(the *host* is what lacks asyncpg) → patch discarded → repeat. *Fix:* (a)
`asyncpg` imported inside `main()` (fixes both tests on any Python); (b)
`repair-ledger.sh` — the same repo-repairable failure set is handed to Codex
once, not every 6 h, until the fingerprint changes or 7 days pass; the audit
itself still runs every 6 h and notices a merged fix immediately; (c)
`codex-backoff.sh` — a `usage limit` exit in any lane writes a marker with the
quoted "try again at" time and the dispatcher launches no lane until then
(capped 24 h). Tests: `test_autopr_self_audit.sh`, `test_kanban_autopr_dispatch.sh`,
`test_kanban_autopr.sh`.

**F4 (A + operator). Kanban re-dispatched a 35-second no-op run every 66 s for
hours.** The dispatch log names the mechanism: 148 × `dispatch kanban-pass`
from the *scheduler* path, not the request watcher. The installed
`com.matcha.kanban-autopr-dispatch.plist` has `StartInterval 60` and the
installed `dispatch-if-idle.sh` (2026-08-31) predates the twenty-minute Kanban
floor, `run-snapshot.sh`, and the request watcher (which is not installed at
all). The repo's five-minute/twenty-minute design never reached the machine.
*Operator action (not done here — it changes the machine):*
`./scripts/kanban-autopr/install-launch-agent.sh`. *Fixes in repo:*
`hot-redispatch-guard.sh` runs first in the workflow and skips a pass when the
previous completed Kanban run ended < 5 min ago (GitHub-side floor, fails open
on API error); the dispatcher remembers the request set it last forced so one
button press costs at most one forced run per request TTL even if the run dies
before claiming; `audit.sh` now reports a stale installed dispatcher or wrong
plist intervals as an operator action; the dispatch log rotates at 5 MB.

**F5 (A). Production-freshness gate compared against a stale local `main`.**
`resolve-production-context.sh` used `main` in the persistent runner clone.
*Fix:* best-effort `git fetch origin main`, then compare against `origin/main`
→ `main` → `HEAD`, first that resolves. Test: fixture repo whose local main lags
origin by the deployed commit.

**F6 (A now, B later). Error-bot notifier executed Python inside the live prod
container and was broken.** *Fix now:* `load_settings()` before
`get_email_service()`; `--reconcile` scans only bot-authored bodies/comments
for the notify marker. *B:* notify from the runner (SES/SMTP creds on the Mac),
not by `docker exec` into prod.

**F7 (A). Every no-op Kanban run paid the full prelude.** *Fix:* labels created
only when missing (one `gh label list`); SSH key + production resolution moved
behind `steps.select.outputs.skip == 'false'`; `collect-pr-context.sh` runs once
and its `bot-prs.json` feeds the reconciler (known-open PRs skip `gh pr view`)
and the selector's cap.

**F8 (A). `needs-work` was noise and `verify.sh` could lie.** *Fix:* `run_suite`
captures pytest's exit status — rc ∉ {0,1,5} renders **unavailable** and sets
`AUTOFIX_NEW_FAILURES=1`; `^ERROR` (collection) ids count as failing; the
interpreter is resolved from the tree under verification first, then the dev
venv, then the cache; the no-interpreter early exit now also emits 1 (it emitted
0 while the tail emitted 1). The `needs-work` label description now says "or
could not run". Test: a fake interpreter returning rc 2.

**F9 (A). Uncommitted model edits survived into the next card's PR.** *Fix:*
all three workflows' recovery step does `git reset --hard HEAD && git clean -fd`
(ignored paths such as `node_modules`, `venv`, `.env` untouched).

**F10 (A). Open-PR cap failed open.** *Fix:* the count read is `|| die` and
must be numeric; prefers the run-scoped snapshot. Test: failing `gh` → exit 1,
not 3.

**F11 (A). Undeployed merged fix → perpetual re-investigation + duplicate PR.**
*Fix:* the error workflow resolves the deployed build from
`https://hey-matcha.com/version.json` (`AUTOFIX_DEPLOYED_SHA`); `select.sh`
skips a MERGED fingerprint whose merge commit is not an ancestor of it.
Unknown SHA ⇒ old grace-window rule. Caveat: this is the *frontend* SHA; a
backend-only rollout that diverges makes the gate conservative (waits), never
duplicate-prone.

**F12 (A). Merged autofix PRs were never production-verified.** *Fix:*
`verify-deployed-fixes.sh` runs after collection — deployed + 6 h grace +
fingerprint silent ⇒ `production-verified`; recurred ⇒
`production-verification-failed`.

**F13 (A). A PR closed without merge never released its card.** *Fix:* webhook
`closed && !merged` on a `bot/task-*` head moves `in_progress`/`changes_requested`
→ `todo` with a `PR CLOSED: NOT MERGED` note; `reconcile-merged-cards.sh`
mirrors it. Cross-lane links (error-bot drafts closed as superseded/duplicate)
are left alone. The card does not auto-rerun. Tests: webhook pytest cases,
`test_kanban_autopr_reconcile.sh`.

### P2 — waste, fragility, duplication

**F14 (B). Two to three full sandbox rebuilds per card** — investigation,
corrective retry, publication-copy pass (whose output is a 72-char subject and
a 240-char note). Reuse the clone when `MODEL_BASE_SHA` is unchanged; fold
subject/note into the investigation's decision JSON.

**F15 (B). Three near-identical lanes.** Confidence banding in two
`decision.sh`; fingerprint in three places; redaction in four; SSH→docker→python
harness in five; `die()` in five; six `stat` epoch helpers and five `date -j -f`
parsers; `feedback_snapshot()` byte-duplicated; `write-commit-subject.sh` ≈ 80%
of `write-publication-copy.sh`; `_prompt_todo.txt`/`_prompt_rework.txt` share
123 lines and have diverged. Consolidate into `scripts/autopr-common/`.

**F16 (A partial, B). `progress_note` grammar parsed in three languages,
drifted.** *Fixed:* the `PAUSED: RUNTIME APPROVAL REQUIRED` marker is no longer
written (`checkpoint.sh` writes `PAUSED: APPROVE 10 MORE MINUTES` since 67f3b9c),
but the four readers still recognize it: it *was* written between 4a74cfd and
67f3b9c, and cards paused in that window would otherwise silently un-pause and be
picked up as fresh work — cheaper than a data migration; `acceptance_criteria_met` is now accepted by
every no-spec parser (`github.py`, `project_task_service.py`, `checkpoint.sh`;
`migration_required` stays as legacy because old cards carry it); the
`🤖 AUTO SETUP` structured-note regex in `github.py` matched only the status
segment (greedy `[^·]+` ate the separator's leading space) and rebuilt rework
notes with a doubled `· ·`. *B:* one reason-set constant emitted from `lib.sh`;
a structured `autopr_state` column for Espresso instead of
`note.hasPrefix(...)`.

**F17 (B).** `reconcile.sh` re-asks Codex the same equivalence question every
10 min per open draft × later human merge; needs a memo on (draft head × candidate
SHAs).

**F18 (B).** Error-bot selection is an uncached GitHub N+1 capped at 100.

**F19 (A).** Dead no-fix escape hatch (sentinel never written) replaced by a
7-day cooldown measured from the confirmation timestamp `publish.sh` stamps into
the issue body — not `updatedAt`, which any human comment bumps; attempt markers
pruned after 7 days; dispatch log rotated.

**F20 (B).** Overlap guard is TTL-shaped (60 s snapshot, `rmdir`+`mkdir`
reclaim). Lifetime dispatch lock.

**F21 (B).** One Mac, one ChatGPT login, one runner slot, no staleness alarm;
`msandbox stop` boots the runner; `StartInterval` agents don't catch up after
sleep; `watch-health.sh` can't see an expired runner token. The stale-installed-
dispatcher audit check is the first alarm; the rest is backlog.

**F22 (B).** Post-deploy regression check baselines *after* the deploy, alerts
only at ≥ 2 new fingerprints, single `curl` with no retry.

**F23 (A).** Doc drift: `AGENT_SANDBOX.md` vs `MSANDBOX_SESSIONS.md` on CLI
pinning (both were true of different image lineages; now say so); the error
workflow said "every 5 minutes"; `KANBAN_AUTOPR.md` has a spend-guards /
known-limitations section; the webhook table documents closed-unmerged.

### msandbox itself

**F24 (B).** Two live control-plane implementations (`scripts/agent-sandbox.sh`
1084 lines; `scripts/msandbox/` ~6k lines). Make the bash file a thin shim over
`python -m msandbox` for the AutoPR verbs.

**F25 (B).** CLI auto-update mints a ~5.75 GB image per upstream release for
interactive sessions while the AutoPR lane runs the non-content-addressed
`:latest` (Codex 0.150.1 observed vs 0.153.4 pinned). Resolve at most daily;
rebuild only on `msandbox build`/`install`; one lineage or an explicit note.

**F26 (doc).** Isolation claims match the code. Residual risk as documented: an
Autonomous interactive session holds prod SSH and account-wide AWS keys; the
least-privilege IAM profile is still not done.

## Batch A — what this PR changes

| Area | Files |
|---|---|
| Error lane | `_query.py` (safe request id, lazy asyncpg), `fetch-correlated-log.sh`, `notify-review-ready.sh`, `select.sh` (deployed gate, no-fix cooldown, pruning), `verify.sh`, new `verify-deployed-fixes.sh` |
| Kanban lane | `resolve-production-context.sh`, `dispatch-if-idle.sh`, `run-codex-sandboxed.sh`, `select.sh`, `reconcile-merged-cards.sh`, `checkpoint.sh`, `install-launch-agent.sh`, new `codex-backoff.sh`, new `hot-redispatch-guard.sh` |
| Self-audit | `audit.sh` (installed-dispatcher check), `investigate.sh` (narrowed denylist), new `repair-ledger.sh` |
| Workflows | `kanban-autopr.yml`, `silent-error-autofix.yml`, `autopr-self-audit.yml` |
| Server / Espresso | `routes/matcha_work/github.py`, `services/matcha_work/project_task_service.py`, `KanbanCard.swift`, `TaskViewerSheet+Header.swift` (dead marker only) |
| Tests | `test_error_autofix.sh` (+14), `test_error_autofix_query.py` (+2), `test_kanban_autopr.sh` (+10), `test_kanban_autopr_dispatch.sh` (+15), `test_kanban_autopr_reconcile.sh` (+1), `test_autopr_self_audit.sh` (+2), `server/tests/matcha_work/test_github_autopr_webhook.py` (+4) |
| Docs | `AGENT_SANDBOX.md`, `MSANDBOX_SESSIONS.md`, `SILENT_ERROR_AUTOFIX.md`, `KANBAN_AUTOPR.md`, this file |

### After merge — operator checklist

1. `./scripts/kanban-autopr/install-launch-agent.sh` — installs the repo's
   dispatcher (with `codex-backoff.sh`), the 300 s scheduler, and the 60 s
   request watcher. Until then the machine keeps running the 2026-08-31 copy.
2. `msandbox audit` — expect the new `installed_dispatcher` check to pass and
   `contract_tests` to pass on the runner's Python.
3. One manual `workflow_dispatch` of each lane; for Kanban, confirm the
   `Refuse a hot re-dispatch` step and that "Resolve active production build"
   is skipped on a no-op pass.
4. Watch `~/Library/Caches/matcha-autopr-dashboard/dispatch/` for
   `codex-usage-limit.json` and `self-audit-repair-ledger.json` appearing when
   those conditions occur.

## Batch B — backlog (separate PRs)

1. `scripts/autopr-common/` consolidation (F15) + prompt merge.
2. Decision-JSON publication copy + sandbox clone reuse (F14).
3. Reconcile memo (F17); cached/paginated error selection (F18).
4. Lifetime dispatch lock (F20).
5. Runner/`msandbox stop` decoupling, staleness alarm, wake catch-up (F21).
6. Regression-check redesign (F22).
7. Notification off prod-exec (F6).
8. Structured `autopr_state` for Espresso; one reason-set constant (F16).
9. Bash shim over the Python control plane (F24).
10. Daily-TTL CLI version resolution; one image lineage for AutoPR (F25).
11. Least-privilege IAM profile for the sandbox (F26).
12. Snapshot `agent-sandbox.sh` + compose + `scripts/msandbox` into the control
    root once it can take an explicit runtime root (F2 remainder).
13. Web `/work` ticket parity with Espresso for research cards: a Proposed
    Outreach section (send / handled / dismiss), Run research now, and rendered
    `.md` attachments (`react-markdown` + `remark-gfm` are already deps;
    `TaskAttachments.tsx` downloads them today).
14. Delete `TaskHistoryTimeline.swift` — no callers, and it would render
    "AutoPR: <email body>" for a staged row (pbxproj edit, so its own PR).
15. Research round numbering has three derivations (publisher filename count,
    `investigate.sh` round_started count, server `round_index`); unify on one.
