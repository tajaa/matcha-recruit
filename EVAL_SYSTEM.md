# Jurisdictional Data Eval System — Control Flow

What it accomplishes, in one sentence: **it turns "we think our jurisdictional data is good" into a
per-(jurisdiction × industry) number you can defend — and it says `null` when nothing has checked,
rather than letting silence read as correct.**

Code: `server/app/core/services/compliance_evals/`
Admin UI: `/admin/jurisdiction-data` → **Evals** tab
Migration: `jureval01` (tables `compliance_eval_runs` / `_results` / `_findings`)

Nodes are numbered so branches can be referenced in review (`D4.2`, `T-READY`). Prefixes:
`N` = step, `D` = decision, `T` = terminal, `F` = emits a finding.

---

## 0. The two chains

There are two independent entry points. The **read path** does not depend on the **run path** ever
having executed — completeness is deterministic, so it is recomputed live.

```
                        ┌──────────────────────┐
                        │  jurisdiction_       │   2,724 rows / 105 jurisdictions
                        │  requirements        │   ← READ-ONLY to everything below
                        └──────────┬───────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
      ┌───────▼────────┐                       ┌────────▼─────────┐
      │  RUN PATH      │  batch, writes        │  READ PATH       │  live, writes nothing
      │  (§1 – §4)     │  a scorecard          │  (§6)            │  answers one question
      └───────┬────────┘                       └────────┬─────────┘
              │                                         │
     compliance_eval_runs                     GET /evals/onboarding-readiness
     compliance_eval_results                  GET /evals/core-checklist
     compliance_eval_findings                 GET /evals/scorecard
```

---

## 1. Trigger

```
N0  TRIGGER
├── N0.a  Admin clicks "Run"  →  POST /admin/jurisdictions/evals/run
│   │
│   ├── N1   INSERT compliance_eval_runs (status='running')
│   │        └── happens BEFORE any work, so a crash leaves evidence
│   │
│   └── D1   suites ∩ NETWORK_SUITES ≠ ∅ ?          (NETWORK_SUITES = {authority})
│       ├── YES → N1.1  dispatch Celery task `compliance_evals.run`
│       │                └── WHY: authority fetches ~855 distinct regulator URLs;
│       │                    a slow .gov host would pin a uvicorn worker for minutes
│       └── NO  → N1.2  BackgroundTasks → run_evals(...) inline
│
└── N0.b  Hourly host cron restarts matcha-worker  →  @worker_ready fires
    │
    ├── D2   scheduler_settings['compliance_evals'].enabled ?
    │   ├── NO  → T-SKIP  (seeded disabled by the migration)
    │   └── YES → D3
    │
    └── D3   last *scheduled* completed run older than MIN_SCHEDULED_INTERVAL_DAYS (6) ?
        ├── NO  → T-DECLINE
        │         └── WHY: there is no celery-beat in this repo. The scheduler row is only an
        │             on/off switch, and the worker restarts hourly — so the task MUST decline
        │             on its own or enabling the row runs a full network sweep every hour.
        └── YES → N1.2 (all four suites, trigger_source='scheduled')
```

---

## 2. Suite execution

`run_evals(suites, jurisdiction_ids × industries)`. Each suite returns `(results, findings)`.
**No suite writes to `jurisdiction_requirements`.**

### 2.1 `completeness` — per (jurisdiction × industry)

