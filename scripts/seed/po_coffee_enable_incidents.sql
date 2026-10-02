-- Po Coffee Co (c4c256c3-60ef-4cf5-8d4c-55e963c58416): turn the `incidents`
-- feature ON so the test tenant can file incident reports. Every /ir/incidents
-- route is gated on it, and so is the whole HR cases intake -> triage path.
-- Prod value before this pack: "incidents": false (key present).
--
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_enable_incidents.sql --dry-run
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_enable_incidents.sql
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_enable_incidents.sql --undo

UPDATE companies
SET enabled_features = COALESCE(enabled_features, '{}'::jsonb) || '{"incidents": true}'::jsonb
WHERE id = 'c4c256c3-60ef-4cf5-8d4c-55e963c58416';
