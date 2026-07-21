"""matcha_work_document — storage helpers (L6 split).

Extracted from the monolithic service; re-exported by the package __init__.
"""
from app.core.services.storage import get_storage
from app.database import get_connection
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID
import json
import mimetypes
import posixpath
from app.matcha.services.matcha_work_document._coerce import (
    _parse_jsonb,
)

import logging
logger = logging.getLogger(__name__)

MATCHA_WORK_STORAGE_ROOT = "matcha-work"

def _should_enforce_company_scoped_matcha_work_storage() -> bool:
    storage = get_storage()
    return bool(storage.s3_client and storage.bucket)

def build_matcha_work_thread_storage_prefix(company_id: UUID, thread_id: UUID, asset_kind: str) -> str:
    return f"{MATCHA_WORK_STORAGE_ROOT}/companies/{company_id}/threads/{thread_id}/{asset_kind}"

def _storage_key_from_path(path: Optional[str]) -> Optional[str]:
    if not path or not isinstance(path, str):
        return None

    storage = get_storage()
    if storage.cloudfront_domain:
        cloudfront_prefix = f"https://{storage.cloudfront_domain}/"
        if path.startswith(cloudfront_prefix):
            return path[len(cloudfront_prefix):]

    if path.startswith("s3://"):
        parts = path[5:].split("/", 1)
        return parts[1] if len(parts) > 1 else ""

    return None

def _storage_path_has_prefix(path: Optional[str], prefix: str) -> bool:
    key = _storage_key_from_path(path)
    return bool(key and key.startswith(f"{prefix}/"))

def _storage_filename(path: Optional[str], default_filename: str) -> str:
    key = _storage_key_from_path(path)
    if key:
        filename = posixpath.basename(key)
        if filename:
            return filename

    if path:
        filename = posixpath.basename(urlparse(path).path)
        if filename:
            return filename

    return default_filename

async def _migrate_matcha_work_asset_to_scope(
    path: str,
    *,
    company_id: UUID,
    thread_id: UUID,
    asset_kind: str,
    default_filename: str,
) -> str:
    if not _should_enforce_company_scoped_matcha_work_storage():
        return path

    expected_prefix = build_matcha_work_thread_storage_prefix(company_id, thread_id, asset_kind)
    if _storage_path_has_prefix(path, expected_prefix):
        return path

    storage = get_storage()
    if not storage.is_supported_storage_path(path):
        return path

    file_bytes = await storage.download_file(path)
    filename = _storage_filename(path, default_filename)
    content_type = mimetypes.guess_type(filename)[0]
    scoped_path = await storage.upload_file(
        file_bytes,
        filename,
        prefix=expected_prefix,
        content_type=content_type,
    )

    if scoped_path != path:
        try:
            await storage.delete_file(path)
        except Exception as exc:
            logger.warning("Failed to delete legacy Matcha Work asset %s after migration: %s", path, exc)

    return scoped_path

async def ensure_matcha_work_thread_storage_scope(
    thread_id: UUID,
    company_id: UUID,
    current_state: dict,
) -> dict:
    if not _should_enforce_company_scoped_matcha_work_storage():
        return current_state
    if not isinstance(current_state, dict) or not current_state:
        return current_state

    normalized_state = dict(current_state)
    changed = False

    top_level_cover = normalized_state.get("cover_image_url")
    if isinstance(top_level_cover, str) and top_level_cover:
        scoped_cover = await _migrate_matcha_work_asset_to_scope(
            top_level_cover,
            company_id=company_id,
            thread_id=thread_id,
            asset_kind="covers",
            default_filename="cover.png",
        )
        if scoped_cover != top_level_cover:
            normalized_state["cover_image_url"] = scoped_cover
            changed = True

    presentation = normalized_state.get("presentation")
    if isinstance(presentation, dict):
        normalized_presentation = dict(presentation)
        presentation_cover = normalized_presentation.get("cover_image_url")
        if isinstance(presentation_cover, str) and presentation_cover:
            scoped_cover = await _migrate_matcha_work_asset_to_scope(
                presentation_cover,
                company_id=company_id,
                thread_id=thread_id,
                asset_kind="covers",
                default_filename="cover.png",
            )
            if scoped_cover != presentation_cover:
                normalized_presentation["cover_image_url"] = scoped_cover
                normalized_state["presentation"] = normalized_presentation
                changed = True

    images = normalized_state.get("images")
    if isinstance(images, list) and images:
        scoped_images: list[str] = []
        image_changed = False
        for index, image_path in enumerate(images):
            if not isinstance(image_path, str) or not image_path:
                scoped_images.append(image_path)
                continue
            scoped_image = await _migrate_matcha_work_asset_to_scope(
                image_path,
                company_id=company_id,
                thread_id=thread_id,
                asset_kind="images",
                default_filename=f"image-{index + 1}.jpg",
            )
            scoped_images.append(scoped_image)
            image_changed = image_changed or scoped_image != image_path
        if image_changed:
            normalized_state["images"] = scoped_images
            changed = True

    if changed:
        async with get_connection() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT current_state
                    FROM mw_threads
                    WHERE id=$1 AND company_id=$2
                    FOR UPDATE
                    """,
                    thread_id,
                    company_id,
                )
                if row is not None:
                    latest_state = _parse_jsonb(row["current_state"])
                    merged_state = dict(latest_state)

                    if "cover_image_url" in normalized_state:
                        merged_state["cover_image_url"] = normalized_state["cover_image_url"]
                    if "images" in normalized_state:
                        merged_state["images"] = normalized_state["images"]
                    if isinstance(normalized_state.get("presentation"), dict):
                        latest_presentation = latest_state.get("presentation")
                        merged_presentation = dict(latest_presentation) if isinstance(latest_presentation, dict) else {}
                        if "cover_image_url" in normalized_state["presentation"]:
                            merged_presentation["cover_image_url"] = normalized_state["presentation"]["cover_image_url"]
                        merged_state["presentation"] = merged_presentation

                    await conn.execute(
                        """
                        UPDATE mw_threads
                        SET current_state=$1
                        WHERE id=$2 AND company_id=$3
                        """,
                        json.dumps(merged_state),
                        thread_id,
                        company_id,
                    )
                    normalized_state = merged_state

    return normalized_state
