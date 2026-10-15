# Espresso Tasks

A person gives Espresso a directive ("find me a 1bd in SF under $3,500 that
allows dogs", "best organic lip balm under $15", "ramen near the Mission open
late"). It runs in the background, keeps what it found with the evidence for
each fact, and takes follow-ups: refine ("only the Mission"), search more, make
a document.

**Off on prod until its migrations and deploy land**: `ESPRESSO_TASKS_ENABLED`
(settings `espresso_tasks_enabled`), admins either way (`enqueue.tasks_enabled`).
`scripts/dev-remote.sh` turns it on in dev (`ESPRESSO_TASKS_ENABLED=0` runs dev
like prod). Without it Espresso has no `tasks` ability, so "find me apartments"
gets a chat answer, not a task.
Personal Espresso accounts (`agent_runtime.eligibility`), Pro and up
(`features_for_plan()["agent_tasks"]`), the shared monthly allowance
(`allowance.py`).

Server names avoid "task" alone: `mw_tasks` is kanban cards. Tables are
`mw_agent_tasks`, `mw_agent_task_rounds`, `mw_agent_task_items` (migration
`agenttask01`; forms `agenttask02`), `mw_agent_task_actions` (`agenttask04`),
routes are `/matcha-work/agent-tasks`.

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
| Actions on findings | `actions/` | `ItemAction` (`base.py`), `ACTIONS` + `validate` (`__init__.py`), propose / confirm / cancel / history (`service.py`); Buy (`buy.py`), Apply (`apply.py`) |
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
starts and when it ends; the finished card shows the summary's five picks in
its order (`chat.picks`). `create_task`'s `origin` is server-only. The day's
caps (10 tasks started, 30 follow-ups) refuse with `code: daily_limit` and a
sentence saying so (`enqueue._daily`): a bare "Too many requests" had
Espresso retrying three times and telling the person the search service was
busy.

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

## Actions on findings (`actions/`)

A playbook names what its findings can do in the world (`Playbook.actions`,
keys into `actions.ACTIONS`); `item_actions` stay the person's own marks
(save, dismiss, a note). An action is an `ItemAction`: a label, an icon key
(`cart`, `calendar`, `envelope`, `link`, `phone`), the item kinds it fits, its
own fields (`params`, intake fields), a daily limit, and three functions:

- `available(ctx)`: why not, for this finding (shown on the button), or None.
- `prepare(ctx, params)`: a `Proposal`: `frozen` (all `perform` gets) plus how
  it reads (title, lines, note, and the button's words if not the default).
  Built from the stored finding and the person's own saved details only,
  never from a model.
- `perform(ctx, frozen)`: carry it out; returns `outcome(headline, lines, url)`.

`service.py` owns the rest. Propose (`POST /{task}/items/{item}/actions/{key}`)
checks the action is the playbook's for that kind, available, under its daily
limit, then stores the proposal (30 minutes; an older one for the same finding
expires). Confirm (`POST /actions/{id}/confirm`) claims it `proposed ->
running` only while fresh, so a second confirm never runs it twice and a retry
returns what came of it; a deleted task's proposal is cancelled, not run.
`GET`/`PATCH` of a finding return `actions` (checked for the person) and
`action_history`. The Mac draws whatever it is sent (`TaskActionSheet`).
Actions are deterministic: no model run and no assistant hold/resume (that
machinery is bound to a chat run).

**Buy** (`buy.py`, products): Espresso never pays or orders.
- A store counts as Shopify only when Shopify vouches for it: the host's
  `/meta.json` names a `*.myshopify.com` shop, and that shop's
  `/products/<handle>.js` must come back from the finding's own host (Shopify
  redirects a shop to its own domain only). Then a cart permalink
  `https://<store>/cart/<variant>:<qty>` opens checkout with it in the cart,
  at the store's price now in the shop's currency (`/meta.json`; a bare
  amount when unknown, and "when found" only compared in the same currency),
  refused when the variant is sold out.
- "Fill in my email and saved address" (an action field, on by default)
  adds `checkout[email]` and `checkout[shipping_address][...]` to that link;
  the preview lists them. The result keeps the link without them
  (`stored_url`); the frozen proposal and preview keep them as the person's
  own record of what they agreed to.
- Any other store: its product page. A finding with only Google's page can't
  be bought. Quantity is a whole number 1–10.

**Apply** (`apply.py`, listings): Espresso never applies, pays a fee, signs or
fills anything in. It loads the listing's own page now and reads its links for
an application: words ("Apply now", "application") beat a path
(`/apply`), the listing's own site beats a leasing portal (`PORTALS`: RentCafe,
Entrata, AppFolio, ...) beats anything else; job and career links are skipped;
https only (the listing's own site as served). None found, or the page can't
be read: the listing's page. A 404/410 is refused (off the market). The
preview shows the rent, specials, address and leasing office phone as found.

Guards (`service.py`): 10 proposals a minute a person (each may read the
store's pages); an advisory lock per finding and action around expire +
insert; a `running` row older than 10 minutes is settled as failed; the
daily limit counts by `decided_at`.

## Adding a kind of task, or an action

- **An action**: a module in `actions/` with an `ACTION`, added to `ACTIONS`;
  name its key in the playbooks whose findings take it. Nothing else changes
  (`test_adding_an_action_needs_nothing_else`).
- **A kind of task**: a `Playbook` (`playbook.py`) in `playbooks.PLAYBOOKS`
  and a cost in `allowance.WEIGHTS`. Its intake builds the chat's form, its
  `description` is how Espresso picks it, its field library the facts its
  findings may carry. The chain runs its `phases`; an engine of its own (like
  job search) is a pointer row read through an adapter (`job_tasks.py`).
- Every Espresso feature ships its feature guide (`FeatureGuides.swift`).

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
| Brief + intake fields (`ResearchBrief`, `ApartmentBrief`, `validator`) | `brief.py` |
| Where a finding is: the anchor, distance and direction (`resolve_anchor`, `distance_fields`, `from_address`) | `geo.py` |
| Kinds of search: products, apartments, places (data) | `kinds.py` |

### Kinds of search (`research/kinds.py`)

A `SearchKind` is data that becomes a playbook of its own
(`research.kind_playbook`): research's phases, stored under research's
phase names (`Playbook.phase_prefix`; a phase name runs one function,
checked by `validate_registry`). The phases read the kind from the task's
playbook (`kinds.of(task)`). What a kind fixes, in `contracts.finalize_plan`
(the one place every plan goes through: the model's, the fallback, a
refine):

| Kind | Finding | Starts at | Its own questions | Its limits | Actions |
|---|---|---|---|---|---|
| `products` | product | Google Shopping | budget each, must / nice / avoid, needed by | price | Buy |
| `apartments` | listing | Google Maps (buildings), then the web | where (required), rent up to / from a month, beds, baths, pets, move-in, a place to measure from + miles at least / at most + directions | rent/month ≤ and ≥, beds ≥, baths ≥, pets includes, available ≤ move-in, distance ≥ / ≤, direction any of | Apply |
| `places` | place | Google Maps | near (required), must / nice / avoid | — | — |

A kind's answers become constraints with `source: brief`, like a typed
budget: the plan can't drop them, a refine may change them (its
`limit_keys` are left out when the refined plan is finalized). The planner
is told the kind (`prompts.plan_instructions`) and gets every answer by the
kind's own labels (refine too). A budget has a unit only when the kind
says so (`budget_unit`: apartments' rent is a month); generic research's
has none, so it compares with a price in any unit and a home to buy isn't
read as a monthly rent. `research` stays the catch-all. A task row's
`playbook_label` names its kind for the app.

### Distance from a named place (`research/geo.py`)

An apartments brief's `near` ("Lady Bird Lake") is the anchor: found once per
task by `phases.ensure_anchor` (Google Maps through the provider, one provider
call; else the US Census geocoder for a street address) and kept in the plan
as `anchor` (`{name, lat, lng, source, label}`, or `{name, error}`, so a place
that can't be found isn't looked up again). A finding's point: a Google Maps
result's `gps_coordinates` (`ProviderItem.point`), its page's schema.org `geo`
(`page_extract` adds `geo` to a listing or place only when the page has one),
else its stored address through the Census geocoder (a street number needed).
`distance` (miles, straight line, shown "12.4 mi north") and `direction` (the
quarter of the compass it lies in: north is within 45° of due north) are
`fields.COMPUTED`: arithmetic, never a model's claim (not in the discover
contract's fact enum; `_fact` drops them), as verified as the point they came
from. `min_miles` / `max_miles` / `directions` become `distance gte` /
`distance lte` / `direction any_of` limits; without a `near`, a plan carries
no distance limits, preferences or columns. `near` itself isn't refinable (a
new place is a new task); the miles and directions are.

Where the map is searched follows the limits, not the planner's queries:
`geo.areas` puts a map centre (`@lat,lng,12z`, the providers' `ll`) out in
each direction asked (between the miles, or 5 past "at least", or
`DIRECTION_MILES` with none), or on the anchor for "within", and
`run_providers` searches the kind's `area_query` ("apartments") around each
before the plan's own queries, at 13z (at 12z Google drifted to the city's
dense middle: a centre 15 mi south came back 4-9 mi out). A planner that
writes four northern suburbs and one southern one still gets the south
searched, and with two or more directions `prerank` takes the room (30
buildings) from each in turn (`by_direction`), not whichever way most
queries leaned. A distance preference always ranks nearer first: the model
can't flip `higher_is_better` on a computed field ("at least 10 miles" is a
limit, not a wish to be far away; a run where it did ranked Georgetown at 33
mi over Kyle at 18 and cut the south).

