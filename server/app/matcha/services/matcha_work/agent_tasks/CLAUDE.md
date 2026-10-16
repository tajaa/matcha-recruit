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
| Emailing | `mail.py` | The account's email gets the headline, summary and top picks when a task ends (once a round) |
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
busy. The 24 hours start at the first of them (a fixed Redis window), so the
sentence and `Retry-After` say when they end, from the key's TTL.

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
Entrata, AppFolio, ...) beats anything else; job and career links are skipped,
and so is fine print (`_FINE_PRINT`: "Restrictions apply" on a specials banner
used to beat the portal's "Lease Online Now"); https only (the listing's own
site as served). Links come from `page_extract.anchors`, the one link reader
the floor plans finder and `page_links` share. None found, or the page can't
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

## Telling the person (`notify.py`, `mail.py`)

A task runs entirely in the worker chain, so the person can start one and
close Espresso; nothing waits on the app (opening it only nudges a stalled
chain sooner than the main worker's hourly `reconcile`).

- **Bell + live push** (`notify.py`) when a task is done, stopped or waiting.
- **Email** (`mail.py`) to the account's address (`users.email`; none for an
  inactive or suspended account) when a round ends `done` or `failed`: the
  headline, the summary or why it stopped, and the top picks (`chat.picks`,
  the same ones as the chat card) with up to 4 facts in the plan's column
  order (unconfirmed ones left out), the homes that fit, the summary's "why"
  and the finding's link (http(s) only; everything HTML-escaped). Sent as
  "Espresso" through `send_email_with_fallback`, so reserved test domains are
  never sent to.
  - **Once a round:** `close_round` returns True only for the call that
    settled the round, and `_stopped` emails only then. A waiting task's round
    stays open, so it sends nothing.
  - **Not while the person is there:** a round settled within `EMAIL_AFTER`
    (60 s) of being asked (a refine that only re-sorts, a document) sends none.
  - **Job searches** are emailed their top `TOP_LEADS` jobs once, when
    `search_stopped` completes the pointer.
  - Best effort: a failed email never fails the task. There is no opt-out
    setting yet.

## Research (`research/`)

`plan -> providers -> discover -> enrich -> screen -> rank -> summarize`;
refine starts at `refine`, "search more" at `providers`.

| Piece | File |
|---|---|
| Field library, reading pages, checking claims (pure) | `fields.py` |
| Hard constraints, bands, scores (pure) | `ranking.py` |
| Finish contracts and their checks (pure) | `contracts.py` |
| Google Maps from Google's Places API (New) Text Search (`GooglePlaces`, `GOOGLE_MAPS_API_KEY`, the key Tell-Us uses), else as Shopping is; Google Shopping via SearchAPI (`SEARCH_API_KEY`), else SerpApi (`SERP_API_KEY`); a Shopping product's stores (`stores`, `with_store`); `choose_provider(source)` puts the ones with keys in that order (`Listings`), so Shopping falls back to SerpApi and Maps to the SERP APIs, by `matcha_work/search_apis.py`'s rules (shared with job search): one that refuses for good (a refused key, no searches left) is dropped for the phase and logged once as an error, one still down after its retry is passed over when another follows. With every one refused, nothing more is asked that round (no store lookups either); the web search still runs | `providers.py` |
| The model's page loader: agent cards' page facts plus the page's same-site links | `fetch.py` |
| No-model phases, `rerank`, `Deps` | `phases.py` |
| Model phases | `model_phases.py` |
| Brief + intake fields (`ResearchBrief`, `ApartmentBrief`, `validator`) | `brief.py` |
| Where a finding is: the anchor, distance and direction (`resolve_anchor`, `distance_fields`, `from_address`) | `geo.py` |
| Kinds of search: products, apartments, places (data) | `kinds.py` |
| An apartment building's homes one by one from its leasing system: SightMap, Avalon (pure, plus `find_units`) | `units.py` |

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
task by `phases.ensure_anchor` (Google Maps through the places provider, one
provider call; else the US Census geocoder for a street address) and kept in the plan
as `anchor` (`{name, lat, lng, source, label}`, or `{name, error}`, so a place
that can't be found isn't looked up again). A lookup that failed rather than
found nothing (a provider error, a geocoder error, or no provider calls left)
is kept with `transient` and `tries`, and the next step tries again, up to
`ANCHOR_TRIES` (3) times in all; otherwise one rate limit would leave every
distance Unconfirmed for the life of the task. A finding's point: a Google Maps
result's point (`gps_coordinates`, or Places `location`: `ProviderItem.point`), its page's schema.org `geo`
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
dense middle: a centre 15 mi south came back 4-9 mi out). `GooglePlaces` turns
`ll` into a `locationRestriction` rectangle (`providers.map_box`: 5 mi each way
at 13z, doubling per zoom level out), so its answers stay inside the area; the
search APIs take `ll` as a map centre. Live on 2026-10-15, Lady Bird Lake +
"at least 10 mi, north or south": 20 places 10–17 mi north (19 with their own
site), 12 places 11–20 mi south (7). A planner that
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
(`fields.starting_at`). A building has no rent (`_no_rent`) only when it has
no price or every span is "starting at"; then its floor plans (and its own
page, viewed) are read, and their rent replaces the one there only if it is a
real one (`_take_rent`), never another "starting at". A figure that is the
front of a bigger one ("$1,250,000", a sale price) is never a rent. A rent limit is met when any span overlaps it
(`ranking._in_range`): a "starting at" below the range is Unconfirmed (dearer
homes may fit), above it a violation.