```
N2  load_jurisdiction_graph()          2 queries: all jurisdictions + all requirements
│
├── N2.1  normalize every catalog key           (keys.py:normalize_key)
│   └── D4   category == 'minimum_wage' ?
│       ├── NO  → pass through unchanged
│       └── YES → D4.1  bare key == 'general' ?
│           ├── YES → D4.2  jurisdiction level?
│           │        ├── city / county / special_district → 'local_minimum_wage'
│           │        ├── federal / national, or country ≠ US → 'national_minimum_wage'
│           │        └── state (or unknown)                  → 'state_minimum_wage'
│           └── NO  → rate_type → registry name
│                     tipped→tipped_minimum_wage, exempt_salary→exempt_salary_threshold,
│                     fast_food→…, healthcare→…, large_employer→…, small_employer→…
│                     'hotel' → LEFT UNMAPPED on purpose (no registry key; the resulting
│                                `invalid_key` finding is a true registry gap, not noise)
│
│   WHY: the catalog speaks two dialects at once. _compute_requirement_key keys minimum-wage
│   rows on rate_type; the registry names the same facts state_minimum_wage etc. Dev holds
│   BOTH. Comparing raw would report phantom gaps on rows that plainly exist.
│
├── N2.2  PRESENT = keys@self ∪ keys@state ∪ keys@country-root
│   └── D5   country_code == 'US' ?
│       ├── YES → root = federal_id            (the single `level='federal'` row)
│       └── NO  → root = national_ids[cc]      (`level='national'` = UK / Mexico / Singapore)
│
│   WHY: `federal` and `national` are NOT the same bucket. Collapsing them let a US city
│   inherit UK law — and since the UK row is empty, silently lose all 50 real federal rows.
│   Whichever the query returned last won.
│
│   NOTE: preemption needs no filter here. Presence is presence. When a state preempts local
│   minimum-wage ordinances, the state row is exactly where the key belongs, and the union
│   already reflects that.
│
├── N2.3  EXPECTED
│   ├── D6   depth?
│   │   ├── core (DEFAULT for the gate) → CORE_LABOR_KEYS (12) + CORE_INDUSTRY_KEYSETS[ind] (15)
│   │   │     = 27 keys. Auditable by a human in one sitting.
│   │   │     └── D6.1  industry has a curated core?   (manufacturing | healthcare)
│   │   │         ├── YES → use it
│   │   │         └── NO  → core_keys() RAISES; the endpoint falls back to full
│   │   │                   (silently returning the labor core alone would claim an
│   │   │                    industry verdict the checklist cannot support)
│   │   └── full → (labor ∪ supplementary ∪ industry categories) → all registry keys
│   │              180 for manufacturing, 237 for healthcare
│   │
│   └── N2.3.1  filter by _key_applies_to_country(key, cat, cc)  — ALWAYS, including US
│         WHY: get_missing_regulations short-circuits this filter when cc == 'US', so it
│         demands Mexico-only keys (finiquito, liquidacion, nom_035_psychosocial_risk) of a
│         Los Angeles employer. Live bug upstream. The eval must not inherit it.
│
└── N2.4  for key in EXPECTED − PRESENT:
    └── D7   key's category ∈ focused set ?
        ├── YES → F:missing_key  severity=critical
        └── NO  → F:missing_key  severity=warn
        (in `core` depth every miss is critical by construction — the set only contains
         keys whose absence is unambiguous)
```

### 2.2 `tagging` — per catalog row

```
N3  for each row (joined to its jurisdiction):
│
├── N3.1  key = normalize_key(...)         same normalization as N2.1, or `invalid_key`
│                                          would brand hundreds of correct rows
│
├── D8   category ∈ registry ?
│   └── NO → F:invalid_category (warn)
│
├── D9   key ∈ EXPECTED_REGULATION_KEYS[category] ?
│   └── NO → F:invalid_key (info)
│            └── a key nobody expects is a key no coverage report will notice is missing
│
├── D10  category is owned by an industry ?     (machine_safety→manufacturing, etc.)
│   ├── NO  → universal row, nothing to check
│   └── YES → D10.1  does any tag root-match that industry ?
│             (root match: 'healthcare:oncology' satisfies 'healthcare' and vice versa)
│       ├── YES → ok
│       └── NO  → F:industry_tag_missing  severity=CRITICAL
│                 └── CONSEQUENCE: _filter_requirements_for_company passes every UNTAGGED
│                     row to EVERY tenant. This is not untidiness — a restaurant receives
│                     the factory's RCRA and EPCRA obligations. 345 rows in dev.
│
└── N3.2  micro-averaged precision/recall vs fixtures/tagging_labels.json
    └── mismatch → F:tag_precision_error (warn)
        └── WHY a second mechanism: D10 can only see tags that are ABSENT.
            Only labels can see a tag that is WRONG — e.g. a universal CA overtime rule
            tagged `healthcare:behavioral_health`, which HIDES it from everyone else.
```

### 2.3 `golden` — per curated fact

