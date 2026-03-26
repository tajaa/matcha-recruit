"""add credential_types and role_categories reference tables

Revision ID: y0z1a2b3c4d5
Revises: x9y0z1a2b3c4
Create Date: 2026-03-26
"""

from alembic import op


revision = "y0z1a2b3c4d5"
down_revision = "x9y0z1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── credential_types: living registry of credential kinds ─────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS credential_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key VARCHAR(60) NOT NULL UNIQUE,
            label VARCHAR(200) NOT NULL,
            category VARCHAR(40) NOT NULL DEFAULT 'clinical',
            description TEXT,
            has_expiration BOOLEAN NOT NULL DEFAULT true,
            has_number BOOLEAN NOT NULL DEFAULT false,
            has_state BOOLEAN NOT NULL DEFAULT false,
            verification_method VARCHAR(40) DEFAULT 'document_upload',
            is_system BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Seed with existing 6 types + new granular types
    op.execute("""
        INSERT INTO credential_types (key, label, category, description, has_expiration, has_number, has_state) VALUES
        -- Existing 6 types (match credential_inference.py VALID_DOCUMENT_TYPES)
        ('medical_license',        'Professional License',                    'clinical',    'State-issued professional license (MD, RN, PT, etc.)',                      true,  true,  true),
        ('dea',                    'DEA Registration',                        'federal',     'DEA controlled substance registration',                                    true,  true,  false),
        ('npi',                    'NPI Verification',                        'federal',     'National Provider Identifier',                                             false, true,  false),
        ('board_cert',             'Board Certification',                     'clinical',    'Board certification in a specialty',                                       true,  true,  false),
        ('malpractice',            'Malpractice Insurance',                   'insurance',   'Professional liability / malpractice insurance',                           true,  true,  false),
        ('health_clearance',       'Health Clearance (General)',              'clearance',   'General health clearance (legacy catch-all)',                               true,  false, false),
        -- New granular training certifications
        ('bls_cert',               'BLS Certification',                       'training',    'Basic Life Support certification',                                         true,  true,  false),
        ('acls_cert',              'ACLS Certification',                      'training',    'Advanced Cardiovascular Life Support certification',                        true,  true,  false),
        ('pals_cert',              'PALS Certification',                      'training',    'Pediatric Advanced Life Support certification',                            true,  true,  false),
        ('cpr_cert',               'CPR Certification',                       'training',    'CPR certification (non-BLS)',                                              true,  true,  false),
        ('cpi_cert',               'CPI Certification',                       'training',    'Crisis Prevention Institute certification',                                true,  true,  false),
        -- Health clearances (granular)
        ('tb_test',                'TB Test',                                  'clearance',   'Tuberculosis screening (PPD or chest X-ray)',                              true,  false, false),
        ('hep_b_vaccine',          'Hepatitis B Vaccination',                  'clearance',   'Hepatitis B vaccination series or titer',                                 false, false, false),
        ('flu_vaccine',            'Influenza Vaccination',                    'clearance',   'Annual influenza vaccination or declination',                              true,  false, false),
        ('covid_vaccine',          'COVID-19 Vaccination',                     'clearance',   'COVID-19 vaccination series',                                             false, false, false),
        ('drug_screening',         'Drug Screening',                           'clearance',   'Pre-employment or periodic drug screening',                               false, false, false),
        ('physical_exam',          'Physical Examination',                     'clearance',   'Pre-employment or annual physical exam',                                  true,  false, false),
        -- Background checks
        ('background_check',       'Background Check',                         'background',  'Criminal background check',                                               false, false, true),
        ('fingerprint_clearance',  'Fingerprint Clearance',                    'background',  'State fingerprint-based background check (e.g., CA LiveScan)',             false, false, true),
        ('child_abuse_clearance',  'Child Abuse Clearance',                    'background',  'Child abuse history clearance (e.g., PA Act 33)',                          false, false, true),
        ('fbi_background',         'FBI Background Check',                     'background',  'Federal FBI criminal background check',                                   false, false, false),
        ('oig_exclusion_check',    'OIG Exclusion Check',                      'background',  'OIG List of Excluded Individuals/Entities check',                         true,  false, false),
        ('sam_exclusion_check',    'SAM Exclusion Check',                      'background',  'System for Award Management exclusion check',                             true,  false, false),
        -- Other
        ('food_handler_card',      'Food Handler Card',                        'clearance',   'Food handler certification (dietary/nutrition roles)',                     true,  true,  true),
        ('drivers_license',        'Driver''s License',                        'clearance',   'Valid driver''s license (home health, transport roles)',                   true,  true,  true),
        ('infection_control',      'Infection Control Training',               'training',    'State-mandated infection control training (e.g., NY)',                     true,  false, true)
        ON CONFLICT (key) DO NOTHING
    """)

    # ── role_categories: normalizes _ROLE_PATTERNS into DB ────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS role_categories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key VARCHAR(60) NOT NULL UNIQUE,
            label VARCHAR(200) NOT NULL,
            match_patterns TEXT[],
            is_clinical BOOLEAN NOT NULL DEFAULT true,
            sort_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Seed from credential_inference.py _ROLE_PATTERNS
    op.execute(r"""
        INSERT INTO role_categories (key, label, match_patterns, is_clinical, sort_order) VALUES
        ('physician',       'Physician',                         ARRAY['\m(physician|doctor|md|m\.d\.|do|d\.o\.|attending|hospitalist|surgeon)\M'],  true,  1),
        ('psychiatrist',    'Psychiatrist',                      ARRAY['\mpsychiatrist\M'],                                                         true,  2),
        ('dentist',         'Dentist',                           ARRAY['\m(dentist|dds|dmd|oral surgeon)\M'],                                       true,  3),
        ('np_aprn',         'Nurse Practitioner / APRN',         ARRAY['\m(nurse practitioner|aprn|crna|cnm|np)\M'],                                true,  4),
        ('pa',              'Physician Assistant',               ARRAY['\m(physician assistant|pa-c|pa)\M'],                                        true,  5),
        ('pharmacist',      'Pharmacist',                        ARRAY['\mpharmacist\M'],                                                           true,  6),
        ('rn',              'Registered Nurse',                  ARRAY['\m(registered nurse|rn|charge nurse|nurse manager|staff nurse)\M'],          true,  7),
        ('lpn_lvn',         'Licensed Practical/Vocational Nurse', ARRAY['\m(lpn|lvn|licensed practical nurse|licensed vocational nurse)\M'],        true,  8),
        ('therapist',       'Therapist (PT/OT/SLP/RT)',          ARRAY['\m(physical therapist|occupational therapist|speech.*pathologist|respiratory therapist|pt|ot|slp|ccc-slp)\M'], true, 9),
        ('psychologist',    'Psychologist',                      ARRAY['\mpsychologist\M'],                                                         true,  10),
        ('licensed_counselor', 'Licensed Counselor/Social Worker', ARRAY['\m(lcsw|lmft|lpc|licensed.*(social worker|counselor|therapist))\M'],      true,  11),
        ('behavioral_health', 'Behavioral Health Tech',          ARRAY['\m(behavioral.*(tech|specialist)|counselor|case manager)\M'],               true,  12),
        ('cna_ma',          'CNA / Medical Assistant',           ARRAY['\m(cna|certified nursing assistant|medical assistant|patient care tech|pct)\M'], true, 13),
        ('pharmacy_tech',   'Pharmacy Technician',               ARRAY['\mpharmacy tech\M'],                                                       true,  14),
        ('lab_rad_tech',    'Lab / Radiology Technologist',      ARRAY['\m(radiology|x-ray|imaging|lab|laboratory|phlebotom|sonograph|ultrasound)\M.*\m(tech|specialist|scientist)\M'], true, 15),
        ('paramedic_emt',   'Paramedic / EMT',                   ARRAY['\m(paramedic|emt|emergency medical tech)\M'],                               true,  16),
        ('dietitian',       'Dietitian / Nutritionist',          ARRAY['\m(dietitian|dietician|nutritionist|rd)\M'],                                true,  17),
        ('non_clinical',    'Non-Clinical / Administrative',     ARRAY['\m(admin|administrator|receptionist|front desk|billing|coder|medical records|scheduler|hr|human resources|it |information tech|marketing|sales|finance|accounting|executive|director of operations|office manager|practice manager|compliance officer|ceo|cfo|coo|cto)\M'], false, 99)
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS role_categories")
    op.execute("DROP TABLE IF EXISTS credential_types")
