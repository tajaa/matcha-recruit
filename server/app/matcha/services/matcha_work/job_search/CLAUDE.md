# Espresso Job search

A person describes the job they want ("COO roles across the US — I care most
about salary, bonus and equity"). A search plans its queries, finds postings,
screens them for fit, reads each one for pay and application details, ranks
them by what the person weighs, and drafts how to approach the top ones:
route in, contacts, outreach, answers to the application's own questions and
a cover letter. Nothing is sent, applied for or submitted.

Personal Espresso accounts only (the assistant's rule,
`agent_runtime.eligibility`), Pro and up (`features_for_plan()["job_search"]`),
the shared monthly task allowance (`agent_tasks/allowance.py`: a whole search
costs 5 units of Pro's 60 / Business's 150, so 12 searches with nothing else;
`quota.job_search_usage` counts it in searches), and the `jobs-1` consent
(`agent_runtime/consent.py`).

## The shape

| Piece | File | What it owns |
|---|---|---|
| Listings | `providers.py` | Google Jobs via SearchAPI (`SEARCH_API_KEY`), then SerpApi (`SERP_API_KEY`) (`FallbackJobs`). Requests and moving between them are `matcha_work/search_apis.py`'s, shared with research tasks: one that refuses for good (a refused key, or no searches left: a 402, or a 429 in the API's own words, `out_of_searches`; never a per-minute quota) is dropped for the phase and logged as an error (Admin → Server Errors); one still down after its retry is passed over when another follows. Only query + location leave the server |
| ATS | `ats.py` | Greenhouse / Lever / Ashby detection from apply links, their public APIs, application questions; `find_on_board`, the employer's own board found by name |
| Pay | `comp.py` (pure) | Text scanning, structured mappers, `combine`, claim checks (`verify_quote`, `numbers_supported`) |
| Ranking | `ranking.py` (pure) | Weighted score inside bands; `comp_line` |
| Helpers | `normalize.py` (pure) | Dedupe key, state, remote, URL checks, posted age |
| Data | `service.py` | Owner-scoped reads/writes, re-rank, cancel, tombstone delete |
| Allowance | `quota.py` | The monthly count |
| Start | `enqueue.py` | `preflight`, `create_search`, `dispatch`, `queue_for` |
| Chain | `orchestrator.py` | `PHASES`, `_ending`, `JOB_CHAIN` (the search's `ChainSpec`); `claim` / `advance` / `run_phase`, `nudge`, `reconcile` are the engine's (`agent_runtime/chain.py`) bound to it |
| Phases | `phases.py` | `discover`, `enrich` (+ ranking, + queue the top 8 for approaches); `plan_from_criteria`; `Guard`, `grant`, `refund` bound to the search row |
| Model phases | `model_phases.py` | `plan`, `screen`, `approach` |
| One model run | `agent_phase.py` | The search as a `phase_run.RunOwner` (kind `job_search`, counted on the search row); the run itself is `agent_runtime/phase_run.py` |
| Model contracts | `contracts.py` (pure) | Finish tools + `normalize_plan` / `normalize_screen` / `normalize_approaches` |
| Prompts | `prompts.py` | Phase instructions and user turns |

REST: `routes/matcha_work/job_search.py` (`/matcha-work/job-searches`).
Worker: `workers/tasks/job_search.py`. Migration: `mwjobs01`
(`mw_job_searches`, `mw_job_leads`, run kind `job_search`).

## Invariants

- **A posting is the lead's only when it is the same job.** Google Jobs lists
  other employers' jobs among a posting's apply links. In a 2026-10-15 dev audit
  of 116 leads, 6 of the 60 postings enrich read belonged to another job. One
  was Flex shown at Headway's $230–300K, when Flex's own posting says
  $320–400K. So every read must pass `normalize.same_title`, which spells out
  abbreviations, so COO equals Chief Operating Officer. Wherever the source
  names an employer, it must also pass `normalize.same_employer`: Greenhouse's
  `company_name`, an ATS board's name, or a page's hiring organization. A
  posting that fails is passed over and the next link tried, never kept.
- **No pay figure without evidence.** Every base/bonus/equity value carries
  `evidence {quote, origin, url}`. From text, the quote is a slice of the text
  it came from; from a structured field (Lever `salaryRange`, Greenhouse pay
  ranges, Ashby components, JSON-LD `baseSalary`) it is the field and its raw
  values. A model's pay claim (later phases) must pass `verify_quote` against
  text fetched in that run and `numbers_supported`, or it is dropped.
- **Unposted pay is unknown, never $0.** Such a lead ranks in band 2 with the
  base weight removed and the rest renormalized. Currencies are never compared
  (band 1 is base pay in another currency).
- **Text scanning is conservative.** Outside a known pay field (Google's
  `salary`), an amount needs a currency or a K, so "12 hour days" and "24 hour
  on-call" are not hourly pay. Millions are never a salary, and "401k",
  "403(b)", "457(b)" are retirement plans. "Budget", "revenue", "Series B"
  right next to an amount wins over a "salary" elsewhere in the sentence. A
  percentage is a bonus (or equity) only in the same clause as the word:
  "a 401(k) match of 4% and an annual bonus" is a mentioned bonus, not 4%.
  "Private equity-backed", "DEI", "is a bonus" are not compensation, but "plus
  a bonus of up to 20%" is. Tests: `tests/job_search/test_comp.py`.
- **Page data reaching a model is bounded.** `page_extract` keeps only the
  scalar fields of JSON-LD `baseSalary` (currency, min/max/value, unit), so a
  page cannot ride a giant salary object into the model's input.
- **Ranking is deterministic.** Base is scored as a share of the best posted
  base in its currency (not a percentile: $10K apart should be 1.0 vs 0.96).
  Ties break on fit, then newest posting, then id.
- **One live search per person** (partial unique index). A create while one
  runs is 409. A live search idle for `STALE_INTERVAL` (2 hours) is ended at
  the next create exactly as reconcile ends it (`service.end_stale`): `done`
  and ranked when it found jobs, `failed` (free) when it found none.
- **A retried create is answered first.** `create_search` looks up
  `(user_id, request_id)` before the plan, cap and rate-limit checks, so a
  person whose first answer was lost gets their running search, not a 429.
- **Allowance counts what cost money.** Every status but `failed` counts. A
  search the system could not run (nothing found, queue down, every query
  failed) is `failed` and free. Cancelled and deleted searches count; delete
  keeps a blanked row for that reason. Re-ranking never counts.
- **The server chooses where it connects.** ATS API URLs are built from tokens
  matched by strict patterns, on fixed hosts, through `safe_fetch.fetch_public`.
  The tokens come from an apply link, or from a board name guessed from the
  employer's name (`ats.board_names`).
  Company pages go through the same fetcher; aggregators (LinkedIn, Indeed, …)
  are skipped, not scraped.

## The chain

One search is a chain of short Celery tasks, one phase each, because prod has
no `AGENT_*_QUEUE` and every task shares the single-slot main worker. Route it
elsewhere with `AGENT_JOBS_QUEUE` (else `AGENT_CARD_QUEUE`).

The engine lives in `agent_runtime/chain.py` so other owners can reuse it
(see that package's CLAUDE.md, "Chains"). Job search is its first spec,
`orchestrator.JOB_CHAIN`: table `mw_job_searches`, the status names the phase
(no phase column), budget columns `provider_calls` / `fetch_calls`,
`release_drafts` on terminal, `_ending` for a search that cannot go on. The
SQL it runs is the same as before the move. Tests that fake the database
patch `chain.connection_or_direct` for the engine's statements (claim,
advance, restart, reconcile, `Guard`, `grant`, `refund`), and fake dispatch by
replacing `JOB_CHAIN` (`dataclasses.replace(..., dispatch=...)`).

- `claim`: one UPDATE that succeeds only for the current `dispatch_token`, a
  live status and an expired lease (10 min, longer than the task's 560s hard
  limit, so a restart can never run beside a task still alive). Duplicates and
  retired chains do nothing. Every claim counts an attempt; only a finished
  phase resets it. The claim past `MAX_ATTEMPTS` ends the search (`done` if it
  found jobs) instead of running the phase: a task killed by the memory limit
  or the hard time limit cannot loop through restarts forever.
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

Budgets per search, across retries: 30 provider calls, 120 leads, 240 page/API
fetches (`MAX_FETCHES`), at most `LEAD_FETCHES` (10) for one lead. Calls are reserved on the search row before they are made
(`phases.grant` → `chain.grant`, one statement under a row lock) and only the unused part is
given back (`refund`). A task killed mid-phase gives nothing back, so a retry
works from what is left: it can never buy a second budget. A lead the budget
ran out before is left unread (`NOT_TRIED`), not marked read.

## Phases

| Status | Phase | Notes |
|---|---|---|
| `queued` → `planning` | `model_phases.plan` | Model: queries (≤8), titles, deal-breakers, profile summary, weights (applied only while `weights_source='default'`). Falls back to `plan_from_criteria`; what the person typed is always searched. Google's `location` only takes Google place names, so a city goes in the query text |
| `discovering` | `discover` | Up to 3 pages per query, 3 at a time; dedupe on company + title + city; exclusions and remote preference applied. Every API refused for good: nothing more is asked and what was found goes on to screening; with nothing found, fails at once with `UNAVAILABLE` ("Job listings aren't available right now…", free), never retried. Passing errors on every query: retried |
| `screening` | `model_phases.screen` | Model, batches of 40 by short id (J1…): relevant, fit 0-5, reasons, deal-breaker. A failed batch stays in (unranked fit) |
| `enriching` | `enrich` | Batches of 24. Reads up to 2 ATS links (via the API), then up to 2 company pages (their JSON-LD `JobPosting`); a careers page that redirects into an ATS is read as that ATS. Only the lead's own job counts, see Invariants. If no link is it, `ats.find_on_board` looks the title up on the employer's Greenhouse, Lever and Ashby boards, by name. Then `service.rerank` and the top 8 are queued (`phase_cursor.approach_queue`) |
| `approaching` | `model_phases.approach` | Model with web search + `fetch_page`, 2 jobs per task. A failed batch is `approach_status='failed'`; the person can redraft |
| `done` / `failed` / `cancelled` | | |

## Model phases

Each is one ordinary agent-runtime run (`agent_phase.run_model_phase`, over
`agent_runtime/phase_run.run_model_phase` with the search as its `RunOwner`):
the search is a third caller of `runner.run_agent`, after the chat assistant and
agent cards. There is still one loop. The run row is `kind='job_search'`,
`surface='job_search'`, `job_search_id` set, no project or channel. Runs are
not stored by the provider (`store_responses=False`): the ask and, when the
person chose "use my résumé", their résumé (`user_resumes`, ≤6k chars) are in
the input. The model is settled at create (`agent_surfaces.ESPRESSO_JOB_SEARCH`,
Admin → AI models; else Claude Haiku, `claude_default`) and re-checked against `models.offered()`
(a model no longer offered runs `models.fallback()`).

The output of each phase is its **finish contract**, not draft tools (a finish
next to a write is refused by the runner, and the last turn forces finish).
`contracts.py` checks it; the orchestrator writes what survives:

- ids must be the batch's short ids;
- a contact must be named on a page `fetch_page` loaded in this run, with that
  page as its source;
- `outreach.to_email` must be printed on a loaded page or typed in the ask;
- answers only to the posting's `open` questions; file, authorization and
  demographic questions are listed as `unanswered`, never answered; with no
  known questions, at most four "likely" ones;
- sources must be links this run's searches or loads returned.

A search that ends any other way (cancelled, past `MAX_ATTEMPTS`, swept as
stale) drafts nothing more: `service.release_drafts` marks its still-queued
jobs `approach_status='failed'`, so they show Redraft, never "drafting" forever.

Redraft: `POST …/leads/{lead}/approach` puts a `done` or `cancelled` search
back into `approaching` for that one job (free; ≤20 per search, 10/hour). The
cursor's `after` remembers which: a cancelled search goes back to `cancelled`
when the draft finishes, fails or goes stale (`service.resting_status`), never
to `done`. A `failed` search has no ranked jobs and can't redraft. The pay-law
hint (`service.PAY_LAW_STATES`: the employer-side list plus MA) is set at
re-rank for unposted pay and given to the approach phase.

## In the assistant

`agent_runtime/abilities/jobs.py` (`private_only`, `jobs-1`): list and read
searches and jobs, keep the person's status and notes (`update_job_lead`),
re-rank (`rank_job_search`). The `jobs` block is rebuilt from the jobs the run
read, so pay in chat is always the posting's own.

## In Tasks

Searches live in Espresso's Tasks section; the separate Job search section is
gone. Each search has a pointer row in `mw_agent_tasks` (`engine =
'job_search'`), written in `create_search`'s transaction
(`agent_tasks/job_tasks.insert_pointer`; `agenttask03` for older searches) and
tombstoned by `delete_search`. Tasks reads the search's own state through it,
cancels and deletes through this service, and refuses refine / more /
document (a search is re-ranked and redrafted here).

Started from chat as a task: the `tasks` ability's `start_task` or a submitted
form with playbook `job_search` (`job_tasks.PLAYBOOK`: titles, places, remote,
minimum base, saved résumé, the `jobs` disclosure) goes through
`create_search` with the conversation as `origin`. When a search first ends
`done` or `failed`, the chain's `on_terminal` (`orchestrator._stopped`) tells
the person (bell + push, `agent_task_id` metadata) and posts the task card in
that conversation; a redraft that ends later doesn't tell them again.
