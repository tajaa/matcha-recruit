# Agent runtime (the Espresso assistant)

One bounded agent loop, and a registry of abilities it can use. A person asks
Espresso in chat ("reply to the landlord and say Friday works", "book Nopa for
four on Friday at 7"); each message is one run.

Agent cards (`../agent_card/`) are a caller of this same loop, and so are Job
search's model phases (`../job_search/agent_phase.py`, run kind `job_search`).
There is one loop in this package and no other: do not add a second.

## The shape

| Piece | File | What it owns |
|---|---|---|
| Registry | `registry.py` | `AgentTool`, `Ability`, `validate_catalog`, `offered_tools`. Standard library only |
| Loop | `runner.py` | Budgets, dispatch by name, forced finish, one repair, the commit pipeline |
| Policy | `policy.py` | `evaluate_commit`: allow / confirm / deny. Pure: no I/O, no clock, no model |
| Result | `result.py` | `agent_result.v2` (headline, summary, typed blocks); reads v1 as v2 |
| Catalog | `catalog.py` | Every ability, and `abilities_for`: the only filter on what a run gets |
| Abilities | `abilities/*.py` | `web`, `screenshots`, `shopping`, `flights`, `email`, `calendar`, `reservations`, `purchase`, `domains`, `sales`, `jobs` |
| Chat entry | `chat_entry.py` | A chat message on its way to a run; answers to questions |
| Enqueue | `enqueue.py`, `quota.py` | Gates, the daily allowance, one live run per person per conversation |
| Models | `models.py` | The model menu and which model a run uses |
| The run | `assistant.py` | Builds the context, runs the loop, posts what came of it |
| Questions | `prompts.py`, `ask.py` | `ask_user` and `confirm_action`, in `mw_agent_card_prompts` |
| Progress | `chat_progress.py` | One progress message per run + `agent_run_progress` events |
| Grants | `grants.py`, `consent.py` | Which abilities a person switched on, and what they agreed to |
| Conversation | `conversation.py` | The private conversation (`channel_scope='assistant'`) |

Worker: `workers/tasks/assistant.py`. REST: `routes/matcha_work/assistant.py`.
Browser: `../browser/`. Migrations: `agentrt01` (run kind, steps, prompts),
`agentrt02` (channel scope), `agentrt03` (grants), `assistbuy01` (shipping
addresses, card billing address, purchases without a project/task),
`assistdom01` (domain registrations), `mwcal01` (the Espresso calendar and the
person's timezone).

## Adding an ability

1. `abilities/<key>.py` with `build(...) -> Ability`.
2. Add it to `catalog.build_catalog`.
3. If it acts outward or sends the person's data somewhere new: a `Disclosure`
   in `consent.py`, `private_only=True`, and `consent_version` on the ability.
4. If it has a result block: `block_schemas` + `gate` on the ability, and a
   renderer in both apps (an unknown block is skipped, never an error).

`runner.py` does not change. `test_adding_an_ability_needs_no_runner_change`
pins that.

## Tool effects

Every tool declares one. The rest of the runtime keys on it.

| Effect | Meaning | Policy |
|---|---|---|
| `read` | Looks something up | none |
| `draft` | Writes something the person still has to act on (a Gmail draft, a to-do on their own board) | none |
| `commit` | Acts outward: sends, invites, books, archives | `evaluate_commit` first |
| `ask` | Ends the run with a question | runner-owned |
| `finish` | The structured result | runner-owned |

A commit tool must declare `targets` and `preview` (`validate_catalog` refuses
it otherwise), and should declare `resolve`.

## Invariants

- **The default is allow.** A person who switched an ability on is not asked
  before each action. Three things override it, all decided in code:
  - `deny`: a ceiling was reached, or a private-only tool ran outside the
    private conversation.
  - `confirm`: the action reaches an address or a site the person never named.
  - `confirm`: the tool is `always_confirm` (spending money: `buy_item`),
    grounded or not. Only a commit tool may set it (`validate_tool`).
- **Grounded means the person named it.** A target is grounded when it is
  literally in the requester's own messages, is their own address, sits on a
  thread or event they pointed at, or (domains) is a booking platform in the
  ability's `trusted_domains`.
  - A thread the agent merely read grounds nothing. Otherwise anyone who
    emails the person becomes someone the agent may write to.
  - A typed address grounds itself only, never the others on a thread it
    appears on. Otherwise an attacker puts themselves on a thread with the
    person's boss and becomes a recipient when the boss is named.
  - A display name never grounds an address ("reply to Dana" is held, and the
    card shows the real address).
  - In a shared chat, only the requester's messages ground anything.
    `history.build_history` returns them apart from the replay.
- **A held action is frozen.** `resolve` turns the model's arguments into a
  complete, self-contained action before the policy sees it. The frozen
  arguments, targets and preview go into the question's payload. A yes starts
  a run that carries out exactly that payload before any model call; the model
  never gets to restate the action between the question and the answer. A
  frozen action needs nothing from the run that froze it, which is why handlers
  read only resolved arguments, never the run's session.
- **A result is never written beside a write.** A `finish` in the same
  response as a `commit` or a `draft` is refused (`runner.WRITES`,
  `FINISH_AFTER_ACTION`): it was written before the write's outcome existed,
  and a failed draft ("that date does not exist") would otherwise be reported
  as done. The model reads the outcome and finishes on the next turn.
- **The claim is written before the call.** `store.claim_step` (status
  `claimed`), then the handler, then `store.resolve_step`. A request that left
  and got no answer resolves to `unknown`, never `failed`, and the model is
  told not to retry. Handlers raise `runner.TransportUncertain` for that; a
  refusal from the provider (an HTTP error status) is a definite failure.
- **Ceilings count what may have happened.** `assistant.load_counts` sums
  `ok`, `claimed` and `unknown` steps, weighted (`weight`: one archive call can
  be fifty actions). Before every commit (including approved resumes),
  `store.claim_step` rechecks every window and inserts the claim in one short
  READ COMMITTED transaction under an owner/tool advisory lock. Concurrent
  conversations and workers share that allowance; provider calls run after
  the reservation commits. Failed calls release their allowance on resolution;
  crashes and unknown outcomes retain it until the window expires.
- **Calendar consent enables live calendar changes by default.** An unset
  `ASSISTANT_COMMIT_MODE` makes the calendar ability live after the user's
  consent; every other commit ability still defaults to dry run. An explicit
  server value overrides all abilities: exactly `live` enables writes, any
  other value pauses them. `RunContext.commit_modes` carries per-ability modes
  through the same policy, ceilings, audit and receipt pipeline.
- **Personal data stays in the private conversation.** `email`, `calendar` and
  `reservations` are `private_only`. `catalog.abilities_for` leaves them out of
  a project chat, and `evaluate_commit` still denies one that got through.
  `conversation.is_private_conversation` also requires that the channel has
  exactly one member.
- **An ability can be per-account.** `Ability.allowance` names an allowance
  the run's `Situation.allowed` must carry (`catalog.allowances_for(user)`;
  `purchases` = `chat_flow.purchases_allowed`). `catalog.offered` is the one
  rule: an ability not offered is not in the run, not listed by
  `GET /assistant/abilities`, not hinted at, and `PUT /abilities/{key}` 404s.
  The worker's claim query carries `requester_role` and `requester_email`.
- **The model is told what is off, not left to say "I can't".**
  `catalog.switch_on_hints` lists abilities this person could use but can't in
  this run (not switched on, private-only, needs Google) with what would turn
  them on; `build_system_prompt(unavailable=…)` puts that in the prompt.
  Server-not-ready and not-allowed abilities are left out.
- **The model is never offered a dead tool.** `abilities_for` drops an ability
  that cannot run; `offered_tools` drops a tool whose scope was not granted
  (archive and label without `gmail.modify`).
- **Untrusted content is delimited.** A tool with `untrusted_output=True`
  (email bodies, calendar events, fetched pages in assistant runs) reaches the
  model wrapped as data with a note. The audit row for `read_email` keeps who
  and what, never the body.
- **Result blocks are rebuilt, not trusted.** `emails` and `events` are built
  from the run's session by id, and so is `screenshots` (each one the run took
  with `view_page`, already on our CDN) and `flights` (each offer from the run's
  `FlightSession`, through `agent_card.schema.gate_flights`; the model's prices
  are ignored); `reservation` is written by the server and
  what the model put in the block is ignored; `picks`, `sections` and
  `sources` go through the agent-card provenance gates.
