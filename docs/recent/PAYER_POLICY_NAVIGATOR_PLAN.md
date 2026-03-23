# Payer Medical Policy Navigator

## Context

Physicians need to query payer coverage criteria by procedure/diagnosis — "What does Aetna require to approve brain MRI?" The system returns the relevant medical policy language with specific clinical criteria to document. No patient data involved.

This extends the existing payer_contracts on facility_attributes and reuses the RAG infrastructure we just built for regulatory Q&A. Separate tables because payer policies are keyed by (payer, procedure), not (jurisdiction, category).

## Data Sources (Tiered)

| Tier | Payer | Source | Data Quality |
|------|-------|--------|-------------|
| **1 (API)** | Medicare | CMS Coverage API (`api.coverage.cms.gov`) | Structured, authoritative, free |
| **2 (AI)** | Commercial (Aetna, UHC, BCBS, Cigna) | Gemini + Google Search grounding | Good, needs verification |

### CMS Coverage API (Tier 1)

Tested and confirmed working. Provides:
- **NCDs** (National Coverage Determinations): Federal-level coverage policies with full clinical criteria, indications, contraindications, coverage conditions
- **LCDs** (Local Coverage Determinations): Regional policies with clinical indication criteria, documentation requirements, coding guidelines
- **Articles** (Billing/Coding): CPT/HCPCS procedure codes + ICD-10 diagnosis codes that support/don't support medical necessity

**Key endpoints:**
- `GET /v1/reports/national-coverage-ncd/` — list all NCDs
- `GET /v1/data/ncd/?ncdid=177&ncdver=6` — full NCD detail (e.g., MRI policy)
- `GET /v1/reports/local-coverage-final-lcds/` — list all LCDs
- `GET /v1/data/lcd/?lcdid=35175&ver=64` — full LCD detail with clinical criteria
- `GET /v1/data/lcd/related-documents?lcdid=35175&ver=64` — find associated billing articles
- `GET /v1/data/article/hcpc-code?articleid=57215&ver=41` — CPT/HCPCS codes for an article
- `GET /v1/data/article/icd10-covered?articleid=57215&ver=41` — ICD-10 codes supporting medical necessity
- `GET /v1/metadata/license-agreement/` — get auth token (1hr validity, no API key needed)

**Ingestion strategy:** Bulk-import all NCDs + LCDs + associated articles with their CPT/ICD code mappings. This gives us complete Medicare coverage for every procedure with structured, authoritative data.

---

## Phase 1: Schema Migration

Single Alembic migration. Down_revision: `zl9m0n1o2p3q` (our compliance_embeddings migration).

### 1A. `payer_medical_policies` table (new)

Shared knowledge base — not company-scoped. Company filtering happens at query time via facility_attributes.payer_contracts.

```
payer_medical_policies (
    id UUID PK DEFAULT gen_random_uuid(),
    payer_name VARCHAR(100) NOT NULL,
    payer_type VARCHAR(50),                -- government, commercial, medicaid_managed_care
    policy_number VARCHAR(100),            -- payer's internal ID (CPB 0123, LCD L12345)
    policy_title TEXT,
    procedure_codes TEXT[],                -- CPT/HCPCS codes
    diagnosis_codes TEXT[],                -- ICD-10 codes
    procedure_description TEXT,
    coverage_status VARCHAR(30) NOT NULL DEFAULT 'conditional',
    requires_prior_auth BOOLEAN DEFAULT false,
    clinical_criteria TEXT,                -- KEY FIELD: detailed approval criteria
    documentation_requirements TEXT,       -- what physicians must submit
    medical_necessity_criteria TEXT,
    age_restrictions VARCHAR(100),
    frequency_limits VARCHAR(200),
    place_of_service TEXT[],
    effective_date DATE,
    last_reviewed DATE,
    source_url TEXT,
    source_document TEXT,
    research_source VARCHAR(30) DEFAULT 'gemini',  -- 'cms_api', 'gemini', 'manual'
    cms_document_id INTEGER,                       -- CMS NCD/LCD document_id
    cms_document_type VARCHAR(10),                 -- 'ncd', 'lcd', 'article'
    cms_document_version INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(payer_name, policy_number)
)
Indexes: payer_name, GIN(procedure_codes), (payer_name, coverage_status), cms_document_id
```

### 1B. `payer_policy_embeddings` table (new)

