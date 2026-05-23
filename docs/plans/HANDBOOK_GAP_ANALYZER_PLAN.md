# Handbook Gap Analyzer — Free Lead Magnet

## Context

Acquisition gap: HR professionals have no easy on-ramp into the Free tier (`signup_source='resources_free'`). Current free hub is mostly passive content (state guides, glossary, calculators). Need a high-pull tool that:

1. Solves a problem HR pros normally pay an employment lawyer $2k–$5k for.
2. Reuses our existing compliance + handbook engine (cheap to build).
3. Forces a Free signup to unlock the value — but delivers enough teaser pre-signup to prove credibility.

**The product:** prospect uploads their current employee handbook PDF → we diff it against the legally-required clauses for their state(s) → return a "missing / stale / out-of-compliance" gap report. Top-line counts visible pre-signup; full clause-by-clause report gated behind Free signup; "fix these gaps" CTA upgrades them to Matcha-lite or Matcha.

**Why this works as a lead magnet:**
- HR's #1 chronic anxiety: outdated handbook = wrongful-termination exposure + state penalty risk.
- Currently requires manual review by employment counsel; nobody self-serves it.
- Output is a tangible, shareable artifact (PDF report) — viral surface inside HR teams.
- Maps cleanly to upsell: "we found 14 gaps → Matcha-lite generates the missing clauses for you."

## Product Surface

### Public landing — `/resources/handbook-gap-analyzer`
- Hero: "See what's missing from your employee handbook in 90 seconds."
- Drag-drop PDF upload (≤10MB, employee handbook only).
- State multi-select (required — gap depends on jurisdiction).
- Industry select (optional — sharpens detection of industry-specific clauses, e.g. healthcare HIPAA).
- "Analyze" button → redirects to `/resources/handbook-gap-analyzer/result/:reportId`.

### Result page (pre-signup teaser)
- Top tile: "We found **N gaps** across **M states**." Severity breakdown (Critical / Important / Recommended).
- Blurred clause-by-clause list with first 2 rows visible.
- Email-gate: "Enter email + create free account to see all N gaps + download PDF."
- Free signup form inline (uses existing `/auth/resources-signup` flow with `signup_source='resources_free'` + `resources_free_via='handbook_gap_analyzer'` for attribution).

### Result page (post-signup, full)
- Per-clause card: clause name, severity, jurisdiction citation, "what's missing" excerpt, "what good looks like" template snippet (truncated — full template gated to Matcha-lite).
- Download report as PDF (WeasyPrint, same path as `_render_project_pdf`).
- Persistent — accessible from `/resources` dashboard later as "My Handbook Audits".
- CTA banner: "Fix all 14 gaps automatically with Matcha-lite — $X/mo" → `/matcha-lite/checkout`.

## Implementation

### Backend

**New router** — `server/app/core/routes/handbook_gap_analyzer.py`:
- `POST /resources/handbook-gap-analyzer/analyze` (public, no auth)
  - Accepts: multipart PDF + `states: list[str]` + optional `industry`.
  - Stores PDF in S3 under `handbook-audits/{report_id}.pdf` (existing `storage.py`).
  - Inserts row in new `handbook_audit_reports` table — see schema below.
  - Dispatches `analyze_handbook_audit` Celery task.
  - Returns `{report_id, status: 'processing'}` — frontend polls.
- `GET /resources/handbook-gap-analyzer/report/{report_id}` (public for top-line counts; full payload requires JWT)
  - Anonymous caller: returns `{status, gap_counts: {critical, important, recommended}, total_states, sample_gaps: [first 2]}`.
  - Authed caller (matched `email` on report row OR signed-up Free user with that email): returns full `gaps: [...]` payload.
- `POST /resources/handbook-gap-analyzer/report/{report_id}/claim` — links anonymous report to a newly-created Free account by email.
- `GET /resources/handbook-gap-analyzer/report/{report_id}/pdf` — WeasyPrint render, authed.

**New worker** — `server/app/workers/tasks/handbook_audit.py`:
- `analyze_handbook_audit(report_id)`:
  1. Fetch PDF bytes from S3.
  2. Extract sections from uploaded PDF — pass PDF directly to Gemini multimodal (`gemini-2.0-flash` or current). Prompt: "Identify each policy section in this handbook. Return JSON: `[{section_title, content_excerpt, page_range}]`." Avoids adding a PDF lib dependency.
  3. For each scoped state, call `_fetch_state_requirements(states=[state], industry, scope_cities=[])` from `server/app/core/services/handbook_service.py:1398` to get the canonical required-topic set.
  4. Run gap detection: reuse `_find_missing_state_topics` (handbook_service.py:1632) and `_validate_required_state_coverage` (handbook_service.py:1652) with the **uploaded** sections as input rather than generated ones. May need a thin adapter wrapper since current callers assume generated section dicts.
  5. For each gap, ask Gemini one focused validation prompt: "Does this handbook cover {topic} for {state}? Section excerpts: {top-3 semantic matches from uploaded handbook}. Answer JSON: `{covered: bool, severity: critical|important|recommended, citation: str, what_good_looks_like: str}`." Use `compliance_rag.py` patterns for grounded retrieval if possible; otherwise plain Gemini call.
  6. Write results to `handbook_audit_reports.gaps_jsonb`, set `status='ready'`.
  7. Email the prospect (if Free account claimed): "Your handbook audit is ready — N gaps found." Reuse `core/services/email.py`.

**New table** — `handbook_audit_reports`:
```sql
CREATE TABLE handbook_audit_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT,                           -- captured at upload OR at claim
    user_id UUID REFERENCES users(id),    -- nullable; populated on claim
    states TEXT[] NOT NULL,
    industry TEXT,
    pdf_s3_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',  -- processing | ready | failed
    gap_counts JSONB,                     -- {critical: int, important: int, recommended: int}
    gaps_jsonb JSONB,                     -- full per-clause findings
    extracted_sections_jsonb JSONB,       -- cached PDF extraction
    error_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    pdf_render_s3_key TEXT
);
CREATE INDEX idx_handbook_audit_email ON handbook_audit_reports (email);
CREATE INDEX idx_handbook_audit_user ON handbook_audit_reports (user_id);
```
Alembic migration in `server/alembic/versions/`. Per CLAUDE.md: write the migration but **do not run** — user must execute against prod.

**Rate limit + abuse guard:**
- Anonymous `POST /analyze`: max 3 per IP per 24h (use existing rate-limit infra if present; otherwise simple Redis counter).
- PDF size cap 10MB enforced server-side.
- Reject non-PDF mimetypes.
- Strip metadata before storing.

### Frontend

**New page** — `client/src/pages/landing/HandbookGapAnalyzer.tsx`:
- Marketing landing wrapped in `MarketingNav` (`client/src/pages/landing/MarketingNav.tsx`) for top-of-funnel SEO.
- Add `{ to: '/handbook-gap-analyzer', label: 'Handbook Audit' }` to `NAV_LINKS` in MarketingNav (line 10).

**Upload component** — `client/src/components/resources-free/HandbookGapUploader.tsx`:
- React-dropzone or native input.
- State multi-select (reuse `HandbookStateSelector.tsx` patterns).
- Posts to `/api/resources/handbook-gap-analyzer/analyze`.
- Pushes to result route on response.

**Result page** — `client/src/pages/resources/HandbookGapResult.tsx`:
- Polls `GET /report/:id` every 2s while `status='processing'`.
- Renders `<HandbookGapTeaser>` for anonymous viewers (gap counts + 2 sample gaps + signup form).
- Renders `<HandbookGapFullReport>` for authed viewers with matching email.
- Both live under `client/src/components/resources-free/`.

**Free signup attribution** — `client/src/pages/auth/ResourcesSignup.tsx`:
- Read `?from=handbook_gap_analyzer&report_id=...` query params; pass through to signup payload as `resources_free_via` field. Backend writes to a new `companies.signup_via` TEXT column or to existing `signup_source` metadata. After signup, POST `/handbook-gap-analyzer/report/:id/claim` to link the report.

**Routes** — `client/src/App.tsx`:
- `/handbook-gap-analyzer` → public landing.
- `/handbook-gap-analyzer/result/:reportId` → result page (handles both anon + authed).

### Reuse Map (no new code where possible)

| Need | Existing piece | File |
|---|---|---|
| Jurisdiction-aware required-clause lookup | `_fetch_state_requirements` | `server/app/core/services/handbook_service.py:1398` |
| Gap detection algorithm | `_find_missing_state_topics`, `_validate_required_state_coverage` | `server/app/core/services/handbook_service.py:1632, 1652` |
| Gemini compliance grounding | `compliance_rag.py`, `gemini_compliance.py` | `server/app/core/services/` |
| S3 upload + signed URL | `storage.py` | `server/app/core/services/storage.py` |
| PDF render | WeasyPrint pattern in `_render_project_pdf` | `server/app/matcha/routes/matcha_work.py` |
| Free signup flow | `ResourcesSignup.tsx`, `signup_source='resources_free'` | `client/src/pages/auth/`, `server/app/core/routes/auth.py` |
| Marketing nav | `MarketingNav.tsx` | `client/src/pages/landing/` |
| Free-tier sidebar nav | `ResourcesFreeSidebar.tsx` | `client/src/components/resources-free/` |
| Upgrade CTA card | `UpgradeUpsellCard.tsx`, `UpgradePanel.tsx` | `client/src/components/`, `resources-free/` |

