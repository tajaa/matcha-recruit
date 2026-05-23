# Missing Implementations

Status review of planning docs created in the last week (Mar 25–Apr 1, 2026).

---

## POLICY_SUGGESTIONS_PLAN.md — ~95% Done

| Component | Status |
|-----------|--------|
| `policy_suggestion_service.py` (gap detection) | Done |
| `GET /policies/suggestions` | Done |
| `POST /policies/suggestions/dismiss` | Done |
| Frontend suggestions banner on Policies.tsx | Done |
| ER analysis pipeline hook (`policies_potentially_applicable`) | Done |
| **`POST /suggestions/generate-draft`** | **Not built** — `/policies/draft` serves the same purpose |

---

## CODE_REVIEW.md — 11 Issues Found, None Fixed

Code review of compliance-architecture-v2 branch. All issues are still open.

### HIGH (must fix)

| # | Issue | File |
|---|-------|------|
| 1 | Missing Alembic migration for `policy_suggestions_dismissed` | `database.py:748` |
| 2 | Race condition (TOCTOU) in `dismiss_suggestion()` | `policy_suggestion_service.py:172-196` |
| 3 | Duplicated RAG block with mangled variable names | `matcha_work.py ~1723, ~1971` |
| 4 | Jurisdiction ORM missing `country_code` column | `orm/jurisdiction.py` |
| 5 | JurisdictionRequirement ORM missing `key_definition_id` | `orm/requirement.py` |

### MEDIUM

| # | Issue | File |
|---|-------|------|
| 6 | Redundant line in migration helper | `s4t5u6v7w8x9...py:280` |
| 7 | Silent catch on frontend dismiss | `Policies.tsx:91` |
| 8 | Suggestions not refreshed after policy creation | `Policies.tsx:129` |
| 9 | Silent `except Exception: pass` on RAG failure | `matcha_work.py` |

### LOW

| # | Issue | File |
|---|-------|------|
| 10 | Dead `confidence` field always 0.0 | `policy_suggestion_service.py:28,165` |
| 11 | Unused `case_status` in SELECT; closed cases still contribute | `policy_suggestion_service.py:82` |

---

## ESCALATED_QUERIES_PLAN.md — Nothing Built

Low-confidence Matcha Work queries → client dashboard escalation. All 9 steps unbuilt.

| Step | What | Status |
|------|------|--------|
| 1 | DB migration (`mw_escalated_queries` table) | Not started |
| 2 | Escalation service (`escalation_service.py`) | Not started |
| 3 | Wire into matcha_work.py message flow | Not started |
| 4 | Dashboard stats integration | Not started |
| 5 | Escalation API endpoints (list/detail/resolve/dismiss) | Not started |
| 6 | Frontend types + API client | Not started |
| 7 | Dashboard stat card + PendingActions | Not started |
| 8 | Escalated Queries page (`EscalatedQueries.tsx`) | Not started |
| 9 | Route + sidebar nav entry | Not started |

---

## COMPLIANCE_IMPLEMENTATION_PLAN.md — Nothing Built

Three-phase plan for international compliance architecture. All phases unbuilt.

### Phase 1: Schema Foundation

| Item | Status |
|------|--------|
| ORM models for `regulation_key_definitions`, history, alerts | Not started |
| Enum updates (`national`, `province`, `region`) | Not started |
| Migration: `applicable_countries` column, seed ~50 intl keys, national jurisdictions, precedence rules, widen `current_value`, fix London data, backfill `key_definition_id` | Not started |
| Registry update with `_INTERNATIONAL_REGULATION_KEYS` | Not started |

### Phase 2: Runtime Safety

| Item | Status |
|------|--------|
| CTE country_code safety in `resolve_jurisdiction_stack()` | Not started |
| Country-aware gap detection in `get_missing_regulations()` | Not started |
| Country-filtered context in `jurisdiction_context.py` | Not started |
| Ingest key linking validation in `ingest_research_md.py` | Not started |

### Phase 3: Data Ingest

| Item | Status |
|------|--------|
| Auto-link parent for international jurisdictions | Not started |
| Ingest Mexico City (58 requirements) | Not started |
| Ingest NYC life sciences (11 requirements) | Not started |
| Ingest Boston life sciences (8 requirements) | Not started |

### Deferred (explicitly out of scope)

- US key normalization (1,668 legacy keys → 353 canonical)
- Admin cherry-pick endpoint
- Admin coverage dashboard country filter
- `_filter_with_preemption()` non-US guard

