-- Real, PUBLIC workers'-comp loss-cost changes for the broker WC rate overlay.
-- Replaces the illustrative demo seed for the states below with sourced values
-- (NCCI 2026 filing season + independent bureaus). No licensed NCCI manual data
-- here — only publicly-reported state loss-cost % changes. source='public-filing-2026'.
--
-- Sources (retrieved 2026-06):
--   CT -3.8%  blog.pia.org/2025/10/31 (CID approved, eff 1/1/2026)
--   NH -6.1%  blog.pia.org/2025/08/08 (NHID approved, eff 1/1/2026)
--   WV -13.5% wtap.com 2025-08-11 (NCCI filed, eff 1/1/2026)
--   FL -6.9%  insurancejournal.com 2025-11-18 (OIR approved voluntary, eff 1/1/2026)
--   IL -1.2%  ncci.com IL state advisory (voluntary loss cost, eff 1/1/2026)
--   GA -8.8%  ncci.com GA state advisory (voluntary, eff 3/1/2026)
--   TN -2.0%  ncci.com TN state advisory (voluntary, eff 3/1/2026)
--   NV +21.6% riskandinsurance.com (NCCI 2026 — largest increase; verify exact eff date)
--   CA +8.7%  wcirb.com (approved 9/1/2025; +10.4% proposed 9/1/2026 pending CDI)
--   US -5.0%  ncci.com 2026 State of the Line (avg premium-impact estimate)
--
-- Idempotent: clears prior rows for these states, then inserts the sourced values.

DELETE FROM wc_state_rates WHERE state IN ('CT','NH','WV','FL','IL','GA','TN','NV','CA','US');

INSERT INTO wc_state_rates (state, loss_cost_change_pct, effective_date, trend, source, note) VALUES
  ('US', -5.0, '2026-01-01', 'decrease', 'public-filing-2026', 'NCCI 2026 avg premium-impact estimate (range -15.6% to +21.6%)'),
  ('CA',  8.7, '2025-09-01', 'increase', 'public-filing-2026', 'WCIRB approved 9/1/2025; +10.4% proposed 9/1/2026 pending CDI'),
  ('IL', -1.2, '2026-01-01', 'decrease', 'public-filing-2026', 'NCCI 2026 voluntary loss cost'),
  ('FL', -6.9, '2026-01-01', 'decrease', 'public-filing-2026', 'FL OIR approved voluntary — 9th straight annual cut'),
  ('CT', -3.8, '2026-01-01', 'decrease', 'public-filing-2026', 'CID approved 2026'),
  ('NH', -6.1, '2026-01-01', 'decrease', 'public-filing-2026', 'NHID approved 2026'),
  ('WV',-13.5, '2026-01-01', 'decrease', 'public-filing-2026', 'NCCI filed 2026'),
  ('GA', -8.8, '2026-03-01', 'decrease', 'public-filing-2026', 'NCCI 2026 voluntary'),
  ('TN', -2.0, '2026-03-01', 'decrease', 'public-filing-2026', 'NCCI 2026 voluntary'),
  ('NV', 21.6, '2026-03-01', 'increase', 'public-filing-2026', 'NCCI 2026 — largest increase; verify exact effective date');
