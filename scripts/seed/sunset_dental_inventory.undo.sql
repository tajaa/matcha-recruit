-- Undo for sunset_dental_inventory.sql — deletes only the pinned rows this
-- pack created. Does not touch the `inventory` feature flag (already on
-- before this pack ran; not this pack's to revert).
DELETE FROM inventory_movements WHERE id::text LIKE '5eedaaaa-0002-%';
DELETE FROM inventory_items WHERE id::text LIKE '5eedaaaa-0001-%';
