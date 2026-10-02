-- Undo: restore the pre-pack value (incidents was false, key present).
UPDATE companies
SET enabled_features = COALESCE(enabled_features, '{}'::jsonb) || '{"incidents": false}'::jsonb
WHERE id = 'c4c256c3-60ef-4cf5-8d4c-55e963c58416';
