-- Seed commercial-property (P-side) demo data for the Roystar dev tenant.
--
-- Exercises the full Statement-of-Values surface: a 6-building portfolio spanning
-- COPE grades A→D, fully- and under-insured (ITV), and coastal-wind / seismic /
-- inland catastrophe variety. Buildings are tied to Roystar's real
-- business_locations. Geocode + per-peril hazard are seeded directly (geocode_source
-- 'seed (demo)') so the catastrophe UI renders WITHOUT running the external
-- FEMA/USGS/USFS cat task — re-running the real property_cat_refresh task later just
-- overwrites these rows.
--
-- DEV ONLY (matcha-postgres :5432). Idempotent: clears Roystar's buildings first
-- (peril rows cascade), then re-inserts. Run:
--   PGPASSWORD=matcha_dev psql -h 127.0.0.1 -p 5432 -U matcha -d matcha \
--     -f scripts/sql/seed_roystar_property.sql

\set company_id '78db605a-0f59-40b7-98ba-3832f9d75008'

BEGIN;

-- Clean slate (peril rows cascade via FK ON DELETE CASCADE).
DELETE FROM company_property_buildings WHERE company_id = :'company_id';

-- 6 buildings. Construction types must match property_sov.CONSTRUCTION_GRADE keys.
INSERT INTO company_property_buildings
  (company_id, location_id, name, address, city, state, zipcode, county, occupancy,
   construction_type, year_built, sq_ft, stories, roof_year, sprinklered, protection_class,
   building_value, contents_value, bi_value, replacement_cost, insured_value,
   lat, lng, geocoded_at, geocode_source, cat_refreshed_at)
VALUES
  -- A-grade fire-resistive HQ, fully insured, low cat (inland TX, wind only).
  (:'company_id', '00adfefd-2e78-499f-87ce-50bc2c64f33f', 'Dallas Flagship & HQ',
   '500 Commerce St', 'Dallas', 'TX', '75201', 'Dallas', 'Office / flagship retail',
   'fire_resistive', 2018, 85000, 6, 2018, TRUE, '2',
   12000000, 3000000, 4000000, 15000000, 15000000,
   32.776700, -96.797000, NOW(), 'seed (demo)', NOW()),

  -- D-grade frame distribution center, badly under-insured (ITV 0.60), severe coastal cat.
  (:'company_id', 'ad8610a5-dee0-42cf-9a9f-b883cf54b92e', 'Miami Distribution Center',
   '7200 NW 19th St', 'Miami', 'FL', '33126', 'Miami-Dade', 'Warehouse / distribution',
   'frame', 1992, 140000, 1, 2005, FALSE, '6',
   6000000, 8000000, 5000000, 9000000, 5400000,
   25.761700, -80.191800, NOW(), 'seed (demo)', NOW()),

  -- B-grade masonry store, fully insured, FL wind + wildfire.
  (:'company_id', 'e0939070-6fc6-47ae-b509-c50ab27c20ff', 'Orlando Store #14',
   '4100 Conroy Rd', 'Orlando', 'FL', '32839', 'Orange', 'Retail store',
   'masonry_non_combustible', 2010, 32000, 1, 2010, FALSE, '3',
   2500000, 1200000, 1500000, 3000000, 3000000,
   28.538300, -81.379200, NOW(), 'seed (demo)', NOW()),

  -- B-grade old masonry store, under-insured (ITV 0.84), severe quake.
  (:'company_id', 'f8fdf5e6-d49c-4839-80fb-0bfde2675b74', 'San Francisco Union Sq Store',
   '170 Geary St', 'San Francisco', 'CA', '94108', 'San Francisco', 'Retail store',
   'masonry_non_combustible', 1925, 28000, 3, 2002, TRUE, '2',
   4000000, 1500000, 2000000, 5000000, 4200000,
   37.787900, -122.407500, NOW(), 'seed (demo)', NOW()),

  -- B-grade joisted-masonry store, fully insured, low cat.
  (:'company_id', '6c098ba9-bf3b-43b0-abd5-e23a1f02f08a', 'Chicago Michigan Ave Store',
   '600 N Michigan Ave', 'Chicago', 'IL', '60611', 'Cook', 'Retail store',
   'joisted_masonry', 1998, 26000, 2, 2015, TRUE, '3',
   3000000, 1000000, 1500000, 3500000, 3500000,
   41.878100, -87.629800, NOW(), 'seed (demo)', NOW()),

  -- A-grade non-combustible store, fully insured, high quake (Cascadia).
  (:'company_id', 'c89ded6a-e2d5-4a30-8679-9a516c9c42b3', 'Seattle Downtown Store',
   '1500 5th Ave', 'Seattle', 'WA', '98101', 'King', 'Retail store',
   'non_combustible', 2015, 24000, 2, 2015, TRUE, '3',
   2800000, 1100000, 1400000, 3200000, 3200000,
   47.606200, -122.332100, NOW(), 'seed (demo)', NOW());

