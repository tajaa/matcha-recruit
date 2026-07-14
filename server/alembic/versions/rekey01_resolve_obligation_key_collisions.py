"""Resolve the 6 live obligation-key collisions — two obligations, one tag.

b694559 ("one obligation, one tag, one active row") deliberately did NOT touch
these. They are not duplicates: they are KEY COLLISIONS, two genuinely different
obligations wearing one regulation_key. A blind supersede would have DELETED a
live obligation, so that pass reported them and stopped. This is the curation it
left to a human (COMPLIANCE_SYSTEM_GAP_REVIEW.md §9, the idempotency lane).

    LA · billing_integrity · provider_enrollment_revalidation
        "Medi-Cal Provider Enrollment and Screening"  vs  the Medicare rule
        -> medicaid_provider_enrollment   (42 CFR 455 Subpart E is a STATE
           Medicaid program with its own agency, screening levels and
           revalidation clock — not the Medicare rule wearing a state name)

    LA · payer_relations · medicare_advantage_compliance
        "California Prior Authorization Reform (SB 306)"  vs  the MA rule
        -> prior_authorization_requirements   (SB 306 is a prior-auth statute;
           it has nothing to do with Medicare Advantage)

    LA · quality_reporting · mips_qpp
        "California Adverse Event Reporting (22 CCR 70972)"  vs  MIPS
        -> state_quality_reporting_mandates   (a state hospital adverse-event
           mandate; MIPS is the federal CMS program)

    NY · minimum_wage · exempt_salary_threshold
        "…Exempt Salary Threshold (Downstate)"  vs  the statewide threshold
        -> exempt_salary_threshold_regional, via rate_type
           'exempt_salary_regional'. minimum_wage derives its write identity
           from RATE_TYPE, not regulation_key (_compute_key_parts), so the key
           alone cannot separate them — the dialect entry in keys.py is what
           makes the two rows two identities.

    Paris / Singapore · sick_leave · statutory_sick_leave
        Maternity leave  vs  sick leave
        -> leave · statutory_maternity_leave   (maternity is not sick leave;
           they were colliding because the maternity rows were filed under
           sick_leave to begin with)

The mis-keyed titles recur across 16-17 jurisdictions (SB 306, adverse-event
reporting), all wrong the same way, so the re-key is applied wherever the
(title, category, regulation_key) triple matches — not just where a collision
happens to have formed.

**requirement_key is recomputed by calling _compute_key_parts itself**, not by
rebuilding the string here. It is the ON-CONFLICT write identity and is derived
from category + rate_type + applicable_entity_types + title; reconstructing it
by hand is what makes this migration dangerous. If the stored identity doesn't
match what a future research pass will compute, the next pass mints a TWIN and
re-opens the collision it just closed.

Idempotent (re-running matches nothing). A row whose target identity is already
taken by another row in the same jurisdiction is SKIPPED and reported, never
overwritten.

Revision ID: rekey01
Revises: codify03
Create Date: 2026-07-14
"""
from alembic import op
from sqlalchemy import text

revision = "rekey01"
down_revision = "codify03"
branch_labels = None
depends_on = None


# title, old_category, old_key -> new_category, new_key, new_rate_type|None
_REKEYS = [
    ("Medi-Cal Provider Enrollment and Screening",
     "billing_integrity", "provider_enrollment_revalidation",
     "billing_integrity", "medicaid_provider_enrollment", None),
    ("California Prior Authorization Reform (SB 306)",
     "payer_relations", "medicare_advantage_compliance",
     "payer_relations", "prior_authorization_requirements", None),
    ("California Adverse Event Reporting (22 CCR 70972)",
     "quality_reporting", "mips_qpp",
     "quality_reporting", "state_quality_reporting_mandates", None),
    ("Executive/Administrative Exempt Salary Threshold (Downstate)",
     "minimum_wage", "exempt_salary_threshold",
     "minimum_wage", "exempt_salary_threshold_regional", "exempt_salary_regional"),
    ("Maternity Leave (Congé de Maternité)",
     "sick_leave", "statutory_sick_leave",
     "leave", "statutory_maternity_leave", None),
    ("Government-Paid Maternity Leave (GPML)",
     "sick_leave", "statutory_sick_leave",
     "leave", "statutory_maternity_leave", None),
]

# RKD rows for the two keys the registry gained (compliance_registry.py). The
# code registry is the source of truth; this seeds its DB projection, without
# which key_definition_id can't resolve and the tagging suite flags the rows.
_NEW_RKD = [
    ("medicaid_provider_enrollment", "billing_integrity",
     "Medicaid Provider Enrollment & Screening (42 CFR Part 455 Subpart E)",
     "State Medicaid enrollment, screening, site visits, fingerprinting and "
     "revalidation — administered by the state Medicaid agency.",
     "medicaid.gov/medicaid/program-integrity"),
    ("exempt_salary_threshold_regional", "minimum_wage",
     "Exempt Employee Salary Threshold — Regional Tier",
     "Higher exempt-salary threshold applying to a named sub-state region "
     "(e.g. NY downstate: NYC, Nassau, Suffolk, Westchester).",
     "dol.ny.gov"),
]


