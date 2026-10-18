"""Private-only streamed media. Generated keys and checksums are mandatory."""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

from boto3.s3.transfer import TransferConfig

from app.config import get_settings
from app.core.services.storage import get_storage

from app.matcha.models.matcha_work.recaps import Asset
from .settings import SOURCE_BYTES

PREFIX = re.compile(r"\Aespresso-recaps/[a-f0-9-]{36}/[a-f0-9-]{36}/[a-f0-9-]{36}/(?:[a-z0-9./-]*)\Z")


def client():
    bucket = get_settings().s3_private_bucket
    storage = get_storage()
    if not bucket or storage.s3_client is None:
        raise RuntimeError("private_storage_unavailable")
    return storage.s3_client, bucket


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


async def upload(path: Path, key: str, mime: str, *, limit=SOURCE_BYTES) -> Asset:
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise ValueError("media_size_limit")
    digest = await asyncio.to_thread(checksum, path)
    asset = Asset(key=key, sha256=digest, bytes=size, mime=mime)
    s3, bucket = client()
    await asyncio.to_thread(s3.upload_file, str(path), bucket, asset.key,
                            ExtraArgs={"ContentType": mime, "ServerSideEncryption": "AES256", "Metadata": {"sha256": digest}},
                            Config=TransferConfig(max_concurrency=1, use_threads=False))
    head = await asyncio.to_thread(s3.head_object, Bucket=bucket, Key=key)
    if head["ContentLength"] != size or head.get("Metadata", {}).get("sha256") != digest:
        raise ValueError("upload_verification_failed")
    return asset


async def download(asset: Asset, destination: Path):
    s3, bucket = client()
    head = await asyncio.to_thread(s3.head_object, Bucket=bucket, Key=asset.key)
    if head["ContentLength"] != asset.bytes or head.get("Metadata", {}).get("sha256") != asset.sha256:
        raise ValueError("asset_metadata_mismatch")
    await asyncio.to_thread(s3.download_file, bucket, asset.key, str(destination),
                            Config=TransferConfig(max_concurrency=1, use_threads=False))
    if destination.stat().st_size != asset.bytes or await asyncio.to_thread(checksum, destination) != asset.sha256:
        raise ValueError("asset_checksum_mismatch")


def signed(asset: Asset) -> str:
    s3, bucket = client()
    return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": asset.key,
        "ResponseContentType": asset.mime, "ResponseContentDisposition": "inline"}, ExpiresIn=300)


async def cleanup(bucket: str, prefix: str) -> bool:
    s3, expected = client()
    if bucket != expected or not PREFIX.fullmatch(prefix) or ".." in prefix or not prefix.endswith("/"):
        raise ValueError("invalid_cleanup_prefix")
    # Delete versions as well as delete markers. A bounded batch is repeatable;
    # the next sweep starts at the prefix again, so no pagination state is lost.
    versions = await asyncio.to_thread(s3.list_object_versions, Bucket=bucket, Prefix=prefix, MaxKeys=200)
    objects = [{"Key": obj["Key"], "VersionId": obj["VersionId"]}
               for obj in [*versions.get("Versions", []), *versions.get("DeleteMarkers", [])]]
    if objects:
        response = await asyncio.to_thread(s3.delete_objects, Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
        if response.get("Errors"):
            raise RuntimeError("storage_cleanup_failed")
        return False
    # Unversioned buckets still have a null version, but this also covers S3
    # compatible implementations whose version listing omits ordinary objects.
    listing = await asyncio.to_thread(s3.list_objects_v2, Bucket=bucket, Prefix=prefix, MaxKeys=200)
    objects = [{"Key": obj["Key"]} for obj in listing.get("Contents", [])]
    if objects:
        response = await asyncio.to_thread(s3.delete_objects, Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
        if response.get("Errors"):
            raise RuntimeError("storage_cleanup_failed")
        return False
    return True
