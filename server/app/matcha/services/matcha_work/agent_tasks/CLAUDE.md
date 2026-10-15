# Espresso Tasks

A person gives Espresso a directive ("find me a 1bd in SF under $3,500 that
allows dogs", "best organic lip balm under $15", "ramen near the Mission open
late"). It runs in the background, keeps what it found with the evidence for
each fact, and takes follow-ups: refine ("only the Mission"), search more, make
a document.

**Off until the Mac Tasks tab ships**: `ESPRESSO_TASKS_ENABLED` (settings
`espresso_tasks_enabled`), admins either way (`enqueue.tasks_enabled`).
Personal Espresso accounts (`agent_runtime.eligibility`), Pro and up
(`features_for_plan()["agent_tasks"]`), the shared monthly allowance
(`allowance.py`).

Server names avoid "task" alone: `mw_tasks` is kanban cards. Tables are
`mw_agent_tasks`, `mw_agent_task_rounds`, `mw_agent_task_items` (migration
`agenttask01`; forms `agenttask02`), routes are `/matcha-work/agent-tasks`.

## The shape

| Piece | File | What it owns |
|---|---|---|
| A kind of task | `playbook.py` | `Playbook` (intake, brief check, field library, phases, round entry points, rerank), `IntakeField`, `ItemField`, `Budgets`; `validate()` |
| Registry | `playbooks.py` | `PLAYBOOKS`, `chain_phases()`; validated at import |
| Allowance | `allowance.py` | `WEIGHTS` (a task's first round, per playbook), `ROUND_UNITS` (follow-ups), `used_units` (one statement over card runs, job searches and task rounds), `lock` |
| Start | `enqueue.py` | `preflight`, `create_task`, `start_round` (refine / more / document), `dispatch`, `queue_for`, `tasks_enabled` |
| Data | `service.py` | Owner-scoped views, list, summary, get (marks seen), status (+ nudge), item patch, cancel, tombstone delete, `close_round`, `end_stale`, `expire_waiting` |
| Findings | `items.py` | `dedupe_key`, `insert_items` (token-guarded, counts the round), views |
| Chain | `orchestrator.py` | `TASK_CHAIN` over `agent_runtime/chain.py`, `_ending`, `_stopped` (settle the round, notify) |
| Model runs | `model_run.py` | The task as a `phase_run.RunOwner` (kind `agent_task`, usage `matcha.espresso.tasks.<playbook>`) |
| Document | `document.py` | Fixed Markdown (no model) saved as a journal note via `journal_service.create_note_direct` |
| Telling | `notify.py` | Bell + live push when a task finishes, stops or needs the person |
| Intake | `intake.py` | Field values, the `ask_form` form (built from the playbook only), submitting it (`answer_form`) |
| Chat cards | `chat.py` | The `agent_task` card posted where a task started, and when it ends |
| From chat | `../agent_runtime/abilities/tasks.py` | The `tasks` ability: list, read, start, follow up, cancel, mark findings; the `task` block |
| Research | `research/` | The first playbook: see below |
| Job searches | `job_tasks.py` | Job search as a task: pointer rows, `overlay` (the search's state), `lead_item`, the `job_search` playbook, `start`, `search_stopped` |

REST: `routes/matcha_work/agent_tasks.py`. Worker: `workers/tasks/agent_tasks.py`
(`run_agent_task_phase` 500/560s, `reconcile_agent_tasks` at worker start).
Queue: `AGENT_TASKS_QUEUE`, else `AGENT_CARD_QUEUE`, else the default.

## From chat

In the person's private conversation (`tasks` ability, allowance
`agent_tasks` = `tasks_enabled`), Espresso picks a playbook and calls
`start_task` with what they said, by intake field key. When something that
matters is missing it calls `ask_form` instead: the model names the playbook
and field keys; the form (labels, types, files, consent) comes from the
playbook's `intake` alone. Submitting it (`POST /agent-tasks/prompts/{id}/answer`)
checks the values and files against the same fields and starts the task with
no model run, so no daily request; the prompt id is the task's request id. A
typed reply answers the form like any question and the next run carries on.
A task started from a conversation posts a card there (`chat.py`) when it
starts and when it ends. `create_task`'s `origin` is server-only.

`start_task` runs in the worker, so the gates it goes through are pool-free
(`workspace_enabled`, `resolve_plan_for_user`, `get_token_budget`).

## Job searches

A job search keeps its own engine and tables (`job_search/`); in Tasks it is a
pointer row (`engine = 'job_search'`, `job_search_id`, request id = the
search's id) written with the search. Every read joins the search
(`job_tasks.JOIN` / `COLUMNS`) and `task_view` overlays its status (its phases
read as `running`), note, counts and dates, so the two never drift. The
pointer's own `status` is always `done`: `chain.reconcile` scans the table's
live rows and must never take a pointer for a chain. Its own `completed_at`
marks that the person was told.

- Get: the search's jobs as findings (`lead_item`; pay `verified` only when
  posted) plus `job_search`, the search itself. The Mac shows the search's own
  view (`JobSearchDetailView`).
- Status, cancel, delete go through `job_search/service.py`; item reads and
  marks, refine, more and document are refused (409).
- Start: playbook `job_search` (`startable`, with the chains) builds a
  `JobSearchCreate` from the brief and calls `create_search`, whose gates
  apply (plan, allowance, `jobs` consent, one live search).
- Who sees them: job search isn't behind the Tasks switch. Someone with job
  search but not Tasks gets the routes, reads and manages their searches, and
  starts nothing else (`routes._engines`).

## Statuses and rounds

- `queued` / `running`: a live chain (at most `MAX_LIVE` = 2 per person).
- `waiting`: needs the person (a form, a confirmation). Holds no worker, so it
  is not live; `expire_waiting` cancels it after 7 days and that round is free.
  Nothing in research waits yet; the rules are here for intake and bookings.
- `done` / `failed` / `cancelled`: resting.
- Every piece of work is a round (`initial`, `refine`, `more`, `document`).
  A round costs its `units` unless it failed: `close_round` marks it failed
  when the task failed, the phase said `round_failed`, or a "search more" added
  nothing. Cancelled counts (like job search).
- A deleted task keeps its row and rounds (blanked), so it still counts.

## Research (`research/`)

`plan -> providers -> discover -> enrich -> screen -> rank -> summarize`;
refine starts at `refine`, "search more" at `providers`.

| Piece | File |
|---|---|
| Field library, reading pages, checking claims (pure) | `fields.py` |
| Hard constraints, bands, scores (pure) | `ranking.py` |
| Finish contracts and their checks (pure) | `contracts.py` |
| Google Shopping / Google Maps via SearchAPI (`SEARCH_API_KEY`), else SerpApi (`SERP_API_KEY`); a Shopping product's stores (`stores`, `with_store`) | `providers.py` |
| The model's page loader: agent cards' page facts plus the page's same-site links | `fetch.py` |
| No-model phases, `rerank`, `Deps` | `phases.py` |
| Model phases | `model_phases.py` |
| Brief + intake fields | `brief.py` |

## Invariants

- **Every fact carries its evidence and a status.** `verified`: structured
  data (a provider, the page's schema.org JSON-LD), the item's own page text
  (`scan_listing_text`), or a model claim whose quote is printed on the item's
  own page. `claimed`: a model claim quoted from some other page. Anything else
  is not stored. A quote must pass `fields.verify_quote` and state the value
  (`fields.supports`).
- **Hard constraints act on verified facts only.** Missing or claimed means
  band 1 "Unconfirmed", never a violation and never a match.
- **The person's own limits win.** A brief's budget and date become
  constraints the plan can't drop; a refine may change one, but one the model
  merely left out stays.
- **A Shopping finding links to a store, not Google.** Neither provider puts a
  store's link in its results (only Google's product page), so `run_providers`
  asks for each new product's stores (SearchAPI `google_product_offers` with
  `product_token`, SerpApi `google_immersive_product` with
  `immersive_product_page_token`), at most `STORE_LOOKUPS` (12) a round, best
  of each query first, and keeps the listing's seller there (else the first
  store, with its price and name). That page is then the finding's own, so
  `enrich` reads it (availability, schema.org data) and the dedupe key no
  longer changes with the query. A product past the lookups, or whose lookup
  failed, keeps Google's page.
