# Golden facts

Hand-verified ground truth for the jurisdiction catalog. One file per jurisdiction.
These files are **truth**; the database stores only *results*. Code review is
curation review, and `git blame` is provenance.

## The rule

> A fact does not count until a human has opened its `authority_url` and confirmed
> the value on the page.

Facts drafted by research (`curated_by: claude-research`) ship with `verified_by:
null`. The admin Evals tab counts these and warns. **Set `verified_by` to your
name only after reading the primary source.** An unverified fact still runs — it
just should not be trusted to zero an accuracy score, which is why none of the
uncertain ones are marked `critical`.

## Severity

- `critical` — an unambiguous, high-confidence number whose wrongness invalidates
  everything downstream (a state minimum wage). **One critical failure zeroes the
  jurisdiction's accuracy subscore.** Use sparingly.
- `warn` — correct but brittle: region-split values, `text_contains` substrings
  that depend on the catalog's phrasing, tiered rules.
- `info` — informational.

## Comparators

| Comparator | Use when |
|---|---|
| `numeric_eq` | An exact figure. Compares `numeric_value`, falling back to parsing `current_value`. |
| `numeric_within` | An exact figure with a stated `tolerance`. |
| `text_contains` | The phrase is a **distinctive term of art** ("seventh consecutive day", "recognized hazards"). Never use a generic substring like "40" — it passes trivially and manufactures false confidence. |
| `date_eq` | Compares `effective_date`. |
| `exists` | The rule is qualitative or tiered, and all we can honestly assert is that the key is present. |

## Time

Law moves. Every fact carries `effective_from` and (where it reindexes)
`effective_to`, which is **exclusive**: a wage that changes on July 1 is not
asserted on July 1.

Only facts whose window contains today are compared. A fact whose window has
closed with **no successor for the same key** raises a `golden_stale` finding —
the fixture polices its own freshness instead of asserting last year's wage
forever. See `us_ca_los_angeles.json`, where the $17.87 → $18.42 pair is the
worked example.

CPI-indexed wages (LA, SF: every July 1; CA, NY: every January 1) need a successor
fact curated before the window closes. `legislation_watch` alerts are the prompt.

## Known gaps

Facts were dropped where the registry has no matching key, rather than inventing
one. Each is a real gap in `EXPECTED_REGULATION_KEYS`, not an omission here:

- **LA hotel worker minimum wage** ($25.00 + $4.25/hr health benefit from
  2026-07-01) — no `hotel_worker_minimum_wage` key.
- **SF Health Care Security Ordinance** expenditure rates ($4.11 / $2.74 per hour
  from 2026-01-01) — no `health_care` category.
- **SF Fair Chance Ordinance** — no `fair_chance` category; the nearest key is
  `anti_discrimination:salary_history_ban`, which is a different rule.
- **NYC Local Law 144** AI hiring bias audit — no `ai_hiring_audit` key under
  `anti_discrimination` (the `workforce_compliance` feature tracks this
  separately, per-tenant).
- **LA County unincorporated** ($18.47, distinct from LA City's $18.42) — needs
  its own county-level jurisdiction fixture.

## Provenance caveats on the current corpus

Recorded honestly so a verifier knows where to look hardest:

- `wagesla.lacity.gov`, `bca.lacity.gov`, and the amlegal LAMC library all return
  HTTP 403 to automated fetches. The LA City general minimum wage was confirmed
  from the official Office of Wage Standards 2026 increase memo (PDF); the other
  LA City values rest on official-page snippets plus corroborating legal sources.
- `sf.gov` renders the HCSO rate table as an image, so those values are not
  machine-readable from the primary page.
- CA `fast_food_minimum_wage` ($20.00) could not be confirmed as *current* — the
  DIR FAQ shows no post-2024 Fast Food Council adjustment. Marked `warn`.
- `us_ny_new_york_city.json` → `predictive_scheduling` carries a **wrong
  `authority_url`** (it points at the Local Law 144 rule). Fix it during
  verification.
