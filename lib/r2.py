#!/usr/bin/env python3
"""r2.py — uploader ke Cloudflare R2 (S3-compatible) buat Threads CMS v2.

Baca credential dari ~/threads-cms-v2/.env
Bucket: media (shared sama PromptedSite), prefix threads/ biar kepisah.
Public URL lewat CDN: https://cdn.promptedsite.com/threads/<key>
"""
import os, uuid, mimetypes
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta

import boto3
from botocore.config import Config

BASE = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7))


def _load_env():
    envf = BASE / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID", "")
SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
BUCKET = os.environ.get("R2_MEDIA_BUCKET", "media")
CDN_URL = os.environ.get("R2_CDN_URL", "https://cdn.promptedsite.com").rstrip("/")
PREFIX = os.environ.get("R2_PREFIX", "threads")

ENDPOINT = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"

_client = None


def client():
    global _client
    if _client is None:
        if not (ACCOUNT_ID and ACCESS_KEY and SECRET_KEY):
            raise RuntimeError("R2 credential belum lengkap di .env")
        _client = boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            config=Config(signature_version="s3v4", region_name="auto"),
        )
    return _client


def _gen_key(filename):
    ext = Path(filename).suffix.lower() or ".bin"
    stamp = datetime.now(WIB).strftime("%Y%m%d")
    return f"{PREFIX}/{stamp}/{uuid.uuid4().hex[:12]}{ext}"


def upload_bytes(data: bytes, filename: str, content_type: Optional[str] = None):
    """Upload bytes ke R2, return (r2_key, public_url)."""
    key = _gen_key(filename)
    ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    client().put_object(
        Bucket=BUCKET, Key=key, Body=data, ContentType=ct,
        CacheControl="public, max-age=31536000",
    )
    return key, f"{CDN_URL}/{key}"


def upload_file(path):
    p = Path(path)
    return upload_bytes(p.read_bytes(), p.name)


def delete_key(key):
    client().delete_object(Bucket=BUCKET, Key=key)


def ping():
    """Test koneksi: list 1 objek."""
    r = client().list_objects_v2(Bucket=BUCKET, Prefix=f"{PREFIX}/", MaxKeys=1)
    return {"ok": True, "bucket": BUCKET, "endpoint": ENDPOINT, "count": r.get("KeyCount", 0)}


if __name__ == "__main__":
    import json
    print(json.dumps(ping(), indent=2))
