# Healthcare Specialty Subcategories (Oncology) — Implementation Plan

## Context

Healthcare companies currently get all healthcare-specific compliance policies (HIPAA, bloodborne pathogens, clinical safety, etc.), but there's no way to distinguish between an oncology practice and a behavioral health practice. An oncology clinic needs radiation safety, chemotherapy handling, and tumor registry requirements that are irrelevant to behavioral health — and vice versa.

**Goal:** Add hierarchical industry subcategories so oncology practices get both general healthcare policies AND oncology-specific policies, while other healthcare companies only get general healthcare. Companies select specialties in their business profile settings (client admin users). Starting with oncology as the first specialty — the pattern should be extensible to future specialties (behavioral health, dental, etc.).

**Mechanism:** `applicable_industries` tags use colon-delimited hierarchy: `["healthcare"]` for general, `["healthcare:oncology"]` for oncology-specific. An oncology company matches both via prefix matching.

---

## Step 1. Database: Add `healthcare_specialties` column to companies

- [x] **New migration:** `server/alembic/versions/zc_add_healthcare_specialties.py`
- [x] **Update:** `server/app/database.py` init_db() DDL

```sql
ALTER TABLE companies ADD COLUMN IF NOT EXISTS healthcare_specialties TEXT[];
```

Stores `["oncology"]` etc. Only meaningful when `industry` resolves to `healthcare`. Multiple specialties allowed (e.g., a hospital could have `["oncology", "behavioral_health"]`).

---

## Step 2. Backend model: Add to CompanyUpdate

- [x] `server/app/matcha/models/company.py` — Add `healthcare_specialties: Optional[list[str]] = None` to `CompanyCreate`, `CompanyUpdate`, and `CompanyResponse`
- [x] `server/app/matcha/routes/companies.py` — Add `"healthcare_specialties"` to the `updatable` list with `$N::text[]` cast for TEXT[] handling

---

## Step 3. Backend: Hierarchical industry matching in compliance_service.py

**File:** `server/app/core/services/compliance_service.py`

- [x] **3a.** New helper `_get_company_industry_tags(conn, company_id)` — returns `{"healthcare", "healthcare:oncology"}` for oncology companies, `{"healthcare"}` for plain healthcare, `{"retail"}` for retail. Keep existing `_get_company_canonical_industry()` alongside.

- [x] **3b.** Update `_requirement_applicable_industries()` (line 189) — pass through colon-delimited tags as-is when they contain `:` instead of collapsing through `_resolve_industry()`.

- [x] **3c.** Update `_filter_requirements_for_company()` (line 1762) — replace flat `company_industry in industries` with set intersection matching against company tags.

  Key matching logic:
  - `{"healthcare:oncology"} & {"healthcare", "healthcare:oncology"}` → matches (oncology company gets oncology reqs)
  - `{"healthcare"} & {"healthcare", "healthcare:oncology"}` → matches (oncology company gets general healthcare reqs)
  - `{"healthcare:oncology"} & {"healthcare"}` → does NOT match (plain healthcare company skips oncology reqs)

- [x] **3d.** Add `ONCOLOGY_CATEGORIES` constant (after `HEALTHCARE_CATEGORIES` line 80):
  - `radiation_safety`
  - `chemotherapy_handling`
  - `tumor_registry`
  - `oncology_clinical_trials`
  - `oncology_patient_rights`

- [x] **3e.** Add oncology research context in `_INDUSTRY_RESEARCH_CONTEXT` (NRC 10 CFR 35, USP <800>, OSHA chemo limits, tumor registry mandates, clinical trial regs, oncology patient rights)

- [x] **3f.** Add `_ONCOLOGY_TEXT_MARKERS` tuple + `_looks_oncology_specific()` for fallback inference on untagged requirements

- [x] **3g.** New `_research_oncology_requirements_for_jurisdiction()` — follows `_research_healthcare_requirements_for_jurisdiction()` pattern exactly. Iterates `ONCOLOGY_CATEGORIES`, auto-tags with `["healthcare:oncology"]`.

