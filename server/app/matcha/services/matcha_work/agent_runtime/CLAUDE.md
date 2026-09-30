# Agent runtime (the Espresso assistant)

One bounded agent loop, and a registry of abilities it can use. A person asks
Espresso in chat ("reply to the landlord and say Friday works", "book Nopa for
four on Friday at 7"); each message is one run.

Agent cards (`../agent_card/`) are a caller of this same loop. There is one
loop in this package and no other: do not add a second.

## The shape

| Piece | File | What it owns |
|---|---|---|
| Registry | `registry.py` | `AgentTool`, `Ability`, `validate_catalog`, `offered_tools`. Standard library only |
| Loop | `runner.py` | Budgets, dispatch by name, forced finish, one repair, the commit pipeline |
| Policy | `policy.py` | `evaluate_commit`: allow / confirm / deny. Pure: no I/O, no clock, no model |
| Result | `result.py` | `agent_result.v2` (headline, summary, typed blocks); reads v1 as v2 |
| Catalog | `catalog.py` | Every ability, and `abilities_for`: the only filter on what a run gets |
| Abilities | `abilities/*.py` | `web`, `shopping`, `flights`, `email`, `calendar`, `reservations` |
| Chat entry | `chat_entry.py` | A chat message on its way to a run; answers to questions |
| Enqueue | `enqueue.py`, `quota.py` | Gates, the daily allowance, one live run per person per conversation |
| The run | `assistant.py` | Builds the context, runs the loop, posts what came of it |
| Questions | `prompts.py`, `ask.py` | `ask_user` and `confirm_action`, in `mw_agent_card_prompts` |
| Progress | `chat_progress.py` | One progress message per run + `agent_run_progress` events |
| Grants | `grants.py`, `consent.py` | Which abilities a person switched on, and what they agreed to |
| Conversation | `conversation.py` | The private conversation (`channel_scope='assistant'`) |

Worker: `workers/tasks/assistant.py`. REST: `routes/matcha_work/assistant.py`.
Browser: `../browser/`. Migrations: `agentrt01` (run kind, steps, prompts),
`agentrt02` (channel scope), `agentrt03` (grants).

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
  before each action. Two things override it, both decided in code:
  - `deny`: a ceiling was reached, or a private-only tool ran outside the
    private conversation.
  - `confirm`: the action reaches an address or a site the person never named.
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
- **The claim is written before the call.** `store.claim_step` (status
  `claimed`), then the handler, then `store.resolve_step`. A request that left
  and got no answer resolves to `unknown`, never `failed`, and the model is
  told not to retry. Handlers raise `runner.TransportUncertain` for that; a
  refusal from the provider (an HTTP error status) is a definite failure.
- **Ceilings count what may have happened.** `assistant.load_counts` sums
  `ok`, `claimed` and `unknown` steps, weighted (`weight`: one archive call can
  be fifty actions).
- **`ASSISTANT_COMMIT_MODE` must be exactly `live`.** Anything else, unset
  included, is a dry run: the action is claimed, audited and shown as a
  receipt, and the handler is never called.
- **Personal data stays in the private conversation.** `email`, `calendar` and
  `reservations` are `private_only`. `catalog.abilities_for` leaves them out of
  a project chat, and `evaluate_commit` still denies one that got through.
  `conversation.is_private_conversation` also requires that the channel has
  exactly one member.
- **The model is never offered a dead tool.** `abilities_for` drops an ability
  that cannot run; `offered_tools` drops a tool whose scope was not granted
  (archive and label without `gmail.modify`).
- **Untrusted content is delimited.** A tool with `untrusted_output=True`
  (email bodies, calendar events, fetched pages in assistant runs) reaches the
  model wrapped as data with a note. The audit row for `read_email` keeps who
  and what, never the body.
- **Result blocks are rebuilt, not trusted.** `emails` and `events` are built
  from the run's session by id, and so is `flights` (each offer from the run's
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
- **Card runs store `agent_result.v1`, byte for byte.** `agent_card/agent.py`
  keeps its limits and collaborators as module attributes read at call time,
  because its tests patch them there. Do not move them behind a re-export.
- **This package never imports `werk`.** `conversation.py` writes `channels`
  rows with the scope as a literal, and chat posts go through the existing
  `project_agent/chat.py` bridge. The matcha → werk boundary stays at the two
  fan-out imports it has.

## Conversation model

Each message is one durable run (`mw_project_agent_runs.kind='assistant'`).
There is no long-lived model session: the last 20 channel messages are replayed
as context. `ask_user` ends a run with a question card; the reply is the next
message and starts the next run.

Entry points:

| Where | How a message gets here | Abilities |
|---|---|---|
| Private conversation | every message, no mention (`channels_ws._bg_assistant_message`) | all the person has |
| Project chat | `@espresso …` that is not code talk and not a shopping errand (`chat_entry.assistant_request`) | `web`, `shopping` only |

In a project chat a shopping errand still becomes an agent card, and a question
about the code still goes to the repository agent. The mention dispatcher tries
them in that order: card, assistant, repository agent.

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

`enqueue.queue_for`: a run that has the `reservations` ability goes to
`$AGENT_BROWSER_QUEUE`; every other run goes to `$AGENT_ASSISTANT_QUEUE`, else
`$AGENT_CARD_QUEUE`, else Celery's default. Chromium never runs on the main
worker: without `AGENT_BROWSER_QUEUE` the reservations ability is not offered
at all. The worker for it is the `matcha-agent-worker` compose service
(profile `agent-worker`).

## The private conversation

`channel_scope='assistant'`, one per person per company
(`channels.assistant_user_id`, partial unique index).

- `capability_allowed` decides this scope **before** the platform-admin
  bypass: chat only, owner only, flag on. A platform admin cannot read someone
  else's conversation over REST or the socket.
- Every route that changes who is in a channel, or what the channel is, goes
  through `channels._require_shared_channel`, which refuses this scope. A test
  walks the route table.
- It is never in the channel list; it is opened with
  `POST /matcha-work/assistant/channel`.
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

## Google

Email and calendar ride the person's existing Gmail connection
(`gmail_service.GmailService`). The base scopes cover search, read, draft and
send. `gmail.modify` (archive, label) and `calendar.events` are asked for only
when the person switches that on: `POST /agent/email/connect` takes
`abilities` and requests the union with `include_granted_scopes=true`. The
callback stores what Google granted, not what was asked for.
