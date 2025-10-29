"""Common DRF helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import exception_handler as drf_exception_handler


def ok_response(data: Dict[str, Any] | Iterable[Any], status_code: int = status.HTTP_200_OK) -> Response:
    """Return a standardized success envelope."""

    return Response({"ok": True, "data": data}, status=status_code)


def error_response(message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    """Return a standardized error envelope."""

    return Response({"ok": False, "error": message}, status=status_code)


def exception_handler(exc, context):
    """Ensure DRF errors follow the {ok:false,error:...} contract."""

    response = drf_exception_handler(exc, context)
    if response is None:
        return response
    data = response.data
    message: Any
    if isinstance(data, dict):
        message = data.get("detail") or data.get("message") or "ERROR"
    else:
        message = "ERROR"
    response.data = {"ok": False, "error": str(message)}
    return response


class WriteRateThrottle(SimpleRateThrottle):
    """Limit write requests per client IP."""

    scope = "write"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        ident = self.get_ident(request)
        if ident is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}
