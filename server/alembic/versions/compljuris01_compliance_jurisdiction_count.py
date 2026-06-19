"""add compliance_jurisdiction_count to company_handbook_profiles

Backs the Matcha Compliance product's per-jurisdiction pricing component.
Stored at signup (/auth/register/business) and read at checkout
(/resources/checkout/compliance) + /auth/me. Nullable — every other tier
leaves it NULL.

Revision ID: compljuris01
Revises: zzzzcappe18
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "compljuris01"
down_revision: Union[str, Sequence[str], None] = "zzzzcappe18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_handbook_profiles",
        sa.Column("compliance_jurisdiction_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_handbook_profiles", "compliance_jurisdiction_count")
