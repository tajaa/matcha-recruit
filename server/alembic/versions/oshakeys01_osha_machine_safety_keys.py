"""Seed 5 core OSHA machine/electrical-safety regulation keys.

The ``machine_safety`` category existed with zero keys, so the corresponding
enumerated OSHA authority items (29 CFR 1910.147/.212/.146/.333/.178) could be
classified but never codified — there was no key to link them to a value. These
five are well-defined federal standards, each cited to its eCFR section. Severity
is set from the curated ``compliance_registry`` map (the same source rkdsev01
seeds from). ``authority_source_urls`` points at the primary eCFR text.

Revision ID: oshakeys01
Revises: scopetag01
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "oshakeys01"
down_revision: Union[str, Sequence[str], None] = "scopetag01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (key, name, description, cfr_part, severity) — cfr_part builds the eCFR URL.
_KEYS = [
    ("lockout_tagout",
     "Control of Hazardous Energy (Lockout/Tagout)",
     "Energy-control procedures, equipment, and employee training to disable "
     "machinery during service/maintenance (29 CFR 1910.147).",
     "147", "critical"),
    ("machine_guarding",
     "Machine Guarding — General Requirements",
     "Guards to protect operators from hazards such as points of operation, "
     "ingoing nip points, and rotating parts (29 CFR 1910.212).",
     "212", "critical"),
    ("confined_space",
     "Permit-Required Confined Spaces",
     "Written permit-space program: hazard evaluation, entry permits, atmospheric "
     "testing, attendants, and rescue (29 CFR 1910.146).",
     "146", "critical"),
    ("electrical_safety",
     "Electrical — Safety-Related Work Practices",
     "Selection and use of work practices to prevent electric shock and arc-flash "
     "injuries during work on or near energized parts (29 CFR 1910.333).",
     "333", "critical"),
    ("powered_industrial_trucks",
     "Powered Industrial Trucks",
     "Design, maintenance, and operator training/certification for forklifts and "
     "other powered industrial trucks (29 CFR 1910.178).",
     "178", "high"),
]


def upgrade() -> None:
    conn = op.get_bind()
    cat_id = conn.execute(
        text("SELECT id FROM compliance_categories WHERE slug = 'machine_safety' LIMIT 1")
    ).scalar()
    if cat_id is None:
        raise RuntimeError("machine_safety category missing; seed compliance_categories first")

    inserted = 0
    for key, name, desc, part, severity in _KEYS:
        url = f"https://www.ecfr.gov/current/title-29/part-1910/section-1910.{part}"
        res = conn.execute(
            text(
                """
                INSERT INTO regulation_key_definitions
                    (key, category_slug, category_id, name, description,
                     enforcing_agency, authority_source_urls, state_variance,
                     base_weight, severity, update_frequency,
                     staleness_warning_days, staleness_critical_days, staleness_expired_days)
                VALUES
                    (:key, 'machine_safety', :cat_id, :name, :desc,
                     'OSHA', ARRAY[:url], 'Low/None',
                     1.5, :severity, 'Rarely amended',
                     90, 180, 365)
                ON CONFLICT (category_slug, key) DO NOTHING
                """
            ),
            {"key": key, "cat_id": cat_id, "name": name, "desc": desc,
             "url": url, "severity": severity},
        )
        inserted += res.rowcount or 0
    print(f"oshakeys01: seeded {inserted} OSHA machine-safety keys")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            "DELETE FROM regulation_key_definitions "
            "WHERE category_slug = 'machine_safety' AND key = ANY(:keys)"
        ),
        {"keys": [k[0] for k in _KEYS]},
    )
