# Legal Pilot Robustness — Technical Plan

Jurisdiction grounding, richer compliance evidence, and external legal research (CourtListener + grounded Gemini) for the Legal Pilot (`legal_defense` flag, `/app/legal-pilot`).

**Status: plan only — not yet implemented.**

## Context

Legal Pilot grounds its AI in 7 internal evidence sources, but matters carry **no jurisdiction**, the compliance source is a thin slice of per-location requirement values, and there is no external legal context at all. Meanwhile the platform already holds a rich jurisdiction corpus (`jurisdiction_requirements` with statute citations/penalties/source URLs, `jurisdiction_legislation`, a pgvector RAG index via `ComplianceRAGService`) that Legal Pilot never touches.

Approved scope:

1. **Jurisdiction-aware matters + governing-law evidence** — matters get an optional `location_id` + `jurisdiction_state`; new citable corpus sources `law:` / `bill:` built from the matter's jurisdiction stack.
2. **Richer compliance evidence** — statute citations joined into the existing compliance source; new `compliance_alert:` source (monitoring history = good-faith/diligence signal for the defense narrative).
3. **External legal research (CourtListener + Gemini grounding)** — on-demand research per matter; only CourtListener-API-returned cases become citable `case:` records; Gemini-grounded agency-guidance synthesis is informational-only and never citable.
4. **Surfacing** — chat + a new Legal Context panel; the packet gets an **opt-in** "Legal landscape — informational; verify with counsel" section (default off), kept visually and textually separate from the evidence narrative.

Out of scope (deliberately deferred): wiring the `ir_precedent`/`er_precedent` company-precedent engines into Legal Pilot.

**Anti-hallucination invariant (paramount):** `validate_citations` (`server/app/matcha/services/legal_defense.py:371`) is pure index-membership — every new record type flows into `corpus["index"]` and through the gate unchanged. Gemini guidance text NEVER mints citation IDs; only DB rows and persisted CourtListener API rows do.

---

## Phase 1 — Migration

**New** `server/alembic/versions/legaldef02_matter_jurisdiction_research.py`
`revision="legaldef02"`, `down_revision="mwtaskhtxt01"` (verified leaf of the branch containing `legaldef01`: `legaldef01 → lossratio01 → … → posterbrand01 → mwtaskhtxt01`). The repo has many migration leaves — copy the multi-leaf caveat comment style from `lossratio01`. All DDL via `op.execute` with `IF NOT EXISTS` (matches `legaldef01`).

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
    cases         JSONB,      -- verified CourtListener API rows ONLY (mint case:<id> cids)
    guidance      JSONB,      -- grounded-Gemini synthesis; informational, never citable
    error         TEXT,
    created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_legal_matter_research_matter
    ON legal_matter_research(matter_id, created_at DESC);
```

Jurisdiction design: both columns optional. `location_id` preferred (→ `business_locations.jurisdiction_id` → full city/county/state/federal stack); `jurisdiction_state` is the fallback (company has no location, location has no `jurisdiction_id`, or the dispute is in a different state). Downgrade drops the table + both columns.

## Phase 2 — Config

`server/app/config.py`: add `courtlistener_api_token: Optional[str] = None` near `openstates_api_key` (~line 171); wire `os.getenv("COURTLISTENER_API_TOKEN")` in `load_settings()` (~line 337). Token optional (anonymous works; token raises CourtListener rate limits).

## Phase 3 — New service `server/app/matcha/services/legal_research.py`

Module docstring: external legal research is **informational, never legal advice**; only API-verified cases become citable.

- `COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v4"`, timeout 20s, `httpx.AsyncClient` (repo convention — see `services/property_cat.py`; `httpx>=0.25.0` already pinned).
- `_parse_search_results(payload, limit=8) -> list[dict]` — **pure**, tolerant of missing keys (unit-testable, no HTTP). Maps each `results[]` item to `{id, case_name, citation (first of list or None), court, date_filed, url ("https://www.courtlistener.com" + absolute_url), snippet}`. Verify exact v4 field names (`caseName` vs `case_name`, `cluster_id`) against one live response during implementation; pin in a test fixture.
- `search_case_law(query, state=None, limit=8)` — GET `/search/?q=…&type=o&order_by=score desc`; `Authorization: Token …` when configured. No court-id filtering in v1 (CourtListener court slugs are non-obvious) — append the state's full name to the query text instead.
- `synthesize_guidance(matter, cases) -> dict` — grounded Gemini call (own local helper, not the compliance singleton — its retry machinery is compliance-prompt-specific): `get_genai_client().aio.models.generate_content` with `tools=[types.Tool(google_search=types.GoogleSearch())]`, `temperature=0.0`, `asyncio.wait_for(…, 90)`; rate-limit via `get_rate_limiter().check_limit("gemini_compliance", "legal_research")` + `record_call` (reuse existing bucket, no new limiter key). Prompt: given matter type/allegation/jurisdiction, summarize the agency-guidance landscape (EEOC / DOL / state agency) with source URLs; strict JSON `{"summary", "key_authorities":[{name,url,publisher,relevance}]}`; parse with `legal_defense._parse_json`. Explicit instruction: informational only, no conclusions, no advice.
- `run_research(conn, matter, created_by) -> dict` — INSERT row status `running`; query = matter_type label + first ~300 chars of allegation; run case search and guidance each in its own try/except (partial success OK; both fail → `failed` + error); UPDATE to `complete` with cases/guidance + `completed_at`; return the row.

