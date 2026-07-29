# Plan: discovery-first entry + general intent routing for Huume

## Context

Huume skill #6 (incident→discipline, PR #94, now merged to main) works, but its conversational
entry requires the admin to already know the incident id. The natural opening — "which IRs
require disciplinary action?" — is unanswerable today, and the failure generalizes:

- `lookup_context(topic='incidents')` deliberately withholds descriptions (legal record), so the
  model can't triage from a lookup.
- `check_incident_policy` is one-incident-per-call, 60s Gemini each; tool calls run **serially**
  (`agent.py` tool loop) against `_MAX_MODEL_CALLS=8` / `_WALL_CLOCK_SECONDS=240.0` — a
  10-incident scan force-finishes after 3–4 and the model reports partial work as the answer.
- Huume runs flat `gemini-3.6-flash`, **no ThinkingConfig, no intent recognition** (`agent.py:54`,
  config at `:941`): "yes, confirm" and "I have this ER situation, what should I do?" get
  identical model effort.

Repo precedents to reuse (not reinvent):
- **Merlin routing** `app/cappe/services/merlin/routing.py` — heuristic-first tier resolution,
  `MODEL_TIERS` catalog (`catalog.py:233`), "failure routes UP, not down".
- **matcha_work_ai** — `classify_thinking_level` (`_models.py:90`), ThinkingConfig wiring
  (`provider.py:415-419`: `"none"` → `thinking_budget=0`, else `thinking_level=`).
- **legal_skill/handbook_skill** — pilot-bridge pattern: `actions.evaluate_pilot_tool`
  (`actions.py:568`) + `PILOT_TOOL_REQUIRED_FEATURE`, citations accumulated via
  `_collect_citations` (`agent.py:400`) into `huume_result.citations`.

Decisions already made by the user: all four parts in one pass; deep tier = **flash + high
thinking** (not pro-preview — one-line catalog edit later if wanted); **new branch off main**.

## Branch / PR

PR #94 merged. `git checkout main && git pull` (verify `cc3ea06`/`18ff081` present), then
`git checkout -b matcha/huume-intent-routing` (user approved). New PR to main at the end.

---

## Part A — `find_discipline_candidates`

### A1. Batch check in `services/discipline/discipline_policy_check.py`

Corpus is per-company; today rebuilt per incident. Refactor (no behavior change to the single
path):

```python
async def _build_check_corpus(conn, company_id: UUID) -> Optional[dict[str, Any]]:
    # body = current lines 139-146 (gather_grounding + build_corpus(with_full_text=True));
    # returns None on exception (logged), corpus dict otherwise.

async def _check_one(corpus: dict[str, Any], incident: dict[str, Any]) -> dict[str, Any]:
    # body = current lines 148-208: empty-index early return, Gemini call w/ 60s wait_for,
    # _parse_json, _resolve_cid repair, validate_citations, _clean_title shaping.
    # NO conn. Never raises (returns _unavailable_result()).

async def check_incident_against_handbook(conn, *, company_id, incident) -> dict[str, Any]:
    corpus = await _build_check_corpus(conn, company_id)
    if corpus is None:
        return _unavailable_result()
    return await _check_one(corpus, incident)   # signature + return shape unchanged

async def check_incidents_against_handbook(
    conn, *, company_id: UUID, incidents: list[dict[str, Any]], concurrency: int = 3,
) -> dict[str, dict[str, Any]]:
    """Batch: corpus built ONCE; _check_one under asyncio.Semaphore(concurrency) via
    gather (no conn use inside); then persist_policy_check sequentially on the caller's
    single conn, only for available results. Corpus failure -> every incident maps to
    _unavailable_result(). Returns {str(incident['id']): result}."""
```

### A2. Skill fn `discipline_skill.find_candidates`

```python
_FRESH_CHECK_CAP = 6          # max fresh Gemini checks per call
_BATCH_BUDGET_SECONDS = 100   # asyncio.wait_for around the batch; leftovers -> not_yet_checked
_RELEVANCE_RANK = {"violated": 2, "bent": 1, "related": 0}

def _rank_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure. rows = [{incident fields..., 'matches': [...]}]. Drops zero-match rows,
    sorts by (max relevance rank, max confidence) desc. Unit-tested DB-free."""

async def find_candidates(
    *, company_id: UUID, days: int = 30, limit: int = 5, recheck: bool = False,
) -> dict[str, Any]:
```

