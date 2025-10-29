"""Authentication API views."""

from __future__ import annotations

from typing import Any, Dict, List

from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditLog, ClinicMembership
from apps.common.api import error_response, ok_response


def _serialize_user(user: User) -> Dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def _serialize_clinics(user: User) -> List[Dict[str, Any]]:
    memberships = (
        ClinicMembership.objects.select_related("clinic")
        .filter(user=user)
        .order_by("clinic__slug")
    )
    return [
        {
            "slug": membership.clinic.slug,
            "role": membership.role,
        }
        for membership in memberships
    ]


class LoginView(APIView):
    """Handle email/password login using JWT tokens."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: HttpRequest):
        payload = request.data or {}
        email = payload.get("email", "").strip().lower()
        password = payload.get("password", "")
        if not email or not password:
            return error_response("INVALID_CREDENTIALS", status_code=status.HTTP_401_UNAUTHORIZED)

        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password) or not user.is_active:
            AuditLog.objects.create(
                actor_user=user if user else None,
                action="LOGIN_FAILURE",
                scope=AuditLog.Scope.AUTH,
                meta={"user_id": user.id} if user else {},
            )
            return error_response("INVALID_CREDENTIALS", status_code=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        clinics = _serialize_clinics(user)
        staff = getattr(user, "staff_account", None)
        with transaction.atomic():
            AuditLog.objects.create(
                actor_user=user,
                action="LOGIN_SUCCESS",
                scope=AuditLog.Scope.AUTH,
                meta={"user_id": user.id},
            )

        data = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": _serialize_user(user),
            "clinics": clinics,
            "hq_role": staff.role if staff else None,
        }
        return ok_response(data)


class MeView(APIView):
    """Return authenticated user profile and memberships."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: HttpRequest):
        user: User = request.user
        staff = getattr(user, "staff_account", None)
        data = {
            "user": _serialize_user(user),
            "clinics": _serialize_clinics(user),
            "hq_role": staff.role if staff else None,
        }
        return ok_response(data)
