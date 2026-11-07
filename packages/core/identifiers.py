"""Prefixed identifiers. The prefix is for operators; uniqueness comes from UUID4."""

from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    if not prefix or not prefix.isascii() or any(ch not in "abcdefghijklmnopqrstuvwxyz" for ch in prefix):
        raise ValueError("identifier prefix must be lowercase ascii")
    return f"{prefix}_{uuid4().hex}"