- **Private-conversation runs are not stored by the provider.** `RunContext.
  store_responses` is False for every run in the private conversation (its
  replayed history can hold earlier mail and calendar answers, even when this
  run has no such ability) and for any run with a private-only ability. Such a
  run cannot chain on `previous_response_id` (there is nothing stored to chain
  onto), so the runner sends `chain=False` and resends the whole conversation
  every call: the request, each response's output items as returned (reasoning
  comes back as `reasoning.encrypted_content` and goes back as is), and the
  tool outputs. A stored run sends only what is new.
- **The model is settled at enqueue.** `models.py` owns the menu: OpenAI Luna,
  plus Claude Haiku/Sonnet 5.5 when the server has an Anthropic key. Espresso's
  assistant header sends the pick as `assistant_model` on each socket message;
  `models.resolve` keeps it only if offered, else uses the default (Admin →
  Settings → *AI models* for `espresso.assistant`, else Luna). An explicit pick
  wins over that setting. The row's `model` is what the worker runs; a model
  the server stopped offering by then runs the default and is re-stamped. The
  menu reaches the apps as `entitlements.workspace.assistant_models` /
  `default_assistant_model`. No plan check: Sonnet and the assistant are both
  Pro and up.
- **Claude runs keep the turn in-process.** When the run's model is Claude
  (picked, or the admin setting for `espresso.assistant`), `ClaudeSession.keeps_history` makes the runner send only
  what is new even on a private run: Messages has no stored-response chain to
  opt out of, so `store=False`/`chain=False` and the encrypted-reasoning replay
  do not apply. Web search becomes Anthropic's server tool; its results reach
  the provenance gate as the same Responses items (`claude_client.output_items`).
