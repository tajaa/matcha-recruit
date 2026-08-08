"""Oceanlab standalone app — all oceanlab_* tables.

Oceanlab is its own app (music catalog / label ingestion pipeline) running on
the matcha stack, same pattern as Cappe/Tell-Us: own tables (oceanlab_*
prefix), own static bearer-token auth, nothing here touches matcha's tenant
model. DDL generated from app/oceanlab/models/*.py (Base.metadata) after the
oceanlab_* table rename, to avoid hand-transcription drift from the ORM.

Rooted on a current head (tellus_app_15); apply with `alembic upgrade heads`.

Revision ID: oceanlab_app_01
Revises: tellus_app_15
Create Date: 2026-08-08
"""
from alembic import op


revision = "oceanlab_app_01"
down_revision = "tellus_app_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_artists (
            id UUID NOT NULL,
            name VARCHAR NOT NULL,
            sort_name VARCHAR,
            country VARCHAR(2),
            spotify_id VARCHAR,
            apple_music_id VARCHAR,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_artists PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_artists_name UNIQUE (name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_contributors (
            id UUID NOT NULL,
            name VARCHAR NOT NULL,
            legal_name VARCHAR,
            ipi_number VARCHAR(11),
            pro_affiliation VARCHAR,
            email VARCHAR,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_contributors PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_files (
            id UUID NOT NULL,
            kind VARCHAR(19) NOT NULL,
            storage_key VARCHAR NOT NULL,
            original_filename VARCHAR NOT NULL,
            mime_type VARCHAR NOT NULL,
            size_bytes BIGINT NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            width INTEGER,
            height INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_files PRIMARY KEY (id),
            CONSTRAINT ck_oceanlab_files_kind CHECK (kind IN ('audio_master', 'artwork', 'royalty_statement', 'package', 'registration_export', 'rendered_video')),
            CONSTRAINT uq_oceanlab_files_storage_key UNIQUE (storage_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_isrc_config (
            id INTEGER NOT NULL,
            registrant_prefix VARCHAR(5) NOT NULL,
            year_digits VARCHAR(2) NOT NULL,
            next_designation INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_isrc_config PRIMARY KEY (id),
            CONSTRAINT ck_oceanlab_isrc_config_singleton CHECK (id = 1)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_jobs (
            id UUID NOT NULL,
            kind VARCHAR NOT NULL,
            status VARCHAR(7) NOT NULL,
            payload JSONB NOT NULL,
            result JSONB,
            error TEXT,
            started_at TIMESTAMP WITH TIME ZONE,
            finished_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_jobs PRIMARY KEY (id),
            CONSTRAINT ck_oceanlab_jobs_status CHECK (status IN ('queued', 'running', 'done', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_works (
            id UUID NOT NULL,
            title VARCHAR NOT NULL,
            iswc VARCHAR(11),
            language VARCHAR(2),
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_works PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_works_iswc UNIQUE (iswc)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_recordings (
            id UUID NOT NULL,
            title VARCHAR NOT NULL,
            version VARCHAR,
            isrc VARCHAR(12),
            explicit BOOLEAN,
            language VARCHAR(2),
            recording_year INTEGER,
            audio_file_id UUID,
            duration_seconds NUMERIC(9, 3),
            sample_rate INTEGER,
            bit_depth INTEGER,
            channels INTEGER,
            audio_format VARCHAR,
            primary_artist_id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_recordings PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_recordings_isrc UNIQUE (isrc),
            CONSTRAINT fk_oceanlab_recordings_audio_file_id_oceanlab_files FOREIGN KEY(audio_file_id) REFERENCES oceanlab_files (id) ON DELETE RESTRICT,
            CONSTRAINT fk_oceanlab_recordings_primary_artist_id_oceanlab_artists FOREIGN KEY(primary_artist_id) REFERENCES oceanlab_artists (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_releases (
            id UUID NOT NULL,
            title VARCHAR NOT NULL,
            release_type VARCHAR(6) NOT NULL,
            status VARCHAR(9) NOT NULL,
            upc VARCHAR(13),
            catalog_number VARCHAR,
            release_date DATE,
            original_release_date DATE,
            label_name VARCHAR NOT NULL,
            c_line VARCHAR,
            p_line VARCHAR,
            genre VARCHAR,
            subgenre VARCHAR,
            territories VARCHAR NOT NULL,
            artwork_file_id UUID,
            primary_artist_id UUID NOT NULL,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_releases PRIMARY KEY (id),
            CONSTRAINT ck_oceanlab_releases_release_type CHECK (release_type IN ('album', 'ep', 'single')),
            CONSTRAINT ck_oceanlab_releases_status CHECK (status IN ('draft', 'ready', 'packaged', 'delivered', 'released')),
            CONSTRAINT uq_oceanlab_releases_upc UNIQUE (upc),
            CONSTRAINT uq_oceanlab_releases_catalog_number UNIQUE (catalog_number),
            CONSTRAINT fk_oceanlab_releases_artwork_file_id_oceanlab_files FOREIGN KEY(artwork_file_id) REFERENCES oceanlab_files (id) ON DELETE RESTRICT,
            CONSTRAINT fk_oceanlab_releases_primary_artist_id_oceanlab_artists FOREIGN KEY(primary_artist_id) REFERENCES oceanlab_artists (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_royalty_statements (
            id UUID NOT NULL,
            source VARCHAR NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            currency VARCHAR(3) NOT NULL,
            file_id UUID NOT NULL,
            status VARCHAR(8) NOT NULL,
            total_amount NUMERIC(12, 4),
            line_count INTEGER NOT NULL,
            matched_count INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_royalty_statements PRIMARY KEY (id),
            CONSTRAINT fk_oceanlab_royalty_statements_file_id_oceanlab_files FOREIGN KEY(file_id) REFERENCES oceanlab_files (id),
            CONSTRAINT ck_oceanlab_royalty_statements_statement_status CHECK (status IN ('uploaded', 'parsing', 'parsed', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_work_writers (
            id UUID NOT NULL,
            work_id UUID NOT NULL,
            contributor_id UUID NOT NULL,
            role VARCHAR(17) NOT NULL,
            share_pct NUMERIC(6, 3) NOT NULL,
            publisher_name VARCHAR,
            publisher_share_pct NUMERIC(6, 3),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_work_writers PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_work_writers_work_contributor_role UNIQUE (work_id, contributor_id, role),
            CONSTRAINT fk_oceanlab_work_writers_work_id_oceanlab_works FOREIGN KEY(work_id) REFERENCES oceanlab_works (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_work_writers_contributor_id_oceanlab_contributors FOREIGN KEY(contributor_id) REFERENCES oceanlab_contributors (id),
            CONSTRAINT ck_oceanlab_work_writers_role CHECK (role IN ('composer', 'lyricist', 'composer_lyricist', 'arranger', 'translator'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_credits (
            id UUID NOT NULL,
            recording_id UUID NOT NULL,
            contributor_id UUID NOT NULL,
            role VARCHAR(18) NOT NULL,
            credited_as VARCHAR,
            position INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_credits PRIMARY KEY (id),
            CONSTRAINT fk_oceanlab_credits_recording_id_oceanlab_recordings FOREIGN KEY(recording_id) REFERENCES oceanlab_recordings (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_credits_contributor_id_oceanlab_contributors FOREIGN KEY(contributor_id) REFERENCES oceanlab_contributors (id),
            CONSTRAINT ck_oceanlab_credits_role CHECK (role IN ('producer', 'performer', 'mixer', 'mastering_engineer', 'recording_engineer', 'featured', 'remixer', 'other'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_deliveries (
            id UUID NOT NULL,
            release_id UUID NOT NULL,
            target VARCHAR(14) NOT NULL,
            status VARCHAR(11) NOT NULL,
            package_file_id UUID,
            external_ref VARCHAR,
            error TEXT,
            log TEXT,
            started_at TIMESTAMP WITH TIME ZONE,
            finished_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_deliveries PRIMARY KEY (id),
            CONSTRAINT fk_oceanlab_deliveries_release_id_oceanlab_releases FOREIGN KEY(release_id) REFERENCES oceanlab_releases (id) ON DELETE CASCADE,
            CONSTRAINT ck_oceanlab_deliveries_target CHECK (target IN ('export_package', 'youtube', 'soundcloud')),
            CONSTRAINT ck_oceanlab_deliveries_status CHECK (status IN ('pending', 'in_progress', 'complete', 'failed', 'manual')),
            CONSTRAINT fk_oceanlab_deliveries_package_file_id_oceanlab_files FOREIGN KEY(package_file_id) REFERENCES oceanlab_files (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_master_splits (
            id UUID NOT NULL,
            recording_id UUID NOT NULL,
            contributor_id UUID NOT NULL,
            role VARCHAR(18),
            share_pct NUMERIC(6, 3) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_master_splits PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_master_splits_recording_contributor UNIQUE (recording_id, contributor_id),
            CONSTRAINT fk_oceanlab_master_splits_recording_id_oceanlab_recordings FOREIGN KEY(recording_id) REFERENCES oceanlab_recordings (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_master_splits_contributor_id_oceanlab_contributors FOREIGN KEY(contributor_id) REFERENCES oceanlab_contributors (id),
            CONSTRAINT ck_oceanlab_master_splits_role CHECK (role IN ('producer', 'performer', 'mixer', 'mastering_engineer', 'recording_engineer', 'featured', 'remixer', 'other'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_recording_works (
            recording_id UUID NOT NULL,
            work_id UUID NOT NULL,
            CONSTRAINT pk_oceanlab_recording_works PRIMARY KEY (recording_id, work_id),
            CONSTRAINT fk_oceanlab_recording_works_recording_id_oceanlab_recordings FOREIGN KEY(recording_id) REFERENCES oceanlab_recordings (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_recording_works_work_id_oceanlab_works FOREIGN KEY(work_id) REFERENCES oceanlab_works (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_registration_tasks (
            id UUID NOT NULL,
            release_id UUID NOT NULL,
            target VARCHAR(13) NOT NULL,
            status VARCHAR(14) NOT NULL,
            external_ref VARCHAR,
            export_file_id UUID,
            submitted_at TIMESTAMP WITH TIME ZONE,
            confirmed_at TIMESTAMP WITH TIME ZONE,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_registration_tasks PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_registration_tasks_release_target UNIQUE (release_id, target),
            CONSTRAINT fk_oceanlab_registration_tasks_release_id_oceanlab_releases FOREIGN KEY(release_id) REFERENCES oceanlab_releases (id) ON DELETE CASCADE,
            CONSTRAINT ck_oceanlab_registration_tasks_target CHECK (target IN ('pro', 'mlc', 'soundexchange', 'distributor')),
            CONSTRAINT ck_oceanlab_registration_tasks_status CHECK (status IN ('not_started', 'in_progress', 'submitted', 'confirmed', 'not_applicable')),
            CONSTRAINT fk_oceanlab_registration_tasks_export_file_id_oceanlab_files FOREIGN KEY(export_file_id) REFERENCES oceanlab_files (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_release_artists (
            id UUID NOT NULL,
            release_id UUID NOT NULL,
            artist_id UUID NOT NULL,
            role VARCHAR(8) NOT NULL,
            position INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_release_artists PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_release_artists_release_artist_role UNIQUE (release_id, artist_id, role),
            CONSTRAINT fk_oceanlab_release_artists_release_id_oceanlab_releases FOREIGN KEY(release_id) REFERENCES oceanlab_releases (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_release_artists_artist_id_oceanlab_artists FOREIGN KEY(artist_id) REFERENCES oceanlab_artists (id),
            CONSTRAINT ck_oceanlab_release_artists_role CHECK (role IN ('primary', 'featured'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_royalty_lines (
            id UUID NOT NULL,
            statement_id UUID NOT NULL,
            raw JSONB NOT NULL,
            isrc VARCHAR,
            iswc VARCHAR,
            upc VARCHAR,
            title_raw VARCHAR,
            artist_raw VARCHAR,
            territory VARCHAR,
            units BIGINT,
            amount NUMERIC(12, 4) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            recording_id UUID,
            work_id UUID,
            match_method VARCHAR(9) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_royalty_lines PRIMARY KEY (id),
            CONSTRAINT fk_oceanlab_royalty_lines_statement_id_oceanlab_royalty_0d9d FOREIGN KEY(statement_id) REFERENCES oceanlab_royalty_statements (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_royalty_lines_recording_id_oceanlab_recordings FOREIGN KEY(recording_id) REFERENCES oceanlab_recordings (id) ON DELETE SET NULL,
            CONSTRAINT fk_oceanlab_royalty_lines_work_id_oceanlab_works FOREIGN KEY(work_id) REFERENCES oceanlab_works (id) ON DELETE SET NULL,
            CONSTRAINT ck_oceanlab_royalty_lines_match_method CHECK (match_method IN ('isrc', 'iswc', 'manual', 'unmatched'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_oceanlab_royalty_lines_isrc ON oceanlab_royalty_lines (isrc)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_oceanlab_royalty_lines_statement_id ON oceanlab_royalty_lines (statement_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_oceanlab_royalty_lines_recording_id ON oceanlab_royalty_lines (recording_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_tracks (
            id UUID NOT NULL,
            release_id UUID NOT NULL,
            recording_id UUID NOT NULL,
            disc_number INTEGER NOT NULL,
            position INTEGER NOT NULL,
            title_override VARCHAR,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_tracks PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_tracks_release_disc_position UNIQUE (release_id, disc_number, position) DEFERRABLE INITIALLY DEFERRED,
            CONSTRAINT fk_oceanlab_tracks_release_id_oceanlab_releases FOREIGN KEY(release_id) REFERENCES oceanlab_releases (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_tracks_recording_id_oceanlab_recordings FOREIGN KEY(recording_id) REFERENCES oceanlab_recordings (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_upc_codes (
            id UUID NOT NULL,
            code VARCHAR(13) NOT NULL,
            status VARCHAR(9) NOT NULL,
            release_id UUID,
            assigned_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_upc_codes PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_upc_codes_code UNIQUE (code),
            CONSTRAINT ck_oceanlab_upc_codes_status CHECK (status IN ('available', 'assigned')),
            CONSTRAINT fk_oceanlab_upc_codes_release_id_oceanlab_releases FOREIGN KEY(release_id) REFERENCES oceanlab_releases (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oceanlab_delivery_items (
            id UUID NOT NULL,
            delivery_id UUID NOT NULL,
            track_id UUID NOT NULL,
            status VARCHAR(11) NOT NULL,
            external_ref VARCHAR,
            error TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_oceanlab_delivery_items PRIMARY KEY (id),
            CONSTRAINT uq_oceanlab_delivery_items_delivery_track UNIQUE (delivery_id, track_id),
            CONSTRAINT fk_oceanlab_delivery_items_delivery_id_oceanlab_deliveries FOREIGN KEY(delivery_id) REFERENCES oceanlab_deliveries (id) ON DELETE CASCADE,
            CONSTRAINT fk_oceanlab_delivery_items_track_id_oceanlab_tracks FOREIGN KEY(track_id) REFERENCES oceanlab_tracks (id) ON DELETE CASCADE,
            CONSTRAINT ck_oceanlab_delivery_items_status CHECK (status IN ('pending', 'in_progress', 'complete', 'failed', 'manual'))
        )
        """
    )

    # Guarantee the id=1 row exists so app code (GET /settings/isrc, the
    # assign_isrc FOR UPDATE lock target) never has to create-on-read.
    op.execute(
        "INSERT INTO oceanlab_isrc_config (id, registrant_prefix, year_digits, next_designation) "
        "VALUES (1, '', '', 1) ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    for table in (
        "oceanlab_delivery_items",
        "oceanlab_upc_codes",
        "oceanlab_tracks",
        "oceanlab_royalty_lines",
        "oceanlab_release_artists",
        "oceanlab_registration_tasks",
        "oceanlab_recording_works",
        "oceanlab_master_splits",
        "oceanlab_deliveries",
        "oceanlab_credits",
        "oceanlab_work_writers",
        "oceanlab_royalty_statements",
        "oceanlab_releases",
        "oceanlab_recordings",
        "oceanlab_works",
        "oceanlab_jobs",
        "oceanlab_isrc_config",
        "oceanlab_files",
        "oceanlab_contributors",
        "oceanlab_artists",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
