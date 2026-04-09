import asyncio
import os

import pytest

from app.config import load_settings
from app.core.services.storage import StorageService


def test_is_supported_storage_path_rejects_arbitrary_local_paths():
    load_settings()
    storage = StorageService()
    assert not storage.is_supported_storage_path("/etc/passwd")
    assert storage.is_supported_storage_path("/uploads/resumes/example.pdf")


def test_download_file_blocks_non_upload_paths():
    load_settings()
    storage = StorageService()
    with pytest.raises(RuntimeError, match="outside uploads directory"):
        asyncio.run(storage.download_file("/etc/passwd"))


def test_download_file_allows_uploads_path():
    load_settings()
    storage = StorageService()
    if getattr(storage, "s3_client", None):
        pytest.skip("Local storage path test is only valid when S3 is not configured")

    filename = "handbook-storage-test.txt"
    local_path = os.path.join(storage.local_dir, filename)
    with open(local_path, "wb") as f:
        f.write(b"ok")

    data = asyncio.run(storage.download_file(f"/uploads/resumes/{filename}"))
    assert data == b"ok"