## Phase 4 — `server/app/matcha/services/legal_defense.py`

### 4a. Jurisdiction resolution

New `resolve_matter_jurisdiction(conn, matter) -> dict | None`:

1. If `location_id`: fetch `jurisdiction_id, name, state` from `business_locations` (company-scoped).
2. `jid` = the location's `jurisdiction_id`, else state-level lookup (`SELECT id FROM jurisdictions WHERE state=$1 AND level='state' AND country_code='US'` — pattern at `core/routes/resources.py:1384`) on `jurisdiction_state` or the location's state.
3. If `jid`: light recursive CTE walking `jurisdictions.parent_id` for the chain only (do NOT call `compliance_service.resolve_jurisdiction_stack` — it drags all requirements along).
4. Return `{jurisdiction_id, chain:[{id,level,display_name}], state, location_name}` or `None` (feature degrades silently).

### 4b. New corpus sources

- `_MATTER_TYPE_CATEGORIES: dict[str, list[str]|None]` — matter_type → `jurisdiction_requirements.category` filter sets (wage/hour set for `class_action`/`single_plaintiff`; discrimination/harassment/accommodations set for `eeoc_charge`; `None` = no filter for `subpoena`/`audit`/`other`). **Verify slugs against `SELECT DISTINCT category FROM jurisdiction_requirements` on dev before hardcoding** — a wrong map is non-fatal (fallback below).
- `_gather_law(conn, matter, juris)` → `(law_source, legislation_source)`:
  - Primary: RAG — lazy-import `ComplianceRAGService` guarded by API key (copy the pattern at `matcha_work/messaging.py:49-68`); `search_requirements(query=allegation + type label, jurisdiction_ids=chain ids, categories=…, top_k=30, min_similarity=0.25)`.
  - Fallback (no key / zero hits / exception): direct `jurisdiction_requirements WHERE jurisdiction_id=ANY(chain) AND status='active'` + optional category filter, `ORDER BY effective_date DESC NULLS LAST LIMIT 40`.
  - Record shape: `cid=f"law:{id}"`, ref = `statute_citation or _hum(category)`, summary = title + current_value + jurisdiction name/level + effective date. Cap 40.
  - Legislation: `jurisdiction_legislation WHERE jurisdiction_id=ANY(chain) ORDER BY expected_effective_date NULLS LAST LIMIT 15` → `cid=f"bill:{id}"`, summary from title + current_status + expected_effective_date + impact snippet.
- `_gather_case_law(conn, matter_id)` — latest `complete` `legal_matter_research` row; each persisted case → `cid=f"case:{c['id']}"`, ref = citation or court, summary = case_name — court, when = date_filed. Source label: "Case law (external research — informational)".

### 4c. `gather_evidence` (line 279)

