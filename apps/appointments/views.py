"""Appointment API endpoints."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.appointments.models import Appointment
from apps.common.utils import minimal_ok


@require_GET
def appointments_today(request: HttpRequest) -> JsonResponse:
    today = date.today()
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(today, time.min), tz)
    end = start + timedelta(days=1)

    qs = Appointment.objects.filter(slot__overlap=(start, end))
    clinic_id = request.GET.get("clinic")
    if clinic_id:
        qs = qs.filter(clinic_id=clinic_id)

    data = [
        {
            "id": appt.id,
            "clinic": appt.clinic_id,
            "patient": appt.patient_id,
            "service": appt.service_id,
            "status": appt.status,
            "start": appt.slot.lower.isoformat() if appt.slot else None,
            "end": appt.slot.upper.isoformat() if appt.slot else None,
        }
        for appt in qs.select_related("clinic", "patient", "service")
    ]
    return minimal_ok(appointments=data)
