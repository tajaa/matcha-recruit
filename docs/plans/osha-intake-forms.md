# OSHA 300 Log — HIPAA-safe intake, per-employee Privacy Case, AI name-cleansing

## Context

**Original bug:** patient names (Julianna, Simon) print verbatim in the OSHA 300 log's **Description** column (CSV export). Root cause was a pure-regex scrubber that only catches names with a lexical anchor ("patient John") and leaks bare names ("tending to Julianna"). Regex can't do open-vocabulary name recognition.

**Deeper finding:** the real exposure is upstream. Every IR analysis path sends raw `title`/`description` to the **consumer Gemini endpoint** (`genai.Client(api_key=…)`), which is **not BAA-eligible** — so any patient name in the narrative is an impermissible PHI disclosure on ~14 call sites, with zero pre-send de-identification.

**Prior work:** an earlier pass on the **`fix-names`** branch (commits `95ea3b7`, `bc0fbb2`, unmerged) already built the deterministic Privacy-Case core (no migrations, no new tables — all in existing `category_data` + `osha_form_301_data` JSONB; the "different tables" were really a `SafetyData` Pydantic destructure). It diverged at `f416852` and touches only IR files the werk commits never touched, so it **cherry-picks cleanly** onto `osha-intake-forms`. This plan **reuses that core** and layers the redesign on top.

## Two distinct columns (do not conflate)

- **Column B — Employee Name** → masked to the literal `"Privacy Case"` **only** for the 6 sensitive categories (29 CFR 1904.29). Hides the *employee's* identity. Trigger = **Hybrid** (below).
- **Column F — Description** → **all** human names stripped (patient / coworker / employee / anyone), on **every** recordable row, privacy case or not. This is what kills the Julianna/Simon leak. Always runs: **AI-cleanse → structured phrase fallback → placeholder**; the raw narrative never reaches the export.

## Forks locked with the user

- **Transport** → **Vertex AI + Google Cloud BAA** (makes sending names lawful). Built **gated** behind `USE_VERTEX_AI`; runs on the consumer endpoint until the user provisions GCP + signs the BAA + flips the flag.
- **Privacy scope** → **per injured employee** (co-injured non-privacy employees keep their real names).
- **Name-masking trigger (Column B)** → **Hybrid**: `determine_privacy_case()` auto-suggests the category and acts as a fail-closed safety net; the human's per-employee Copilot answer is the source of truth.
- **Bring-in** → cherry-pick the 2 `fix-names` commits, then layer the redesign.

## The 6 OSHA Privacy Case categories (29 CFR 1904.29(b)(6)-(b)(10))

