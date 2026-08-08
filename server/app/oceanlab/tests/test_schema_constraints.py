"""Regression coverage for schema-level fixes: IsrcConfig singleton CHECK
constraint and RoyaltyStatement.status enum enforcement.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.codes import IsrcConfig


def test_isrc_config_singleton_constraint_rejects_second_row(db):
    db.add(IsrcConfig(id=1, registrant_prefix="QZABC", year_digits="26", next_designation=1))
    db.flush()

    db.add(IsrcConfig(id=2, registrant_prefix="QZABC", year_digits="26", next_designation=1))
    with pytest.raises(IntegrityError):
        db.flush()