```
N4  load fixtures/golden/*.json → Pydantic-validate → resolve jurisdiction → index catalog
│                                                      by `category:normalized_key`
│
└── for each fact:
    D11   today ∈ [effective_from, effective_to) ?      (effective_to is EXCLUSIVE:
    │                                                    a wage that reindexes July 1 is
    │                                                    not asserted ON July 1)
    ├── NO ── D11.1  expired ?
    │   ├── NO  → T-PENDING (future fact, ignored)
    │   └── YES → D11.2  another fact for this key is active today ?
    │       ├── YES → T-SUPERSEDED (silent; this is the curated successor pattern)
    │       └── NO  → F:golden_stale (warn)
    │                 └── the fixture polices its own freshness rather than asserting
    │                     last year's minimum wage forever
    │
    └── YES → D12   catalog row exists for this category:key ?
        ├── NO  → F:golden_fail ("no catalog row")
        └── YES → D13  comparator
            ├── numeric_eq / numeric_within → numeric_value, else parse current_value
            ├── text_contains → distinctive terms of art ONLY ("seventh consecutive day",
            │                    "recognized hazards"). Never "40" — it passes trivially
            │                    and manufactures false confidence.
            ├── date_eq → effective_date
            └── exists  → the key is present; all we can honestly assert for tiered or
                          qualitative rules (CA SB 525 healthcare wage varies by facility)
            │
            └── D13.1  passed ?
                ├── YES → count toward accuracy
                └── NO  → F:golden_fail @ fact.severity
                          └── severity=critical ⇒ ZEROES the jurisdiction's accuracy (see D19)
```

### 2.4 `authority` — per distinct URL, then per row

```
N5  collect distinct source_urls → fetch each ONCE (8 concurrent, 15s timeout)
│
├── D14  row has a source_url ?
│   └── NO → F:missing_citation  severity=CRITICAL     (424 rows in dev)
│
├── D15  liveness (HEAD, then ranged GET)
│   ├── 403 / 405 / 429            → alive_unverified
│   │     └── gov hosts routinely reject HEAD and bot user-agents. The response PROVES
│   │         the host is up. Calling it dead would bury the eval in false positives.
│   ├── 2xx / 3xx                  → alive
│   ├── TimeoutException           → `timeout`  → F:url_unreachable (info)
│   │     └── A timeout is not evidence against the citation. wagesla.lacity.gov answers
│   │         HEAD 200 alone but times out under concurrency. Marking it dead sends a
│   │         curator chasing a URL that is fine. Scored on its domain class instead.
│   └── ConnectError / 4xx / 5xx   → `dead`     → F:dead_url (warn)
│         └── TLS verification stays ON: a cert that doesn't validate is not a citation
│             we can stand behind.
│
├── D16  classify_domain(url)          [pure function, unit-tested, no network]
│   ├── primary            (.gov, .mil, eCFR, state legislatures, official municode) → 1.0
│   ├── secondary_official (NCSL, Joint Commission, USP, Justia*)                    → 0.7
│   ├── aggregator         (SHRM, ADP, law-firm alerts, minimum-wage.org)            → 0.3
│   └── unknown                                                                       → 0.1
│       * Justia mirrors statute text; it does not publish it. Demoted deliberately.
│
├── D17  source_tier == 'tier_1_government' AND class ≠ primary ?
│   └── YES → F:tier_label_mismatch (warn)
│             └── dev: 414 rows CLAIM tier_1_government; 0 rows link a structured_source_id
│
└── D18  url domain ∉ regulation_key_definitions.authority_source_urls[key] ?
    └── YES → F:non_authoritative_domain (info)
```

### 2.5 `freshness` — always, regardless of requested suites

```
N6  % of a jurisdiction's rows re-verified inside their key's SLA
    └── regulation_key_definitions.staleness_warning_days, default 90
    └── reuses existing SLA machinery; does not re-model it
```

### 2.6 `grounding` — per `gemini_grounded` catalog row

Does a scope-registry-researched value actually appear in the statute text it
cites? `metadata.grounding='grounded'` proves the model cited a REAL excerpt
(`scope_registry.grounded.validate_requirement_citations`), NOT that the value is
in it — a recalled number can wear a genuine citation. This suite closes that gap.

