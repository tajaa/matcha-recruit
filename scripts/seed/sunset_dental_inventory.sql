-- Sunset Smile Dental Group — Wilshire inventory demo data, matching the huume
-- inventory-topic conversation exercised in dev (Nitrile Gloves / Printer
-- Paper counts). `inventory` is already enabled on prod for this company —
-- this pack only adds Wilshire-scoped catalog, ledger, and order rows so the
-- Inventory page and @huume have a useful dataset to answer from.
-- Wilshire location_id: 59bf0bdc-558f-4530-8917-a792eb7f5d98.
--
-- Deliberately NOT seeding a "Suction Tips" item — its absence is the
-- point (the "we don't have anything on file for X" branch of the demo
-- conversation), not something to fake.
--
-- Pinned UUID scheme (prefix 5eedaaaa — "seed"), so undo is a one-liner
-- and a re-run is idempotent via ON CONFLICT.
--
--   ./scripts/seed-prod.sh scripts/seed/sunset_dental_inventory.sql --dry-run
--   ./scripts/seed-prod.sh scripts/seed/sunset_dental_inventory.sql
--   ./scripts/seed-prod.sh scripts/seed/sunset_dental_inventory.sql --undo

-- ON CONFLICT targets the real constraint (uniq_inventory_items_name, migration
-- oploc01) rather than the surrogate id: @huume may have already auto-created
-- one of these items on prod from the exercised conversation, in which case
-- the surrogate-key target would 23505 and abort the whole pack.
INSERT INTO inventory_items
  (id, company_id, location_id, name, normalized_name, unit, current_quantity,
   low_stock_threshold, auto_created, created_by)
VALUES
  ('5eedaaaa-0001-4001-8001-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Nitrile Gloves (M)', 'nitrile gloves m', 'boxes', 34, 15, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Printer Paper', 'printer paper', 'reams', 12, 5, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2')
ON CONFLICT (company_id, location_id, normalized_name) WHERE archived_at IS NULL DO NOTHING;

-- Back the seeded current_quantity with a matching ledger row so the demo
-- item doesn't show stock against an empty movement history. Only inserted
-- alongside a fresh item row above (ON CONFLICT on the pinned movement id
-- keeps a re-run idempotent without double-crediting an existing item).
WITH candidates (id, company_id, item_id, kind, quantity, quantity_delta,
                 quantity_estimated, narrative) AS (
  VALUES
    ('5eedaaaa-0002-4001-8001-000000000001'::uuid, '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'::uuid,
     '5eedaaaa-0001-4001-8001-000000000001'::uuid, 'adjust', 34, 34, FALSE,
     'Seed: initial count for demo data'),
    ('5eedaaaa-0002-4001-8001-000000000002'::uuid, '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'::uuid,
     '5eedaaaa-0001-4001-8001-000000000002'::uuid, 'adjust', 12, 12, FALSE,
     'Seed: initial count for demo data')
)
INSERT INTO inventory_movements
  (id, company_id, item_id, kind, quantity, quantity_delta, quantity_estimated,
   narrative, created_at)
SELECT c.id, c.company_id, c.item_id, c.kind, c.quantity, c.quantity_delta,
       c.quantity_estimated, c.narrative, NOW()
FROM candidates c
WHERE NOT EXISTS (
  SELECT 1 FROM inventory_movements existing WHERE existing.item_id = c.item_id
)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Expanded catalog. The first two items above are kept as the original demo
-- anchors. These rows cover ordinary stock, low-stock thresholds, unit costs,
-- and several consumables that make the audit and reorder views useful.
-- ---------------------------------------------------------------------------
INSERT INTO inventory_items
  (id, company_id, location_id, name, normalized_name, unit, current_quantity,
   low_stock_threshold, unit_cost, auto_created, created_by)
