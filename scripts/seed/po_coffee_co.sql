-- Po Coffee Co (matcha_ops product, company_id c4c256c3-60ef-4cf5-8d4c-55e963c58416)
-- heavy test/demo data: locations, roster, 2 weeks of schedule, inventory
-- catalog + movement history (incl. sales), matching the flags already ON
-- for this company: employees, inventory, employee_schedule, sales_intake.
--
-- All rows pinned under UUID prefix c0ffeeee- so undo/re-run are one-liners.
-- Emails use @example.com (RFC 2606 reserved) per repo test-data rule.
--
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_co.sql --dry-run
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_co.sql
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_co.sql --undo

-- ---------------------------------------------------------------------------
-- Locations
-- ---------------------------------------------------------------------------
INSERT INTO business_locations
  (id, company_id, name, address, city, state, zipcode, country_code, is_active, source)
VALUES
  ('c0ffeeee-0001-4001-8001-000000000001', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'Po Coffee Co — Downtown', '412 Market St', 'San Francisco', 'CA', '94103', 'US', TRUE, 'manual'),
  ('c0ffeeee-0001-4001-8001-000000000002', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'Po Coffee Co — Mission', '2288 Mission St', 'San Francisco', 'CA', '94110', 'US', TRUE, 'manual')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Roster: 12 employees (store manager, 2 shift leads, 9 baristas) split
