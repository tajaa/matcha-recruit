"""An owner's own licensed fonts for Gummfit Studio, per magazine (site).

Each row is one face, stored as a TrueType file at `cappe/fonts/<sha>.ttf`
(the same key the catalog's faces use) and named in pages by its family key
(`u-<16 hex>`). A face is hidden, never deleted: pages that name it keep
rendering. Additive; the downgrade refuses while any face exists.

Revision ID: cappefont01
Revises: cappeidentity01
Create Date: 2026-10-24
"""
from alembic import op

revision = "cappefont01"
down_revision = "cappeidentity01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE cappe_studio_fonts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            family TEXT NOT NULL CHECK (family ~ '^u-[0-9a-f]{16}$'),
            name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 60),
            weight INTEGER NOT NULL CHECK (weight BETWEEN 100 AND 900),
            italic BOOLEAN NOT NULL,
            sha TEXT NOT NULL CHECK (sha ~ '^[0-9a-f]{64}$'),
            bytes INTEGER,
            upm INTEGER,
            "asc" INTEGER,
            "desc" INTEGER,
            cap INTEGER,
            x INTEGER,
            features TEXT[] NOT NULL DEFAULT '{}',
            filename TEXT,
            licence_attested_at TIMESTAMPTZ NOT NULL,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            hidden_at TIMESTAMPTZ,
            UNIQUE (site_id, sha)
        )
    """)
    op.execute("CREATE UNIQUE INDEX idx_cappe_studio_fonts_style ON cappe_studio_fonts (site_id, family, weight, italic) "
               "WHERE hidden_at IS NULL")
    op.execute("CREATE INDEX idx_cappe_studio_fonts_sha ON cappe_studio_fonts (sha)")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM cappe_studio_fonts) THEN
                RAISE EXCEPTION 'Uploaded Studio fonts exist; pages may name them, so they cannot be dropped';
            END IF;
        END $$
    """)
    op.execute("DROP TABLE cappe_studio_fonts")
