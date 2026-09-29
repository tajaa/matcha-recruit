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
| Reviewer sends it back (existing reject + note) | `changes_requested`; round N+1 runs **while it stays there** | `tasks.py` reject hook → `reason="redirect"` |
| Approve | `done` | existing `approve_project_task` |
| Failure | column unchanged; `progress_note` = "Agent stopped: … Use Run again" | `POST …/tasks/{t}/agent-runs` reruns |

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
- **AutoPR must never pick these up.** AutoPR maps unknown categories to the code lane. Both `apps/msandbox/harness/collect.sh` and halion's `collect.sh` drop `category == "agent"`.

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
  - ≤10 page loads;
  - 300s wall clock.
- **Last turn:** forces `tool_choice=finish` with no search tool.
- **Bad finish:** one repair turn, then fail.

## Queue

`enqueue` dispatches to `$AGENT_CARD_QUEUE`, or to Celery's default queue if that is unset. The main worker runs `--concurrency=1`, so production should run a dedicated worker:

```
celery -A app.workers.celery_app worker -Q agent_cards --concurrency=3 --max-tasks-per-child=20
```

Then set `AGENT_CARD_QUEUE=agent_cards` on the API. Until then, runs share the main worker.

## Endpoints

- `GET /matcha-work/projects/{p}/tasks/{t}/agent-runs`: rounds, newest first, with result and steps.
- `POST /matcha-work/projects/{p}/tasks/{t}/agent-runs`: run again. Returns 202, or 409 while a run is live or the card is in review/done.
- Create and reject responses carry `agent_run` (`{run_id, round, status}`) or `agent_run_error` (the gate's `detail`).