- **Card runs store `agent_result.v1`, byte for byte.** `agent_card/agent.py`
  keeps its limits and collaborators as module attributes read at call time,
  because its tests patch them there. Do not move them behind a re-export.
- **This package never imports `werk`.** `conversation.py` writes `channels`
  rows with the scope as a literal, and chat posts go through the existing
  `project_agent/chat.py` bridge. The matcha → werk boundary stays at the two
  fan-out imports it has.

## Photos and screenshots

Two ways an answer shows pictures. Neither is ever a hotlink: the clients
render https images only, which means our CDN.

- **`photos`** (`abilities/web.py`). `fetch_page` notes every image a loaded
  page returned (`og_image`, products' `images`) with the page it was on
  (`remember_images`). A `photos` block may use only those; the page is taken
  from that record, not from the model. Before the result is stored,
  `assistant._deliver` rehosts each photo through `agent_card/images.py` (the
  same SSRF-guarded fetch and Pillow re-encode as pick photos), and a photo
  that cannot be rehosted is dropped. At most 6. Picks and photos go through
  one `rehost_images` call (`photos=`), so they share its budget of 6 images
  and its deadline; a photo keeps its own alt text, empty included.
- **`screenshots`** (`abilities/screenshots.py`, tool `view_page`). It opens
  one page in the guarded browser (`../browser`, the main frame kept on the
  page's own site), waits for it to settle, and returns the text as drawn,
  one line per row. That is the point for pages like a building's unit list,
  which only appears with JavaScript and is invisible to `fetch_page`. Like
  `fetch_page`, an HTTP status of 400 or more is a failure, not a page: an
  error or "Access denied" page is never read, cited or screenshotted. A
  page that ends up off its own site fails and says where it went; that is
  checked on the final URL, because the navigation guard never sees an HTTP
  redirect (Playwright routes only a redirect's first request). The
  screenshot is stored through `images.store_image` (WebP, at most 1200px)
  under the run's prefix. The model gets only a `screenshot_id`, and the
  block is rebuilt from the session by id. At most 4 views per run and 4
  screenshots in an answer. Each view launches its own Chromium (on the
  browser worker every task is a fresh process anyway) and is held to
  `VIEW_SECONDS` from launch to screenshot. Offered only where
  `AGENT_BROWSER_QUEUE` is set (see Queues); read-only and no consent, so it
  is listed as "Not set up on this server yet." until then.
- **A gate never costs the answer.** `result.normalize` drops a block whose
  gate raises anything but `ValueError` (the ask-again signal), with a
  warning, so odd model input (a list where an id goes) loses that block only.

## Buying (`abilities/purchase.py`)

`prepare_purchase` (read) loads, from the database, the buyable picks of the
person's last few results **in this conversation** (`item-N`, via
`chat_flow.pick_offer`: first verified buy link, source-checked price or
none), their unexpired cards (`card-N`) and shipping addresses
(`address-N`, default first). The model sees names, stores, prices, "Visa
ending 4242" and "Haley Smith, Oakland CA" — never a card number, street or
phone. `buy_item` (commit, `always_confirm`) names those ids; `resolve`
freezes item, card, shipping and billing (card's own, or `None` = same as
shipping) into the question payload, so the yes buys exactly what the card
showed.

- A missing card or address ends the run with `purchase_setup`, a
  server-written block (`Ability.auto_blocks` adds it even when the model
  leaves it out; what the model writes in it is ignored). Both apps render it
  with a link to Settings. Card numbers and addresses are never collected in
  chat.
- The handler re-reads the card (removed/expired ⇒ nothing bought), inserts
  `mw_agent_purchase_requests` (`channel_id` + address snapshots, no
  project/task), then charges through `agent_card/test_charge.py`: a Stripe
  **test-mode** charge with a verified price and a test key, else a handoff
  (checkout link). No real money moves.
- **One yes buys once.** The row's `prompt_id` is the approved confirmation
  (`RunContext.resume_prompt_id`, UNIQUE, `ON CONFLICT`): a second run of the
  same yes reports the first outcome and never inserts or charges again; the
  Stripe idempotency key is the row id. A row is `charging` from before the
  Stripe call until its outcome is written; a crash or timeout in between is
  an `unknown` receipt (`TransportUncertain`), and the next attempt on that
  approval re-charges under the same key, which settles it.
- **Buyable = an https buy link.** "It" is the latest *answer* (a run with a
  headline; question-only and held runs don't count). When that answer had
  nothing to buy, the model is told to ask rather than buy an older pick.
- Gated three ways: `purchases_allowed` (allowance), the `purchase-1`
  disclosure (switched on in Espresso's settings), private conversation only.
  `ASSISTANT_COMMIT_MODE` still applies: unset, a yes gives a dry-run receipt.
- Real checkout (sending the address to a merchant) needs a new disclosure
  version before it ships.

## Domains (`abilities/domains.py`)

`check_domains` (read) asks Porkbun for availability and the live first-year
price of up to four registrable names per call and keeps what it saw in the
run. `register_domain` (commit, `always_confirm`) takes a name the run saw
free; `resolve` freezes `{domain, cost_cents}` from that check, never from
the model, and Porkbun itself refuses a `cost` that doesn't match its live
price.

- **Real money.** Unlike `purchase`, nothing is test mode: registration draws
  on Matcha's funded Porkbun balance and the domain is held in that account
  (WHOIS private, renews yearly). Gates: Porkbun keys set (`env_ready`), the
  `purchases` allowance, the `domains-1` disclosure, private conversation,
  `ASSISTANT_COMMIT_MODE=live`, a ceiling of 2 a day, and
  `ASSISTANT_DOMAIN_MAX_CENTS` (default 5000) on price.
- **One yes registers once.** `mw_agent_domain_registrations` is UNIQUE on
  the confirmation; `registering` until Porkbun's answer is written; the
  Porkbun idempotency key is `espresso-domain-<row id>`. A `PorkbunError`
  caused by a transport error is `unknown` and leaves the row `registering`;
  a refusal marks it `failed` and is not retried on a repeat of that yes.
- The client is `core/services/porkbun.py`, shared with Cappe's domain
  reselling. DNS and hosting are not part of this ability.

## Conversation model

Each message is one durable run (`mw_project_agent_runs.kind='assistant'`).
There is no long-lived model session: the last 20 channel messages are replayed
as context. `ask_user` ends a run with a question card; the reply is the next
message and starts the next run.

What carries over from earlier runs, besides their words (`history.py`):

- **A run record.** Each replayed `agent_result` (the 5 newest) ends with a
  line the server writes from that run's own steps of kind `fetch`, `search`
  and `browse`: "loaded …", "searched the web for …", "tried to load …, which
  failed", "did not try … (the run's page budget or time ran out)", and the
  server's own label for flights, bookings and later tools, with ", which
  failed" / ", outcome unknown". A `skipped` step was never tried and is never
  reported as a failed load. Mail and calendar steps are left out. Without the
  record a follow-up run had only the earlier answer's wording and "corrected"
  a page load that had happened.
- **Only the server writes one.** `[system record` in any replayed message
  (a person's, or an answer a page talked a model into) is defused to
  `(system record` before the real line is appended. A separate system item
  would not do: the Claude client turns every non-assistant item into user
  text.
- **Bounded.** Each record is at most 600 characters and counts toward the
  replay's `max_chars`; the oldest messages go first when it does not fit.
- **Verified links, for the answer only.** `earlier_links` collects what the
  5 latest finished runs in this conversation verified: links their stored
  results cite (`agent_card.schema.verified_links`, shared with card
  revisions: sources, buy links, review pages, price and rating sources, photo
  pages, never an image URL), the pages their `photos` and `screenshots` came
  from, and pages they loaded (`fetch_page`) or viewed (`view_page`), newest
  run first, capped
  at 60. Every run in the conversation counts: in a shared chat a coworker's
  answer is already on everyone's screen. They go to
  `RunState.earlier_links`, which only result blocks read
  (`RunState.citable`). Run provenance, and so `resolve_booking`'s check that
  this run found the booking page, never includes them.

The base prompt tells the model to go to the source the person named (the
building's own site, not just the listing), to keep the work in proportion
(a few searches and page loads, more only when the request needs it), to ask
one short question when the request is ambiguous or a choice is theirs, never
to say a page could not be reached unless `fetch_page` failed on it in this
run, and to go by a record when it and an earlier answer's wording disagree.

## Limits and gating

- **Who gets it:** every personal Espresso account (`companies.is_personal`,
  with `matcha_work`), never a business workspace. There is no company flag:
  `eligibility.assistant_available` is the one rule, used by
  `enqueue.workspace_enabled` (preflight, the REST router, entitlements'
  `workspace.espresso_assistant` both apps read), the channel access check and
  the project-chat mention route. `espresso_assistant` is in
  `RETIRED_COMPANY_FEATURES`, so a stale stored value is dropped. Admins are
  gated by it too.
- **Plan:** Pro/Business (`features_for_plan()["assistant"]`). Admins bypass.
- **Daily allowance per person:** `ASSISTANT_DAILY_RUNS` (Pro 30 / Business
  60), UTC day, counted apart from the monthly agent-card allowance. Only
  `queued|running|done` runs count. Surfaced as `quotas.assistant_runs`.
- **Other gates:** workspace token budget, 30 per hour per person.
- **Per run:** 10 model calls, 330s of model turns, 450s backstop in the worker.
- **One live run per person per conversation** (partial unique index). A
  second message while one is live is refused in chat, not queued.
- **Stale runs:** swept at 11 minutes inside enqueue; `reconcile_stale_runs`
  closes the progress card of anything older than 15.

## Queues

`enqueue.queue_for`: a run that has the `reservations` ability (it drives
the browser inside the run) goes to `$AGENT_BROWSER_QUEUE`; every other run
goes to `$AGENT_ASSISTANT_QUEUE`, else `$AGENT_CARD_QUEUE`, else Celery's
default. `screenshots` does not move the run, since it needs no consent and
would otherwise send every run to the browser worker's one slot. Each
`view_page` is its own task there instead (`workers/tasks/assistant.view_page`,
`expires` after `QUEUE_SECONDS`), and the run polls its result. A view still
queued after `QUEUE_SECONDS` is called off with "the browser is busy". The
exception is a run already on a worker that serves the browser queue
(`celery_app.consumes_queue`, read from the `-Q` set when the process
starts): waiting on that queue from its one slot would wait on itself, so the
view runs in-process. That covers the default setup, where assistant runs
fall back to `agent_cards` on the same `matcha-agent-worker`.
Chromium never runs on the main worker: without `AGENT_BROWSER_QUEUE` neither
ability is offered at all. The worker for it is the `matcha-agent-worker` compose service
(profile `agent-worker`).

## The private conversation

`channel_scope='assistant'`, one per conversation, owned by
`channels.assistant_user_id`. `assistthread01` replaces the one-per-person
index with a listing index, preserving the existing canonical conversation.
The unique `(company_id, slug)` remains: `/assistant/channel` opens the canonical
`espresso-<user UUID>` conversation for older clients. New conversations use
an owner-prefixed client request UUID as their slug, making create retries
idempotent; channel + sole-owner membership are written in one transaction.

- `GET /assistant/conversations` lists only this company and owner (50 at a
  time); `POST` creates a separate history; `PATCH /{id}` renames only an owned
  assistant channel. No member, invite, call, broadcast or generic channel
  mutation path is opened by these routes.
- Espresso's desktop picker creates, names and reopens these conversations.
  Switching recreates its channel view so replies and attachments cannot cross
  conversations. Email handoffs open a new conversation with an editable draft
  containing only message/thread IDs, never sender-controlled text or bodies.

- `capability_allowed` decides this scope **before** the platform-admin
  bypass: chat only, owner only, flag on. A platform admin cannot read someone
  else's conversation over REST or the socket.
- Every route that changes who is in a channel, or what the channel is, goes
  through `channels._require_shared_channel`, which refuses this scope. A test
  walks the route table.
- It is never in the shared channel list; the assistant endpoints own its listing and creation.
- A card number typed here is removed before the message is stored, whatever it
  was a reply to.

## Chat messages

| `metadata.kind` | Payload |
|---|---|
| `agent_progress` | `run_id`; history adds `progress` (`status`, `steps[]`) from the run's rows |
| `agent_result` | `run_id`, `result_v2`: `result.chat_view()` |
| `agent_receipt` | `run_id`, `action_receipt`: `assistant.receipt_view()` |
| `agent_card_prompt` | `prompt_kind` `ask_user` / `confirm_action`, `run_id`, `owner_user_id`, `view` (with `view.action` on a confirmation) |

Questions reuse the agent-card prompt message and its socket event
(`agent_card_prompt_updated`), so a button press is a threaded reply through
the normal send, exactly like a card question. Only the person who was asked
can answer. `prompts.parse_confirmation` is a closed list: a confirmation goes
ahead on a clear yes and on nothing else.

## Calendar (`abilities/calendar.py`)

Three calendar sources in one ability:

- **The Espresso calendar** (`../calendar_service.py`, `mw_calendar_events`,
  REST in `routes/work/calendar.py`, the Calendar tab in the macOS app) is the
  default. `list_espresso_events` reads it with the person's dated to-dos;
  `add_espresso_event`, `update_espresso_event` and `delete_espresso_event` are
  `draft` tools: the calendar is the person's alone and nobody is told, so
  nothing is held, claimed or dry-run. They need no Google connection, but the
  ability's consent (`calendar-openai-2`) and the private conversation still
  apply. Update and delete take only an event this run listed or added.
  `from_email_id` links an added event to an email **this run read** (the
  email session's `messages`), so the calendar can show "From email: …".
- **Google Calendar** keeps its commit tools (`create_event` & co.), offered
  only with `calendar.events`. The prompt sends invitations there and nowhere
  else; the Espresso calendar never emails anyone.

The `events` result block gates ids from both sessions and says which with
`calendar` (`google` / `espresso` / `apple`); both apps render it.

**The person's timezone.** The macOS app reports its IANA zone
(`PUT /matcha-work/calendar/prefs`, also on every email calendar suggestion)
into `mw_calendar_prefs`. `assistant.py` reads it into `RunContext.timezone`
(`calendar_service.get_timezone`, which never raises: a missing table logs
and reads as None), `build_system_prompt` then gives the local time beside
UTC, and Espresso-calendar times are written in that zone.

## Apple Calendar (`abilities/apple_calendar.py`)

The connected Mac shares only selected calendars through EventKit. Snapshots
cover 30 days back through 336 days ahead, at most 500 events. Read results
carry freshness and coverage; partial, stale or out-of-range data cannot prove
availability. Only personal events in writable calendars are editable; existing
invitations remain read-only. Google handles invitations.

Consent exposes the Apple tools only in the private assistant. Writes freeze
the connection, original event and new fields, then queue a `handoff` receipt.
The Mac claims once, rechecks consent, live mode, macOS permission, selected
calendar and original event before saving. A missing acknowledgment becomes
`unknown` after five minutes and is never replayed; check Calendar before
retrying. Reconnection cancels pending work and invalidates the old Mac.
The app polls every 30 seconds while open; Calendar settings shows recent
operations. Calendar access is live when ASSISTANT_COMMIT_MODE is unset; an
explicit non-live value pauses writes. Other abilities retain preview defaults.

`mwcal02` adds private connections and actions (user foreign keys with cascading
deletes). Deploy the additive migration before connecting a Mac. EventKit
permission and real iCloud/Google propagation require manual Mac validation.

## Google

Email and calendar ride the person's existing Gmail connection
(`gmail_service.GmailService`). The base scopes cover search, read, draft and
send. `gmail.modify` (archive, label) and `calendar.events` are asked for only
when the person switches that on: `POST /agent/email/connect` takes
`abilities` and requests the union with `include_granted_scopes=true`. The
callback stores what Google granted, not what was asked for. OAuth requests
`consent select_account`, so an existing browser session never silently chooses
the account. Calendar settings shows the connected email address and explains
that selecting a different account replaces the shared Email/Calendar connection.
The calendar feed keeps its existing `error` / `needs_permission` statuses and
adds optional controlled `reason` / `message` fields for reconnection, missing
scope, a disabled Calendar API, throttling and provider failures. Raw Google
error text is never returned. A disabled API requires operator setup; reconnecting
an account cannot enable it.


## Desktop email workspace

`POST /agent/email/fetch` accepts optional `{mailbox: unread|read|all,
page_token}` and returns `{emails, next_page_token}` in pages of 25. With no
body it retains the original unread response for older clients. No fetch
marks a message read. Deleted messages can disappear between listing and
reading; other provider failures fail the page so the client can retry its
current cursor. The desktop rejects stale fetch/triage results when changing
mailboxes and clears cached mail on logout. AI triage processes loaded mail
in batches of 25; the search field filters loaded messages only.

The agent can draft or send to a mailing-list address or a pasted list of up
to 50 total To/Bcc recipients. Bcc recipients are deduplicated against To,
checked by the same grounding policy, frozen into confirmations and included
in previews/receipts. The send tool counts recipients against 100/hour and
200/day. Gmail also reserves recipient attempts in the shared rate-limit
store before sending so concurrent conversations cannot bypass these limits;
a partially refused batch conservatively spends reserved attempts but sends
nothing. Existing 5-message/minute and 50-message/hour limits still apply.
As with the existing send limiter, the fallback is per-process while Redis is
unavailable. Reserved test recipients are skipped. A timeout remains unknown
and must not be retried automatically.

`create_email_label` is a separate Gmail-modify commit with its own receipt.
It reuses an existing label on retry; `label_email` applies it in a separate
step, so a failure after creation leaves a visible empty label and can safely
be retried. The runtime offers these tools only with `gmail.modify`.

Apply `assistthread01` before the new API/app. It drops no conversation data.
Rollback refuses if any owner has multiple conversations; reconcile those
explicitly rather than deleting or merging histories automatically. Neither
migration direction is automatically applied by this change.

## Sales campaigns

`sales` is private-only and requires `sales-1` consent. Tools use
`../sales_service.py` to discover/import contacts, save source-backed research,
organize stages and persist drafts. The existing web tools provide research;
there is no second agent loop. Reads page up to 25 prospects inside the runtime
output budget and return `next_offset`; large text is explicitly marked partial.

- **Addresses are grounded.** An email the agent saves (add *or* update) must be
  typed by the person, printed on a page `fetch_page` loaded this run
  (`RunState.observed_emails`, filled by the web ability), or on mail read this
  run (`ref_participants`). A source URL alone does not vouch for an address.
- **Templates only on request.** `draft_sales_template` refuses unless the
  person's own text mentions a template, and runs with `overwrite=False`: it fills
  prospects with no draft and never replaces one.
- **No sales tool sends mail.** Human review in the desktop Pipeline freezes
  recipient, subject, body and the campaign footer under a server fingerprint,
  in batches of at most 50, before a durable worker sends each message
  separately. Opt-outs (`mw_sales_suppressions`) are honoured at import,
  approval and claim. Details and recovery: `docs/ESPRESSO_SALES.md`.
