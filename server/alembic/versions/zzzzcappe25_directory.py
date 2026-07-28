"""cappe: public Discover directory — listing metadata, search vector, geo

Cappe tenants each publish an island. Every one of the ~25 public endpoints
under `/api/cappe/public/*` resolves a SINGLE known slug, so there is no path
from "I want a coffee shop near me" to a Cappe site and the platform generates
zero discovery value for the businesses on it.

This adds the columns a public directory needs:

* `listed` / `directory_blocked` — two SEPARATE switches on purpose. `listed`
  is the tenant's own opt-out (published implies listed by default, so the
  directory is populated on day one). `directory_blocked` is the platform-side
  takedown for spam/abuse listings, and it must NOT be something the spammer
  can flip back from their own settings page.
* `directory_category` / `directory_tags` / `directory_blurb` — there is no
  site-level category or description today; business identity lives in the site
  `name` and unstructured `meta_config` JSONB. Populated by Merlin inference on
  publish, then editable by the tenant (`directory_confirmed_at` records that
  they looked).
* `cappe_site_search` — cappe has no full-text search of any kind (zero tsvector
  / pg_trgm / GIN in the product). Maintained by `services/directory.py:
  refresh_site_search`, weighted A=name, B=category+tags, C=blurb,
  D=product names + location city.

  **Its own table rather than a column on `cappe_sites`, deliberately.**
  `routes/_shared.py:get_owned_site` is `SELECT * FROM cappe_sites` and feeds
  nearly every owner-side read, so a `tsvector` column there would be decoded by
  asyncpg on every one of those requests — making the entire Cappe owner surface
  depend on tsvector codec behaviour to serve a column none of them use. A side
  table keeps the hot row narrow and puts the GIN index on a table that holds
  nothing else.
* `cappe_locations.city` / `.region` / `.geocoded_at` — `lat`/`lng` are today
  OPTIONAL HAND-TYPED form fields used only to draw an OpenStreetMap embed, so
  they are null for nearly every site and radius search over them would match
  nothing. `core/services/geo.py` now backfills them from `address`.

Deliberately no `CREATE EXTENSION`: distance is a bounding-box prefilter plus
inline haversine, so this needs no PostGIS/earthdistance/pg_trgm on RDS (which
would require explicit approval per CLAUDE.md).

Additive with defaults throughout — existing rows are unchanged and no site
becomes visible until it has a category + blurb (the directory quality gate),
so a blank published template can never land on the first screen.

Revision ID: zzzzcappe25
Revises: zzzzcappe24
Create Date: 2026-07-28
"""
from alembic import op

revision = "zzzzcappe25"
down_revision = "zzzzcappe24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_sites
            ADD COLUMN IF NOT EXISTS listed BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN IF NOT EXISTS directory_blocked BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS directory_category VARCHAR(60),
            ADD COLUMN IF NOT EXISTS directory_tags TEXT[] NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS directory_blurb VARCHAR(200),
            ADD COLUMN IF NOT EXISTS directory_confirmed_at TIMESTAMPTZ
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_site_search (
            site_id UUID PRIMARY KEY REFERENCES cappe_sites(id) ON DELETE CASCADE,
            search_vector tsvector,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        ALTER TABLE cappe_locations
            ADD COLUMN IF NOT EXISTS city VARCHAR(120),
            ADD COLUMN IF NOT EXISTS region VARCHAR(60),
            ADD COLUMN IF NOT EXISTS geocoded_at TIMESTAMPTZ
        """
    )

    # Seed a name-only vector for rows that already exist so text search works
    # the moment the feature ships. The full weighted vector (products,
    # locations, tags) is written by refresh_site_search on the next publish or
    # listing save — one set-based UPDATE here, never a per-row loop.
    op.execute(
        """
        INSERT INTO cappe_site_search (site_id, search_vector)
        SELECT id, setweight(to_tsvector('english', coalesce(name, '')), 'A')
          FROM cappe_sites
        ON CONFLICT (site_id) DO NOTHING
        """
    )

    # A site that already wrote an SEO description gets a free blurb, so it only
    # needs a category before it can appear.
    op.execute(
        """
        UPDATE cappe_sites
           SET directory_blurb = left(btrim(meta_config #>> '{seo,description}'), 200)
         WHERE directory_blurb IS NULL
           AND btrim(coalesce(meta_config #>> '{seo,description}', '')) <> ''
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_site_search ON cappe_site_search USING GIN (search_vector)"
    )
    # The directory's base predicate, as a partial index — the listable set is a
    # small fraction of all sites.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cappe_sites_directory
            ON cappe_sites (published_at DESC, id)
         WHERE status = 'published' AND listed AND NOT directory_blocked
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cappe_locations_geo
            ON cappe_locations (lat, lng)
         WHERE active AND lat IS NOT NULL AND lng IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_locations_geo")
    op.execute("DROP INDEX IF EXISTS idx_cappe_sites_directory")
    op.execute("DROP TABLE IF EXISTS cappe_site_search")
    op.execute(
        """
        ALTER TABLE cappe_locations
            DROP COLUMN IF EXISTS city,
            DROP COLUMN IF EXISTS region,
            DROP COLUMN IF EXISTS geocoded_at
        """
    )
    op.execute(
        """
        ALTER TABLE cappe_sites
            DROP COLUMN IF EXISTS listed,
            DROP COLUMN IF EXISTS directory_blocked,
            DROP COLUMN IF EXISTS directory_category,
            DROP COLUMN IF EXISTS directory_tags,
            DROP COLUMN IF EXISTS directory_blurb,
            DROP COLUMN IF EXISTS directory_confirmed_at
        """
    )
