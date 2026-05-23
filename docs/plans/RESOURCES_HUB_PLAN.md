# Resources Hub — Landing Page Plan

> **Audience for this doc:** HR manager critique. Goal = pressure-test whether these resources are what HR pros actually search for, download, and trust.

---

## Context

Matcha-recruit landing currently has: Platform, Matcha Work, Consulting, Blog. Blog is the only educational surface. We want to convert the landing into a **general HR resource center** — a destination HR pros visit for free tools, templates, and compliance lookups, then convert to paid platform users.

Why now:
- Existing blog gets some SEO but no lead magnets — visitors leave with nothing.
- We already own valuable structured data (jurisdiction compliance, policy registry, 70+ jurisdiction markdown briefs) that is currently locked inside the paid product.
- HR pros search for templates + state-specific compliance answers constantly — high-intent traffic we are missing.

Outcome: a `/resources` hub that ranks for HR long-tail SEO, captures emails via gated downloads, and funnels qualified leads into the platform.

---

## Resource Tab — Proposed Structure

New top-level nav item: **Resources** (between Consulting and Blog in `MarketingNav.tsx`).

Hub landing page `/resources` with categorized cards. Each card links to a sub-route.

### 1. Templates (gated downloads)

Free downloadable docs in exchange for email. The bread and butter of HR lead-gen.

| Template | Format | Why HR cares |
|---|---|---|
| Offer letter | DOCX + PDF | Most-searched HR template online |
| Job description library (50+ roles) | DOCX | Covers nurse, line cook, sales rep, etc. |
| Employee handbook starter | DOCX | State-aware via jurisdiction data |
| PIP (Performance Improvement Plan) | DOCX | High-stakes, HR pros want a safe template |
| Onboarding checklist (30/60/90) | PDF | Universal need |
| Termination checklist | PDF | Legal landmine — they want a guide |
| I-9 / W-4 packet wrapper | PDF | Compliance hand-holding |
| Interview scorecard | DOCX | Reduces bias claims |
| PTO policy template | DOCX | State-specific variants |
| Workplace investigation report | DOCX | Pulls from ER Copilot patterns |

**Gating:** First download free no-email; second+ requires email. Or always-gated with "instant access" framing. HR manager input needed here.

### 2. State Compliance Guides

One page per US state + key cities. Pulls directly from existing `jurisdictions` + `jurisdiction_requirements` tables — near-zero new content cost.

Routes: `/resources/compliance/california`, `/resources/compliance/new-york-city`, etc.

Each guide:
- Required posters
- Min wage + tipped wage
- PTO/sick leave law
- Final paycheck rules
- Background check restrictions
- Pay transparency law
- Recent law changes (last 12 months)
- "Get full compliance scan for your business" CTA → signup

**SEO play:** every state page targets "[state] HR compliance guide" — high commercial intent.

### 3. Calculators (interactive lead magnets)

Lightweight client-side tools. Email gate to "save/export results."

- **PTO accrual calculator** — by state, by tenure, by hours/year
- **Salary benchmark lookup** — by role + zip (pulls comp data we already have)
- **Turnover cost calculator** — inputs avg salary, # leavers → $ cost
- **Overtime calculator** — FLSA-compliant by state
- **Total comp calculator** — base + bonus + benefits + equity
- **Workforce composition / EEO-1 readiness check**

### 4. Policy Library Preview

Surface 20–30 policy summaries from the policy registry as read-only cards. Title, summary, "applies in X states." Full policy + customization → signup.

Routes: `/resources/policies`, `/resources/policies/:slug`.

### 5. HR Glossary

Alphabetized terms: FLSA, ACA, FMLA, ADAAA, HIPAA, COBRA, EEOC, OSHA, etc. 200–500 word definitions. Pure SEO play — long-tail "what is FMLA" type queries.

Route: `/resources/glossary`, `/resources/glossary/:term`.

### 6. Guides (long-form, ungated)

Long-form how-tos. Uses existing blog infra (`BlogIndex`/`BlogPost` patterns) but separate index for "evergreen guide" framing.

