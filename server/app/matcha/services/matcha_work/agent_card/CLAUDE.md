# Agent cards (`mw_tasks.category = 'agent'`)

A kanban card whose title is an errand ("Find me the best organic lip balm").
The matcha server answers it with a web agent and a structured result page.
The work runs natively. It is not AutoPR/halion, which is operator tooling on one Mac.
It is not the MCP connector either: that is push-only, so it can't advance a card by itself.

## Lifecycle

| Event | Card column | Code |
|---|---|---|
| Card created (`POST …/tasks`, category `agent`) | forced to `todo`, run queued | `routes/matcha_work/tasks.py` → `enqueue.enqueue_card_agent(reason="created")` |
| `@espresso find me … to buy` in a project chat | same: new card in `todo`, run queued | `werk/routes/channels_ws.py:_bg_dispatch_espresso_mention` → `chat_create.handle_mention` |
| Worker claims round 1 | `todo → in_progress` | `workers/tasks/agent_card.py` → `board.claim_column` |
| Result stored | `→ review` | `board.finish_column` |
| Reviewer sends it back (existing reject + note) | `changes_requested`; round N+1 runs **while it stays there** | `tasks.py` reject hook: editor check + `preflight` **before** the card moves, then `reason="redirect"` |
| Result stored, project has a discussion chat | Espresso asks "want to see what I found?" | `workers/tasks/agent_card.py` → `chat_flow.offer_result` (best-effort) |
| Approve | `done` | existing `approve_project_task` |
| Failure / broker down / worker killed | column unchanged; `progress_note` = "Agent stopped: … Use Run again" | `POST …/tasks/{t}/agent-runs` reruns |

## Invariants

- **Each run is one `mw_project_agent_runs` row.** Its fields are `kind='card_agent'`, `task_id` and `round`, and the result lives in `result` JSONB, not as a file attachment. The partial unique index `idx_mw_project_agent_runs_task_live` allows one live run per card, and the enqueue path maps its violation to a 409. Migration: `agentcard01`.
- **Worker-safe writes only.** Celery has no pool, and `project_task_service` / `project_file_service` need one. So card writes go through `board.py` on `connection_or_direct()`.
- **Board events use `projects:fanout`.** `board.publish_task_updated` publishes the same envelope `routes/work/project_ws.py` subscribes to. A test pins that the channel names match.
- **Never yank a moved card.** `finish_column` only moves out of `in_progress` / `changes_requested`. A card the person dragged elsewhere mid-run stays where it is, and the result is still stored.
- **Provenance gate.** `schema.normalize_result` drops every buy link, price/rating source, review URL and source that isn't in the run's provenance set:
  - `url_citation` annotations;
  - `web_search_call.action.sources` (requested via `include`);
  - `fetch_page` final URLs plus their JSON-LD offer URLs;
  - links a previous round already verified.

  The model can rank and summarise. It cannot mint a link.
