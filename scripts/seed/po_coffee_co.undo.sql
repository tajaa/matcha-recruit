DELETE FROM inventory_movements WHERE id::text LIKE 'c0ffeeee-000%';
DELETE FROM inventory_items WHERE id::text LIKE 'c0ffeeee-0006-%';
DELETE FROM schedule_shift_assignments WHERE id::text LIKE 'c0ffeeee-0005-%';
DELETE FROM schedule_shifts WHERE id::text LIKE 'c0ffeeee-0004-%';
DELETE FROM employees WHERE id::text LIKE 'c0ffeeee-0003-%';
DELETE FROM users WHERE id::text LIKE 'c0ffeeee-0002-%';
DELETE FROM business_locations WHERE id::text LIKE 'c0ffeeee-0001-%';
UPDATE companies
SET enabled_features = COALESCE(enabled_features, '{}'::jsonb) - 'ems' - 'inventory_waste'
WHERE id = 'c4c256c3-60ef-4cf5-8d4c-55e963c58416';