1. Injury to an intimate / reproductive body part
2. Injury resulting from a sexual assault
3. Work-related mental illness
4. HIV / Hepatitis / Tuberculosis infection
5. Needlestick / cut from a contaminated sharp
6. Voluntary opt-out — **illness** case **and** the employee asked to withhold their name (human-only; AI can't infer a privacy choice)

## Bring-in (execution step 0)

`git cherry-pick 95ea3b7 bc0fbb2` onto `osha-intake-forms` (keeps the user's authorship, lands ~830 lines of the privacy core), then layer the redesign below. Staying on `osha-intake-forms` (no branch switch).

## Data model — NO migration (existing columns + `category_data` JSONB)

- **Injured employees** = `ir_incidents.involved_employee_ids` (UUID[]). One 300-log row per id. Empty → single reporter-fallback row (preserves matcha-lite no-roster behavior).
- **Per-employee privacy answer** = `category_data.privacy_cases` : `{ "<employee_id>" | "reporter": "<reason>" | "none" }`. Written by the Copilot accept handler (`"none"` = human reviewed and explicitly cleared).
- **Name-mask resolution per row** (in `_resolve_osha_privacy`):
  - human answer present & ≠ `"none"` → **mask**, reason = that answer (human authority, per-employee precise).
  - human answer = `"none"` → **don't mask** (explicit clear wins over auto).
  - unanswered → fall back to `determine_privacy_case(incident signals)` — **safety net**, masks if the 6-condition rule fires (incident-level, so may over-mask co-injured; the safe direction).
- **Cleansed description** = `category_data.osha_clean_description` (string). Written by the create-time background task.
- **Per-row case number** = derived at render: base (`osha_case_number` or `str(id)[:8]`); when >1 injured, suffix `-1`, `-2`… by array order. No new column.

## Phase 1 — PHI-safe OSHA privacy (no new egress; shippable before the BAA)

Makes the export name-safe **without relying on AI** — the compliance floor.

**`server/app/core/services/osha_privacy.py`** (from cherry-pick; keep as-is): `PRIVACY_NAME`, `PRIVACY_DESCRIPTION_PLACEHOLDER`, `PRIVACY_CASE_REASONS` (+labels), `INTIMATE_BODY_PARTS`, `INFECTIOUS_PRIVACY_AGENTS`, `_truthy`, `_is_illness`, `determine_privacy_case` (auto-suggest + safety net), `compose_clinical_description` (structured Column F fallback).

**`osha.py`:**
- `get_osha_300_log` — **rewrite the loop to one row per `involved_employee_ids` entry** via the existing `_shared._hydrate_involved_employees` (returns `first_name/last_name/job_title`); derive per-row case number; reporter-fallback row when no roster ids. Mask via `_resolve_osha_privacy` (hybrid resolution above, keyed per employee). **Column F = `osha_clean_description` → `compose_clinical_description(category_data)` → placeholder** (drop `redact_osha_text(description)`).
- `get_osha_301_form` — same per-row masking + same Column F precedence.
- `/osha/privacy-cases` (from cherry-pick) — adapt to per-employee rows; real name + reason + case number; already `require_admin_or_client`, company-scoped, `log_audit("privacy_case_names_viewed")`.
- `_aggregate_300a` — `'mental_illness'` already folded into `total_other_illnesses` by the cherry-pick.

**`models/ir_incident.py`** (from cherry-pick): `Osha300LogEntry` privacy fields + `OshaPrivacyCaseEntry` + `SafetyData` destructure — keep.

**`_shared.py`:**
- `OSHA_INJURY_TYPES`/labels/injury-type card `mental_illness` — from cherry-pick, keep.
- `extract_privacy_signals` overlay in `_auto_classify_incident_task` — from cherry-pick, **keep** (now lawful under Vertex): it populates the structured signals that feed `determine_privacy_case`'s auto-suggestion. Merge stays existing-wins so a human/Copilot answer always beats the AI.
- New `build_privacy_case_query_card(employee_name, employee_key, suggested_reason)` → `quick_reply`, choices = 6 reasons + "Not a privacy case", `quick_reply_kind="privacy_case_query"`, carrying `employee_key`; the choice matching `suggested_reason` (from `determine_privacy_case`) is pre-highlighted.

**Copilot privacy prompt** (deterministic):
- `services/ir_flow.py` + `copilot.py` OSHA chain — after recordable + injury type confirmed, enqueue one privacy card per injured employee (resolve `involved_employee_ids` → names; else reporter), each pre-filled with the auto-suggested reason.
- `copilot.py` `_handle_quick_reply` — branch `kind == "privacy_case_query"`: write `category_data.privacy_cases[key] = reason | "none"` via `jsonb_set`; chain the next employee's card.
- `services/ir_ai_orchestrator.py` — add `"privacy_case_query"` to `IR_VALID_QUICK_REPLY_KINDS`.

**Intake trim — `client/src/components/ir/IRCreateIncidentModal.tsx`:** the cherry-pick adds sensitive-case checkboxes — **remove them** (privacy is Copilot-driven now) and **remove the "Recommended next steps" field** + its `corrective_actions` POST. Keep only the 6 native fields (reporter, date/time, location, description, involved employees [roster], witnesses).

**Frontend 300-log — `OshaLogsPanel.tsx`** (mostly from cherry-pick): masked employee cell + reason badge + admin "Reveal confidential names" → `/osha/privacy-cases`. Verify against the per-employee rows. `client/src/types/ir.ts` — privacy fields.

## Phase 2 — AI description cleansing (Column F upgrade)

- `services/ir_analysis.py` — new `IRAnalyzer.cleanse_description(title, description)`; prompt replaces every human name with a role noun (Employee / a coworker / a patient / a visitor), keeps the mechanism of injury, returns one sentence, emits no names. Uses existing `_call_with_retry` + `_parse_json_response`.
- `_shared.py` `_auto_classify_incident_task` — after categorize/severity, call `cleanse_description` and store `category_data.osha_clean_description` (best-effort, same `jsonb_set` pattern as the privacy-signal overlay).
- Column F precedence (Phase 1) uses it when present; missing/failed → structured fallback (fail-closed, never raw).

## Phase 3 — Vertex AI + BAA (gated)

- **New `server/app/core/services/genai_client.py`:** `get_genai_client(api_key=None, **kwargs)` → `genai.Client(vertexai=True, project=…, location=…)` when `settings.use_vertex_ai` else `genai.Client(api_key=…)`. SDK is `google-genai` (supports `vertexai=True`).
- **`config.py`:** `use_vertex_ai` (`USE_VERTEX_AI`, default `False`), `vertex_ai_project` (`VERTEX_AI_PROJECT`), `vertex_ai_location` (`VERTEX_AI_LOCATION`).
- **Flip the IR PHI path:** `ir_analysis.py` (`get_ir_analyzer`) → factory; migrate `osha_ai_determination` off the legacy `google.generativeai` SDK to the factory so it's Vertex-capable + consistent.
- **Out-of-code prerequisites (USER):** GCP project, signed Google Cloud BAA, set the 3 env vars, then `USE_VERTEX_AI=true`. Until then AI runs on the consumer endpoint — Column F stays name-safe via the structured fallback regardless.
- **Follow-up sweep (separate):** flip the remaining ~37 `genai.Client(...)` sites to the factory for a complete HIPAA posture (mechanical).

## Critical files

- `server/app/core/services/osha_privacy.py` *(cherry-pick — keep)*, `server/app/core/services/genai_client.py` *(new)*
- `server/app/matcha/routes/ir_incidents/osha.py` *(per-injured rows, hybrid masking, Column F, confidential endpoint, determine→factory)*
- `server/app/matcha/routes/ir_incidents/_shared.py` *(privacy card builder, keep extract overlay, cleansing store)*
- `server/app/matcha/routes/ir_incidents/copilot.py` + `services/ir_flow.py` + `services/ir_ai_orchestrator.py` *(privacy prompt chain + accept branch)*
- `server/app/matcha/services/ir_analysis.py` *(cleanse_description + factory client)*
- `server/app/matcha/models/ir_incident.py` *(cherry-pick — keep)*, `server/app/config.py` *(Vertex settings)*
- `client/src/components/ir/IRCreateIncidentModal.tsx` *(trim)*, `client/src/components/ir/OshaLogsPanel.tsx`, `client/src/types/ir.ts`
- `server/tests/ir_incidents/test_osha_privacy_case.py` *(cherry-pick — extend for hybrid resolution + per-employee)*

## Verification

- Unit: `cd server && ./venv/bin/python -m pytest tests/ir_incidents/ -q` (composer, `determine_privacy_case` conditions, hybrid resolution, per-employee). `cd client && npx tsc --noEmit`.
- Live (dev tunnel, RFC 2606 data only): recordable incident with 2 roster employees → Copilot per-employee privacy prompt (one privacy, one not) → `GET /osha/300-log?year=` shows two rows, distinct case numbers, one masked `"Privacy Case"` + reason, the other real name, both Column F name-free; **CSV** confirms no patient/coworker names; `/osha/privacy-cases?year=` resolves the real name + writes an audit row; a single broken-leg incident → real name, name-free Column F, absent from privacy-cases; an unanswered sensitive case (e.g. `infectious_agent=hiv` extracted) → still masked by the safety net.

## Notes / risks

- **Phase 1 alone kills the leak** (Column F never raw; names masked) with no new egress — ship before the BAA.
- AI cleansing + existing IR analysis only become HIPAA-lawful at the Vertex flip; the structured fallback is the floor until then.
- Hybrid safety net is incident-level → may over-mask co-injured rows when unanswered (safe direction; human per-employee answer corrects it).
- `osha_ai_determination`'s legacy SDK must move to the new SDK for Vertex.
- Re-read each file after the cherry-pick before editing — resolve any conflict against `osha-intake-forms`.
