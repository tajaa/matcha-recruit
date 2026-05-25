-- anonymize_dev.sql
-- Scrubs PII / secrets / third-party IDs from a FRESH CLONE of the production
-- matcha DB so it is safe to use as a local dev database.
--
-- Invoked by scripts/refresh-dev-from-prod.sh AFTER prod has been cloned into a
-- staging DB (matcha_new) and BEFORE the rename-swap. NEVER runs against prod.
--
-- Contract:
--   * runs with `psql -v ON_ERROR_STOP=1` inside a single transaction, so an
--     unknown column aborts the whole thing and the staging DB is discarded —
--     dev is never left half-scrubbed.
--   * the refresh script substitutes __DEV_PW_HASH__ with a real bcrypt(cost 10)
--     hash of the dev login password before this file is shipped to the host.
--
-- WHAT IS DELIBERATELY *NOT* SCRUBBED (kept for dev realism — extend below if
-- you need them gone): free-text narratives such as ir_incidents.description /
-- root_cause / corrective_actions, companies.*_summary / *_notes / company_values,
-- offer_letters.benefits, lead_contacts.gemini_ranking_reason,
-- mw_review_requests.feedback, chat/message bodies. These can embed PII but are
-- the substance devs usually need.
--
-- Column list validated against the live prod schema on 2026-05-25. Re-validate
-- (\d <table>) if the schema has changed since.

\set ON_ERROR_STOP on
BEGIN;

-- ============================================================================
-- 1. AUTH — reset every login to a known dev password, drop OAuth tokens.
--    All users share one password (printed by the refresh script); log in with
--    any anonymized email below.
-- ============================================================================
UPDATE users SET
    password_hash = '__DEV_PW_HASH__',
    email         = 'user_' || replace(id::text, '-', '') || '@example.com',
    gmail_token   = NULL;

-- ============================================================================
-- 2. EMAILS (identifiers) -> RFC-2606 reserved domains (never deliverable).
--    id-derived where the column is UNIQUE / NOT NULL to avoid collisions.
-- ============================================================================
UPDATE employees SET
    email          = 'emp_' || replace(id::text, '-', '') || '@example.com',
    personal_email = CASE WHEN personal_email IS NOT NULL
                          THEN 'emp_' || replace(id::text, '-', '') || '@personal.example.com' END;
UPDATE candidates                SET email = CASE WHEN email IS NOT NULL THEN 'cand_' || replace(id::text,'-','') || '@example.com' END;
UPDATE ir_people                 SET email = CASE WHEN email IS NOT NULL THEN 'person_' || replace(id::text,'-','') || '@example.com' END;
UPDATE ir_incidents              SET reported_by_email = CASE WHEN reported_by_email IS NOT NULL THEN 'reporter_' || replace(id::text,'-','') || '@example.com' END;
UPDATE ir_investigation_interviews SET interviewee_email = CASE WHEN interviewee_email IS NOT NULL THEN 'interviewee_' || replace(id::text,'-','') || '@example.com' END;
UPDATE lead_contacts             SET email = CASE WHEN email IS NOT NULL THEN 'lead_' || replace(id::text,'-','') || '@example.com' END;
UPDATE external_identities       SET external_email = CASE WHEN external_email IS NOT NULL THEN 'ext_' || replace(id::text,'-','') || '@example.com' END;
UPDATE offer_letters             SET candidate_email = CASE WHEN candidate_email IS NOT NULL THEN 'offer_' || replace(id::text,'-','') || '@example.com' END;
UPDATE mw_review_requests        SET recipient_email = 'review_' || replace(id::text,'-','') || '@example.com';
UPDATE beta_invitations          SET email = 'beta_' || replace(id::text,'-','') || '@example.com';
UPDATE company_sso_configs       SET email_domain = 'example.com';

-- ============================================================================
-- 3. PERSON NAMES -> synthetic. (Synthetic, not nulled, so NOT NULL holds and
--    the dev UI still renders something sensible.)
-- ============================================================================
UPDATE admins        SET name = 'Admin ' || left(replace(id::text,'-',''), 6);
UPDATE employees     SET first_name = 'Test', last_name = 'Emp-' || left(replace(id::text,'-',''), 6);
UPDATE candidates    SET name = CASE WHEN name IS NOT NULL THEN 'Candidate ' || left(replace(id::text,'-',''), 6) END;
UPDATE clients       SET name = 'Client ' || left(replace(id::text,'-',''), 6);
UPDATE ir_people     SET display_name = 'Person ' || left(replace(id::text,'-',''), 6),
                         normalized_name = 'person ' || left(replace(id::text,'-',''), 6);