- **Images are rehosted, never hotlinked.** `images.rehost_images` fetches each image through `core/services/safe_fetch.fetch_public`, verifies and re-encodes it with Pillow (WebP, ≤1200px, metadata stripped), and uploads it. Any failure drops the image. The dev local-storage path is not a client URL, so it drops too.
- **Every model-chosen URL goes through `safe_fetch.fetch_public`.** It resolves the host once, requires public IPs only, pins the IP (Host header + SNI), and re-validates each redirect hop. Default ports only.
- **Read-only agent.** The tools are hosted `web_search`, `fetch_page` and `finish`. The prompt treats page content as untrusted data.
- **AutoPR must never pick these up.** AutoPR maps unknown categories to the code lane. The server refuses them (`project_task_service._AUTOPR_EXCLUDED_CATEGORIES`): `request_autopr_run` and `request_autopr_reconsideration` raise, `claim_autopr_run` returns `ok: False`, and `list_autopr_run_requests` filters them out, so no harness version can queue or claim one. `apps/msandbox/harness/collect.sh` and halion's `collect.sh` also drop `category == "agent"`, as a cheaper first filter.
- **A refusal never strands a card.** Send-back runs every gate *before* `reject_project_task` moves the card, so a 403/429 leaves it in Review with the reviewer's note unspent. If the queue refuses after the move (a live run, the broker down) the card sits in Changes requested with its note saved, `agent_run_error` in the response, and "Run again" visible: the clients offer it in any open column with no live run.
- **A dead worker can't block reruns.** `enqueue` fails runs still `queued`/`running` past 11 minutes (Celery's hard limit is 600s) inside the same transaction, before the one-live-run index can 409. The worker also wraps the run in a 420s backstop, and `reconcile_stale_runs` covers the rest. A broker failure at dispatch fails the just-inserted row (it would hold the index and count against the cap).
- **The cap is atomic.** `enqueue` takes a per-user advisory lock (then the per-card one, always in that order) and counts inside it; `preflight` is only the early, friendly check. The rate limit lives in `preflight`, so it also runs before the card moves.
- **AI drafts never choose `agent`.** `task_draft._TASK_DRAFT_CATEGORIES` and `task_draft_agent._CATEGORIES` exclude it (pinned by `test_category_allowlists_stay_in_sync`): a create would 403 for a Free/Lite user and silently spend a run for a Pro user. Agent cards come from the Agent template.
- **Section Markdown is sanitized.** `schema.sanitize_markdown` drops images, raw HTML, reference links and any link or bare URL the run never saw, since `body_md` is the one field both clients render as live Markdown. The clients add a second lock (web renders no `<img>` and only http(s) links; Espresso strips non-http(s) `.link` attributes).
- **Every await on hostile input is bounded.** `fetch_public` has a total deadline (per-socket timeouts never trip on a slow-drip host), requests `Accept-Encoding: identity` and refuses compressed replies (the byte cap counts decoded bytes, so a small gzip/brotli bomb would inflate inside one chunk). `is_global` is the address test (it also excludes CGNAT `100.64.0.0/10`), with NAT64/6to4/Teredo refused. Page extraction is iterative with node/depth caps and runs inside a try, so hostile JSON-LD/HTML is "a bad page", not a failed run. A photo failure (fetch, decode, S3 error) costs that photo only; storage that returns no public URL (`CLOUDFRONT_DOMAIN` unset) drops every photo once, with one warning, instead of uploading orphans.

## Limits and gating

- **Plan:** Pro/Business (`entitlements_service.features_for_plan()["agent_cards"]`, `require_plan(PLAN_PRO)`). Admins bypass it.
- **Monthly cap per user:** `AGENT_CARD_MONTHLY_RUNS` (Pro 40 / Business 100), counted on UTC month. Only `queued|running|done` rows count, so a failed run is free. The cap is surfaced in `GET /matcha-work/entitlements` → `quotas.agent_runs`.
- **Other request gates:**
  - workspace token budget checked (non-admin);
  - `check_rate_limit` 20 per hour per user;
  - tokens deducted after the run, failed runs included.
- **Per run (`agent.py`):**
  - ≤8 model calls;
  - ≤12 hosted searches (`max_tool_calls` per response plus a running total);
  - ≤10 page loads, 25s each;
  - 300s of model turns, 60s of photo work, 420s overall backstop in the worker.
- **Last turn:** forces `tool_choice=finish` with no search tool.
- **Bad finish:** one repair turn, then fail.

## Queue

`enqueue` dispatches to `$AGENT_CARD_QUEUE`, or to Celery's default queue if that is unset. The main worker runs `--concurrency=1`, so production should run a dedicated worker:

```
celery -A app.workers.celery_app worker -Q agent_cards --concurrency=3 --max-tasks-per-child=20
```

Then set `AGENT_CARD_QUEUE=agent_cards` on the API. Until then, runs share the main worker.

`on_worker_ready` (the scheduler dispatch that fires on every worker start) is queue-aware: a worker that doesn't consume Celery's default queue (`_serves_default_queue`) skips it, so the dedicated worker doesn't enqueue every scheduled task a second time.

## Endpoints