### A building's homes, one by one (`research/units.py`, `agenttask05`)

Where a building's site names its leasing system, `enrich_one` keeps every
home to let in `mw_agent_task_items.units` (cheapest first, at most
`MAX_UNITS` 80): number, floor, plan, beds, baths, sq ft, rent, move-in date,
lease length, special, floor plan image, tour link, its own page. Two systems
answer a plain request:

- **SightMap**, the unit map embedded on many buildings' sites (Brookfield,
  Essex, Jonah and others): `sightmap.com/embed/<id>` in the page (often
  JSON-escaped), whose embed page names its API
  (`sightmap.com/app/api/v1/<x>/sightmaps/<n>`). Two loads. A map with no
  rents (AVA's) lists nothing. Its API always sends gzip, so it is loaded with
  `fetch_public(gzip=True)`, which inflates a bounded amount at a time. Its
  homes carry no page of their own (`url` None): the unit map is the building's.
- **Avalon** (`avaloncommunities.com` pages only): `communityId: 'AVB-CA104'`
  in the page, then `api.avalonbay.com/json/reply/ApartmentSearch`. One load;
  its community promotions too. A home with no unit key in its id is known by
  `<floor plan>#<number>` (no page link); one with neither is skipped.

Its own page is tried first, then its floor plans page (`plans_page`), which a
building now loads even when its own page gave a rent: the unit map is often
only there. **A building's page loads are its own:** `BUILDING_LOADS` (4) is
its site, its floor plans page and `LEASING_LOADS` (2) leasing-system loads,
checked against a per-building `Budget` before the round's shared one, and a
system already asked (`avalon:<code>`, `sightmap:<id>`, the shared `tried` set)
is never asked again from the floor plans page, so an AVA-style building (an
Avalon code with no homes plus a rentless unit map) can't spend other
buildings' loads. A building whose system answered gets its price, soonest
move-in and special from its homes (origin `leasing`, which outranks
`jsonld` and a provider: the leasing system is the building's own current
list), with the cheapest home as the quote; its floor plans text is not read
and no view is made. Otherwise everything above applies unchanged. 403s to a server
(Vara, Strata, OLUME, Hanover, Equity) and RentCafe/RealPage/AppFolio
widgets are not read yet.

- **A building with homes is judged on its homes.** A limit on rent, beds,
  baths, sq ft or move-in date (`ranking.UNIT_FIELDS`) is met only when one
  home meets all of them at once (`unit_verdict`), never one home's rent with
  another's bedrooms. Every home breaking one limit names that limit ("From
  $4,211/mo (18 homes)"); otherwise "No home here meets every limit at once".
  A home missing a figure makes the building Unconfirmed, not hidden. A
  building that breaks a limit of its own (no dogs) has no home that fits:
  `units_fit` is empty. The homes that fit are `rank_explain.units_fit`; the app shows "3 of 18 homes
  fit · from $X" (`items.homes_view`) and marks each home (`units_view`).
- **Net rent comes only from free time a special states** (`units.net_rent`):
  "6 weeks free", "1 month free", "first month free", over the lease the
  special or the home states (12 months, said to be assumed, when neither
  does). "Up to …" is a ceiling, so no net. Avalon's own net effective rent
  is used when no special gives one. A rent limit is met when the net rent is
  inside it (each home's price spans net to gross), as the person asked
  ("if the promo makes it less than 3.1k that will count"). `units.lowest_rent`
  is the one rule for a home's lowest rent (net, else gross); ranking, the
  building's span, its cheapest home and `homes_view` all use it.
- **Floor plans are ours or nothing.** A home keeps the leasing system's
  plan as `plan_source` (stored, never sent to the app: `units_view` drops
  it) and `plan_image` is our CDN copy or None. `rehost_plans` copies up to
  `PLAN_IMAGES` (8) new plans a building a pass, the plans of homes that meet
  the limits first, within `PLAN_IMAGE_SECONDS` (45 s), reusing copies a
  re-read already has. A refine that makes other homes fit copies theirs
  (`fill_plans`, `PLAN_FILL_SECONDS` 30 s, after the rerank; a failure never
  fails the refine).
- **A batch's photos and floor plans are copied at the same time**, the
  photos within `IMAGE_SECONDS` (60 s) as a whole.
- **A page the browser drew is kept apart from the photos**, in
  `mw_agent_task_items.screenshots` (already on our CDN): it never counts
  against the photo caps or stands in for a photo. The app shows it after
  the photos, marked "Its page".
- The model sees a building's `homes`: how many are listed and, before
  ranking, up to 6 example lines; once ranked, how many meet every limit and
  only those homes (`homes_that_fit`), or, when none does, the 3 cheapest as
  `cheapest_not_fitting`, which the summary must never call a fit
  (`items.view_for_model`). A document lists up to 8 homes, fitting first.
- Live 2026-10-16, San Francisco: The George 18 homes, Canyon 26, AVA 55
  Ninth 11, Solaire 19, 1190 Mission 11, Duboce 2, SoMa at 788 6; every one
  with floor plans, four with 3D tours.

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
  lookups; Google Places pages by token, so page n of a search is n calls:
  `providers.calls_per_search`), 160 page loads (a building may cost
  `BUILDING_LOADS` four: its page, its floor plans page and its leasing system,
  whose unit map is two), 24 browser views, reserved with `chain.grant` before use and refunded after.
  80 findings per task, 120 once it searched more. Counters reset when a
  round starts.
- A page drawn by JavaScript is viewed in the browser only when the browser
  worker exists (`AGENT_BROWSER_QUEUE`) and the view budget allows.
  - A building with no rent may take two views: its floor plans page, then
    its own page (some sites draw rents only there). Its own page is never
    viewed twice.
  - An enrich batch views one page at a time, because the browser worker has
    one slot and a view still queued after 20 s comes back busy. No view
    starts after `ENRICH_VIEW_SECONDS` (150 s), so the step ends inside its
    420 s. A view not made goes back to the budget. A row gives up its
    enrich slot while it waits for the browser, so rows that only load a
    page never queue behind views.
  - Measured 2026-10-15 on an Austin search: viewing the 22 buildings still
    without a rent took 32 views and about 2 minutes, and found 4 more rents
    from the buildings' own sites. 7 sites refused the browser too.
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
