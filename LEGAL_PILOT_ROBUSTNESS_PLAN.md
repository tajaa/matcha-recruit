# Legal Pilot Robustness — Implementation-Grade Technical Plan (v2)

Jurisdiction grounding, richer compliance evidence, and external legal research (CourtListener + grounded Gemini) for Legal Pilot (`legal_defense` flag, `/app/legal-pilot`).

**Status: implemented + review-hardened** (server, routes, frontend, tests all landed; migration `legaldef02` not yet applied to dev/prod — run `./scripts/migrate-dev.sh` then `./scripts/migrate-prod.sh` when ready). One deviation from the plan below, found during implementation: asyncpg has no jsonb codec registered on this pool, so `legal_matter_research.cases`/`.guidance` come back as raw JSON text, not parsed objects — every reader (`legal_research.run_research`, the two research routes, `legal_defense._gather_case_law`) explicitly `json.loads`s them. `legal_research.parse_research_row()` centralizes this for the route layer.

**Post-review hardening (multi-agent review, 2026-07-04)** — deviations from the plan text below, all in code:
- RAG path passes `statuses=["active"]` (new optional param on `ComplianceRAGService.search_requirements`) — repealed/superseded requirements were retrievable via embeddings and could read as current law in the packet.
- `run_research` no longer takes a `conn`: it acquires its own short-lived connections around the DB phases so no pooled connection (max_size=10) is held across the ~110s of external CourtListener + Gemini calls. The route loads the matter (404 **before** consuming the 10/hr rate budget), releases, calls `run_research`, then audits on a fresh conn.
- `deploy/nginx/matcha.conf` gained a `/api/legal-pilot/matters/.../research` carve-out at 180s — the generic `/api/` block's 90s `proxy_read_timeout` would 504 the worst-case run.
- Jurisdiction precedence unified: the **location governs when set** (chain AND state), in both `resolve_matter_jurisdiction` and `legal_research._resolve_state` (which is also company-scoped now) — previously the chain came from the location while the CourtListener query used the state override.
- `legal_matter_research.jurisdiction_state` column added (migration amended pre-apply): each run records the state it was grounded in; `_gather_case_law` and the packet's `include_research` fetch skip runs whose state no longer matches the matter's current jurisdiction.
- `_research_html` renders a "Partial run" banner from `research.error` — an empty cases table was indistinguishable from a genuine zero-result search.
- `_memo_html` renders "(no longer in evidence scope at generation time)" for cited ids absent from the packet-time re-gather instead of silently-blank index cells.
- `_dt_date` normalizes law/bill dates (RAG pre-isoformats to str, SQL returns date objects — same date rendered two ways).
- Module-level `assert` on `_MATTER_TYPE_CATEGORIES` removed (whole-app boot blast radius on a registry rename); the invariant lives in `test_matter_type_categories_are_registry_keys`.
- Law/legislation lookup cached per (matter, jurisdiction, type, allegation) with a 300s TTL — it costs a Gemini embedding round-trip and ran on every chat turn inside the held connection.
- Frontend: `openMatter`/`handleRunResearch` guard awaited setState with an active-matter ref (rapid matter switches could render the wrong matter's data); `LegalContextPanel` renders an "interrupted run" note for orphaned `running` rows; `_src_compliance_alerts` gained `LIMIT 100`; the duplicated jurisdiction-state input, duplicated `_upper_state` validator (now a mixin with `check_fields=False`), and duplicated `_gather_law` SQL were deduped.

This v2 replaces the v1 plan already on PR #12: all open items from v1 are now resolved (category slugs pinned to the canonical registry, CourtListener v4 fields verified against official docs, exact code insertion points read from source). On approval: rewrite `LEGAL_PILOT_ROBUSTNESS_PLAN.md` at repo root with this content and push to `claude/legal-pilot-robustness-grkay3` (updates PR #12).

## Context

Legal Pilot grounds its AI in 7 internal evidence sources, but matters carry no jurisdiction, the compliance source is a thin slice, and there is no external legal context. The platform already holds `jurisdiction_requirements` (statute citations/penalties/source URLs), `jurisdiction_legislation`, hierarchy in `jurisdictions.parent_id`, and pgvector RAG (`ComplianceRAGService`).

**Anti-hallucination invariant:** `validate_citations` (`legal_defense.py:371`) is pure index-membership. Every new record kind mints cids only from DB rows or persisted CourtListener API rows — never from model text. Gemini guidance never mints cids.

Out of scope (user deselected): `ir_precedent`/`er_precedent` wiring.

---

## Phase 1 — Migration

**New** `server/alembic/versions/legaldef02_matter_jurisdiction_research.py` — `revision="legaldef02"`, `down_revision="mwtaskhtxt01"` (verified: `legaldef01 → lossratio01 → mlpricing01..04 → tellus_app_01..03 → irinforeq01 → brokersubnote01 → irinforesp01 → posterbrand01 → mwtaskhtxt01` is a leaf). Copy the multi-leaf caveat docstring style from `lossratio01`. All DDL via `op.execute` with `IF NOT EXISTS`:

```sql
ALTER TABLE legal_matters ADD COLUMN IF NOT EXISTS location_id UUID
    REFERENCES business_locations(id) ON DELETE SET NULL;
ALTER TABLE legal_matters ADD COLUMN IF NOT EXISTS jurisdiction_state VARCHAR(2);

CREATE TABLE IF NOT EXISTS legal_matter_research (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id     UUID NOT NULL REFERENCES legal_matters(id) ON DELETE CASCADE,
    company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    status        VARCHAR(16) NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','complete','failed')),
    query         TEXT,
    cases         JSONB,   -- CourtListener API rows ONLY; mint case:<cluster_id> cids
    guidance      JSONB,   -- grounded-Gemini synthesis; informational, never citable
    error         TEXT,
    created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_legal_matter_research_matter
    ON legal_matter_research(matter_id, created_at DESC);
```

Downgrade: drop table + both columns. Runtime jurisdiction resolution order: location's `jurisdiction_id` → state-level jurisdiction (`WHERE state=$1 AND level='state' AND country_code='US'`, exact pattern at `core/routes/resources.py:1384`) → none (all new sources silently absent).

## Phase 2 — Config

`server/app/config.py`: `courtlistener_api_token: Optional[str] = None` near `openstates_api_key` (~line 171); `courtlistener_api_token=os.getenv("COURTLISTENER_API_TOKEN")` in `load_settings()` (~line 337). Optional — anonymous CourtListener works at lower rate limits.

## Phase 3 — New service `server/app/matcha/services/legal_research.py`

Module docstring: informational research, never legal advice; only API-verified cases become citable. Uses `httpx.AsyncClient` (repo convention, `services/property_cat.py`; already pinned).

```python
COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v4"
_CL_TIMEOUT = 20.0
_MAX_CASES = 8
```

**`_parse_search_results(payload: dict, limit: int = _MAX_CASES) -> list[dict]`** — pure, never raises. v4 `type=o` result fields (verified against CourtListener REST docs): `caseName`, `caseNameFull`, `absolute_url`, `cluster_id`, `citation` (array of strings), `citeCount`, `dateFiled`, `court` (display name), `court_id`, `docketNumber`, and a nested `opinions` array (per-opinion `snippet` lives there in v4). Map each result to:

```python
{
    "id": str(r.get("cluster_id") or r.get("id") or ""),
    "case_name": r.get("caseName") or r.get("caseNameFull") or "",
    "citation": (r.get("citation") or [None])[0],          # first citation string or None
    "court": r.get("court") or "",
    "date_filed": r.get("dateFiled"),
    "url": "https://www.courtlistener.com" + (r.get("absolute_url") or ""),
    "snippet": r.get("snippet")
               or ((r.get("opinions") or [{}])[0].get("snippet") if r.get("opinions") else None),
}
```
Skip entries with empty `id` or `case_name`. **One live smoke call at implementation time** (this sandbox's proxy blocks courtlistener.com): `curl "https://www.courtlistener.com/api/rest/v4/search/?q=test&type=o" | python3 -m json.tool | head -80` from the dev machine; pin the real response as the test fixture.

**`search_case_law(query, state=None, limit=_MAX_CASES)`** — GET `{COURTLISTENER_BASE}/search/`, `params={"q": q, "type": "o", "order_by": "score desc"}`; when `state`, append the state's full name to `q` (map via a small `_STATE_NAMES` dict; no court-slug filtering in v1). Header `Authorization: Token {settings.courtlistener_api_token}` when configured. `resp.raise_for_status()` → `_parse_search_results(resp.json(), limit)`.

**`synthesize_guidance(matter: dict, juris_display: str | None, cases: list[dict]) -> dict`** — grounded Gemini (own helper; the compliance singleton's retry machinery is prompt-specific):

```python
from google.genai import types
resp = await asyncio.wait_for(
    get_genai_client().aio.models.generate_content(
        model=ld.MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    ),
    timeout=90,
)
data = ld._parse_json(getattr(resp, "text", "") or "")
```
Rate-limit around the call: `get_rate_limiter().check_limit("gemini_compliance", "legal_research")` + `record_call(...)` (reuses the existing bucket; see `gemini_compliance.py:579-612` for the pattern). Prompt (verbatim skeleton):

> You are compiling an INFORMATIONAL briefing of the public legal landscape for outside counsel. Matter type: {label}. Jurisdiction: {juris_display or "unspecified"}. Allegation summary: {first 300 chars}. Cases already located (do not re-verify): {case names}. Using web search, summarize current federal and state agency guidance relevant to this matter type (EEOC enforcement guidance, DOL opinion letters, state agency rules), each with its source URL. Do NOT give legal advice, do NOT assess the company's position, do NOT invent case citations. Return STRICT JSON: {"summary": "<neutral 2-4 paragraph overview>", "key_authorities": [{"name","url","publisher","relevance"}]}

Return `{"summary": str, "key_authorities": [...]}`; tolerate empty.

**`run_research(conn, matter: dict, created_by) -> dict`** — orchestration:
1. `INSERT INTO legal_matter_research (matter_id, company_id, query, created_by) VALUES ($1,$2,$3,$4) RETURNING id, created_at` (status defaults `running`); `query` = `_hum(matter_type)` + first 300 chars of allegation.
2. `cases`, `case_err` = try `search_case_law(query, state=matter.get("jurisdiction_state") or location-state)` / except → `[]`, str(e).
3. `guidance`, `guid_err` = try `synthesize_guidance(...)` / except → `None`, str(e).
4. If both failed: `UPDATE ... SET status='failed', error=$1, completed_at=NOW()`. Else `UPDATE ... SET status='complete', cases=$1::jsonb, guidance=$2::jsonb, error=$3, completed_at=NOW()` (error carries the partial-failure note or NULL).
5. Return the full row dict. Never raises on partial success.

Implementation note: the final `SELECT * FROM legal_matter_research WHERE id = $1` comes back through asyncpg with `cases`/`guidance` as raw JSON text (no jsonb codec on this pool) — `run_research` decodes both via the shared `parse_research_row()` helper before returning, and the two research routes call the same helper on their own `SELECT`s.

## Phase 4 — `server/app/matcha/services/legal_defense.py`

### 4a. `resolve_matter_jurisdiction(conn, matter: dict) -> dict | None` (new, after `_hum` ~line 106)

```python
async def resolve_matter_jurisdiction(conn, matter):
    loc, jid, state = None, None, (matter.get("jurisdiction_state") or "").upper() or None
    if matter.get("location_id"):
        loc = await conn.fetchrow(
            "SELECT jurisdiction_id, name, state FROM business_locations "
            "WHERE id = $1 AND company_id = $2",
            matter["location_id"], matter["company_id"])
        if loc:
            jid = loc["jurisdiction_id"]
            state = state or (loc["state"] or "").upper() or None
    if jid is None and state:
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE state = $1 AND level = 'state' "
            "AND country_code = 'US' LIMIT 1", state)
        jid = row["id"] if row else None
    if jid is None:
        return None
    chain = await conn.fetch(
        """WITH RECURSIVE chain AS (
             SELECT id, parent_id, level, display_name, 0 AS depth
             FROM jurisdictions WHERE id = $1
             UNION ALL
             SELECT j.id, j.parent_id, j.level, j.display_name, c.depth + 1
             FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
             WHERE c.depth < 6)
           SELECT id, level, display_name FROM chain ORDER BY depth""", jid)
    return {"jurisdiction_id": jid,
            "chain": [dict(r) for r in chain],
            "state": state,
            "location_name": loc["name"] if loc else None}
```
Chain only — deliberately NOT `compliance_service.resolve_jurisdiction_stack` (that CTE drags every requirement row).

### 4b. Matter-type → category filter + law/bill/case gatherers

```python
from app.core.compliance_registry import CATEGORY_KEYS  # sanity only; sets below are hand-picked

_WAGE_HOUR = ["minimum_wage", "overtime", "meal_breaks", "pay_frequency", "final_pay",
              "scheduling_reporting", "sick_leave", "leave", "employee_classification",
              "equal_pay", "pay_transparency"]
_EEO = ["anti_discrimination", "equal_pay", "pregnancy_accommodation", "eeo_reporting",
        "background_checks", "pay_transparency", "whistleblower"]
_MATTER_TYPE_CATEGORIES: dict[str, list[str] | None] = {
    "class_action": _WAGE_HOUR, "single_plaintiff": _WAGE_HOUR,
    "eeoc_charge": _EEO,
    "subpoena": None, "audit": None, "other": None,   # None = no category filter
}
```
All slugs verified against `app/core/compliance_registry.py` `CATEGORIES` (labor group, 28 keys). Add a module-load assert: `assert all(k in CATEGORY_KEYS for ks in _MATTER_TYPE_CATEGORIES.values() if ks for k in ks)` — registry renames then fail loudly at import, not silently at query time.

**`_gather_law(conn, matter, juris) -> tuple[dict | None, dict | None]`** — returns `(law_source, legislation_source)` shaped like existing sources (`{"label", "records"}`):

- Primary retrieval: RAG. Lazy import guarded by API key (pattern: `matcha_work/messaging.py:49-68`); `ComplianceRAGService().search_requirements(query=f"{matter.get('allegation') or ''} {_hum(matter.get('matter_type'))}", conn=conn, jurisdiction_ids=[c["id"] for c in juris["chain"]], categories=_MATTER_TYPE_CATEGORIES.get(matter.get("matter_type")), top_k=30, min_similarity=0.25)` — returns `requirement_id, title, current_value, statute_citation, effective_date, category, jurisdiction_level, jurisdiction_name, source_name, source_url` (verified signature, `compliance_rag.py:22-56`; the service actually lives at `core/services/compliance_rag.py`, not `matcha/services/`).
- Fallback (no key / no allegation / zero hits / exception) — direct query, category filter optional; **if the filtered query returns zero rows, retry unfiltered** (a wage map on a non-wage class action must not blank the source):

```sql
SELECT id, title, category, current_value, statute_citation, effective_date,
       jurisdiction_level, jurisdiction_name
FROM jurisdiction_requirements
WHERE jurisdiction_id = ANY($1::uuid[]) AND status = 'active'
  AND ($2::text[] IS NULL OR category = ANY($2))
ORDER BY effective_date DESC NULLS LAST LIMIT 40
```
- Law record shape (mirrors existing compact style):
```python
{"cid": f"law:{r['requirement_id' or 'id']}",
 "ref": r.get("statute_citation") or _hum(r["category"]),
 "summary": f"{r['title']}" + (f" = {r['current_value']}" if r.get("current_value") else "")
            + f" ({r.get('jurisdiction_name') or ''}, {_hum(r.get('jurisdiction_level'))})",
 "when": _dt(r.get("effective_date"))}
```
- Legislation (columns verified in `database.py:3194+`):
```sql
SELECT id, title, category, current_status, expected_effective_date, impact_summary
FROM jurisdiction_legislation
WHERE jurisdiction_id = ANY($1::uuid[])
ORDER BY expected_effective_date ASC NULLS LAST LIMIT 15
```
→ `{"cid": f"bill:{r['id']}", "ref": _hum(r["category"]) or "Legislation", "summary": f"{r['title']} — {_hum(r['current_status'])}" + impact-snippet (first 160 chars), "when": _dt(r["expected_effective_date"])}`.

**`_gather_case_law(conn, matter_id) -> dict | None`** — `SELECT cases FROM legal_matter_research WHERE matter_id=$1 AND status='complete' AND cases IS NOT NULL ORDER BY created_at DESC LIMIT 1`; each case → `{"cid": f"case:{c['id']}", "ref": c.get("citation") or c.get("court") or "opinion", "summary": f"{c['case_name']} — {c.get('court') or ''}", "when": c.get("date_filed") or ""}`. Label: `"Case law (external research — informational)"`. Decodes `cases` from JSON text itself (see the asyncpg jsonb note above) — isolated try/except, returns `None` on any parse failure rather than raising.

### 4c. `gather_evidence` (line 279) — signature + assembly

`async def gather_evidence(conn, company_id, start, end, features: dict, matter: dict | None = None)` — keyword default keeps the 3 existing call sites and all existing tests source-compatible. After the `_SOURCES` loop (line 305), before the index build (line 307):

```python
legal_context = None
if matter:
    try:
        legal_context = await resolve_matter_jurisdiction(conn, matter)
    except Exception as e:
        logger.warning("legal_defense: jurisdiction resolve failed: %s", e)
        notes.append("Jurisdiction: unavailable")
    if legal_context:
        try:
            law_src, bill_src = await _gather_law(conn, matter, legal_context)
            if law_src and law_src["records"]:
                sources["law"] = law_src
            if bill_src and bill_src["records"]:
                sources["legislation"] = bill_src
        except Exception as e:
            logger.warning("legal_defense: law source unavailable: %s", e)
            notes.append("Governing requirements (jurisdiction): unavailable")
    try:
        case_src = await _gather_case_law(conn, matter.get("id"))
        if case_src and case_src["records"]:
            sources["case_law"] = case_src
    except Exception as e:
        logger.warning("legal_defense: case-law source unavailable: %s", e)
        notes.append("Case law (external research): unavailable")
```
Return gains `"legal_context": legal_context` alongside sources/index/notes. Index build unchanged — new cids flow into `index` and through `validate_citations` untouched. Labels: `law` = "Governing requirements (jurisdiction)", `legislation` = "Pending legislation (jurisdiction)".

### 4d. Richer compliance (line 149 + new source)

- `_src_compliance`: add `LEFT JOIN jurisdiction_requirements jr ON jr.id = cr.jurisdiction_requirement_id`, select `jr.statute_citation`, append `f" [{r['statute_citation']}]"` to `summary` when present. Corpus stays compact.
- New `_src_compliance_alerts(conn, company_id, start, end)` — columns verified (`database.py` compliance_alerts: title, message, severity, status, category, action_required, source_url, source_name, deadline, created_at):

```sql
SELECT ca.id, ca.title, ca.severity, ca.status, ca.category, ca.deadline, ca.created_at,
       bl.name AS location_name
FROM compliance_alerts ca JOIN business_locations bl ON bl.id = ca.location_id
WHERE ca.company_id = $1
  AND ($2::date IS NULL OR ca.created_at >= $2)
  AND ($3::date IS NULL OR ca.created_at < ($3::date + 1))
ORDER BY ca.created_at DESC
```
Date-filtered (history — shows the company was monitoring during the window; deliberate contrast with the not-date-filtered posture source). Record: `{"cid": f"compliance_alert:{r['id']}", "ref": _hum(r["category"]) or "Alert", "summary": f"{r['title']} — {_hum(r['severity'])}, {_hum(r['status'])}" + (f", deadline {_dt(r['deadline'])}" if deadline) + (f" @ {location_name}"), "when": _dt(r["created_at"])}`. Registered in `_SOURCES` right after `"compliance"`:
```python
("compliance_alerts", "Compliance monitoring alerts", _src_compliance_alerts,
 lambda f: bool(f.get("compliance") or f.get("compliance_lite"))),
```

### 4e. Prompt (`_SYSTEM` line 319, `_build_prompt` line 352)

Appended to `_SYSTEM` HARD RULES (verbatim):

> - Records with `law:`, `bill:`, or `case:` IDs are LEGAL CONTEXT (governing requirements, pending legislation, externally researched case law) — they describe the legal landscape, NOT the company's conduct. You may cite them to identify which requirements or authorities appear relevant. NEVER conclude the company complied with or violated anything, and NEVER present a `case:` record as precedent analysis — flag it for counsel to evaluate.

`_build_prompt` MATTER block gains one line: `Jurisdiction: {" → ".join(c["display_name"] for c in (corpus.get("legal_context") or {}).get("chain", [])) or "(not specified)"}`.

### 4f. Packet (`_memo_html` 501, `_APPENDIX_SECTIONS` 889, `build_defense_packet` 928)

- `_AUDIT_ACTION_LABELS` (line 474): `"research": "External legal research run"`.
- New fetchers: `_detail_law(conn, req_id)` — `SELECT * FROM jurisdiction_requirements WHERE id = $1` (global repo table, no tenant scope; comment why). `_detail_alert(conn, alert_id, company_id)` — alerts row JOIN business_locations for scoping.
- New renderers `_law_section(cid, d)` (grid: statute citation / category / jurisdiction / current value / effective / source; `metadata->'penalties'` summary line when present) and `_alert_section(cid, d)` (grid: severity / status / category / deadline / location + message narr). Registered `"law"` and `"compliance_alert"` in `_APPENDIX_SECTIONS`; the two prefixes added to the detail-fetch dispatch in `build_defense_packet`. `bill:`/`case:` get NO appendix section — they still appear in the evidence-index table.
- Extended `_detail_compliance`/`_compliance_section` with joined `jr.statute_citation`.
- `build_defense_packet(conn, matter, corpus, memo, company_name=None, research: dict | None = None)`: when `research`, `_memo_html` appends `_research_html(research)` after the custody block — a `.appendix-section` page with:
  - `<h2>Legal landscape — informational; verify with counsel</h2>`
  - Bold standalone disclaimer paragraph.
  - Cases table: Name / Citation / Court / Filed / URL.
  - Guidance: summary paragraphs + key-authorities list (name — publisher, URL).
- `_collect_source_files` and `_build_zip`: unchanged — new kinds have no uploaded documents.

## Phase 5 — Routes `server/app/matcha/routes/legal_defense.py`

- `MatterCreate` + `MatterUpdate`: added
  ```python
  location_id: Optional[UUID] = None
  jurisdiction_state: Optional[str] = Field(None, min_length=2, max_length=2)
  ```
  with a `field_validator("jurisdiction_state")` uppercasing.
- New helper `_check_location(conn, location_id, company_id)` → 400 "Location not found" unless `SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2`. Called in `create_matter` and in `update_matter` when `location_id` in fields.
- `create_matter` INSERT: added the two columns.
- All three `gather_evidence` call sites pass `matter=matter`: `get_evidence`, `chat`, `generate_packet`.
- `get_evidence` response: added `"legal_context": corpus.get("legal_context")`.
- New endpoints:

```python
@router.post("/matters/{matter_id}/research")
async def run_matter_research(matter_id: str, request: Request,
                              current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    await check_rate_limit(str(company_id), "legal_research", 10, 3600)
    async with get_connection() as conn:
        matter = await _load_matter(conn, matter_id, company_id)
        row = await legal_research.run_research(conn, matter, getattr(current_user, "id", None))
        await _audit(conn, matter_id, current_user, request, "research",
                     {"cases": len(row.get("cases") or []), "status": row.get("status")})
    return row

@router.get("/matters/{matter_id}/research")
async def list_matter_research(matter_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_matter(conn, matter_id, company_id)
        rows = await conn.fetch(
            "SELECT * FROM legal_matter_research WHERE matter_id = $1 ORDER BY created_at DESC",
            matter_id)
    return [legal_research.parse_research_row(dict(r)) for r in rows]
```
  Synchronous POST (worst case ~110s: 20s CourtListener + 90s Gemini) — acceptable behind an explicit button; the row-status design supports a later move to `BackgroundTasks` + GET-poll with no schema change. `run_research` resolves `state` itself from `matter["jurisdiction_state"]`, else a `business_locations` lookup by `matter["location_id"]`.
- `PacketIn`: `include_research: bool = False`. In `generate_packet`, when set: fetch the latest complete research row, decode it via `legal_research.parse_research_row`, pass `research=row` to `build_defense_packet`; `"research": body.include_research` added to the audit details.
- No new feature flag; no mount changes (`routes/__init__.py` untouched — both routers already mounted).

## Phase 6 — Frontend

**`client/src/api/legalDefense.ts`**
- `Matter`/`MatterCreate`: `location_id?: string | null`, `jurisdiction_state?: string | null`.
- `EvidencePreview`: `legal_context?: LegalContext | null` (`{ jurisdiction_id, chain: {id,level,display_name}[], state, location_name }`).
- New types + calls: `ResearchCase`, `ResearchGuidance`, `ResearchRow`, `runResearch(matterId)`, `listResearch(matterId)`.
- `generatePacket(id, kind, includeResearch = false)` → body `{ kind, include_research: includeResearch }`.

**`client/src/pages/app/LegalDefense/shared.ts`**
- `CID_KIND_LABEL` += `law`, `bill`, `case`, `compliance_alert`.
- `SOURCE_META` += `compliance_alerts` (`Bell`), `law` (`Landmark`), `legislation` (`ScrollText`), `case_law` (`BookMarked`).

**`modals.tsx` — NewMatterModal**
- Loads `fetchLocations()` from `api/compliance.ts` on mount; optional "Location (governing jurisdiction)" select + a 2-letter "or state" fallback input. Both included in the `createMatter` payload.

**New `LegalContextPanel.tsx`** (top of right rail in `index.tsx`, above `EvidencePanel`)
- Renders: jurisdiction chain breadcrumb chips; "Research" button (spinner while running); latest research — cases as external links + guidance summary + authorities links (capped at `max-h-64 overflow-y-auto` so a long research result doesn't push the packets panel off-screen); permanent disclaimer caption; failed-state error line; empty state when no jurisdiction is set.

**`Masthead.tsx`** — Toggle "Include legal landscape (informational)" shown only when a `complete` research row exists, default off; `onGenerate` signature widened to `(kind, includeResearch)`.

**`index.tsx`** — `openMatter` now also fetches `listResearch(matter.id)`; holds `research`/`researching` state; `handleRunResearch` calls `runResearch` and replaces state on completion; threaded into `Masthead` + `LegalContextPanel`.

## Phase 7 — Tests

`server/tests/legal_defense/test_legal_defense.py` (12 tests total, up from 7):
- `test_validate_citations_accepts_new_cid_kinds`, `test_gather_evidence_without_matter_adds_no_law_source`, `test_gather_evidence_jurisdiction_failure_degrades`, `test_src_compliance_alerts_shape`, `test_matter_type_categories_are_registry_keys`.

New `server/tests/legal_defense/test_legal_research.py` (5 tests):
- `test_parse_search_results_maps_v4_fields`, `test_parse_search_results_tolerates_missing_keys`, `test_run_research_persists_only_api_rows`, `test_run_research_partial_failure_completes`, `test_run_research_total_failure_marks_failed`.

`cd server && ./venv/bin/python -m pytest tests/legal_defense/ -q` → **17 passed**. Frontend: `cd client && npx tsc --noEmit --incremental false` → clean.

## Verification (end-to-end)

1. Unit tests + tsc — done, both green (see Phase 7).
2. Live CourtListener smoke call — **not yet run** (this sandbox's proxy blocks courtlistener.com); do this from the dev machine before relying on `_parse_search_results` against real traffic, and adjust the fixture if any v4 key differs.
3. Migration **not yet applied** — run `./scripts/migrate-dev.sh` (requires explicit approval per repo DB rules), then in the dev UI: create matters with (a) location, (b) state-only, (c) neither → confirm law/legislation sources appear/degrade; run research → cases + guidance render with disclaimers; generate packet with `include_research` on and off → verify the legal-landscape page and the unchanged evidence memo; confirm `research` rows in the chain-of-custody table on regeneration.
4. Commit + push to `claude/legal-pilot-robustness-grkay3` (updates PR #12).

## Risks / notes

- CourtListener v4 keys: high confidence from official docs, but the live smoke call is still pending; isolated to one pure function + fixture.
- Prod EC2 needs outbound HTTPS to `courtlistener.com` (no proxy there — fine); this sandbox cannot reach it.
- RAG coverage may be sparse per jurisdiction → direct-query fallback, plus unfiltered retry when a category filter zeroes out.
- Corpus growth ≤ ~63 lines (law 40 + bills 15 + cases 8); `_PER_SOURCE_CAP` already bounds each source.
- Synchronous research POST ~110s worst case; frontend button shows a spinner; background move is a no-schema-change follow-up.
- Legal posture: `case:` hits are search-relevance results, not vetted precedent — prompt rule + fixed "informational — verify with counsel" labels in panel and packet; keep the language intact in review.
- asyncpg jsonb columns come back as raw text on this pool (no codec registered) — every new reader of `legal_matter_research.cases`/`.guidance` decodes explicitly via `legal_research.parse_research_row()` or an inline `json.loads` guard, matching the pre-existing pattern used elsewhere in `legal_defense.py` (`_latest_memo`, `_describe_audit`).