- `GET /matcha-work/projects/{p}/tasks/{t}/agent-runs`: rounds, newest first, with result and steps.
- `POST /matcha-work/projects/{p}/tasks/{t}/agent-runs`: run again. Returns 202, or 409 while a run is live or the card is in review/done.
- Create and reject responses carry `agent_run` (`{run_id, round, status}`) or `agent_run_error` (the gate's `detail`).

## Chat questions and purchases (`chat_flow.py`, migration `agentchat01`)

When a run finishes and the card's project has a discussion chat, Espresso asks there "I finished "<card>". Want to see what I found?". The conversation:

| Question (`mw_agent_card_prompts.kind`) | How it's answered | yes | no |
|---|---|---|---|
| `show_result` (7 days) | threaded reply, or a plain "yes" | posts the short read (headline, top pick with price/rating/why/buy link, alternatives); the full page stays on the card. For an admin with a shopping result, asks `purchase` | threaded only: "It's on the card" |
| `purchase` (2 days) | its owner: threaded reply, "buy it", or "yes" within 10 min | no saved card → says where to add one and **stays open**; else asks `pick_card` | "I won't buy it" |
| `pick_card` (2 hours) | its owner: threaded reply, the card's number / last 4, or "yes" within 10 min | the card's number (1, 2, …), its last 4 when unique, or yes with one card → inserts `mw_agent_purchase_requests` and posts the checkout link | cancelled |

Invariants:

- **No model call.** `parse_answer` (threaded replies) is a closed set of yes/no phrases plus a last 4 or a card number. `is_plain_yes` (unthreaded) is only "yes" / "yes please" / "show me" / "show it".
- **Everyday chat is never an answer.** A question answers to a threaded reply, or to a plain message (`_plain_target`) that resolves as follows:
  - an explicit, un-negated buy phrase that points back at the pick (`is_buy_intent`: "buy it", "buy the best one", "purchase this", or a bare "buy"; also when replying to another message, e.g. the result) goes to the sender's **own** open `purchase`/`pick_card`;
  - a bare card number or last 4 goes to the sender's own open `pick_card`;
  - a plain "yes" goes to the sender's own buy/card question only within 10 minutes of it being asked (`FRESH_PURCHASE_QUESTION`), otherwise to the channel's newest `show_result`.

  "ok", "sure" and "don't buy it" never match, and nobody else's message can answer someone's buy question. The WS router (`_routes_to_agent_card`) is regex-only: project discussion chats, no mentions, and no live Huume pill.
- **The agent never says it can't buy.** `prompt.py` tells it to research and pick with exact price and link. The purchase question comes from Espresso after review.
- **Answered once, never from a stale result.** Every claim runs in a transaction that takes `enqueue`'s own per-card lock (`{task_id}:card_agent`). The claim first checks whether a newer run on the card counts (`_NEWER_RUN_SQL`: queued/running/done; failed and never-dispatched runs don't). If one does, it closes the card's open questions and replies "replaced by a newer run". Otherwise it is one conditional `UPDATE … WHERE status='open' AND expires_at > NOW()`. `offer_result` takes the same lock and skips a run that is no longer the latest. `enqueue` closes open questions only **after** a successful dispatch, so a broker failure leaves the current result's questions open. There is one offer per run (partial unique index).
- **Who may answer.** Every question uses the REST API's own rule, `project_service.resolve_project_access`, which `_verify_project_access` also calls. So collaborators and the company's own users qualify, except that employees never reach discipline/recruiting boards, and admins qualify only as collaborators. `purchase`/`pick_card` answer only to their `owner_user_id`, the person who said yes to seeing the result.
- **The approved purchase is frozen and verified.** `purchase_offer` takes the top pick at its first provenance-gated buy link. The total is the pick's **source-checked** `price` with its currency, or nothing ("price not confirmed"). A buy link's own `price` is only the model's claim and has no currency, so it is never offered. The payload is frozen into the question and copied verbatim into the purchase row.
- **Card choice is unambiguous.** Options are numbered and shown with label and expiry. A last 4 digits shared by two cards gets "reply with its number".
- **No real money moves.** By default (`AGENT_PURCHASE_MODE=stripe_test`), an approved purchase with a verified total is charged in **Stripe test mode** (`test_charge.py`, migration `agentchat02`).
  - It only runs with a `sk_test_`/`rk_test_` key: `AGENT_PURCHASE_STRIPE_KEY`, else `STRIPE_SECRET_KEY`. A live key means no charge, never a live one.
  - The saved card's number is never sent to Stripe. Stripe's test payment method for the brand (`pm_card_visa`, …) stands in.
  - The purchase id is the idempotency key. The call runs after the purchase row commits, and the outcome is recorded in `status` (`test_charged`/`test_failed`), `stripe_payment_intent_id` and `charge_error`.
  - With no verified price, no key, or `AGENT_PURCHASE_MODE=handoff`, the purchase is a handoff (`status='handoff'`): the user finishes checkout at the link.

  Real checkout is a later change.
- **Purchases are internal-only in v1** (`chat_flow.purchases_allowed`): platform admins plus the accounts in `AGENT_PURCHASE_ALLOWED_EMAILS` (comma-separated). Everyone else still gets the "see it?" question. The clients show Payment cards when `GET /payment-cards` says `enabled` (or cards exist), never by role.

### Rich chat messages

Every Espresso message in this flow carries structured `metadata` that both apps render as a card: web `components/channels/AgentCardMessage.tsx`, Espresso `Views/Channels/AgentCardMessageView.swift`. The `content` is only a short plain-text fallback, used for notifications and older apps, with **no raw URLs**.

