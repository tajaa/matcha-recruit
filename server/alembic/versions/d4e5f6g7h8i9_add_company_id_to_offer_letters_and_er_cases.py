"""add company_id to offer_letters and er_cases

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-01-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- offer_letters: add company_id ---
    op.add_column(
        'offer_letters',
        sa.Column('company_id', UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_offer_letters_company_id',
        'offer_letters', 'companies',
        ['company_id'], ['id'],
    )
    op.create_index('idx_offer_letters_company_id', 'offer_letters', ['company_id'])

    # Backfill step 1: case-insensitive name match
    op.execute(sa.text("""
        UPDATE offer_letters ol SET company_id = c.id
        FROM companies c
        WHERE LOWER(TRIM(ol.company_name)) = LOWER(TRIM(c.name))
          AND ol.company_id IS NULL
    """))

    # Backfill step 2: if only one company exists, assign remaining orphans
    op.execute(sa.text("""
        UPDATE offer_letters SET company_id = (SELECT id FROM companies LIMIT 1)
        WHERE company_id IS NULL
          AND (SELECT COUNT(*) FROM companies) = 1
    """))

    # --- er_cases: add company_id ---
    op.add_column(
        'er_cases',
        sa.Column('company_id', UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_er_cases_company_id',
        'er_cases', 'companies',
        ['company_id'], ['id'],
    )
    op.create_index('idx_er_cases_company_id', 'er_cases', ['company_id'])

    # Backfill step 1: client users via clients table
    op.execute(sa.text("""
        UPDATE er_cases ec SET company_id = cl.company_id
        FROM clients cl
        WHERE ec.created_by = cl.user_id AND ec.company_id IS NULL
    """))

    # Backfill step 2: admin users via companies.owner_id
    op.execute(sa.text("""
        UPDATE er_cases ec SET company_id = co.id
        FROM companies co
        WHERE ec.created_by = co.owner_id AND ec.company_id IS NULL
    """))

    # Backfill step 3: if only one company exists, assign remaining orphans
    op.execute(sa.text("""
        UPDATE er_cases SET company_id = (SELECT id FROM companies LIMIT 1)
        WHERE company_id IS NULL
          AND (SELECT COUNT(*) FROM companies) = 1
    """))


def downgrade() -> None:
    op.drop_index('idx_er_cases_company_id', table_name='er_cases')
    op.drop_constraint('fk_er_cases_company_id', 'er_cases', type_='foreignkey')
    op.drop_column('er_cases', 'company_id')

    op.drop_index('idx_offer_letters_company_id', table_name='offer_letters')
    op.drop_constraint('fk_offer_letters_company_id', 'offer_letters', type_='foreignkey')
    op.drop_column('offer_letters', 'company_id')
