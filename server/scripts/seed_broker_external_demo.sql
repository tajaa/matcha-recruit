-- Demo External Book (off-platform / Broker Pro clients) for test broker
-- "Regina George LLC" (broker 574c50d6…, user fb7b0bbc…). Mirrors the pass-through
-- showcase spread: one exposed, one adequate, one at-risk. Joins the existing
-- Northwind prospect. Idempotent (fixed ids, delete+insert). No real PII.
--   docker exec -i matcha-postgres psql -U matcha -d matcha < server/scripts/seed_broker_external_demo.sql

DELETE FROM broker_external_epl_attestations WHERE external_client_id IN
  ('b0000001-0000-0000-0000-000000000001','b0000001-0000-0000-0000-000000000002','b0000001-0000-0000-0000-000000000003');
DELETE FROM broker_external_wc WHERE external_client_id IN
  ('b0000001-0000-0000-0000-000000000001','b0000001-0000-0000-0000-000000000002','b0000001-0000-0000-0000-000000000003');
DELETE FROM broker_external_clients WHERE id IN
  ('b0000001-0000-0000-0000-000000000001','b0000001-0000-0000-0000-000000000002','b0000001-0000-0000-0000-000000000003');

INSERT INTO broker_external_clients (id, broker_id, name, industry, headcount, primary_state, note, status, created_by) VALUES
  ('b0000001-0000-0000-0000-000000000001','574c50d6-e3d2-4bef-a4d7-4e153b6da053','Lakeside Senior Living','healthcare',120,'IL','Prospect — renewal in 90 days','active','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','574c50d6-e3d2-4bef-a4d7-4e153b6da053','Brightline Retail Co','retail',80,'CA','Prospect — clean account','active','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','574c50d6-e3d2-4bef-a4d7-4e153b6da053','Summit Builders','construction',45,'NV','Prospect — rate pressure (NV +21.6%)','active','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566');

-- WC loss-run snapshots (one per client)
INSERT INTO broker_external_wc (external_client_id, period_label, recordable_cases, dart_cases, lost_days, restricted_days, ct_cases, acute_cases, post_termination_cases, lost_time_open, lost_time_resolved, avg_days_to_rtw, current_emr, carrier, annual_premium, updated_by) VALUES
  ('b0000001-0000-0000-0000-000000000001','2024-2025',11,7,220,40,6,5,3,4,3,48,1.28,'Travelers',240000,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','2024-2025',3,1,25,5,1,2,0,0,2,18,0.97,'Hartford',95000,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','2024-2025',7,4,130,20,2,5,1,2,2,35,1.15,'AmTrust',165000,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566');

-- EPL questionnaire answers (all 10 factors; off-platform = all attested)
INSERT INTO broker_external_epl_attestations (external_client_id, item_key, status, updated_by) VALUES
  -- Lakeside (exposed)
  ('b0000001-0000-0000-0000-000000000001','anti_harassment_policy','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000001','harassment_training','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000001','documented_discipline','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000001','er_case_management','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000001','wage_hour_compliance','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000001','pay_transparency','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000001','pay_equity','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000001','dei_posture','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  -- Brightline (adequate/strong)
  ('b0000001-0000-0000-0000-000000000002','anti_harassment_policy','in_place','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','harassment_training','in_place','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','documented_discipline','in_place','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','er_case_management','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','wage_hour_compliance','in_place','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','pay_transparency','in_place','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','pay_equity','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000002','dei_posture','in_place','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  -- Summit (at-risk / mixed)
  ('b0000001-0000-0000-0000-000000000003','anti_harassment_policy','in_place','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','harassment_training','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','documented_discipline','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','er_case_management','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','wage_hour_compliance','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','pay_transparency','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','biometrics_bipa','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','pay_equity','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','ai_hiring_audit','gap','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
  ('b0000001-0000-0000-0000-000000000003','dei_posture','partial','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566');
