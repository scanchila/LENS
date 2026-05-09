"""MinIO / S3-compatible object storage wrapper.

Thin facade over ``boto3`` for raw user uploads. The default bucket is
``settings.MINIO_BUCKET_RAW_UPLOADS`` (``lens-raw``); the FastAPI
lifespan calls :func:`ensure_bucket` at startup to create it idempotently.

Key convention (TICKET-015): ``<owner_id>/<document_id>/<filename>``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.client import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.config import settings


@dataclass(frozen=True)
class ObjectInfo:
    bucket: str
    key: str
    etag: str | None
    size: int
    content_type: str | None


class MinIOClient:
    def __init__(
        self,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        self._endpoint_url = endpoint_url or settings.MINIO_ENDPOINT
        self._access_key = access_key or settings.MINIO_ROOT_USER
        self._secret_key = secret_key or settings.MINIO_ROOT_PASSWORD
        self._bucket = bucket or settings.MINIO_BUCKET_RAW_UPLOADS
        self._region = region or settings.MINIO_REGION
        self._client: Any | None = None

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def s3(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
                config=Config(signature_version="s3v4"),
            )
        return self._client

    def ensure_bucket(self) -> None:
        try:
            self.s3.head_bucket(Bucket=self._bucket)
            return
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise
        try:
            self.s3.create_bucket(Bucket=self._bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise

    def put_object(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
    ) -> ObjectInfo:
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        resp = self.s3.put_object(**kwargs)
        return ObjectInfo(
            bucket=self._bucket,
            key=key,
            etag=resp.get("ETag"),
            size=len(data),
            content_type=content_type,
        )

    def get_object(self, key: str) -> bytes:
        resp = self.s3.get_object(Bucket=self._bucket, Key=key)
        body = resp["Body"]
        try:
            data: bytes = body.read()
            return data
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        url: str = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
        return url

    def delete_object(self, key: str) -> None:
        self.s3.delete_object(Bucket=self._bucket, Key=key)


minio_client = MinIOClient()


def get_minio_client() -> MinIOClient:
    return minio_client


def ensure_bucket() -> None:
    minio_client.ensure_bucket()