## Out of Scope

- **Auto-fix / generate replacement clauses** — that's the upgrade hook (Matcha-lite). Free tier only diagnoses, never fixes.
- **Federal-only handbooks** — must require ≥1 state. Federal-only review = future v2.
- **Editing uploaded PDFs** — read-only analysis. No annotation, no redline.
- **Indexing uploaded handbooks into pgvector** — separate concern from `HANDBOOK_RAG_PLAN.md` (which covers customer-generated handbooks). Audits are throwaway.
- **Multi-language handbooks** — English only at launch. Spanish later.
- **Full reuse of `handbook_freshness` worker** — that worker evaluates *generated* handbooks against a known section catalog. Audit flow is the inverse (uploaded sections → required catalog), so the gap-detection helpers are reusable but the worker harness is not.
- **CCPA / GDPR cookie banner work** — assume existing site policy covers PDF upload telemetry. Re-audit if Legal flags.

## Funnel Metrics to Wire

Instrument from day 1 — without these, can't tell if it's working:
- Landing page visit (segment by source).
- PDF upload submitted.
- Analysis completed (% completion).
- Anonymous teaser view (gap_counts revealed).
- Signup conversion from teaser → Free account.
- Full report viewed post-signup.
- Upgrade CTA clicked → Matcha-lite checkout.

Reuse existing analytics pattern in `client/src/api/analytics.ts` if present, else add minimal event POST to `core/routes/analytics.py`.

## Verification

1. **End-to-end happy path:**
   - Visit `/handbook-gap-analyzer` anonymous. Upload sample handbook PDF, select CA + NY, submit.
   - Polling resolves to `status='ready'` within 60s.
   - Teaser shows gap counts + 2 sample gaps.
   - Sign up via inline form → claim posts → full report renders.
   - Click "Download PDF" → WeasyPrint output downloads.
   - Click "Fix these gaps" → lands on `/matcha-lite/checkout`.

2. **Anonymous abuse:**
   - 4th upload from same IP within 24h returns 429.
   - Non-PDF upload (e.g. .docx) returns 400 with clear error.
   - 11MB PDF returns 413.

3. **Auth boundary:**
   - Hit `/report/{id}` unauthed → returns gap counts only.
   - Hit `/report/{id}` as different user (wrong email) → returns gap counts only (not full).
   - Hit `/report/{id}/pdf` unauthed → 401.

4. **Gap detection sanity:**
   - Hand-pick known-bad handbook (missing CA pregnancy disability leave clause). Confirm CA PDL appears in report as `severity='critical'`.
   - Hand-pick known-good handbook. Confirm gap count is low (≤2 trivial recommendations) — false-positive sanity check.

5. **Tests:**
   - Unit: gap-detection adapter wrapping `_validate_required_state_coverage` with mock uploaded sections.
   - Integration (manual, per CLAUDE.md DB rules): full pipeline from upload through claim — user runs against staging.
   - Existing handbook + compliance test suites must still pass.

## Open Questions (resolve before build)

- Pricing CTA target: send to Matcha-lite checkout direct, or to a "fix gaps" intermediate page that quotes per-gap fix cost? Recommend lite-checkout direct — fewer steps, higher conversion.
- Email capture timing: at upload (forces email before result) or at teaser-reveal (sees value first, then gives email)? Recommend teaser-first — better perceived value, lower bounce.
- Report retention: keep audit reports forever, or expire after 90d unless claimed by a Free account? Recommend 90d expiry for unclaimed; permanent for claimed.

---

# Companion Lead Magnets — Other Free-Tier Tool Candidates

Handbook Gap Analyzer above is the flagship. Listed below are six additional self-serve tools that follow the same recipe — high HR pain, existing Matcha capability does the heavy lifting, gated behind Free signup. Ranked by **(estimated pull) × (build ease)**, descending.

Use these as a portfolio: ship the flagship first, then 1–2 companions to widen the top of the funnel and give SEO a wider footprint.

## 1. Multi-State Posting Requirements Pack — *quick win, SEO bait*

**HR pain.** State and federal posting requirements change yearly; missing posters carry per-poster fines ($100–$10,000 depending on jurisdiction). HR teams chase printable PDFs across 50 state DOL websites annually.