One embedding per policy row (same 1:1 pattern as compliance_embeddings).

```
payer_policy_embeddings (
    id UUID PK DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL UNIQUE → payer_medical_policies(id) ON DELETE CASCADE,
    payer_name VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
)
Indexes: payer_name
```

**Files:**
- New: `server/alembic/versions/zm0n1o2p3q4r_add_payer_medical_policies.py`
- Modify: `server/app/database.py` — add tables in init_db() after compliance_embeddings block

---

## Phase 2: Backend Services

### 2A. CMS Coverage API Ingestion Service

**New file: `server/app/core/services/cms_coverage_api.py`**

Primary data source for Medicare. Ingests NCDs, LCDs, and their associated billing articles with CPT/ICD code mappings.

```python
class CMSCoverageAPI:
    BASE_URL = "https://api.coverage.cms.gov"

    async def get_license_token(self) -> str

    # NCD ingestion
    async def list_ncds(self) -> list[dict]
    async def get_ncd(self, ncd_id: int, version: int) -> dict

    # LCD ingestion
    async def list_lcds(self, state: str = None) -> list[dict]
    async def get_lcd(self, lcd_id: int, version: int) -> dict
    async def get_lcd_related_documents(self, lcd_id: int, version: int) -> list[dict]

    # Article (billing/coding) data
    async def get_article_cpt_codes(self, article_id: int, version: int) -> list[dict]
    async def get_article_icd10_covered(self, article_id: int, version: int) -> list[dict]
    async def get_article_icd10_noncovered(self, article_id: int, version: int) -> list[dict]

    # High-level ingestion
    async def ingest_ncd(self, ncd_id: int, version: int, conn) -> dict
        """Fetch NCD, parse clinical criteria from HTML, store in payer_medical_policies."""
    async def ingest_lcd_with_codes(self, lcd_id: int, version: int, conn) -> dict
        """Fetch LCD + related articles + CPT/ICD codes, store as policy row."""
    async def ingest_all_ncds(self, conn) -> int
    async def ingest_all_lcds(self, conn, state: str = None) -> int
```

The ingest functions:
1. Fetch the NCD/LCD detail (clinical criteria in HTML — strip tags to get plain text)
2. Fetch related articles → get CPT/HCPCS codes + ICD-10 covered codes
3. Compose a `payer_medical_policies` row with:
   - `payer_name` = "Medicare"
   - `policy_number` = NCD display_id or LCD display_id (e.g., "NCD 220.2" or "L35175")
   - `policy_title` = title
   - `procedure_codes` = CPT codes from associated article
   - `diagnosis_codes` = ICD-10 covered codes from associated article
   - `clinical_criteria` = parsed `indications_limitations` (NCD) or `indication` (LCD)
   - `documentation_requirements` = parsed `doc_reqs` field from LCD
   - `coverage_status` = "covered" / "conditional" based on content
   - `source_url` = CMS URL
   - `research_source` = "cms_api"
   - `cms_document_id`, `cms_document_type`, `cms_document_version`
4. Upsert with `ON CONFLICT (payer_name, policy_number) DO UPDATE`
5. Embed via `embed_updated_policies`

### 2B. Payer Policy RAG Service

**New file: `server/app/core/services/payer_policy_rag.py`**

Follows `compliance_rag.py` exactly:

```python
class PayerPolicyRAGService:
    def __init__(self, embedding_service: EmbeddingService)

    async def search_policies(
        query, conn, payer_names=None, top_k=10, min_similarity=0.3
    ) -> list[dict]

    async def get_context_for_query(
        query, conn, company_id, location_id=None, payer_name=None, max_tokens=8000
    ) -> tuple[str, list[dict]]
```

- Vector search: `1 - (embedding <=> $1::vector) AS similarity` on `payer_policy_embeddings` joined with `payer_medical_policies`
- Payer filtering: resolves company's payer_contracts from `facility_attributes`:
  ```sql
  SELECT DISTINCT jsonb_array_elements_text(facility_attributes->'payer_contracts')
  FROM business_locations WHERE company_id = $1 AND is_active = true
  ```
- Context format per result:
  ```
  [{payer_name} — {policy_title}]
    Procedure: {procedure_description} ({procedure_codes})
    Coverage: {coverage_status} | Prior Auth: {requires_prior_auth}
    Clinical Criteria: {clinical_criteria}
    Documentation: {documentation_requirements}
    Source: {source_url}
  ```