-- across the two locations. users first (employees.user_id FK), then
-- employees itself.
-- ---------------------------------------------------------------------------
INSERT INTO users (id, email, password_hash, role, is_active)
VALUES
  ('c0ffeeee-0002-4001-8001-000000000001', 'maria.rossi@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000002', 'devon.cole@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000003', 'priya.nair@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000004', 'jonah.brooks@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000005', 'lena.abara@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000006', 'sam.ferreira@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000007', 'kai.tanaka@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000008', 'ruth.okafor@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000009', 'ivan.petrov@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000010', 'nadia.hassan@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000011', 'ben.orozco@example.com', '!', 'employee', TRUE),
  ('c0ffeeee-0002-4001-8001-000000000012', 'ellie.marsh@example.com', '!', 'employee', TRUE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO employees
  (id, org_id, user_id, email, first_name, last_name, work_state, employment_type,
   start_date, phone, work_location_id, pay_classification, pay_rate, work_city,
   job_title, department, employment_status, is_supervisor, is_manager)
VALUES
  ('c0ffeeee-0003-4001-8001-000000000001', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000001', 'maria.rossi@example.com', 'Maria', 'Rossi',
   'CA', 'full_time', '2024-03-01', '415-555-0101',
   'c0ffeeee-0001-4001-8001-000000000001', 'hourly', 28.00, 'San Francisco',
   'Store Manager', 'Operations', 'active', TRUE, TRUE),
  ('c0ffeeee-0003-4001-8001-000000000002', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000002', 'devon.cole@example.com', 'Devon', 'Cole',
   'CA', 'full_time', '2024-05-14', '415-555-0102',
   'c0ffeeee-0001-4001-8001-000000000001', 'hourly', 22.00, 'San Francisco',
   'Shift Lead', 'Operations', 'active', TRUE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000003', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000003', 'priya.nair@example.com', 'Priya', 'Nair',
   'CA', 'full_time', '2024-06-03', '415-555-0103',
   'c0ffeeee-0001-4001-8001-000000000002', 'hourly', 22.00, 'San Francisco',
   'Shift Lead', 'Operations', 'active', TRUE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000004', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000004', 'jonah.brooks@example.com', 'Jonah', 'Brooks',
   'CA', 'part_time', '2024-07-01', '415-555-0104',
   'c0ffeeee-0001-4001-8001-000000000001', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000005', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000005', 'lena.abara@example.com', 'Lena', 'Abara',
   'CA', 'part_time', '2024-08-19', '415-555-0105',
   'c0ffeeee-0001-4001-8001-000000000001', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000006', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000006', 'sam.ferreira@example.com', 'Sam', 'Ferreira',
   'CA', 'part_time', '2024-09-09', '415-555-0106',
   'c0ffeeee-0001-4001-8001-000000000001', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000007', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000007', 'kai.tanaka@example.com', 'Kai', 'Tanaka',
   'CA', 'part_time', '2024-10-21', '415-555-0107',
   'c0ffeeee-0001-4001-8001-000000000002', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000008', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000008', 'ruth.okafor@example.com', 'Ruth', 'Okafor',
   'CA', 'part_time', '2024-11-11', '415-555-0108',
   'c0ffeeee-0001-4001-8001-000000000002', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000009', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000009', 'ivan.petrov@example.com', 'Ivan', 'Petrov',
   'CA', 'part_time', '2025-01-06', '415-555-0109',
   'c0ffeeee-0001-4001-8001-000000000002', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000010', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000010', 'nadia.hassan@example.com', 'Nadia', 'Hassan',
   'CA', 'part_time', '2025-02-17', '415-555-0110',
   'c0ffeeee-0001-4001-8001-000000000001', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000011', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000011', 'ben.orozco@example.com', 'Ben', 'Orozco',
   'CA', 'part_time', '2025-03-24', '415-555-0111',
   'c0ffeeee-0001-4001-8001-000000000002', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE),
  ('c0ffeeee-0003-4001-8001-000000000012', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'c0ffeeee-0002-4001-8001-000000000012', 'ellie.marsh@example.com', 'Ellie', 'Marsh',
   'CA', 'part_time', '2025-04-30', '415-555-0112',
   'c0ffeeee-0001-4001-8001-000000000001', 'hourly', 19.50, 'San Francisco',
   'Barista', 'Operations', 'active', FALSE, FALSE)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Schedule: 2 weeks of shifts (open/mid/close x2 locations x14 days),
-- each with one assigned employee. Week starting the Monday two weeks ago
-- relative to seed authoring date (2026-08-24) -> 2026-08-10.
-- ---------------------------------------------------------------------------
WITH days AS (
  SELECT generate_series('2026-08-10'::date, '2026-08-23'::date, interval '1 day') AS d
),
shift_defs AS (
  SELECT d, loc, slot, row_number() OVER () AS rn
  FROM days,
       (VALUES ('c0ffeeee-0001-4001-8001-000000000001'::uuid),
               ('c0ffeeee-0001-4001-8001-000000000002'::uuid)) AS l(loc),
       (VALUES ('open', time '06:00', time '14:00'),
               ('close', time '13:30', time '21:30')) AS s(slot, start_t, end_t)
),
shift_defs2 AS (
  SELECT sf.d, sf.loc, sf.slot, sf.rn,
         s.start_t, s.end_t
  FROM shift_defs sf
  JOIN (VALUES ('open', time '06:00', time '14:00'),
               ('close', time '13:30', time '21:30')) AS s(slot, start_t, end_t)
    ON s.slot = sf.slot
),
candidates AS (
  SELECT
    ('c0ffeeee-0004-4001-8001-' || lpad(rn::text, 12, '0'))::uuid AS id,
    'c4c256c3-60ef-4cf5-8d4c-55e963c58416'::uuid AS company_id,
    loc AS location_id,
    'Barista' AS role,
    (d + start_t) AT TIME ZONE 'America/Los_Angeles' AS starts_at,
    (d + end_t) AT TIME ZONE 'America/Los_Angeles' AS ends_at,
    'published' AS status,
    CASE (rn % 12) + 1
      WHEN 1 THEN 'c0ffeeee-0003-4001-8001-000000000004'
      WHEN 2 THEN 'c0ffeeee-0003-4001-8001-000000000005'
      WHEN 3 THEN 'c0ffeeee-0003-4001-8001-000000000006'
      WHEN 4 THEN 'c0ffeeee-0003-4001-8001-000000000007'
      WHEN 5 THEN 'c0ffeeee-0003-4001-8001-000000000008'
      WHEN 6 THEN 'c0ffeeee-0003-4001-8001-000000000009'
      WHEN 7 THEN 'c0ffeeee-0003-4001-8001-000000000010'
      WHEN 8 THEN 'c0ffeeee-0003-4001-8001-000000000011'
      WHEN 9 THEN 'c0ffeeee-0003-4001-8001-000000000012'
      WHEN 10 THEN 'c0ffeeee-0003-4001-8001-000000000002'
      WHEN 11 THEN 'c0ffeeee-0003-4001-8001-000000000003'
      ELSE 'c0ffeeee-0003-4001-8001-000000000001'
    END::uuid AS employee_id
  FROM shift_defs2
)
INSERT INTO schedule_shifts (id, company_id, location_id, role, starts_at, ends_at, status)
SELECT id, company_id, location_id, role, starts_at, ends_at, status FROM candidates
ON CONFLICT (id) DO NOTHING;

WITH days AS (
  SELECT generate_series('2026-08-10'::date, '2026-08-23'::date, interval '1 day') AS d
),
shift_defs AS (
  SELECT d, loc, row_number() OVER () AS rn
  FROM days,
       (VALUES ('c0ffeeee-0001-4001-8001-000000000001'::uuid),
               ('c0ffeeee-0001-4001-8001-000000000002'::uuid)) AS l(loc),
       (VALUES ('open'), ('close')) AS s(slot)
),
candidates AS (
  SELECT
    ('c0ffeeee-0005-4001-8001-' || lpad(rn::text, 12, '0'))::uuid AS id,
    'c4c256c3-60ef-4cf5-8d4c-55e963c58416'::uuid AS company_id,
    ('c0ffeeee-0004-4001-8001-' || lpad(rn::text, 12, '0'))::uuid AS shift_id,
    CASE (rn % 12) + 1
      WHEN 1 THEN 'c0ffeeee-0003-4001-8001-000000000004'
      WHEN 2 THEN 'c0ffeeee-0003-4001-8001-000000000005'
      WHEN 3 THEN 'c0ffeeee-0003-4001-8001-000000000006'
      WHEN 4 THEN 'c0ffeeee-0003-4001-8001-000000000007'
      WHEN 5 THEN 'c0ffeeee-0003-4001-8001-000000000008'
      WHEN 6 THEN 'c0ffeeee-0003-4001-8001-000000000009'
      WHEN 7 THEN 'c0ffeeee-0003-4001-8001-000000000010'
      WHEN 8 THEN 'c0ffeeee-0003-4001-8001-000000000011'
      WHEN 9 THEN 'c0ffeeee-0003-4001-8001-000000000012'
      WHEN 10 THEN 'c0ffeeee-0003-4001-8001-000000000002'
      WHEN 11 THEN 'c0ffeeee-0003-4001-8001-000000000003'
      ELSE 'c0ffeeee-0003-4001-8001-000000000001'
    END::uuid AS employee_id,
    'confirmed' AS status
  FROM shift_defs
)
INSERT INTO schedule_shift_assignments (id, company_id, shift_id, employee_id, status)
SELECT id, company_id, shift_id, employee_id, status FROM candidates
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Inventory catalog: 16 coffee-shop items across both locations.
-- ---------------------------------------------------------------------------
INSERT INTO inventory_items
  (id, company_id, location_id, name, normalized_name, unit, current_quantity,
   low_stock_threshold, unit_cost, category, auto_created)
VALUES
  ('c0ffeeee-0006-4001-8001-000000000001', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Espresso Beans (House Blend)', 'espresso beans house blend', 'lbs', 40, 15, 9.25, 'coffee', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000002', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Decaf Beans', 'decaf beans', 'lbs', 12, 8, 9.75, 'coffee', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000003', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Whole Milk', 'whole milk', 'gallons', 18, 10, 4.10, 'dairy', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000004', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Oat Milk', 'oat milk', 'gallons', 14, 8, 6.50, 'dairy_alt', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000005', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Vanilla Syrup', 'vanilla syrup', 'bottles', 9, 4, 7.00, 'syrup', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000006', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Caramel Syrup', 'caramel syrup', 'bottles', 7, 4, 7.00, 'syrup', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000007', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   '12oz Hot Cups', '12oz hot cups', 'sleeves', 22, 10, 5.80, 'disposables', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000008', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   '16oz Cold Cups', '16oz cold cups', 'sleeves', 20, 10, 6.20, 'disposables', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000009', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Croissants', 'croissants', 'units', 30, 12, 1.25, 'pastry', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000010', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000001',
   'Blueberry Muffins', 'blueberry muffins', 'units', 24, 10, 1.10, 'pastry', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000011', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000002',
   'Espresso Beans (House Blend)', 'espresso beans house blend', 'lbs', 35, 15, 9.25, 'coffee', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000012', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000002',
   'Whole Milk', 'whole milk', 'gallons', 16, 10, 4.10, 'dairy', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000013', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000002',
   'Oat Milk', 'oat milk', 'gallons', 11, 8, 6.50, 'dairy_alt', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000014', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000002',
   '12oz Hot Cups', '12oz hot cups', 'sleeves', 18, 10, 5.80, 'disposables', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000015', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000002',
   'Croissants', 'croissants', 'units', 20, 12, 1.25, 'pastry', FALSE),
  ('c0ffeeee-0006-4001-8001-000000000016', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416', 'c0ffeeee-0001-4001-8001-000000000002',
   'Cold Brew Concentrate', 'cold brew concentrate', 'gallons', 6, 3, 14.00, 'coffee', FALSE)
ON CONFLICT (company_id, location_id, normalized_name) WHERE archived_at IS NULL DO NOTHING;

-- Opening-count movements matching current_quantity for every seeded item.
WITH src AS (
  SELECT id AS item_id, company_id, current_quantity
  FROM inventory_items
  WHERE id::text LIKE 'c0ffeeee-0006-%'
),
numbered AS (
  SELECT item_id, company_id, current_quantity, row_number() OVER () AS rn FROM src
)
INSERT INTO inventory_movements
  (id, company_id, item_id, kind, quantity, quantity_delta, quantity_estimated, narrative, created_at)
SELECT
  ('c0ffeeee-0007-4001-8001-' || lpad(rn::text, 12, '0'))::uuid,
  company_id, item_id, 'adjust', current_quantity, current_quantity, FALSE,
  'Seed: opening count', now() - interval '14 days'
FROM numbered
ON CONFLICT (id) DO NOTHING;

-- Two weeks of daily 'sale' depletion movements against the two highest-
-- velocity items per location (espresso beans + milk), small negative deltas.
WITH days AS (
  SELECT generate_series(1, 14) AS n
),
targets AS (
  SELECT unnest(ARRAY[
    'c0ffeeee-0006-4001-8001-000000000001', 'c0ffeeee-0006-4001-8001-000000000003',
    'c0ffeeee-0006-4001-8001-000000000009', 'c0ffeeee-0006-4001-8001-000000000011',
    'c0ffeeee-0006-4001-8001-000000000012', 'c0ffeeee-0006-4001-8001-000000000015'
  ])::uuid AS item_id
),
candidates AS (
  SELECT item_id, n, row_number() OVER () AS rn
  FROM targets CROSS JOIN days
)
INSERT INTO inventory_movements
  (id, company_id, item_id, kind, quantity, quantity_delta, quantity_estimated, narrative, created_at)
SELECT
  ('c0ffeeee-0008-4001-8001-' || lpad(rn::text, 12, '0'))::uuid,
  'c4c256c3-60ef-4cf5-8d4c-55e963c58416', item_id, 'sale',
  1.5 + (rn % 3), -1 * (1.5 + (rn % 3)), TRUE,
  'Seed: daily POS depletion', now() - (14 - n) * interval '1 day'
FROM candidates
ON CONFLICT (id) DO NOTHING;
