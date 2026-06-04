-- Additive Action Center demo rows for broker Regina George LLC.
-- Mirrors what broker_milestones / broker_risk_alerts workers would compute
-- from the seeded WC data — inserted directly so we DON'T trigger the risk-alert
-- worker's broker email send. Idempotent via ON CONFLICT. Reversible:
--   DELETE FROM broker_milestones  WHERE broker_id='574c50d6-e3d2-4bef-a4d7-4e153b6da053';
--   DELETE FROM broker_risk_alerts WHERE broker_id='574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND message LIKE '%trailing year%';
BEGIN;

-- ── Milestones (positive achievements) ───────────────────────────────────────
INSERT INTO broker_milestones
  (broker_id, company_id, milestone_key, milestone_family, tier, title, detail,
   current_value, benchmark_value, achieved_at, last_evaluated_at, is_read)
VALUES
  -- Gretchin Weiners (993605b1) — 3 milestones
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','993605b1-9e58-41f1-8115-b3e5c68bc7fc',
   'incident_free_180','incident_free',180,'180 days incident-free',
   '200 days since the last recordable incident',200,NULL,NOW(),NOW(),false),
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','993605b1-9e58-41f1-8115-b3e5c68bc7fc',
   'dart_free_year','dart_free',NULL,'DART-free year',
   'No lost-time (DART) cases in the last 12 months — down from 3.',0,NULL,NOW(),NOW(),false),
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','993605b1-9e58-41f1-8115-b3e5c68bc7fc',
   'trir_below_benchmark','trir_below_benchmark',NULL,'TRIR below benchmark',
   'TRIR 0.67 is under the Retail Trade median of 3.6 and trending down.',0.67,3.6,NOW(),NOW(),false),
  -- Limbo (7501ca6a) — 365-day streak + DART-free year
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','7501ca6a-f9ea-4a46-addf-0073b43b5e60',
   'incident_free_365','incident_free',365,'365 days incident-free',
   '400 days since the last recordable incident',400,NULL,NOW(),NOW(),false),
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','7501ca6a-f9ea-4a46-addf-0073b43b5e60',
   'dart_free_year','dart_free',NULL,'DART-free year',
   'No lost-time (DART) cases in the last 12 months — down from 1.',0,NULL,NOW(),NOW(),false)
ON CONFLICT (broker_id, company_id, milestone_key) DO NOTHING;

-- ── Risk alerts (negative trends) ────────────────────────────────────────────
INSERT INTO broker_risk_alerts
  (broker_id, company_id, metric_key, severity, current_value, prior_value, delta_pct,
   premium_direction, message, first_alerted_at, last_alerted_at, last_evaluated_at, is_read)
VALUES
  -- Bags (3e69de7a) — TRIR + DART spikes + premium increase
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','3e69de7a-0c0e-4a34-ab7b-3e9462756516',
   'trir','critical',20,8,150,NULL,
   'TRIR rose 150% over the trailing year (8 → 20).',NOW(),NOW(),NOW(),false),
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','3e69de7a-0c0e-4a34-ab7b-3e9462756516',
   'dart','critical',20,8,150,NULL,
   'DART rate rose 150% over the trailing year (8 → 20).',NOW(),NOW(),NOW(),false),
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','3e69de7a-0c0e-4a34-ab7b-3e9462756516',
   'premium_increase','warning',24750,NULL,NULL,'increase',
   'Estimated WC premium impact now +$24,750/yr and trending up.',NOW(),NOW(),NOW(),false),
  -- Coffee (4b2f5f47) — premium drift
  ('574c50d6-e3d2-4bef-a4d7-4e153b6da053','4b2f5f47-f637-49be-a6a9-aac103622b2f',
   'premium_increase','warning',303,NULL,NULL,'increase',
   'Estimated WC premium impact now +$303/yr and trending up.',NOW(),NOW(),NOW(),false)
ON CONFLICT (broker_id, company_id, metric_key) DO NOTHING;

COMMIT;