- **Links are provenance-gated.** A candidate's URL must be one the run saw
  (a search result, a page it loaded, or a link printed on one: `fetch.py`);
  photos only ones a loaded page showed, rehosted on our CDN
  (`images.rehost_urls`), at most 3 per finding and 24 per task.
- **A summary states only numbers its findings show**, or the person's own
  ask, limits and the counts (`unsupported_numbers`, `context`);
  a reason that doesn't is dropped, a headline that doesn't gets one repair,
  then the ranking-only summary.
- **Budgets per round** (`Budgets`): 30 provider calls (searches and store
  lookups), 60 page loads, 6
  browser views, reserved with `chain.grant` before use and refunded after.
  80 findings per task, 120 once it searched more. Counters reset when a
  round starts.
- A page drawn by JavaScript is viewed in the browser only when the browser
  worker exists (`AGENT_BROWSER_QUEUE`) and the view budget allows.
- The model never writes: phases store what the contracts let through, under
  the chain's token.

## The Mac app

`platforms/desktop/Espresso`: the Tasks section (`Views/Tasks/`,
`TasksViewModel`, `AgentTaskService`, `AgentTaskModels`), the `ask_form` and
`agent_task` chat cards (`Views/Tasks/TaskChatCards.swift`), and the sidebar
row, shown when entitlements carry `workspace.agent_tasks` or
`workspace.job_search`. A job search task shows the search's own view
(`Views/JobSearch/JobSearchDetailView.swift`). Notification
metadata is strings only and carries `agent_task_id` (the app decodes
metadata as `[String: String]`; `task_id` is a kanban card there).

## Not yet (later PRs)

Agent cards as tasks (`engine` `board`; the columns exist), reservations.
