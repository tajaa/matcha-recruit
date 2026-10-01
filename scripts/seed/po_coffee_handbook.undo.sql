-- Undo for po_coffee_handbook.sql. Sections cascade from the version, which
-- cascades from the handbook; deleted explicitly anyway, children first.
DELETE FROM handbook_sections WHERE id::text LIKE 'c0ffeeee-0b00-%';
DELETE FROM handbook_versions WHERE id::text LIKE 'c0ffeeee-0b00-%';
DELETE FROM handbooks WHERE id::text LIKE 'c0ffeeee-0b00-%';
