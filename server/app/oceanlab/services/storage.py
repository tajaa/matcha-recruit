"""Object storage for oceanlab masters, artwork, packages and renders.

Prod is S3. That is not a preference — the backend runs in blue-green Docker
containers that are *removed* on every deploy (`deploy-backend-bluegreen.sh`),
so anything written to container disk is gone at the next release. Masters are
the one asset in this system that cannot be regenerated.

We reuse the monolith's configured boto3 client
(`app.core.services.storage.StorageService.s3_client`) but deliberately NOT its
`upload_private_file`: that method is `async` (oceanlab routes are sync), takes
the whole body as `bytes` (a 24-bit/96kHz five-minute master is ~170MB and the
worker cgroup is 768M), and mints its own random key, which would throw away
the deterministic key scheme the rest of this package relies on.
"""

import hashlib
import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Protocol

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1MB — used for every hash/copy loop in this module


class StorageError(Exception):
    """Storage failure whose message is safe to show a user."""


def _validate_key(key: str) -> str:
    """Reject traversal and absolute keys before they reach a filesystem or S3."""
    if not key or key != key.strip():
        raise StorageError("Storage key must be a non-empty, untrimmed-free string")
    if key.startswith("/") or ".." in key.split("/"):
        raise StorageError(f"Unsafe storage key: {key!r}")
    return key


def hash_and_size(src: BinaryIO) -> tuple[int, str]:
    """Stream `src` once to compute (size_bytes, sha256_hex), then rewind it.

    Never reads the whole object into memory — callers hand us Starlette's
    SpooledTemporaryFile, which is already on disk for anything over 1MB.
    """
    digest = hashlib.sha256()
    size = 0
    src.seek(0)
    while chunk := src.read(CHUNK_SIZE):
        digest.update(chunk)
        size += len(chunk)
    src.seek(0)
    return size, digest.hexdigest()


class ObjectStore(Protocol):
    def put(self, key: str, src: BinaryIO, *, content_type: str) -> tuple[int, str]:
        """Store `src` at `key`. Returns (size_bytes, sha256_hex). Overwrites."""

    def open(self, key: str) -> BinaryIO: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Delete `key`. Missing key is a no-op, not an error."""

    def local_copy(self, key: str) -> AbstractContextManager[Path]:
        """Yield a real filesystem path for `key` — ffmpeg cannot read a stream."""

    def presigned_url(self, key: str, expires_in: int = 900) -> str | None:
        """Time-limited download URL, or None when the backend can't mint one."""


class S3Store:
    """S3-backed store. Keys are namespaced under `prefix` inside `bucket`."""

    def __init__(self, client, bucket: str, prefix: str):
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}/{_validate_key(key)}" if self._prefix else _validate_key(key)

    def put(self, key: str, src: BinaryIO, *, content_type: str) -> tuple[int, str]:
        # Two passes over the caller's already-on-disk temp file: hash, then
        # upload. boto3's upload_fileobj does its own multipart chunking, so
        # neither pass materializes the object in memory.
        size, sha256 = hash_and_size(src)
        self._client.upload_fileobj(
            src,
            self._bucket,
            self._full_key(key),
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )
        return size, sha256

    def open(self, key: str) -> BinaryIO:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=self._full_key(key))
        except Exception as e:  # botocore ClientError and friends
            raise StorageError(f"Could not read {key}: {e}") from e
        return resp["Body"]

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._full_key(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=self._full_key(key))
        except Exception as e:
            logger.warning("oceanlab: delete failed for %s: %s", key, e)

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        suffix = Path(key).suffix
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            try:
                self._client.download_fileobj(self._bucket, self._full_key(key), tmp)
            except Exception as e:
                raise StorageError(f"Could not download {key}: {e}") from e
            tmp.close()
            yield Path(tmp.name)
        finally:
            tmp.close()
            os.unlink(tmp.name)

    def presigned_url(self, key: str, expires_in: int = 900) -> str | None:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": self._full_key(key)},
                ExpiresIn=expires_in,
            )
        except Exception:
            return None


class LocalDiskStore:
    """Filesystem store for local dev and tests. NOT safe for prod — see module docstring."""

    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / _validate_key(key)).resolve()
        # Defence in depth: _validate_key already rejects "..", but a symlinked
        # root could still escape, so assert containment on the resolved path.
        if not path.is_relative_to(self._root.resolve()):
            raise StorageError(f"Unsafe storage key: {key!r}")
        return path

    def put(self, key: str, src: BinaryIO, *, content_type: str) -> tuple[int, str]:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        size, sha256 = hash_and_size(src)
        # Write to a sibling temp then os.replace, so a crash mid-write can't
        # leave a truncated master sitting at the real key.
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as out:
            shutil.copyfileobj(src, out, CHUNK_SIZE)
        os.replace(tmp, path)
        return size, sha256

    def open(self, key: str) -> BinaryIO:
        try:
            return open(self._path(key), "rb")
        except FileNotFoundError as e:
            raise StorageError(f"Could not read {key}: not found") from e

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except StorageError:
            return False

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"Could not read {key}: not found")
        yield path

    def presigned_url(self, key: str, expires_in: int = 900) -> str | None:
        return None  # caller falls back to streaming the bytes itself


@lru_cache(maxsize=1)
def get_store() -> ObjectStore:
    """Resolve the configured store once per process.

    S3 when a bucket is configured (oceanlab's own, else the monolith's shared
    private bucket), LocalDiskStore otherwise so local dev works with no AWS
    credentials at all.
    """
    from app.oceanlab.config import settings

    try:
        from app.core.services.storage import StorageService

        core = StorageService()
        bucket = settings.s3_bucket or core.private_bucket or core.bucket
        if core.s3_client and bucket:
            return S3Store(core.s3_client, bucket, settings.key_prefix)
    except Exception as e:
        logger.warning("oceanlab: S3 unavailable (%s), falling back to local disk", e)

    logger.warning(
        "oceanlab: using LocalDiskStore at %s — masters will NOT survive a container replacement",
        settings.storage_root,
    )
    return LocalDiskStore(settings.storage_root)


# ---------------------------------------------------------------------------
# Key scheme (PROJECT.md:185). File.storage_key stores these un-prefixed; the
# store adds settings.key_prefix. Keep every key construction in this module so
# a scheme change is one file.
# ---------------------------------------------------------------------------


def master_key(recording_id, ext: str) -> str:
    return f"masters/{recording_id}/original.{ext.lstrip('.')}"


def artwork_key(release_id, ext: str) -> str:
    return f"artwork/{release_id}/cover.{ext.lstrip('.')}"


def package_key(release_id, stamp: str) -> str:
    return f"packages/{release_id}/{stamp}/package.zip"


def render_key(delivery_id, track_id) -> str:
    return f"renders/{delivery_id}/{track_id}.mp4"


def export_key(registration_id, filename: str) -> str:
    return f"exports/{registration_id}/{filename}"


def statement_key(statement_id, filename: str) -> str:
    return f"statements/{statement_id}/{filename}"
