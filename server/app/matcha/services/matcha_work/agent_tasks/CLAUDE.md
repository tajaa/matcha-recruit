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
`agenttask01`), routes are `/matcha-work/agent-tasks`.

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
| Research | `research/` | The first playbook: see below |

REST: `routes/matcha_work/agent_tasks.py`. Worker: `workers/tasks/agent_tasks.py`
(`run_agent_task_phase` 500/560s, `reconcile_agent_tasks` at worker start).
Queue: `AGENT_TASKS_QUEUE`, else `AGENT_CARD_QUEUE`, else the default.

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
| Google Shopping / Google Maps via SearchAPI (`SEARCH_API_KEY`), else SerpApi (`SERP_API_KEY`) | `providers.py` |
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
- **Links are provenance-gated.** A candidate's URL must be one the run saw
  (a search result, a page it loaded, or a link printed on one: `fetch.py`);
  photos only ones a loaded page showed, rehosted on our CDN
  (`images.rehost_urls`), at most 3 per finding and 24 per task.
- **A summary states only numbers its findings show**, or the person's own
  ask, limits and the counts (`unsupported_numbers`, `context`);
  a reason that doesn't is dropped, a headline that doesn't gets one repair,
  then the ranking-only summary.
- **Budgets per round** (`Budgets`): 30 provider calls, 60 page loads, 6
  browser views, reserved with `chain.grant` before use and refunded after.
  80 findings per task, 120 once it searched more. Counters reset when a
  round starts.
- A page drawn by JavaScript is viewed in the browser only when the browser
  worker exists (`AGENT_BROWSER_QUEUE`) and the view budget allows.
- The model never writes: phases store what the contracts let through, under
  the chain's token.

## Not yet (later PRs)

Intake forms and the `tasks` ability (start from chat), the Mac Tasks tab,
agent cards and job searches as tasks (`engine` `board` / `job_search`; the
columns exist), reservations.