| `metadata.kind` | Payload | Card |
|---|---|---|
| `agent_card_result` | `result`: `result_view()`, which is the headline, a ≤420-char summary, the top pick (https CDN photo, price, rating, 3 reasons, buy link) and ≤3 alternatives | product card with "View at <store>" and an "Also compared" list |
| `agent_card_prompt` | `view`: `{question, offer?, buttons[]}` | the question, an offer preview, and quick-reply buttons |
| `agent_card_receipt` | `receipt`: `receipt_view()` with status `paid_test` / `approved` / `no_price` / `failed` | a receipt labelled TEST MODE |

- **Buttons.** A button sends its `reply` ("Show me", "Buy it", "Use card 1", …) as a **threaded reply** to the question through the normal chat send, so the server path is identical to typing it. A test pins that every button reply parses as the answer it stands for.
- **History.** Chat history (`werk/routes/channels.py` → `chat_flow.overlay_prompt_statuses`) stamps each question with `prompt_status` (open/answered/superseded/expired) and `answer`, so a reloaded chat shows answered questions without live buttons.
- **Links and photos.** Photos render only from https URLs, which means our CDN. Links are http(s) only and open without referrer or opener.

### `@espresso` errands (`chat_create.py`)

`@espresso find me organic sweat pants to buy online. ship home, not office.` creates an agent card and runs it.

- **The card.** The title is the first sentence ("Find me organic sweat pants to buy online") and the whole message becomes the details, so the constraints reach the agent. It is created in To do and moves along the board like any agent card. Espresso replies "On it" with a ticket chip, then asks when the result is ready.
- **Gates.** It uses the same gates as the board, **before** the card exists: the REST access rule, the editor role (`role_can_edit`), and `enqueue.preflight`. A refusal is posted in chat, and no card is created.
- **What counts as an errand (`errand_request`).** It is deterministic:
  - the message has at least 3 words and starts with find / buy / order / compare / research / recommend / "what's the best" / …;
  - in a **repo-connected** project it also needs a shopping signal (buy, price, best, under $…, ship, …), so "@espresso find where we validate webhooks" still goes to the repo agent.
- **"@espresso buy it" with an open buy question** answers that question and creates no card.
- **Buy phrases.** A buy phrase only ever answers a question when it points back at the pick ("buy it", "buy the best one", "purchase this") or is a bare "buy" / "place the order". "Find me socks to buy" is always a new errand.

### Card vault (`core/services/card_vault.py`, `routes/matcha_work/payment_cards.py`)

- **Encryption.** Only the card number is encrypted: AES-256-GCM with keys from `PAYMENT_CARD_KEYS`, never the JWT-derived `secret_crypto` key. Saving fails closed (503) when no key is configured. Each ciphertext is bound (associated data) to its row id and owner.
- **No CVV** column, field or prompt. Brand, last 4, expiry and a label are the only readable fields, and no endpoint returns the number. A **label with more than 4 digits is refused**, because it is plain text shown in chat. `DELETE` removes the row, ciphertext included; past purchases keep a `card_last4` snapshot.
- **Card numbers never go through chat or the model.** Chat only ever shows brand plus last 4. `redact_card_numbers` replaces a card number with `[card number removed]` **before** it is stored, broadcast, emailed or notified. It runs on both the chat socket's send path and `werk/routes/channels.py`'s message edit. It covers:
  - a reply to one of Espresso's questions;
  - any message from someone who owns an open `purchase`/`pick_card` question in that channel.

  Espresso then posts a warning. Ordinary chat is never rewritten, and the lookup fails closed.
- **What counts as a card number (`contains_pan`).** A window of whole digit groups that meets all of these:
  - it is card-shaped: one 13-19 digit group, or groups of at least 4 digits such as 4-4-4-4, 4-6-5 or 8-8, with a short trailing group allowed only after 4-digit groups;
  - it has 13-19 digits;
  - it starts with 2-6;
  - it passes Luhn.

  Separators are up to three whitespace characters (newlines and non-breaking spaces included), `.`, `-` or `/`. Every matching window is found and overlaps merged, so no digits of a card survive. Dates and phone numbers are not card-shaped (0% measured). A random card-shaped digit string matches about 5% of the time, which is why redaction only runs in the purchase context above.
- **Photos.** A card photo in reply to a purchase question gets a "delete that image" warning; nothing reads it.
- **Endpoints.** `GET/POST /matcha-work/payment-cards` and `DELETE /matcha-work/payment-cards/{id}` are per user with a maximum of 5 cards. Adding needs `purchases_allowed` (`403 purchases_unavailable`); anyone can list or delete their own. `GET …/agent-runs` also returns `purchases`, the caller's own only.
