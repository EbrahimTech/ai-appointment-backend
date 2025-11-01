"""Request middleware enforcing clinic scoping."""

from __future__ import annotations

from typing import Callable, Optional

from django.http import JsonResponse
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from apps.accounts.models import AuditLog, ClinicMembership, SupportSession
from apps.accounts.support import hash_support_token


class ClinicScopeMiddleware:
    """Authenticate requests to /clinic/<slug>/... and attach membership context."""

    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.jwt_authenticator = JWTAuthentication()

    def __call__(self, request):
        path = request.path
        if not path.startswith("/clinic/"):
            return self.get_response(request)

        slug = self._extract_slug(path)
        if not slug:
            return JsonResponse({"ok": False, "error": "FORBIDDEN"}, status=403)

        token = self._get_bearer_token(request)
        support_session = self._resolve_support_session(token) if token else None
        if support_session:
            return self._handle_support_session(request, support_session, slug)

        return self._handle_standard_auth(request, slug)

    def _handle_standard_auth(self, request, slug: str):
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

    def _handle_support_session(self, request, session: SupportSession, slug: str):
        if session.clinic.slug != slug:
            self._audit_support_request(session, request, allowed=False, status_code=403)
            return JsonResponse({"ok": False, "error": "FORBIDDEN"}, status=403)

        if not session.is_active():
            self._deactivate_session(session)
            self._audit_support_request(session, request, allowed=False, status_code=401)
            return JsonResponse({"ok": False, "error": "UNAUTHORIZED"}, status=401)

        if not self._support_allowed(request, slug):
            self._audit_support_request(session, request, allowed=False, status_code=403)
            return JsonResponse({"ok": False, "error": "FORBIDDEN"}, status=403)

        request.user = session.staff_user
        membership = ClinicMembership(
            clinic=session.clinic,
            user=session.staff_user,
            role=ClinicMembership.Role.ADMIN,
        )
        request.clinic_membership = membership
        request.clinic = session.clinic
        request.support_session = session

        try:
            response = self.get_response(request)
        except Exception:
            self._audit_support_request(session, request, allowed=True, status_code=500)
            raise

        self._audit_support_request(session, request, allowed=True, status_code=getattr(response, "status_code", 200))
        return response

    @staticmethod
    def _get_bearer_token(request) -> Optional[str]:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return None
        return auth_header.split(" ", 1)[1].strip()

    @staticmethod
    def _extract_slug(path: str) -> Optional[str]:
        parts = path.split("/")
        if len(parts) >= 3 and parts[2]:
            return parts[2]
        return None

    @staticmethod
    def _support_allowed(request, slug: str) -> bool:
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return True
        if (
            request.method == "POST"
            and request.path.startswith(f"/clinic/{slug}/conversations/")
            and request.path.endswith("/reply")
        ):
            return True
        return False

    @staticmethod
    def _deactivate_session(session: SupportSession):
        if session.active:
            session.active = False
            session.ended_at = timezone.now()
            session.save(update_fields=["active", "ended_at", "updated_at"])

    def _resolve_support_session(self, token: str) -> Optional[SupportSession]:
        token_hash = hash_support_token(token)
        return (
            SupportSession.objects.select_related("clinic", "staff_user")
            .filter(token_hash=token_hash, active=True)
            .first()
        )

    @staticmethod
    def _audit_support_request(session: SupportSession, request, *, allowed: bool, status_code: int):
        AuditLog.objects.create(
            actor_user=session.staff_user,
            action="SUPPORT_SESSION_REQUEST",
            scope=AuditLog.Scope.CLINIC,
            clinic=session.clinic,
            meta={
                "impersonation": True,
                "clinic_slug": session.clinic.slug,
                "path": request.path,
                "method": request.method,
                "allowed": allowed,
                "status": status_code,
            },
        )
