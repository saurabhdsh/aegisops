"""Encrypt connector secrets with the process APP_SECRET. The database stores ciphertext only."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def _key(app_secret: str) -> bytes:
    return hashlib.sha256(app_secret.encode("utf-8")).digest()


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    produced = 0
    while produced < length:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        blocks.append(block)
        produced += len(block)
        counter += 1
    return b"".join(blocks)[:length]


def seal(plaintext: str, app_secret: str) -> str:
    key = _key(app_secret)
    nonce = secrets.token_bytes(16)
    body = plaintext.encode("utf-8")
    tag = hmac.new(key, nonce + body, hashlib.sha256).digest()
    cipher = bytes(left ^ right for left, right in zip(body, _stream(key, nonce, len(body)), strict=True))
    return (nonce + tag + cipher).hex()


def open_secret(blob: str, app_secret: str) -> str:
    if not blob:
        return ""
    raw = bytes.fromhex(blob)
    if len(raw) < 48:
        raise ValueError("secret could not be decrypted")
    nonce, tag, cipher = raw[:16], raw[16:48], raw[48:]
    key = _key(app_secret)
    body = bytes(left ^ right for left, right in zip(cipher, _stream(key, nonce, len(cipher)), strict=True))
    expected = hmac.new(key, nonce + body, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("secret could not be decrypted")
    return body.decode("utf-8")
