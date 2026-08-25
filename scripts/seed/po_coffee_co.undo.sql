DELETE FROM inventory_movements WHERE id::text LIKE 'c0ffeeee-000%';
DELETE FROM inventory_items WHERE id::text LIKE 'c0ffeeee-0006-%';
DELETE FROM schedule_shift_assignments WHERE id::text LIKE 'c0ffeeee-0005-%';
DELETE FROM schedule_shifts WHERE id::text LIKE 'c0ffeeee-0004-%';
DELETE FROM employees WHERE id::text LIKE 'c0ffeeee-0003-%';
DELETE FROM users WHERE id::text LIKE 'c0ffeeee-0002-%';
DELETE FROM business_locations WHERE id::text LIKE 'c0ffeeee-0001-%';
