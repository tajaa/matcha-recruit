"""Oceanlab label defaults — singleton settings row driving release/recording prefill.

The label is single-owner (100% master + publishing), so every release repeats
the same c-line/p-line/territories/genre and every recording the same 100%
split. This table holds those answers once; services/defaults.py applies them
at create time as REAL rows, not a read-time overlay, so they stay editable
and the packaging manifest sees exactly what the UI shows.

isrc_source / upc_source also drive validator severity: with distributor-issued
codes (DistroKid hands out both free) a missing ISRC/UPC is a warning, not the
hard error that would otherwise block packaging until a $95 usisrc.org prefix
and $30 GS1 GTINs are bought. Flip to 'own' once those exist — no code change.

Revision ID: oceanlab_app_02
Revises: tellus_app_16
Create Date: 2026-08-09
"""

from alembic import op


revision = "oceanlab_app_02"
down_revision = "tellus_app_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_label_settings (
            id INTEGER NOT NULL,
            default_artist_id UUID,
            default_contributor_id UUID,
            default_genre VARCHAR,
            default_territories VARCHAR NOT NULL DEFAULT 'WW',
            c_line_template VARCHAR NOT NULL DEFAULT '{year} {label}',
            p_line_template VARCHAR NOT NULL DEFAULT '{year} {label}',
            isrc_source VARCHAR NOT NULL DEFAULT 'distributor',
            upc_source VARCHAR NOT NULL DEFAULT 'distributor',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_label_settings PRIMARY KEY (id),
            CONSTRAINT ck_oceanlab_label_settings_singleton CHECK (id = 1),
            CONSTRAINT ck_oceanlab_label_settings_isrc_source
                CHECK (isrc_source IN ('own', 'distributor')),
            CONSTRAINT ck_oceanlab_label_settings_upc_source
                CHECK (upc_source IN ('own', 'distributor')),
            CONSTRAINT fk_oceanlab_label_settings_default_artist_id_oceanlab_artists
                FOREIGN KEY (default_artist_id) REFERENCES oceanlab_artists (id) ON DELETE SET NULL,
            CONSTRAINT fk_oceanlab_label_settings_default_contributor_id_oceanlab_contributors
                FOREIGN KEY (default_contributor_id) REFERENCES oceanlab_contributors (id) ON DELETE SET NULL
        )
        """
    )
    # Seed the singleton so reads never have to create it as a GET side effect
    # (same shape as oceanlab_isrc_config's id=1 row).
    op.execute(
        "INSERT INTO oceanlab_label_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oceanlab_label_settings CASCADE")
