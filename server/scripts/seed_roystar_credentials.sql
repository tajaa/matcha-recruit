-- Seed Roystar as a primary care healthcare company with mock credentials
-- Run: psql -U matcha -d matcha -f seed_roystar_credentials.sql

BEGIN;

-- 1. Update company profile
UPDATE companies
SET industry = 'healthcare',
    healthcare_specialties = ARRAY['primary_care']
WHERE id = '78db605a-0f59-40b7-98ba-3832f9d75008';

-- 2. Update employee titles / departments to match a primary care office
UPDATE employees SET job_title = 'Family Medicine Physician', department = 'Clinical' WHERE id = 'a4578c90-2ec9-4440-8f19-d8f446822deb'; -- Alexander Martin
UPDATE employees SET job_title = 'Internal Medicine Physician', department = 'Clinical' WHERE id = '862063ad-e72c-4cd9-9b6f-3a4baf422e4c'; -- John Smith
UPDATE employees SET job_title = 'Nurse Practitioner (FNP-BC)', department = 'Clinical' WHERE id = '6135dfcc-f04d-4329-a3de-0dd18b939270'; -- Amanda Thomas
UPDATE employees SET job_title = 'Nurse Practitioner (FNP-BC)', department = 'Clinical' WHERE id = '9a0551c0-94b6-4524-b389-32c9ad55a072'; -- Jane Doe
UPDATE employees SET job_title = 'Physician Assistant (PA-C)', department = 'Clinical' WHERE id = 'e75182c9-ec25-4653-aaad-758c91468b0a'; -- Jane Austin
UPDATE employees SET job_title = 'Physician Assistant (PA-C)', department = 'Clinical' WHERE id = '296c983d-a8db-4e19-9340-f37e4605229d'; -- Liam Taylor
UPDATE employees SET job_title = 'Registered Nurse (RN)', department = 'Clinical' WHERE id = '06e9855b-ecdf-4d4b-9bae-c21c415e8e2c'; -- Isabella Jackson
UPDATE employees SET job_title = 'Registered Nurse (RN)', department = 'Clinical' WHERE id = '1893177a-e3de-40bd-b7b8-34f30147915e'; -- Lily Carter
UPDATE employees SET job_title = 'Registered Nurse (RN)', department = 'Clinical' WHERE id = '979b9255-204a-4df9-84a3-6974b64727d2'; -- Elena Rodriguez
UPDATE employees SET job_title = 'Medical Assistant (CMA)', department = 'Clinical' WHERE id = '4b78cbcc-031e-4789-ad96-53798fb7563d'; -- Ava Anderson
UPDATE employees SET job_title = 'Medical Assistant (CMA)', department = 'Clinical' WHERE id = '265cae62-225f-4cac-a910-9b56cae1b9c8'; -- Evelyn Young
UPDATE employees SET job_title = 'Medical Assistant (CMA)', department = 'Clinical' WHERE id = '4203328b-472d-4930-aebb-996765a11a02'; -- Chloe King
UPDATE employees SET job_title = 'Practice Manager', department = 'Administration' WHERE id = '98dca456-d904-4383-a06a-88358018727e'; -- Emma Roberts
UPDATE employees SET job_title = 'Front Office Coordinator', department = 'Administration' WHERE id = 'dab81901-6096-438e-bc7c-7b16bb7a3c9f'; -- Charlotte Clark
UPDATE employees SET job_title = 'Medical Billing Specialist', department = 'Administration' WHERE id = 'e8815329-bc64-4a5f-b350-3aa3fe6e8997'; -- Ethan White
UPDATE employees SET job_title = 'Patient Care Coordinator', department = 'Administration' WHERE id = '9f45cdb5-1471-4695-b4be-f5d4b573f477'; -- Harper Robinson
UPDATE employees SET job_title = 'Health IT Specialist', department = 'Technology' WHERE id = '3dcd9727-4fbf-42c5-93ed-e0fcf32bc452'; -- Avery Green
UPDATE employees SET job_title = 'Compliance Officer', department = 'Administration' WHERE id = '09a5a91d-9f92-4484-8981-82d7b6f597d7'; -- David Anderson

-- 3. Upsert credentials

