# Casualty Coverage Audit — Matcha vs. Casualty Market Needs

**Date:** 2026-06-21
**Scope:** how well the app meets the casualty-insurance needs (GL, commercial auto, WC, umbrella/excess) for brokers + the insureds they serve, with attention to which gaps an existing **agent** can close. Audit only — no code changed. Evidence cited as `file:symbol`.

## TL;DR verdict

Matcha is a **deep Workers'-Comp + EPL casualty tool** sitting on a **large agentic HR/compliance spine** (52 AI/assistive features). For casualty it is **strong on WC**, **moderate on EPL/cross-cutting**, and **largely absent on GL, commercial auto, umbrella/excess, and the P&C-placement layer** (carrier/MGA appetite, tower modeling, alternative risk transfer). The good news: most *reachable* gaps are **extensions of agents that already exist** — `legislation_watch`, `submission_packet.generate_coverage_gap`, `loss_run_parser`, `wc_benchmarks`. The unreachable gaps (towers, carrier registry, captives) are P&C-placement plumbing outside the current data moat.

- **Covered (real code path):** submission packet + narrative, loss-run parse (WC), WC class-code/EMR/state-rate/CT depth, OSHA 300/300A, composite risk index, **claims-readiness** (just shipped), **controls-evidence** (just shipped), **submission-readiness** (just shipped).
- **Partial:** benchmarking (no limits), exclusion-gap (free-gen, ungrounded), tort tracker (labor-law only), rate-movement (WC static), OSHA/BLS enrichment, medical-mgmt/reserve, driver risk (MVR healthcare-siloed).
- **Absent:** venue/nuclear-verdict severity, litigation-funding signals, carrier/MGA appetite + financial-security, program/tower modeling, alternative risk transfer, all of commercial auto (fleet/FMCSA/telematics/hired-non-owned/AV), GL product-liability/SAM/reserve-dev, umbrella/excess tower.

---

## 1. Agent & assistive inventory (the casualty lens)

52 agentic/assistive features total. The **extensible** ones (already call Gemini + read/write structured data → cheapest to extend for casualty):

| Agent | Job | Reads → Writes | Grounding | Location |
|---|---|---|---|---|
| **IR Copilot / IRAnalyzer** | incident categorize, severity, root-cause, recommendations, policy-mapping, similar | `ir_incidents`,`policies`,`handbooks` → `ir_incident_analysis` | structured + docs | `services/ir_ai_orchestrator.py`, `services/ir_analysis.py`, `routes/ir_incidents/ai_analysis.py` |
| **ER Copilot / ERAnalyzer** | timeline, discrepancy, policy-check, outcome, similar-cases, risk narrative | `er_cases`,`er_case_documents` → `er_case_analysis` | case docs + policies | `routes/er_copilot.py`, `services/er_analyzer.py` |
| **Compliance research (tiered)** | jurisdiction requirement discovery (repository→state→Gemini) | jurisdiction tables → `jurisdiction_requirements` | tiered + live Gemini | `core/services/compliance_service.py`, `gemini_compliance.py` |
| **Legislation Watch** | RSS → Gemini relevance → proactive alerts | `rss_feed_sources`,`rss_feed_items` → `compliance_alerts` | RSS + Google-Search grounding | `core/services/legislation_watch.py` + worker |
| **Structured Data Fetch** | pull/parse govt feeds (Federal Register, eCFR, OpenStates, CMS) | govt APIs → `jurisdiction_requirements` | external APIs | `workers/tasks/structured_data_fetch.py` |
| **Coverage-gap** | AI read of WC/EPL posture → gap + action JSON | submission context → transient | **free-gen Gemini (ungrounded)** | `services/submission_packet.py:generate_coverage_gap` |
| **Loss-run parser** | WC loss-run PDF → structured counts/EMR | PDF → `broker_external_wc` draft | Gemini vision (inline PDF) | `services/loss_run_parser.py:parse_loss_run` |
| **WC class-map** | job titles → NCCI class codes | `employees`,`wc_class_codes` → `company_wc_class_exposures` draft | Gemini + ref table | `services/wc_classmap.py` |
| **Risk narrative / Broker outreach / Theme alerts** | broker-voiced summaries + portfolio pattern alerts | risk index, incidents → transient / `broker_risk_alerts` | structured | `services/risk_narrative.py`, `broker_outreach.py`, `broker_theme_alerts.py` |
| **Leads agent / Research browse** | web research w/ Google-Search + Jina Reader | web → transient | **web-grounded** | `core/services/leads_agent.py`, `services/research_browse_service.py` |