**Product.** Form: select states + headcount → output: PDF pack with every required workplace poster, download links to canonical sources, Spanish versions where mandated, posting deadlines, and a printable cover sheet for the bulletin board.

**Build effort.** Days. Pure jurisdiction lookup against existing structured data (`server/app/workers/tasks/structured_data_fetch.py` already pulls federal/state regulator feeds; same data powers the existing state guides at `server/app/core/routes/resources.py:553` `list_state_guides`).

**Reuse.**
- `list_state_guides` (resources.py:553) — already returns state-keyed compliance content; extend with `posters` field.
- WeasyPrint render path for PDF assembly.
- `core/services/storage.py` for hosting poster PDFs in S3 + CloudFront (already used).

**Funnel hook.** Annual return visit (posters update yearly → email re-engagement). Strong SEO terms: "California workplace posters 2026", "all-in-one labor law poster". Low intent per visit but high volume.

**Gating.** Email capture before download; full pack delivered to email + accessible in Free dashboard.

**Risks.** Low — purely informational. Worth noting: avoid claiming the pack substitutes for paid all-in-one poster vendors (legal risk). Frame as "free reference for what's required" not "compliance guarantee".

---

## 2. Termination Risk Scorecard — *highest intent, moderate build*

**HR pain.** Every involuntary termination triggers wrongful-term anxiety. Current path: HR calls outside counsel ($350–$500/hr) or guesses. The decision happens in the moment under time pressure.

**Product.** Wizard form: protected-class status (age, race, gender, disability, pregnancy, religion, military, age 40+), recent protected activity (complaint filed, leave taken, accommodation requested, safety concern raised), comparator treatment, performance documentation status, jurisdiction → AI-generated risk score (low/moderate/high/critical) + required-doc checklist + retaliation-window flags.

**Build effort.** ~1.5 weeks. The pre-termination intelligence engine already exists for paid tiers (`server/app/matcha/services/` — referenced in CLAUDE.md as "9-dimension agentic risk assessment"). Surface a stripped-down 4-dimension version as a one-shot wizard: no employee record persistence, no docs uploaded, just guided Q&A → Gemini-grounded risk narrative.

**Reuse.**
- Pre-termination logic (existing paid-tier code).
- `gemini_compliance.py` for the jurisdiction-aware narrative generation.
- `compliance_rag.py` retrieval pattern for citing the controlling state whistleblower / retaliation statute.

**Funnel hook.** Highest-intent free user signature. HR person filling this out has an active fire — they convert to paid at higher rates than any other tool. Direct upgrade pitch: "Upgrade to Matcha-lite for full pre-termination workflow + counsel-ready memo + audit trail on every separation."

**Gating.** Top-line score visible pre-signup; full narrative + checklist + state citation gated behind Free signup. Cap at 3 scorecards/month per Free account to push toward paid tier.

**Risks.** Two:
- *Liability framing* — must be crystal-clear "not legal advice, doesn't replace counsel". Use existing disclaimer pattern in resources flow.
- *Cannibalization* — Matcha-lite paid tier doesn't currently include pre-termination intel (Platform-only). The Free scorecard is OK because it's one-shot and de-coupled from employee records; paid value is the workflow integration, not the calculation itself. Verify before launch.

---

## 3. OSHA Recordability Quick Check — *industrial niche, very fast build*

**HR pain.** Plant safety + HR teams in manufacturing, construction, healthcare constantly second-guess OSHA 300 recordability. Wrong call = OSHA citation OR over-reporting (drives up DART rate, raises insurance).

**Product.** Single-question wizard: incident facts (injury type, treatment received, days away, restricted duty, healthcare visit type) → recordable yes/no, with 29 CFR 1904 citation + reasoning.

**Build effort.** Days. Recordability logic already exists in IR incident pipeline (`server/app/matcha/routes/ir_incidents.py` — generates OSHA 300/300A logs). Extract the determination function as a public endpoint.

**Reuse.**
- IR recordability evaluator (already in incidents router).
- No new AI calls needed — pure rules engine. Renders fast, cheap to serve.

**Funnel hook.** Industrial / healthcare HR target. Repeat usage (every incident is a query). Hooks into upgrade: "Track every incident with full OSHA 300 log generation in Matcha-lite, $X/mo."

**Gating.** Anonymous use (no signup required) for the first 3 queries per IP / 24h; signup required after. Builds top-of-funnel via search ("is X OSHA recordable").

**Risks.** Low. Liability framing same as scorecard.

---

## 4. Multi-State New-Hire Checklist Generator — *moderate pull, very fast build*