```
N5b tier-1, deterministic, no network (pure evaluate_row):
    ├── pull each grounded row's cited excerpts' authority_index_items.body_text
    ├── strip citation references from the value (29 CFR 1904, § 207 — pointers, not values)
    ├── extract numeric tokens; check each in the text (comma + spelled-out legal forms)
    └── verdict:
        ├── value_in_text      → grounded for real (no finding)
        ├── value_not_in_text  → CRITICAL: real citation, number absent → blocks
        │                        readiness via the existing open-critical gate (N8)
        ├── corpus_stub        → cited body < 500ch (a heading) → grounding hollow (warn)
        └── value_unverifiable → prose, no numeric claim tier-1 can judge (info; tier-2 TODO)
    score = value_in_text / (value_in_text + value_not_in_text); stubs/prose excluded
            from the denominator (unmeasured ≠ 100). Its own scorecard row, NOT in the
            composite (a hallucinated value gates through the critical-finding path, not
            a reweight).
    extension points (in-file, unwired): tier-2 adversarial LLM verifier on the
    unresolved rows; golden cross-check (grounded row vs a golden fact = grounded_but_wrong).
```

---

## 3. Persist

```
N7  executemany → compliance_eval_findings
N8  tally CRITICAL findings:  per jurisdiction  AND  per (jurisdiction × industry)
N9  compliance_eval_results:
    ├── industry IS NULL  → authority | tagging | golden | freshness   (industry-agnostic)
    └── industry = X      → completeness  +  composite (carries onboarding_ready)
N10 UPDATE run status='completed', totals=…   |   on exception: status='failed', error_text=…
```

---

## 4. The gate — `scoring.evaluate_readiness`

```
D19  EVALUATE
│
├── completeness ≥ 90 ?                                       ── no ──┐
├── 100% of focused/core keys present ?                       ── no ──┤
├── zero open CRITICAL findings ?                             ── no ──┤
├── authority ≥ 70 (if measured) ?                            ── no ──┤
├── freshness ≥ 80 (if measured) ?                            ── no ──┤
│                                                                     │
└── accuracy:                                                         │
    ├── D19.1  accuracy is null  (no golden facts) ─────────── no ────┤
    │          └── SILENCE IS NOT A PASS. This is the whole point.    │
    ├── D19.2  golden_fact_count < 10 ──────────────────────── no ────┤
    ├── D19.3  accuracy == 0  (a CRITICAL golden fact failed) ─ no ───┤
    │          └── 40 passing facts cannot launder a wrong state      │
    │              minimum wage; averaging it away would hide it.     │
    └── D19.4  accuracy ≥ 95 ───────────────────────────────── yes ───┤
                                                                      │
   ┌──────────────────────────────────────────────────────────────────┤
   │                                                                  │
   ▼ no blocking reasons                                     ▼ any blocking reason
T-READY                                            D20  completeness ≥ 75
                                                        AND accuracy ≠ 0 ?
                                                   ├── YES → T-DEGRADED
                                                   └── NO  → T-NOT_READY

  A cell with no golden facts can never reach T-READY. It caps at T-DEGRADED.
```

---

## 5. Findings taxonomy

| finding_type | suite | severity | means |
|---|---|---|---|
| `missing_key` | completeness | critical / warn | expected key absent at this jurisdiction chain |
| `industry_tag_missing` | tagging | **critical** | untagged industry row → served to every tenant |
| `tag_precision_error` | tagging | warn | tag present but wrong (vs labeled sample) |
| `invalid_category` | tagging | warn | category not in the registry |
| `invalid_key` | tagging | info | key not in `EXPECTED_REGULATION_KEYS[category]` |
| `golden_fail` | golden | fact's own | catalog disagrees with verified law |
| `golden_stale` | golden | warn | fact's window closed with no successor curated |
| `missing_citation` | authority | **critical** | row has no `source_url` at all |
| `dead_url` | authority | warn | citation does not resolve |
| `url_unreachable` | authority | info | citation timed out — **not** judged dead |
| `tier_label_mismatch` | authority | warn | claims `tier_1_government`, cites an aggregator |
| `non_authoritative_domain` | authority | info | domain not in the key's declared authorities |

---

## 6. Read path — independent of any run

