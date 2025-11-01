"""Authentication backend for HQ support impersonation sessions."""

from __future__ import annotations

from typing import Optional, Tuple

from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication

from apps.accounts.models import SupportSession


class SupportSessionAuthentication(BaseAuthentication):
    """Authenticate requests that already resolved to a support session in middleware."""

    def authenticate(self, request) -> Optional[Tuple[User, SupportSession]]:
        session = getattr(request, "support_session", None)
        if session is None and hasattr(request, "_request"):
            session = getattr(request._request, "support_session", None)
        if session is None:
            return None
        return session.staff_user, session
