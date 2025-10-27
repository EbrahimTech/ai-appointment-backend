"""Utility helpers shared across apps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from django.http import JsonResponse
from django.utils import timezone


def now_utc():
    """Return timezone-aware UTC now."""
    return timezone.now()


def minimal_ok(**extra: Any) -> JsonResponse:
    """Return the default JSON envelope enforced by the API spec."""
    payload: Dict[str, Any] = {"ok": True}
    payload.update(extra)
    return JsonResponse(payload)


@dataclass(slots=True)
class ServiceResult:
    """Lightweight service outcome container."""

    ok: bool = True
    message: str | None = None
    data: dict | None = None
