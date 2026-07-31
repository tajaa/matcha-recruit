# Huume threads: EMS events knowledge + promote-to-incident + IR pilot bridge

## Context

EMS events are logged from channels (`@huume <text>`) and reviewed in the `/work/events` tab (route: `WorkRouteTree.tsx:51`). Huume **threads** (`/work/<thread_id>`, `huume_mode=true` — no @mention needed; the whole turn is the agent loop) know nothing about them. From a thread, the user wants:

1. **Ask about events** — "what events were logged this week?" → answerable **with narrative content** (user's explicit call, diverging from the incidents/er_cases metadata-only rule; rationale: pre-promotion documentation already typed openly in a channel; once promoted the record is an `ir_incidents` row and inherits the strict rule automatically).
2. **Promote to incident** — staged, confirm-first action.
3. **Run the incident report pilot** — **both** an IR Copilot chat bridge (persists to the incident's Copilot transcript) AND analysis runners (root_cause / recommendations, cached to `ir_incident_analysis`).

No migration — all state rides `mw_threads.current_state` JSONB. No frontend changes — `RecordViewer.tsx` renders any record shape; `routes/matcha_work/huume.py:172` reads `RECORD_REQUIRED_FEATURE` dynamically (unknown type ⇒ 404, flag off ⇒ 403, zero route edits).

---

## 1. Lift `_EVENT_SELECT` out of routes → new `server/app/matcha/services/ems/queries.py`

Services must not import routes, but `promote_event` needs an event row carrying `channel_name`/`reporter_name` (neither is a column — `routes/ems.py:28-46` resolves them via 5 LEFT JOINs; loading the event any other way files the incident as `#unknown channel` / `reported_by_name="Unknown"`).

```python
"""Shared EMS event SELECT. Lifted from routes/ems.py (2026-07-30) so
services/huume/ems_skill.py can load a promote-ready event row without a
services -> routes import — same lift pattern as services/er/er_case_context.py.
routes/ems.py re-imports these under their old names, so route callers and
their tests are untouched."""

_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"

EVENT_SELECT = f"""
    SELECT ev.id, ev.company_id, ev.channel_id, ch.name AS channel_name, ...
"""  # moved verbatim from routes/ems.py:28-46
```

- `routes/ems.py`: delete the literals, add `from app.matcha.services.ems.queries import EVENT_SELECT as _EVENT_SELECT, _NAME_EXPR` (keep old local names — 4 usage sites unchanged).

## 2. New `server/app/matcha/services/huume/ems_skill.py`

```python
"""Huume EMS skill — promote a logged event into a real IR incident from chat.

Executor contract matches hr_ops_skill.py: assumes evaluate_huume_action
already returned kind=="proceed"; returns {status, message, record_id?,
record_label?, bg_tasks?}; status MUST be exactly "created" on success
(agent.py:702 treats anything else as failure); bg_tasks are (fn, args,
kwargs) tuples the caller awaits post-commit — never awaited here.

The single-flag _HUUME_ACTION_REQUIRED_FEATURE registry carries only "ems";
the incidents+role+status half of the gate is re-asserted HERE per call via
ems.promote.evaluate_promote — the same envelope the REST promote route runs
(routes/ems.py:227), so chat can never promote what the button couldn't."""

async def execute_promote(
    *, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any],
) -> dict[str, Any]:
```

Body:
1. `async with get_connection() as conn:` → `role = await conn.fetchval("SELECT role FROM users WHERE id = $1", actor_user_id)`; `features = await get_company_features(company_id, conn=conn)` (`app.core.feature_flags`).
2. `row = await conn.fetchrow(f"{EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2", event_id, company_id)` → `None` ⇒ `{"status": "error", "message": "No logged event with that id exists for this company."}`.
3. `verdict = evaluate_promote(role=role, features=features, event_status=event["status"])` → refuse ⇒ `{"status": "error", "message": verdict.reason}` (covers missing `ems`, missing `incidents`, wrong role, already promoted/dismissed — one reusable envelope, zero new gate logic).
4. `overrides = {k: action[k] for k in ("title", "incident_type", "severity", "occurred_at", "location") if action.get(k)}` — `occurred_at` already a datetime from `_parse_iso_datetime` in the validator; `promote_event` runs `naive_occurred_at` on it (promote.py:123).
5. ```python
   try:
       async with conn.transaction():
           incident_row, bg_tasks = await promote_event(
               conn, company_id=company_id, event=event,
               channel_name=event.get("channel_name"),
               reporter_name=event.get("reporter_name"),
               overrides=overrides, actor_user_id=actor_user_id,
               actor_email=None,  # resolved from users row below, mirrors route's getattr
           )
   except PromoteRaceError:
       return {"status": "error", "message": "Someone promoted or dismissed this event first — refresh Events."}
   ```
   (fetch `email` alongside `role` in step 1; pass it as `actor_email`.)
6. ```python
   label = incident_row.get("incident_number") or incident_row.get("title") or "the incident"
   return {
       "status": "created",
       "message": f"Promoted the event into incident {label}. The IR classifier and "
                  "policy mapper are running in the background; the record is editable in Incidents.",
       "record_id": str(incident_row["id"]), "record_label": str(label),
       "bg_tasks": list(bg_tasks or []),   # auto-classify + policy-map + notification — same 3 as REST promote
   }
   ```

## 3. New `server/app/matcha/services/huume/ir_skill.py`

Mirrors `er_skill.py` conventions: never raises past the boundary — degrades to `{"status": "error"}`; opens its own connections; releases the connection before any Gemini call (er_skill.py:317-324 rationale).

```python
async def _resolve_incident(conn, company_id: UUID, requested: Optional[str], fallback_id: Optional[str]):
    """Explicit incident_id → the thread's active incident
    (current_state.huume_ir) → a refusal naming both options.
    Returns (incident_id_uuid, error) — mirrors er_skill._resolve_case:241."""
```
UUID-parse guard; existence check `SELECT id FROM ir_incidents WHERE id = $1 AND company_id = $2`.

```python
async def ask_copilot(
    *, company_id: UUID, actor_user_id: Optional[UUID],
    incident_id: Optional[str], state_incident_id: Optional[str], question: str,
) -> dict[str, Any]:
```
1. Empty-question guard (er_skill.py:279 idiom).
2. conn → `_resolve_incident` → `incident, analyses, messages = await load_incident_state(conn, iid, company_id)` (`ir_ai_orchestrator.py:441`; returns `(None, [], [])` if missing → error status).
3. `user_row = await append_message(conn, incident_id=iid, role="user", message_type="text", content=question[:4000], created_by=actor_user_id)` (`:981`); `messages.append(user_row)`.
4. Audit **in the same connection** (er_skill.py:293 rule — "leaving nothing behind because the request came from chat would be a silent gap"): `log_audit(conn, str(iid), str(actor_user_id), "copilot_message", "incident", str(iid), {"via": "huume", "user_message_len": len(question)})`. `log_audit` lives in `routes/ir_incidents/_shared.py:246` — services→routes edge; use a function-local import with a comment pointing at `ir_copilot_flow.py:47 _LazyIrShared`'s docstring (the package's sanctioned deferral for exactly this edge).
5. **Release conn.** `payload = await generate_guidance(incident=incident, analyses=analyses, messages=messages)` (`:486` — DB-free; rate limit `check_limit("ir_analysis","ir_copilot")` is internal).
6. Fresh conn → `persist_assistant_round(conn, incident_id=iid, user_id=actor_user_id, user_message=None, guidance_payload=payload)` (`:1049`) — the transcript persists, so the conversation continues in `IRCopilotPanel` on `/app/ir/{id}` (legal_skill's one-tables-two-surfaces pattern).
7. Return, cards flattened to text (chat can't click a card):
```python
return {
    "status": "ok", "incident_id": str(iid), "incident_number": incident.get("incident_number"),
    "summary": payload.get("summary"), "open_questions": payload.get("open_questions") or [],
    "suggested_actions": [c.get("title") for c in (payload.get("cards") or []) if c.get("title")],
    "note": "This exchange is saved to the incident's Copilot transcript on the IR detail page.",
}
```

```python
_ANALYSIS_TYPES = ("root_cause", "recommendations")
_GEMINI_TIMEOUT = 60

async def run_analysis(
    *, company_id: UUID, actor_user_id: Optional[UUID],
    incident_id: Optional[str], state_incident_id: Optional[str], analysis_type: str,
) -> dict[str, Any]:
    """Deliberately NOT reusing ai_analysis.run_*_inline — those hard-couple
    to a FastAPI current_user via _get_incident_with_company_check
    (ai_analysis.py:596). Same cache table/keys, so the IR detail panels
    open pre-cached either way."""
```
1. Type guard → error. `_resolve_incident`.
2. Cache probe: `SELECT analysis_data FROM ir_incident_analysis WHERE incident_id = $1 AND analysis_type = $2 ORDER BY generated_at DESC LIMIT 1` → hit ⇒ `{"status": "ok", "cached": True, "analysis": parsed}` (no Gemini).
3. Gather inputs, mirroring the inline runners' bodies:
   - root_cause (ai_analysis.py:270-281): incident row cols `title, description, incident_type, severity, location, category_data, witnesses` → `get_ir_analyzer().analyze_root_cause(...)` with `category_data` json-loaded, `witnesses=[w.model_dump() for w in parse_witnesses(...)]` (`parse_witnesses` from `_shared.py:619` — same lazy-import note as `log_audit`).
   - recommendations (ai_analysis.py:481-544): + `companies.name/industry/size/ir_guidance_blurb` + `business_locations.city/state` → `.generate_recommendations(...)` incl. `root_cause=row["root_cause"]`.
4. `asyncio.wait_for(..., timeout=_GEMINI_TIMEOUT)`; `IRAnalysisError`/timeout ⇒ `{"status": "error"}`.
5. Fresh conn, **upsert** — not the plain INSERT at ai_analysis.py:289/:547, a known `UniqueViolationError` footgun on concurrent/cache-miss re-runs:
```python
INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
VALUES ($1, $2, $3)
ON CONFLICT (incident_id, analysis_type)
DO UPDATE SET analysis_data = EXCLUDED.analysis_data, generated_at = NOW()
```
6. `log_audit(..., "analysis_run", "analysis", None, {"type": analysis_type, "via": "huume"})`. Return `{"status": "ok", "cached": False, "analysis": result, "note": "Cached — the AI Analysis tab on the incident opens pre-computed."}`.

## 4. `services/huume/tools.py`

- Line 26 — `LOOKUP_TOPICS += ("events",)`.
- Line 34 — `SHOW_RECORD_TYPES = (..., "discipline", "ems_event")`.
- Three `_tool(...)` entries appended to `TOOLS` (after the ER bridge block, ~line 530):

```python
    # ---- EMS events skill (feature `ems`; promotion also needs `incidents`) --
    _tool(
        "promote_ems_event", "staged",
        "Promote a logged EMS event into a real IR incident. This STAGES the "
        "promotion for the admin's confirmation — nothing is filed until they "
        "confirm on a LATER turn by calling this again with EXACTLY the same "
        "event_id. Get event ids from lookup_context(topic='events'). The "
        "event's own title/suggested type/severity are used unless overridden. "
        "Promotion is one-way; the incident is a legal record editable in Incidents.",
        properties={
            "event_id": types.Schema(type=types.Type.STRING, description="The EMS event id, from lookup_context(topic='events') or show_record."),
            "title": types.Schema(type=types.Type.STRING),
            "incident_type": types.Schema(type=types.Type.STRING, enum=["safety", "behavioral", "property", "near_miss", "other"]),
            "severity": types.Schema(type=types.Type.STRING, enum=["critical", "high", "medium", "low"]),
            "occurred_at": types.Schema(type=types.Type.STRING, description="ISO datetime. Omit to use the event's logged time."),
            "location": types.Schema(type=types.Type.STRING),
        },
        required=["event_id"],
        intent_hints=("promote", "logged event", "make it an incident", "escalate the event"),
    ),
    # ---- IR Copilot bridge (feature `ir_copilot`) ----------------------------
    _tool(
        "ask_ir_copilot", "write",
        "Ask the IR Copilot for guidance on an incident — a grounded summary, "
        "open questions, and suggested next steps from the incident's own "
        "record and cached analyses. The exchange is saved to the incident's "
        "Copilot transcript on the IR detail page, where the admin can "
        "continue it. Pass incident_id when more than one is in play; omit to "
        "use the thread's active incident (e.g. one just promoted).",
        properties={
            "question": types.Schema(type=types.Type.STRING),
            "incident_id": types.Schema(type=types.Type.STRING),
        },
        required=["question"],
        intent_hints=("incident copilot", "incident report pilot", "guidance on the incident"),
    ),
    _tool(
        "run_incident_analysis", "write",
        "Run one AI analysis on an incident and cache it to the incident's AI "
        "Analysis panels: root_cause (primary cause, contributing factors, "
        "prevention) or recommendations (corrective actions). Returns the "
        "cached result instantly if it already ran.",
        properties={
            "analysis_type": types.Schema(type=types.Type.STRING, enum=["root_cause", "recommendations"]),
            "incident_id": types.Schema(type=types.Type.STRING),
        },
        required=["analysis_type"],
        intent_hints=("root cause", "corrective action recommendations"),
    ),
```
No `discovery=True` (none is a which-X-need-attention batch scan). Hints are multi-word on purpose — `resolve_tier` (routing.py:153) is a plain substring match; a bare `"events"` would deep-route "prevents"/"eventually".

## 5. `services/huume/actions.py`

- `:93-105` — `_HUUME_ACTION_REQUIRED_FEATURE["ems_promote"] = "ems"` with comment: `# incidents half of the gate lives in ems_skill.execute_promote via evaluate_promote — the registry is single-flag.`
- New validator (after `_validate_ir_report`, :279):
```python
def _validate_ems_promote(staged: dict[str, Any]) -> HuumeVerdict:
    event_id = str(staged.get("event_id") or "").strip()
    if not _is_uuid(event_id):
        return HuumeVerdict("refuse", "A valid event_id is required — get one from lookup_context(topic='events').")
    occurred_at = None
    if staged.get("occurred_at"):
        occurred_at = _parse_iso_datetime(staged["occurred_at"])
        if occurred_at is None:
            return HuumeVerdict("refuse", "occurred_at isn't a valid ISO datetime.")
    normalized = {
        "type": "ems_promote", "event_id": event_id,
        "title": (str(staged.get("title") or "").strip() or None),
        "incident_type": staged.get("incident_type") or None,
        "severity": staged.get("severity") or None,
        "occurred_at": occurred_at, "location": (str(staged.get("location") or "").strip() or None),
    }
    return HuumeVerdict("proceed", action=normalized)
```
- Dispatch chain (:188-243): `elif action_type == "ems_promote": return _validate_ems_promote(staged_action)`.
- `execute_huume_action` (:736): `if atype == "ems_promote": from . import ems_skill; return await ems_skill.execute_promote(company_id=company_id, actor_user_id=actor_user_id, action=action)`.
- `PILOT_TOOL_REQUIRED_FEATURE` (:556): `"ask_ir_copilot": "ir_copilot", "run_incident_analysis": "ir_copilot"`. `_PILOT_FEATURE_LABEL["ir_copilot"] = "IR Copilot"`. The generic gate at agent.py:805 then covers both — zero new gate code, and `evaluate_pilot_tool` already enforces role + `huume` + `matcha_work` + flag.

## 6. `services/huume/agent.py`

- `:48` import list += `ems_skill, ir_skill`.
- `_HR_OPS_TOOL_SPECS` new entry — natural-id form (template: `decide_pto_request`, :268):
```python
    "promote_ems_event": {
        "action_type": "ems_promote",
        "match_key": "event_id",
        "mints_confirm_id": False,
        "fields": ("event_id", "title", "incident_type", "severity", "occurred_at", "location"),
        "staged_label": "Staged: promote event to incident",
        "refused_label": "Event promotion refused",
        "done_label": "Promoted event to incident",
        "failed_label": "Event not promoted",
        "done_status": "promoted",
    },
```
- In the `_HR_OPS_TOOL_SPECS` success branch (after :703's `state_updates["huume_action"] = ...`):
```python
                # Promote hands the incident to the IR bridge: "now run the
                # pilot on it" resolves without the model re-asking for an id.
                if done and spec["action_type"] == "ems_promote" and result.get("record_id"):
                    state_updates["huume_ir"] = {
                        "incident_id": result["record_id"],
                        "incident_number": result.get("record_label"),
                    }
```
- `_state_ir()` reader next to `_state_er()` (:424): same three lines over `"huume_ir"`.
- Two handlers after the `ask_er_copilot` block (:898), same shape:
```python
            if name == "ask_ir_copilot":
                result = await ir_skill.ask_copilot(
                    company_id=company_id, actor_user_id=user_id,
                    incident_id=args.get("incident_id"),
                    state_incident_id=_state_ir().get("incident_id"),
                    question=str(args.get("question") or ""),
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_ir"] = {"incident_id": result["incident_id"], "incident_number": result.get("incident_number")}
                step = recorder.record(tool=name, kind="write",
                    label="Ran IR Copilot" if ok else "IR Copilot failed",
                    status="ok" if ok else "error", detail=result.get("message"))
                return _json_safe(result), step
```
(`run_incident_analysis` identical, label "Ran incident analysis", passes `analysis_type=str(args.get("analysis_type") or "")`.) No `_collect_citations` — the IR copilot payload carries no citation records (it grounds on the loaded incident row itself, matching the existing copilot surface).

## 7. `services/huume/record_view.py`

- `RECORD_REQUIRED_FEATURE["ems_event"] = "ems"` (:31).
- Batch builder — **narrative included, per the user's decision**:
```python
async def _model_ems_events_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    # Unlike _model_incidents_batch, this INCLUDES a truncated narrative +
    # doc: an EMS event is pre-promotion documentation the reporter typed
    # openly in a channel, not yet a legal record — the strict no-narrative
    # rule attaches the moment it's promoted (it becomes an ir_incidents row
    # and this builder never sees it again). Deliberate product call, 2026-07-30.
```
`SELECT id, title, category, severity_hint, status, incident_recommendation, suggested_incident_type, suggested_severity, narrative, doc, created_at FROM ems_events WHERE id = ANY($1::uuid[]) AND company_id = $2` — entry: `record_id`, `label` (`title or narrative[:60]`), `category`, `record_status`, `severity_hint`, `incident_recommendation`, `narrative[:500]`, `doc` (json-loaded), `created_at` iso.
- View builder → `{title, chips, meta, sections, link}`:
  - chips: category (zinc), status (`logged`→amber / `promoted`→emerald / `dismissed`→zinc), severity_hint, `{"label": "Flagged for incident review", "tone": "orange"}` when `incident_recommendation`.
  - meta: channel name (join `channels`), reporter (reuse `queries._NAME_EXPR` joins), logged date, clarification rounds.
  - sections: `{"label": "Narrative", "body": narrative}` + one `{"label": key.replace('_',' ').title(), "body": value}` per doc entry + incident_reasoning when present.
  - `link`: `/work/events/{id}` (route exists — `WorkRouteTree.tsx:52 events/:eventId`); when promoted also meta row `Incident → /app/ir/{incident_id}`.
- `_MODEL_BATCH_BUILDERS["ems_event"]` + `_VIEW_BUILDERS["ems_event"]` — the parity test (`tests/huume/test_huume_record_view.py`) asserts all four key sets match, so missing one fails CI.

## 8. `services/huume/onboarding_skill.py` — `events` lookup topic

- `_TOPIC_REQUIRED_FEATURE["events"] = "ems"` (:110 dict).
- Branch in `_lookup_context_impl` (after `er_cases`, :370) — three-state idiom is automatic via the dict:
```python
        if topic == "events":
            # EMS channel-logged events. Narrative IS included (truncated) —
            # see _model_ems_events_batch's note for why this diverges from
            # the incidents/er_cases no-narrative rule. Ids included because
            # promote_ems_event and show_record take them.
            counts = await conn.fetch(
                "SELECT status, COUNT(*) FROM ems_events WHERE company_id = $1 GROUP BY status", company_id)
            window = _clamp_incident_days(days, default=30)
            rows = await conn.fetch(
                """
                SELECT ev.id, ev.title, ev.category, ev.severity_hint, ev.status,
                       ev.incident_recommendation, ev.incident_id,
                       LEFT(ev.narrative, 400) AS narrative, ch.name AS channel_name, ev.created_at
                FROM ems_events ev LEFT JOIN channels ch ON ch.id = ev.channel_id
                WHERE ev.company_id = $1 AND ev.created_at >= NOW() - ($2 || ' days')::interval
                  AND ($3::text IS NULL OR ev.title ILIKE '%' || $3 || '%' OR ev.narrative ILIKE '%' || $3 || '%')
                ORDER BY ev.created_at DESC LIMIT 20
                """, company_id, str(window), query)
            return {"topic": "events", "window_days": window,
                    "counts_by_status": {r["status"]: r["count"] for r in counts},
                    "events": [dict(r) for r in rows],
                    "note": "Promote one with promote_ems_event(event_id=...); open detail with show_record('ems_event', ...)."}
```

## 9. `services/huume/prompt.py`

- `build_state_block`: `ems_promote` branch in the staged-action chain (after `pto_decision`, :110), same shape:
```python
        elif action.get("type") == "ems_promote":
            lines.append(
                f"- STAGED ACTION awaiting the admin's confirmation: promote EMS event "
                f"event_id={action.get('event_id')} into an IR incident"
                + (f" as '{action.get('title')}'" if action.get("title") else "") + ". "
                f"Calling promote_ems_event again with EXACTLY this event_id after the admin "
                f"confirms files it; a different event_id stages a NEW proposal instead."
            )
```
- `huume_ir` block after `huume_er` (:171): `f"- Active incident (IR Copilot bridge): {ir.get('incident_number') or ir.get('incident_id')} — ask_ir_copilot / run_incident_analysis without an id target it."`
- **The staged-tool enumeration string (:218)** — "Seven tools are 'staged': send_offer, draft_discipline, build_onboarding_plan, report_incident, open_er_case, assign_training, and decide_pto_request" — is already stale (missing `draft_disciplinary_action`/`decide_disciplinary_action`). Rewrite without a count: "These tools are 'staged': send_offer, draft_discipline, draft_disciplinary_action, decide_disciplinary_action, build_onboarding_plan, report_incident, open_er_case, assign_training, decide_pto_request, and promote_ems_event." (drops the count so the next skill can't re-stale it).
- Two prose sections (after "## ER Copilot bridge", :280):
```
## EMS events
lookup_context(topic="events") lists channel-logged events with ids. Open one with
show_record("ems_event", ...). To make one a real incident, stage promote_ems_event —
confirm-first like every write. After promotion the incident is the active IR record.

## IR Copilot bridge
ask_ir_copilot answers questions about an incident and saves the exchange to the
incident's own Copilot transcript. run_incident_analysis(root_cause|recommendations)
computes and caches the analysis the IR detail page shows. Both default to the
thread's active incident (e.g. one just promoted).
```

---

## Tests

### `tests/huume/test_huume_actions.py` — extend `TestEvaluateHuumeAction`
| test | asserts |
|---|---|
| `test_ems_promote_stages_with_valid_event_id` | `this_turn_staged_new=True`, valid UUID → `kind == "stage"` |
| `test_ems_promote_confirm_proceeds` | staged dict `status="proposed"`, `this_turn_staged_new=False` → `kind == "proceed"`, `action["event_id"]` normalized, `action["occurred_at"]` is datetime when ISO string sent |
| `test_ems_promote_bad_event_id_refuses` | `event_id="not-a-uuid"` → refuse, message names lookup_context |
| `test_ems_promote_bad_occurred_at_refuses` | garbage `occurred_at` → refuse |
| `test_ems_promote_requires_ems_flag` | `features={"huume":True,"matcha_work":True}` (no `ems`) → refuse |
| `test_pilot_tools_include_ir` | `evaluate_pilot_tool(tool="ask_ir_copilot", role="client", features={... "ir_copilot": False})` → refusal naming "IR Copilot"; with flag → `None` |

### New `tests/huume/test_ems_skill.py`
Fake conn pattern from `tests/ems/test_event_intake_parsing.py` (`_FakeConn` recording fetchrow/execute); `monkeypatch.setattr` on **`ems_skill`** — the module that defines the caller, per the repo patching rule (server/CLAUDE.md).
| test | asserts |
|---|---|
| `test_refuses_when_incidents_flag_off` | features `{"ems":True,"incidents":False}` → `status=="error"`, `promote_event` never called (mock) |
| `test_refuses_wrong_role` | users row role `"employee"` → error |
| `test_refuses_already_promoted` | event row `status="promoted"` → error mentioning status (from `evaluate_promote`'s 409 reason) |
| `test_success_returns_created_with_bg_tasks` | mocked `promote_event` → `(row, [sentinel])`; result `status=="created"`, `record_id` str, `bg_tasks == [sentinel]` |
| `test_promote_race_maps_to_error` | mocked `promote_event` raises `PromoteRaceError` → `status=="error"`, no raise |
| `test_overrides_only_carry_sent_fields` | action with only `event_id` → `promote_event` called with `overrides == {}` |

### New `tests/huume/test_ir_skill.py`
| test | asserts |
|---|---|
| `test_resolve_explicit_id_wins_over_state` | both supplied → explicit used |
| `test_resolve_falls_back_to_state` | `incident_id=None`, state id → used |
| `test_resolve_neither_refuses` | error message names both options |
| `test_ask_empty_question_refuses` | `status=="error"`, no model call |
| `test_run_analysis_unknown_type_refuses` | `analysis_type="similar"` → error |
| `test_run_analysis_cache_hit_skips_analyzer` | fake conn returns cached row → `cached is True`, `get_ir_analyzer` mock not called |
| `test_run_analysis_upsert_uses_on_conflict` | recorded execute SQL contains `ON CONFLICT (incident_id, analysis_type)` |

### `tests/huume/test_huume_record_view.py`
Parity test picks up `ems_event` automatically (fails until all four dicts carry it). Add `test_ems_event_model_batch_includes_narrative` (fake conn row → entry has truncated `narrative`, `label`) and `test_ems_event_view_shape` (`record_type/link/chips/sections` present, link `/work/events/{id}`).

### Prompt/state tests (wherever `build_state_block` is tested — `tests/huume/test_huume_prompt.py` if present, else new)
- staged `ems_promote` renders its `event_id`; `huume_ir` renders `incident_number`; staged-tool enumeration string contains `promote_ems_event`.

---

## Verification

1. `cd server && ./venv/bin/python -m pytest tests/huume/ tests/ems/ -q` (py_compile hook covers syntax on each edit).
2. Live dev (Sunset Smile Dental — `ems` already on): enable `huume` (+ confirm `ir_copilot` default-True survives its stored overrides); flip/create a huume-mode thread. Scripted or browser:
   - "what events do we have?" → events lookup, narratives visible in the answer.
   - "show me the autoclave one" → `ems_event` panel via `GET /matcha-work/threads/{id}/huume/record?record_type=ems_event`.
   - "promote it" → staged frame naming event_id → next message "confirm" → `ems_events.status='promoted'`; `ir_incident_analysis` gains `categorization`/`severity`/`policy_mapping` rows (bg tasks ran).
   - "run the incident copilot — what should I do next?" → guidance; `/app/ir/{id}` Copilot tab shows both turns.
   - "run root cause" → `analysis_type='root_cause'` row; second call returns `cached: true`.
3. Negative: strip `ir_copilot` from a test company → both pilot tools refuse naming "IR Copilot"; strip `incidents` → promote refuses at confirm with `evaluate_promote`'s reason.
