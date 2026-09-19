#!/usr/bin/env python3
"""Import one tenant's ogo24 product catalog through the Cappe owner API.

The command is deliberately dry-run by default.  ``--apply`` is required
before it performs any network request.  Products are tagged with a stable
``ogo24:<id>`` SKU so an interrupted import can be resumed without creating
duplicates.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable


COPY_HEADER = re.compile(
    r"^COPY\s+(?:public\.)?products\s+\((?P<columns>[^)]+)\)\s+FROM\s+stdin;$"
)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_DUMP = Path(__file__).resolve().parents[3] / "ogo24" / "ahnimal_backup.sql"


class ImportFailure(RuntimeError):
    """A product could not be safely mapped or sent to Cappe."""


@dataclass(frozen=True)
class CatalogProduct:
    source_id: int
    source_status: str
    source_image: str | None
    image_key: str | None
    payload: dict[str, Any]


@dataclass
class ImportResult:
    source_id: int
    name: str
    action: str
    image: str | None = None
    product_id: str | None = None
    error: str | None = None


def _decode_copy_value(value: str) -> str | None:
    """Decode PostgreSQL COPY text escaping without interpreting JSON itself."""
    if value == r"\N":
        return None
    output: list[str] = []
    index = 0
    escapes = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    while index < len(value):
        char = value[index]
        if char != "\\" or index + 1 >= len(value):
            output.append(char)
            index += 1
            continue
        index += 1
        escaped = value[index]
        if escaped in escapes:
            output.append(escapes[escaped])
            index += 1
        elif escaped == "x" and index + 2 < len(value):
            candidate = value[index + 1 : index + 3]
            try:
                output.append(chr(int(candidate, 16)))
                index += 3
            except ValueError:
                output.append(escaped)
                index += 1
        elif escaped in "01234567":
            end = index + 1
            while end < min(index + 3, len(value)) and value[end] in "01234567":
                end += 1
            output.append(chr(int(value[index:end], 8)))
            index = end
        else:
            output.append(escaped)
            index += 1
    return "".join(output)


def read_products_copy(path: Path) -> Iterable[dict[str, str | None]]:
    """Yield dictionaries from the ``COPY public.products`` section."""
    columns: list[str] | None = None
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if columns is None:
                match = COPY_HEADER.match(line.rstrip("\r"))
                if match:
                    columns = [column.strip() for column in match.group("columns").split(",")]
                continue
            if line.rstrip("\r") == r"\.":
                return
            values = line.rstrip("\r").split("\t")
            if len(values) != len(columns):
                raise ImportFailure(
                    f"malformed products COPY row: expected {len(columns)} fields, got {len(values)}"
                )
            yield dict(zip(columns, (_decode_copy_value(value) for value in values), strict=True))
    if columns is None:
        raise ImportFailure("COPY public.products section was not found")
    raise ImportFailure("COPY public.products section was not terminated")


def _json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImportFailure(f"invalid JSON value: {exc}") from exc
    return value if isinstance(value, list) else []


def _bool(raw: str | None) -> bool:
    return (raw or "").lower() in {"t", "true", "1", "yes"}


def _price_cents(row: dict[str, str | None]) -> int:
    raw = row.get("sale_price") if row.get("sale_price") not in {None, ""} else row.get("price")
    try:
        amount = Decimal(raw or "0")
    except InvalidOperation as exc:
        raise ImportFailure(f"invalid price {raw!r}") from exc
    if amount < 0:
        raise ImportFailure(f"negative price {raw!r}")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _option_group(name: str, values: list[Any], sort_order: int) -> dict[str, Any] | None:
    options: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, value in enumerate(values):
        label = str(value).strip()
        folded = label.casefold()
        if not label or folded in seen:
            continue
        seen.add(folded)
        options.append({"name": label[:120], "price_delta_cents": 0, "sort_order": position})
    if not options:
        return None
    return {
        "name": name,
        "select_type": "single",
        "required": True,
        "sort_order": sort_order,
        "options": options,
    }


def map_product(row: dict[str, str | None]) -> CatalogProduct:
    """Apply the documented ogo24-to-Cappe field mapping."""
    try:
        source_id = int(row.get("id") or "")
    except ValueError as exc:
        raise ImportFailure(f"invalid source product id {row.get('id')!r}") from exc
    # Two archived rows in the current dump have an empty title.  Keep them as
    # obvious drafts for manual cleanup instead of making one bad legacy row
    # prevent the other products from being imported.
    title = (row.get("title") or "").strip() or f"Untitled ogo24 product {source_id}"

    description_parts = [part.strip() for part in (row.get("description"), row.get("about")) if part and part.strip()]
    images = _json_list(row.get("images"))
    try:
        primary_index = int(row.get("primary_image_index") or 0)
    except ValueError:
        primary_index = 0
    image: dict[str, Any] = {}
    if images:
        selected = images[primary_index] if 0 <= primary_index < len(images) else images[0]
        image = selected if isinstance(selected, dict) else {}

    groups = [
        group
        for group in (
            _option_group("Size", _json_list(row.get("sizes")), 0),
            _option_group("Color", _json_list(row.get("colors")), 1),
        )
        if group is not None
    ]
    category_parts = []
    for raw in (row.get("category"), row.get("subcategory")):
        value = (raw or "").strip()
        if value and value.casefold() not in {part.casefold() for part in category_parts}:
            category_parts.append(value)
    recurring = _bool(row.get("recurring_enabled"))
    source_status = (row.get("status") or "").strip().lower()

    payload: dict[str, Any] = {
        "name": title[:255],
        "description": "\n\n".join(description_parts) or None,
        "price_cents": _price_cents(row),
        "currency": "USD",
        "image_url": None,
        "sku": f"ogo24:{source_id}",
        "inventory": 0 if _bool(row.get("sold_out")) else None,
        "status": "active" if source_status == "active" else "draft",
        "sort_order": source_id,
        "fulfillment": "physical",
        "category": " / ".join(category_parts)[:120] or None,
        "option_groups": groups,
        "subscription_intervals": ["month"] if recurring else [],
        "subscription_discount_bps": 0,
    }
    return CatalogProduct(
        source_id=source_id,
        source_status=source_status,
        source_image=str(image.get("url") or "").strip() or None,
        image_key=str(image.get("s3_key") or "").strip() or None,
        payload=payload,
    )


def load_catalog(path: Path, domain: str) -> list[CatalogProduct]:
    products: list[CatalogProduct] = []
    for row in read_products_copy(path):
        if (row.get("domain") or "").strip().casefold() != domain.casefold():
            continue
        products.append(map_product(row))
    return sorted(products, key=lambda product: product.source_id)


class CappeOwnerAPI:
    def __init__(self, base_url: str, token: str, site_id: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.site_id = site_id
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = "application/json",
    ) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ImportFailure(f"Cappe API {exc.code} for {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ImportFailure(f"Cappe API request failed for {path}: {exc.reason}") from exc
        return json.loads(data) if data else None

    def existing_skus(self) -> dict[str, str]:
        rows = self._request("GET", f"/sites/{self.site_id}/products", content_type=None)
        return {
            row["sku"]: row["id"]
            for row in rows or []
            if isinstance(row, dict) and row.get("sku") and row.get("id")
        }

    def upload_image(self, filename: str, content_type: str, data: bytes) -> str:
        boundary = f"----cappe-ogo24-{uuid.uuid4().hex}"
        disposition = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename.replace(chr(34), "_")}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        body = disposition + data + f"\r\n--{boundary}--\r\n".encode()
        response = self._request(
            "POST",
            f"/sites/{self.site_id}/upload",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        if not isinstance(response, dict) or not response.get("url"):
            raise ImportFailure("Cappe image upload returned no URL")
        return str(response["url"])

    def create_product(self, payload: dict[str, Any]) -> str:
        response = self._request(
            "POST",
            f"/sites/{self.site_id}/products",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        if not isinstance(response, dict) or not response.get("id"):
            raise ImportFailure("Cappe product create returned no id")
        return str(response["id"])


def _image_candidate(product: CatalogProduct, image_root: Path | None) -> str | Path | None:
    if image_root and product.image_key:
        local = image_root / product.image_key
        if local.is_file():
            return local
    return product.source_image


def read_image(source: str | Path) -> tuple[str, str, bytes]:
    """Read an image from an optional local archive or the dump's source URL."""
    if isinstance(source, Path):
        data = source.read_bytes()
        filename = source.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    else:
        request = urllib.request.Request(source, headers={"User-Agent": "matcha-cappe-catalog-import/1"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                length = int(response.headers.get("Content-Length", "0") or 0)
                if length > MAX_IMAGE_BYTES:
                    raise ImportFailure(f"source image is larger than {MAX_IMAGE_BYTES} bytes")
                data = response.read(MAX_IMAGE_BYTES + 1)
                content_type = response.headers.get_content_type()
        except urllib.error.URLError as exc:
            raise ImportFailure(f"source image download failed: {exc.reason}") from exc
        filename = Path(urllib.parse.unquote(urllib.parse.urlparse(source).path)).name or "product-image"
    if not data:
        raise ImportFailure("source image is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImportFailure(f"source image is larger than {MAX_IMAGE_BYTES} bytes")
    if content_type == "application/octet-stream":
        content_type = mimetypes.guess_type(filename)[0] or content_type
    return filename, content_type, data


def run_import(
    products: list[CatalogProduct],
    *,
    api: CappeOwnerAPI,
    image_root: Path | None,
    allow_missing_images: bool,
) -> list[ImportResult]:
    existing = api.existing_skus()
    results: list[ImportResult] = []
    for product in products:
        name = product.payload["name"]
        sku = product.payload["sku"]
        if sku in existing:
            results.append(
                ImportResult(product.source_id, name, "skipped", product_id=existing[sku])
            )
            continue
        payload = dict(product.payload)
        try:
            source = _image_candidate(product, image_root)
            uploaded_url: str | None = None
            if source is not None:
                try:
                    filename, content_type, data = read_image(source)
                    uploaded_url = api.upload_image(filename, content_type, data)
                except ImportFailure:
                    if not allow_missing_images:
                        raise
            payload["image_url"] = uploaded_url
            product_id = api.create_product(payload)
            results.append(
                ImportResult(product.source_id, name, "created", uploaded_url, product_id)
            )
        except ImportFailure as exc:
            results.append(ImportResult(product.source_id, name, "failed", error=str(exc)))
    return results


def _print_mapping(products: list[CatalogProduct]) -> None:
    print("source_id\tstatus\tprice_cents\tcategory\toptions\trecurring\tname")
    for product in products:
        payload = product.payload
        option_count = sum(len(group["options"]) for group in payload["option_groups"])
        print(
            f"{product.source_id}\t{payload['status']}\t{payload['price_cents']}\t"
            f"{payload['category'] or ''}\t{option_count}\t"
            f"{'yes' if payload['subscription_intervals'] else 'no'}\t{payload['name']}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP)
    parser.add_argument("--domain", default="ahnimal")
    parser.add_argument("--api-base", default=os.getenv("CAPPE_API_URL", "https://gummfit.com/api/cappe"))
    parser.add_argument("--site-id", default=os.getenv("CAPPE_SITE_ID"))
    parser.add_argument("--token", default=os.getenv("CAPPE_ACCESS_TOKEN"))
    parser.add_argument("--image-root", type=Path, help="Optional local root containing each images[].s3_key")
    parser.add_argument(
        "--allow-missing-images",
        action="store_true",
        help="Create products even when a source image cannot be downloaded",
    )
    parser.add_argument("--limit", type=int, help="Import only the first N mapped products")
    parser.add_argument("--report", type=Path, help="Write the result report as JSON")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform uploads and product creates. Without this flag the command is a dry run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.dump.is_file():
        print(f"error: dump not found: {args.dump}", file=sys.stderr)
        return 2
    try:
        products = load_catalog(args.dump, args.domain)
    except (ImportFailure, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.limit is not None:
        if args.limit < 0:
            print("error: --limit must be non-negative", file=sys.stderr)
            return 2
        products = products[: args.limit]
    _print_mapping(products)
    print(f"\nMapped {len(products)} product(s) for domain={args.domain!r}.")
    if not args.apply:
        print("Dry run only; no network requests were made. Pass --apply to import.")
        return 0
    if not args.site_id or not args.token:
        print("error: --apply requires --site-id and --token (or CAPPE_SITE_ID/CAPPE_ACCESS_TOKEN)", file=sys.stderr)
        return 2

    api = CappeOwnerAPI(args.api_base, args.token, args.site_id)
    try:
        results = run_import(
            products,
            api=api,
            image_root=args.image_root,
            allow_missing_images=args.allow_missing_images,
        )
    except ImportFailure as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for result in results:
        suffix = f" ({result.error})" if result.error else ""
        print(f"{result.action:7} ogo24:{result.source_id} {result.name}{suffix}")
    if args.report:
        args.report.write_text(
            json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    failed = sum(result.action == "failed" for result in results)
    created = sum(result.action == "created" for result in results)
    skipped = sum(result.action == "skipped" for result in results)
    print(f"Created {created}; skipped {skipped}; failed {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
