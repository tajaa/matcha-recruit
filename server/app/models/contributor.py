import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Contributor(Base, TimestampMixin):
    __tablename__ = "contributors"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    ipi_number: Mapped[str | None] = mapped_column(sa.String(11), nullable=True)
    pro_affiliation: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
