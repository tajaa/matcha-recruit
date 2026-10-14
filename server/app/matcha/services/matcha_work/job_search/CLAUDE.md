# Espresso Job search

A person describes the job they want ("COO roles across the US — I care most
about salary, bonus and equity"). A search finds postings, reads each one for
pay and application details, and ranks them by what the person weighs. Later
phases (screening, approach drafts) run model calls on the agent runtime.

Personal Espresso accounts only (the assistant's rule,
`agent_runtime.eligibility`), Pro and up (`features_for_plan()["job_search"]`),
a monthly allowance of whole searches (`JOB_SEARCH_MONTHLY_RUNS`, Pro 4 /
Business 10), and the `jobs-1` consent (`agent_runtime/consent.py`).

## The shape

| Piece | File | What it owns |
|---|---|---|
| Listings | `providers.py` | Google Jobs via SearchAPI (`SEARCH_API_KEY`) or SerpApi (`SERP_API_KEY`). Only query + location leave the server |
| ATS | `ats.py` | Greenhouse / Lever / Ashby detection from apply links, their public APIs, application questions |
| Pay | `comp.py` (pure) | Text scanning, structured mappers, `combine`, claim checks (`verify_quote`, `numbers_supported`) |
| Ranking | `ranking.py` (pure) | Weighted score inside bands; `comp_line` |
| Helpers | `normalize.py` (pure) | Dedupe key, state, remote, URL checks, posted age |
| Data | `service.py` | Owner-scoped reads/writes, re-rank, cancel, tombstone delete |
| Allowance | `quota.py` | The monthly count |
| Start | `enqueue.py` | `preflight`, `create_search`, `dispatch`, `queue_for` |
| Chain | `orchestrator.py` | `claim` / `advance` / `run_phase`, `nudge`, `reconcile` |
| Phases | `phases.py` | `plan`, `discover`, `enrich` (+ ranking) |

REST: `routes/matcha_work/job_search.py` (`/matcha-work/job-searches`).
Worker: `workers/tasks/job_search.py`. Migration: `mwjobs01`
(`mw_job_searches`, `mw_job_leads`, run kind `job_search`).

## Invariants

- **No pay figure without evidence.** Every base/bonus/equity value carries
  `evidence {quote, origin, url}`. From text, the quote is a slice of the text
  it came from; from a structured field (Lever `salaryRange`, Greenhouse pay
  ranges, Ashby components, JSON-LD `baseSalary`) it is the field and its raw
  values. A model's pay claim (later phases) must pass `verify_quote` against
  text fetched in that run and `numbers_supported`, or it is dropped.
- **Unposted pay is unknown, never $0.** Such a lead ranks in band 2 with the
  base weight removed and the rest renormalized. Currencies are never compared
  (band 1 is base pay in another currency).
- **Text scanning is conservative.** A bare number is never pay. Millions are
  never a salary. "Budget", "revenue", "Series B" right next to an amount wins
  over a "salary" elsewhere in the sentence. "Private equity-backed", "DEI",
  "is a bonus" are not compensation. Tests: `tests/job_search/test_comp.py`.
- **Ranking is deterministic.** Base is scored as a share of the best posted
  base in its currency (not a percentile: $10K apart should be 1.0 vs 0.96).
  Ties break on fit, then newest posting, then id.
- **One live search per person** (partial unique index). A create while one
  runs is 409; a live search idle for 2 hours is failed at the next create.
- **Allowance counts what cost money.** Every status but `failed` counts. A
  search the system could not run (nothing found, queue down, every query
  failed) is `failed` and free. Cancelled and deleted searches count; delete
  keeps a blanked row for that reason. Re-ranking never counts.
- **The server chooses where it connects.** ATS API URLs are built from tokens
  matched by strict patterns, on fixed hosts, through `safe_fetch.fetch_public`.
  Company pages go through the same fetcher; aggregators (LinkedIn, Indeed, …)
  are skipped, not scraped.

## The chain

One search is a chain of short Celery tasks, one phase each, because prod has
no `AGENT_*_QUEUE` and every task shares the single-slot main worker. Route it
elsewhere with `AGENT_JOBS_QUEUE` (else `AGENT_CARD_QUEUE`).

- `claim`: one UPDATE that succeeds only for the current `dispatch_token`, a
  live status and an expired lease (9 min). Duplicates and retired chains do
  nothing.
- `advance`: writes the outcome under the token and gives the next task a NEW
  token, so a late duplicate of an older message cannot start a second chain.
  Returns `(written, next_token)`.
- A phase is capped at 420s (`PHASE_SECONDS`, under the task's 500s soft
  limit). A failure retries the same phase after 30s, up to 3 attempts; then
  the search ends `done` (jobs found, ranked) or `failed` (none, free).
  `PhaseFailed` ends it at once.
- Every phase write checks the token (`Guard`), so cancel/delete stop writes
  at the next check.
- Recovery: `nudge` (every `GET …/status` of a live search) and `reconcile`
  (main-worker start, next to the sales reconcile) give an idle live search a
  new token and dispatch it. Celery does not redeliver a killed task.

Budgets per search, across retries: 30 provider calls, 120 leads, 60 page/API
fetches.

## Phases

| Status | Phase | Notes |
|---|---|---|
| `queued` → `planning` | `plan` | Queries from criteria. Google's `location` only takes Google place names, so a city goes in the query text |
| `discovering` | `discover` | Up to 3 pages per query, 3 at a time; dedupe on company + title + city; exclusions and remote preference applied |
| `enriching` | `enrich` | Batches of 24: ATS API first, then the company page's JSON-LD `JobPosting` (a careers page that redirects into an ATS reads the ATS). Then `service.rerank` |
| `done` / `failed` / `cancelled` | | |

`screening` and `approaching` are reserved statuses for the model phases.

## Not here (yet)

Model phases (plan expansion, screening/fit, comp research, approach drafts),
the chat ability, and the macOS UI. Those reuse `agent_runtime.runner` as a
caller (no second loop), and run rows of kind `job_search` point at their
search through `mw_project_agent_runs.job_search_id`.
