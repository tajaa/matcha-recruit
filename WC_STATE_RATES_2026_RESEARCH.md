# Workers' Comp State Rate Data — 2026 Research (free, cited)

Research compiled 2026-06-21. Target metric = **overall voluntary-market loss cost level change %** (the `wc_state_rates.loss_cost_change_pct` column), for each state's most recent filing effective in 2026. For independent-bureau states (CA, NY, NJ, PA, DE, MA, MI, MN, WI) and monopolistic state funds (ND, OH, WA, WY) the equivalent advisory-rate / pure-premium / fund base-rate change is used.

**No paid dataset used.** Every number below is from a free public source: state DOI orders/bulletins, state rating-bureau circulars, NCCI per-state advisory PDFs (downloaded + `pdftotext`-extracted), or reputable trade press (Insurance Journal, PIA Northeast, WorkCompWire, Claims Journal).

There is **no single free bulk file** for loss-cost-change % — NCCI is the rating bureau for ~38 states and its consolidated data is licensed. The per-state *approved loss-cost-level change* is public regulatory record, gathered here one state at a time.

## Status legend
- **approved** — confirmed by a state DOI order / rating-bureau circular / reputable trade press reporting approval.
- **filed** — number is from NCCI's per-state advisory PDF (the *filed/proposed* figure); no separate approval order located, but most effective dates have already passed and NCCI filings are typically adopted as filed.
- **null** — no public figure found; left blank per decision (UI shows "no data", not a guess).
- **repo** — already seeded in migration `wcdeep01` as `source='NCCI 2026 filing'` (not re-verified this pass; cross-check pending).

## Confirmed data (41 jurisdictions + US national)