### 2C. Embedding Pipeline

**New file: `server/app/core/services/payer_policy_embedding_pipeline.py`**

Follows `compliance_embedding_pipeline.py`:

- `compose_policy_embedding_text(policy)` — Format: `"{payer_name}: {procedure_description} ({codes}). Coverage: {status}. Requires prior auth: {bool}. Clinical criteria: {criteria}. Documentation: {docs}"`
- `embed_policies(conn, payer_name=None, batch_size=50) -> int`
- `embed_updated_policies(conn) -> int`

### 2D. Gemini Research Service (Tier 2 — commercial payers)

**New file: `server/app/core/services/payer_policy_research.py`**

`research_payer_policy(payer_name, procedure, conn) -> Optional[dict]`

Fallback for non-Medicare payers (Aetna, UHC, BCBS, Cigna, etc.) where no API exists.

- Uses `GeminiComplianceService()._call_with_retry()` with Google Search grounding
- Prompt asks for structured JSON: policy_number, procedure_codes, coverage_status, clinical_criteria, documentation_requirements, medical_necessity_criteria, etc.
- On success: INSERT into `payer_medical_policies` with `ON CONFLICT (payer_name, policy_number) DO UPDATE`
- Immediately embeds the new row via `embed_updated_policies`
- On failure: returns None (caller handles gracefully)

---

## Phase 3: API Endpoints

All added to `server/app/core/routes/compliance.py`.

### 3A. `POST /compliance/payer-policies/ask`

Single-turn Q&A (same shape as `/compliance/ask`):
- Body: `{ question: str, location_id?: str, payer_name?: str }`
- Response: `{ answer: str, sources: [...], confidence: float }`
- Flow: RAG search → if empty, auto-research via Gemini → compose context → generate answer
- System prompt: "You are a medical policy expert. Cite specific clinical criteria and documentation requirements. State whether prior auth is required."

### 3B. `GET /compliance/payer-policies`

List/browse policies:
- Query params: `payer_name`, `procedure_code`, `requires_prior_auth`, `coverage_status`, `limit`, `offset`
- Filters to company's payer_contracts
- Returns `PayerPolicyResponse[]`

### 3C. `POST /compliance/payer-policies/research`

Explicit research trigger:
- Body: `{ payer_name: str, procedure: str }`
- Calls `research_payer_policy`, returns the new policy or 422

### 3D. Response model

Add to `server/app/core/models/compliance.py`:

```python
class PayerPolicyResponse(BaseModel):
    id: str
    payer_name: str
    payer_type: Optional[str] = None
    policy_number: Optional[str] = None
    policy_title: Optional[str] = None
    procedure_codes: list[str] = []
    procedure_description: Optional[str] = None
    coverage_status: str
    requires_prior_auth: bool = False
    clinical_criteria: Optional[str] = None
    documentation_requirements: Optional[str] = None
    medical_necessity_criteria: Optional[str] = None
    frequency_limits: Optional[str] = None
    source_url: Optional[str] = None
    source_document: Optional[str] = None
    effective_date: Optional[str] = None
    last_reviewed: Optional[str] = None
```

---

## Phase 4: Frontend

### 4A. API client additions

**Modify: `client/src/api/compliance.ts`**

Add types + functions:
- `PayerPolicySource`, `PayerPolicyQAResponse`, `PayerPolicy` interfaces
- `askPayerPolicyQuestion(question, locationId?, payerName?)`
- `fetchPayerPolicies(params)`
- `researchPayerPolicy(payerName, procedure)`

### 4B. PayerPolicyNavigator component

**New file: `client/src/components/compliance/PayerPolicyNavigator.tsx`**

