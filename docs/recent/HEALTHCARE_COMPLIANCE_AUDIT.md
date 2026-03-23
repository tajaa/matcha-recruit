# Healthcare Compliance Gap Analysis

Audit of Matcha Recruit backend against the 5 core healthcare/biotech compliance challenges.
Date: 2026-03-21

---

## Challenge 1: Regulatory Complexity & Fragmentation

**Status: STRONG**

### What We Have
- 229 regulations across 40 compliance categories, 30+ healthcare-specific
- 8 healthcare categories (HIPAA Privacy, Billing Integrity, Clinical Safety, Workforce, Corporate Integrity, Research Consent, State Licensing, Emergency Prep)
- 5 oncology categories, 17 medical compliance categories
- Multi-level jurisdiction engine (federal/state/local) with preemption rules (`orm/jurisdiction.py`)
- FDA, CMS, HHS OCR, OIG, DOJ, Joint Commission, CLIA coverage
- Industry-specific filtering via `healthcare_specialties` and `applicable_industries` JSONB
- State variance tracking (High/Moderate/Low/None) per regulation

### Key Files
- `server/app/core/compliance_registry.py` — 229 regulations
- `server/app/orm/jurisdiction.py` — preemption logic
- `server/app/core/services/compliance_service.py` — check engine

### Gaps
- **OIG Exclusion Screening (LEIE)** — No integration with OIG's List of Excluded Individuals/Entities. Federal requirement for all healthcare employers.
- **Stark Law / Anti-Kickback Automation** — Category exists but no active monitoring of physician relationships, referrals, or compensation arrangements.
- **State Medical Board License Verification** — No automated lookup against individual state medical board APIs. No license type tracking (MD, DO, NP, PA, RN).
- **CMS Facility Accreditation Status** — No Conditions of Participation tracking, no automated CMS facility lookup, no survey readiness checks.
- **Payer Contract Management** — Category exists but no contract terms, rate tracking, or expiration alerts.

---

## Challenge 2: Siloed, Manual Compliance Processes

**Status: STRONG**

### What We Have
- Scheduled compliance checks every 7 days via Celery workers (`workers/tasks/compliance_checks.py`)
- 3-tier data sourcing: structured → repository → Gemini AI research
- Automatic drift detection with material change thresholds
- Policy creation, versioning, category tagging, signature workflows with email notifications
- Incident reporting with AI-powered categorization, severity assessment, root cause analysis
- Precedent matching (7-dimension similarity scoring)
- Policy-to-incident mapping (links incidents to violated policies)
- Compliance alert system (critical, warning, material change, upcoming legislation)

### Key Files
- `server/app/core/services/compliance_service.py` — check engine
- `server/app/core/services/policy_service.py` — policy management
- `server/app/matcha/routes/ir_incidents.py` — incident framework
- `server/app/matcha/services/ir_analysis.py` — AI analysis

### Gaps
- **Policy Enforcement Verification** — Policies are signed but no mechanism to verify they're being followed. No automated enforcement triggers (e.g., "unsigned after 30 days → flag manager").
- **Cross-System Workflow Triggers** — No automation hooks between compliance, HR, and payroll (e.g., "new hire → auto-initiate credentialing").
- **Real-Time Compliance Validation** — No blocking/warning when a non-compliant action is about to happen (e.g., payroll below minimum wage).

---

## Challenge 3: Cultural Resistance & Executive Buy-In

**Status: MODERATE**

### What We Have
- Risk scoring (0-100) across 5 dimensions with configurable weights
- Monte Carlo simulation (10,000 iterations) for loss exposure modeling
- Value-at-Risk (VaR) at 95% and 99% confidence, Conditional VaR (CVaR)
- Cost-of-risk in dollar terms per dimension (wage violations, ER litigation, OSHA penalties)
- Industry benchmarking via NAICS codes
- Anomaly detection (z-score based) on time-series risk data

### Key Files
- `server/app/matcha/services/risk_assessment_service.py` — 5-dimension scoring
- `server/app/matcha/services/monte_carlo_service.py` — simulations
- `server/app/matcha/services/benchmark_service.py` — peer comparison
- `server/app/matcha/services/anomaly_detection_service.py` — trend breaks

