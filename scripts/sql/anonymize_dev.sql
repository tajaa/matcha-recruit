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
-- ALSO NOT SCRUBBED: `is_test` companies (Sunset Smile Dental Group, 720
-- Behavioral, Onc, ...) and their directly-owned rows (employees via org_id,
-- clients/business_locations/ir_incidents/ir_people/external_identities via
-- company_id, offer_letters via company_id, and the `users` rows reached via
-- clients.user_id / employees.user_id). These are demo data shown to buyers —
-- scrubbing them would rename the tenant out from under
-- scripts/sync-test-tenants.sh's UUID-keyed lookup and break the sync's own
-- email-normalization comparison. Real customer data is unaffected: this
-- carve-out only widens as `is_test` is opted into, never narrows existing
-- scrubbing.
--
-- Secrets/tokens (blocks 6-7) ARE ALSO exempted for is_test companies, for a
-- different reason than the rest of this carve-out: sync_tenants.py's merge
-- engine descends the FK graph from a test company's `companies` row and
-- pushes whatever it finds there BACK TO PROD. Scrubbing (e.g.)
-- companies.report_email_token or mw_subscriptions.stripe_subscription_id
-- here doesn't stay in dev — the next `sync-test-tenants.sh --auto` (wired
-- into every deploy) treats the scrub as a dev-side edit and overwrites the
-- live prod value with it. Only tables/columns reachable from a test
-- company's row are exempted below; a table with no company-scoping column
-- (gusto_webhook_tokens, beta_invitations, project_outreach) isn't in the
-- sync's descend graph regardless, so scrubbing it can't leak to prod.
--
-- Column list validated against the live prod schema on 2026-05-25. Re-validate
-- (\d <table>) if the schema has changed since.

\set ON_ERROR_STOP on
BEGIN;

-- Test-tenant carve-out, materialized once. The DO block tolerates a prod
-- dump taken before migration testacct01 landed (companies.is_test absent):
-- the temp table stays empty and everything is scrubbed — same degradation
-- the refresh script's own leak check already does.
CREATE TEMP TABLE _test_companies (id uuid PRIMARY KEY);
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'companies' AND column_name = 'is_test') THEN
    EXECUTE 'INSERT INTO _test_companies SELECT id FROM companies WHERE is_test';
  END IF;
END $$;

-- ============================================================================
-- 1. AUTH — reset logins to a known dev password, drop OAuth tokens.
--    All users share one password (printed by the refresh script).
--    EXCEPTION: emails in the preserve allowlist (the dev owner's own
--    accounts, substituted as __PRESERVE_EMAILS__ by the refresh script) keep
--    their REAL email + REAL password_hash, so you can sign into dev with your
--    traditional credentials instead of being gated to anonymized test users.
--    Empty allowlist => ARRAY[]::text[] => every user scrubbed (the default).
-- ============================================================================
-- Drop the Gmail OAuth token for EVERY user (a live secret) — even preserved.
UPDATE users SET gmail_token = NULL;
-- Scrub email + password only for users NOT in the preserve allowlist and not
-- owned by an is_test company (see the note above the WHAT IS NOT SCRUBBED
-- section).
UPDATE users SET
    password_hash = '__DEV_PW_HASH__',
    email         = 'user_' || replace(id::text, '-', '') || '@example.com'
WHERE email <> ALL(ARRAY[__PRESERVE_EMAILS__]::text[])
  AND id NOT IN (
    SELECT user_id FROM clients WHERE user_id IS NOT NULL
      AND company_id IN (SELECT id FROM _test_companies)
    UNION
    SELECT user_id FROM employees WHERE user_id IS NOT NULL
      AND org_id IN (SELECT id FROM _test_companies)
  );

-- ============================================================================
-- 2. EMAILS (identifiers) -> RFC-2606 reserved domains (never deliverable).
--    id-derived where the column is UNIQUE / NOT NULL to avoid collisions.
-- ============================================================================
UPDATE employees SET
    email          = 'emp_' || replace(id::text, '-', '') || '@example.com',
    personal_email = CASE WHEN personal_email IS NOT NULL
                          THEN 'emp_' || replace(id::text, '-', '') || '@personal.example.com' END
WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = employees.org_id);
UPDATE candidates                SET email = CASE WHEN email IS NOT NULL THEN 'cand_' || replace(id::text,'-','') || '@example.com' END;
UPDATE ir_people                 SET email = CASE WHEN email IS NOT NULL THEN 'person_' || replace(id::text,'-','') || '@example.com' END
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = ir_people.company_id);
UPDATE ir_incidents              SET reported_by_email = CASE WHEN reported_by_email IS NOT NULL THEN 'reporter_' || replace(id::text,'-','') || '@example.com' END
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = ir_incidents.company_id);
UPDATE ir_investigation_interviews SET interviewee_email = CASE WHEN interviewee_email IS NOT NULL THEN 'interviewee_' || replace(id::text,'-','') || '@example.com' END;
UPDATE lead_contacts             SET email = CASE WHEN email IS NOT NULL THEN 'lead_' || replace(id::text,'-','') || '@example.com' END;
UPDATE external_identities       SET external_email = CASE WHEN external_email IS NOT NULL THEN 'ext_' || replace(id::text,'-','') || '@example.com' END
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = external_identities.company_id);
UPDATE offer_letters             SET candidate_email = CASE WHEN candidate_email IS NOT NULL THEN 'offer_' || replace(id::text,'-','') || '@example.com' END
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = offer_letters.company_id);
UPDATE mw_review_requests        SET recipient_email = 'review_' || replace(id::text,'-','') || '@example.com';
UPDATE beta_invitations          SET email = 'beta_' || replace(id::text,'-','') || '@example.com';
UPDATE company_sso_configs       SET email_domain = 'example.com';

-- ============================================================================
-- 3. PERSON NAMES -> synthetic. (Synthetic, not nulled, so NOT NULL holds and
--    the dev UI still renders something sensible.)
-- ============================================================================
UPDATE admins        SET name = 'Admin ' || left(replace(id::text,'-',''), 6);
UPDATE employees     SET first_name = 'Test', last_name = 'Emp-' || left(replace(id::text,'-',''), 6)
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = employees.org_id);
UPDATE candidates    SET name = CASE WHEN name IS NOT NULL THEN 'Candidate ' || left(replace(id::text,'-',''), 6) END;
UPDATE clients       SET name = 'Client ' || left(replace(id::text,'-',''), 6)
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = clients.company_id);
UPDATE ir_people     SET display_name = 'Person ' || left(replace(id::text,'-',''), 6),
                         normalized_name = 'person ' || left(replace(id::text,'-',''), 6)
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = ir_people.company_id);
UPDATE ir_incidents  SET reported_by_name = 'Reporter ' || left(replace(id::text,'-',''), 6)
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = ir_incidents.company_id);
UPDATE ir_investigation_interviews SET interviewee_name = CASE WHEN interviewee_name IS NOT NULL THEN 'Interviewee ' || left(replace(id::text,'-',''), 6) END;
UPDATE lead_contacts SET name = 'Lead ' || left(replace(id::text,'-',''), 6),
                         first_name = CASE WHEN first_name IS NOT NULL THEN 'Lead' END,
                         last_name  = CASE WHEN last_name  IS NOT NULL THEN left(replace(id::text,'-',''), 6) END,
                         linkedin_url = NULL;
UPDATE offer_letters SET candidate_name = 'Candidate ' || left(replace(id::text,'-',''), 6),
                         manager_name   = CASE WHEN manager_name IS NOT NULL THEN 'Manager ' || left(replace(id::text,'-',''), 6) END
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = offer_letters.company_id);

-- ============================================================================
-- 4. COMPANY NAMES (real customer identities). Scrubbed because these are
--    confidential. >>> To KEEP real company names for dev usability, comment
--    out this whole block. <<<
-- ============================================================================
UPDATE companies     SET name = 'Company ' || left(replace(id::text,'-',''), 8)
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = companies.id);
UPDATE offer_letters SET company_name = 'Company ' || left(replace(COALESCE(company_id, id)::text,'-',''), 8)
    WHERE company_name IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = offer_letters.company_id);

-- ============================================================================
-- 5. CONTACT / LOCATION PII
-- ============================================================================
UPDATE employees      SET phone = NULL, address = NULL, emergency_contact = '{}'::jsonb
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = employees.org_id);
UPDATE candidates     SET phone = NULL, resume_text = NULL, parsed_data = '{}'::jsonb;
UPDATE clients        SET phone = NULL
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = clients.company_id);
UPDATE lead_contacts  SET phone = NULL;
UPDATE business_locations SET address = NULL   -- keep city/state/zip for jurisdiction realism
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = business_locations.company_id);

