# Espresso Job search

A person describes the job they want ("COO roles across the US — I care most
about salary, bonus and equity"). A search plans the titles to look for, finds postings,
screens them for fit, reads each one for pay and application details, ranks
them by what the person weighs, and drafts how to approach the top ones:
route in, contacts, outreach, answers to the application's own questions and
a cover letter. Nothing is sent, applied for or submitted.

Personal Espresso accounts only (the assistant's rule,
`agent_runtime.eligibility`), Pro and up (`features_for_plan()["job_search"]`),
the shared monthly task allowance (`agent_tasks/allowance.py`: a whole search
costs 5 units of Pro's 60 / Business's 150, so 12 searches with nothing else;
`quota.job_search_usage` counts it in searches), and the `jobs-2` consent
(`agent_runtime/consent.py`). A `jobs-1` grant still lets the chat `jobs`
ability read, note and re-rank existing searches (it sends nothing to Brave:
`reading_covers`, `grants.is_active`); a new search asks for `jobs-2`
(`grants.is_current`).

**Brave and Claude only.** Postings are found with code's Brave searches and a
Claude run's web search, and read on the boards and pages themselves. There is
no search API: the Google Jobs step (SearchAPI, else SerpApi, `providers.py`)
was taken out on 2026-10-18, with the plan's Google Jobs queries, and `jobs-1`
(which named Google Jobs) became `jobs-2` (Brave). Don't bring one back. Leads
it found keep `source = 'google_jobs'` and read as before; a lead saved with
no source is `web`.

## The shape

| Piece | File | What it owns |
|---|---|---|
| Discovery | `discovery.py` | The `discovering` phase in three steps: code's Brave searches of Greenhouse, Lever and Ashby (`boards.py`), a model web search for postings elsewhere, then reading each one (ATS API or JSON-LD) into an already-read lead |
| Boards | `boards.py` | Code's board searches: Brave (`Deps.web_search`, 20 results each) for each title on each board host and in each place named (a whole state by its name and its job hubs, `STATE_HUBS`), ≤24 a search, 1 a second; every Greenhouse/Lever/Ashby job link in the answers goes to the read step, after the stored postings that fit. No model chooses |
| Stored postings | `postings.py` | Every board posting read, kept (`mw_job_postings`): reused when read live in the last 12 h, skipped when its board said closed in the last 14 days, and `matching` a later search's titles and places. Board searches Brave was sent (`mw_job_board_searches`): the same one within a day asks for its next page. Fails soft |
| Places | `places.py` (pure) + `data/us_places.tsv.gz` | Whether a job is in a place the person named (`fits`): its location text split into places, put on the map with the US Census gazetteer (offline, built by `server/scripts/build_job_places.py`), kept within 50 miles of one of theirs, or remote when they'd take it |
| ATS | `ats.py` | Greenhouse / Lever / Ashby / Workable detection from apply links, their public APIs, application questions (Greenhouse's, and Workable's public form); `fetch(ref, more=take)`: one call the caller pays for first, and Workable's form a second paid with `more()` (asked only for a published posting); `most_reads(ref)`, what to reserve; `NAMES`, each ATS by name; `find_on_board`, the employer's own Greenhouse, Lever or Ashby board found by name |
| Pay | `comp.py` (pure) | Text scanning, structured mappers, `combine`, claim checks (`verify_quote`, `numbers_supported`) |
| Ranking | `ranking.py` (pure) | Weighted score inside bands; `comp_line` |
| Helpers | `normalize.py` (pure) | Dedupe key, state, remote, URL checks, posted age, `related_title` |
| Data | `service.py` | Owner-scoped reads/writes, re-rank, cancel, tombstone delete |
| Allowance | `quota.py` | The monthly count |
| Start | `enqueue.py` | `preflight`, `create_search`, `dispatch`, `queue_for` |
| Chain | `orchestrator.py` | `PHASES`, `_ending`, `JOB_CHAIN` (the search's `ChainSpec`); `claim` / `advance` / `run_phase`, `nudge`, `reconcile` are the engine's (`agent_runtime/chain.py`) bound to it |
| Phases | `phases.py` | `enrich` (+ ranking, + queue the top 8 for approaches); `plan_from_criteria` (the typed titles, or the role the ask names: `title_from_ask`); `must_search` and `cover` (below); `keep_job`; `read_job_page`; `Guard`, `grant`, `refund` bound to the search row |
| Model phases | `model_phases.py` | `plan`, `screen`, `approach` (the web search is in `discovery.py`) |
| One model run | `agent_phase.py` | The search as a `phase_run.RunOwner` (kind `job_search`, counted on the search row); the run itself is `agent_runtime/phase_run.py` |
| Model contracts | `contracts.py` (pure) | Finish tools + `normalize_plan` / `normalize_postings` / `normalize_screen` / `normalize_approaches` |
| Prompts | `prompts.py` | Phase instructions and user turns |
| Tailored résumé | `tailor.py` | One job's résumé, rewritten for it on request (below): `request`, the worker's `run`, `status_of` (stale reads failed), `view`, `as_text` |

REST: `routes/matcha_work/job_search.py` (`/matcha-work/job-searches`).
Worker: `workers/tasks/job_search.py`. Migrations: `mwjobs01`
(`mw_job_searches`, `mw_job_leads`, run kind `job_search`), `mwjobs03`
(`source = 'workable'` allowed), `mwjobs04` (`mw_job_postings`,
`mw_job_board_searches`), `mwjobs05` (`mw_job_leads.resume_*`).

## How a search finds jobs (call map)

The quick chat look-up (`find_jobs`, "Quick") and a job search task's
discovery ("Full") run the same steps on the same functions. Read this before
the code; the Invariants below say why each rule holds.

```
ENTRY
  Quick: runner.run_agent → find_jobs → agent_runtime/abilities/job_listings._find
  Full:  discovery.discover → _search_boards → boards.find       (boards step)
                            → _read → read_postings              (read step)

1. PLACES TO SEARCH IN
   boards.board_searches(titles, criteria)
     ├─ boards.search_places(criteria)
     │    ├─ places.targets(criteria)        offline Census gazetteer
     │    └─ boards.STATE_HUBS[state]        a whole state: its name + hubs (CA → LA, SF, San Diego)
     └─ phases.cover(...)                    titles × places × board hosts, each reached before a repeat

2. STORED POSTINGS
   Quick: job_listings._store()  ·  Full: postings.store(connection_or_direct)
     ├─ Store.sent(searches)                 SELECT mw_job_board_searches
     └─ Store.matching(titles, criteria)     SELECT mw_job_postings (title tsvector index)
          └─ postings.keep → normalize.related_title + phases.keep_job

3. BRAVE SEARCH
   postings.plan(searches, sent)             page 0 / next page / skip (read to its end)
   Quick: job_listings._web_search  ·  Full: deps.web_search
     └─ brave_search.search(query, count=20, offset=page)        → Brave API
   postings.key_of_url → ats.detect          board job links only
   postings.last_page                        was it the search's last page?

4. READ EACH LINK
   Store.known(keys)                         SELECT mw_job_postings
     read live < 12 h → stored record · closed < 14 d → skip · else read:
   Quick: _read_some (8 at once, 40 s) → _read(url)
   Full:  read_postings (6 at once, 240 s)
     └─ discovery.read_posting
          └─ postings.Reads.fetch → ats.read(ref)
               ├─ safe_fetch.fetch_public(ref.api_url())          → the board's public API
               └─ ats.parse_greenhouse / parse_lever / parse_ashby / parse_workable

5. SAVE
   Store.save(read, closed)                  INSERT … ON CONFLICT mw_job_postings
   Store.searched(pages)                     INSERT … ON CONFLICT mw_job_board_searches
     Full: boards.record_searched, in the read step once the links are read

6. FILTER + ANSWER
   normalize.related_title                   a related title?
   phases.keep_job → places.fits             in a place named, or remote?
   Quick: _shown_before(ctx)                 SELECT mw_project_agent_runs (jobs shown in this chat)
   normalize.same_posting                    the same job on two boards?
   Quick: job_row → model_line → job_postings block (gate_block)
   Full:  phases.insert_leads → mw_job_leads
          → model_phases.screen (Claude: fit against the résumé)
          → phases.enrich → service.rerank (ranking.py)
          → model_phases.approach (Claude: drafts for the top 8)
```

The Full search also runs the web step between boards and read
(`discovery.web_run`: a Claude run with web search only, from
`discovery.web_searches`, for careers pages and other boards); its links go
through step 4 too. Outside services called: Brave (step 3), the boards'
public APIs and employers' pages (step 4), and Claude (the chat run, and the
Full search's plan, web, screen and approach). Everything else is our own
Postgres or code.

## Invariants

- **A posting is the lead's only when it is the same job.** Google Jobs (the
  first source until 2026-10-18) listed other employers' jobs among a posting's apply links. In a 2026-10-15 dev audit
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
  (other than Remote and the nationwide words), every job, from the boards
  or the web, is kept only when a place its own posting names is
  within 50 miles of one of theirs (`places.NEAR_MILES`), in a state they
  named, or matched by name abroad, or when it is remote and they'd take
  remote (`phases.keep_job` → `places.fits`). A location code can't place is
  dropped, not guessed at, and so is a remote job open only outside the
  country of every place they named. Code decides from the posting's text and
  the Census gazetteer, never a model: a model given Brave results with no
  location in their snippets kept one of six that fit (prod, 2026-10-17). So
  a read posting carries only its own location (`discovery._ats_record`,
  `_page_record`), never the web run's claim. How places are read
  (`places.named`): "OR" in capitals is Oregon, never the word "or"; a city
  and state with no comma ("Austin TX") is the city in that state; a country
  alone ("Canada") keeps the jobs its postings place there (`Target.country`);
  nationwide phrases ("US only", "Open to relocation") name no place; regions
  ("Midwest", "East Coast") are measured from their biggest city (`ALIASES`);
  "not remote" is not remote. A whole state keeps a job anywhere in it, and
  its board searches name the state and its job hubs
  (`boards.search_places`, `STATE_HUBS`: California is also Los Angeles, San
  Francisco and San Diego), since most postings write "Los Angeles, CA" and
  never the state. Until 2026-10-19 a state got no board search in it at all:
  "California" was searched nationwide and filtered afterwards. Tests: `tests/job_search/test_places.py`.
- **A board or web posting is kept only for a related title.** A board search
  for "Chief People Officer" turns up any job that names it somewhere, so a
  posting read from the boards or the web is kept only when its title shares
  a core word with a wanted title (`normalize.related_title`: "HR Business
  Partner" for "Head of HR", never "Software Engineer"). Words are kin when
  equal or one a short inflection of the other (`normalize._kin`), never a
  five-letter stem (which kept Forklift Operator for COO). A wanted title of
  level words alone (CEO, President, General Manager) needs the whole title
  and no level word of the posting's own: an Account Executive is not a CEO.
  `same_title` is symmetric (either side may add a city or a team), and
  `same_employer` compares whole names, never one word of a longer one
  (Delta Air Lines' "delta" board is not Delta Dental's). Tests:
  `tests/job_search/test_normalize.py`. Level is the screen's to judge.
- **A posting is read once, and kept.** Every Greenhouse, Lever, Ashby or
  Workable posting a search or `find_jobs` reads is stored in
  `mw_job_postings` (`postings.py`): live with the lead record as read, or
  closed only when its ATS said so (`ats.read`: a 404 or 410, an Ashby board
  without it, an unpublished Workable job; a timeout or a 5xx says nothing).
  A posting read live in the last `LIVE_HOURS` (12) is used as read, with no
  fetch; one closed in the last `CLOSED_DAYS` (14) isn't read; an older one
  is read again on its own board (`Stored.read_url`). `Store.matching` gives a
  search the live postings earlier searches read (within 7 days) that it
  would keep (`related_title`, `keep_job`), ahead of Brave's links. And
  `mw_job_board_searches` remembers each board search Brave was sent: the
  same query within `SEARCH_HOURS` (24, from its first page) asks for its
  next page (pages 0 to 4), and one read to its end isn't sent. A page is
  recorded only once its postings are read (the full search's read step,
  from `phase_cursor.searched`; `find_jobs` when every link is settled), so a
  task killed before then sends the same page again. Both tables are shared
  public data: no user, company, criteria or résumé on them. Every statement
  fails soft (`Store`): no table or no database reads as nothing stored. On
  2026-10-19 a chat follow-up ("any others?") re-sent its first answer's
  searches word for word and re-read the same 119 postings to find one new
  job. Tests: `tests/job_search/test_postings.py`.
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
- **Every title they typed is searched, and every place.** The plan lists
  the typed titles first, then kept directions, then its own
  (`model_phases.plan`). Code's searches take at least their usual few titles
  and always all of the first two kinds (`phases.must_search`), host by host
  and title by place (`phases.cover`), so a capped list still has every
  typed title, direction and place in it: when the Google Jobs step went, so
  did its query per typed title and place, and directions placed third had
  pushed typed titles past the cap.
- **A suggested direction is the résumé's, word for word.** With a résumé the
  plan may name up to 3 `directions` (`contracts.MAX_DIRECTIONS`): roles
  beyond the titles asked for (Solutions Architect for an engineer who led
  customer integrations), each with `why` and `evidence`. `check_directions`
  keeps one only when its evidence is in the résumé text (`comp.verify_quote`)
  and its title isn't one already asked for; no résumé, none. A kept one is
  listed right after the titles they typed, and later phases are told it
  (`prompts.person_block`): the screen counts it as relevant. `get_search`
  marks a job `direction` when it is squarely that title
  (`normalize.title_covers`, every word, level words included) and not the
  same job as one they asked for. The web shows "Beyond your title" with the
  quote; the assistant reads them through `read_job_search`.

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

Budgets per search, across retries: 48 provider calls (Brave's board searches, 24 a pass: a re-claimed boards step runs again, and a search begun before 2026-10-18 had spent some on Google Jobs), 120 leads, 400 page/API
fetches (`MAX_FETCHES`, shared: discovery's reads first, then enrich), at most `LEAD_FETCHES` (10) for one lead. Calls are reserved on the search row before they are made
(`phases.grant` → `chain.grant`, one statement under a row lock) and only the unused part is
given back (`refund`). A task killed mid-phase gives nothing back, so a retry
works from what is left: it can never buy a second budget. A lead the budget
ran out before is left unread (`NOT_TRIED`), not marked read.

## Phases

| Status | Phase | Notes |
|---|---|---|
| `queued` → `planning` | `model_phases.plan` | Model: titles (≥1, ≤10, as postings write them: theirs, then real synonyms at that level), deal-breakers, profile summary, weights (applied only while `weights_source='default'`), directions. Falls back to `plan_from_criteria`. What the person typed always comes first, then kept directions, and every search takes all of both (`phases.must_search`); a failed plan with nothing typed searches the role the ask names (`phases.title_from_ask`), never the sentence, or no title |
| `discovering` | `discovery.discover` | Three steps, each its own task (`phase_cursor.step`; a cursor still saying `listings`, from before 2026-10-18, starts at `boards`). `boards`: code's Brave searches (`boards.board_searches`: at least 4 titles (and every typed title and kept direction) on each of the 4 board hosts, titles and hosts paired by `phases.cover` so a capped list reaches every host (listed host by host, two places left Ashby unsearched), interleaved with the first 2 titles in each of up to 6 places, also paired with the hosts, ≤24, one a second for Brave's free plan; a Brave that is out stops them, a cancelled search stops at the next guard check, and the unused searches go back). Every board job link waits in the cursor (`boards_ok` when any search answered, or when the budget was already spent by an earlier pass, which did search). `web`: one model run with web search only (no page loads: code reads every posting; with them a run spent its turns re-checking pages), ≤300 s, ≤16 searches (≤4 in one turn, `prompts.SEARCHES_PER_TURN`, and its prompt says so: told "one at a time", a dev run sent 7 at once and 3 were refused), finds ≤40 postings on careers pages, other boards and search firms; the links wait in the cursor. Code writes the searches it starts from (`web_searches`: at least 3 titles, every typed one and direction, each title and each place reached first, then on Workable and SmartRecruiters, then the other pairs, ≤14), half to each run, because a model left to choose ran one search and stopped. Workday isn't asked for: its pages are scripts with no posting data, and its API refuses servers (checked 2026-10-16). `read` (after the boards and after each web run): each is read (1 fetch reserved for a board link, 2 for Workable's (`ats.most_reads`; a closed or missing one spends 1 and the rest goes back), 4 for a page, 6 at a time, 240 s; what's still loading then is dropped), and kept only for a related title in a place named (Invariants). Each read counts what became of every posting it was handed (`discovery.READ_OUTCOMES`: known, aggregator, unread, late, title, elsewhere, duplicate, full, kept) into the search's `progress.reads`, under `boards` or `web`, and logs it: a dev search read 160 board links and kept 21, and nothing said why the 139 went. A careers page that can't be read (a bot check, a script page) is looked up on the employer's own board (`ats.find_on_board`, same title and employer). Known links and aggregators are skipped, and duplicates of a lead are dropped (`dedupe_key`, `same_posting`). Kept leads are `enriched_at` set with `source` greenhouse/lever/ashby/workable/web and their `ats` questions. Workable postings (`apply.workable.com/{account}/j/{shortcode}`) were dropped here until 2026-10-18: 3 of the web runs' postings in one prod search. The web runs when fewer than 30 came from the boards, and a second time when the search is still short and the first added jobs or searches are left. Nothing found: `UNAVAILABLE` (free) when no source could be searched (the boards and the web both failed), else "No postings matched" |
| `screening` | `model_phases.screen` | Model, batches of 40 by short id (J1…): relevant, fit 0-5, reasons, deal-breaker ("None"/"N/A" as text is none). A failed batch stays in (unranked fit). A job the model skipped (the contract lets 20% go) stays `pending` and is shown once more (`phase_cursor.rescreen`); skipped again, it is kept in unrated, never counted as a match unseen |
| `enriching` | `enrich` | Batches of 24. Reads up to 2 ATS links (via the API), then up to 2 company pages (their JSON-LD `JobPosting`); a careers page that redirects into an ATS is read as that ATS. Only the lead's own job counts, see Invariants. If no link is it, `ats.find_on_board` looks the title up on the employer's Greenhouse, Lever and Ashby boards, by name. Only jobs at the fit floor (Invariants); the floor is written token-guarded before the re-rank reads it. Then `service.rerank` and the top 8 matches are queued (`phase_cursor.approach_queue`). A widen ends here, drafting nothing |
| `approaching` | `model_phases.approach` | Model with web search + `fetch_page`, 2 jobs per task. A failed batch is `approach_status='failed'`; the person can redraft. The done note counts the jobs as they are (`_drafted_note`): "5 of 8 approaches drafted", or none, never "drafted" when they failed |
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
The finish tool's parameters are the answer's fields themselves
(`agent_runtime/finish.tool`, shared with research tasks). Wrapped in one `result` object, Claude Haiku sent that
object as JSON text in 4 of 12 plan and approach runs on prod (2026-10-15..18),
and each failed. `finish.answer` still
reads the wrapped form, an answer sent as JSON text and a list or object sent
as JSON text inside it. A list field (`postings`, `verdicts`, `approaches`)
that comes as text it can't read is refused by name (`finish.items`), so the
repair fixes the JSON: read letter by letter, it came back as "give an
approach for each job shown, by its short id", which sent the model after its
ids. A refused finish keeps what was sent on its step (`arguments`, capped at
4,000 characters like any step), next to the error. `contracts.py` checks it;
the orchestrator writes what survives:

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
That holds because every write that marks a job `queued` or `drafting`
(enrich's top-8 queue, approach's `drafting`) checks the chain's token, so a
cancel landing between them can't leave one behind. The stale sweep at
create (`service.end_stale`) runs the same terminal hooks as the chain
(`job_tasks.search_stopped`: told once, the Tasks row completed). The worker
tasks run under `run_with_chat_fanout`, so the done card and bell reach an
open Espresso.

Redraft: `POST …/leads/{lead}/approach` puts a `done` or `cancelled` search
back into `approaching` for that one job (free; ≤20 per search, 10/hour; the
hour's limit is spent only after `service.check_redraftable` says it would be
accepted). The cursor's `after` remembers which: a cancelled search goes back
to `cancelled` when the draft finishes, fails or goes stale
(`service.resting_status`), never to `done`; Cancel during a redraft or widen
returns the search to its `after`, not `cancelled`. Widen and redraft clear
an earlier "stopped early" `error`. A `failed` search has no ranked jobs and
can't redraft.

Widen ("Show N more at 3/5" on the Mac): `POST …/widen` puts a `done` or
`cancelled` search still at floor 4 back into `enriching` with the floor at 3
(`service.widen`; cursor `{after, widen: true}`), so its 3/5 postings are read
and ranked with the rest; the phase then returns to `after` with nothing new
queued (any job can still be drafted). Free and once per search: a search at
floor 3 is refused 409, which is also the rate limit. The pay-law
hint (`service.PAY_LAW_STATES`: the employer-side list plus MA) is set at
re-rank for unposted pay and given to the approach phase.

## Tailored résumé

"Tailor my résumé" on a job (`POST …/leads/{lead}/resume`, 202) rewrites the
person's saved résumé for that posting, to read before they apply
(`tailor.py`). On the web it is the job pane's "Your résumé for this job"
(`pages/JobSearch/TailoredResume.tsx`): each line opens to the résumé lines it
came from, then what changed and what the posting asks for that the résumé
doesn't show. The person can edit it on the page (not saved), Copy it or
Download it as text. Nothing is sent, attached or submitted. The Mac has no
pane for it yet (the lead JSON only gains fields).

- **Nothing new in anyone's record.** The model gets the posting and the
  résumé's own text (`user_resumes.raw_text`, ≤20k chars, not the 6k parsed
  summary the phases get) and no tools. `contracts.normalize_tailored` keeps a
  line only when each of its `sources` is in the résumé word for word
  (`comp.verify_quote`) and every number in it is in those sources
  (`comp.amounts_in` / `numbers_supported`); a role, employer, date or skill
  is kept only as the résumé writes it (blanked otherwise; a role with
  neither title nor employer goes). A summary that fails is dropped, not the
  résumé. `dropped` counts what was left out and the page says so. What the
  posting asks for and the résumé lacks goes in `gaps`, never into the résumé.
  Nothing kept at all gets the model one repair, then the job is `failed`.
  In a 2026-10-29 check with Claude Haiku on a sample résumé, every line
  survived. The prompt also forbids summary claims worked out from the
  résumé ("over a decade"): before that, Haiku wrote one.
- **One run, its own token.** `request` sets `resume_status = 'queued'` with a
  new `resume_token` and dispatches `workers/tasks/job_search.tailor_job_resume`
  (same queue as the search, `queue_for`). The task claims `queued → drafting`
  under that token; only that token writes the outcome (`_finish`), so a newer
  ask replaces an older run's write. Asked while one runs, the first is left to
  finish and nothing is spent. A run queued or drafting past `STALE_MINUTES`
  (7, past the task's 360 s hard limit) died: it reads `failed` everywhere and
  can be asked again. There is no sweep.
- **Counted like the search's runs, outside its chain.** The run is a
  `phase_run` run owned by the search (kind `job_search`, phase
  `tailor_resume`, counted in `model_runs` / `tokens`, charged to the
  workspace's tokens), with `dispatch_token` and `recap_generation` cleared,
  so it never joins a recap and never touches the search's status, cursor or
  progress note. Delete takes it with the search's runs.
- **Gates.** Pro (`require_plan`, `job_search`), a posting that has been read
  (≥200 chars, else 409 `posting_unread`), a saved résumé (else 422
  `resume_required`), then 10 an hour (`HOURLY_LIMIT`) and the token budget,
  checked only once it would be accepted. Admins skip the plan, limit and
  budget. No allowance units: it isn't a search.
- **The web polls the open job** while it is `queued`/`drafting`
  (`useJobSearch`): tailoring doesn't move the search's status, so the
  search's poll never sees it.

## In the assistant

A run that can look for jobs (`tasks`, `job_listings` or `jobs`) is told
whether a résumé is saved (`RunContext.saved_resume`, from
`service.resume_on_file`: name, date, title, never the text). Saved: a
`job_search` task uses it unless they say not to
(`abilities/tasks.with_resume_default`). None: the model asks "a quick general
search here, or a full job search task using your résumé?" (`tasks.QUICK` /
`WITH_RESUME`); quick is `find_jobs`, résumé is the form below. `start_task`
with `use_resume` and none saved is refused back to `ask_form`, and
`job_tasks.start` refuses it too (422 `form_invalid`), for the form and chat
alike. The form's `use_resume` field carries `widget: "resume"`: the web draws
the saved résumé or a drop zone (`components/resume/ResumeFormField.tsx`),
which saves it to the profile at once; asked for with none saved, the field is
asked switched on (`intake` `prefill`) so the drop zone shows.

The résumé itself is `user_resumes` (`core/routes/identity/profile_resume.py`):
the original file in the private bucket (SSE-AES256, public access blocked,
fifteen-minute links), its text and parsed fields in the row. The owner reads
the text (`GET /users/me/resume`, `text`) and edits it
(`PUT /users/me/resume/text`: re-parsed, the parsed fields kept if that fails,
the file untouched); a recruiter's read never carries it. On the web it lives
in Tasks → Résumé (`/tasks?view=resume`, `components/resume/ResumePane.tsx`).

A quick look at open roles in chat is `agent_runtime/abilities/job_listings.py`
(`find_jobs`): this package's Brave board searches (`boards.board_searches`),
reader (`discovery.read_posting`), place filter and stored postings
(`postings.py`), run in one tool call with no search row and no model phases
(see the agent runtime's CLAUDE.md, "Job listings").

`agent_runtime/abilities/jobs.py` (`private_only`, `jobs-2`): list and read
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
other lookup failures keep the search and job URL with a retry button. A new
search opens its task through this same exact lookup, independently of list
refreshes, and falls back to the search's own link (with its retry) only when
that lookup fails. Tasks
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
`xl`. The hook has no searches list (Tasks lists, starts and deletes them);
only the search polls its detail. The web workspace endpoint returns
lightweight search task metadata, with the search's own fingerprint (the one
`/status` reports), or an ordinary task with its selected finding in the same
response. When the search's status moves, Tasks refreshes this metadata once to
persist `seen_at`, retrying only a read that missed while the task remains
open; opening a search does not immediately reload the Tasks list. A search
opened from a link that is older than the recent page stays listed across list
refreshes. Draft
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

## Optional web recaps

`recap_generation` identifies a new enabled search execution. Accepted widen or
approach restart freezes the old resting recap source before mutable results
change, then enrolls a new generation under the existing source lock. Ordinary
worker retries/batches keep the generation. Phase evidence includes dispatch
epoch fencing. Completion mail ownership is durable; deletion revokes recaps.
Flags default off; see `docs/ops/ESPRESSO_RECAPS.md`.
