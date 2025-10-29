from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import List
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.calendars.models import GoogleCredential
from apps.calendars.services import GoogleCalendarService, GoogleCalendarServiceError
from apps.clinics.models import ClinicService


@dataclass
class SuggestedSlot:
    start: datetime
    end: datetime
    tentative: bool = False
    source: str = "local"


def suggest_slots(clinic, *, service: ClinicService | None = None, count: int = 2) -> List[SuggestedSlot]:
    service = service or clinic.services.filter(is_active=True).order_by("duration_minutes").first()
    if not service:
        return []

    tz = ZoneInfo(clinic.tz or "UTC")
    now = timezone.now().astimezone(tz)
    search_end = now + timedelta(days=7)

    busy_windows, calendar_failed = _fetch_busy_windows(clinic, now, search_end)

    suggestions: list[SuggestedSlot] = []
    for day_offset in range(0, 7):
        target_date = (now + timedelta(days=day_offset)).date()
        weekday = target_date.weekday()
        day_hours = service.hours.filter(weekday=weekday).order_by("start_time")
        for hours in day_hours:
            start_dt = datetime.combine(target_date, hours.start_time, tzinfo=tz)
            end_window = datetime.combine(target_date, hours.end_time, tzinfo=tz)
            duration = timedelta(minutes=service.duration_minutes)
            slot_start = max(start_dt, now)
            while slot_start + duration <= end_window:
                if _is_available(clinic, service, slot_start, duration, busy_windows):
                    suggestions.append(
                        SuggestedSlot(
                            start=slot_start,
                            end=slot_start + duration,
                            tentative=calendar_failed,
                            source="google" if not calendar_failed else "local",
                        )
                    )
                    if len(suggestions) >= count:
                        return suggestions
                slot_start += duration
    return suggestions


def _is_available(clinic, service, start: datetime, duration: timedelta, busy_windows) -> bool:
    start_utc = start.astimezone(timezone.utc)
    end_utc = (start + duration).astimezone(timezone.utc)
    overlap = Appointment.objects.filter(
        clinic=clinic,
        service=service,
        status__in=[AppointmentStatus.PENDING, AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED],
        slot__overlap=(start_utc, end_utc),
    ).exists()
    if overlap:
        return False
    for busy_start, busy_end in busy_windows:
        if start < busy_end and (start + duration) > busy_start:
            return False
    return True


def _fetch_busy_windows(clinic, start: datetime, end: datetime):
    credential = (
        GoogleCredential.objects.filter(clinic=clinic).order_by("-updated_at").first()
    )
    if not credential:
        return [], False
    service = GoogleCalendarService()
    try:
        windows = service.get_free_busy(credential, start, end)
        return windows, False
    except GoogleCalendarServiceError:
        return [], True