Flow (clamps: `days = min(max(days,1),180)`, `limit = min(max(limit,1),10)`):

1. `connection_or_direct(force_direct=True)` — holds conn across Gemini calls (same comment/
   reason as `check_incident_policy`).
2. Feature gate, verbatim idiom from `check_incident_policy` lines 74-94: `discipline` off →
   `{"status": "module_off", ...}`; `handbooks` off → module_off with the "no corpus ≠ clean"
   wording.
3. One query:
   ```sql
   SELECT i.id, i.incident_number, i.severity, i.incident_type, i.occurred_at,
          i.title, i.description,                       -- for the fresh check only, never returned
          a.analysis_data,                              -- stored policy_mapping row or NULL
          EXISTS (SELECT 1 FROM progressive_discipline pd
                  WHERE pd.source_incident_id = i.id) AS already_disciplined
   FROM ir_incidents i
   LEFT JOIN ir_incident_analysis a
          ON a.incident_id = i.id AND a.analysis_type = 'policy_mapping'
   WHERE i.company_id = $1 AND i.status = 'closed'
     AND i.updated_at > NOW() - ($2 || ' days')::interval
   ORDER BY i.updated_at DESC
   ```
4. Partition: **cached** = `analysis_data.checked_by == 'discipline_policy_check'` and not
   `recheck` → matches read from the stored row, zero Gemini. **fresh** = the rest, first
   `_FRESH_CHECK_CAP` only; run through `check_incidents_against_handbook` wrapped in
   `asyncio.wait_for(_BATCH_BUDGET_SECONDS)` (TimeoutError → those become not-yet-checked too).
   Remainder + `available=False` results → `not_yet_checked`.
5. Build result:
   ```python
   {
     "status": "ok",
     "candidates": [                      # ranked, top `limit`
       {"incident_id", "incident_number", "occurred_at",  # ISO date
        "severity", "policy_titles": [...], "top_relevance", "top_confidence",
        "already_disciplined": bool},
     ],
     "checked": int, "cached": int,
     "not_yet_checked": {"count": int, "incident_numbers": [...]},
     "clean_count": int,                  # checked incidents with zero matches
   }
   ```
   Name-free by construction: description/title/involved ids never copied into the payload.

### A3. Tool decl + dispatch

`tools.py`: new `_tool("find_discipline_candidates", "read", ..., properties={days:int,
limit:int, recheck:bool})`, `required=[]`, `discovery=True`, `intent_hints=("which incidents",
"need discipline", "disciplinary action", "broke policy", "policy violations", "require a
write-up")`. Description: names nobody; use `show_record` to see people; `not_yet_checked` must
be relayed.

`agent.py`: dispatch branch beside `check_incident_policy` (`:507`):
```python
if name == "find_discipline_candidates":
    result = await discipline_skill.find_candidates(
        company_id=company_id,
        days=int(args.get("days") or 30), limit=int(args.get("limit") or 5),
        recheck=bool(args.get("recheck")),
    )
    n = len(result.get("candidates") or [])
    step = recorder.record(tool=name, kind="read",
        label=f"Scanned closed incidents — {n} with possible policy matches"
              if result.get("status") == "ok" else "Could not scan incidents",
        status="ok" if result.get("status") == "ok" else "error", detail=result.get("message"))
    return _json_safe(result), step
```
(int() coercion in try/except like the other branches; bad args → error result, not raise.)

---

## Part B — intent routing (`services/huume/routing.py`, new)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class HuumeTier:
    planner_model: str            # first model call of the turn
    planner_thinking: Optional[str]   # None = omit ThinkingConfig (today's behavior)
    executor_model: str           # calls 2..N
    executor_thinking: Optional[str]

_FLASH = "gemini-3.6-flash"       # single source; agent._MODEL is replaced by the catalog
TIERS: dict[str, HuumeTier] = {
    "lite":     HuumeTier(_FLASH, "none", _FLASH, "none"),   # thinking_budget=0
    "standard": HuumeTier(_FLASH, None,   _FLASH, None),
    "deep":     HuumeTier(_FLASH, "high", _FLASH, "low"),
}
FALLBACK_TIER = "standard"        # Merlin rule: unsure/failure routes to the middle, never lite