Based on `RegulatoryQuickAsk.tsx` pattern with payer-specific additions:
- Payer dropdown filter (populated from location's facility_attributes.payer_contracts)
- Search input with medical-focused placeholder
- Answer panel with: coverage status badge (green/yellow/red), prior auth indicator
- Source badges: payer name + policy number + link
- Props: `{ locationId?, payerContracts?: string[] }`

### 4C. Integration as Compliance tab

**Modify: `client/src/pages/app/Compliance.tsx`**

Add `'payer-policies'` tab, conditionally shown when location has `payer_contracts`:
```typescript
type Tab = '...' | 'payer-policies'
```

Pass `locationId` and `payer_contracts` to `PayerPolicyNavigator`.

---

## Phase 5: Data Ingestion Scripts

### 5A. CMS Medicare Ingestion (primary)

**New file: `server/scripts/ingest_cms_coverage.py`**

Bulk-imports all Medicare coverage data from CMS API:
1. Fetch all NCDs → ingest each with full clinical criteria
2. Fetch all final LCDs → ingest each with related articles, CPT codes, ICD-10 codes
3. Embed all ingested policies

Estimated: ~400 NCDs + ~2000 LCDs = comprehensive Medicare coverage. Rate limit: 10K req/sec (generous). Should complete in 10-15 minutes.

### 5B. Commercial Payer Seed (secondary)

**New file: `server/scripts/seed_commercial_payer_policies.py`**

Gemini research for top procedures across major commercial payers:
- Payers: Aetna, Blue Cross Blue Shield, UnitedHealthcare, Cigna
- Procedures: top 20-30 by volume (MRI brain, knee replacement, colonoscopy, cataract surgery, etc.)
- Rate-limited Gemini research + embed

---

## Implementation Order

```
Phase 1 (Schema)
    |
    ├── Phase 2 (Services)
    |     2A: cms_coverage_api.py       ← CMS API client + ingestion (primary data)
    |     2B: payer_policy_rag.py       ← RAG search
    |     2C: payer_policy_embedding_pipeline.py
    |     2D: payer_policy_research.py  ← Gemini fallback for commercial payers
    |
    ├── Phase 3 (API endpoints)         ← depends on Phase 2
    |     3A-C: routes + models
    |
    ├── Phase 4 (Frontend)              ← depends on Phase 3
    |     4A-C: API client + navigator + tab
    |
    └── Phase 5 (Data ingestion)        ← run after Phase 2
          5A: ingest_cms_coverage.py    ← bulk Medicare import (run first)
          5B: seed_commercial_payer_policies.py ← Gemini research for Aetna/UHC/etc.
```

---

## Key Files

| File | Action | Purpose |
|------|--------|---------|
| `server/alembic/versions/zm0n1o2p3q4r_...py` | New | Migration |
| `server/app/database.py` | Modify | init_db() additions |
| `server/app/core/services/cms_coverage_api.py` | New | CMS API client + Medicare ingestion |
| `server/app/core/services/payer_policy_rag.py` | New | Vector search over payer policies |
| `server/app/core/services/payer_policy_embedding_pipeline.py` | New | Embed payer policies |
| `server/app/core/services/payer_policy_research.py` | New | Gemini research for commercial payers |
| `server/app/core/routes/compliance.py` | Modify | 3 new endpoints |
| `server/app/core/models/compliance.py` | Modify | PayerPolicyResponse model |
| `server/scripts/ingest_cms_coverage.py` | New | Bulk Medicare import from CMS API |
| `server/scripts/seed_commercial_payer_policies.py` | New | Gemini research for Aetna/UHC/etc. |
| `client/src/api/compliance.ts` | Modify | API functions + types |
| `client/src/components/compliance/PayerPolicyNavigator.tsx` | New | Navigator widget |
| `client/src/pages/app/Compliance.tsx` | Modify | Tab integration |

**Reused without modification:**
- `server/app/core/services/embedding_service.py`
- `server/app/core/services/gemini_compliance.py` (reuse `_call_with_retry`)
- `server/app/core/services/compliance_rag.py` (pattern reference)
- `server/app/core/services/compliance_embedding_pipeline.py` (pattern reference)

---

## Verification

1. **Schema**: Run migration, verify tables exist with `\dt payer_*`
2. **Research**: Hit `POST /compliance/payer-policies/research` with `{payer_name: "Medicare", procedure: "Brain MRI"}`. Verify row created in `payer_medical_policies` + embedding in `payer_policy_embeddings`.
3. **RAG Q&A**: Hit `POST /compliance/payer-policies/ask` with `{question: "What does Medicare require to approve a brain MRI?"}`. Verify sourced answer with clinical criteria.
4. **List**: Hit `GET /compliance/payer-policies?payer_name=Medicare`. Verify filtered results.
5. **Frontend**: Navigate to Compliance page → Payer Policies tab → ask a question → verify answer with coverage badge and sources.
