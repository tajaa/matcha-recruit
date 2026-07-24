-- Sunset Smile Dental Group — demo benefits data (plans, OE periods, elections,
-- roster + eligibility exceptions, renewal-risk radar).
--
-- Tenant: Sunset Smile Dental Group, company_id 287fffb5-ea50-40a2-bf07-6b5c2ca3c400
-- (Maria Chen, maria.chen@example.com). benefits_admin flag already on for this
-- company in dev; this pack pushes to prod via scripts/sync-test-tenants.sh
-- (which carries the companies row + enabled_features along with it).
--
-- Pinned UUID scheme (prefix b09e11e5 = "benefits"), so re-running or undoing
-- is exact and dev/prod rows share ids:
--   0001-... plans          0005-... elections
--   0002-... plan tiers      0006-... roster entries
--   0003-... OE periods      0007-... eligibility exceptions
--   0004-... life events     0008-... renewal-risk rows
--
-- No BEGIN/COMMIT/SAVEPOINT here — scripts/seed-prod.sh owns the transaction
-- envelope. Every INSERT is ON CONFLICT DO NOTHING (idempotent re-run). All
-- emails are @example.com (RFC 2606 reserved). Dates are relative to
-- CURRENT_DATE so the demo stays fresh whenever this is run.
--
-- Undo: benefits_sunset_dental.undo.sql