-- ============================================================================
-- 6. SECRETS / ACCESS TOKENS -> random-unique (NOT NULL) or NULL (nullable).
--    is_test-owned rows (reachable from the sync's FK walk) are exempted —
--    see the note atop this file: a scrub here would get pushed to live
--    prod by the next sync-test-tenants.sh run.
-- ============================================================================
UPDATE password_reset_tokens SET token = md5(random()::text || clock_timestamp()::text || id::text)
    WHERE user_id NOT IN (
        SELECT user_id FROM clients WHERE user_id IS NOT NULL
          AND company_id IN (SELECT id FROM _test_companies)
        UNION
        SELECT user_id FROM employees WHERE user_id IS NOT NULL
          AND org_id IN (SELECT id FROM _test_companies)
      );
UPDATE employee_invitations  SET token = md5(random()::text || clock_timestamp()::text || id::text)
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = employee_invitations.org_id);
UPDATE project_outreach      SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE beta_invitations      SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE mw_review_requests    SET token = md5(random()::text || clock_timestamp()::text || id::text);
UPDATE gusto_webhook_tokens  SET verification_token = md5(random()::text || clock_timestamp()::text || id::text),
                                 gusto_company_uuid = NULL;
UPDATE er_case_export_links  SET token = md5(random()::text || clock_timestamp()::text || id::text),
                                 password_hash = '__DEV_PW_HASH__'
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = er_case_export_links.org_id);
UPDATE offer_letters         SET candidate_token = NULL
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = offer_letters.company_id);
UPDATE companies             SET report_email_token = NULL
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = companies.id);
UPDATE ir_investigation_interviews SET invite_token = NULL
    WHERE NOT EXISTS (
        SELECT 1 FROM ir_incidents ii
        JOIN _test_companies tc ON tc.id = ii.company_id
        WHERE ii.id = ir_investigation_interviews.incident_id
      );
UPDATE company_sso_configs   SET idp_x509_cert = '-----BEGIN CERTIFICATE-----' || chr(10) || 'DEV-SCRUBBED' || chr(10) || '-----END CERTIFICATE-----'
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = company_sso_configs.company_id);
UPDATE integration_connections SET secrets = '{}'::jsonb, config = '{}'::jsonb
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = integration_connections.company_id);
UPDATE external_identities   SET external_user_id = NULL, raw_profile = '{}'::jsonb
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = external_identities.company_id);
UPDATE employees             SET hris_id = NULL, external_uid = NULL
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = employees.org_id);
TRUNCATE oauth_states;       -- ephemeral CSRF state, no value in dev

-- ============================================================================
-- 7. THIRD-PARTY BILLING IDS -> fake, so dev never touches prod Stripe.
--    is_test-owned rows exempted for the same reason as block 6.
-- ============================================================================
UPDATE mw_subscriptions  SET stripe_subscription_id = 'sub_dev_' || replace(id::text,'-',''),
                             stripe_customer_id      = 'cus_dev_' || replace(id::text,'-','')
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = mw_subscriptions.company_id);
UPDATE mw_stripe_sessions SET stripe_session_id      = 'cs_dev_'  || replace(id::text,'-','')
    WHERE NOT EXISTS (SELECT 1 FROM _test_companies tc WHERE tc.id = mw_stripe_sessions.company_id);

COMMIT;

-- Sanity (outside the txn): must return 0. Preserved (allowlisted) emails and
-- is_test-company users are intentionally real, so both are excluded from
-- the leak count (test-tenant emails are already reserved-domain post-scrub
-- via scripts/sync_tenants.py, so this is defensive, not expected to fire).
SELECT 'LEAK: non-reserved user emails = ' || count(*) AS check
FROM users
WHERE email NOT LIKE '%@example.com'
  AND email <> ALL(ARRAY[__PRESERVE_EMAILS__]::text[])
  AND id NOT IN (
    SELECT user_id FROM clients WHERE user_id IS NOT NULL
      AND company_id IN (SELECT id FROM _test_companies)
    UNION
    SELECT user_id FROM employees WHERE user_id IS NOT NULL
      AND org_id IN (SELECT id FROM _test_companies)
  );
