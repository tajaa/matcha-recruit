# Behavioral Health Credential Requirements — California (Los Angeles)

Credential requirements for 360 Behavioral Health, resolved via the tiered credential template system.
Generated 2026-03-31 from HRIS sync of 55 behavioral health specialists.

---

## How Requirements Were Resolved

The system uses a 4-tier fallback:
1. **Company-specific templates** (none defined yet)
2. **System-wide templates** (none pre-existing for these roles in CA)
3. **Static fallback** (`credential_inference.py`) — matched psychiatrist, psychologist, NP, RN, OT, LCSW/LMFT/LPCC
4. **Gemini AI research** — researched CA/LA requirements for behavioral_health, licensed_counselor, therapist roles and saved as system-wide templates

---

## Requirements by Role

### Psychiatrist (7 employees)
**Resolution tier:** Static fallback
**Match pattern:** `\bpsychiatrist\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (MD/DO) | Yes | blocking | CA Medical Board license |
| DEA Registration | Yes | blocking | Schedule II-V prescribing |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Board Certification | Yes | blocking | ABPN (specialty-specific) |
| Malpractice Insurance | Yes | blocking | Required for clinical practice |
| Health Clearance | Yes | blocking | TB, immunizations |

### Psychologist (6 employees)
**Resolution tier:** Static fallback
**Match pattern:** `\bpsychologist\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (PsyD/PhD) | Yes | blocking | CA Board of Psychology license |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Malpractice Insurance | Yes | blocking | Required for clinical practice |
| Health Clearance | Yes | blocking | TB, immunizations |

### Psychiatric Nurse Practitioner (5 employees)
**Resolution tier:** Static fallback
**Match pattern:** `\b(nurse practitioner|aprn|crna|cnm|np)\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (PMHNP) | Yes | blocking | CA BRN license + NP furnishing number |
| DEA Registration | Yes | blocking | Prescriptive authority |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Board Certification | Yes | blocking | ANCC PMHNP-BC |
| Malpractice Insurance | Yes | blocking | Required for clinical practice |
| Health Clearance | Yes | blocking | TB, immunizations |

### Licensed Clinical Social Worker (7 employees)
**Resolution tier:** Static fallback
**Match pattern:** `\b(lcsw|licensed.*social worker)\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (LCSW) | Yes | blocking | CA BBS license |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Health Clearance | Yes | blocking | TB, immunizations |

### Licensed Marriage & Family Therapist (5 employees)
**Resolution tier:** Static fallback (same pattern as LCSW)
**Match pattern:** `\b(lmft|licensed.*therapist)\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (LMFT) | Yes | blocking | CA BBS license |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Health Clearance | Yes | blocking | TB, immunizations |

### Licensed Professional Clinical Counselor (4 employees)
**Resolution tier:** Static fallback (same pattern as LCSW)
**Match pattern:** `\b(lpc|licensed.*counselor)\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (LPCC) | Yes | blocking | CA BBS license |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Health Clearance | Yes | blocking | TB, immunizations |