-- Alexander Martin — Family Medicine MD
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, dea_number, dea_expiration,
    board_certification, board_certification_expiration,
    clinical_specialty, oig_status, oig_last_checked,
    malpractice_carrier, malpractice_policy_number, malpractice_expiration
) VALUES (
    'a4578c90-2ec9-4440-8f19-d8f446822deb', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'MD', 'G102847', 'CA', '2026-09-30',
    '1245873691', 'BM4829371', '2026-06-30',
    'American Board of Family Medicine (ABFM)', '2028-01-15',
    'Family Medicine', 'clear', '2025-12-01',
    'ProAssurance', 'PA-2024-88341', '2026-12-31'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, dea_number = EXCLUDED.dea_number,
    dea_expiration = EXCLUDED.dea_expiration, board_certification = EXCLUDED.board_certification,
    board_certification_expiration = EXCLUDED.board_certification_expiration,
    clinical_specialty = EXCLUDED.clinical_specialty, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, malpractice_carrier = EXCLUDED.malpractice_carrier,
    malpractice_policy_number = EXCLUDED.malpractice_policy_number,
    malpractice_expiration = EXCLUDED.malpractice_expiration;

-- John Smith — Internal Medicine MD (license expiring soon)
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, dea_number, dea_expiration,
    board_certification, board_certification_expiration,
    clinical_specialty, oig_status, oig_last_checked,
    malpractice_carrier, malpractice_policy_number, malpractice_expiration
) VALUES (
    '862063ad-e72c-4cd9-9b6f-3a4baf422e4c', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'MD', 'A204519', 'CA', '2026-04-30',
    '1386724509', 'BS7341028', '2027-03-31',
    'American Board of Internal Medicine (ABIM)', '2027-06-01',
    'Internal Medicine / Primary Care', 'clear', '2026-01-15',
    'The Doctors Company', 'TDC-2025-44892', '2026-12-31'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, dea_number = EXCLUDED.dea_number,
    dea_expiration = EXCLUDED.dea_expiration, board_certification = EXCLUDED.board_certification,
    board_certification_expiration = EXCLUDED.board_certification_expiration,
    clinical_specialty = EXCLUDED.clinical_specialty, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, malpractice_carrier = EXCLUDED.malpractice_carrier,
    malpractice_policy_number = EXCLUDED.malpractice_policy_number,
    malpractice_expiration = EXCLUDED.malpractice_expiration;

-- Amanda Thomas — FNP-BC
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, dea_number, dea_expiration,
    board_certification, board_certification_expiration,
    clinical_specialty, oig_status, oig_last_checked,
    malpractice_carrier, malpractice_policy_number, malpractice_expiration
) VALUES (
    '6135dfcc-f04d-4329-a3de-0dd18b939270', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'NP', 'NP95031', 'CA', '2027-02-28',
    '1497830256', 'AT3847291', '2026-11-30',
    'Family Nurse Practitioner-Board Certified (FNP-BC)', '2026-08-20',
    'Primary Care', 'clear', '2026-02-01',
    'NSO (Nurses Service Organization)', 'NSO-2025-77341', '2026-12-31'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, dea_number = EXCLUDED.dea_number,
    dea_expiration = EXCLUDED.dea_expiration, board_certification = EXCLUDED.board_certification,
    board_certification_expiration = EXCLUDED.board_certification_expiration,
    clinical_specialty = EXCLUDED.clinical_specialty, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, malpractice_carrier = EXCLUDED.malpractice_carrier,
    malpractice_policy_number = EXCLUDED.malpractice_policy_number,
    malpractice_expiration = EXCLUDED.malpractice_expiration;

-- Jane Doe — FNP-BC (DEA expiring soon)
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, dea_number, dea_expiration,
    board_certification, board_certification_expiration,
    clinical_specialty, oig_status, oig_last_checked,
    malpractice_carrier, malpractice_policy_number, malpractice_expiration
) VALUES (
    '9a0551c0-94b6-4524-b389-32c9ad55a072', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'NP', 'NP87614', 'CA', '2027-06-30',
    '1538092741', 'AD9182746', '2026-04-15',
    'Family Nurse Practitioner-Board Certified (FNP-BC)', '2027-03-10',
    'Primary Care / Preventive Medicine', 'clear', '2026-01-20',
    'NSO (Nurses Service Organization)', 'NSO-2025-55612', '2026-12-31'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, dea_number = EXCLUDED.dea_number,
    dea_expiration = EXCLUDED.dea_expiration, board_certification = EXCLUDED.board_certification,
    board_certification_expiration = EXCLUDED.board_certification_expiration,
    clinical_specialty = EXCLUDED.clinical_specialty, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, malpractice_carrier = EXCLUDED.malpractice_carrier,
    malpractice_policy_number = EXCLUDED.malpractice_policy_number,
    malpractice_expiration = EXCLUDED.malpractice_expiration;

-- Jane Austin — PA-C
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, dea_number, dea_expiration,
    board_certification, board_certification_expiration,
    clinical_specialty, oig_status, oig_last_checked,
    malpractice_carrier, malpractice_policy_number, malpractice_expiration
) VALUES (
    'e75182c9-ec25-4653-aaad-758c91468b0a', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'PA', 'PA20483', 'CA', '2026-12-31',
    '1604829375', 'AA5837261', '2027-01-31',
    'Physician Assistant-Certified (PA-C)', '2028-05-01',
    'Primary Care', 'clear', '2026-02-10',
    'NORCAL Mutual', 'NM-2025-39841', '2026-12-31'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, dea_number = EXCLUDED.dea_number,
    dea_expiration = EXCLUDED.dea_expiration, board_certification = EXCLUDED.board_certification,
    board_certification_expiration = EXCLUDED.board_certification_expiration,
    clinical_specialty = EXCLUDED.clinical_specialty, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, malpractice_carrier = EXCLUDED.malpractice_carrier,
    malpractice_policy_number = EXCLUDED.malpractice_policy_number,
    malpractice_expiration = EXCLUDED.malpractice_expiration;

-- Liam Taylor — PA-C (license expired)
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, dea_number, dea_expiration,
    board_certification, board_certification_expiration,
    clinical_specialty, oig_status, oig_last_checked,
    malpractice_carrier, malpractice_policy_number, malpractice_expiration
) VALUES (
    '296c983d-a8db-4e19-9340-f37e4605229d', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'PA', 'PA18274', 'CA', '2026-02-28',
    '1719384052', 'AL2948371', '2027-09-30',
    'Physician Assistant-Certified (PA-C)', '2026-11-15',
    'Primary Care', 'clear', '2025-11-30',
    'NORCAL Mutual', 'NM-2025-28374', '2026-12-31'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, dea_number = EXCLUDED.dea_number,
    dea_expiration = EXCLUDED.dea_expiration, board_certification = EXCLUDED.board_certification,
    board_certification_expiration = EXCLUDED.board_certification_expiration,
    clinical_specialty = EXCLUDED.clinical_specialty, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, malpractice_carrier = EXCLUDED.malpractice_carrier,
    malpractice_policy_number = EXCLUDED.malpractice_policy_number,
    malpractice_expiration = EXCLUDED.malpractice_expiration;

-- Isabella Jackson — RN
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, oig_status, oig_last_checked,
    board_certification, board_certification_expiration,
    clinical_specialty
) VALUES (
    '06e9855b-ecdf-4d4b-9bae-c21c415e8e2c', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'RN', 'RN952047', 'CA', '2027-04-30',
    '1823740591', 'clear', '2026-01-15',
    'Ambulatory Care Nursing Certification (AMB-BC)', '2027-09-01',
    'Primary Care Nursing'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, board_certification = EXCLUDED.board_certification,
    board_certification_expiration = EXCLUDED.board_certification_expiration,
    clinical_specialty = EXCLUDED.clinical_specialty;

-- Lily Carter — RN
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, oig_status, oig_last_checked,
    clinical_specialty
) VALUES (
    '1893177a-e3de-40bd-b7b8-34f30147915e', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'RN', 'RN874193', 'CA', '2028-01-31',
    '1934852067', 'clear', '2026-02-01',
    'Primary Care Nursing'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, clinical_specialty = EXCLUDED.clinical_specialty;

-- Elena Rodriguez — RN (license expiring soon)
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    npi_number, oig_status, oig_last_checked,
    clinical_specialty
) VALUES (
    '979b9255-204a-4df9-84a3-6974b64727d2', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'RN', 'RN631024', 'CA', '2026-05-15',
    '1047293851', 'clear', '2026-01-10',
    'Primary Care Nursing'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    npi_number = EXCLUDED.npi_number, oig_status = EXCLUDED.oig_status,
    oig_last_checked = EXCLUDED.oig_last_checked, clinical_specialty = EXCLUDED.clinical_specialty;

-- Ava Anderson — CMA
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    oig_status, oig_last_checked, clinical_specialty
) VALUES (
    '4b78cbcc-031e-4789-ad96-53798fb7563d', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'CMA', 'CMA048321', 'CA', '2027-07-31',
    'clear', '2026-01-20', 'Clinical Support'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    oig_status = EXCLUDED.oig_status, oig_last_checked = EXCLUDED.oig_last_checked,
    clinical_specialty = EXCLUDED.clinical_specialty;

-- Evelyn Young — CMA
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    oig_status, oig_last_checked, clinical_specialty
) VALUES (
    '265cae62-225f-4cac-a910-9b56cae1b9c8', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'CMA', 'CMA073815', 'CA', '2026-10-31',
    'clear', '2026-01-20', 'Clinical Support'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    oig_status = EXCLUDED.oig_status, oig_last_checked = EXCLUDED.oig_last_checked,
    clinical_specialty = EXCLUDED.clinical_specialty;

-- Chloe King — CMA (cert expired)
INSERT INTO employee_credentials (
    employee_id, org_id,
    license_type, license_number, license_state, license_expiration,
    oig_status, oig_last_checked, clinical_specialty
) VALUES (
    '4203328b-472d-4930-aebb-996765a11a02', '78db605a-0f59-40b7-98ba-3832f9d75008',
    'CMA', 'CMA061247', 'CA', '2026-01-31',
    'clear', '2025-12-15', 'Clinical Support'
) ON CONFLICT (employee_id) DO UPDATE SET
    license_type = EXCLUDED.license_type, license_number = EXCLUDED.license_number,
    license_state = EXCLUDED.license_state, license_expiration = EXCLUDED.license_expiration,
    oig_status = EXCLUDED.oig_status, oig_last_checked = EXCLUDED.oig_last_checked,
    clinical_specialty = EXCLUDED.clinical_specialty;

COMMIT;

SELECT 'Seeded ' || COUNT(*) || ' credential records' FROM employee_credentials
WHERE org_id = '78db605a-0f59-40b7-98ba-3832f9d75008';
