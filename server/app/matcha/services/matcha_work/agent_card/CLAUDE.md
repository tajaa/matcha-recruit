# Agent cards (`mw_tasks.category = 'agent'`)

A kanban card whose title is an errand ("Find me the best organic lip balm").
The matcha server answers it with a web agent and a structured result page.
The work runs natively. It is not AutoPR/halion, which is operator tooling on one Mac.
It is not the MCP connector either: that is push-only, so it can't advance a card by itself.

## Lifecycle

| Event | Card column | Code |
|---|---|---|
| Card created (`POST …/tasks`, category `agent`) | forced to `todo`, run queued | `routes/matcha_work/tasks.py` → `enqueue.enqueue_card_agent(reason="created")` |
| Worker claims round 1 | `todo → in_progress` | `workers/tasks/agent_card.py` → `board.claim_column` |
| Result stored | `→ review` | `board.finish_column` |
| Reviewer sends it back (existing reject + note) | `changes_requested`; round N+1 runs **while it stays there** | `tasks.py` reject hook: editor check + `preflight` **before** the card moves, then `reason="redirect"` |
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
