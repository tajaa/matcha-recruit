# WC data (class codes + BLS injury-rate benchmark)

## BLS injury-rate benchmark (#22)

Real BLS SOII injury/illness incidence rates (TRC + DART) by NAICS — replaces the
17 hardcoded 2-digit sector medians in `wc_benchmarks.py` with ~1,000 codes at
2–6 digit granularity, so a client's TRIR/DART benchmarks against its *actual*
industry (e.g. nursing care `6231` TRC 6.3 vs the health-care sector `62` ~4.4).

- **Source (free/public, no login — bot-blocked so downloaded by hand):**
  BLS Table 1 — incidence rates by industry & case type
  ([page](https://www.bls.gov/web/osh/table-1-industry-rates-national.htm)).
  Saved here as `bls_table1_industry_rates_2024.pdf` (gitignored; re-download to refresh).
- **Build:** `cd server && ./venv/bin/python scripts/wc_data/build_bls_rates.py`
  → regenerates `app/matcha/services/bls_injury_rates_2024.py` (GENERATED static
  dict; needs `pdftotext`/poppler). 2-digit ranges (31-33/44-45/48-49) expanded
  to each member code.
- **Use:** `wc_benchmarks.lookup_benchmark(industry, naics=None)` prefers the most
  detailed NAICS (explicit `naics` → `INDUSTRY_TO_NAICS` subsector → 2-digit
  sector), walking up to the sector if a code has no row. No DB/migration — it's
  a static module compiled into the image; nothing to seed in prod.

---

# WC class-code data (California, real)

Real California WC class codes + advisory pure premium rates, replacing the
~10 illustrative demo rows in `wc_class_codes` (state `US`, `source='seed (demo)'`).
**California only** — CA has its own bureau (WCIRB), independent of NCCI.

## Sources (both free, public)

| File | What | Source |
|---|---|---|
| `wcirb_advisory_pure_premium_rates_09012026.csv` | `class_code,rate` (advisory pure premium per $100 payroll), no header | WCIRB **Sep 1 2026 Pure Premium Rate Filing** → "Advisory Pure Premium Rates → Delimited File" (downloaded by hand from [wcirb.com](https://www.wcirb.com/filings-and-plans/regulatory-and-pure-premium-rate-filings)) |
| (downloaded at build) `WCIRB_ClassCodes.xlsx` | class code + description ("Wording"), 2013–2025 sheets | CA DIR/DWC mirror — `https://www.dir.ca.gov/dwc/WCIS/WCIRB_ClassCodes.xlsx` (no login) |
| `ca_wc_class_codes_2026.csv` | **generated** join: `state,class_code,description,base_rate` | output of `build_ca_class_codes.py` |

## Regenerate

```bash
cd server && ./venv/bin/python scripts/wc_data/build_ca_class_codes.py
```

Downloads the CA-gov xlsx (descriptions), joins the WCIRB rates CSV, writes
`ca_wc_class_codes_2026.csv` (~494 codes, ~492 with a rate).

## Load

- **Dev / scripted:** `./venv/bin/python scripts/wc_data/seed_ca_wc_class_codes.py`
  (idempotent upsert on `(state, class_code)`; `source='WCIRB 9/1/2026 advisory pure premium'`).
- **Prod:** upload `ca_wc_class_codes_2026.csv` via the admin **WC rates → import class codes**
  endpoint (`POST /admin/wc-rates/class-codes`) — same columns. No migration needed
  (table + endpoint already exist).

## Notes / license

- `base_rate` here is WCIRB's **advisory pure premium rate** (loss cost, no expense
  loading) — labelled via `source`, distinct from an NCCI "manual rate". Directional
  for the viewer, not a quote.
- WCIRB material is copyrighted; copies may be made **only to facilitate workers'-comp
  insurance** (our use). Do **not** redistribute raw, and do **not** substitute NCCI
  Scopes data here — NCCI is licensed. Other independent-bureau states (NY/NJ/PA/MI/WI…)
  publish their own files if we expand beyond CA.