UPDATE ir_incidents  SET reported_by_name = 'Reporter ' || left(replace(id::text,'-',''), 6);
UPDATE ir_investigation_interviews SET interviewee_name = CASE WHEN interviewee_name IS NOT NULL THEN 'Interviewee ' || left(replace(id::text,'-',''), 6) END;
UPDATE lead_contacts SET name = 'Lead ' || left(replace(id::text,'-',''), 6),
                         first_name = CASE WHEN first_name IS NOT NULL THEN 'Lead' END,
                         last_name  = CASE WHEN last_name  IS NOT NULL THEN left(replace(id::text,'-',''), 6) END,
                         linkedin_url = NULL;
UPDATE offer_letters SET candidate_name = 'Candidate ' || left(replace(id::text,'-',''), 6),
                         manager_name   = CASE WHEN manager_name IS NOT NULL THEN 'Manager ' || left(replace(id::text,'-',''), 6) END;

-- ============================================================================
-- 4. COMPANY NAMES (real customer identities). Scrubbed because these are
--    confidential. >>> To KEEP real company names for dev usability, comment
--    out this whole block. <<<
-- ============================================================================
UPDATE companies     SET name = 'Company ' || left(replace(id::text,'-',''), 8);
UPDATE offer_letters SET company_name = 'Company ' || left(replace(company_id::text,'-',''), 8) WHERE company_id IS NOT NULL;

-- ============================================================================
-- 5. CONTACT / LOCATION PII
-- ============================================================================
UPDATE employees      SET phone = NULL, address = NULL, emergency_contact = '{}'::jsonb;
UPDATE candidates     SET phone = NULL, resume_text = NULL, parsed_data = '{}'::jsonb;
UPDATE clients        SET phone = NULL;
UPDATE lead_contacts  SET phone = NULL;
UPDATE business_locations SET address = NULL;   -- keep city/state/zip for jurisdiction realism

-- ============================================================================
-- 6. SECRETS / ACCESS TOKENS -> random-unique (NOT NULL) or NULL (nullable).
-- ============================================================================
UPDATE password_reset_tokens SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE employee_invitations  SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE project_outreach      SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE beta_invitations      SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE mw_review_requests    SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE gusto_webhook_tokens  SET verification_token = md5(random()::text || clock_timestamp()::text || id::text),
                                 gusto_company_uuid = NULL;
UPDATE er_case_export_links  SET token = md5(random()::text || clock_timestamp()::text || id::text),
                                 password_hash = '__DEV_PW_HASH__';
UPDATE offer_letters         SET candidate_token = NULL;
UPDATE companies             SET report_email_token = NULL;
UPDATE ir_investigation_interviews SET invite_token = NULL;
UPDATE company_sso_configs   SET idp_x509_cert = '-----BEGIN CERTIFICATE-----' || chr(10) || 'DEV-SCRUBBED' || chr(10) || '-----END CERTIFICATE-----';
UPDATE integration_connections SET secrets = '{}'::jsonb, config = '{}'::jsonb;
UPDATE external_identities   SET external_user_id = NULL, raw_profile = '{}'::jsonb;
UPDATE employees             SET hris_id = NULL, external_uid = NULL;
TRUNCATE oauth_states;       -- ephemeral CSRF state, no value in dev

-- ============================================================================
-- 7. THIRD-PARTY BILLING IDS -> fake, so dev never touches prod Stripe.
-- ============================================================================
UPDATE mw_subscriptions  SET stripe_subscription_id = 'sub_dev_' || replace(id::text,'-',''),
                             stripe_customer_id      = 'cus_dev_' || replace(id::text,'-','');
UPDATE mw_stripe_sessions SET stripe_session_id      = 'cs_dev_'  || replace(id::text,'-','');

COMMIT;

-- Sanity (outside the txn): must return 0.
SELECT 'LEAK: non-reserved user emails = ' || count(*) AS check
FROM users WHERE email NOT LIKE '%@example.com';
