"""Decorators enforcing clinic and HQ role access."""

from __future__ import annotations

from functools import wraps
from typing import Callable, Iterable, Optional

from django.http import HttpRequest, JsonResponse

from apps.accounts.models import ClinicMembership, StaffAccount

try:
    from rest_framework.request import Request as DRFRequest
except ModuleNotFoundError:  # pragma: no cover - rest_framework always installed
    DRFRequest = None


def _resolve_request(args) -> Optional[object]:
    for arg in args:
        if isinstance(arg, HttpRequest):
            return arg
        if DRFRequest and isinstance(arg, DRFRequest):
            return arg
    return None


def _extract_attribute(request_obj, name: str):
    if request_obj is None:
        return None
    value = getattr(request_obj, name, None)
    if value is None and hasattr(request_obj, "_request"):
        value = getattr(request_obj._request, name, None)
    return value


def require_clinic_role(allowed: Iterable[str]):
    """Ensure the caller has an allowed ClinicMembership role."""

    allowed_set = set(allowed)

    def decorator(view_func: Callable):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            request = _resolve_request(args[:2])
            membership = _extract_attribute(request, "clinic_membership")
            if membership is None or membership.role not in allowed_set:
                return JsonResponse({"ok": False, "error": "FORBIDDEN"}, status=403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def require_hq_role(allowed: Iterable[str] | None = None):
    """Ensure the caller has an HQ StaffAccount with an allowed role."""

    allowed_set = set(allowed or [StaffAccount.Role.SUPERADMIN, StaffAccount.Role.OPS])

    def decorator(view_func: Callable):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            request = _resolve_request(args[:2])
            user = _extract_attribute(request, "user")
            if not user:
                return JsonResponse({"ok": False, "error": "UNAUTHORIZED"}, status=401)
            staff = getattr(user, "staff_account", None)
            if staff is None or staff.role not in allowed_set:
                return JsonResponse({"ok": False, "error": "FORBIDDEN"}, status=403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