_CONFIRM_RE   = re.compile(r"^(yes|yep|yeah|ok(ay)?|confirm(ed)?|go ahead|do it|send it|approve[d]?|proceed|sounds good)\b", re.I)
_ANALYTICAL_RE = re.compile(r"\b(which|why|analy[sz]e|compare|recommend|assess|risk|what should|"
                            r"how (do|should) (i|we)|what('s| is) (the best|going on)|help me (figure|decide|handle))\b", re.I)
_NARRATIVE_CHARS = 280            # matcha_work_ai's own long-message threshold
_NARRATIVE_NEWLINES = 2

def has_pending_confirmable(current_state: dict[str, Any]) -> bool:
    """True when a staged action or an approvable/executable plan is waiting —
    i.e. a short 'yes' is a real confirm turn, not an empty message."""
    action = current_state.get("huume_action")
    if isinstance(action, dict) and action.get("status") == "staged":
        return True
    for plan in (current_state.get("huume_plans") or {}).values():
        if isinstance(plan, dict) and plan.get("status") in ("proposed", "approved"):
            return True
    return False
    # NOTE at impl: verify plan-level status vocabulary against store.py/actions.py
    # (proposed/approved/executing/done) before pinning these two.

def resolve_tier(message: str, *, current_state: dict[str, Any],
                 hint_index: tuple[tuple[str, str], ...]) -> str:
    """Pure, never raises (internally guarded -> FALLBACK_TIER). Order load-bearing:
    1. short (<= 8 words) confirm-shaped message AND has_pending_confirmable -> "lite"
    2. any registered intent hint substring match (lowercased) -> "deep"
    3. _ANALYTICAL_RE or len > _NARRATIVE_CHARS or newlines > _NARRATIVE_NEWLINES -> "deep"
    4. else FALLBACK_TIER
    hint_index: ((hint_phrase, tool_name), ...) — from build_hint_index(TOOLS)."""

def build_hint_index(tools: Iterable[HuumeTool]) -> tuple[tuple[str, str], ...]:
    """((lowercased hint, tool.name), ...) — module-level constant, built once."""

def thinking_config(level: Optional[str]) -> Optional[types.ThinkingConfig]:
    """provider.py:415-418 mapping: None -> None; "none" -> ThinkingConfig(thinking_budget=0);
    else ThinkingConfig(thinking_level=level)."""
```

### agent.py wiring

- Delete `_MODEL` constant (`:54`); import `routing`.
- After history/state setup, before the loop:
  ```python
  tier_name = routing.resolve_tier(_last_user_text(history), current_state=current_state,
                                   hint_index=routing.HINT_INDEX)
  tier = routing.TIERS[tier_name]
  ```
  `_last_user_text(history)`: last `role == "user"` entry's content, `""` if none (tiny helper
  next to `_to_contents`).
- Build the shared `GenerateContentConfig` kwargs once (tools + system_instruction, `:941-948`);
  two configs differing only in `thinking_config`:
  ```python
  planner_config, executor_config = _tier_configs(tier, base_kwargs)
  ```
- In the loop: `is_first = model_calls == 0` **before** the increment;
  `model = tier.planner_model if is_first else tier.executor_model`; config likewise (`:963`).
- Usage/audit: `total_usage["model"]` (`:1081`) becomes
  `total_usage["model"] = tier.planner_model; total_usage["tier"] = tier_name` — rides the
  existing `huume_runs.token_usage` JSONB via `store.complete_run` (**no migration**). Also
  `yield {"type": "status", "message": "Thinking hard…"}` only when tier == deep (visible signal,
  cheap).
- Rate limiter untouched (`check_limit("huume", "agent")` counts calls, not thinking).

---

## Part C — registry-driven discovery

### tools.py

```python
@dataclass(frozen=True)
class HuumeTool:
    name: str
    kind: str
    declaration: types.FunctionDeclaration
    discovery: bool = False               # batch "which X need attention" entry point
    intent_hints: tuple[str, ...] = ()    # lowercase phrases meaning "user wants THIS tool"