VALUES
  ('5eedaaaa-0001-4001-8001-000000000003', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Nitrile Gloves - Small', 'nitrile gloves small', 'boxes', 36, 20, 45.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000004', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Surgical Masks', 'surgical mask', 'boxes', 6, 8, 28.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000005', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Disposable Isolation Gowns', 'disposable isolation gown', 'boxes', 15, 6, 62.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000006', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Patient Bibs', 'patient bib', 'packs', 87, 30, 18.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000007', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Cotton Rolls', 'cotton roll', 'bags', 44, 15, 24.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000008', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Saliva Ejectors', 'saliva ejector', 'bags', 0, 8, 35.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000009', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Prophy Angles', 'prophy angle', 'boxes', 53, 20, 74.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000010', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Fluoride Varnish', 'fluoride varnish', 'boxes', 16, 10, 95.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000011', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Composite Resin Syringes', 'composite resin syringe', 'syringes', 42, 12, 12.50, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000012', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Etch Gel', 'etch gel', 'syringes', 11, 6, 9.25, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000013', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Bonding Agent', 'bonding agent', 'bottles', 6, 5, 31.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000014', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Anesthetic Carpules', 'anesthetic carpule', 'boxes', 3, 5, 88.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000015', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Short Needles', 'short needle', 'boxes', 8, 4, 39.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000016', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Sterilization Pouches', 'sterilization pouch', 'boxes', 7, 10, 42.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000017', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Autoclave Indicator Strips', 'autoclave indicator strip', 'boxes', 4, 5, 29.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000018', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Surface Disinfectant', 'surface disinfectant', 'gallons', 6, 8, 21.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000019', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Instrument Wipes', 'instrument wipe', 'packs', 12, 8, 16.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000020', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Nitrile Gloves - Large', 'nitrile gloves large', 'boxes', 18, 20, 48.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000021', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Printer Toner Cartridge', 'printer toner cartridge', 'cartridges', 4, 2, 110.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000022', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '59bf0bdc-558f-4530-8917-a792eb7f5d98',
   'Patient Safety Glasses', 'patient safety glasses', 'each', 18, 8, 6.00, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2')
ON CONFLICT (company_id, location_id, normalized_name) WHERE archived_at IS NULL DO NOTHING;

-- Every added item gets an opening count. The extra history below deliberately
-- mixes out, sale, in, and stockout rows so reorder suggestions and the audit
-- sheet have real history to inspect. The final quantities above already
-- include these deltas.
INSERT INTO inventory_movements
  (id, company_id, item_id, kind, quantity, quantity_delta, quantity_estimated,
   note, narrative, created_at)
VALUES
  ('5eedaaaa-0002-4001-8001-000000000003', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000003', 'adjust', 60, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000004', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000004', 'adjust', 18, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000005', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000005', 'adjust', 24, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000006', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000006', 'adjust', 150, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000007', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000007', 'adjust', 40, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000008', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000008', 'adjust', 30, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000009', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000009', 'adjust', 100, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000010', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000010', 'adjust', 36, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000011', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000011', 'adjust', 45, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000012', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000012', 'adjust', 20, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000013', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000013', 'adjust', 16, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000014', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000014', 'adjust', 12, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000015', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000015', 'adjust', 9, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000016', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000016', 'adjust', 22, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000017', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000017', 'adjust', 10, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000018', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000018', 'adjust', 18, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000019', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000019', 'adjust', 30, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000020', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000020', 'adjust', 42, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000021', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000021', 'adjust', 6, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000022', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000022', 'adjust', 30, NULL, FALSE, 'Seed: opening count', 'Seed: opening count for demo data', NOW() - INTERVAL '90 days'),
  ('5eedaaaa-0002-4001-8001-000000000023', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000003', 'out', 8, -8, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '70 days'),
  ('5eedaaaa-0002-4001-8001-000000000024', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000003', 'out', 6, -6, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '40 days'),
  ('5eedaaaa-0002-4001-8001-000000000025', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000003', 'out', 10, -10, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '12 days'),
  ('5eedaaaa-0002-4001-8001-000000000026', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000004', 'out', 4, -4, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '70 days'),
  ('5eedaaaa-0002-4001-8001-000000000027', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000004', 'out', 3, -3, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '40 days'),
  ('5eedaaaa-0002-4001-8001-000000000028', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000004', 'out', 5, -5, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '12 days'),
  ('5eedaaaa-0002-4001-8001-000000000029', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000005', 'out', 3, -3, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '65 days'),
  ('5eedaaaa-0002-4001-8001-000000000030', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000005', 'out', 2, -2, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '35 days'),
  ('5eedaaaa-0002-4001-8001-000000000031', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000005', 'out', 4, -4, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '8 days'),
  ('5eedaaaa-0002-4001-8001-000000000032', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000007', 'out', 5, -5, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '65 days'),
  ('5eedaaaa-0002-4001-8001-000000000033', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000007', 'out', 7, -7, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '35 days'),
  ('5eedaaaa-0002-4001-8001-000000000034', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000007', 'in', 20, 20, FALSE, 'Seed: delivery receipt', 'Seed: delivery receipt for demo data', NOW() - INTERVAL '20 days'),
  ('5eedaaaa-0002-4001-8001-000000000035', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000007', 'out', 4, -4, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '7 days'),
  ('5eedaaaa-0002-4001-8001-000000000036', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000008', 'out', 10, -10, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '60 days'),
  ('5eedaaaa-0002-4001-8001-000000000037', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000008', 'out', 8, -8, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '30 days'),
  ('5eedaaaa-0002-4001-8001-000000000038', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000008', 'stockout', 0, NULL, FALSE, 'Seed: stockout example', 'Seed: stockout example for demo data', NOW() - INTERVAL '5 days'),
  ('5eedaaaa-0002-4001-8001-000000000039', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000009', 'out', 15, -15, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '65 days'),
  ('5eedaaaa-0002-4001-8001-000000000040', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000009', 'sale', 12, -12, FALSE, 'Seed: POS sale', 'Seed: POS sale for demo data', NOW() - INTERVAL '32 days'),
  ('5eedaaaa-0002-4001-8001-000000000041', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000009', 'out', 20, -20, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '10 days'),
  ('5eedaaaa-0002-4001-8001-000000000042', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000010', 'out', 8, -8, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '60 days'),
  ('5eedaaaa-0002-4001-8001-000000000043', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000010', 'out', 7, -7, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '28 days'),
  ('5eedaaaa-0002-4001-8001-000000000044', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000010', 'in', 24, 24, FALSE, 'Seed: delivery receipt', 'Seed: delivery receipt for demo data', NOW() - INTERVAL '18 days'),
  ('5eedaaaa-0002-4001-8001-000000000045', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000010', 'out', 8, -8, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '6 days'),
  ('5eedaaaa-0002-4001-8001-000000000046', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000015', 'in', 6, 6, FALSE, 'Seed: delivery receipt', 'Seed: delivery receipt for demo data', NOW() - INTERVAL '9 days'),
  ('5eedaaaa-0002-4001-8001-000000000047', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000015', 'out', 7, -7, FALSE, 'Seed: routine usage', 'Seed: routine usage for demo data', NOW() - INTERVAL '3 days')
ON CONFLICT (id) DO NOTHING;

-- A few order states make the queue, approval, receipt, and cancellation UI
-- immediately testable. The received order points at the seeded receipt
-- movement above; no fake channel message is needed for these demo rows.
INSERT INTO inventory_orders
  (id, company_id, item_id, created_by, status, suggested_quantity, quantity,
   suggestion, approved_by, approved_at, ordered_at, received_by, received_at,
   received_quantity, receipt_movement_id)
VALUES
  ('5eedaaaa-0003-4001-8001-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000004',
   '8e7614eb-7174-4802-8f6e-b44d065993e2', 'queued', 18, 18,
   '{"suggested_quantity": 18, "daily_rate": 0.86, "cover_days": 14, "confidence": "medium", "n_samples": 3}'::jsonb,
   NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('5eedaaaa-0003-4001-8001-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000008',
   '8e7614eb-7174-4802-8f6e-b44d065993e2', 'queued', 24, 24,
   '{"suggested_quantity": 24, "daily_rate": 0.6, "cover_days": 14, "confidence": "medium", "n_samples": 3}'::jsonb,
   NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('5eedaaaa-0003-4001-8001-000000000003', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000014',
   '8e7614eb-7174-4802-8f6e-b44d065993e2', 'ordered', 12, 6,
   '{"suggested_quantity": 12, "daily_rate": 0.52, "cover_days": 14, "confidence": "medium", "n_samples": 3}'::jsonb,
   '8e7614eb-7174-4802-8f6e-b44d065993e2', NOW() - INTERVAL '4 days', NOW() - INTERVAL '4 days', NULL, NULL, NULL, NULL),
  ('5eedaaaa-0003-4001-8001-000000000004', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000015',
   '8e7614eb-7174-4802-8f6e-b44d065993e2', 'received', 6, 6,
   '{"suggested_quantity": 6, "daily_rate": 0.3, "cover_days": 14, "confidence": "low", "n_samples": 3}'::jsonb,
   '8e7614eb-7174-4802-8f6e-b44d065993e2', NOW() - INTERVAL '12 days', NOW() - INTERVAL '12 days',
   '8e7614eb-7174-4802-8f6e-b44d065993e2', NOW() - INTERVAL '9 days', 6, '5eedaaaa-0002-4001-8001-000000000046'),
  ('5eedaaaa-0003-4001-8001-000000000005', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', '5eedaaaa-0001-4001-8001-000000000017',
   '8e7614eb-7174-4802-8f6e-b44d065993e2', 'cancelled', 8, 8,
   '{"suggested_quantity": 8, "daily_rate": 0.4, "cover_days": 14, "confidence": "low", "n_samples": 3}'::jsonb,
   NULL, NULL, NULL, NULL, NULL, NULL, NULL)
ON CONFLICT (id) DO NOTHING;
