import os
from typing import Optional
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from ...config import get_settings


class StorageService:
    """Service for storing files in S3 or locally."""

    def __init__(self):
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.region = settings.s3_region
        self.cloudfront_domain = settings.cloudfront_domain
        self.app_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.uploads_root = os.path.join(self.app_root, "uploads")

        if self.bucket:
            self.s3_client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
        else:
            self.s3_client = None
            # Fall back to local storage
            self.local_dir = os.path.join(
                self.uploads_root,
                "resumes",
            )
            os.makedirs(self.local_dir, exist_ok=True)

    def _generate_key(self, filename: str, prefix: str = "resumes") -> str:
        """Generate a unique S3 key for a file."""
        ext = os.path.splitext(filename)[1].lower()
        unique_id = uuid4().hex
        return f"{prefix}/{unique_id}{ext}"

    def _get_cloudfront_url(self, key: str) -> str:
        """Generate CloudFront URL from S3 key."""
        if self.cloudfront_domain:
            return f"https://{self.cloudfront_domain}/{key}"
        return f"s3://{self.bucket}/{key}"

    def _resolve_local_upload_path(self, path: str) -> str:
        """Resolve and validate a local storage path under app/uploads."""
        if path.startswith("/uploads/"):
            candidate = os.path.join(self.app_root, path.lstrip("/"))
        elif path.startswith("uploads/"):
            candidate = os.path.join(self.app_root, path)
        elif os.path.isabs(path):
            candidate = path
        else:
            raise RuntimeError("Unsupported local storage path")

        resolved = os.path.realpath(candidate)
        uploads_root = os.path.realpath(self.uploads_root)
        if resolved != uploads_root and not resolved.startswith(f"{uploads_root}{os.sep}"):
            raise RuntimeError("Local storage path is outside uploads directory")
        return resolved

    def is_supported_storage_path(self, path: Optional[str]) -> bool:
        """Return True when path is a supported storage reference."""
        if not path or not isinstance(path, str):
            return False

        if self.cloudfront_domain and path.startswith(f"https://{self.cloudfront_domain}/"):
            return True
        if path.startswith("s3://"):
            return True
        try:
            self._resolve_local_upload_path(path)
            return True
        except RuntimeError:
            return False

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        prefix: str = "resumes",
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file and return storage path/URL.

        Returns:
            CloudFront URL (if configured) or S3 URI (s3://bucket/key) or local file path
        """
        if self.s3_client and self.bucket:
            key = self._generate_key(filename, prefix)

            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            try:
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=file_bytes,
                    **extra_args,
                )
                return self._get_cloudfront_url(key)
            except ClientError as e:
                raise RuntimeError(f"Failed to upload to S3: {e}")
        else:
            # Local storage fallback
            ext = os.path.splitext(filename)[1].lower()
            unique_id = uuid4().hex
            local_path = os.path.join(self.local_dir, f"{unique_id}{ext}")

            with open(local_path, "wb") as f:
                f.write(file_bytes)

            return f"/uploads/resumes/{unique_id}{ext}"

    async def download_file(self, path: str) -> bytes:
        """Download a file from storage.

        Args:
            path: CloudFront URL, S3 URI (s3://bucket/key), or local file path

        Returns:
            File contents as bytes
        """
        # Handle CloudFront URLs - convert back to S3 path
        if self.cloudfront_domain and path.startswith(f"https://{self.cloudfront_domain}/"):
            key = path[len(f"https://{self.cloudfront_domain}/"):]
            if not self.s3_client or not self.bucket:
                raise RuntimeError("S3 not configured but CloudFront path provided")
            try:
                response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                return response["Body"].read()
            except ClientError as e:
                raise RuntimeError(f"Failed to download from S3: {e}")

        if path.startswith("s3://"):
            if not self.s3_client:
                raise RuntimeError("S3 not configured but S3 path provided")

            # Parse s3://bucket/key
            parts = path[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""

            try:
                response = self.s3_client.get_object(Bucket=bucket, Key=key)
                return response["Body"].read()
            except ClientError as e:
                raise RuntimeError(f"Failed to download from S3: {e}")

        local_path = self._resolve_local_upload_path(path)
        with open(local_path, "rb") as f:
            return f.read()

    async def delete_file(self, path: str) -> bool:
        """Delete a file from storage.

        Returns:
            True if deleted, False if not found
        """
        # Handle CloudFront URLs - convert back to S3 path
        if self.cloudfront_domain and path.startswith(f"https://{self.cloudfront_domain}/"):
            if not self.s3_client or not self.bucket:
                return False
            key = path[len(f"https://{self.cloudfront_domain}/"):]
            try:
                self.s3_client.delete_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return False

        if path.startswith("s3://"):
            if not self.s3_client:
                return False

            parts = path[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""

            try:
                self.s3_client.delete_object(Bucket=bucket, Key=key)
                return True
            except ClientError:
                return False

        try:
            local_path = self._resolve_local_upload_path(path)
        except RuntimeError:
            return False
        if os.path.exists(local_path):
            os.unlink(local_path)
            return True
        return False

    def get_presigned_url(self, path: str, expires_in: int = 3600) -> Optional[str]:
        """Get a presigned URL for downloading a file.

        Only works for S3 storage. Returns None for local files.
        """
        if not path.startswith("s3://") or not self.s3_client:
            return None

        parts = path[5:].split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError:
            return None


# Singleton instance
_storage: Optional[StorageService] = None


def get_storage() -> StorageService:
    """Get the storage service singleton."""
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
