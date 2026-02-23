"""Add IR company/location context

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op

revision = 'e5f6g7h8i9j0'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ir_guidance_blurb to companies
    op.add_column('companies', sa.Column('ir_guidance_blurb', sa.Text(), nullable=True))

    # Add company_id and location_id to ir_incidents
    op.add_column('ir_incidents', sa.Column('company_id', postgresql.UUID(), nullable=True))
    op.add_column('ir_incidents', sa.Column('location_id', postgresql.UUID(), nullable=True))

    # Create foreign key constraints
    op.create_foreign_key(
        'fk_ir_incidents_company',
        'ir_incidents', 'companies',
        ['company_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_ir_incidents_location',
        'ir_incidents', 'business_locations',
        ['location_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create indexes for the new foreign keys
    op.create_index('idx_ir_incidents_company_id', 'ir_incidents', ['company_id'])
    op.create_index('idx_ir_incidents_location_id', 'ir_incidents', ['location_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_ir_incidents_location_id', table_name='ir_incidents')
    op.drop_index('idx_ir_incidents_company_id', table_name='ir_incidents')

    # Drop foreign keys
    op.drop_constraint('fk_ir_incidents_location', 'ir_incidents', type_='foreignkey')
    op.drop_constraint('fk_ir_incidents_company', 'ir_incidents', type_='foreignkey')

    # Drop columns from ir_incidents
    op.drop_column('ir_incidents', 'location_id')
    op.drop_column('ir_incidents', 'company_id')

    # Drop column from companies
    op.drop_column('companies', 'ir_guidance_blurb')
