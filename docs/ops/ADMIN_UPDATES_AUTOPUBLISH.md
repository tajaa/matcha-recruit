# Production admin-update autopublisher

`.github/workflows/admin-updates-autopublish.yml` publishes deployed feature notes to
Matcha `/admin/updates` and Tell-Us `/tellus/admin/updates`. Every successful Matcha
backend/frontend swap dispatches it from `scripts/update-ec2.sh`; the dispatch is
non-fatal to the deploy because the code is already live by then.

## What it publishes

The workflow starts at production's `changelog_autogen_state.last_pr_number` and
examines merged PRs in merge-time order. It also rechecks a 24-hour window before the
state row's `updated_at` timestamp. That overlap catches a lower-number PR merged after
a higher-number PR advanced the numeric watermark, as well as merges racing a run. A
PR is eligible only when:

- its merge commit is an ancestor of every active image its changed paths require
  (`server/` → backend, `client/` → frontend);
- every migration added by the PR is already represented in production's migration
  graph; and
- the relevant product table does not already contain an id beginning with that PR
  number.

A backend/frontend PR therefore waits for both halves of a split deploy. If any PR in
the selected batch is not deployed or migration-ready, the workflow publishes none of
that batch and leaves the watermark unchanged. Docs, CI, scripts, tests, and non-EC2
application paths advance without a model call because they cannot produce a
production web-app update.

GitHub's PR-list GraphQL response exposes at most 100 changed files. When a PR reaches
that boundary, the trusted collector replaces it with the complete paginated REST file
list before product classification; at the REST endpoint's 3,000-file ceiling it fails
closed rather than risking an incomplete product update.

The publication date is the day the change actually went live, not the merge date. The
collector takes the tightest defensible bound per component a PR needed, the latest
across those components, floors it at the PR's merge time, and renders it in
`America/Los_Angeles` (override with `ADMIN_UPDATES_TIMEZONE`). Two bounds are combined:

- the running blue/green container's `started_at`, read fresh in the same run. It proves
  the component has served an image containing the PR since then, but only as an upper
  bound -- a retry, a batch released by `deferred`, or a `since_pr` backfill observes a
  *later* deploy than the one that carried the PR; and
- the dispatching deploy's own timestamp, for exactly the components its `target`
  replaced, and only when its source SHA contains the merge commit and it does not
  predate the merge. This workflow shares one self-hosted runner, so a dispatch can sit
  queued for a day and describe a deploy that could not have carried the PR at all.

A container that has never run reports Docker's zero-value `0001-01-01T00:00:00Z`, which
parses cleanly; the collector rejects any start before the year 2000 as unknown. When a
required component's start time is unknown the collector falls back to whichever is later
of the dispatch and this run's production check. Rendering in Pacific matters too: a UTC
calendar day turns every deploy after 17:00 Pacific into tomorrow's entry. The model never
computes a date; the validator rejects any entry that changes the one it was given.
Existing ids are never overwritten, so a hand-edited entry remains authoritative on
retries.

## Trust boundary

Collection and publication are trusted host steps. They hold the GitHub token and
`EC2_SSH_KEY`, resolve the active blue/green image SHAs, and read only changelog ids plus
the watermark from production.

Drafting reuses `scripts/kanban-autopr/run-codex-sandboxed.sh`:

- model: `gpt-5.6-luna`;
- reasoning effort: `high`;
- tracked-files-only repository clone with no remote;
- empty AWS mount and no GitHub, Matcha, SSH, or production credentials; and
- `AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1`, so the writing pass cannot change code.

The model receives a bounded plan and production context, and must emit one
entry-or-skip decision for every requested `(PR, product)` pair. It does not read merge
diffs: the trusted collector calls `gh pr view` for the few candidate PRs only and
attaches truncated commit messages, review discussion, and per-file stats to each
candidate (`scripts/admin-updates/enrich.py`), so the writer works from what a human
wrote about the change and opens current files only to confirm a real control label.
Discussion is ordered chronologically and reserves a share of its budget for `reviews`,
whose approve / request-changes rationale a run of long bot comments used to truncate
away, and the evidence for all candidates shares one plan-wide budget so a backlog run
cannot grow the plan without bound. Enrichment is evidence, not a gate: if it fails the
run warns and publishes from PR titles and bodies. The
validator rejects extra keys, missing decisions, changed ids/dates, unknown categories,
control characters, oversized prose, setup prerequisites, and `action-needed` tags.

The final publisher validates the JSON again, sends only that JSON to a fixed Python
program inside the active backend, and performs one transaction. It can insert into only
`admin_updates` or `tellus_admin_updates`, renumber those two tables, and advance the
single watermark with `GREATEST`. It accepts no SQL from the model. A post-write read
verifies both the watermark and every submitted id.

The legacy test-tenant sync still carries new hand-authored changelog ids from dev to
production, but now does so additively (`ON CONFLICT DO NOTHING`). Production wins on
an existing id, so a stale dev copy cannot overwrite an automated or manually corrected
production entry.

## Operations

The self-hosted Mac must have `msandbox start` enabled and a valid host Codex login.
The workflow uses the same `matcha-kanban-autopr-sandbox` identity as the other AutoPR
lanes and the one-slot runner serializes their use.

Normal operation needs no command: deploy completion dispatches the workflow. For the
first run only, if production has neither a watermark nor a `pr-<number>-...` row to
infer one from, run it manually with the last already-accounted-for PR:

```sh
gh workflow run admin-updates-autopublish.yml --ref main -f since_pr=360
```

Do not use `since_pr` for ordinary retries; production state is authoritative. A failed
run opens or updates the deduplicated `ops-health:admin-updates` issue, and a successful
later run comments on and closes it. The deploy itself remains successful.

`server/scripts/generate_changelog.py` remains available only as historical/manual
tooling. `update-ec2.sh` no longer invokes its Gemini/dev-database path, preventing it
from racing or advancing state independently of the production-aware workflow.
