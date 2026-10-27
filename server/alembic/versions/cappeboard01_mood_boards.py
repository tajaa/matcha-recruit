"""Mood boards: a site's pinboards of photos, screenshots, documents, notes and
links (`services/boards/`). Additive; no existing rows change.

A pin's own files are private (the private bucket, served through signed
links), never the public CDN: inspiration is usually someone else's work. A
photo pinned from the library points at its `cappe_assets` row instead and
goes when the library picture does.

Apply before deploying the boards API. Old application versions ignore these
tables. Downgrade refuses while any board exists, to prevent data loss.
"""
from alembic import op

revision = "cappeboard01"
down_revision = "cappereader01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE cappe_boards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_cappe_boards_site ON cappe_boards (site_id, updated_at DESC)")
    op.execute("""
        CREATE TABLE cappe_board_pins (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            board_id UUID NOT NULL REFERENCES cappe_boards(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('image', 'file', 'note', 'link')),
            x REAL NOT NULL,
            y REAL NOT NULL,
            w REAL NOT NULL,
            h REAL NOT NULL,
            rotation REAL NOT NULL DEFAULT 0,
            z INTEGER NOT NULL DEFAULT 0,
            asset_id UUID REFERENCES cappe_assets(id) ON DELETE CASCADE,
            file_path TEXT,
            thumb_path TEXT,
            filename TEXT,
            mime TEXT,
            size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
            width INTEGER,
            height INTEGER,
            note TEXT CHECK (note IS NULL OR char_length(note) <= 2000),
            color TEXT,
            url TEXT CHECK (url IS NULL OR char_length(url) <= 2048),
            title TEXT CHECK (title IS NULL OR char_length(title) <= 300),
            description TEXT CHECK (description IS NULL OR char_length(description) <= 500),
            site_name TEXT CHECK (site_name IS NULL OR char_length(site_name) <= 120),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT cappe_board_pins_image CHECK (kind <> 'image' OR ((asset_id IS NULL) <> (file_path IS NULL))),
            CONSTRAINT cappe_board_pins_file CHECK (kind <> 'file' OR (file_path IS NOT NULL AND asset_id IS NULL)),
            CONSTRAINT cappe_board_pins_note CHECK (
                kind <> 'note' OR (note IS NOT NULL AND asset_id IS NULL AND file_path IS NULL)),
            CONSTRAINT cappe_board_pins_link CHECK (
                kind <> 'link' OR (url IS NOT NULL AND asset_id IS NULL AND file_path IS NULL))
        )
    """)
    op.execute("CREATE INDEX idx_cappe_board_pins_board ON cappe_board_pins (board_id, z)")
    op.execute("CREATE INDEX idx_cappe_board_pins_site ON cappe_board_pins (site_id)")
    op.execute("CREATE INDEX idx_cappe_board_pins_asset ON cappe_board_pins (asset_id) WHERE asset_id IS NOT NULL")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM cappe_boards) THEN
                RAISE EXCEPTION 'Mood boards exist; remove them before downgrading';
            END IF;
        END $$
    """)
    op.execute("DROP TABLE cappe_board_pins")
    op.execute("DROP TABLE cappe_boards")
