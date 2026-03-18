"""Deduplicate jurisdiction requirements by routing to source level.

Move federal- and state-level requirements that were incorrectly stored
on city jurisdictions to their proper jurisdiction rows (federal or state).
This eliminates duplicate rows across cities sharing the same parent
requirements.

Revision ID: 92583427c259
Revises: zp4q5r6s7t8u
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "92583427c259"
down_revision = "zp4q5r6s7t8u"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Move state-level requirements from city jurisdictions to state jurisdictions ──
    conn.execute(sa.text("""
        WITH to_move AS (
            SELECT jr.id AS jr_id,
                   jr.requirement_key, jr.category, jr.rate_type,
                   jr.jurisdiction_level, jr.jurisdiction_name,
                   jr.title, jr.description, jr.current_value, jr.numeric_value,
                   jr.source_url, jr.source_name, jr.effective_date, jr.expiration_date,
                   jr.last_verified_at, jr.requires_written_policy, jr.applicable_industries,
                   jr.source_tier, jr.status, jr.statute_citation, jr.canonical_key,
                   jr.previous_value, jr.last_changed_at, jr.trigger_conditions,
                   jr.applicable_entity_types, jr.category_id,
                   j_state.id AS target_jid
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j_city ON j_city.id = jr.jurisdiction_id AND j_city.level = 'city'
            JOIN jurisdictions j_state ON j_state.state = j_city.state AND j_state.level = 'state'
            WHERE jr.jurisdiction_level = 'state'
        ),
        inserted AS (
            INSERT INTO jurisdiction_requirements (
                jurisdiction_id, requirement_key, category, rate_type,
                jurisdiction_level, jurisdiction_name,
                title, description, current_value, numeric_value,
                source_url, source_name, effective_date, expiration_date,
                last_verified_at, requires_written_policy, applicable_industries,
                source_tier, status, statute_citation, canonical_key,
                previous_value, last_changed_at, trigger_conditions,
                applicable_entity_types, category_id
            )
            SELECT DISTINCT ON (target_jid, requirement_key)
                   target_jid, requirement_key, category, rate_type,
                   jurisdiction_level, jurisdiction_name,
                   title, description, current_value, numeric_value,
                   source_url, source_name, effective_date, expiration_date,
                   last_verified_at, requires_written_policy, applicable_industries,
                   source_tier, status, statute_citation, canonical_key,
                   previous_value, last_changed_at, trigger_conditions,
                   applicable_entity_types, category_id
            FROM to_move
            ORDER BY target_jid, requirement_key, last_verified_at DESC NULLS LAST
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                last_verified_at = GREATEST(
                    jurisdiction_requirements.last_verified_at,
                    EXCLUDED.last_verified_at
                ),
                current_value = EXCLUDED.current_value,
                description = EXCLUDED.description,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                updated_at = NOW()
            RETURNING id
        )
        DELETE FROM jurisdiction_requirements
        WHERE id IN (SELECT jr_id FROM to_move)
    """))

    # ── 2. Move federal-level requirements from city jurisdictions to the federal jurisdiction ──
    conn.execute(sa.text("""
        WITH to_move AS (
            SELECT jr.id AS jr_id,
                   jr.requirement_key, jr.category, jr.rate_type,
                   jr.jurisdiction_level, jr.jurisdiction_name,
                   jr.title, jr.description, jr.current_value, jr.numeric_value,
                   jr.source_url, jr.source_name, jr.effective_date, jr.expiration_date,
                   jr.last_verified_at, jr.requires_written_policy, jr.applicable_industries,
                   jr.source_tier, jr.status, jr.statute_citation, jr.canonical_key,
                   jr.previous_value, jr.last_changed_at, jr.trigger_conditions,
                   jr.applicable_entity_types, jr.category_id,
                   j_fed.id AS target_jid
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j_city ON j_city.id = jr.jurisdiction_id AND j_city.level = 'city'
            JOIN jurisdictions j_fed ON j_fed.level = 'federal' AND j_fed.state = 'US'
            WHERE jr.jurisdiction_level = 'federal'
        ),
        inserted AS (
            INSERT INTO jurisdiction_requirements (
                jurisdiction_id, requirement_key, category, rate_type,
                jurisdiction_level, jurisdiction_name,
                title, description, current_value, numeric_value,
                source_url, source_name, effective_date, expiration_date,
                last_verified_at, requires_written_policy, applicable_industries,
                source_tier, status, statute_citation, canonical_key,
                previous_value, last_changed_at, trigger_conditions,
                applicable_entity_types, category_id
            )
            SELECT DISTINCT ON (target_jid, requirement_key)
                   target_jid, requirement_key, category, rate_type,
                   jurisdiction_level, jurisdiction_name,
                   title, description, current_value, numeric_value,
                   source_url, source_name, effective_date, expiration_date,
                   last_verified_at, requires_written_policy, applicable_industries,
                   source_tier, status, statute_citation, canonical_key,
                   previous_value, last_changed_at, trigger_conditions,
                   applicable_entity_types, category_id
            FROM to_move
            ORDER BY target_jid, requirement_key, last_verified_at DESC NULLS LAST
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                last_verified_at = GREATEST(
                    jurisdiction_requirements.last_verified_at,
                    EXCLUDED.last_verified_at
                ),
                current_value = EXCLUDED.current_value,
                description = EXCLUDED.description,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                updated_at = NOW()
            RETURNING id
        )
        DELETE FROM jurisdiction_requirements
        WHERE id IN (SELECT jr_id FROM to_move)
    """))

    # ── 3. Move state-level requirements from county jurisdictions to state jurisdictions ──
    conn.execute(sa.text("""
        WITH to_move AS (
            SELECT jr.id AS jr_id,
                   jr.requirement_key, jr.category, jr.rate_type,
                   jr.jurisdiction_level, jr.jurisdiction_name,
                   jr.title, jr.description, jr.current_value, jr.numeric_value,
                   jr.source_url, jr.source_name, jr.effective_date, jr.expiration_date,
                   jr.last_verified_at, jr.requires_written_policy, jr.applicable_industries,
                   jr.source_tier, jr.status, jr.statute_citation, jr.canonical_key,
                   jr.previous_value, jr.last_changed_at, jr.trigger_conditions,
                   jr.applicable_entity_types, jr.category_id,
                   j_state.id AS target_jid
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j_county ON j_county.id = jr.jurisdiction_id
                AND j_county.city LIKE '_county_%'
            JOIN jurisdictions j_state ON j_state.state = j_county.state AND j_state.level = 'state'
            WHERE jr.jurisdiction_level = 'state'
        ),
        inserted AS (
            INSERT INTO jurisdiction_requirements (
                jurisdiction_id, requirement_key, category, rate_type,
                jurisdiction_level, jurisdiction_name,
                title, description, current_value, numeric_value,
                source_url, source_name, effective_date, expiration_date,
                last_verified_at, requires_written_policy, applicable_industries,
                source_tier, status, statute_citation, canonical_key,
                previous_value, last_changed_at, trigger_conditions,
                applicable_entity_types, category_id
            )
            SELECT DISTINCT ON (target_jid, requirement_key)
                   target_jid, requirement_key, category, rate_type,
                   jurisdiction_level, jurisdiction_name,
                   title, description, current_value, numeric_value,
                   source_url, source_name, effective_date, expiration_date,
                   last_verified_at, requires_written_policy, applicable_industries,
                   source_tier, status, statute_citation, canonical_key,
                   previous_value, last_changed_at, trigger_conditions,
                   applicable_entity_types, category_id
            FROM to_move
            ORDER BY target_jid, requirement_key, last_verified_at DESC NULLS LAST
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                last_verified_at = GREATEST(
                    jurisdiction_requirements.last_verified_at,
                    EXCLUDED.last_verified_at
                ),
                current_value = EXCLUDED.current_value,
                description = EXCLUDED.description,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                updated_at = NOW()
            RETURNING id
        )
        DELETE FROM jurisdiction_requirements
        WHERE id IN (SELECT jr_id FROM to_move)
    """))

    # ── 4. Move federal-level requirements from county jurisdictions ──
    conn.execute(sa.text("""
        WITH to_move AS (
            SELECT jr.id AS jr_id,
                   jr.requirement_key, jr.category, jr.rate_type,
                   jr.jurisdiction_level, jr.jurisdiction_name,
                   jr.title, jr.description, jr.current_value, jr.numeric_value,
                   jr.source_url, jr.source_name, jr.effective_date, jr.expiration_date,
                   jr.last_verified_at, jr.requires_written_policy, jr.applicable_industries,
                   jr.source_tier, jr.status, jr.statute_citation, jr.canonical_key,
                   jr.previous_value, jr.last_changed_at, jr.trigger_conditions,
                   jr.applicable_entity_types, jr.category_id,
                   j_fed.id AS target_jid
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j_county ON j_county.id = jr.jurisdiction_id
                AND j_county.city LIKE '_county_%'
            JOIN jurisdictions j_fed ON j_fed.level = 'federal' AND j_fed.state = 'US'
            WHERE jr.jurisdiction_level = 'federal'
        ),
        inserted AS (
            INSERT INTO jurisdiction_requirements (
                jurisdiction_id, requirement_key, category, rate_type,
                jurisdiction_level, jurisdiction_name,
                title, description, current_value, numeric_value,
                source_url, source_name, effective_date, expiration_date,
                last_verified_at, requires_written_policy, applicable_industries,
                source_tier, status, statute_citation, canonical_key,
                previous_value, last_changed_at, trigger_conditions,
                applicable_entity_types, category_id
            )
            SELECT DISTINCT ON (target_jid, requirement_key)
                   target_jid, requirement_key, category, rate_type,
                   jurisdiction_level, jurisdiction_name,
                   title, description, current_value, numeric_value,
                   source_url, source_name, effective_date, expiration_date,
                   last_verified_at, requires_written_policy, applicable_industries,
                   source_tier, status, statute_citation, canonical_key,
                   previous_value, last_changed_at, trigger_conditions,
                   applicable_entity_types, category_id
            FROM to_move
            ORDER BY target_jid, requirement_key, last_verified_at DESC NULLS LAST
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                last_verified_at = GREATEST(
                    jurisdiction_requirements.last_verified_at,
                    EXCLUDED.last_verified_at
                ),
                current_value = EXCLUDED.current_value,
                description = EXCLUDED.description,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                updated_at = NOW()
            RETURNING id
        )
        DELETE FROM jurisdiction_requirements
        WHERE id IN (SELECT jr_id FROM to_move)
    """))

    # ── 5. Recount requirement_count on all jurisdictions ──
    conn.execute(sa.text("""
        UPDATE jurisdictions j SET requirement_count = (
            SELECT COUNT(*) FROM jurisdiction_requirements jr WHERE jr.jurisdiction_id = j.id
        )
    """))


def downgrade() -> None:
    # Downgrade is not practical — duplicates cannot be recreated.
    # The data is still correct; city jurisdictions just have fewer rows.
    pass
