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