### Gaps
- **ROI Calculator** — No "compliance software cost vs risk exposure reduction" calculation. No payback period analysis.
- **C-Suite Dashboard** — No executive-optimized view. No compliance roadmap with milestones. No "days to full HIPAA readiness" projection.
- **Cost-of-Risk Accuracy** — Estimates use simplified models (no OCR penalty history lookup, no actuarial data for incident costs).
- **Compliance ROI Tracking** — No continuous measurement of avoided costs or "months since last compliance incident."

---

## Challenge 4: Cybersecurity & Data Governance

**Status: SOLID FOUNDATION**

### What We Have
- Fernet encryption at rest (`secret_crypto.py`)
- Medical credential field encryption — license, NPI, DEA, malpractice numbers (`credential_crypto.py`)
- Row-level security (RLS) on PostgreSQL with tenant isolation
- RBAC with JWT auth, separate chat JWT secret
- Audit logging: IR incidents (user/action/IP), policy changes (field-level), structured data operations
- SSL/TLS database connections configurable
- S3 storage with private credentials bucket

### Key Files
- `server/app/core/services/secret_crypto.py` — encryption
- `server/app/core/services/credential_crypto.py` — medical credential encryption
- `server/app/core/dependencies.py` — auth/RBAC
- `server/app/core/services/structured_data/audit.py` — audit logging

### Gaps
- **HIPAA Breach Notification Workflow** — No 60-day discovery/notification process, no HHS breach report generation, no affected individuals tracking.
- **BAA Tracking** — No Business Associate Agreement management. Critical since we're a BA for healthcare clients.
- **Session Security** — No session timeout enforcement, no MFA, no account lockout after failed attempts.
- **Audit Trail Completeness** — Logs aren't append-only/immutable. No centralized admin action log. No retention management.
- **Data Classification** — No PII/PHI/PSI labeling. No data retention policies. No secure deletion verification.

---

## Challenge 5: Third-Party & Supply Chain Risk

**Status: MINIMAL**

### What We Have
- Broker portal with onboarding, invite workflows, feature preconfiguration
- Google Workspace integration for credential provisioning
- Stripe billing integration

### Key Files
- `server/app/matcha/routes/brokers.py` — broker management
- `server/app/matcha/services/google_workspace_service.py` — GWS integration

### Gaps
- **Vendor Risk Assessment** — No vendor questionnaire, risk rating, or continuous monitoring.
- **BAA Tracking for Sub-Processors** — No tracking of BAAs with vendors who handle PHI.
- **Contract/SLA Management** — No contract terms, renewal dates, or expiration alerts.
- **CRO/Subcontractor Monitoring** — No support for clinical research organization risk tracking.
- **Supplier Attestation Collection** — No SOC 2, HIPAA, ISO 27001 certificate tracking.

---

## Priority Gaps for Healthcare Go-to-Market

| Priority | Gap | Reason |
|----------|-----|--------|
| 1 | OIG Exclusion Screening | Federal requirement for all healthcare employers |
| 2 | HIPAA Breach Notification Workflow | Regulatory requirement (60-day rule) |
| 3 | BAA Framework | Required to sell to healthcare (we're a Business Associate) |
| 4 | State Medical Board License Verification | Core credentialing automation |
| 5 | Vendor Risk Assessment | Sub-processors need BAAs too |
| 6 | Executive ROI Dashboard | Overcomes buy-in resistance |
| 7 | Real-Time Compliance Validation | Prevents costly violations before they happen |
| 8 | Stark Law Safe Harbor Automation | Prevents legal exposure |

---

## Summary

| Challenge | Status | Score |
|-----------|--------|-------|
| 1. Regulatory Complexity | Strong | 7/10 |
| 2. Automated Compliance | Strong | 7/10 |
| 3. Executive Buy-In | Moderate | 5/10 |
| 4. Cybersecurity & Data Gov | Solid | 6/10 |
| 5. Third-Party Risk | Minimal | 2/10 |
