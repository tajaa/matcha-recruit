-- ============================================================================
-- Demo seed for the two 2026-06-22 features, on the Regina George LLC book:
--   1. EMR trajectory automation  → Bags (3e69de7a…): WC class-payroll exposures
--      + a loss-run triangle (rising incurred) so the directional PROXY renders,
--      + flips the 2026 mod to source='worksheet' to show the badge.
--   2. Pay-equity report depth     → Sea Cafe (19e02494…): enables workforce_compliance
--      + drops one Barista below the pay band so the remediation $ is non-zero.
--
-- broker_id 574c50d6-e3d2-4bef-a4d7-4e153b6da053 · user fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566
-- DEV target. Idempotent. INSERT/UPDATE only (no DDL). No emails generated.
--
-- PREREQS:
--   • migration wcmodsrc01 applied (adds company_wc_mods.source) — the worksheet
--     UPDATE below needs it.
--   • seed_demo_employee_roles.sql already applied (gives Sea Cafe repeated roles);
--     it is, in the standard dev book.
--
-- Run:  docker exec -i matcha-postgres psql -U matcha -d matcha < server/scripts/seed_emr_payequity_demo.sql
-- ============================================================================

BEGIN;

-- ── 1a. Bags WC class-payroll exposures (expected-loss base for the proxy) ───
-- state 'US' so it joins the US reference base rates (5403=8.50, 5022=7.00,
-- 8810=0.14 per $100) → expected annual losses ≈ $275,700.
DELETE FROM company_wc_class_exposures
 WHERE company_id='3e69de7a-0c0e-4a34-ab7b-3e9462756516' AND note='seed:emr-demo';
INSERT INTO company_wc_class_exposures (company_id, broker_id, class_code, state, payroll, headcount, note, created_by) VALUES
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','5403','US',2000000,18,'seed:emr-demo','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','5022','US',1500000,12,'seed:emr-demo','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','8810','US', 500000, 6,'seed:emr-demo','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566');

-- ── 1b. Bags loss-run triangle (WC), 3 valuations → proxy ≈ 0.91 → 1.11 → 1.20 ──
-- echoes the rising real mod (1.05 → 1.18 → 1.32). Incurred = paid + reserved.
INSERT INTO wc_loss_runs (broker_id, subject_kind, subject_id, line, policy_period_label, policy_period_start, valuation_date, claim_count, open_count, paid, reserved, source, note, created_by) VALUES
 -- PY2024 developed across three valuations
 ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','company','3e69de7a-0c0e-4a34-ab7b-3e9462756516','wc','2024','2024-01-01','2024-12-31', 9,4,150000,100000,'seed:emr-demo',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','company','3e69de7a-0c0e-4a34-ab7b-3e9462756516','wc','2024','2024-01-01','2025-12-31', 9,2,220000,100000,'seed:emr-demo',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','company','3e69de7a-0c0e-4a34-ab7b-3e9462756516','wc','2024','2024-01-01','2026-12-31', 9,1,300000, 50000,'seed:emr-demo',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 -- PY2025 across two valuations
 ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','company','3e69de7a-0c0e-4a34-ab7b-3e9462756516','wc','2025','2025-01-01','2025-12-31',11,6,180000,110000,'seed:emr-demo',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','company','3e69de7a-0c0e-4a34-ab7b-3e9462756516','wc','2025','2025-01-01','2026-12-31',11,3,250000, 90000,'seed:emr-demo',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 -- PY2026 at its first valuation
 ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','company','3e69de7a-0c0e-4a34-ab7b-3e9462756516','wc','2026','2026-01-01','2026-12-31',13,9,200000,100000,'seed:emr-demo',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566')
ON CONFLICT ON CONSTRAINT uq_wc_loss_runs DO NOTHING;

-- ── 1c. Mark Bags' latest mod as captured from a worksheet (source badge) ────
UPDATE company_wc_mods
   SET source='worksheet', note='Auto-extracted from experience-rating worksheet'
 WHERE company_id='3e69de7a-0c0e-4a34-ab7b-3e9462756516' AND policy_period_start='2026-01-01';

-- ── 2a. Pay-equity: enable workforce_compliance for Sea Cafe ─────────────────
UPDATE companies
   SET enabled_features = COALESCE(enabled_features,'{}'::jsonb) || '{"workforce_compliance":true}'::jsonb
 WHERE id='19e02494-8427-44b5-9c1b-98064b7e94e1';

-- ── 2b. Drop one Sea Cafe Barista below the pay band → non-zero remediation ──
-- Baristas run $16.50–$22/hr; one at $13.00 lands under 80% of the role median,
-- so the report shows a below-band count + a remediation dollar figure.
UPDATE employees
   SET pay_rate=13.00, pay_classification='hourly'
 WHERE id = (SELECT id FROM employees
              WHERE org_id='19e02494-8427-44b5-9c1b-98064b7e94e1' AND job_title='Barista'
              ORDER BY id LIMIT 1);

COMMIT;
