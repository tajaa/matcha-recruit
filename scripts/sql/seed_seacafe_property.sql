-- Seed commercial-property (P-side) demo data for the Sea Cafe dev tenant.
--
-- Sea Cafe is a small coffee chain (one business_location on file), so this seeds a
-- roastery/HQ + four storefronts. Only the roastery ties to the existing location;
-- the storefronts carry their own addresses (location_id NULL is allowed). Spans COPE
-- A→D, fully- and under-insured (ITV), and West-Coast seismic / wildfire catastrophe.
-- Geocode + per-peril hazard seeded directly so the cat UI renders without the
-- external FEMA/USGS/USFS task.
--
-- NOTE: Sea Cafe is matcha_lite (IrSidebar), so the /app/property nav link won't
-- appear in its sidebar — open /app/property directly. The page itself renders once
-- the `property` flag is on (flipped below).
--
-- DEV ONLY (matcha-postgres :5432). Idempotent. Run:
--   PGPASSWORD=matcha_dev psql -h 127.0.0.1 -p 5432 -U matcha -d matcha \
--     -f scripts/sql/seed_seacafe_property.sql

\set company_id '19e02494-8427-44b5-9c1b-98064b7e94e1'

BEGIN;

DELETE FROM company_property_buildings WHERE company_id = :'company_id';

INSERT INTO company_property_buildings
  (company_id, location_id, name, address, city, state, zipcode, county, occupancy,
   construction_type, year_built, sq_ft, stories, roof_year, sprinklered, protection_class,
   building_value, contents_value, bi_value, replacement_cost, insured_value,
   lat, lng, geocoded_at, geocode_source, cat_refreshed_at)
VALUES
  -- A-grade masonry roastery/HQ, fully insured (the big one). Ties to the LA location.
  (:'company_id', 'fcc0c956-6c1a-4dd8-9584-c48890bb4b1f', 'Sea Cafe Roastery & HQ',
   '1320 E 7th St', 'Los Angeles', 'CA', '90021', 'Los Angeles', 'Roastery / commissary / office',
   'masonry_non_combustible', 2016, 22000, 2, 2016, TRUE, '2',
   4500000, 2000000, 2500000, 5000000, 5000000,
   34.033000, -118.230000, NOW(), 'seed (demo)', NOW()),

  -- D-grade old frame storefront, badly under-insured (ITV 0.63), high quake.
  (:'company_id', NULL, 'Sea Cafe — Santa Monica',
   '2901 Main St', 'Santa Monica', 'CA', '90405', 'Los Angeles', 'Cafe storefront',
   'frame', 1968, 3200, 1, 2008, FALSE, '4',
   1200000, 400000, 600000, 1600000, 1000000,
   34.001000, -118.487000, NOW(), 'seed (demo)', NOW()),

  -- C-grade non-combustible storefront, fully insured, wildfire exposure.
  (:'company_id', NULL, 'Sea Cafe — San Diego',
   '2730 Historic Decatur Rd', 'San Diego', 'CA', '92106', 'San Diego', 'Cafe storefront',
   'non_combustible', 2012, 2800, 1, 2012, FALSE, '3',
   1000000, 350000, 500000, 1200000, 1200000,
   32.740000, -117.213000, NOW(), 'seed (demo)', NOW()),

  -- B-grade joisted-masonry storefront, fully insured, Cascadia quake.
  (:'company_id', NULL, 'Sea Cafe — Portland',
   '1001 SE Division St', 'Portland', 'OR', '97202', 'Multnomah', 'Cafe storefront',
   'joisted_masonry', 1995, 3000, 2, 2018, TRUE, '3',
   1100000, 400000, 500000, 1300000, 1300000,
   45.504000, -122.654000, NOW(), 'seed (demo)', NOW()),

  -- A-grade masonry storefront, under-insured (ITV 0.80), high quake.
  (:'company_id', NULL, 'Sea Cafe — Seattle',
   '1424 11th Ave', 'Seattle', 'WA', '98122', 'King', 'Cafe storefront',
   'masonry_non_combustible', 2008, 3400, 2, 2008, TRUE, '4',
   1300000, 450000, 600000, 1500000, 1200000,
   47.614000, -122.317000, NOW(), 'seed (demo)', NOW());