```
`_tool(...)` gains passthrough kwargs `discovery=False, intent_hints=()`.

Hints added to existing tools in the same pass (not just the new ones):
- `find_discipline_candidates` — Part A list, `discovery=True`
- `list_pending_approvals` — `("pending approvals", "awaiting approval")`, `discovery=True`
  (it already IS a queue-discovery tool; gets the prompt block for free)
- `ask_er_copilot` / `er_case_brief` — Part D list

### prompt.py

```python
def build_discovery_block(tools: Iterable[HuumeTool]) -> str:
    """One '## Broad questions' section: a line per discovery=True tool —
    '- Questions like <hints, quoted> -> call <name> FIRST, then show_record, then act.'
    Plus two standing rules: discovery results name nobody (show_record for people);
    a nonzero not_yet_checked means a BOUNDED scan — report it, never imply completeness.
    Returns "" when no discovery tools exist (block absent, not empty-headed)."""
```
`build_system_prompt` calls it (module-level constant is fine — TOOLS is static) and the
hand-written "which incidents" phrasing stays OUT of per-skill sections (skill sections keep
only their tool semantics; discovery routing lives in the generated block).

### routing.py

`HINT_INDEX = build_hint_index(TOOLS)` — the router consumes the same declarations. Net effect:
**a future skill declares one tool with `discovery=True, intent_hints=(...)` and gets prompt
teaching + deep-tier routing with zero harness edits.**

---

## Part D — ER bridge (`services/huume/er_skill.py`, new)

"I have this employee relations issue…" → deep tier (hints) → grounded on ER Copilot's own data.
Mirrors `legal_skill.py`; same envelope, same citation flow.

### D1. Service lift (routes must not be imported by services)

The context builders live in `routes/er_copilot/_shared.py` today. Lift to a new
`services/er/er_case_context.py` (CLAUDE.md's own precedent: "shared-service lifts that shipped
with this — routes now delegate"):

```python
# moved bodies, signatures unchanged; routes/_shared.py re-imports and delegates:
async def load_guidance_context(conn, case_id: UUID, case_row) -> dict[str, Any]   # was _load_guidance_context
def build_document_excerpts(rows, *, text_key: str) -> str                          # was _build_document_excerpts
def build_er_analyzer(model_override: Optional[str] = None) -> ERAnalyzer           # was _build_er_analyzer
```
`routes/er_copilot/_shared.py` keeps the old underscore names as aliases (tests import
`_build_document_excerpts` from the package — re-export contract in its CLAUDE.md).

### D2. Tools

```python
# er_skill.py
async def case_brief(*, company_id: UUID, case_id: str) -> dict[str, Any]:
    """Read, no Gemini. UUID-parse guard -> error; case fetched WHERE id=$1 AND company_id=$2
    (tenant rule — no _verify_case_company import, same inline pattern as
    discipline_skill.check_incident_policy). Returns name-free:
    {status, case_id, case_number, title, status, category, created_at,
     involved_count,                       # never names/ids of people
     documents: [{id, filename, document_type}],   # titles OK — they're files, not people
     analyses: {timeline|discrepancies|policy_check|similar_cases|retaliation_risk:
                {generated_at, headline}},  # headline = 1-line summary lifted from analysis_data
     notes_count, open_days}
    Reads er_cases + er_case_documents + er_case_analysis (analysis_type per row).
    Three-state: er_copilot flag off is handled by evaluate_pilot_tool in agent.py."""

