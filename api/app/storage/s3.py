"""Object storage for uploaded documents and generated certificates.

Talks S3 to SeaweedFS (S3_ENDPOINT); pointing S3_ENDPOINT at AWS is the only
change needed to use real S3. Called by the documents route, the certificate
generator, and app/main.py at startup (ensure_bucket). Depends on: boto3.

boto3 is synchronous, so every call made from the event loop goes through one of
the `a*` wrappers at the bottom of this file rather than the bare function.
"""

import asyncio
import logging
import re
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings

log = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

# botocore's defaults are a 60 s connect, a 60 s read and 3 attempts — up to
# three minutes inside one call. A *hung* (rather than refused) object store
# therefore blocked the single event loop for long enough that the 10 s compose
# healthcheck queued behind it and the container flapped. These numbers are
# generous for a 30 KB PDF against a store in the same network, and brutal
# against a black hole.
CONNECT_TIMEOUT_S = 3
READ_TIMEOUT_S = 10
MAX_ATTEMPTS = 2


@lru_cache
def client() -> Any:
    """One shared boto3 S3 client. path-style addressing: SeaweedFS has no DNS
    for virtual-hosted buckets."""
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=CONNECT_TIMEOUT_S,
            read_timeout=READ_TIMEOUT_S,
            retries={"max_attempts": MAX_ATTEMPTS},
        ),
    )


def ensure_bucket() -> None:
    """Create S3_BUCKET if it is missing. Safe to call on every startup."""
    c = client()
    try:
        c.head_bucket(Bucket=settings.s3_bucket)
        log.info("s3: bucket %s present", settings.s3_bucket)
    except ClientError:
        c.create_bucket(Bucket=settings.s3_bucket)
        log.info("s3: created bucket %s", settings.s3_bucket)


def key_for(kind: str, id: str | int, filename: str) -> str:
    """Deterministic object key: `<kind>/<id>/<sanitised filename>`.

    e.g. key_for("documents", 12, "My Permit.pdf") -> "documents/12/My_Permit.pdf"
    """
    safe = _SAFE.sub("_", filename).strip("_") or "file"
    return f"{kind}/{id}/{safe}"


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Store bytes under key; returns the key so callers can persist it."""
    client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return key


def get_bytes(key: str) -> bytes:
    """Read an object back (certificate download, re-extraction)."""
    return client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()


# --------------------------------------------------------------------- async
# Thin wrappers so no coroutine calls boto3 directly. Each one hands a single
# blocking call to the default thread pool, which leaves the event loop free to
# serve the other in-flight SSE streams and /health while object storage is slow.


async def ahead_bucket() -> None:
    """head_bucket off the event loop — the /health S3 probe."""
    await asyncio.to_thread(client().head_bucket, Bucket=settings.s3_bucket)


async def aput_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """put_bytes off the event loop — resident uploads."""
    return await asyncio.to_thread(put_bytes, key, data, content_type)


async def aget_bytes(key: str) -> bytes:
    """get_bytes off the event loop — the certificate download."""
    return await asyncio.to_thread(get_bytes, key)
