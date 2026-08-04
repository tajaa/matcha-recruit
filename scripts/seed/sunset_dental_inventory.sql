-- Sunset Smile Dental Group — inventory demo data, matching the huume
-- inventory-topic conversation exercised in dev (Nitrile Gloves / Printer
-- Paper counts). `inventory` is already enabled on prod for this company —
-- this pack only adds the missing rows so @huume has something to answer
-- from. Company-wide (location_id NULL) on purpose: the Front Desk channel
-- on prod is unscoped (channels.location_id IS NULL), so a store-scoped
-- item would silently not show up there — see channel_grounding.py's
-- "location_id IS NULL OR" tolerance, which this relies on.
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
  ('5eedaaaa-0001-4001-8001-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', NULL,
   'Nitrile Gloves (M)', 'nitrile gloves m', 'boxes', 34, 15, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2'),
  ('5eedaaaa-0001-4001-8001-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400', NULL,
   'Printer Paper', 'printer paper', 'reams', 12, 5, FALSE,
   '8e7614eb-7174-4802-8f6e-b44d065993e2')
ON CONFLICT (company_id, location_id, normalized_name) WHERE archived_at IS NULL DO NOTHING;

-- Back the seeded current_quantity with a matching ledger row so the demo
-- item doesn't show stock against an empty movement history. Only inserted
-- alongside a fresh item row above (ON CONFLICT on the pinned movement id
-- keeps a re-run idempotent without double-crediting an existing item).
INSERT INTO inventory_movements
  (id, company_id, item_id, kind, quantity, quantity_delta, quantity_estimated,
   narrative, created_at)
VALUES
  ('5eedaaaa-0002-4001-8001-000000000001', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400',
   '5eedaaaa-0001-4001-8001-000000000001', 'adjust', 34, 34, FALSE,
   'Seed: initial count for demo data', NOW()),
  ('5eedaaaa-0002-4001-8001-000000000002', '287fffb5-ea50-40a2-bf07-6b5c2ca3c400',
   '5eedaaaa-0001-4001-8001-000000000002', 'adjust', 12, 12, FALSE,
   'Seed: initial count for demo data', NOW())
ON CONFLICT (id) DO NOTHING;