def _entity_types(raw) -> list:
    """applicable_entity_types comes back as a JSONB *string* on this driver.

    _compute_key_parts prefixes the identity with `aet[0]`, so handing it the raw
    string yields `[` as the prefix — a silently corrupted write identity
    (`[:billing_integrity:...`). Caught by dry-running this migration before
    applying it.
    """
    import json

    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    return list(raw) if isinstance(raw, (list, tuple)) else []


def upgrade() -> None:
    from app.core.services.compliance_service import _compute_key_parts

    conn = op.get_bind()

    for key, slug, name, desc, url in _NEW_RKD:
        cat_id = conn.execute(
            text("SELECT id FROM compliance_categories WHERE slug = :s LIMIT 1"),
            {"s": slug},
        ).scalar()
        if cat_id is None:
            raise RuntimeError(f"compliance_categories row missing for {slug!r}")
        conn.execute(
            text("""
                INSERT INTO regulation_key_definitions
                    (key, category_slug, category_id, name, description,
                     authority_source_urls, base_weight, severity,
                     staleness_warning_days, staleness_critical_days, staleness_expired_days)
                VALUES (:k, :s, :cid, :n, :d, ARRAY[:u], 1.0, 'moderate', 90, 180, 365)
                ON CONFLICT (category_slug, key) DO NOTHING
            """),
            {"k": key, "s": slug, "cid": cat_id, "n": name, "d": desc, "u": url},
        )

    rekeyed = skipped = 0
    for title, old_cat, old_key, new_cat, new_key, new_rate in _REKEYS:
        rows = conn.execute(
            text("""
                SELECT jr.id, jr.jurisdiction_id, jr.title, jr.rate_type,
                       jr.jurisdiction_level, jr.jurisdiction_name,
                       jr.applicable_entity_types,
                       COALESCE(j.country_code, 'US') AS country_code
                FROM jurisdiction_requirements jr
                JOIN jurisdictions j ON j.id = jr.jurisdiction_id
                WHERE jr.title = :t AND jr.category = :c
                  AND jr.regulation_key = :k
                  AND COALESCE(jr.status, 'active') = 'active'
            """),
            {"t": title, "c": old_cat, "k": old_key},
        ).mappings().all()

        new_cat_id = conn.execute(
            text("SELECT id FROM compliance_categories WHERE slug = :s LIMIT 1"),
            {"s": new_cat},
        ).scalar()
        kd_id = conn.execute(
            text("SELECT id FROM regulation_key_definitions "
                 "WHERE key = :k AND category_slug = :s LIMIT 1"),
            {"k": new_key, "s": new_cat},
        ).scalar()

        for r in rows:
            # Recompute the identity the way the upsert will, so a future
            # research pass UPDATEs this row instead of minting a twin.
            req = {
                "category": new_cat,
                "title": r["title"],
                "jurisdiction_name": r["jurisdiction_name"],
                "jurisdiction_level": r["jurisdiction_level"],
                "country_code": r["country_code"],
                "rate_type": new_rate if new_rate else r["rate_type"],
                "regulation_key": new_key,
                "applicable_entity_types": _entity_types(r["applicable_entity_types"]),
            }
            requirement_key, bare = _compute_key_parts(req)

            taken = conn.execute(
                text("""
                    SELECT 1 FROM jurisdiction_requirements
                    WHERE jurisdiction_id = :j AND requirement_key = :rk AND id <> :id
                """),
                {"j": r["jurisdiction_id"], "rk": requirement_key, "id": r["id"]},
            ).scalar()
            if taken:
                # Another row already owns the target identity. Collapsing them
                # is a merge decision, not a re-key — leave both and report.
                print(f"[rekey01] SKIP {title!r} in {r['jurisdiction_name']}: "
                      f"identity {requirement_key!r} already taken")
                skipped += 1
                continue

            conn.execute(
                text("""
                    UPDATE jurisdiction_requirements
                    SET category = :cat,
                        category_id = COALESCE(:cat_id, category_id),
                        regulation_key = :bare,
                        key_definition_id = COALESCE(:kd, key_definition_id),
                        requirement_key = :rk,
                        rate_type = :rt,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"cat": new_cat, "cat_id": new_cat_id, "bare": bare, "kd": kd_id,
                 "rk": requirement_key, "rt": req["rate_type"], "id": r["id"]},
            )
            rekeyed += 1

    print(f"[rekey01] re-keyed {rekeyed} row(s), skipped {skipped}")


def downgrade() -> None:
    # Not reversible by construction: the pre-migration state is the collision
    # (two obligations sharing one identity), and restoring it would re-create
    # the duplicate_active_obligation the tagging suite flags as critical. The
    # RKD rows are left in place — they are correct registry entries.
    pass
