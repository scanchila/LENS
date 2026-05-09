"""MinIO client tests (TICKET-015).

Run inside the docker compose test stack where the ``minio`` service is
reachable. The bucket is bootstrapped on app startup; these tests
exercise the wrapper directly.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.storage import MinIOClient, ensure_bucket, minio_client


def _unique_key(prefix: str = "tests") -> str:
    return f"{prefix}/{uuid.uuid4()}.bin"


def test_bucket_bootstrap_idempotent() -> None:
    ensure_bucket()
    ensure_bucket()
    assert minio_client.bucket


def test_put_and_get() -> None:
    ensure_bucket()
    key = _unique_key()
    payload = b"hello world"
    info = minio_client.put_object(payload, key, content_type="text/plain")
    assert info.key == key
    assert info.size == len(payload)
    fetched = minio_client.get_object(key)
    assert fetched == payload
    minio_client.delete_object(key)


def test_presigned_url_works() -> None:
    ensure_bucket()
    key = _unique_key()
    payload = b"presigned-roundtrip"
    minio_client.put_object(payload, key, content_type="application/octet-stream")
    url = minio_client.presigned_url(key, expires_seconds=120)
    assert url.startswith(("http://", "https://"))
    resp = httpx.get(url, timeout=10.0)
    assert resp.status_code == 200, resp.text
    assert resp.content == payload
    minio_client.delete_object(key)


def test_minio_client_uses_settings() -> None:
    c = MinIOClient()
    assert c.bucket == minio_client.bucket


def test_get_nonexistent_raises() -> None:
    ensure_bucket()
    with pytest.raises(ClientError):
        minio_client.get_object(_unique_key("does-not-exist"))