Deterministic/assistive (no Gemini): `submission_readiness.py`, `controls_evidence.py`, `claims_readiness.py`, `wc_benchmarks.py`, `risk_index.py`, `epl_readiness.py`, `wc_depth.py`, OSHA 300A render.
Out-of-domain agents (not casualty leverage): matcha-work AI, interview/culture/conversation analyzers, werk commit-scan, training grading, leave agent.

**Reusable plumbing:** singleton analyzers (`get_ir_analyzer`/`get_er_analyzer`), DB-backed `GeminiRateLimiter`, SSE streaming, `core/services/pdf.py:safe_url_fetcher`. **Web-grounding already exists** (`leads_agent`, `legislation_watch`, `research_browse`) — the key enabler for venue/tort/exclusion intel.

---

## 2. Coverage matrix (needs 1–32)

Status: ✅ Covered · 🟡 Partial · ❌ Missing · ⛔ N/A (out of moat). Priority: **P1** quick win (extend existing agent) · **P2** medium · **P3** low/defer · **—** already covered.

### A. Cross-cutting
| # | Need | Status | Evidence | Agentic opportunity | Pri |
|---|---|---|---|---|---|
| 1 | Venue / nuclear-verdict severity | ❌ | compliance models are regulatory-only (`core/models/compliance.py`); no venue/court fields | Curated nuclear-verdict county list + **web-grounded** Gemini (reuse `research_browse`/`leads_agent` grounding); attach to `business_locations` | P2 |
| 2 | Litigation-funding awareness | ❌ | no funding signal anywhere | Tacit/unpublished → hard to source reliably | P3 |
| 3 | Tort-reform / regulatory tracker | 🟡 | `legislation_watch.py` tracks **labor law only** (min-wage, sick-leave…) | **Extend `legislation_watch`**: add tort-reform/auto-reform/WC-presumption RSS sources + category enum; per-account alerts already exist | **P1** |
| 4 | Submission quality + risk narrative | ✅ | `submission_packet.py` (PDF + `_wc_narrative`/`_epl_narrative`), `risk_narrative.py` | Extend narrative to more lines as data lands | — |
| 5 | Loss-run ingestion & normalization | 🟡 | `loss_run_parser.py` parses **WC counts snapshot only**; no triangulation/trend/development; external clients only | **Extend the parser agent**: multi-period ingest + development factors; add GL/auto loss-run schemas | **P1** |
| 6 | Benchmarking & limit-adequacy | 🟡 | `wc_benchmarks.py` (BLS NAICS medians + premium-impact); **no limits, no contractual** | Add limit-adequacy + a **contract-review assistive flow** (Gemini reads contracts → required limits) | P2 |
| 7 | Program structure / tower modeling | ⛔ | none | P&C-placement plumbing; not our data moat | ⛔ |
| 8 | Carrier / MGA appetite + financial-security | ⛔/❌ | only historical `carrier` text on `company_wc_mods` | Net-new carrier DB + AM-Best feed; outside moat | P3 |
| 9 | Exposure & exclusion-gap analysis | 🟡 | `generate_coverage_gap` is **free-gen**; `cybersecurity`/BIPA in `compliance_registry.py` only | **Ground the coverage-gap agent** with a curated exclusion-template registry (PFAS, A&M, TBI, wildfire, biometric, silent-cyber/AI) + per-industry known-gaps | **P1** |
| 10 | Alternative risk transfer (captive/parametric) | ⛔ | none | Capital-management modeling; outside moat | ⛔ |
| 11 | Claims-readiness & defense support | ✅ | `claims_readiness.py` (incident + ER defense packets) — **just shipped** | — | — |
| 12 | Risk-mitigation evidence | ✅ | `controls_evidence.py` (8 controls + verify + PDF), `resident_care.py` (MVR/safety) — **just shipped** | Telematics capture still missing (see #15) | — |
| 13 | Renewal / rate-movement intelligence | 🟡 | `wc_state_rates` static WC + admin viewer; `broker_risk_alerts` backward-looking | Extend rate feed (multi-line) + forward renewal alerts; pairs with #3 | P2 |

### B. Commercial auto
| # | Need | Status | Evidence | Agentic opportunity | Pri |
|---|---|---|---|---|---|
| 14 | Fleet enrichment (recalls, motor-carrier scores) | ❌ | none | New line + external feeds (FMCSA/NHTSA); `structured_data_fetch` could host the pulls | P3 |
| 15 | Driver-risk + telematics | 🟡 | MVR only in `resident_care.py`/`mvr_reviews` (healthcare-siloed); no scoring/telematics | Generalize MVR off the healthcare vertical + scoring; telematics = new integration | P2 |
| 16 | Hired / non-owned auto | ❌ | none | New capture | P3 |
| 17 | Fleet segmentation + venue overlay | ❌ | none | Depends on #14 + #1 | P3 |
| 18 | Primary-auto → umbrella cascade | ⛔ | none (no tower) | depends on #7 | ⛔ |
| 19 | Autonomous-vehicle liability | ❌ | none | niche; defer | P3 |

### C. Workers' comp (our strength)
| # | Need | Status | Evidence | Agentic opportunity | Pri |
|---|---|---|---|---|---|
| 20 | Class-code (NCCI) payroll exposure | ✅ | `wc_depth.py`, `wc_classmap.py`, `wc_class_codes`/`company_wc_class_exposures` | real per-class rates still thin (10 demo) — load WCIRB free file | — |
| 21 | Jurisdiction + CT (CA) + EMR + mod-creep | ✅ (mod-creep 🟡) | `wc_depth.latest_mods`/`mod_trajectory`, CT/post-term cols on `ir_incidents`, `wc_state_rates` | add explicit ELR/mod-creep-when-loss-costs-fall modeling | P3 |
| 22 | OSHA / BLS enrichment | 🟡 | OSHA 300/301/300A + ITA (`routes/ir_incidents/osha.py`); BLS only as NAICS benchmark medians | Use `structured_data_fetch` to pull BLS establishment injury + wage data | P2 |
| 23 | Medical-mgmt / reserve-adequacy / RTW | 🟡 | RTW covered (`compute_wc_metrics` rtw); no reserve/medical-mgmt depth | reserve-dev from multi-period loss runs (pairs with #5) | P2 |
| 24 | Presumption-law / mental-health-compensability | ❌/🟡 | not tracked; `legislation_watch` is labor-only | **Extend `legislation_watch`** with WC-presumption category (same change as #3) | **P1** |

### D. General liability
| # | Need | Status | Evidence | Agentic opportunity | Pri |
|---|---|---|---|---|---|
| 25 | Venue litigation intelligence (freq/severity) | ❌ | none | same as #1 | P2 |
| 26 | Product-liability + emerging exposure (PFAS/abuse/social/silent-AI) | 🟡 | only free-gen coverage-gap | same exclusion registry as #9 | **P1** |
| 27 | Reserve-development; SAM placement | ❌ | none (`abuse_prevention` is a safety-program type, not A&M underwriting) | new capture | P3 |
| 28 | GL limit-adequacy + contractual review | ❌/🟡 | none | same as #6 | P2 |

### E. Umbrella / excess
| # | Need | Status | Evidence | Agentic opportunity | Pri |
|---|---|---|---|---|---|
| 29 | Tower assembly across carriers | ⛔ | none | P&C placement; outside moat | ⛔ |
| 30 | Attachment-point / lead-limit optimization | ⛔ | none | outside moat | ⛔ |
| 31 | Hardening-exclusion tracking across tower | 🟡 | none (exclusion registry from #9 could feed this) | exclusion registry (#9) surfaces creep even without full tower | P2 |
| 32 | Excess-specific benchmarking | ❌ | none | depends on tower data | P3 |

---

## 3. Gap analysis — concrete close paths (favor agent extension)

**P1 quick wins — all extend an existing agent:**
1. **Tort-reform + WC-presumption + auto-reform tracker (#3, #24).** Extend `legislation_watch`: add the relevant RSS/Google-Search sources + a category enum beyond labor law; the per-jurisdiction `compliance_alerts` + per-account alerting already exist. One agent, new feeds/categories. *(This is the reliable, groundable version of the "rate/exclusion tracker" idea — legislation IS published, unlike "what underwriters ask".)*
2. **Grounded exclusion-gap registry (#9, #26, #31).** Replace/augment `generate_coverage_gap` free-gen with a curated **exclusion-template registry** (PFAS, A&M, TBI, wildfire, biometric, silent-cyber, silent-AI) keyed by industry; the agent checks the client's profile against templates → grounded, defensible gaps + tower-creep flags. Reuses the coverage-gap call site + the compliance-registry pattern.
3. **Loss-run triangulation + multi-line (#5, #23).** Extend `loss_run_parser` from single-period WC snapshot to multi-period ingest with development/trend; add GL/auto loss-run schemas. Feeds reserve-adequacy (#23).
4. **Limit-adequacy + contract review (#6, #28).** Extend `wc_benchmarks` with benchmark-based limit recommendations + a Gemini contract-review flow (read insured's contracts → required limits/AI endorsements). New assistive flow, reuses analyzer plumbing.

**P2 — higher effort, in-moat:**
- **Venue/nuclear-verdict severity (#1, #25):** curated tough-venue dataset (Harris/Midland TX, Louisiana, …) + web-grounded Gemini refresh (reuse `research_browse`/`leads_agent` grounding); attach a severity score to `business_locations`, surface in risk index + submission.
- **BLS establishment/wage enrichment (#22):** `structured_data_fetch` pulls BLS → per-establishment injury-rate + wage context.
- **Rate-movement depth (#13):** broaden `wc_state_rates` beyond WC + forward renewal alerts.
- **Generalize driver-risk/MVR (#15):** lift MVR out of the healthcare vertical + add scoring (commercial-auto entry point).

**⛔ Out of moat (don't build without a strategy pivot):** tower/program modeling (#7,#18,#29,#30,#32), carrier/MGA appetite + financial-security (#8), alternative risk transfer (#10), litigation-funding signals (#2), most of commercial auto as a full line (#14,#16,#17,#19). These are P&C-placement infrastructure, not HR-data-derived — same conclusion as the broker gap brief: our edge is turning owned HR/safety data into terms, not becoming a placement platform.

---

## 4. Prioritized recommendations

**Do first (quick wins, days not weeks, all agent extensions):**
1. Exclusion-gap registry grounding (#9/#26/#31) — biggest credibility upgrade; kills the ungrounded free-gen.
2. `legislation_watch` → tort-reform + WC-presumption (#3/#24) — same cron, high casualty relevance, reliable because it's published law.
3. Loss-run triangulation + GL/auto schemas (#5/#23).
4. Limit-adequacy + contract review (#6/#28).

**Then (in-moat depth):** venue severity (#1/#25) · BLS enrichment (#22) · rate-movement breadth (#13) · generalize MVR (#15).

**Defer / out of scope:** towers, carrier registry, ARM, litigation funding, full commercial-auto line, AV.

---

## 5. Over-build flags

- **`generate_coverage_gap` implies lines it has no data for.** The prompt names Cyber / Umbrella / etc. as gap examples, but there is **zero backend data** for those lines — the AI free-gens about coverage we can't substantiate. Either ground it (#9) or scope the prompt to WC/EPL. *(Reliability risk on a broker-facing artifact.)*
- **`resident_care` MVR is healthcare-siloed.** A general driver-risk surface (#15) would duplicate it; consolidate rather than build a parallel MVR.
- **Not over-build, but flag the framing:** the deep EPL/compliance/handbook machinery (handbook audit, tiered compliance research, ER copilot) far exceeds what casualty P&C *placement* needs — but it **is** the HR product and the data moat that differentiates the casualty story. Keep it; just don't mistake its breadth for casualty-line coverage.
- **52 agentic features, ~10 casualty-relevant.** The rest (matcha-work AI, interview analyzers, werk commit-scan, language tutor) are other products — no casualty leverage; fine, just not a casualty asset.

---

## Methodology
All classifications cite `file:symbol` verified in-code by three parallel read-only audits (agent inventory, casualty data surfaces, cross-cutting infra). No code changed. Next step: pick from §4 — the four P1 items are each scoped as a single-agent extension.
