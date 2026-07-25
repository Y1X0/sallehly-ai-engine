from __future__ import annotations

from pathlib import Path

from .provider import IStorageProvider


class S3Provider(IStorageProvider):
    """Real S3-compatible `IStorageProvider` (Phase 8 WP4) via `boto3`.
    `endpoint_url` is what makes this "S3-compatible" rather than
    AWS-only - pointed at a real MinIO/R2/Backblaze endpoint the same
    way as AWS S3 itself (`endpoint_url=None`). URIs returned are
    `s3://<bucket>/<key>` - a stable, storage-agnostic identifier, not a
    fetchable HTTP URL; generating presigned/public HTTP URLs for actual
    client access is `docs/PHASE8_SCALEOUT_PLAN.md` item 26 (signed
    URLs, WP11), not this class's job.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region_name,
        )

    def put(self, key: str, source_path: str | Path) -> str:
        self._client.upload_file(str(source_path), self._bucket, key)
        return self.get_uri(key)

    def get_uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise
