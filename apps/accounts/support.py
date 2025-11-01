"""Helpers for HQ support impersonation sessions and invitations."""

from __future__ import annotations

import hashlib
from django.core import signing

INVITE_SALT = "clinic-invite-token"


def hash_support_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign_invitation_token(uid: str) -> str:
    return signing.dumps({"invite_id": uid}, salt=INVITE_SALT)


def verify_invitation_token(token: str) -> str:
    payload = signing.loads(token, salt=INVITE_SALT)
    invite_id = payload.get("invite_id")
    if not invite_id:
        raise signing.BadSignature("invite_id missing")
    return invite_id