async def ask_case(*, company_id: UUID, actor_user_id: Optional[UUID],
                   case_id: Optional[str], state_case_id: Optional[str],
                   question: str) -> dict[str, Any]:
    """The deep tool — one grounded Gemini call. Shape mirrors legal_skill.ask_matter:
    1. resolve case: explicit case_id, else state_case_id, else error naming both options.
    2. under get_connection(): fetch case row (tenant-scoped), load_guidance_context(...),
       build_document_excerpts(all_doc_text_rows, text_key='scrubbed_text'),
       er_compliance_grounding.build_jurisdiction_corpus(conn, company_id, involved_ids)
         -> (law_text, law_index, truncated).
    3. RELEASE the connection (ask_matter's own comment: never hold conn across Gemini).
    4. corpus index for the citation gate:
         {'ercase:doc-<id>': {...} for docs} | {'ercase:analysis-<type>': {...}} | law_index
       Prompt renders each with [cid]; answer JSON = {"answer": str,
       "evidence": [{"point": str, "cited_ids": [...]}]} -> shared validate_citations ->
       er_compliance_grounding.build_citation_records for the surviving records.
    5. Model: build_er_analyzer()._generate_content_async(prompt) with a new module-level
       _ASK_PROMPT (er_skill.py owns it — ERAnalyzer gains no method; it's a huume-side
       composition, same as discipline_policy_check owns _CHECK_RULES).
    6. Return {status: 'ok', case_id, case_number, answer, citations: [records w/ 'cid'],
       dropped_citations: [...], truncated_grounding: bool}. Never raises -> degraded
       {'status':'error', message} on Gemini failure (legal_skill idiom)."""
