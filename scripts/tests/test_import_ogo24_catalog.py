from pathlib import Path

from scripts.cappe.import_ogo24_catalog import load_catalog, read_products_copy


COLUMNS = (
    "id, seller_id, title, description, price, sizes, colors, category, status, "
    "created_at, updated_at, about, stripe_product_id, images, primary_image_index, "
    "weight, purchase_price, margin_percentage, ingredients, materials, tax_code, "
    "sold_out, company, domain, recurring_enabled, subcategory, labels, video_url, "
    "video_s3_key, sale_price"
)


def _dump(tmp_path: Path) -> Path:
    fields = [
        "42", r"\N", "Soap", r"Line one\nline two", "12.34", '["Small","Large"]',
        '["Blue","blue","Red"]', "care", "active", "2025-01-01", "2025-01-02",
        "More about it", r"\N", '[{"url":"https://example.test/a.webp","s3_key":"a.webp"}]',
        "0", r"\N", "1.00", "0", "{}", "{}", r"\N", "t", r"\N", "ahnimal",
        "t", "soap", "{}", r"\N", r"\N", "10.005",
    ]
    other = fields.copy()
    other[0] = "43"
    other[23] = "another-site"
    path = tmp_path / "catalog.sql"
    path.write_text(
        "-- prelude\n"
        f"COPY public.products ({COLUMNS}) FROM stdin;\n"
        + "\t".join(fields)
        + "\n"
        + "\t".join(other)
        + "\n\\.\n",
        encoding="utf-8",
    )
    return path


def test_copy_parser_decodes_escapes_and_nulls(tmp_path: Path):
    rows = list(read_products_copy(_dump(tmp_path)))
    assert rows[0]["description"] == "Line one\nline two"
    assert rows[0]["seller_id"] is None


def test_catalog_mapping_filters_domain_and_maps_fields(tmp_path: Path):
    products = load_catalog(_dump(tmp_path), "AHNIMAL")
    assert len(products) == 1
    product = products[0]
    assert product.source_id == 42
    assert product.image_key == "a.webp"
    assert product.payload == {
        "name": "Soap",
        "description": "Line one\nline two\n\nMore about it",
        "price_cents": 1001,
        "currency": "USD",
        "image_url": None,
        "sku": "ogo24:42",
        "inventory": 0,
        "status": "active",
        "sort_order": 42,
        "fulfillment": "physical",
        "category": "care / soap",
        "option_groups": [
            {
                "name": "Size",
                "select_type": "single",
                "required": True,
                "sort_order": 0,
                "options": [
                    {"name": "Small", "price_delta_cents": 0, "sort_order": 0},
                    {"name": "Large", "price_delta_cents": 0, "sort_order": 1},
                ],
            },
            {
                "name": "Color",
                "select_type": "single",
                "required": True,
                "sort_order": 1,
                "options": [
                    {"name": "Blue", "price_delta_cents": 0, "sort_order": 0},
                    {"name": "Red", "price_delta_cents": 0, "sort_order": 2},
                ],
            },
        ],
        "subscription_intervals": ["month"],
        "subscription_discount_bps": 0,
    }
