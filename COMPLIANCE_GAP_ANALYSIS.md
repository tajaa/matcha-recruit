# Compliance Coverage Gap Analysis — Federal + CA Labor

_Ground-truth audit (dev DB + code), 2026-07-11._

## Context

Goal for the compliance/jurisdictional tool: **scope the entirety of the federal + California labor obligations a business is responsible for, keep it current as laws change or new ones pass, and let a business map its roster to that catalog and be "always protected."** The 5 admin "Compliance Data" surfaces (Compliance Mgmt, Jurisdictions, Compliance Library, Scope Studio, WC Rate Data — Payer Data out of scope) are meant to account for all of this.

**Verdict: the engine is built and correct; the data is a partial research-accreted set (federal labor is a stub), there is no enumerated definition of "done," the update loop is dormant and can't discover new law on its own, and a new city/industry can't enter the pipeline without a code change.**

### Admin persona this must serve
> "A coffee shop in San Diego is joining. I need everything for San Diego. I assume federal + state are done — now I need San Diego."
> Workflow: **scope → codify → generate policies (agent = Gemini + our eval tools) → store authority source + tag → review in Compliance Library.**

Two false assumptions in that quote, both surfaced below: (1) "federal + state are done" — federal labor is 5 rows; (2) "add San Diego" — no admin path to ingest a new city's authority; it's a code change.

---

## Pillar 1 — Coverage ("scope the entirety of federal + CA labor")

### Have
- Jurisdiction tree + inheritance: city→county→state→federal recursive CTE (`compliance_service.py:8530`).
- **CA state labor: 64 rows** — solid (leave 8, pay_frequency 6, meal_breaks 6, overtime 6, minor_work 5, scheduling 5, safety 5, min_wage 4, anti_discrim 4, final_pay 3, sick_leave 2, WC 1).
- CA local: 1,003 rows across 16 CA cities/counties.
- 28 labor categories enumerated (`compliance_registry.py:7298` `LABOR_CATEGORIES`); 495 `regulation_key_definitions` (+ severity via `rkdsev01`).
- Authority text ingested: 527 federal items (OSHA 1910/1904, FMLA 825, FLSA, RCRA×3) + 30 CA (labor-code, title-8, title-16) with `body_text`.

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **Federal labor catalog** | 🔴 | **5 labor rows.** Zero FMLA, EEO/Title VII, ADA, ADEA, workers-comp, WARN, I-9/E-Verify, ERISA, NLRA, USERRA, COBRA, equal-pay. The 60 federal rows are mostly healthcare. |
| **Enumerated master-list = definition of "done"** | 🔴 | "Entirety" is undefined in code. Expected set is emergent from research — only 12/28 labor categories have expected keys (88 keys); 16 categories structurally empty. Only auditable list = 12-key core checklist (`industry_keysets.py:89`). |
| Completeness never scored vs fed/CA-state | 🔴 | 0 eval results for federal, 3 for CA-state. Closest proxy (LA, inherits both) = **42–46% complete**, `focused_keys_complete=false`, 539 open critical `missing_key`. |
| Federal classification backlog | 🟡 | 193/527 federal items ingested-but-unclassified (all 3 RCRA indexes). |
| Codification depth | 🟡 | 364 classifications → **27 codifications** (12 fed + 15 CA). Classified-but-uncodified = known-applicable, no value. |
| CA jurisdiction hygiene | 🟡 | Dupe/misspelled jurisdictions (`los anageles`, `ca`, `san diego` vs `_county_san diego`) split data. |

---

## Pillar 2 — Freshness ("update regularly, catch changes AND new laws")

### Have (all built, all dormant)
- Change-detection: `previous_value`/`last_changed_at`/`change_status` + per-location `compliance_requirement_history` + alerts.
- Drift detection: eCFR re-ingest diffs → `authority_index_drift` → flags catalog rows `needs_review` (`codify.py:419`).
- `legislation_watch`: Gemini-grounded RSS scan (CA DIR, NY DOL, WA L&I) → proactive alerts.
- `structured_data_fetch`: DOL/UCB/NCSL CSV/HTML → cache.
- Scheduler framework: `scheduler_settings` + hourly `@worker_ready` re-dispatch.

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **Loop is OFF** | 🔴 | Every compliance-refresh scheduler row `enabled=f`. `rss_feed_items=0`, `structured_data_cache=0`, `authority_index_drift=0` — never run. |
| **No net-new discovery path** | 🔴 | Nothing automated INSERTs a catalog row for a new law. legislation_watch → alerts only; codify drift → flags only; scheduled checks `allow_live_research=False`. New CA law stays invisible until a human runs `fill-gaps-*`. |
| No global changelog | 🟡 | "Rule X changed on date Y" exists only per-tenant (empty). No catalog-level version audit. |
| Watch sources thin | 🟡 | 3 RSS feeds; no Federal Register, no CA-Leg bill tracker, no municipal sources. |
| Ingest not scheduled | 🟡 | Authority indexes = one manual populate; sync task exists but disabled. |

