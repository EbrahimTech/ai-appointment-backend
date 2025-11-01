"""Helpers for HQ support impersonation sessions."""

from __future__ import annotations

import hashlib


def hash_support_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
