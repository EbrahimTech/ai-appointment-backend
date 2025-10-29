"""Request middleware enforcing clinic scoping."""

from __future__ import annotations

from typing import Callable

from django.http import JsonResponse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from apps.accounts.models import ClinicMembership


class ClinicScopeMiddleware:
    """Authenticate requests to /clinic/<slug>/... and attach membership context."""

    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.jwt_authenticator = JWTAuthentication()

    def __call__(self, request):
        path = request.path
        if path.startswith("/clinic/"):
            slug = self._extract_slug(path)
            if not slug:
                return JsonResponse({"ok": False, "error": "FORBIDDEN"}, status=403)

            try:
                auth_result = self.jwt_authenticator.authenticate(request)
            except (AuthenticationFailed, InvalidToken):
                return JsonResponse({"ok": False, "error": "UNAUTHORIZED"}, status=401)

            if auth_result is None:
                return JsonResponse({"ok": False, "error": "UNAUTHORIZED"}, status=401)

            user, _token = auth_result
            request.user = user
            membership = (
                ClinicMembership.objects.select_related("clinic")
                .filter(user=user, clinic__slug=slug)
                .first()
            )
            if membership is None:
                return JsonResponse({"ok": False, "error": "FORBIDDEN"}, status=403)

            request.clinic_membership = membership
            request.clinic = membership.clinic

        return self.get_response(request)

    @staticmethod
    def _extract_slug(path: str) -> str | None:
        parts = path.split("/")
        if len(parts) >= 3 and parts[2]:
            return parts[2]
        return None