Signature → `gather_evidence(conn, company_id, start, end, features, matter=None)`. After the `_SOURCES` loop, before the index build: if `matter`, add sources `"law"`, `"legislation"`, `"case_law"` — each in its own try/except with the same degrade-to-note discipline as existing sources. Stash `corpus["legal_context"] = juris` for routes/UI. Index build unchanged → new cids are covered by `validate_citations` automatically.

### 4d. Richer compliance

- `_src_compliance` (line 149): `LEFT JOIN jurisdiction_requirements jr ON jr.id = cr.jurisdiction_requirement_id`; append `jr.statute_citation` to the summary when present. Keep corpus lines compact (description/penalties go to the appendix detail, not the corpus).
- New `_src_compliance_alerts(conn, company_id, start, end)` — `compliance_alerts` JOIN `business_locations` (tenant scope), **date-filtered on `created_at`** (it's history, unlike the not-date-filtered posture source); `cid=f"compliance_alert:{id}"`, summary = title + severity + status + location + deadline. Register in `_SOURCES` (line 261) after `"compliance"` with the same feature predicate (`compliance` or `compliance_lite`).

### 4e. Prompt

- `_SYSTEM` (line 319) additions: records with `law:` / `bill:` / `case:` IDs describe the LEGAL CONTEXT (governing requirements, pending legislation, externally researched case law), not the company's conduct. The model may cite them to identify which requirements/authorities appear relevant, but must NEVER conclude the company complied or violated anything, and NEVER treat `case:` records as precedent analysis — flag them for counsel.
- `_build_prompt` (line 352): MATTER block gains `Jurisdiction: <chain display, e.g. "San Francisco, CA → California → US Federal", or "(not specified)">` from `corpus["legal_context"]`.

### 4f. Packet

- New detail fetchers `_detail_law(conn, req_id)` (global table, no tenant scope needed) and `_detail_alert(conn, alert_id, company_id)` (location-joined scoping like `_detail_compliance`). New renderers `_law_section` (statute citation, current value, jurisdiction, effective date, description, penalties summary from `metadata->'penalties'`, source name/URL) + `_alert_section`; register `"law"` and `"compliance_alert"` in `_APPENDIX_SECTIONS` (line 889). Extend `_detail_compliance`/`_compliance_section` with the joined `jr.statute_citation`/`jr.description`. `bill:`/`case:` get no appendix (they still appear in the evidence-index table via the corpus index).
- `build_defense_packet(..., research=None)` (line 928): when passed, append a `_research_html(research)` section after "Open questions" — its own page titled **"Legal landscape — informational; verify with counsel"** with a bold standalone disclaimer, a cases table (name / citation / court / filed / URL), and the guidance summary + key-authorities list. Visually and textually separated from the record narrative.
- `_AUDIT_ACTION_LABELS` (line 474): add `"research": "External legal research run"` (the chain-of-custody table picks it up automatically).

## Phase 5 — Routes `server/app/matcha/routes/legal_defense.py`

- `MatterCreate` (line 44) / `MatterUpdate`: add `location_id: Optional[UUID]`, `jurisdiction_state: Optional[str]` (2-char, uppercase validator). Ownership check before insert/update: `SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2` else 400 (never trust a client-supplied location_id). Extend INSERT/UPDATE + row serialization.
- Pass `matter=matter` at all three `gather_evidence` call sites (evidence :243, chat :260, packet :332). `get_evidence` response adds `legal_context`.
- New endpoints (same authed router — research ships under the existing `legal_defense` flag, no new flag):
  - `POST /matters/{id}/research` — `_load_matter`; per-company rate limit `check_rate_limit(str(company_id), "legal_research", 10, 3600)` (helper already imported, line 28); synchronous `legal_research.run_research(...)` (worst case ~110s — acceptable for an explicit button; the row-status design supports moving to background execution later with the GET as poll target, no schema change); `_audit(..., "research", {...})`; return the row.
  - `GET /matters/{id}/research` — rows for the matter, newest first.
- `PacketIn` (line 72): add `include_research: bool = False`; when True fetch the latest `complete` research row → `build_defense_packet(research=…)`; record it in the audit details.

## Phase 6 — Frontend

- **`client/src/api/legalDefense.ts`**: `Matter`/`MatterCreate` gain `location_id?`, `jurisdiction_state?`; `EvidencePreview` gains `legal_context?: { chain: {level:string; display_name:string}[]; state: string|null; location_name: string|null } | null`; new `ResearchCase`/`ResearchRow` types + `runResearch(matterId)` / `listResearch(matterId)`; `generatePacket(id, kind, includeResearch=false)` sends `include_research`.
- **`client/src/pages/app/LegalDefense/shared.ts`**: `CID_KIND_LABEL` += `law: 'Governing law'`, `bill: 'Pending bill'`, `case: 'Case law'`, `compliance_alert: 'Compliance alert'`; `SOURCE_META` += `compliance_alerts` (icon `Bell`), `law` (`Landmark`), `legislation` (`ScrollText`), `case_law` (`BookMarked` — `Gavel` is taken by discipline). Masthead's SystemsStrip + EvidencePanel then render the new sources automatically.
- **`modals.tsx` NewMatterModal**: load locations via `fetchLocations()` from `client/src/api/compliance.ts:63`; add an optional "Location (governing jurisdiction)" select + a 2-letter state fallback input (used when no location picked). Pass both in `createMatter`.
- **New `LegalContextPanel.tsx`**: rendered at the top of the right rail in `index.tsx` (above `EvidencePanel`). Shows: jurisdiction chain as breadcrumb chips (from `evidence.legal_context`); a "Research legal landscape" button (calls `runResearch`, spinner while running); latest research result — cases as external links (name, citation, court, date), guidance summary + authority links; a fixed caption "External research is informational only — not legal advice; verify with counsel."; empty state prompting to set a location/state on the matter.
- **`Masthead.tsx`**: checkbox "Include legal landscape (informational)" (only shown when a `complete` research row exists, default **off**) threading `includeResearch` into packet generation.
- **`index.tsx`**: fetch `listResearch(matter.id)` alongside matter/evidence in `openMatter`; hold research state; pass to the panel + masthead.

## Phase 7 — Tests

Extend `server/tests/legal_defense/test_legal_defense.py`:

- `validate_citations` accepts `law:`/`case:` cids present in the index; drops unknown `case:999`.
- `gather_evidence` with `matter=None` has no law source; with a matter whose jurisdiction query raises → degrades to a note, no crash (extend `_FakeConn`).
- `_src_compliance_alerts` record shape.

New `server/tests/legal_defense/test_legal_research.py`:

- `_parse_search_results` maps fields + tolerates missing keys (static v4 fixture).
- `run_research`: only API rows persist to `cases`; guidance stored separately; partial failure (case search raises, guidance succeeds) → status `complete` with the error noted.

## Verification

1. `cd server && python3 -m pytest tests/legal_defense/ -q`
2. `cd client && npx tsc --noEmit`
3. One live CourtListener call to confirm v4 response field names before finalizing `_parse_search_results` + the fixture.
4. Manual (after running the migration via `./scripts/migrate-dev.sh`): create matters with (a) a location, (b) state-only, (c) neither — confirm law/legislation sources appear/degrade correctly; run research; generate the packet with and without the legal-landscape section.

## Sequencing

Migration + config → `legal_research.py` + tests → `legal_defense.py` service changes + tests → routes → frontend (api → shared → modal → panel → masthead → index).

## Risks / open items

- **Category slugs** in `_MATTER_TYPE_CATEGORIES` are unverified against real data — the no-filter fallback makes a wrong map non-fatal; check `SELECT DISTINCT category FROM jurisdiction_requirements` on dev.
- **CourtListener v4 field names** need one live check (isolated in `_parse_search_results` + fixture, so a fix is one function).
- **Embeddings coverage** (`compliance_embeddings`) may be sparse for some jurisdictions — the direct-query fallback covers it; spot-check RAG relevance.
- **Corpus size**: +~60 prompt lines (law ≤40, bills ≤15, cases ≤8) — within budget; per-source caps guard.
- **Multi-leaf alembic**: confirm the environment's head before upgrading (standard caveat carried by recent migrations).
- **Legal posture**: `case:` hits are search-relevance results, not vetted precedent — the prompt rule plus "informational — verify with counsel" labeling in the UI and packet is the mitigation; keep that language intact in review.
