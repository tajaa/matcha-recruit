"""Cappe — product pages: a web address, more than one picture, and the facts
search engines and shopping feeds read.

A product used to have no page of its own (its detail was an overlay with no
URL), one picture, and nothing for structured data beyond a name and a price.

`cappe_products`
  * `slug` — the product's address on its store, `/shop/<slug>`. Unique per
    store, lowercase words joined by hyphens. Stays put when the product is
    renamed: a link someone shared keeps working.
  * `brand`, `gtin` — the maker and the barcode (8, 12, 13 or 14 digits:
    EAN/UPC/GTIN), what Google and Meta match a product on.

`cappe_product_images` — a product's pictures in order. The first is the cover,
and `cappe_products.image_url` keeps mirroring it for everything that reads the
one column (the apps, receipts, the directory).

Backfill, set-based: every product gets a slug from its name, with `-2`, `-3`…
for repeats in a store and a short id suffix for whatever still collides
(a product actually called "Mug 2" beside two "Mug"s); every product with an
`image_url` gets it as its first picture. Then the unique index goes on.

Additive. The downgrade drops the table, the index, the checks and the columns.

Revision ID: zzzzcappe51
Revises: zzzzcappe50
Create Date: 2026-10-20
"""
from alembic import op

revision = "zzzzcappe51"
down_revision = "zzzzcappe50"
branch_labels = None
depends_on = None

_SLUG_SHAPE = "^[a-z0-9]+(-[a-z0-9]+)*$"
_GTIN_SHAPE = "^([0-9]{8}|[0-9]{12,14})$"


_UPGRADE = [
    "ALTER TABLE cappe_products "
    "ADD COLUMN IF NOT EXISTS slug VARCHAR(80), "
    "ADD COLUMN IF NOT EXISTS brand VARCHAR(120), "
    "ADD COLUMN IF NOT EXISTS gtin VARCHAR(14)",
    """
    CREATE TABLE IF NOT EXISTS cappe_product_images (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES cappe_products(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        alt VARCHAR(250),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_product_images_product ON cappe_product_images (product_id, sort_order)",
    # Slugs from names: words → hyphens, at most 72 characters before a suffix.
    """
    WITH base AS (
        SELECT id, site_id, created_at,
               COALESCE(NULLIF(trim(BOTH '-' FROM left(trim(BOTH '-' FROM
                   regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g')), 72)), ''), 'product') AS b
          FROM cappe_products WHERE slug IS NULL
    ), ranked AS (
        SELECT id, b, ROW_NUMBER() OVER (PARTITION BY site_id, b ORDER BY created_at, id) AS n FROM base
    )
    UPDATE cappe_products p
       SET slug = r.b || CASE WHEN r.n > 1 THEN '-' || r.n ELSE '' END
      FROM ranked r WHERE r.id = p.id
    """,
    # Whatever still collides (a literal "Mug 2" beside the second "Mug") gets
    # six characters of its id; the oldest keeps the plain slug.
    """
    WITH dup AS (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY site_id, slug ORDER BY created_at, id) AS n
          FROM cappe_products WHERE slug IS NOT NULL
    )
    UPDATE cappe_products p
       SET slug = left(p.slug, 72) || '-' || left(replace(p.id::text, '-', ''), 6)
      FROM dup d WHERE d.id = p.id AND d.n > 1
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_products_site_slug ON cappe_products (site_id, slug) "
    "WHERE slug IS NOT NULL",
    f"""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_products_slug') THEN
            ALTER TABLE cappe_products ADD CONSTRAINT ck_cappe_products_slug CHECK (slug ~ '{_SLUG_SHAPE}');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_products_gtin') THEN
            ALTER TABLE cappe_products ADD CONSTRAINT ck_cappe_products_gtin CHECK (gtin ~ '{_GTIN_SHAPE}');
        END IF;
    END $$
    """,
    # Every product's one picture becomes its first.
    """
    INSERT INTO cappe_product_images (site_id, product_id, url, sort_order)
    SELECT p.site_id, p.id, p.image_url, 0 FROM cappe_products p
     WHERE COALESCE(p.image_url, '') <> ''
       AND NOT EXISTS (SELECT 1 FROM cappe_product_images i WHERE i.product_id = p.id)
    """,
]

_DOWNGRADE = [
    "DROP TABLE IF EXISTS cappe_product_images",
    "DROP INDEX IF EXISTS uq_cappe_products_site_slug",
    "ALTER TABLE cappe_products DROP CONSTRAINT IF EXISTS ck_cappe_products_slug, "
    "DROP CONSTRAINT IF EXISTS ck_cappe_products_gtin",
    "ALTER TABLE cappe_products DROP COLUMN IF EXISTS gtin, DROP COLUMN IF EXISTS brand, "
    "DROP COLUMN IF EXISTS slug",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