Examples:
- "How to fire someone in California (legally)"
- "First 90 days of onboarding — week-by-week"
- "Building an employee handbook from scratch"
- "Conducting a workplace investigation"
- "Pay transparency laws by state (2026)"
- "Exit interview playbook"

### 7. Compliance Quiz / Self-Audit Tool

Interactive 10-question quiz → emailed PDF "compliance gap report." Strongest lead magnet on the list. Output keyed to user's state + headcount + industry.

Route: `/resources/audit`.

### 8. Webinars + Recorded Sessions (Phase 2)

Recorded sessions with HR pros, employment lawyers. Gated registration. Defer until we have content partners.

---

## Implementation Sketch

**Net-new files:**
- `client/src/pages/landing/ResourcesHub.tsx` — index page with cards
- `client/src/pages/landing/resources/Templates.tsx`
- `client/src/pages/landing/resources/StateCompliance.tsx` (dynamic by `:state`)
- `client/src/pages/landing/resources/Calculators.tsx` + per-calc components
- `client/src/pages/landing/resources/PolicyPreview.tsx`
- `client/src/pages/landing/resources/Glossary.tsx`
- `client/src/pages/landing/resources/Guides.tsx` (reuses blog patterns)
- `client/src/pages/landing/resources/ComplianceAudit.tsx`

**Files to modify:**
- `client/src/pages/landing/MarketingNav.tsx` (~line 1–160) — add Resources nav item
- `client/src/pages/landing/MarketingFooter.tsx` — add Resources column
- `client/src/App.tsx` (~lines 77–82) — register new routes

**Backend additions:**
- `server/app/core/routes/resources.py` (new) — public endpoints for:
  - `GET /api/public/jurisdictions/{slug}/summary` (state guide data)
  - `POST /api/public/lead-capture` (email + asset slug)
  - `POST /api/public/audit` (quiz submission → triggers PDF email)
- New table: `lead_captures(id, email, asset_slug, source, created_at, ip)`
- Reuse existing `compliance.py` API for jurisdiction data — no duplication.

**Existing leverage:**
- `client/src/api/compliance.ts` — `fetchJurisdictions()`, `fetchComplianceRequirements()` already exist
- Policy registry data already structured at `/admin/jurisdiction-data/policy/:id`
- Blog infra (`BlogIndex.tsx`, `BlogPost.tsx`) reusable for Guides

---

## Phasing

| Phase | Scope | Why this order |
|---|---|---|
| **P1** | Resources hub + State Compliance guides + Templates (5 docs) + Glossary | Highest SEO leverage, reuses existing data, fastest to ship |
| **P2** | Calculators (PTO, salary, turnover) + Compliance Audit quiz | Best lead magnets, requires more eng |
| **P3** | Policy library preview + remaining templates + Guides expansion | Content-heavy, needs sustained writing effort |
| **P4** | Webinars / partner content | Needs partnerships, lowest priority |

---

## Open Questions for HR Manager

1. **Which 5 templates would you actually download and use?** (we'll start with those)
2. **Gating philosophy** — always email-gate, or first-download-free?
3. **State guides — which states matter most for your customers?** (CA, NY, TX, FL likely top, but confirm)
4. **Compliance audit quiz** — what 10 questions surface the most useful gaps?
5. **What's missing from the list** that you search for and never find a good free resource for?
6. **Trust signals** — do we need an HR-pro byline / advisory board to make this credible vs. generic content farms?

---

## Verification

- Visit `/resources` — hub loads with all category cards
- Click "California" state guide — shows real compliance data from DB
- Submit email on a template download — entry appears in `lead_captures` table, email delivered
- Run PTO calculator — produces correct accrual numbers per CA + NY rules
- Submit compliance audit — receives PDF report via email within 60s
- SEO check: each state page has unique meta title, description, structured data
- Mobile: all routes render cleanly on iPhone width

---

## Out of Scope

- Paid course / certification content
- Community forum
- Live chat support on resource pages
- AI chatbot trained on HR Q&A (separate initiative)