---

## Step 4. Backend: Oncology policy types in policy_draft_service.py

**File:** `server/app/core/services/policy_draft_service.py`

- [x] **4a.** Add 5 oncology policy types to `POLICY_TYPES` list (all with `"industries": ["healthcare:oncology"]`):
  - Radiation Safety Program
  - Chemotherapy and Hazardous Drug Handling
  - Tumor Registry Reporting
  - Clinical Trials Compliance
  - Oncology Patient Rights

- [x] **4b.** Update `get_policy_types_for_company()` (line 96) — fetch `healthcare_specialties` alongside `industry`, build tag set, use set intersection for matching

- [x] **4c.** Add oncology prompt context in `_INDUSTRY_POLICY_CONTEXT`

---

## Step 5. Backend: Gemini auto-tagging for oncology

- [x] `server/app/core/services/gemini_compliance.py` (line 293) — Add `_ONCOLOGY_CATEGORIES` set and auto-tag block: if category is in oncology set, tag with `["healthcare:oncology"]`

---

## Step 6. Backend: Oncology research Celery task

- [x] **New file:** `server/app/workers/tasks/oncology_research.py` — follows `healthcare_research.py` exactly (asyncio.run wrapper, progress to `admin:oncology_research`, calls `_research_oncology_requirements_for_jurisdiction()`)
- [x] Register in `server/app/workers/tasks/__init__.py`
- [x] Wire into `server/app/core/routes/admin.py` jurisdiction research SSE — after healthcare research, check for missing oncology categories and queue/run oncology research

---

## Step 7. Frontend: CompanyProfile.tsx — Specialty selector

**File:** `client/src/pages/CompanyProfile.tsx`

- [x] **7a.** Add `HEALTHCARE_SPECIALTIES` constant and `healthcareSpecialties` state
- [x] **7b.** Conditional checkbox group after Industry dropdown — only visible when `industry === 'Healthcare'`
- [x] **7c.** Update `handleSave` — include `healthcare_specialties` in PATCH body, clear to `[]` when industry changes away from Healthcare
- [x] **7d.** Update `CompanyData` interface — add `healthcare_specialties: string[] | null`
- [x] **7e.** Load existing specialties in fetch handler

---

## File Summary

| File | Action |
|------|--------|
| `server/alembic/versions/zc_add_healthcare_specialties.py` | **New** — migration |
| `server/app/database.py` | Modify — init_db() DDL |
| `server/app/matcha/models/company.py` | Modify — add `healthcare_specialties` field |
| `server/app/matcha/routes/companies.py` | Modify — handle TEXT[] in PATCH |
| `server/app/core/services/compliance_service.py` | Modify — hierarchical matching, oncology categories, research function |
| `server/app/core/services/policy_draft_service.py` | Modify — oncology policy types, tag matching |
| `server/app/core/services/gemini_compliance.py` | Modify — oncology auto-tagging |
| `server/app/workers/tasks/oncology_research.py` | **New** — Celery task |
| `server/app/workers/tasks/__init__.py` | Modify — register new task |
| `server/app/core/routes/admin.py` | Modify — wire oncology research into SSE |
| `client/src/pages/CompanyProfile.tsx` | Modify — specialty selector |

---

## Verification

1. Set company industry to "Healthcare" in CompanyProfile → specialty checkboxes appear → select "Oncology" → save
2. Verify `healthcare_specialties = ["oncology"]` stored in DB
3. Check `GET /companies/{id}/policy-types` → returns general + healthcare + oncology policy types
4. Check compliance sync for oncology company → gets general + healthcare + oncology requirements
5. Check compliance sync for plain healthcare company → gets general + healthcare only (no oncology)
6. Check compliance sync for retail company → gets general only (no healthcare, no oncology)
7. Trigger oncology research Celery task for a jurisdiction → requirements saved with `applicable_industries=["healthcare:oncology"]`
8. Change company industry away from Healthcare → specialty selector disappears, specialties cleared on save