-- ---------------------------------------------------------------------------
-- 1. Plan catalog
-- ---------------------------------------------------------------------------
INSERT INTO benefit_plans (id, company_id, plan_type, name, carrier_name, description, status, waivable) VALUES
  ('b09e11e5-0001-4001-8001-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'medical', 'Delta Health PPO 500', 'Delta Health', 'Low-deductible PPO. $500 deductible, broad network, no referrals needed.', 'active', true),
  ('b09e11e5-0001-4001-8001-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'medical', 'Delta Health HMO Select', 'Delta Health', 'Lower-premium HMO. In-network only, PCP referrals required.', 'active', true),
  ('b09e11e5-0001-4001-8001-000000000003', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'dental', 'Guardian Dental Complete', 'Guardian', 'Preventive, basic, and major dental coverage.', 'active', true),
  ('b09e11e5-0001-4001-8001-000000000004', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'vision', 'VSP Vision Choice', 'VSP', 'Annual eye exam, lenses, and frame allowance.', 'active', true),
  ('b09e11e5-0001-4001-8001-000000000005', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'life', 'Unum Basic Life 1x', 'Unum', 'Employer-paid basic life, 1x annual salary.', 'active', false)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Plan tiers
-- ---------------------------------------------------------------------------
INSERT INTO benefit_plan_tiers (id, plan_id, coverage_tier, employee_cost, employer_cost, cost_period) VALUES
  -- Delta Health PPO 500
  ('b09e11e5-0002-4002-8002-000000000001', 'b09e11e5-0001-4001-8001-000000000001', 'employee_only', 120.00, 480.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000002', 'b09e11e5-0001-4001-8001-000000000001', 'employee_spouse', 310.00, 720.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000003', 'b09e11e5-0001-4001-8001-000000000001', 'employee_children', 280.00, 690.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000004', 'b09e11e5-0001-4001-8001-000000000001', 'family', 450.00, 980.00, 'monthly'),
  -- Delta Health HMO Select
  ('b09e11e5-0002-4002-8002-000000000005', 'b09e11e5-0001-4001-8001-000000000002', 'employee_only', 90.00, 420.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000006', 'b09e11e5-0001-4001-8001-000000000002', 'employee_spouse', 250.00, 640.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000007', 'b09e11e5-0001-4001-8001-000000000002', 'employee_children', 220.00, 610.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000008', 'b09e11e5-0001-4001-8001-000000000002', 'family', 380.00, 860.00, 'monthly'),
  -- Guardian Dental Complete
  ('b09e11e5-0002-4002-8002-000000000009', 'b09e11e5-0001-4001-8001-000000000003', 'employee_only', 15.00, 35.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000010', 'b09e11e5-0001-4001-8001-000000000003', 'employee_spouse', 28.00, 55.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000011', 'b09e11e5-0001-4001-8001-000000000003', 'employee_children', 25.00, 50.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000012', 'b09e11e5-0001-4001-8001-000000000003', 'family', 45.00, 85.00, 'monthly'),
  -- VSP Vision Choice
  ('b09e11e5-0002-4002-8002-000000000013', 'b09e11e5-0001-4001-8001-000000000004', 'employee_only', 6.00, 10.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000014', 'b09e11e5-0001-4001-8001-000000000004', 'employee_spouse', 11.00, 16.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000015', 'b09e11e5-0001-4001-8001-000000000004', 'employee_children', 10.00, 15.00, 'monthly'),
  ('b09e11e5-0002-4002-8002-000000000016', 'b09e11e5-0001-4001-8001-000000000004', 'family', 16.00, 22.00, 'monthly'),
  -- Unum Basic Life 1x (employer-paid; single tier)
  ('b09e11e5-0002-4002-8002-000000000017', 'b09e11e5-0001-4001-8001-000000000005', 'employee_only', 0.00, 8.00, 'monthly')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. Open enrollment periods — one closed (2026 plan year, already elected
--    and approved) + one currently open (2027 plan year, mid-review)
-- ---------------------------------------------------------------------------
INSERT INTO open_enrollment_periods (id, company_id, name, starts_on, ends_on, plan_year_start, status, opened_at, closed_at) VALUES
  ('b09e11e5-0003-4003-8003-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2026 Plan Year Open Enrollment', CURRENT_DATE - 260, CURRENT_DATE - 230, '2026-01-01', 'closed', NOW() - INTERVAL '260 days', NOW() - INTERVAL '229 days'),
  ('b09e11e5-0003-4003-8003-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2027 Plan Year Open Enrollment', CURRENT_DATE - 7, CURRENT_DATE + 21, '2027-01-01', 'open', NOW() - INTERVAL '7 days', NULL)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. Life events — one approved (active election window), one pending review
-- ---------------------------------------------------------------------------
INSERT INTO life_event_changes (id, company_id, employee_id, event_type, event_date, description, status, window_days, window_ends_on, reviewed_at) VALUES
  ('b09e11e5-0004-4004-8004-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '29fcba2e-a965-4405-bc27-1b26518024f5', 'marriage', CURRENT_DATE - 14, 'Recently married. Adding spouse to medical coverage.', 'approved', 30, CURRENT_DATE + 16, NOW() - INTERVAL '2 days'),
  ('b09e11e5-0004-4004-8004-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '0d961217-58b9-4eee-8fa9-dd41c7202020', 'birth_adoption', CURRENT_DATE - 3, 'Birth of child. Requesting to add dependent to coverage.', 'pending', 30, NULL, NULL)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. Elections
--    2026 window (closed, all approved) — the "current coverage" the portal
--    shows. 2027 window (open) — mixed submitted/draft, the admin review
--    queue demo. One life-event-triggered election off the marriage event.
-- ---------------------------------------------------------------------------
INSERT INTO benefit_elections
  (id, company_id, employee_id, open_enrollment_period_id, life_event_id, plan_type, plan_id, tier_id, waived, dependents, status, submitted_at, decided_at, effective_date)
VALUES
  -- 2026 medical (approved)
  ('b09e11e5-0005-4005-8005-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2c3554c3-2e74-4701-bef4-444ec4bea737', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000001', false, '[]', 'approved', NOW() - INTERVAL '250 days', NOW() - INTERVAL '235 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '9643f36f-dfb7-4454-89f0-203cf592c190', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000005', false, '[]', 'approved', NOW() - INTERVAL '250 days', NOW() - INTERVAL '235 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000003', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2aade054-a6a9-4edb-abe7-17b7ecb5c389', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000002', false, '[]', 'approved', NOW() - INTERVAL '249 days', NOW() - INTERVAL '234 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000004', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'fd135f95-169b-474c-b0e5-cb02bc9ec43c', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000001', false, '[]', 'approved', NOW() - INTERVAL '249 days', NOW() - INTERVAL '234 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000005', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '0d961217-58b9-4eee-8fa9-dd41c7202020', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000006', false, '[]', 'approved', NOW() - INTERVAL '248 days', NOW() - INTERVAL '233 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000006', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'f3b6ccd5-f4e3-407f-9c7f-26fd0861b897', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000001', false, '[]', 'approved', NOW() - INTERVAL '248 days', NOW() - INTERVAL '233 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000007', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '890f3750-553e-413a-bf3b-1f874be8ec64', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000005', false, '[]', 'approved', NOW() - INTERVAL '247 days', NOW() - INTERVAL '232 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000008', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '29fcba2e-a965-4405-bc27-1b26518024f5', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000002', false, '[]', 'approved', NOW() - INTERVAL '247 days', NOW() - INTERVAL '232 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000009', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'b30f714e-3d8d-483b-b73a-39e21ec4b153', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000004', false, '[{"name":"Elena Marek","relationship":"spouse","dob":"1988-04-12"},{"name":"Theo Marek","relationship":"child","dob":"2019-09-30"}]', 'approved', NOW() - INTERVAL '246 days', NOW() - INTERVAL '231 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000010', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '9d0b60a9-6355-4825-8bcf-b3ace5ddeff0', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000005', false, '[]', 'approved', NOW() - INTERVAL '246 days', NOW() - INTERVAL '231 days', '2026-01-01'),
  -- 2026 dental (approved)
  ('b09e11e5-0005-4005-8005-000000000011', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2c3554c3-2e74-4701-bef4-444ec4bea737', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000009', false, '[]', 'approved', NOW() - INTERVAL '250 days', NOW() - INTERVAL '235 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000012', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2aade054-a6a9-4edb-abe7-17b7ecb5c389', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000010', false, '[]', 'approved', NOW() - INTERVAL '249 days', NOW() - INTERVAL '234 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000013', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '0d961217-58b9-4eee-8fa9-dd41c7202020', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000009', false, '[]', 'approved', NOW() - INTERVAL '248 days', NOW() - INTERVAL '233 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000014', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '29fcba2e-a965-4405-bc27-1b26518024f5', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000010', false, '[]', 'approved', NOW() - INTERVAL '247 days', NOW() - INTERVAL '232 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000015', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '9d0b60a9-6355-4825-8bcf-b3ace5ddeff0', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000009', false, '[]', 'approved', NOW() - INTERVAL '246 days', NOW() - INTERVAL '231 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000016', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '8d458a70-1053-44e3-a87d-9b872d036143', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000009', false, '[]', 'approved', NOW() - INTERVAL '246 days', NOW() - INTERVAL '231 days', '2026-01-01'),
  -- 2026 vision (approved)
  ('b09e11e5-0005-4005-8005-000000000017', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2c3554c3-2e74-4701-bef4-444ec4bea737', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'vision', 'b09e11e5-0001-4001-8001-000000000004', 'b09e11e5-0002-4002-8002-000000000013', false, '[]', 'approved', NOW() - INTERVAL '250 days', NOW() - INTERVAL '235 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000018', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '0d961217-58b9-4eee-8fa9-dd41c7202020', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'vision', 'b09e11e5-0001-4001-8001-000000000004', 'b09e11e5-0002-4002-8002-000000000013', false, '[]', 'approved', NOW() - INTERVAL '248 days', NOW() - INTERVAL '233 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000019', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '8d458a70-1053-44e3-a87d-9b872d036143', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'vision', 'b09e11e5-0001-4001-8001-000000000004', 'b09e11e5-0002-4002-8002-000000000013', false, '[]', 'approved', NOW() - INTERVAL '246 days', NOW() - INTERVAL '231 days', '2026-01-01'),
  ('b09e11e5-0005-4005-8005-000000000020', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '8c87a48c-9240-45cc-a485-02fd473ec5c3', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'vision', 'b09e11e5-0001-4001-8001-000000000004', 'b09e11e5-0002-4002-8002-000000000013', false, '[]', 'approved', NOW() - INTERVAL '245 days', NOW() - INTERVAL '230 days', '2026-01-01'),
  -- 2026 dental — waived
  ('b09e11e5-0005-4005-8005-000000000021', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'fd135f95-169b-474c-b0e5-cb02bc9ec43c', 'b09e11e5-0003-4003-8003-000000000001', NULL, 'dental', NULL, NULL, true, '[]', 'approved', NOW() - INTERVAL '249 days', NOW() - INTERVAL '234 days', '2026-01-01'),
  -- 2027 medical — submitted, awaiting admin review
  ('b09e11e5-0005-4005-8005-000000000022', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2c3554c3-2e74-4701-bef4-444ec4bea737', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000001', false, '[]', 'submitted', NOW() - INTERVAL '3 days', NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000023', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '9643f36f-dfb7-4454-89f0-203cf592c190', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000005', false, '[]', 'submitted', NOW() - INTERVAL '3 days', NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000024', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2aade054-a6a9-4edb-abe7-17b7ecb5c389', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000002', false, '[]', 'submitted', NOW() - INTERVAL '2 days', NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000025', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '0d961217-58b9-4eee-8fa9-dd41c7202020', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000006', false, '[]', 'submitted', NOW() - INTERVAL '2 days', NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000026', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'f3b6ccd5-f4e3-407f-9c7f-26fd0861b897', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000001', false, '[]', 'submitted', NOW() - INTERVAL '1 days', NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000027', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '890f3750-553e-413a-bf3b-1f874be8ec64', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000005', false, '[]', 'submitted', NOW() - INTERVAL '1 days', NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000028', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '2c3554c3-2e74-4701-bef4-444ec4bea737', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000009', false, '[]', 'submitted', NOW() - INTERVAL '3 days', NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000029', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '0d961217-58b9-4eee-8fa9-dd41c7202020', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'dental', 'b09e11e5-0001-4001-8001-000000000003', 'b09e11e5-0002-4002-8002-000000000009', false, '[]', 'submitted', NOW() - INTERVAL '2 days', NULL, NULL),
  -- 2027 medical — still draft (not yet submitted)
  ('b09e11e5-0005-4005-8005-000000000030', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'fd135f95-169b-474c-b0e5-cb02bc9ec43c', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000001', false, '[]', 'draft', NULL, NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000031', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'b30f714e-3d8d-483b-b73a-39e21ec4b153', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000004', false, '[{"name":"Elena Marek","relationship":"spouse","dob":"1988-04-12"},{"name":"Theo Marek","relationship":"child","dob":"2019-09-30"}]', 'draft', NULL, NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000032', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '9d0b60a9-6355-4825-8bcf-b3ace5ddeff0', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000002', 'b09e11e5-0002-4002-8002-000000000005', false, '[]', 'draft', NULL, NULL, NULL),
  ('b09e11e5-0005-4005-8005-000000000033', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '8d458a70-1053-44e3-a87d-9b872d036143', 'b09e11e5-0003-4003-8003-000000000002', NULL, 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000001', false, '[]', 'draft', NULL, NULL, NULL),
  -- Life-event-triggered election (marriage) — adding spouse mid-year, outside any OE window
  ('b09e11e5-0005-4005-8005-000000000034', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '29fcba2e-a965-4405-bc27-1b26518024f5', NULL, 'b09e11e5-0004-4004-8004-000000000001', 'medical', 'b09e11e5-0001-4001-8001-000000000001', 'b09e11e5-0002-4002-8002-000000000002', false, '[{"name":"David Ramos","relationship":"spouse","dob":"1990-02-18"}]', 'submitted', NOW() - INTERVAL '5 days', NULL, NULL)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 6. Roster ingest — 20 rows mirror real employees (source='csv'), plus 2
--    fabricated rows that make the eligibility-exception detector fire.
-- ---------------------------------------------------------------------------
INSERT INTO benefit_roster_entries
  (id, company_id, source, external_id, employee_id, first_name, last_name, email, department, location, start_date, termination_date, employment_status, has_benefits_enrollment, employer_health_premium_monthly, gross_pay_period, snapshot_date)
VALUES
  ('b09e11e5-0006-4006-8006-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'maria.reyes0@example.com', '2c3554c3-2e74-4701-bef4-444ec4bea737', 'Maria', 'Reyes', 'maria.reyes0@example.com', 'Clinical', 'Sunset Blvd', '2025-12-26', NULL, 'active', true, 480.00, 3100.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'luis.ortiz1@example.com', '9643f36f-dfb7-4454-89f0-203cf592c190', 'Luis', 'Ortiz', 'luis.ortiz1@example.com', 'Clinical', 'Sunset Blvd', '2025-12-13', NULL, 'active', true, 420.00, 2950.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000003', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'priya.rivas2@example.com', '2aade054-a6a9-4edb-abe7-17b7ecb5c389', 'Priya', 'Rivas', 'priya.rivas2@example.com', 'Clinical', 'Sunset Blvd', '2025-11-30', NULL, 'active', true, 720.00, 3250.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000004', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'daniel.castro3@example.com', 'fd135f95-169b-474c-b0e5-cb02bc9ec43c', 'Daniel', 'Castro', 'daniel.castro3@example.com', 'Clinical', 'Sunset Blvd', '2025-11-17', NULL, 'active', true, 480.00, 2900.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000005', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'grace.rao4@example.com', '0d961217-58b9-4eee-8fa9-dd41c7202020', 'Grace', 'Rao', 'grace.rao4@example.com', 'Clinical', 'Sunset Blvd', '2025-11-04', NULL, 'active', true, 640.00, 3050.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000006', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'omar.costa5@example.com', 'f3b6ccd5-f4e3-407f-9c7f-26fd0861b897', 'Omar', 'Costa', 'omar.costa5@example.com', 'Clinical', 'Sunset Blvd', '2025-10-22', NULL, 'active', true, 480.00, 2800.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000007', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'chen.nguyen6@example.com', '890f3750-553e-413a-bf3b-1f874be8ec64', 'Chen', 'Nguyen', 'chen.nguyen6@example.com', 'Clinical', 'Sunset Blvd', '2025-10-09', NULL, 'active', true, 420.00, 2950.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000008', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'ana.ramos7@example.com', '29fcba2e-a965-4405-bc27-1b26518024f5', 'Ana', 'Ramos', 'ana.ramos7@example.com', 'Clinical', 'Sunset Blvd', '2025-09-26', NULL, 'active', true, 720.00, 3100.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000009', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'jose.marek8@example.com', 'b30f714e-3d8d-483b-b73a-39e21ec4b153', 'Jose', 'Marek', 'jose.marek8@example.com', 'Clinical', 'Sunset Blvd', '2025-09-13', NULL, 'active', true, 980.00, 4200.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000010', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'kim.lang9@example.com', '9d0b60a9-6355-4825-8bcf-b3ace5ddeff0', 'Kim', 'Lang', 'kim.lang9@example.com', 'Clinical', 'Sunset Blvd', '2025-08-31', NULL, 'active', true, 420.00, 4100.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000011', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'sofia.ito10@example.com', '8d458a70-1053-44e3-a87d-9b872d036143', 'Sofia', 'Ito', 'sofia.ito10@example.com', 'Clinical', 'Valley Branch', '2025-08-18', NULL, 'active', true, 480.00, 4400.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000012', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'ravi.malik11@example.com', '8c87a48c-9240-45cc-a485-02fd473ec5c3', 'Ravi', 'Malik', 'ravi.malik11@example.com', 'Clinical', 'Valley Branch', '2025-08-05', NULL, 'active', true, 480.00, 2700.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000013', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'nina.brandt12@example.com', '41c3b2d0-97bd-4562-a250-147a7a17dba3', 'Nina', 'Brandt', 'nina.brandt12@example.com', 'Clinical', 'Valley Branch', '2025-07-24', NULL, 'active', true, 420.00, 2850.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000014', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'tomas.wu13@example.com', 'f298f200-2b1c-42cc-a8ff-99fa16acd6d6', 'Tomas', 'Wu', 'tomas.wu13@example.com', 'Clinical', 'Valley Branch', '2025-07-11', NULL, 'active', true, 480.00, 2900.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000015', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'iris.duarte14@example.com', '0f999f38-5397-46e9-8a77-17807e3142a4', 'Iris', 'Duarte', 'iris.duarte14@example.com', 'Clinical', 'Valley Branch', '2025-06-28', NULL, 'active', true, 420.00, 2750.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000016', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'hugo.moreno15@example.com', 'b5b64b12-5680-4199-935c-c753bf7655dc', 'Hugo', 'Moreno', 'hugo.moreno15@example.com', 'Clinical', 'Valley Branch', '2025-06-15', NULL, 'active', true, 480.00, 2900.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000017', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'lena.serrano16@example.com', 'e02384ee-8019-4b28-bcfc-cfc8386a3c43', 'Lena', 'Serrano', 'lena.serrano16@example.com', 'Clinical', 'Valley Branch', '2025-06-02', NULL, 'active', true, 420.00, 2800.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000018', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'pablo.fontaine17@example.com', '0b3036ff-56dc-4ea8-a44d-bf12fd5b28ae', 'Pablo', 'Fontaine', 'pablo.fontaine17@example.com', 'Clinical', 'Valley Branch', '2025-05-20', NULL, 'active', true, 480.00, 2850.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000019', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'yuki.lindqvist18@example.com', '143104b4-8d23-4c9d-a6e2-6ecc4d7d405d', 'Yuki', 'Lindqvist', 'yuki.lindqvist18@example.com', 'Clinical', 'Valley Branch', '2025-05-07', NULL, 'active', true, 420.00, 2900.00, CURRENT_DATE),
  ('b09e11e5-0006-4006-8006-000000000020', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'rosa.okafor19@example.com', '81737934-59ec-425b-af4b-39cb16c3cff7', 'Rosa', 'Okafor', 'rosa.okafor19@example.com', 'Clinical', 'Valley Branch', '2025-04-24', NULL, 'active', true, 480.00, 2800.00, CURRENT_DATE),
  -- Fabricated: recent hire, not yet enrolled — fires new_hire_enrollment_gap
  ('b09e11e5-0006-4006-8006-000000000021', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'nina.petrov@example.com', NULL, 'Nina', 'Petrov', 'nina.petrov@example.com', 'Front Office', 'Sunset Blvd', CURRENT_DATE - 20, NULL, 'active', false, NULL, 2600.00, CURRENT_DATE),
  -- Fabricated: recently terminated but still carrying employer premium — fires termination_premium_leak
  ('b09e11e5-0006-4006-8006-000000000022', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'csv', 'tom.weller@example.com', NULL, 'Tom', 'Weller', 'tom.weller@example.com', 'Administration', 'Valley Branch', '2024-02-01', CURRENT_DATE - 30, 'inactive', true, 780.00, 3400.00, CURRENT_DATE)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 7. Eligibility exceptions — pre-seeded to match the roster rows above.
--    dedup_key matches detect_eligibility_exceptions()'s format exactly, so
--    a later POST /benefits/run refreshes these rows rather than duplicating.
-- ---------------------------------------------------------------------------
INSERT INTO benefit_eligibility_exceptions
  (id, company_id, dedup_key, roster_entry_id, employee_id, employee_name, exception_type, reference_date, days_elapsed, days_remaining, estimated_monthly_leak, status, source, detected_at, last_seen_at)
VALUES
  ('b09e11e5-0007-4007-8007-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'new_hire_enrollment_gap:csv:nina.petrov@example.com', 'b09e11e5-0006-4006-8006-000000000021', NULL, 'Nina Petrov', 'new_hire_enrollment_gap', CURRENT_DATE - 20, 20, 10, NULL, 'open', 'csv', NOW(), NOW()),
  ('b09e11e5-0007-4007-8007-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'termination_premium_leak:csv:tom.weller@example.com', 'b09e11e5-0006-4006-8006-000000000022', NULL, 'Tom Weller', 'termination_premium_leak', CURRENT_DATE - 30, 30, NULL, 780.00, 'open', 'csv', NOW(), NOW())
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 8. Renewal-risk radar — company + department + location dimensions
-- ---------------------------------------------------------------------------
INSERT INTO benefit_renewal_risk
  (id, company_id, dimension_type, dimension_value, risk_band, turnover_pct, turnover_baseline_pct, turnover_delta_pct, lost_workdays, lost_workdays_baseline, lost_workdays_delta_pct, near_misses, behavioral_incidents, headcount, gross_payroll, policy_month, triggers) VALUES
  ('b09e11e5-0008-4008-8008-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'company', '', 'elevated', 9.5, 5.0, 90.0, 12, 8, 50.0, 0, 1, 63, 168000.00, NULL, '[{"kind":"turnover_spike","detail":"turnover 9.5% vs baseline 5.0%"}]'),
  ('b09e11e5-0008-4008-8008-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'department', 'Clinical', 'stable', 4.0, 5.0, -20.0, 2, 3, -33.0, 0, 0, 60, 158000.00, NULL, '[]'),
  ('b09e11e5-0008-4008-8008-000000000003', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', 'location', 'Valley Branch', 'elevated', 6.0, 5.0, 20.0, 9, 5, 80.0, 1, 1, 10, 30000.00, NULL, '[{"kind":"incident_spike","detail":"lost workdays +80% vs baseline, 1 near-miss reported"}]')
ON CONFLICT DO NOTHING;