```

### D3. Registry + agent wiring

- `actions.py`: `PILOT_TOOL_REQUIRED_FEATURE |= {"er_case_brief": "er_copilot",
  "ask_er_copilot": "er_copilot"}`; `_PILOT_FEATURE_LABEL["er_copilot"] = "ER Copilot"`.
  `evaluate_pilot_tool` itself: **zero changes**.
- `tools.py`: two `_tool` entries. `ask_er_copilot` gets
  `intent_hints=("employee relations", "er case", "er issue", "complaint about", "grievance",
  "investigation")` (not discovery — takes/resolves a case). `er_case_brief` plain read.
  Descriptions: brief first, then ask; propose `open_er_case` (existing staged action) only
  when no case exists and the admin wants one.
- `agent.py`: two branches in the pilot-tools section (beside `ask_legal_pilot`, `:797`):
  gate via `actions.evaluate_pilot_tool(tool=name, role=user_role, features=features)` →
  refusal step on non-None; on `ask_er_copilot` success: `_collect_citations(result)` and
  `state_updates["huume_er"] = {"case_id": result["case_id"], "case_number": ...}`.
- `prompt.py` `build_state_block`: render `huume_er` ("Active ER case: <number>") exactly as
  `huume_legal` renders its matter — so later turns say "the case" and resolve.
- `state_case_id` plumbed like `_state_legal()` (`agent.py:392`): a `_state_er()` closure.
- No new REST routes, no frontend change (citations render via existing `CitationSources`;
  `show_record("er_case", ...)` already exists for the named view).

### Deferred (named, not silently dropped)
`find_er_attention` discovery tool (stale/overdue/high-retaliation-risk queue) — Part A's shape
makes it mechanical; separate PR.

---

## Files

| Part | Files |
|---|---|
| A | `services/discipline/discipline_policy_check.py`, `services/huume/discipline_skill.py`, `services/huume/tools.py`, `services/huume/agent.py` |
| B | `services/huume/routing.py` (new), `services/huume/agent.py` |
| C | `services/huume/tools.py`, `services/huume/prompt.py`, `services/huume/routing.py` |
| D | `services/huume/er_skill.py` (new), `services/er/er_case_context.py` (new, lifted), `routes/er_copilot/_shared.py` (delegate), `services/huume/actions.py`, `services/huume/tools.py`, `services/huume/prompt.py`, `services/huume/agent.py` |
| docs | root `CLAUDE.md` huume row: discovery registry + tiering + ER bridge (one sentence each) |

No migration (`tier` rides `huume_runs.token_usage` JSONB; `huume_er` rides
`mw_threads.current_state`). No frontend change.

## Tests

`tests/discipline/test_discipline_policy_check.py` (extend):
- `test_batch_builds_corpus_once` — spy `_build_check_corpus` (or `build_corpus`), 3 incidents,
  1 call.
- `test_batch_one_gemini_failure_degrades_only_that_incident` — side_effect [ok, raise, ok] →
  middle incident `available=False`, others intact.
- `test_batch_corpus_failure_degrades_all` — corpus None → all `_unavailable_result()`.
- `test_single_incident_path_unchanged` — existing suite already pins this; add one assert that
  `check_incident_against_handbook` still returns the exact legacy key set.

`tests/huume/test_huume_discipline_skill.py` (extend, existing `_FakeConn` harness):
- `test_find_candidates_module_off_discipline` / `_handbooks` — three-state wording.
- `test_find_candidates_cached_rows_skip_gemini` — stored `checked_by='discipline_policy_check'`
  rows; batch fn spy asserts not called.
- `test_find_candidates_recheck_forces_fresh`.
- `test_find_candidates_over_cap_reports_not_yet_checked` — 8 unchecked, cap 6 → count 2 +
  incident numbers present; never in `clean_count`.
- `test_find_candidates_ranking` — violated@0.6 outranks related@0.9; pure `_rank_candidates`
  cases too (empty, all-clean, tie on relevance broken by confidence).
- `test_find_candidates_payload_is_name_free` — walk the returned dict (json.dumps) and assert
  no `description`, `involved_employee_ids`, or seeded employee name substring.
- `test_find_candidates_already_disciplined_flagged_not_suppressed`.

`tests/huume/test_huume_routing.py` (new, pure — no DB, no model):
- confirm-shaped + staged action → `lite`; confirm-shaped + NO pending → not lite.
- each hint phrase → `deep`; analytical regex → `deep`; 300-char narrative → `deep`;
  3-newline message → `deep`.
- plain short ask ("what's maria's start date") → `standard`; empty/None → `standard`.
- `resolve_tier` with a poisoned `current_state` (non-dict values) → `FALLBACK_TIER`, no raise.
- `build_hint_index` lowercases; every `discovery=True` tool contributes ≥1 hint.
- `thinking_config(None) is None`; `"none"` → budget 0; `"high"` → level high.
- **agent wiring**: fake genai client recording (model, config) per call — deep turn: call 1
  thinking high, call 2 thinking low; standard turn: both configs have `thinking_config=None`;
  tier lands in `token_usage["tier"]` of the `huume_result` frame.

`tests/huume/test_huume_er_skill.py` (new):
- `test_er_tools_registered` — both names in `PILOT_TOOL_REQUIRED_FEATURE` → `"er_copilot"`,
  both in `TOOLS_BY_NAME`.
- `test_gate_refuses_without_flag` — `evaluate_pilot_tool(tool="ask_er_copilot", role="client",
  features={"huume":1,"matcha_work":1})` → refusal string naming er_copilot.
- `test_case_brief_is_name_free` — seeded involved employees; payload json has counts only.
- `test_case_brief_tenant_scoped` — other-company case_id → not_found.
- `test_ask_case_resolves_state_case_id` — no explicit id + state id → used; neither → error.
- `test_ask_case_citation_gate` — fake model answer citing one real + one invented cid →
  invented in `dropped_citations`, only real record in `citations`.
- `test_ask_case_gemini_failure_degrades` — `{'status':'error'}`, no raise.
- `test_prompt_discovery_block` (in test_huume_routing or prompt tests): every `discovery=True`
  tool named in `build_discovery_block(TOOLS)`; block present in `build_system_prompt` output;
  `state_block` renders `huume_er`.

## Verification

```bash
cd server && ./venv/bin/python -m pytest tests/discipline/ tests/huume/ tests/workers/ tests/er_copilot/ -q
# baseline 4904 passed / 66 pre-existing failures on main — compare counts, don't just read green
cd client && npx tsc -p tsconfig.app.json --noEmit    # should be a no-op pass (no FE changes)
```

E2E on dev (Sunset Smile Dental — 3 active policies, closed `IR-2026-07-DENT1`, letter template):
1. `which incidents need disciplinary action?` → one `find_discipline_candidates` call;
   `token_usage.tier == "deep"` on the `huume_runs` row; incident ranked with sharps/PPE policy
   titles; reply names nobody.
2. Re-ask → `cached` count 1, no fresh Gemini. Seed a 2nd closed incident, ask with `limit`
   forced low via phrasing → `not_yet_checked` relayed in the reply.
3. Stage a draft (`draft a written warning for Maria Chen from that incident`) → next turn
   `yes, confirm` → run row shows `tier == "lite"`.
4. `I have an ER situation — a hygienist says a coworker keeps undermining her in front of
   patients. what should I do?` → `tier == "deep"`; if a case exists: `er_case_brief` +
   `ask_er_copilot` with rendered citations; else grounded advice + `open_er_case` proposal.
