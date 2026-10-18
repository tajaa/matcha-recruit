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
| Discovery | `discovery.py` | The `discovering` phase in four steps: Google Jobs (`phases.listings`), code's Brave searches of Greenhouse, Lever and Ashby (`boards.py`), a model web search for postings elsewhere, then reading each one (ATS API or JSON-LD) into an already-read lead. Works with no listings key |
| Boards | `boards.py` | Code's board searches: Brave (`Deps.web_search`, 20 results each) for each title on each board host and in each place named, ≤24 a search, 1 a second; every Greenhouse/Lever/Ashby job link in the answers goes to the read step. No model chooses |
| Places | `places.py` (pure) + `data/us_places.tsv.gz` | Whether a job is in a place the person named (`fits`): its location text split into places, put on the map with the US Census gazetteer (offline, built by `server/scripts/build_job_places.py`), kept within 50 miles of one of theirs, or remote when they'd take it |
| Listings | `providers.py` | Google Jobs via SearchAPI (`SEARCH_API_KEY`), then SerpApi (`SERP_API_KEY`) (`FallbackJobs`), as extra coverage: with neither, the web alone. Requests and moving between them are `matcha_work/search_apis.py`'s, shared with research tasks: one that refuses for good (a refused key, or no searches left: a 402, or a 429 in the API's own words, `out_of_searches`; never a per-minute quota) is dropped for the rest of the search and logged as an error (Admin → Server Errors); one still down after its retry is passed over when another follows. Only query + location leave the server |
| ATS | `ats.py` | Greenhouse / Lever / Ashby detection from apply links, their public APIs, application questions; `find_on_board`, the employer's own board found by name |
| Pay | `comp.py` (pure) | Text scanning, structured mappers, `combine`, claim checks (`verify_quote`, `numbers_supported`) |
| Ranking | `ranking.py` (pure) | Weighted score inside bands; `comp_line` |
| Helpers | `normalize.py` (pure) | Dedupe key, state, remote, URL checks, posted age, `related_title` |
| Data | `service.py` | Owner-scoped reads/writes, re-rank, cancel, tombstone delete |
| Allowance | `quota.py` | The monthly count |
| Start | `enqueue.py` | `preflight`, `create_search`, `dispatch`, `queue_for` |
| Chain | `orchestrator.py` | `PHASES`, `_ending`, `JOB_CHAIN` (the search's `ChainSpec`); `claim` / `advance` / `run_phase`, `nudge`, `reconcile` are the engine's (`agent_runtime/chain.py`) bound to it |
| Phases | `phases.py` | `listings` (Google Jobs), `enrich` (+ ranking, + queue the top 8 for approaches); `plan_from_criteria`; `read_job_page`; `Guard`, `grant`, `refund` bound to the search row |
| Model phases | `model_phases.py` | `plan`, `screen`, `approach` (the web search is in `discovery.py`) |
| One model run | `agent_phase.py` | The search as a `phase_run.RunOwner` (kind `job_search`, counted on the search row); the run itself is `agent_runtime/phase_run.py` |
| Model contracts | `contracts.py` (pure) | Finish tools + `normalize_plan` / `normalize_postings` / `normalize_screen` / `normalize_approaches` |
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
- **A posting found on the web is kept only once it has been read.** The web
  run hands back links, and each link must be one its searches or page loads
  returned (`contracts.normalize_postings`). Code then reads each one, from
  the ATS's public API or the page's JobPosting data. A posting the ATS no
  longer has, one past its `validThrough`, or a page with no posting on it is
  dropped. So a model can't add a job that isn't there, and the title, the
  pay and the questions come from the posting, never from the model. The
  same goes for code's own board searches: Brave's index is months behind (10
  of 45 board links in a 2026-10-17 prod run were still posted), so a link is
  only a job once its board's API still has it.
- **A job is kept only where the person wants it.** When they named places
  (other than Remote and the nationwide words), every job, from Google Jobs,
  the boards or the web, is kept only when a place its own posting names is
  within 50 miles of one of theirs (`places.NEAR_MILES`), in a state they
  named, or matched by name abroad, or when it is remote and they'd take
  remote (`phases.keep_job` → `places.fits`). A location code can't place is
  dropped, not guessed at, and so is a remote job open only outside the
  country of every place they named. Code decides from the posting's text and
  the Census gazetteer, never a model: a model given Brave results with no
  location in their snippets kept one of six that fit (prod, 2026-10-17).
- **A board or web posting is kept only for a related title.** A board search
  for "Chief People Officer" turns up any job that names it somewhere, so a
  posting read from the boards or the web is kept only when its title shares
  a core word with a wanted title (`normalize.related_title`: "HR Business
  Partner" for "Head of HR", never "Software Engineer"). Level is the
  screen's to judge.
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
- **The first pass is the strong matches only.** `enrich` settles the search's
  fit floor (`progress.fit_floor`, `ranking.FIT_FLOOR` = 4, or 3 when
  screening rated nothing 4 or higher; `service.fit_floor` reads it) and reads
  only the postings at or above it. Ranking puts every job under the floor in
  band 8 (`BELOW_FLOOR_BAND`), after every match, so the top 8 drafts, the
  Tasks count, the done card and email, the assistant's list and the Mac list
  all follow the floor without each re-checking fit. A failed screening batch
  (unrated fit) still counts as a match. A search from before the floor has
  none: nothing goes in band 8, and it can't widen.
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
  The tokens come from an apply link, a link the web run found, or a board
  name guessed from the employer's name (`ats.board_names`).
  Company pages go through the same fetcher; aggregators (LinkedIn, Indeed, …)
  are skipped, not scraped.
- **The résumé never goes to the web run.** Its searches leave for the open
  web, so it gets only the ask, what the person set, the planned titles and
  what was already found (`prompts.discover_turn`).

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

Budgets per search, across retries: 48 provider calls (Google Jobs ≤24, Brave's board searches ≤24), 120 leads, 400 page/API
fetches (`MAX_FETCHES`, shared: discovery's reads first, then enrich), at most `LEAD_FETCHES` (10) for one lead. Calls are reserved on the search row before they are made
(`phases.grant` → `chain.grant`, one statement under a row lock) and only the unused part is
given back (`refund`). A task killed mid-phase gives nothing back, so a retry
works from what is left: it can never buy a second budget. A lead the budget
ran out before is left unread (`NOT_TRIED`), not marked read.

## Phases

| Status | Phase | Notes |
|---|---|---|
| `queued` → `planning` | `model_phases.plan` | Model: queries (≤8), titles, deal-breakers, profile summary, weights (applied only while `weights_source='default'`). Falls back to `plan_from_criteria`; what the person typed is always searched. Google's `location` only takes Google place names, so a city goes in the query text |
| `discovering` | `discovery.discover` | Four steps, each its own task (`phase_cursor.step`). `listings`: Google Jobs when a key is set, up to 3 pages per query, 3 at a time; dedupe on company + title + city; exclusions, remote preference and places applied. No key, a refusal or failing queries never stop the search. `boards`: code's Brave searches (`boards.board_searches`: each of 4 titles on each of the 4 board hosts, interleaved with each of 2 titles in each of 5 places, ≤24, one a second for Brave's free plan; a Brave that is out stops them, and the unused searches go back). Every board job link waits in the cursor (`boards_ok` when any search answered). `web`: one model run with web search only (no page loads: code reads every posting; with them a run spent its turns re-checking pages), ≤300 s, ≤16 searches, finds ≤40 postings on careers pages, other boards and search firms; the links wait in the cursor. Code writes the searches it starts from (`web_searches`: each of 3 titles in each place, then on Workable and SmartRecruiters, ≤14), half to each run, because a model left to choose ran one search and stopped. Workday isn't asked for: its pages are scripts with no posting data, and its API refuses servers (checked 2026-10-16). `read` (after the boards and after each web run): each is read (1 fetch reserved for a board link, 4 for a page, 6 at a time, 240 s; what's still loading then is dropped), and kept only for a related title in a place named (Invariants). A careers page that can't be read (a bot check, a script page) is looked up on the employer's own board (`ats.find_on_board`, same title and employer). Known links and aggregators are skipped, and duplicates of a lead are dropped (`dedupe_key`, `same_posting`). Kept leads are `enriched_at` set with `source` greenhouse/lever/ashby/web and their `ats` questions. The web runs when fewer than 30 came from the boards, and a second time when the search is still short and the first added jobs or searches are left. Nothing found: `UNAVAILABLE` (free) when no source could be searched (listings, boards and web all failed), else "No postings matched" |
| `screening` | `model_phases.screen` | Model, batches of 40 by short id (J1…): relevant, fit 0-5, reasons, deal-breaker. A failed batch stays in (unranked fit) |
| `enriching` | `enrich` | Batches of 24. Reads up to 2 ATS links (via the API), then up to 2 company pages (their JSON-LD `JobPosting`); a careers page that redirects into an ATS is read as that ATS. Only the lead's own job counts, see Invariants. If no link is it, `ats.find_on_board` looks the title up on the employer's Greenhouse, Lever and Ashby boards, by name. Only jobs at the fit floor (Invariants); the floor is written token-guarded before the re-rank reads it. Then `service.rerank` and the top 8 matches are queued (`phase_cursor.approach_queue`). A widen ends here, drafting nothing |
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
Admin → AI models; else Claude Haiku, `anthropic_messages.surface_model`) and re-checked against
`models.offered()`: a model no longer offered (a Luna search from before the Anthropic key) runs what
a new search would get, the admin's choice included, and the row is re-stamped with it.

The output of each phase is its **finish contract**, not draft tools (a finish
next to a write is refused by the runner, and the last turn forces finish).
`contracts.py` checks it; the orchestrator writes what survives:

- a found posting's link must be one this run's searches or loads returned;
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
to `done`. A `failed` search has no ranked jobs and can't redraft.

Widen ("Show N more at 3/5" on the Mac): `POST …/widen` puts a `done` or
`cancelled` search still at floor 4 back into `enriching` with the floor at 3
(`service.widen`; cursor `{after, widen: true}`), so its 3/5 postings are read
and ranked with the rest; the phase then returns to `after` with nothing new
queued (any job can still be drafted). Free and once per search: a search at
floor 3 is refused 409, which is also the rate limit. The pay-law
hint (`service.PAY_LAW_STATES`: the employer-side list plus MA) is set at
re-rank for unposted pay and given to the approach phase.

## In the assistant

`agent_runtime/abilities/jobs.py` (`private_only`, `jobs-1`): list and read
searches and jobs, keep the person's status and notes (`update_job_lead`),
re-rank (`rank_job_search`). `read_job_search` lists the search's matches
and counts the jobs under its floor (`weaker_matches`); `include_weaker` lists
them too. The `jobs` block is rebuilt from the jobs the run
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

## On the web

On the personal web surface, job searches live inside Tasks at
`/espresso/tasks/:taskId?item=<lead id>`, alongside the person's other tasks.
There is no separate Job search sidebar entry. `pages/Tasks/JobSearchPane.tsx`
opens the search's own ranked jobs and job pane, using the components in
`pages/JobSearch/` and `api/matchaWork/jobSearch.ts`. Tasks starts a search
with New job search, lists it, and deletes it through its pointer task.
The old `/espresso/jobs` redirects to Tasks; `/espresso/jobs/:searchId?job=`
looks up the pointer task and redirects to its `?item=` link (or Tasks when
none is found). It resolves through `GET /agent-tasks/for-search/{search_id}`,
a read-only lookup scoped to the owner and workspace, so the recent task
list's 50-row page never drops an older link. Only a 404 falls back to Tasks;
other lookup failures keep the search and job URL with a retry button. New
searches use this same exact lookup, independently of list refreshes. Tasks
offers Load older tasks through a `(created_at, id)` cursor, so earlier searches
can also be browsed without a saved link. Deleted searches and pointers
are not recreated. While Tasks deletes a search, both its search controls and
lead mutations are held; a failed deletion makes them available again.
The new-search form reads only `/job-searches/setup` (consent and allowance),
reports initialization failures and retries in place, preserving the person's
fields and focus. Creation does not reload search history. The search guide opens on first use after
the Tasks guide, and can be reopened from the search header.
`jobSearchLogic.ts` ports `JobSearchViewModel`'s rules (filters, the 3/5
widen count, Next steps progress, `parseBaseFloor`, `retryIsNewRequest`, pay
lines) with tests, and `useJobSearch.ts` polls `/status` every 5 s only while
the search is live or a job is drafting, reloading the jobs only when the
fingerprint, status or job count changes. Its reads are numbered per kind
(list, search, job), and a change (Redraft, Mark, notes, re-rank, widen,
cancel, Draft email) takes a number when it starts and when it lands, so an
older answer can't undo it; only reads of what is still open are dropped. A
job's load and save failures show in its pane, which covers the search below
`xl`. Inside Tasks the hook skips the searches-list load; only the search
polls its detail. The web workspace endpoint returns lightweight search task
metadata, or an ordinary task with its selected finding in the same response.
Search completion refreshes this metadata to persist `seen_at`, retrying a
failed read while the task remains open; opening a search does not immediately
reload the Tasks list. Draft
email links to Gmail's own drafts folder, since the web has no Email ▸ Drafts
view; Ask Espresso opens the one assistant conversation with the Mac's
hand-off prompt in its composer, unsent.

Edit draft, on the web and the Mac, sends `{"existing_only": true}` to
`…/email-draft`, which never makes a draft: when Gmail no longer has it (sent
or deleted in Gmail itself, where Espresso can't see it), the job forgets it,
as `note_email_draft` does for a draft deleted from Espresso's Email, and the
call is a 409 `email_draft_missing` carrying the job as it is now. The pane
says so, and Draft email is the person's own click to make a new one. Draft
email sends no body, and with no body the endpoint behaves as before (an older
Mac build's Edit draft still recreates a missing draft).
