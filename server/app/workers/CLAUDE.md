# Background workers — deep detail — feature spec(s)

Moved verbatim from root `CLAUDE.md`'s Feature Flags table. Root keeps a one-line summary + `→ full spec:` pointer here. Default column below matches `DEFAULT_COMPANY_FEATURES` in `server/app/core/feature_flags.py`.

## `handbook_watch` (default ❌)

**Scheduled handbook-freshness monitoring** ("handbook watch") — the paid, automated tier of the freshness stack. Gates ONLY the per-company sweep in the `handbook_freshness` Celery worker + its alert emails (worker SQL filters on the stored flag; the global `scheduler_settings['handbook_freshness']` row remains the kill-switch). The manual `POST /handbooks/{id}/freshness-check` stays free with `handbooks`; findings render in the existing `HandbookFreshnessPanel`. Sold as a **Lite-family add-on** (own Stripe sub, `matcha_lite_addon` checkout — see `services/lite_addons.py`); available to both `matcha_lite` and `matcha_lite_essentials`. A paid gate like `incidents`, so NOT in any tier overlay (merged == stored). Default off; admin-toggle.

## Workers are pool-free (moved from root Key Modules)

- **Workers are pool-free — shared service code must not assume a pool.** `celery_app.py` deliberately never calls `init_pool` (each task runs its own `asyncio.run()` loop; an asyncpg pool bound to another loop can't be reused). `database.connection_or_direct()` yields a pooled connection when one exists and a raw one otherwise — use it in shared code that runs in **both** worlds. This is load-bearing: `rate_limiter` and `platform_settings` (the model-mode lookup) sit on the path of **every Gemini call in the codebase** and hard-required the pool, so **no Celery task could call Gemini at all** — it raised in `check_limit` *before* the API call and surfaced only as research that mysteriously produced nothing. Prefer an explicit `conn=` param on worker paths (as `get_recent_corrections` now takes); `connection_or_direct` is for the narrow middle with no caller context.

`tasks/project_agent.py` follows that rule for Espresso's two project tasks:
the WebSocket path persists `repo_question` runs, while the desktop board's
idempotent REST enqueue persists `task_draft` runs. The pool-free worker performs
the same bounded, audited GitHub reads for both; questions post to project chat,
while drafts are polled into the review sheet. Worker startup reconciles
queued/running rows older than 15 minutes to `failed`.


## ir_deadline_alerts (moved from root Background Workers)

- `ir_deadline_alerts` — IR deadline/SLA nudges (overdue corrective actions, stale critical incidents, unclassified OSHA recordables before the 300A/ITA deadline, OSHA 8/24hr emergency window). Scheduler row seeded disabled; dedup via `ir_corrective_actions.reminder_sent_at` + `ir_deadline_alert_log`.


## hr_proactive_push (moved from root Background Workers)

- `hr_proactive_push` — **opens** pre-briefed HR Pilot threads ahead of an HR event (the only worker that creates a matcha-work thread): leave returns (`leave_requests` return date in 7d), discipline hitting `review_date`/`expires_at` (two distinct kinds — a record can fire both), and a weekly per-company digest of `employee_documents` stuck in `pending_signature`. Writes `mw_threads`(`hr_pilot_mode=true`) + an `assistant` briefing + `mw_notifications`(`type='hr_proactive'`) + the ledger stamp in ONE transaction. Briefings are **deterministic templates — no Gemini call in the worker**; the grounded/cited turn happens when the supervisor replies. Dedupe (`hr_proactive_push_log`, migration `hrpush01`) is **one-shot-ever per subject** for the dated triggers (a deadline is a single event; re-raising it daily trains people to ignore it) and **weekly** for the company digest. Worker is pool-free — raw INSERTs, not `doc_svc`/`notification_service`, so there's no live WS bell push (60s REST poll surfaces it). `created_by` = the employee's manager if `manager_id` resolves to an active user, else the oldest company client; threads are company-visible regardless. Scheduler row seeded disabled.

## schedule_auto_generation

- `schedule_auto_generation` executes one tenant/location rule from `schedule_automation_rules` at its exact Celery ETA. It is not part of the worker-ready global sweep. Saving a rule enqueues its current `schedule_version`; edits and disables invalidate already-queued jobs, and a weekly execution enqueues its own next occurrence. The task uses the shared deterministic planner through the pool-free path, writes a review proposal only, and never creates or publishes shifts. A manager cancellation remains terminal for that automatic location/week.