### Psychiatric Registered Nurse (3 employees)
**Resolution tier:** Static fallback
**Match pattern:** `\b(registered nurse|rn)\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (RN) | Yes | blocking | CA BRN license |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Health Clearance | Yes | blocking | TB, immunizations |

### Occupational Therapist (3 employees)
**Resolution tier:** Static fallback
**Match pattern:** `\b(occupational therapist|ot)\b`

| Credential | Required | Priority | Notes |
|-----------|----------|----------|-------|
| Professional License (OTR) | Yes | blocking | CA OT Board license |
| NPI Verification | Yes | blocking | National Provider Identifier |
| Health Clearance | Yes | blocking | TB, immunizations |

---

## AI-Researched Templates (Gemini — CA/Los Angeles)

These were researched by Gemini and saved as system-wide templates in `credential_requirement_templates`.
They will be reused for any future employees in these role categories in CA.

### Behavioral Health Tech (matched: BCBA, Peer Support, CADC)
**Resolution tier:** Gemini AI research → saved as system-wide templates

| Credential | Required | Priority | Due Days | Confidence | Review Status |
|-----------|----------|----------|----------|------------|---------------|
| Fingerprint Clearance | Yes | blocking | 0 | 0.95 | auto_approved |
| BLS Certification | Yes | blocking | 0 | 0.95 | auto_approved |
| TB Test | Yes | blocking | 0 | 0.95 | auto_approved |
| Background Check | Yes | blocking | 0 | 0.90 | auto_approved |
| COVID-19 Vaccination | Yes | blocking | 0 | 0.90 | auto_approved |
| Drug Screening | Yes | blocking | 0 | 0.90 | auto_approved |
| OIG Exclusion Check | Yes | blocking | 0 | 0.90 | auto_approved |
| SAM Exclusion Check | Yes | blocking | 0 | 0.90 | auto_approved |
| Health Clearance (General) | Yes | blocking | 0 | 0.80 | pending |
| CPI Certification | Yes | blocking | 0 | 0.80 | pending |
| Influenza Vaccination | Yes | standard | 30 | 0.80 | pending |
| CPR Certification | No | standard | 30 | 0.70 | pending |
| Hepatitis B Vaccination | No | standard | 30 | 0.70 | pending |

### Licensed Counselor/Social Worker (matched: LCSW, LMFT, LPCC via AI tier)
**Resolution tier:** Gemini AI research → saved as system-wide templates
**Note:** Some employees in this category also matched via static fallback first.

| Credential | Required | Priority | Due Days | Confidence | Review Status |
|-----------|----------|----------|----------|------------|---------------|
| Professional License | Yes | blocking | 0 | 1.00 | auto_approved |
| Fingerprint Clearance | Yes | blocking | 0 | 0.95 | auto_approved |
| NPI Verification | Yes | blocking | 0 | 0.90 | auto_approved |
| BLS Certification | Yes | standard | 30 | 0.90 | auto_approved |
| TB Test | Yes | standard | 30 | 0.90 | auto_approved |
| Drug Screening | Yes | standard | 30 | 0.80 | pending |
| OIG Exclusion Check | Yes | blocking | 0 | 0.80 | pending |
| SAM Exclusion Check | Yes | blocking | 0 | 0.80 | pending |
| COVID-19 Vaccination | No | standard | 30 | 0.70 | pending |
| Malpractice Insurance | No | optional | 0 | 0.70 | pending |

### Therapist — PT/OT/SLP/RT (matched: Art Therapist, Music Therapist via AI tier)
**Resolution tier:** Gemini AI research → saved as system-wide templates

| Credential | Required | Priority | Due Days | Confidence | Review Status |
|-----------|----------|----------|----------|------------|---------------|
| Professional License | Yes | blocking | 0 | 1.00 | auto_approved |
| NPI Verification | Yes | blocking | 0 | 1.00 | auto_approved |
| Fingerprint Clearance | Yes | blocking | 0 | 0.90 | auto_approved |
| Background Check | Yes | blocking | 0 | 0.90 | auto_approved |
| BLS Certification | Yes | standard | 30 | 0.90 | auto_approved |
| TB Test | Yes | standard | 30 | 0.90 | auto_approved |
| Drug Screening | Yes | standard | 30 | 0.80 | pending |
| Health Clearance (General) | Yes | standard | 30 | 0.70 | pending |
| OIG Exclusion Check | Yes | blocking | 0 | 0.80 | pending |
| SAM Exclusion Check | Yes | blocking | 0 | 0.80 | pending |
| COVID-19 Vaccination | No | standard | 30 | 0.70 | pending |
| Malpractice Insurance | No | standard | 30 | 0.70 | pending |

---

## Non-Clinical (no requirements)

| Role | Count | Credentials |
|------|-------|-------------|
| Office Manager | 1 | None (non-clinical) |
| Billing Coordinator | 1 | None (non-clinical) |

---

## Summary

| Metric | Value |
|--------|-------|
| Total employees | 55 |
| Clinical employees | 53 |
| Non-clinical employees | 2 |
| Total credential requirements assigned | 244 |
| Avg requirements per clinical employee | 4.6 |
| Templates from static fallback | Psychiatrist, Psychologist, NP, RN, OT, LCSW/LMFT/LPCC |
| Templates from Gemini AI research | Behavioral Health Tech, Licensed Counselor, Therapist (CA/LA) |
| AI templates auto-approved | 22 |
| AI templates pending review | 13 |

## Review Status Legend

- **auto_approved** — High-confidence AI result (>0.85), immediately active
- **pending** — Lower-confidence AI result, needs admin review before enforcement
- **approved** — Manually reviewed and approved by admin