```
GET /admin/jurisdictions/evals/onboarding-readiness?industry=&state=&city=&depth=core
│
├── D21  jurisdiction row resolves ?
│   └── NO → T-NOT_READY ("no jurisdiction record for this location")
│
├── N11  completeness: RECOMPUTED LIVE  (deterministic; needs no stored run)
│
├── N12  accuracy / authority / freshness / tagging: latest stored per suite
│   └── SELECT DISTINCT ON (suite) … ORDER BY suite, created_at DESC
│       └── WHY DISTINCT ON: a partial re-run of ONE suite must never erase a cell
│           from a suite it did not measure.
│
├── D22  eval tables exist ?   (migration jureval01 applied?)
│   ├── NO  → catch UndefinedTableError → treat every stored subscore as absent
│   │         └── never-measured and measured-badly must not be distinguishable by a 500
│   └── YES → merge them
│
├── N13  evaluate_readiness(...)  → §4
└── N14  ALWAYS return `core_checklist` when the industry has one
          └── 27 rows, each present/missing — auditable key by key. A 180-row gap list
              cannot be checked by a human, so a wrong EXPECTATION would go unnoticed.
```

```
POST /admin/jurisdictions/evals/findings/{id}/resolve
└── writes status / notes / resolved_by ONLY
    └── NEVER touches jurisdiction_requirements
        └── the catalog fix happens through the existing requirement-editing surfaces,
            so the NEXT run independently CONFIRMS the fix rather than confirming its own edit
```

---

## 7. The invariants

Everything above exists to protect four rules.

1. **The eval never mutates the catalog.** It records findings; it does not apply them. This is
   also why it does not copy `_validate_source_urls`, which blanks a dead `source_url` and keeps
   the row — destroying the evidence that the row was ever uncitable.

2. **Unmeasured is `null`, never `100`.** No golden facts ⇒ `accuracy: null` ⇒ cannot be `READY`.
   A catalog must not look authoritative merely because nothing has checked it.

3. **One critical failure zeroes a cell.** Reserved for unambiguous, high-confidence numbers.
   Every brittle fact — region-split values, `text_contains` substrings, tiered rules — is `warn`.

4. **A timeout is not a dead citation.** Nor is a 403 from a regulator. Under-claiming is cheap;
   a false accusation sends a human chasing nothing and teaches them to distrust the eval.

---

## 8. What it found on first run (dev: 2,724 rows / 105 jurisdictions)

| | core checklist | full sweep | authority |
|---|---|---|---|
| Los Angeles × manufacturing | 12/27 | 42.5 — 79/180 present | 58.0 |
| New York City × healthcare | 18/27 | 34.9 — 86/237 present | — |
| San Francisco × retail | — (no core) | 56.1 — 61/107 present | 66.3 |

- **No veracity gate exists upstream.** Gemini writes to the catalog at
  `compliance_service.py:5147` *before* verification. `verify_compliance_changes_batch` covers
  only *changed* values and only suppresses an alert — never the stored row.
  `_validate_requirement` never checks `source_url`. The research prompt says
  *"Do NOT return an empty requirements list."*
- **345 industry-specific rows carry no industry tag**, so `_filter_requirements_for_company`
  serves them to every tenant regardless of industry.
- **424 rows have no citation at all.** `structured_source_id` is linked on **0** rows while 414
  rows nonetheless claim `tier_1_government`.
- **`verification_outcomes` has never held a row** — the confidence-calibration loop was built
  and never fed.
- The federal jurisdiction row holds 50 requirements, **none of them FMLA, HIPAA, EMTALA, or the
  OSHA standards**, which is why `fmla` reads MISS in every US checklist.

---

## 9. Deferred (Phase 3)

An LLM veracity judge: blind re-research of a stratified sample with search grounding, an
adversarial refute pass on disagreements, and writes into `verification_outcomes` to revive
`/compliance/calibration/stats`. The findings table already reserves `judge_verdict`,
`judge_confidence`, `judge_sources`, and `verification_outcome_id` for it.

Pipeline fixes the evals motivate but do not perform (measure first, then change):
a write-gate before the catalog upsert; requiring `source_url` in `_validate_requirement`;
removing the never-return-empty prompt pressure; an industry-tag backfill driven by
`industry_keysets.py`; linking `structured_source_id` on Tier-1 upserts; and fixing
`get_missing_regulations` to apply its country filter for the US.
