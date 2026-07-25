-- CA SB 553 (Cal. Lab. Code § 6401.9) — Workplace Violence Prevention Plan,
-- decomposed into its 5 checkable obligations (reqcomp01 / requirement_components).
--
-- This is CATALOG data, not tenant data: requirement_components hangs off
-- jurisdiction_requirements (the shared SSOT catalog), so this pack seeds the
-- decomposition once and every CA tenant sees it. No company_id anywhere in
-- this file.
--
-- The catalog row itself is server-generated (Gemini research), so its id is
-- NOT a fixed constant across dev/prod/other environments — it is resolved
-- here by (state, regulation_key), not hardcoded. If a given environment has
-- not yet researched CA's workplace_violence_prevention requirement, this
-- INSERT...SELECT simply inserts 0 rows (additive, no error, safe to re-run
-- after that catalog row lands).
--
-- Component ids are left to the column default (gen_random_uuid()) — NOT
-- pinned constants. Idempotency comes from the real uniqueness constraint
-- (reqcomp01: UNIQUE (jurisdiction_requirement_id, component_key)), and the
-- ON CONFLICT target below names that pair explicitly. A pinned-UUID scheme
-- assumes exactly one CA catalog row matches the WHERE clause; if an
-- environment ever has two (regulation_key already spans unrelated statutes
-- across states, and dedup migration 92583427c259 exists precisely because
-- catalog rows collide), a pinned id would silently seed components for only
-- the first match and insert nothing for the second — no error, just a
-- permanently un-decomposable duplicate.
--
-- `j.country_code` uses the same `COALESCE(country_code,'US')` idiom as
-- authority_ingest.py / penalty_schedules.py / admin_onboarding.py — legacy
-- jurisdiction rows can have a NULL country_code that means US, not "unknown
-- country".
--
-- CITATION NOTE: subsection-letter citations below are the best available
-- read of Cal. Lab. Code § 6401.9's structure (written plan / training /
-- incident log / hazard identification / annual review) but have NOT been
-- independently re-verified against the current statute text as part of this
-- change — do not treat `verified_at` as set until a human confirms the exact
-- subsection letters against the live code. Left NULL here deliberately,
-- matching the compliance_evals golden-fixture rule: an unverified citation
-- must not claim verification it hasn't had.
--
-- The violent-incident-log obligation's `derivation_key` is NULL (attest-only):
-- it used to derive `compliant` from a free-text ILIKE match against
-- ir_incidents, but a matching incident title proves an incident was
-- mentioned, not that the statute's log (with its required fields and 5-year
-- retention) exists — see compliance_status.py's blind-never-violating
-- invariant. Only `annual_training` is derivable today.
--
-- No BEGIN/COMMIT/SAVEPOINT here — scripts/seed-prod.sh owns the transaction
-- envelope. Every INSERT is ON CONFLICT DO NOTHING (idempotent re-run).
--
-- Undo: sb553_components.undo.sql

INSERT INTO requirement_components
    (jurisdiction_requirement_id, component_key, label, question,
     statute_citation, suggested_fix, severity, derivation_key, sort_order)
SELECT jr.id, v.component_key, v.label, v.question,
       v.statute_citation, v.suggested_fix, v.severity, v.derivation_key, v.sort_order
FROM jurisdiction_requirements jr
JOIN jurisdictions j ON j.id = jr.jurisdiction_id
JOIN (VALUES
    ('written_plan', 'Written WVP Plan',
     'Is there a written, site-specific workplace violence prevention plan, accessible to employees?',
     'Cal. Lab. Code § 6401.9(b)', 'Draft a written plan covering the statute''s required elements.',
     'critical', NULL, 1),
    ('annual_training', 'Annual Training',
     'Have all employees completed interactive workplace-violence-prevention training within the last 12 months?',
     'Cal. Lab. Code § 6401.9(b) (training)', 'Scope and assign an annual training program.',
     'critical', 'wvp_training', 2),
    ('violent_incident_log', 'Violent Incident Log',
     'Are workplace violence incidents, threats, and near-misses logged and retained for 5 years?',
     'Cal. Lab. Code § 6401.9(c) (violent incident log)', 'Deploy a violent-incident log with 5-year retention.',
     'critical', NULL, 3),
    ('hazard_assessment', 'Hazard Assessment',
     'Has each site had a workplace-specific violence hazard assessment?',
     'Cal. Lab. Code § 6401.9(b) (hazard identification)', 'Schedule per-site hazard assessments.',
     'important', NULL, 4),
    ('annual_review', 'Annual Review',
     'Is there an annual plan review and a post-incident review cadence in place?',
     'Cal. Lab. Code § 6401.9(f) (annual review)', 'Set an annual review cadence.',
     'important', NULL, 5)
) AS v(component_key, label, question, statute_citation, suggested_fix, severity, derivation_key, sort_order)
  ON true
WHERE j.state = 'CA' AND j.level = 'state' AND COALESCE(j.country_code, 'US') = 'US'
  AND jr.regulation_key = 'workplace_violence_prevention'
ON CONFLICT (jurisdiction_requirement_id, component_key) DO NOTHING;