WITH b AS (
  SELECT id, name FROM company_property_buildings WHERE company_id = :'company_id'
)
INSERT INTO property_building_perils (building_id, peril, zone, score, tier, source)
SELECT b.id, v.peril, v.zone, v.score, v.tier, v.source
FROM b
JOIN (VALUES
  -- Roastery LA
  ('Sea Cafe Roastery & HQ', 'flood',    'X (minimal)',  16, 'low',      'FEMA NFHL'),
  ('Sea Cafe Roastery & HQ', 'quake',    'SDS 1.30g',    85, 'high',     'USGS'),
  ('Sea Cafe Roastery & HQ', 'wildfire', 'WHP 3',        50, 'elevated', 'USFS WHP'),
  ('Sea Cafe Roastery & HQ', 'wind',     'CA Pacific',   18, 'low',      'FEMA wind zone (coarse)'),
  -- Santa Monica
  ('Sea Cafe — Santa Monica', 'flood',    'X (coastal)',  34, 'moderate', 'FEMA NFHL'),
  ('Sea Cafe — Santa Monica', 'quake',    'SDS 1.40g',    88, 'high',     'USGS'),
  ('Sea Cafe — Santa Monica', 'wildfire', 'WHP 2',        36, 'moderate', 'USFS WHP'),
  ('Sea Cafe — Santa Monica', 'wind',     'CA Pacific',   18, 'low',      'FEMA wind zone (coarse)'),
  -- San Diego
  ('Sea Cafe — San Diego', 'flood',    'X (minimal)',  14, 'low',      'FEMA NFHL'),
  ('Sea Cafe — San Diego', 'quake',    'SDS 0.80g',    58, 'elevated', 'USGS'),
  ('Sea Cafe — San Diego', 'wildfire', 'WHP 4',        72, 'high',     'USFS WHP'),
  ('Sea Cafe — San Diego', 'wind',     'CA Pacific',   16, 'low',      'FEMA wind zone (coarse)'),
  -- Portland
  ('Sea Cafe — Portland', 'flood',    'X (minimal)',  20, 'low',      'FEMA NFHL'),
  ('Sea Cafe — Portland', 'quake',    'SDS 0.85g',    76, 'high',     'USGS'),
  ('Sea Cafe — Portland', 'wildfire', 'WHP 2',        34, 'moderate', 'USFS WHP'),
  ('Sea Cafe — Portland', 'wind',     'OR Pacific',   18, 'low',      'FEMA wind zone (coarse)'),
  -- Seattle
  ('Sea Cafe — Seattle', 'flood',    'X (minimal)',  14, 'low',      'FEMA NFHL'),
  ('Sea Cafe — Seattle', 'quake',    'SDS 0.90g',    78, 'high',     'USGS'),
  ('Sea Cafe — Seattle', 'wildfire', 'WHP 2',        32, 'moderate', 'USFS WHP'),
  ('Sea Cafe — Seattle', 'wind',     'WA Pacific',   20, 'low',      'FEMA wind zone (coarse)')
) AS v(bname, peril, zone, score, tier, source) ON v.bname = b.name;

UPDATE companies
SET enabled_features = COALESCE(enabled_features, '{}'::jsonb) || '{"property": true}'::jsonb
WHERE id = :'company_id';

COMMIT;

SELECT name, construction_type, sprinklered,
       (building_value + COALESCE(contents_value,0) + COALESCE(bi_value,0)) AS tiv,
       round(insured_value / NULLIF(replacement_cost,0), 2) AS itv
FROM company_property_buildings
WHERE company_id = :'company_id'
ORDER BY tiv DESC;
