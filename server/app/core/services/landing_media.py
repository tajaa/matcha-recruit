"""Direct S3 uploads for public scheduling commercials, served through our CDN.

No bucket or CDN policy is changed here. Assets are immutable, uniquely keyed,
admin-authenticated, and checked before their URLs enter the public settings.
"""
import asyncio
import re
from pathlib import Path
from uuid import uuid4
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from app.core.models.landing_media import CommercialUploadRequest, SchedulingCommercial
from app.core.services.storage import get_storage

_TYPES = {
    'video': {'.mp4': 'video/mp4', '.webm': 'video/webm'},
    'poster': {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'},
    'captions': {'.vtt': 'text/vtt'},
}
_LIMITS = {'video': 150 * 1024 * 1024, 'poster': 5 * 1024 * 1024, 'captions': 1024 * 1024}
_PREFIX = 'landing/scheduling-commercial/'


def _kind(slot: str) -> str:
    return 'captions' if slot == 'captions' else slot.rsplit('_', 1)[1]


def _configured_storage():
    storage = get_storage()
    if not storage.s3_client or not storage.bucket or not storage.cloudfront_domain:
        raise HTTPException(503, 'Commercial uploads require the public S3 bucket and CloudFront domain to be configured.')
    return storage


def prepare_commercial_upload(body: CommercialUploadRequest) -> dict:
    kind = _kind(body.slot)
    ext = Path(body.filename).suffix.lower()
    mime = _TYPES[kind].get(ext)
    if mime is None or body.content_type != mime:
        raise HTTPException(400, f'Unsupported {kind} file or content type.')
    if body.size > _LIMITS[kind]:
        raise HTTPException(400, f'File exceeds the {_LIMITS[kind] // (1024 * 1024)} MB limit.')
    storage = _configured_storage()
    key = f'{_PREFIX}{body.slot}/{uuid4().hex}{ext}'
    fields = {'Content-Type': mime, 'x-amz-server-side-encryption': 'AES256', 'Cache-Control': 'public, max-age=31536000, immutable'}
    conditions = [{name: value} for name, value in fields.items()]
    conditions.append(['content-length-range', body.size, body.size])
    try:
        post = storage.s3_client.generate_presigned_post(Bucket=storage.bucket, Key=key, Fields=fields, Conditions=conditions, ExpiresIn=900)
    except (BotoCoreError, ClientError):
        raise HTTPException(503, 'Could not prepare the upload. Try again.') from None
    return {'upload_url': post['url'], 'fields': post['fields'], 'asset_url': f'https://{storage.cloudfront_domain}/{key}', 'content_type': mime}


async def verify_commercial_asset(slot: str, url: str, *, expected_size: int | None = None, expected_type: str | None = None) -> None:
    storage = _configured_storage()
    prefix = f'https://{storage.cloudfront_domain}/{_PREFIX}{slot}/'
    if not url.startswith(prefix) or not re.fullmatch(r'[a-f0-9]{32}\.[a-z0-9]+', url[len(prefix):]):
        raise HTTPException(400, 'Choose a commercial asset uploaded through Landing Media.')
    key = url[len(f'https://{storage.cloudfront_domain}/'):]
    kind = _kind(slot)
    mime = _TYPES[kind].get(Path(key).suffix)
    if mime is None:
        raise HTTPException(400, 'Asset does not match this upload slot.')
    try:
        head = await asyncio.to_thread(storage.s3_client.head_object, Bucket=storage.bucket, Key=key)
    except (BotoCoreError, ClientError):
        raise HTTPException(400, 'The upload is missing or incomplete. Upload the file again before saving.') from None
    size = head.get('ContentLength', 0)
    if not 0 < size <= _LIMITS[kind] or head.get('ContentType') != mime:
        raise HTTPException(400, 'Uploaded asset has an invalid size or content type.')
    if (expected_size is not None and size != expected_size) or (expected_type is not None and mime != expected_type):
        raise HTTPException(400, 'The uploaded asset does not match the selected file.')


async def verify_commercial_settings(settings: SchedulingCommercial) -> None:
    # Always allow the emergency off switch, even during an S3 outage.
    # Enabling verifies every asset before the database write.
    if not settings.enabled:
        return
    for slot in ('desktop_video', 'mobile_video', 'desktop_poster', 'mobile_poster', 'captions'):
        url = getattr(settings, f'{slot}_url')
        if url:
            await verify_commercial_asset(slot, url)
