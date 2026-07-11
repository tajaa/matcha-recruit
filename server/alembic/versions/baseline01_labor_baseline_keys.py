"""Seed compliance_categories + regulation_key_definitions for the labor baseline.

The federal labor master-list (`compliance_evals/baseline_masterlist.py`) references
regulation keys across 12 labor categories that had NO enumerated keys — and whose
`compliance_categories` rows were never seeded either (they live in the code
CATEGORIES registry but not the table). This migration makes both real so the
baseline eval can score federal + CA-state against the master-list, and so the keys
carry a definition (severity, authority URL) like every other RKD row.

Two steps, both idempotent:
  1. Seed the 12 missing labor `compliance_categories` rows (name/domain/group from
     the registry).
  2. Seed `regulation_key_definitions` for every master-list key not already present,
     with citation + authority_url from the master-list entry and severity from
     `compliance_registry.resolve_severity`.

Revision ID: baseline01
Revises: groundver01
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "baseline01"
down_revision: Union[str, Sequence[str], None] = "groundver01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (slug, name, short) — the 12 labor categories missing from compliance_categories.
_CATEGORIES = [
    ("employee_classification", "Employee Classification", "Classification"),
    ("i9_everify", "I-9 & E-Verify", "I-9/E-Verify"),
    ("warn_act", "WARN Act (Plant Closing & Layoffs)", "WARN Act"),
    ("cobra", "COBRA & Health Coverage Continuation", "COBRA"),
    ("eeo_reporting", "EEO Reporting & Affirmative Action", "EEO/AA"),
    ("background_checks", "Background Checks & Ban the Box", "Background Checks"),
    ("userra", "USERRA (Military Reemployment)", "USERRA"),
    ("garnishment", "Wage Garnishment & Attachment", "Garnishment"),
    ("erisa_benefits", "ERISA & Benefits Compliance", "ERISA"),
    ("pregnancy_accommodation", "Pregnancy & Lactation Accommodation", "Pregnancy Accom"),
    ("equal_pay", "Equal Pay Act & Pay Equity", "Equal Pay"),
    ("nlra_organizing", "NLRA & Union Organizing Rights", "NLRA/Union"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Seed missing labor categories.
    cat_inserted = 0
    for slug, name, short in _CATEGORIES:
        res = conn.execute(
            text(
                """
                INSERT INTO compliance_categories
                    (slug, name, domain, "group", research_mode, sort_order)
                VALUES (:slug, :name, 'labor', 'labor', 'default_sweep', 900)
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {"slug": slug, "name": name},
        )
        cat_inserted += res.rowcount or 0

    # 2. Seed regulation keys for every master-list entry (federal + CA).
    from app.core.compliance_registry import resolve_severity
    from app.core.services.compliance_evals.baseline_masterlist import (
        CA_STATE_LABOR_MASTERLIST,
        FEDERAL_LABOR_MASTERLIST,
    )

    # de-dupe by (category, key); a key can appear in both lists (e.g. daily_weekly_overtime).
    seen = set()
    entries = []
    for e in FEDERAL_LABOR_MASTERLIST + CA_STATE_LABOR_MASTERLIST:
        if (e.category, e.key) in seen:
            continue
        seen.add((e.category, e.key))
        entries.append(e)

    key_inserted = 0
    for e in entries:
        cat_id = conn.execute(
            text("SELECT id FROM compliance_categories WHERE slug = :slug LIMIT 1"),
            {"slug": e.category},
        ).scalar()
        if cat_id is None:
            raise RuntimeError(f"category {e.category!r} missing after seed step")
        severity = resolve_severity(e.category, e.key)
        res = conn.execute(
            text(
                """
                INSERT INTO regulation_key_definitions
                    (key, category_slug, category_id, name, description,
                     authority_source_urls, base_weight, severity,
                     staleness_warning_days, staleness_critical_days, staleness_expired_days)
                VALUES
                    (:key, :slug, :cat_id, :name, :desc,
                     ARRAY[:url], 1.0, :severity, 90, 180, 365)
                ON CONFLICT (category_slug, key) DO NOTHING
                """
            ),
            {"key": e.key, "slug": e.category, "cat_id": cat_id,
             "name": e.citation, "desc": e.applies_note or None,
             "url": e.authority_url, "severity": severity},
        )
        key_inserted += res.rowcount or 0

    print(f"baseline01: seeded {cat_inserted} categories, {key_inserted} regulation keys")


def downgrade() -> None:
    conn = op.get_bind()
    from app.core.services.compliance_evals.baseline_masterlist import (
        CA_STATE_LABOR_MASTERLIST,
        FEDERAL_LABOR_MASTERLIST,
    )
    pairs = {(e.category, e.key) for e in FEDERAL_LABOR_MASTERLIST + CA_STATE_LABOR_MASTERLIST}
    for cat, key in pairs:
        conn.execute(
            text(
                "DELETE FROM regulation_key_definitions "
                "WHERE category_slug = :slug AND key = :key"
            ),
            {"slug": cat, "key": key},
        )
    for slug, _n, _s in _CATEGORIES:
        conn.execute(
            text("DELETE FROM compliance_categories WHERE slug = :slug"),
            {"slug": slug},
        )
