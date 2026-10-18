"""Small S3 Signature V4 client for local MinIO, using the existing HTTP client."""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import quote
import httpx


def request(method, name="", data=b""):
    host = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    access = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    secret = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    date = datetime.now(timezone.utc)
    stamp, day = date.strftime("%Y%m%dT%H%M%SZ"), date.strftime("%Y%m%d")
    path = quote("/recordings" + ("/" + name if name else ""), safe="/~")
    digest = hashlib.sha256(data).hexdigest()
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{digest}\nx-amz-date:{stamp}\n"
    canonical_request = "\n".join((method, path, "", canonical_headers, signed_headers, digest))
    scope = f"{day}/us-east-1/s3/aws4_request"
    to_sign = f"AWS4-HMAC-SHA256\n{stamp}\n{scope}\n" + hashlib.sha256(canonical_request.encode()).hexdigest()
    key = ("AWS4" + secret).encode()
    for value in (day, "us-east-1", "s3", "aws4_request"):
        key = hmac.new(key, value.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    authorization = f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"
    return httpx.request(method, f"http://{host}{path}", content=data, timeout=15,
                         headers={"Authorization": authorization, "x-amz-date": stamp, "x-amz-content-sha256": digest})


def upload(name, data):
    bucket = request("HEAD")
    if bucket.status_code == 404:
        response = request("PUT")
        if response.status_code not in (200, 409):
            response.raise_for_status()
    else:
        bucket.raise_for_status()
    response = request("PUT", name, data)
    response.raise_for_status()


def download(name):
    response = request("GET", name)
    response.raise_for_status()
    return response.content
