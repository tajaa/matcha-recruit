-- ============================================================================
-- Demo seed for broker "Regina George LLC" (test broker ashVidales+regina@gmail.com)
--   broker_id 574c50d6-e3d2-4bef-a4d7-4e153b6da053 · user fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566
--
-- Populates the WC-depth + EPL-readiness features across a realistic spread so
-- the new tabs/strips render. DEV target. Idempotent. INSERT/UPDATE only (no DDL).
-- All seeded emails use reserved *.test domains (never deliverable).
--
-- Run:  docker exec -i matcha-postgres psql -U matcha -d matcha < server/scripts/seed_broker_demo.sql
-- ============================================================================

BEGIN;

-- 1. WC claim typing + return-to-work on existing recordables -----------------
-- Bags (construction CT cluster; 2 post-term; some open lost-time)
UPDATE ir_incidents SET wc_claim_type='acute',             return_to_work_date=occurred_at::date+30 WHERE id='998ffa0a-8f89-4c30-8c78-744e7d71b866';
UPDATE ir_incidents SET wc_claim_type='acute',             return_to_work_date=occurred_at::date+25 WHERE id='bef7fe6e-d941-454d-a2a5-0930f7ce749d';
UPDATE ir_incidents SET wc_claim_type='cumulative_trauma', return_to_work_date=occurred_at::date+45 WHERE id='311aedb2-6d00-432d-af24-234e3dce3aff';
UPDATE ir_incidents SET wc_claim_type='cumulative_trauma', post_termination=true                    WHERE id='4140fb91-0330-475b-a7fa-cb041618fa9b';
UPDATE ir_incidents SET wc_claim_type='cumulative_trauma', return_to_work_date=occurred_at::date+60 WHERE id='9f9fc7dc-1d44-47a2-b3d9-038e33002d62';
UPDATE ir_incidents SET wc_claim_type='cumulative_trauma', post_termination=true                    WHERE id='caee5874-81a0-43e5-a689-fe4d4a713dc5';
UPDATE ir_incidents SET wc_claim_type='cumulative_trauma'                                           WHERE id='98f4f7ec-e266-4596-8218-b60fa1744722';
-- Gretchin Weiners (mostly resolved, 1 CT)
UPDATE ir_incidents SET wc_claim_type='acute',             return_to_work_date=occurred_at::date+20 WHERE id='be3f1914-6b86-4934-8b40-42fd9806b86b';
UPDATE ir_incidents SET wc_claim_type='acute',             return_to_work_date=occurred_at::date+30 WHERE id='46d6dcf4-4db5-43d4-b1da-4db8f87bb062';
UPDATE ir_incidents SET wc_claim_type='cumulative_trauma', return_to_work_date=occurred_at::date+50 WHERE id='1d53e532-6ea5-4f61-bea5-415c95c5d79e';
UPDATE ir_incidents SET wc_claim_type='acute'                                                       WHERE id='38ff5dd0-fa18-4222-b333-b93249a76938';
-- Sea Cafe (one big open 30-day CT lost-time)
UPDATE ir_incidents SET wc_claim_type='acute'                                                       WHERE id='adec838b-64ec-48ea-a95a-4d176395b7c8';
UPDATE ir_incidents SET wc_claim_type='acute',             return_to_work_date=occurred_at::date+21 WHERE id='b1271c26-af80-4197-bfc2-5144c57dd637';
UPDATE ir_incidents SET wc_claim_type='cumulative_trauma'                                           WHERE id='3e1eb03d-287d-4693-8633-2b9f6df87e76';

-- 2. Experience-mod trajectory ----------------------------------------------
INSERT INTO company_wc_mods (company_id, broker_id, policy_period_start, policy_period_end, experience_mod, carrier, annual_premium, note, recorded_by) VALUES
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2024-01-01','2024-12-31',1.05,'Travelers',112500,'baseline','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2025-01-01','2025-12-31',1.18,'Travelers',124000,'CT claims driving mod up','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2026-01-01','2026-12-31',1.32,'Travelers',138000,'continued CT severity','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2024-01-01','2024-12-31',0.98,'Hartford',180000,NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2025-01-01','2025-12-31',0.95,'Hartford',176000,'safety program','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2026-01-01','2026-12-31',0.92,'Hartford',172000,'continued credit','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('19e02494-8427-44b5-9c1b-98064b7e94e1','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2025-01-01','2025-12-31',1.10,'AmTrust',110000,NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('19e02494-8427-44b5-9c1b-98064b7e94e1','574c50d6-e3d2-4bef-a4d7-4e153b6da053','2026-01-01','2026-12-31',1.15,'AmTrust',118000,'open lost-time claim','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566')
ON CONFLICT ON CONSTRAINT uq_company_wc_mod DO NOTHING;

-- 3. NCCI rates for the book's operating states (so the overlay isn't blank) --
INSERT INTO wc_state_rates (state, loss_cost_change_pct, effective_date, trend, source, note) VALUES
 ('CA',-2.0,'2026-01-01','decrease','seed (demo)','CT-claim pressure; CA = CT epicenter'),
 ('IL', 1.5,'2026-01-01','increase','seed (demo)',NULL),
 ('NY',-3.0,'2026-01-01','decrease','seed (demo)',NULL),
 ('TX',-1.0,'2026-01-01','decrease','seed (demo)',NULL)
ON CONFLICT ON CONSTRAINT uq_wc_state_rate DO NOTHING;