---

## Pillar 3 — Roster mapping ("business maps roster to compliance")

### Have
- Roster → jurisdictions: `collect_roster_jurisdictions` → work locations → auto-create `business_locations` → check.
- Full geographic stack fed+state+county+city, precedence/preemption resolved.
- Industry filter: `applicable_industries` ∩ company tags (`_filter_requirements_for_company`).
- Conditional engine capable of attribute/entity_type/and-or-not incl. gte-headcount (`evaluate_trigger_conditions:8431`).

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **Headcount gating unwired for tenants** | 🔴 | `employee_count` never written to `facility_attributes`; 0/2,737 rows carry headcount triggers. FMLA-50-class obligations can't be represented → over-coverage now, silent under-coverage if authored conditionally. Works only in Scope Studio preview (`scope_registry.py:313`). |
| Untagged-industry leakage | 🟡 | 82% rows untagged → industry-specific rows served to everyone; mirror: mis-tagged row silently dropped. |
| Uncodified-applicable invisible to tenant | 🟡 | Scope-registry "applies, no value yet" queue is admin-only; tenant sees green. |
| Hierarchical vs flat views disagree | 🟡 | hierarchical read skips industry filter (`:8810`). |
| Blank work_state silently skipped | 🟡 | employees w/o work_state excluded from scope scan (`roster_jurisdictions.py:46`). |

---

## Pillar 4 — Admin on-ramp (the coffee-shop-in-SD workflow)

### Have
- Full curation pipeline **once authority text exists**: classify (disposition/industry/conditions/sub-jurisdiction tag) → confirm → key → grounded research (Gemini as locator, citation-gated) → codify → review in Compliance Library. Proven on federal this session.
- Eval guardrails: 6 suites incl. scope + grounding tier-1/2a (golden) /2b (LLM verifier) + readiness gate.

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **No local (city/county) authority ingest** | 🔴 | Source registry hardcoded (`authority_sources.py`: 6 eCFR + 4 curated). Adding San Diego municipal code = code change, no admin path. Step 1 of the persona workflow can't start. |
| **No coffee-shop / food-service industry keyset** | 🔴 | Core checklists = manufacturing + healthcare only. "Everything for a food-service tenant" is unmeasurable. |
| No baseline-assurance view | 🔴 | "I assume federal+state are done" is unverifiable in-app (and false). No per-jurisdiction "coverage X/Y ✓" against a real master-list. |
| No SD golden fixture | 🟡 | golden = federal/CA/LA/SF/NYC. SD unverified. |
| Evals scheduled off | 🟡 | `compliance_evals` scheduler row disabled — QA runs only on manual click. |

---

## Bottom line + dependency order

- **Engine: built** — classify→key→grounded-research→codify→eval works and is guarded.
- **Data: federal labor is a stub; no master-list defines "done."**
- **Automation: dormant + can't discover new law by itself.**
- **On-ramp: new city/industry can't enter without code changes.**

Closing order (each stacks on the prior):
1. **Master-list + baseline eval** — enumerate federal + CA-state labor obligations; run completeness against those jurisdictions directly. _Defines "done" and makes "federal+state are ready" a checkable claim._
2. **Federal labor fill** — push the missing federal obligations through the existing scope pipeline to codified rows.
3. **Local-ingest path + industry keysets** — admin-authorable city/county authority source + a food-service (and generic-employer) core keyset. _Unblocks "add San Diego" and per-tenant-type assurance._
4. **Freshness loop on** — enable scheduler rows; wire legislation_watch / ingest-drift to _propose catalog rows_ (net-new discovery), not just alerts; global changelog.
5. **Roster-gating fixes** — headcount attribute wiring, untagged-industry, uncodified-visibility, view consistency.

_This document is a gap analysis, not an implementation plan. Each numbered item above is a separate future planning effort._