**HR pain.** Onboarding employees in unfamiliar states means hunting for state-specific required forms (state W-4, new-hire reporting, paid family leave registrations, sick-leave accrual notices, sexual harassment training mandates). Distributed-workforce HR teams (post-COVID norm) get burned by missed state requirements regularly.

**Product.** Form: hire state + role + employer state → output: PDF checklist of every required form, posting, training, registration, and notice for that hire, with deadlines (e.g., "NY: provide written wage notice within 10 days of hire").

**Build effort.** ~1 week. Combines existing jurisdiction data with handbook generator's `_build_state_addendum_content` (handbook_service.py:1018) which already enumerates state-specific obligations.

**Reuse.**
- `_fetch_state_requirements` (handbook_service.py:1398).
- `_build_state_addendum_content` (handbook_service.py:1018) — already produces state-keyed obligation lists.
- Existing PDF render path.

**Funnel hook.** Repeat use (every new hire in a new state). Sticky for distributed-team HR. Upgrade pitch: "Run this automatically on every onboarding in Matcha-lite."

**Gating.** Email capture before PDF delivery; checklist downloadable + emailed.

**Risks.** Low.

---

## 5. Pay Transparency Compliance Checker — *trending pain, easy build*

**HR pain.** Pay-transparency laws are spreading fast (CO, NY, WA, CA, IL, MD, MN, OH, NJ in 2024–2026). Penalties up to $10,000/violation per posting. HR teams writing job postings have to remember which states require salary ranges, which require benefits summaries, and which require explicit anti-pay-history language.

**Product.** Paste a job posting + select target states → AI flags missing required disclosures per state, with quoted statute and remediation suggestion.

**Build effort.** ~1 week. Single Gemini call against jurisdiction lookup. No new infra.

**Reuse.**
- Jurisdiction data (state guides).
- `gemini_compliance.py` patterns for grounded analysis.

**Funnel hook.** Recruiting / TA professionals — adjacent persona to HR, expands top of funnel. Pay-transparency search volume is climbing rapidly. Upgrade pitch: "Built into job-description generator on Matcha-lite + Platform."

**Gating.** Email capture before showing detailed analysis; counts visible pre-signup.

**Risks.** Low.

---

## 6. Annual Compliance Calendar Generator — *retention play, moderate build*

**HR pain.** HR teams scramble at year-end to compile next year's compliance calendar (EEO-1 deadlines, OSHA 300A posting, ACA 1095-C, state pay-data reporting, harassment training renewals, I-9 reverifications, ERISA notices). Most use shared spreadsheets that drift.

**Product.** Form: states + headcount + applicable benefit plans (health, retirement) + industry → personalized 12-month calendar in PDF + ICS download.

**Build effort.** ~1 week. Data already exists in jurisdiction tables; calendar assembly is pure formatting.

**Reuse.**
- Existing structured compliance data feeds.
- WeasyPrint + new ICS export utility (small new code).

**Funnel hook.** Annual touchpoint (Q4 = peak demand). Re-engagement opportunity each November. Upgrade pitch: "Get every deadline as a dashboard reminder + auto-task assignment in Matcha-lite."

**Gating.** Email capture before download; PDF + ICS both delivered.

**Risks.** Low.

---

## Build Sequencing Recommendation

If shipping the flagship + companions over a quarter:

1. **Week 1–3**: Handbook Gap Analyzer (flagship — see top of doc).
2. **Week 4**: OSHA Recordability Quick Check (cheapest, fastest, niche traffic to validate the funnel infra).
3. **Week 5**: Multi-State Posting Requirements Pack (annual SEO bait).
4. **Week 6–7**: Termination Risk Scorecard (highest-intent paid conversion).
5. **Backlog**: Multi-State New-Hire Checklist, Pay Transparency Checker, Annual Compliance Calendar (ship as quarterly SEO content drops).

**Cross-cutting infra** that should be built once and reused across all six tools:
- Public anonymous job-submit + report-poll endpoint pattern (extract from Handbook Gap Analyzer).
- Email-gate component (`<FreeSignupGate>`) that wraps any teaser content.
- Free-account "Tool History" section in `ResourcesFreeSidebar` listing every tool the user has run, with re-run + saved-output access.
- Unified analytics event taxonomy: `tool_started`, `tool_completed`, `teaser_viewed`, `signup_from_tool`, `upgrade_clicked_from_tool`.
- Single rate-limit middleware for anonymous tool use (3/day/IP default; configurable per tool).

## Out of Scope (across all companion tools)

- Document storage of uploaded materials beyond the analysis window (90 days).
- Multi-user collaboration on Free-tier tool outputs.
- API access to any of these tools (paid-tier only).
- White-label / embeddable widget versions.
