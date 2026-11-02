"""Object storage with the layout from section 5:

originals/{org}/{project}/{document-version}/{filename}
derived/{org}/{project}/{document-version}/{pipeline-version}/{artifact}
reports/{org}/{project}/{run}/{report-version}/{artifact}
assets/{asset-version}/...

Buckets are private. Downloads use short-lived authorized URLs (S3 presigned; local backend
issues a signed token redeemed at /v1/files/{token}).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from .config import get_settings


class Storage(ABC):
    @abstractmethod
    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, bucket: str, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, bucket: str, key: str) -> bool: ...

    @abstractmethod
    def presign_get(self, bucket: str, key: str, ttl_seconds: int = 300, filename: str | None = None) -> str: ...

    @abstractmethod
    def presign_put(self, bucket: str, key: str, content_type: str, ttl_seconds: int = 900) -> dict: ...


class LocalStorage(Storage):
    """Filesystem backend for development. Download URLs are HMAC-signed tokens served by the API."""

    def __init__(self, root: str, secret: str, public_base: str):
        self.root = Path(root)
        self.secret = secret.encode()
        self.public_base = public_base.rstrip("/")

    def _path(self, bucket: str, key: str) -> Path:
        p = (self.root / bucket / key).resolve()
        if not str(p).startswith(str((self.root / bucket).resolve())):
            raise ValueError("invalid key")
        return p

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        p = self._path(bucket, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        (p.parent / (p.name + ".content-type")).write_text(content_type)

    def get(self, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()

    def content_type(self, bucket: str, key: str) -> str:
        p = self._path(bucket, key)
        ct = p.parent / (p.name + ".content-type")
        return ct.read_text() if ct.exists() else "application/octet-stream"

    def exists(self, bucket: str, key: str) -> bool:
        return self._path(bucket, key).exists()

    def sign(self, bucket: str, key: str, exp: int, mode: str) -> str:
        msg = f"{mode}|{bucket}|{key}|{exp}".encode()
        return hmac.new(self.secret, msg, hashlib.sha256).hexdigest()

    def presign_get(self, bucket: str, key: str, ttl_seconds: int = 300, filename: str | None = None) -> str:
        exp = int(time.time()) + ttl_seconds
        sig = self.sign(bucket, key, exp, "get")
        fn = f"&filename={filename}" if filename else ""
        return f"{self.public_base}/v1/files/get?bucket={bucket}&key={key}&exp={exp}&sig={sig}{fn}"

    def presign_put(self, bucket: str, key: str, content_type: str, ttl_seconds: int = 900) -> dict:
        exp = int(time.time()) + ttl_seconds
        sig = self.sign(bucket, key, exp, "put")
        return {"method": "PUT", "url": f"{self.public_base}/v1/files/put?bucket={bucket}&key={key}&exp={exp}&sig={sig}", "headers": {"Content-Type": content_type}}

    def verify(self, bucket: str, key: str, exp: int, sig: str, mode: str) -> bool:
        if exp < time.time():
            return False
        return hmac.compare_digest(self.sign(bucket, key, exp, mode), sig)


class S3Storage(Storage):
    def __init__(self, region: str, endpoint_url: str | None):
        import boto3

        self.client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256")

    def get(self, bucket: str, key: str) -> bytes:
        return self.client.get_object(Bucket=bucket, Key=key)["Body"].read()

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except self.client.exceptions.ClientError:
            return False

    def presign_get(self, bucket: str, key: str, ttl_seconds: int = 300, filename: str | None = None) -> str:
        params = {"Bucket": bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=ttl_seconds)

    def presign_put(self, bucket: str, key: str, content_type: str, ttl_seconds: int = 900) -> dict:
        url = self.client.generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": key, "ContentType": content_type}, ExpiresIn=ttl_seconds)
        return {"method": "PUT", "url": url, "headers": {"Content-Type": content_type}}


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":
            _storage = S3Storage(s.aws_region, s.s3_endpoint_url)
        else:
            _storage = LocalStorage(s.storage_local_root, s.auth_dev_secret, s.api_internal_base_url)
    return _storage


class Buckets:
    @staticmethod
    def originals() -> str:
        return get_settings().s3_bucket_originals

    @staticmethod
    def derived() -> str:
        return get_settings().s3_bucket_derived

    @staticmethod
    def reports() -> str:
        return get_settings().s3_bucket_reports


def original_key(org: uuid.UUID, project: uuid.UUID, version: uuid.UUID, filename: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:200]
    return f"originals/{org}/{project}/{version}/{safe}"


def derived_key(org: uuid.UUID, project: uuid.UUID, version: uuid.UUID, pipeline_version: str, artifact: str) -> str:
    return f"derived/{org}/{project}/{version}/{pipeline_version}/{artifact}"


def report_key(org: uuid.UUID, project: uuid.UUID, run: uuid.UUID, report_version: int, artifact: str) -> str:
    return f"reports/{org}/{project}/{run}/{report_version}/{artifact}"
