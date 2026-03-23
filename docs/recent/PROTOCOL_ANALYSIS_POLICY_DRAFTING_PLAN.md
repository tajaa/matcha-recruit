# Protocol Gap Analysis + Policy Drafting Features

## Context
Two new features that leverage the existing compliance requirements database and Gemini integration:

1. **Protocol Gap Analysis** — User pastes a study design or operational protocol, system cross-references it against applicable regulatory requirements and flags what's missing. This is a comparison between text input and `jurisdiction_requirements`/`compliance_requirements` data.

2. **Policy & Procedure Drafting** — Given a topic and jurisdiction, generate a draft institutional policy with regulatory citations. This is largely built already via `policy_draft_service.py` — needs an endpoint that accepts freeform topic + jurisdiction and returns a draft.

## What Already Exists (reuse heavily)

| Component | File | What it does |
|-----------|------|-------------|
| Requirements DB | `jurisdiction_requirements` table | Master regulatory data with title, description, category, citations, source_url |
| Requirements search | `compliance_service.py` → `search_company_requirements()` | Full-text search across requirements |
| Policy generation | `policy_draft_service.py` | Gemini-based policy drafting from requirements + industry context |
| Policy types | `policy_draft_service.py:27-84` | 40+ policy types mapped to compliance categories (including healthcare) |
| Handbook gap analysis | `handbook_service.py` → `compute_coverage()` | Gap detection: required sections vs authored sections |
| Company context | `ai_chat.py` → `build_company_context()` | Fetches company profile, locations, requirements for AI prompts |
| SSE streaming | `compliance_service.py` → `run_compliance_check_stream()` | Pattern for long-running streaming responses |

## Feature 1: Protocol Gap Analysis

### Endpoint: `POST /compliance/protocol-analysis`

**Input:**
```json
{
  "protocol_text": "Study Design: Phase II randomized...",
  "location_id": "uuid (optional — narrows jurisdiction)",
  "categories": ["clinical_trials", "research_consent"] // optional filter
}
```

**Logic:**
1. Fetch applicable requirements for the company (by location/industry, or all if no location specified)
2. Build a Gemini prompt: "Here is a protocol document. Here are the regulatory requirements. For each requirement, determine if the protocol addresses it, partially addresses it, or doesn't address it."
3. Stream the response (SSE) since this may take 10-20 seconds

**Output:**
```json
{
  "covered": [
    { "requirement_key": "irb_review", "title": "IRB Review", "status": "covered",
      "evidence": "Section 3.2 references IRB approval" }
  ],
  "gaps": [
    { "requirement_key": "informed_consent", "title": "Informed Consent",
      "status": "missing", "guidance": "Protocol does not address consent procedures..." }
  ],
  "partial": [
    { "requirement_key": "adverse_event_reporting", "title": "Adverse Event Reporting",
      "status": "partial", "evidence": "Mentions AE tracking but missing FDA reporting timeline" }
  ],
  "summary": "Protocol covers 12 of 18 applicable requirements. 3 critical gaps identified."
}
```

**Implementation:**
- New: `server/app/core/services/protocol_analysis_service.py` (~200 lines)
  - `analyze_protocol(protocol_text, requirements) -> ProtocolAnalysisResult`
  - Gemini prompt with structured JSON output
  - Validate/parse response
- Add route to: `server/app/core/routes/compliance.py`
  - SSE streaming endpoint following existing `run_compliance_check_stream()` pattern
- Reuse: `get_location_requirements()` from `compliance_service.py` to fetch applicable reqs
- Reuse: `build_company_context()` pattern from `ai_chat.py` for company context

### Frontend
- New component or page section where user pastes protocol text
- "Analyze" button triggers SSE stream
- Results render as a table: covered (green), partial (amber), gaps (red)
- Each row shows requirement title, status, and evidence/guidance text

## Feature 2: Policy & Procedure Drafting

### Endpoint: `POST /policies/draft`

**Input:**
```json
{
  "topic": "Bloodborne Pathogen Exposure Control",
  "jurisdiction": "California",
  "location_id": "uuid (optional)",
  "industry_context": "oncology clinic" // optional
}
```

**Logic:**
1. Fetch requirements matching the topic's compliance category + jurisdiction
2. Use existing `policy_draft_service.py` pattern — build Gemini prompt with requirements as context
3. Generate policy with: purpose, scope, definitions, procedures, responsibilities, citations, review schedule
4. Return structured draft with citations linked to actual requirement records

**Output:**
```json
{
  "title": "Bloodborne Pathogen Exposure Control Plan",
  "content": "## Purpose\n\nThis policy establishes...",
  "citations": [
    { "requirement_key": "bloodborne_pathogens", "title": "OSHA BBP Standard (29 CFR 1910.1030)",
      "source_url": "https://..." }
  ],
  "applicable_jurisdictions": ["Federal", "California"],
  "category": "infection_control"
}
```

**Implementation:**
- Extend: `server/app/core/services/policy_draft_service.py`
  - New function: `draft_policy_from_topic(topic, jurisdiction, requirements, industry) -> PolicyDraft`
  - Gemini prompt: "Draft an institutional policy for {topic} in {jurisdiction}. Use these regulatory requirements as your source of truth: {requirements}. Include citations."
- Add route to: `server/app/core/routes/policies.py`
  - `POST /policies/draft` — accepts topic + jurisdiction, returns draft
- Reuse: `get_policy_types_for_company()` to match topic to policy type
- Reuse: requirement fetch logic from `compliance_service.py`

### Frontend
- "Draft Policy" button/modal in Policies page
- Input: topic field (freeform or dropdown from policy types), jurisdiction selector
- Output: rendered markdown policy with highlighted citations
- "Save as Draft" button to create a policy record from the generated content

## Files to modify

| Action | File |
|--------|------|
| New | `server/app/core/services/protocol_analysis_service.py` |
| Modify | `server/app/core/routes/compliance.py` — add `/protocol-analysis` endpoint |
| Modify | `server/app/core/services/policy_draft_service.py` — add `draft_policy_from_topic()` |
| Modify | `server/app/core/routes/policies.py` — add `/policies/draft` endpoint |

## Verification
- Protocol analysis: paste a sample clinical protocol, verify requirements are matched/flagged
- Policy drafting: request "HIPAA Privacy" for "California", verify draft includes Cal. Civil Code citations
- Both: verify Gemini responses parse correctly, handle edge cases (empty requirements, no matches)