| State | LC change % | Effective | Status | Source |
|---|---|---|---|---|
| AL | -4.5 | 2026-03-01 | approved¹ | [Insurance Journal](https://www.insurancejournal.com/news/southeast/2025/10/20/844265.htm) — NCCI filed, ALDOI hearing 12/4/2025, eff date passed; DOI order not located |
| AK | -3.7 | 2025-11-26 | approved | [WorkCompWire](https://www.workcompwire.com/2025/12/alaska-doi-approves-workers-comp-rate-reduction/) — AK DOI Regulatory Order R 25-03 (latest cycle; no 2026-eff filing yet) |
| AZ | -6.7 | 2026-01-01 | approved | [Insurance Journal](https://www.insurancejournal.com/news/west/2025/11/17/847715.htm) — DIFI; 12th straight yr down |
| CA | 8.7 | 2025-09-01 | approved | [WCIRB 9/1/2025](https://www.wcirb.com/news/press-releases/insurance-commissioner-issues-september-1-2025-pure-premium-rate-filing-decision) — approved advisory pure premium avg $1.52/$100, +8.7% (9/1/2026 proposal +10.4%). *Already in your seed.* |
| CO | -6.9 | 2026-01-01 | approved | [CO DOI Commissioner's Order](https://doi.colorado.gov/sites/doi/files/documents/Commissioner's%20Order%20for%20NCCI's%20Loss%20Cost%20Filing%20-%20Effective%20Jan.%201,%202026.pdf) — 12th straight yr down |
| CT | -3.8 | 2026-01-01 | approved | [PIA Northeast](https://blog.pia.org/2025/10/31/conn-ncci-2026-wc-loss-cost-decrease-of-3-8-approved/) — Commissioner Mais approved |
| DC | 1.7 | 2026-01-01 | filed | [NCCI DC advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_DC_2025.pdf) — filed 8/20/2025; **increase**; DISB order not located |
| DE | -11.6 | 2025-12-01 | approved | [DE Gov press](https://news.delaware.gov/2025/10/23/navarro-announces-ninth-consecutive-workers-comp-rate-decrease/) — DCRB Filing 2501 (voluntary loss cost; residual -9.08%); 9th straight |
| FL | -6.9 | 2026-01-01 | approved | [FLOIR Final Order](https://floir.gov/home/2025/11/17/commissioner-mike-yaworsky-approves-6.9--rate-decrease-for-florida-workers--compensation-policies--marking-9th-consecutive-year-of-decreases) — FL files *rates*; 9th straight cut |
| GA | -8.8 | 2026-03-01 | filed | [NCCI GA advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_GA_2025.pdf) — eff date passed; SBWC/OCI order not located |
| HI | -4.4 | 2026-01-01 | filed | [NCCI HI advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_HI_2025.pdf) — "-4.4% voluntary, eff 1/1/2026" (pdftotext-confirmed) |
| ID | -2.5 | 2026-01-01 | approved | [Idaho DOI press](https://doi.idaho.gov/pressrelease/idahos-workers-compensation-rates-to-drop-again-in-2026/) — DOI reviewed/accepted; 9th straight |
| IL | -1.2 | 2026-01-01 | filed | [NCCI IL advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_IL_2025.pdf) — voluntary LC (advisory rate -0.1%); IL DOI doesn't formally approve |
| IN | -6.1 | 2026-01-01 | approved | [ICRB Circular 2025-08](https://www.icrb.net/wp-content/uploads/2025/12/Rate-Filing-Circular.pdf) — IDOI approved -6.1% advisory LC (Indiana = ICRB, not NCCI) |
| IA | -2.5 | 2026-01-01 | approved | [Iowa Ins Div](https://iid.iowa.gov/legal-resources/data/workers-compensation-rate-filing-and-order) — "Order effective 1/1/2026"; IA is a rate state |
| MA | -14.6 | 2024-07-01 | approved | [Agency Checklists](https://agencychecklists.com/2024/06/24/doubling-down-doi-orders-a-14-6-workers-comp-rate-reduction-71543/) — WCRIBMA/DOI statewide rate cut. **Latest in effect**; 2025 filing (+7.1%) disapproved 5/15/2025, rates held |
| MD | -12.3 | 2026-01-01 | repo | `wcdeep01` `NCCI 2026 filing` — cross-check pending |
| ME | -4.8 | 2026-04-01 | repo | `wcdeep01` `NCCI 2026 filing` — cross-check pending |
| MI | -3.3 | 2026-01-01 | approved | [CAOM 2026 PDF](https://caom.com/Portals/0/Uploads/Rates/DCA/CAOM%202026.pdf) — advisory pure premium (open-competition); Circular #361, 8/21/2025 |
| MN | -4.6 | 2026-01-01 | approved | [MWCIA / MN DLI](https://www.dli.mn.gov/sites/default/files/pdf/wcac_mwcia_presentation_100825.pdf) — pure premium base rate (-6.2% incl. surcharges) |
| MO | 1.3 | 2026-01-01 | repo | `wcdeep01` `NCCI 2026 filing` — emerging increase; cross-check pending |
| MT | 0.5 | 2026-01-01² | repo | `wcdeep01` `NCCI 2026 filing` — cross-check pending |
| NH | -6.1 | 2026-01-01 | approved | [Insurance Journal](https://www.insurancejournal.com/news/east/2025/08/06/834769.htm) — NHID approved; 14th straight cut |
| NJ | -4.3 | 2026-01-01 | approved | [NJ CRIB Circular 2510](https://www.njcrib.com/Search/ViewPDF?id=1364) — DOBI approved -4.3% overall rate level (CRIB, not NCCI) |
| NV | 21.9 | 2026-01-01² | repo | `wcdeep01` `NCCI 2026 filing` — **large increase**, the national outlier; cross-check pending |
| NY | -4.4 | 2025-10-01 | approved | [NYCIRB 10/1/2025](https://www.nycirb.org/filings/2025/2025_Loss_Cost_Filing.pdf) — DFS-approved loss cost level. *Already in your seed.* |
| OH | -1.0 | 2026-07-01 | approved | [WorkCompWire](https://www.workcompwire.com/2026/03/ohio-bwc-board-of-directors-approves-1-workers-comp-rate-cut/) — Ohio BWC private-employer avg base-rate cut (Board 3/2/2026) |
| OK | -4.7 | 2026-01-01 | approved | NCCI OK filing — voluntary & assigned-risk both -4.7%, eff 1/1/2026 (per NCCI state-advisory summary; confirm DOI order) |
| OR | -3.3 | 2026-01-01 | approved | [Oregon DCBS 2026 rate notice](https://www.oregon.gov/DCBS/reports/cost/Documents/3256-WCD-DO-rate-postcard-notice-2026.pdf) — DCBS-set pure premium; 13th straight cut |
| PA | -1.22 | 2026-04-01 | approved | [WorkCompWire](https://www.workcompwire.com/2026/04/pa-insurance-department-approves-1-22-loss-cost-reduction-for-workers-comp/) — PCRB Proposal C-387, PID approved (PCRB, not NCCI) |
| RI | -2.5 | 2026-08-01 | approved | [Insurance Journal](https://www.insurancejournal.com/news/east/2026/05/05/868608.htm) — RI DBR approved 5/5/2026 (industrial classes; F-classes -12.9%) |
| SC | -0.4 | 2026-04-01 | filed | [NCCI SC advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_SC_2025.pdf) — eff date passed (SC mandatory adoption); DOI order not retrievable |
| SD | -5.1 | 2026-07-01 | filed | NCCI SD advisory — -5.1% voluntary (-4.9% assigned risk); future eff date |
| TN | -2.0 | 2026-03-01 | approved | [WorkCompWire](https://www.workcompwire.com/2026/02/tn-workers-comp-rates-decline-for-13th-consecutive-year-in-2026/) — TDCI order signed 12/23/2025; 13th straight |
| TX | -3.8 | 2026-07-01 | approved | [TDI Bulletin B-0001-26](https://www.tdi.texas.gov/bulletins/2026/b-0001-26.html) — TDI accepted NCCI advisory, avg -3.8% (announced 2/27/2026) |
| UT | -4.5 | 2026-02-01 | filed | [NCCI UT advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_UT_2025.pdf) — filed 8/27/2025; UT Ins Dept order not retrievable |
| VA | -7.7 | 2026-04-01 | filed | [NCCI VA advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_VA_2025.pdf) — -7.7% voluntary LC |
| WA | 4.9 | 2026-01-01 | approved | [WA L&I](https://lni.wa.gov/news-events/article/25-32) — state fund avg premium rate **increase** for 2026 (final after 10/2025 hearings) |
| WI | -3.2 | 2025-10-01 | approved | [WCRB Circular 3264](https://www.wcrb.org/circulars/CircularLetters2025/CIRCULAR_LETTER_3264_10_1_25__Rate_Revision.pdf) — OCI-approved full rate change (administered pricing) |
| WV | -13.5 | 2026-01-01 | filed | [NCCI WV advisory PDF](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_WV_2025.pdf) — -13.5% voluntary (-13.9% assigned risk); WV DOI order confirms 1/1/2026 eff date |
| WY | -15.0 | 2026-01-01 | approved | [WorkCompWire](https://www.workcompwire.com/2025/11/wy-governor-approves-15-workers-comp-base-rate-decrease-for-2026/) — state fund; Gov. Gordon approved (class range -2.25% to -27.75%) |
| US | -4.2 | 2026-01-01 | repo | `wcdeep01` national avg (narrowed from -6.0% in 2024) |

¹ AL: number is solid (NCCI filed, eff date passed, no reported rejection); explicit DOI approval order not located.
² MT and NV: NCCI's *Anticipated Effective Dates* PDF lists MT eff **7/1/2026** and NV eff **3/1/2026**, but the repo `wcdeep01` rows use 2026-01-01. Reconcile effective dates when verifying these.

## Null states (no public figure — left blank per decision)

| State | Effective (anticipated) | Why null | Most recent REAL number (prior cycle, for reference only) |
|---|---|---|---|
| AR | 2026-07-01 | 2026 filing not public yet (AR files March for July eff) | -8.8% eff 2025-07-01 ([NCCI AR advisory](https://www.ncci.com/Articles/Documents/II_StateAdvisoryForumState_AR_2025.pdf)) |
| KS | 2026-01-01 | No public figure found | — |
| KY | 2026-01-01 | No public figure found | — |
| LA | 2026-05-01 | No public figure found | — |
| MS | 2026-03-01 | No public figure found | — |
| NC | 2026-04-01 | NC Rate Bureau (NCRB) figure not retrieved | — |
| ND | — | WSI state fund publishes no avg premium-rate-change %; recent relief = 50% dividend credit | — |
| NE | 2026-02-01 | Filing confirmed effective 2/1/2026 but signed % behind NCCI auth; no DOI/trade-press number | — |
| NM | 2026-01-01 | 2026 advisory PDF 404s; OSI published no 2025/2026 order | -11.7% eff 2025-01-01 ([NCCI 2024 advisory](https://www.ncci.com)) |
| VT | 2026-04-01 | Advisory loss cost approved & effective 4/1/2026 (VT DFR) but overall %-change not published in any reachable source | — |

> KS, KY, LA, MS, NC are the genuine gaps worth a second research pass (each NCCI/NCRB; numbers exist in the licensed feed, just not surfaced free). NM/AR have a real prior-cycle number available if a fallback is acceptable later.

## Ready-to-load — SQL seed (idempotent)

Mirrors your `seed_wc_state_rates_real.sql` pattern. Drops the `seed (headline est.)` placeholders for the states it replaces, then upserts on `uq_wc_state_rate (state, effective_date)`. Null states get their pct nulled + an honest source. **Not yet applied to any DB.**

```sql
BEGIN;

-- Replace headline-estimate placeholders for states we now have real data for.
DELETE FROM wc_state_rates
 WHERE source = 'seed (headline est.)'
   AND state IN ('AL','AK','AZ','DE','GA','HI','ID','IL','IN','IA','MA','MI','MN',
                 'NH','NJ','OH','OK','OR','PA','RI','SC','SD','TX','UT','VA','WA','WI','WV','WY');

INSERT INTO wc_state_rates (state, loss_cost_change_pct, effective_date, trend, source, note) VALUES
 ('AL', -4.5, '2026-03-01', 'decrease', 'NCCI 2026 (filed)',   'NCCI filed; ALDOI hearing 12/4/2025; eff date passed'),
 ('AK', -3.7, '2025-11-26', 'decrease', 'AK DOI R 25-03',      'DOI Regulatory Order; latest cycle'),
 ('AZ', -6.7, '2026-01-01', 'decrease', 'AZ DIFI 2026',        '12th straight year of decreases'),
 ('DE',-11.6, '2025-12-01', 'decrease', 'DCRB Filing 2501',    'Voluntary loss cost; residual -9.08%; 9th straight'),
 ('GA', -8.8, '2026-03-01', 'decrease', 'NCCI 2026 (filed)',   'NCCI advisory; SBWC/OCI order not located'),
 ('HI', -4.4, '2026-01-01', 'decrease', 'NCCI 2026 (filed)',   'NCCI advisory voluntary LC'),
 ('ID', -2.5, '2026-01-01', 'decrease', 'ID DOI 2026',         'DOI reviewed/accepted; 9th straight'),
 ('IL', -1.2, '2026-01-01', 'decrease', 'NCCI 2026 (filed)',   'Voluntary LC; advisory rate -0.1%'),
 ('IN', -6.1, '2026-01-01', 'decrease', 'ICRB Circ 2025-08',   'IDOI approved advisory LC (ICRB state)'),
 ('IA', -2.5, '2026-01-01', 'decrease', 'IA Ins Div 2026',     'Order eff 1/1/2026; rate state'),
 ('MA',-14.6, '2024-07-01', 'decrease', 'MA DOI 2024',         'WCRIBMA/DOI; latest in effect (2025 +7.1% disapproved)'),
 ('MI', -3.3, '2026-01-01', 'decrease', 'CAOM 2026',           'Advisory pure premium; Circular #361'),
 ('MN', -4.6, '2026-01-01', 'decrease', 'MWCIA 2026',          'Pure premium base rate (-6.2% incl surcharges)'),
 ('NH', -6.1, '2026-01-01', 'decrease', 'NHID 2026',           '14th straight cut'),
 ('NJ', -4.3, '2026-01-01', 'decrease', 'NJ CRIB 2510',        'DOBI approved overall rate level (CRIB state)'),
 ('OH', -1.0, '2026-07-01', 'decrease', 'Ohio BWC 2026',       'Private-employer avg base-rate cut'),
 ('OK', -4.7, '2026-01-01', 'decrease', 'NCCI 2026',           'Voluntary & assigned-risk both -4.7%'),
 ('OR', -3.3, '2026-01-01', 'decrease', 'OR DCBS 2026',        'DCBS pure premium; 13th straight'),
 ('PA', -1.22,'2026-04-01', 'decrease', 'PCRB C-387',          'PID approved (PCRB state)'),
 ('RI', -2.5, '2026-08-01', 'decrease', 'RI DBR 2026',         'Industrial classes; F-classes -12.9%'),
 ('SC', -0.4, '2026-04-01', 'decrease', 'NCCI 2026 (filed)',   'Mandatory adoption; eff date passed'),
 ('SD', -5.1, '2026-07-01', 'decrease', 'NCCI 2026 (filed)',   'Voluntary; assigned risk -4.9%'),
 ('TX', -3.8, '2026-07-01', 'decrease', 'TDI B-0001-26',       'TDI accepted NCCI advisory'),
 ('UT', -4.5, '2026-02-01', 'decrease', 'NCCI 2026 (filed)',   'Filed 8/27/2025'),
 ('VA', -7.7, '2026-04-01', 'decrease', 'NCCI 2026 (filed)',   'Voluntary LC'),
 ('WA',  4.9, '2026-01-01', 'increase', 'WA L&I 2026',         'State fund avg premium increase'),
 ('WI', -3.2, '2025-10-01', 'decrease', 'WCRB Circ 3264',      'OCI-approved full rate change'),
 ('WV',-13.5, '2026-01-01', 'decrease', 'NCCI 2026 (filed)',   'Voluntary; assigned risk -13.9%'),
 ('WY',-15.0, '2026-01-01', 'decrease', 'WY State Fund 2026',  'Gov. approved; class range -2.25% to -27.75%')
ON CONFLICT ON CONSTRAINT uq_wc_state_rate DO UPDATE SET
  loss_cost_change_pct = EXCLUDED.loss_cost_change_pct,
  trend  = EXCLUDED.trend,
  source = EXCLUDED.source,
  note   = EXCLUDED.note;

-- Null the states with no public figure (show "no data", not a guess).
UPDATE wc_state_rates
   SET loss_cost_change_pct = NULL, trend = 'flat',
       source = 'no public filing data (2026-06-21)',
       note   = 'No free public loss-cost figure located; pending licensed NCCI/bureau feed'
 WHERE source = 'seed (headline est.)'
   AND state IN ('AR','KS','KY','LA','MS','NC','ND','NE','NM','VT');

COMMIT;
```

> CO, CT, FL, MD, ME, MO, MT, NV, DC are intentionally left to the existing `wcdeep01` rows (already `NCCI 2026 filing`). CA/NY are your existing real seed. To overwrite any of those with the cited values above, add them to the INSERT.

## Methodology notes
- NCCI per-state advisory PDFs (`II_StateAdvisoryForumState_{ST}_2025.pdf`) render as compressed binary via WebFetch — download with `curl -sL` + `pdftotext -layout` to read exact %.
- NCCI *Anticipated Effective Dates* PDF (`II_Anticipated-Effective-Dates-State.pdf`) is the authoritative free list of all 38 NCCI-state effective dates — used to anchor each state's filing.
- Bonus free cross-state dataset (different metric — rate *levels*, not change %): **Oregon DCBS Premium Rate Ranking Study 2024** (pub. June 2025), all 51 jurisdictions' premium index rate per $100 payroll — [study PDF](https://www.oregon.gov/DCBS/DCBSPubs/reports/general/prem-rpt/24-2083.pdf) (image-based; needs OCR). Good source for `wc_class_codes.base_rate` context.