Google Maps results in an apartments task are listings (`phases.as_kind`),
without Maps' "cuisine" and price level. Move-in specials (`specials`) are read
from a listing page's text by `scan_listing_text` (time free, then money off,
then deposit, then fees and Look & Lease; the biggest kind wins) or claimed by
the model with a quote. A preference on `specials` ranks a finding that has
any above one that doesn't (`fields.PRESENCE`: the only text fields a
preference may name).

A building's rent is every figure its floor plans state, not one number.
`enrich_one` treats a Google Maps listing as a building: its page and then its
floor plans page (`plans_link`, same site; viewed in the browser when the
figures are drawn by JavaScript) are read by `building_rent`, which keeps each
plan's `[low, high]` in `price.spans` (`high` None for "starting at") and shows
"$1,123–$1,939+/mo". A building that only gives one figure is "From" it
(`fields.starting_at`). A rent limit is met when any span overlaps it
(`ranking._in_range`): a "starting at" below the range is Unconfirmed (dearer
homes may fit), above it a violation.

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
  then the ranking-only summary. Its top picks are always five (or every
  finding shown): the model's, then the ranking's best it left out
  (`fill_top`).
- **Budgets per round** (`Budgets`): 30 provider calls (searches and store
  lookups), 100 page loads (a building costs two: its page and its floor
  plans), 6 browser views, reserved with `chain.grant` before use and refunded after.
  80 findings per task, 120 once it searched more. Counters reset when a
  round starts.
- A page drawn by JavaScript is viewed in the browser only when the browser
  worker exists (`AGENT_BROWSER_QUEUE`) and the view budget allows.
- The model never writes: phases store what the contracts let through, under
  the chain's token.
- **A research finish tool's arguments are the answer's own fields**, not one
  `result` object (`contracts._finish`). Wrapped, Claude Haiku sent the
  object as JSON text now and then, sometimes broken, and every summary of
  the run fell back to the ranking's. `_result` still reads `{"result": ...}`
  and an object or list sent as JSON text (`_unquoted`); a summary gets two
  repairs.

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

Agent cards as tasks (`engine` `board`; the columns exist). Book (places) and
Email-about-it (apartments) actions; a travel playbook. Distance for places
(the same `near` on the places kind).