-- Per-building catastrophe perils (flood / quake / wildfire / wind), matched by name.
WITH b AS (
  SELECT id, name FROM company_property_buildings WHERE company_id = :'company_id'
)
INSERT INTO property_building_perils (building_id, peril, zone, score, tier, source)
SELECT b.id, v.peril, v.zone, v.score, v.tier, v.source
FROM b
JOIN (VALUES
  -- Dallas HQ
  ('Dallas Flagship & HQ', 'flood',    'X (minimal)',      15, 'low',      'FEMA NFHL'),
  ('Dallas Flagship & HQ', 'quake',    'SDS 0.10g',         8, 'low',      'USGS'),
  ('Dallas Flagship & HQ', 'wildfire', 'WHP 1',            10, 'low',      'USFS WHP'),
  ('Dallas Flagship & HQ', 'wind',     'TX Gulf (inland)', 72, 'high',     'FEMA wind zone (coarse)'),
  -- Miami DC
  ('Miami Distribution Center', 'flood',    'AE (1% annual)',  88, 'severe',   'FEMA NFHL'),
  ('Miami Distribution Center', 'quake',    'SDS 0.05g',        5, 'low',      'USGS'),
  ('Miami Distribution Center', 'wildfire', 'WHP 1',            8, 'low',      'USFS WHP'),
  ('Miami Distribution Center', 'wind',     'Miami-Dade HVHZ', 96, 'severe',   'FEMA wind zone (coarse)'),
  -- Orlando store
  ('Orlando Store #14', 'flood',    'X (minimal)',     30, 'moderate', 'FEMA NFHL'),
  ('Orlando Store #14', 'quake',    'SDS 0.05g',        5, 'low',      'USGS'),
  ('Orlando Store #14', 'wildfire', 'WHP 3',           52, 'elevated', 'USFS WHP'),
  ('Orlando Store #14', 'wind',     'FL statewide',    90, 'severe',   'FEMA wind zone (coarse)'),
  -- SF store
  ('San Francisco Union Sq Store', 'flood',    'X (minimal)',     12, 'low',      'FEMA NFHL'),
  ('San Francisco Union Sq Store', 'quake',    'SDS 1.50g',       92, 'severe',   'USGS'),
  ('San Francisco Union Sq Store', 'wildfire', 'WHP 2',           35, 'moderate', 'USFS WHP'),
  ('San Francisco Union Sq Store', 'wind',     'CA Pacific',      20, 'low',      'FEMA wind zone (coarse)'),
  -- Chicago store
  ('Chicago Michigan Ave Store', 'flood',    'X (minimal)',     28, 'moderate', 'FEMA NFHL'),
  ('Chicago Michigan Ave Store', 'quake',    'SDS 0.12g',       12, 'low',      'USGS'),
  ('Chicago Michigan Ave Store', 'wildfire', 'WHP 1',            6, 'low',      'USFS WHP'),
  ('Chicago Michigan Ave Store', 'wind',     'IL inland',       25, 'low',      'FEMA wind zone (coarse)'),
  -- Seattle store
  ('Seattle Downtown Store', 'flood',    'X (minimal)',     14, 'low',      'FEMA NFHL'),
  ('Seattle Downtown Store', 'quake',    'SDS 0.90g',       78, 'high',     'USGS'),
  ('Seattle Downtown Store', 'wildfire', 'WHP 2',           34, 'moderate', 'USFS WHP'),
  ('Seattle Downtown Store', 'wind',     'WA Pacific',      22, 'low',      'FEMA wind zone (coarse)')
) AS v(bname, peril, zone, score, tier, source) ON v.bname = b.name;

-- Enable the property feature for Roystar so the /app/property page + nav render.
UPDATE companies
SET enabled_features = COALESCE(enabled_features, '{}'::jsonb) || '{"property": true}'::jsonb
WHERE id = :'company_id';

COMMIT;

-- Summary readout
SELECT name, construction_type, sprinklered,
       (building_value + COALESCE(contents_value,0) + COALESCE(bi_value,0)) AS tiv,
       round(insured_value / NULLIF(replacement_cost,0), 2) AS itv
FROM company_property_buildings
WHERE company_id = :'company_id'
ORDER BY tiv DESC;
