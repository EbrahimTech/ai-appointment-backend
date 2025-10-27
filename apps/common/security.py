"""Utility helpers for encryption and secret handling."""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from cryptography.fernet import Fernet, InvalidToken

_ENCRYPTION_PREFIX = "enc::"


def _derive_key(source: str) -> bytes:
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    secret = settings.ENCRYPTION_KEY
    if not secret:
        raise ImproperlyConfigured("ENCRYPTION_KEY is required for secret storage")
    key = _derive_key(secret)
    return Fernet(key)


def is_encrypted_secret(value: Optional[str]) -> bool:
    return bool(value and value.startswith(_ENCRYPTION_PREFIX))


def encrypt_secret(value: str) -> str:
    if not value:
        return value
    if is_encrypted_secret(value):
        return value
    fernet = _get_fernet()
    token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENCRYPTION_PREFIX}{token}"


def decrypt_secret(value: Optional[str]) -> str:
    if not value:
        return ""
    if not is_encrypted_secret(value):
        return value
    token = value[len(_ENCRYPTION_PREFIX):]
    fernet = _get_fernet()
    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ImproperlyConfigured("Failed to decrypt secret") from exc
