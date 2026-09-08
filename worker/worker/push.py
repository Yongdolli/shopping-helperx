"""VAPID 키 생성 (무료). `python -m worker vapid` → .env 에 넣을 값 출력."""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def generate_vapid_keys() -> tuple[str, str]:
    """(public_key, private_key) — 둘 다 base64url. public 은 웹(VITE_VAPID_PUBLIC_KEY), private 은 워커."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64url(public), _b64url(private)
