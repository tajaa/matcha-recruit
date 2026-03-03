"""add_industry_compliance_profiles

Revision ID: e6714d5d523f
Revises: 0a9bffab08a8
Create Date: 2026-03-03 12:07:43.569668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY


# revision identifiers, used by Alembic.
revision: str = 'e6714d5d523f'
down_revision: Union[str, Sequence[str], None] = '0a9bffab08a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'industry_compliance_profiles',
        sa.Column('id', UUID(), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('focused_categories', ARRAY(sa.Text()), nullable=False),
        sa.Column('rate_types', ARRAY(sa.Text()), nullable=True),
        sa.Column('category_order', ARRAY(sa.Text()), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    op.execute("""
        INSERT INTO industry_compliance_profiles (name, description, focused_categories, rate_types, category_order) VALUES
        (
            'Restaurant / Hospitality',
            'Restaurants, hotels, and hospitality businesses',
            ARRAY['meal_breaks','scheduling_reporting','minimum_wage','minor_work_permit','overtime'],
            ARRAY['tipped','hotel'],
            ARRAY['meal_breaks','scheduling_reporting','minimum_wage','minor_work_permit','overtime','sick_leave','pay_frequency','final_pay']
        ),
        (
            'Healthcare',
            'Hospitals, clinics, and healthcare providers',
            ARRAY['overtime','scheduling_reporting','meal_breaks','sick_leave'],
            ARRAY['healthcare'],
            ARRAY['overtime','scheduling_reporting','meal_breaks','sick_leave','minimum_wage','pay_frequency','final_pay','minor_work_permit']
        ),
        (
            'Retail',
            'Retail stores and consumer-facing businesses',
            ARRAY['scheduling_reporting','minor_work_permit','meal_breaks','minimum_wage'],
            ARRAY['general'],
            ARRAY['scheduling_reporting','minor_work_permit','meal_breaks','minimum_wage','overtime','sick_leave','pay_frequency','final_pay']
        ),
        (
            'Tech / Professional Services',
            'Technology companies and professional services firms',
            ARRAY['overtime','sick_leave','pay_frequency','final_pay'],
            ARRAY['exempt_salary'],
            ARRAY['overtime','sick_leave','pay_frequency','final_pay','minimum_wage','meal_breaks','scheduling_reporting','minor_work_permit']
        ),
        (
            'Fast Food',
            'Fast food chains and quick-service restaurants',
            ARRAY['scheduling_reporting','meal_breaks','minimum_wage','minor_work_permit'],
            ARRAY['fast_food'],
            ARRAY['scheduling_reporting','meal_breaks','minimum_wage','minor_work_permit','overtime','sick_leave','pay_frequency','final_pay']
        ),
        (
            'Construction / Manufacturing',
            'Construction sites, factories, and manufacturing',
            ARRAY['overtime','meal_breaks','minor_work_permit','pay_frequency'],
            ARRAY['general'],
            ARRAY['overtime','meal_breaks','minor_work_permit','pay_frequency','minimum_wage','scheduling_reporting','sick_leave','final_pay']
        )
    """)


def downgrade() -> None:
    op.drop_table('industry_compliance_profiles')
