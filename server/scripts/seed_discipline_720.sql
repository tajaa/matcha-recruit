-- Seed discipline test data for "720 Behavioral" demo tenant.
-- Idempotent on policy mappings (UNIQUE(company_id, infraction_type)).
-- Re-running will append duplicate progressive_discipline rows — guard
-- with the WHERE NOT EXISTS clause around the INSERT body if you don't
-- want that.
--
-- Run from the EC2 host:
--   ssh -i roonMT-arm.pem ec2-user@3.101.83.217 \
--     "sudo docker exec -i matcha-postgres psql -U matcha -d matcha" \
--     < server/scripts/seed_discipline_720.sql

\set ON_ERROR_STOP on
BEGIN;

-- Infraction → severity policy mappings the recommend engine uses as defaults.
INSERT INTO discipline_policy_mapping (
    company_id, infraction_type, label, default_severity,
    lookback_months_minor, lookback_months_moderate, lookback_months_severe,
    auto_to_written
)
VALUES
  ('1a1123e5-4c24-4735-8501-9a64a1dd7691', 'attendance',         'Attendance / tardiness',         'minor',             6, 9, 12, false),
  ('1a1123e5-4c24-4735-8501-9a64a1dd7691', 'documentation',      'Documentation errors',           'moderate',          6, 9, 12, false),
  ('1a1123e5-4c24-4735-8501-9a64a1dd7691', 'patient_safety',     'Patient safety / clinical care', 'severe',            6, 9, 12, true),
  ('1a1123e5-4c24-4735-8501-9a64a1dd7691', 'hipaa',              'HIPAA / privacy violation',      'severe',            6, 9, 12, true),
  ('1a1123e5-4c24-4735-8501-9a64a1dd7691', 'professionalism',    'Professionalism / conduct',      'moderate',          6, 9, 12, false),
  ('1a1123e5-4c24-4735-8501-9a64a1dd7691', 'workplace_violence', 'Workplace violence / threats',   'immediate_written', 6, 9, 12, true)
ON CONFLICT (company_id, infraction_type) DO NOTHING;

-- Skip seeding if records already exist for this tenant — keeps the script
-- safely re-runnable.
DO $$
DECLARE
  existing int;
BEGIN
  SELECT count(*) INTO existing
  FROM progressive_discipline
  WHERE company_id = '1a1123e5-4c24-4735-8501-9a64a1dd7691';
  IF existing > 0 THEN
    RAISE NOTICE 'progressive_discipline already has % rows for 720 Behavioral — skipping seed', existing;
    RETURN;
  END IF;

  WITH emp AS (
    SELECT id, first_name FROM employees
    WHERE org_id = '1a1123e5-4c24-4735-8501-9a64a1dd7691'
      AND first_name IN ('Aisha','Andre','Brian','Carlos','Dana','Brittany','Angela','Christina')
  ),
  inserted AS (
    INSERT INTO progressive_discipline (
      employee_id, company_id, discipline_type, issued_date, issued_by,
      description, expected_improvement, review_date,
      status, infraction_type, severity, lookback_months,
      expires_at, signature_status, meeting_held_at
    )
    SELECT
      e.id,
      '1a1123e5-4c24-4735-8501-9a64a1dd7691'::uuid,
      d.discipline_type,
      d.issued_date,
      '55c8b446-b174-4042-ba1e-4d2f437bd609'::uuid,
      d.description,
      d.expected_improvement,
      d.review_date,
      d.status,
      d.infraction_type,
      d.severity,
      d.lookback_months,
      d.expires_at,
      d.signature_status,
      d.meeting_held_at
    FROM emp e
    JOIN (VALUES
      ('Aisha',     'verbal_warning',  (CURRENT_DATE -   7)::date, 'Late to morning huddle on three occasions over the past two weeks.', 'Arrive on or before 8:55am for daily huddle.',     (CURRENT_DATE +  21)::date, 'active',          'attendance',      'minor',             6,  (NOW() + INTERVAL '6 months'),  'signed',  (NOW() - INTERVAL '7 days')),
      ('Andre',     'written_warning', (CURRENT_DATE -  14)::date, 'Documentation completed late for 4 sessions, exceeding 48hr policy.','All session notes locked within 48 hours.',        (CURRENT_DATE +  30)::date, 'active',          'documentation',   'moderate',          9,  (NOW() + INTERVAL '9 months'),  'signed',  (NOW() - INTERVAL '14 days')),
      ('Brian',     'pip',             (CURRENT_DATE -  21)::date, '60-day Performance Improvement Plan covering caseload management.',  'Maintain caseload of 22 with 95% note compliance.', (CURRENT_DATE +  60)::date, 'active',          'professionalism', 'moderate',          9,  (NOW() + INTERVAL '9 months'),  'signed',  (NOW() - INTERVAL '21 days')),
      ('Carlos',    'final_warning',   (CURRENT_DATE -  30)::date, 'Final warning following repeated documentation infractions.',        'Zero late or missing notes for next 90 days.',     (CURRENT_DATE +  90)::date, 'active',          'documentation',   'severe',            12, (NOW() + INTERVAL '12 months'), 'signed',  (NOW() - INTERVAL '30 days')),
      ('Dana',      'suspension',      (CURRENT_DATE -  45)::date, '3-day unpaid suspension following confirmed HIPAA disclosure.',      'Complete HIPAA refresher; no further violations.', (CURRENT_DATE +  30)::date, 'completed',       'hipaa',           'severe',            12, (NOW() + INTERVAL '12 months'), 'signed',  (NOW() - INTERVAL '45 days')),
      ('Brittany',  'written_warning', (CURRENT_DATE -   3)::date, 'Pending HR meeting to review patient safety report.',                'Follow safety protocol on every patient handoff.', (CURRENT_DATE +  14)::date, 'pending_meeting', 'patient_safety',  'severe',            12, NULL,                            'pending', NULL),
      ('Angela',    'verbal_warning',  (CURRENT_DATE - 200)::date, 'Verbal coaching for tardiness — issue resolved.',                    'N/A',                                              (CURRENT_DATE - 170)::date, 'expired',         'attendance',      'minor',             6,  (NOW() - INTERVAL '20 days'),   'signed',  (NOW() - INTERVAL '200 days')),
      ('Christina', 'written_warning', (CURRENT_DATE -   1)::date, 'Drafted but not yet issued — pending manager review.',               'TBD',                                              (CURRENT_DATE +  30)::date, 'draft',           'professionalism', 'moderate',          9,  NULL,                            'pending', NULL)
    ) AS d(first_name, discipline_type, issued_date, description, expected_improvement, review_date, status, infraction_type, severity, lookback_months, expires_at, signature_status, meeting_held_at)
      ON e.first_name = d.first_name
    RETURNING id, '55c8b446-b174-4042-ba1e-4d2f437bd609'::uuid AS issuer
  )
  INSERT INTO discipline_audit_log (discipline_id, actor_user_id, action, details)
  SELECT id, issuer, 'created', jsonb_build_object('seed', true) FROM inserted;
END $$;

COMMIT;

-- Sanity check
SELECT status, count(*) AS records
FROM progressive_discipline
WHERE company_id = '1a1123e5-4c24-4735-8501-9a64a1dd7691'
GROUP BY status
ORDER BY status;