-- 4. Anti-harassment policies + signatures (reserved *.test emails) -----------
INSERT INTO policies (id, company_id, title, content, status, category, source_type, effective_date) VALUES
 ('a0000001-0000-0000-0000-000000000001','993605b1-9e58-41f1-8115-b3e5c68bc7fc','Anti-Harassment & EEO Policy','Seed demo policy.','active','anti-harassment','manual',CURRENT_DATE),
 ('a0000001-0000-0000-0000-000000000002','3e69de7a-0c0e-4a34-ab7b-3e9462756516','Anti-Harassment & EEO Policy','Seed demo policy.','active','anti-harassment','manual',CURRENT_DATE),
 ('a0000001-0000-0000-0000-000000000003','19e02494-8427-44b5-9c1b-98064b7e94e1','Anti-Harassment & EEO Policy','Seed demo policy.','active','anti-harassment','manual',CURRENT_DATE)
ON CONFLICT (id) DO NOTHING;

-- Gretchin: 11/12 signed (~92%)
INSERT INTO policy_signatures (policy_id, signer_type, signer_name, signer_email, token, status, signed_at, expires_at)
SELECT 'a0000001-0000-0000-0000-000000000001','employee','Employee '||g,'signer'||g||'@gretchin.test',
       'a0000001-0000-0000-0000-000000000001-'||g,
       CASE WHEN g<=11 THEN 'signed' ELSE 'pending' END,
       CASE WHEN g<=11 THEN NOW() ELSE NULL END, NOW()+interval '90 days'
FROM generate_series(1,12) g ON CONFLICT (token) DO NOTHING;
-- Bags: 2/6 signed (~33%)
INSERT INTO policy_signatures (policy_id, signer_type, signer_name, signer_email, token, status, signed_at, expires_at)
SELECT 'a0000001-0000-0000-0000-000000000002','employee','Employee '||g,'signer'||g||'@bags.test',
       'a0000001-0000-0000-0000-000000000002-'||g,
       CASE WHEN g<=2 THEN 'signed' ELSE 'pending' END,
       CASE WHEN g<=2 THEN NOW() ELSE NULL END, NOW()+interval '90 days'
FROM generate_series(1,6) g ON CONFLICT (token) DO NOTHING;
-- Sea Cafe: 5/8 signed (~62%)
INSERT INTO policy_signatures (policy_id, signer_type, signer_name, signer_email, token, status, signed_at, expires_at)
SELECT 'a0000001-0000-0000-0000-000000000003','employee','Employee '||g,'signer'||g||'@seacafe.test',
       'a0000001-0000-0000-0000-000000000003-'||g,
       CASE WHEN g<=5 THEN 'signed' ELSE 'pending' END,
       CASE WHEN g<=5 THEN NOW() ELSE NULL END, NOW()+interval '90 days'
FROM generate_series(1,8) g ON CONFLICT (token) DO NOTHING;

-- 5. Wage-hour compliance per showcase location (idempotent NOT EXISTS guard) -
INSERT INTO compliance_requirements (location_id, category, jurisdiction_level, jurisdiction_name, title, current_value, effective_date)
SELECT bl.id, cat.category, 'state', bl.state, cat.title, cat.val, CURRENT_DATE
FROM business_locations bl
CROSS JOIN (VALUES ('minimum_wage','State minimum wage','$16.00/hr'),
                   ('overtime','Daily overtime threshold','8 hrs/day'),
                   ('pay_frequency','Pay frequency','Semi-monthly')) AS cat(category,title,val)
WHERE bl.company_id IN ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','3e69de7a-0c0e-4a34-ab7b-3e9462756516','19e02494-8427-44b5-9c1b-98064b7e94e1')
  AND NOT EXISTS (SELECT 1 FROM compliance_requirements cr WHERE cr.location_id=bl.id AND cr.category=cat.category);

-- 6. EPL attestations (the 5 attested factors) -------------------------------
INSERT INTO company_epl_attestations (company_id, broker_id, item_key, status, note, updated_by) VALUES
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','pay_transparency','in_place',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','biometrics_bipa','in_place',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','pay_equity','partial','annual study planned','fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','ai_hiring_audit','partial',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('993605b1-9e58-41f1-8115-b3e5c68bc7fc','574c50d6-e3d2-4bef-a4d7-4e153b6da053','dei_posture','in_place',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','pay_transparency','gap',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','pay_equity','gap',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','ai_hiring_audit','gap',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('3e69de7a-0c0e-4a34-ab7b-3e9462756516','574c50d6-e3d2-4bef-a4d7-4e153b6da053','dei_posture','partial',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('19e02494-8427-44b5-9c1b-98064b7e94e1','574c50d6-e3d2-4bef-a4d7-4e153b6da053','pay_transparency','partial',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('19e02494-8427-44b5-9c1b-98064b7e94e1','574c50d6-e3d2-4bef-a4d7-4e153b6da053','biometrics_bipa','gap',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566'),
 ('19e02494-8427-44b5-9c1b-98064b7e94e1','574c50d6-e3d2-4bef-a4d7-4e153b6da053','pay_equity','partial',NULL,'fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566')
ON CONFLICT ON CONSTRAINT uq_company_epl_attestation DO UPDATE SET
    status=EXCLUDED.status, note=EXCLUDED.note, updated_by=EXCLUDED.updated_by, updated_at=NOW();

-- 7. Close one Gretchin ER case (so the ER factor shows a resolution rate) ----
UPDATE er_cases SET status='closed', closed_at=NOW(), outcome='resolved'
WHERE id=(SELECT id FROM er_cases WHERE company_id='993605b1-9e58-41f1-8115-b3e5c68bc7fc' AND status<>'closed' ORDER BY created_at LIMIT 1);

COMMIT;
