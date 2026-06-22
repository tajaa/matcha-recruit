-- Real WC state rate changes for CA + NY (free, authoritative public filings).
-- Replaces the demo `seed (headline est.)` placeholders. Idempotent.
--
-- CA is NOT an NCCI state — its rating bureau is the WCIRB. The Insurance
-- Commissioner approved the Sept 1, 2025 advisory pure premium rates at an
-- average $1.52 per $100 of payroll, +8.7% vs the approved 9/1/2024 rates.
-- (The 9/1/2026 WCIRB proposal is +10.4%, not yet approved as of this seed.)
--   https://www.wcirb.com/news/press-releases/insurance-commissioner-issues-september-1-2025-pure-premium-rate-filing-decision
--
-- NY is also independent — its board is the NYCIRB. The Oct 1, 2025 loss cost
-- filing approved by DFS produced a -4.4% loss cost level change.
--   https://www.nycirb.org/filings/2025/2025_Loss_Cost_Filing.pdf
--
-- Run (dev):  docker exec -i matcha-postgres psql -U matcha -d matcha < server/scripts/seed_wc_state_rates_real.sql

BEGIN;

-- Drop the demo placeholders for these two states so the real (older effective
-- date) rows win the `DISTINCT ON (state) ORDER BY effective_date DESC` lookup.
DELETE FROM wc_state_rates WHERE state IN ('CA', 'NY') AND source LIKE 'seed%';

INSERT INTO wc_state_rates (state, loss_cost_change_pct, effective_date, trend, source, note) VALUES
 ('CA',  8.7, '2025-09-01', 'increase', 'WCIRB 9/1/2025',
   'Approved advisory pure premium rates avg $1.52/$100 payroll, +8.7% vs 9/1/2024 (WCIRB; 9/1/2026 proposal +10.4%)'),
 ('NY', -4.4, '2025-10-01', 'decrease', 'NYCIRB 10/1/2025',
   'DFS-approved loss cost level change -4.4% (NYCIRB Oct 1 2025 filing)')
ON CONFLICT ON CONSTRAINT uq_wc_state_rate DO UPDATE SET
  loss_cost_change_pct = EXCLUDED.loss_cost_change_pct,
  trend = EXCLUDED.trend,
  source = EXCLUDED.source,
  note = EXCLUDED.note;

COMMIT;