---

## INTERNATIONAL_COMPLIANCE_ARCHITECTURE.md — Reference Doc

Architecture/design document. No direct implementation items beyond what's in COMPLIANCE_IMPLEMENTATION_PLAN.md above. Documents the data model, hierarchy design, key definitions, and precedence rules. Tracks same checklist — all items unchecked.

---

## POLICY_EXPANSION_PLAN.md — Nothing Built

Expands policy registry from 483 → ~750+ keys. 8 phases, all unbuilt.

| Phase | What | New Keys | Status |
|-------|------|----------|--------|
| 1 | Tier 1: FDA lifecycle, device lifecycle, QMS, cybersecurity, reimbursement/VBC, environmental, supply chain | ~65 | Not started |
| 2 | Penalty/risk fields on `regulation_key_definitions` | 0 (schema) | Not started |
| 3 | Entity-type backfill (`applicable_entity_types`) | 0 (data) | Not started |
| 4 | Tier 2: International frameworks (EU MDR, intl drug regulatory, intl data protection) | ~25 | Not started |
| 5 | Pending regulations pipeline (legislation → requirement promotion) | 0 (schema) | Not started |
| 6 | Cross-reference dependency graph (`key_dependencies` table) | 0 (schema) | Not started |
| 7 | Audit & attestation workflow fields on `jurisdiction_requirements` | 0 (schema) | Not started |
| 8 | Sparse metadata backfill (~180 keys missing agency/description) | 0 (data) | Not started |

---

## PROJECT_TYPES_DESIGN.md — Partially Built

Project types for Matcha Work right panel.

| Type | Status |
|------|--------|
| General / Research | Done (existing) |
| Presentation | Done (PresentationPanel exists) |
| **Recruiting / Job Posting** | **Not started** — pipeline UI (posting/candidates/interviews/shortlist tabs), `project_type` column, `project_data` JSONB, type picker on creation |
| Policy / Handbook | Not started (marked future in doc) |
| Onboarding Plan | Not started (marked future in doc) |

---

## BEHAVIORAL_HEALTH_CREDENTIAL_REQUIREMENTS.md — Reference Doc

Documents credential requirements resolved for 360 Behavioral Health (55 employees, CA/LA). This is output/documentation of the existing credential template system working correctly — no missing implementations.

---

## COMPETITIVE_ANALYSIS.md — Reference Doc

Market positioning analysis. No implementation items.

---

## POLICY_REGISTRY.md — Reference Doc

Registry of all 483 policy keys. Reference documentation, not an implementation plan.

---

## HR_FEATURES_GAP_ANALYSIS.md — Almost Nothing Built

### Major Features

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | Approval Workflows Engine | Not started | Multi-step sign-off chains, auto-routing, delegation |
| 2 | Manager Self-Service Dashboard | Not started | Team roster, PTO calendar, pending approvals |
| 3 | Time & Attendance Tracking | Not started | Clock in/out, timesheets, overtime alerts, break compliance |
| 4 | Continuous Feedback & 1:1 Tracking | Not started | 1:1 notes, peer kudos, goal/OKR tracking |
| 5 | Compensation Bands & Pay Equity | Not started | Pay bands, equity analysis, compa-ratio |
| 6 | HR Ticketing / Employee Request System | Not started | Employee request forms, SLA tracking, knowledge base |
| 7 | Org Chart & Reporting Structure | Partial | `manager_id` exists on employee model + 2 migrations, but no UI, no span of control, no visualization |
| 8 | Benefits Open Enrollment | Not started | COBRA exists but no enrollment portal |

### Quick Wins (all unbuilt)

- Team PTO calendar view
- Employee directory with search
- Announcement board
- Document vault (beyond credentials)
- Birthday/anniversary notifications
- Bulk status change

---

## OPS_AGENT_FEATURES.md — Nothing Built

### MVP Features

| Feature | Status |
|---------|--------|
| Invoice/Receipt Processing | Not started |
| Daily Sales Digest (Toast API) | Not started |
| Checklist Engine | Not started |

### Broader Ops Features (all unbuilt)

- Inventory / par level monitoring
- Waste tracking & analysis
- POS integrations (Toast, Square, Clover)
- Shift gap detection / scheduling
- Vendor / procurement management
- Work order management
- P&L variance analysis
- Cash flow forecasting
