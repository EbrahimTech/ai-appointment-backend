"""Google Calendar OAuth endpoints."""

from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.calendars.services import GoogleCalendarService, GoogleCalendarServiceError
from apps.common.utils import minimal_ok

service = GoogleCalendarService()


@require_GET
def google_oauth_start(request: HttpRequest) -> JsonResponse:
    clinic_id = request.GET.get("clinic")
    if not clinic_id:
        return JsonResponse({"ok": False, "error": "clinic required"}, status=400)
    url = service.get_authorization_url(int(clinic_id))
    return minimal_ok(url=url)


@require_GET
def google_oauth_callback(request: HttpRequest) -> JsonResponse:
    code = request.GET.get("code")
    state_raw = request.GET.get("state")
    if not code or not state_raw:
        return JsonResponse({"ok": False, "error": "missing params"}, status=400)

    state = json.loads(state_raw)
    clinic_id = state.get("clinic_id")
    try:
        service.exchange_code(int(clinic_id), code)
    except GoogleCalendarServiceError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return minimal_ok()
