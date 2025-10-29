"""Google Calendar integration helpers."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Dict, Tuple
from uuid import uuid4

import requests
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.calendars.models import CalendarEvent, GoogleCredential


class GoogleCalendarServiceError(RuntimeError):
    """Raised when Google Calendar integration fails."""


class GoogleCalendarService:
    """Wrapper around Google Calendar REST API."""

    OAUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    CALENDAR_API = "https://www.googleapis.com/calendar/v3"

    def get_authorization_url(self, clinic_id: int) -> str:
        client_id = settings.GOOGLE_CLIENT_ID
        redirect_uri = settings.GOOGLE_REDIRECT_URI
        scopes = "https://www.googleapis.com/auth/calendar"
        state = json.dumps({"clinic_id": clinic_id, "nonce": str(uuid4())})
        return (
            f"{self.OAUTH_URL}?response_type=code&client_id={client_id}"
            f"&redirect_uri={redirect_uri}&scope={scopes}&access_type=offline&prompt=consent"
            f"&state={state}"
        )

    def exchange_code(self, clinic_id: int, code: str) -> GoogleCredential:
        payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        response = requests.post(self.TOKEN_URL, data=payload, timeout=15)
        if response.status_code >= 400:
            raise GoogleCalendarServiceError(response.text)
        data = response.json()
        expires_at = timezone.now() + timedelta(seconds=data.get("expires_in", 3600))
        credential, _ = GoogleCredential.objects.update_or_create(
            clinic_id=clinic_id,
            account_email=data.get("email", "calendar@unknown"),
            defaults={
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", ""),
                "expires_at": expires_at,
                "calendar_id": settings.GOOGLE_CALENDAR_ID if hasattr(settings, "GOOGLE_CALENDAR_ID") else "primary",
                "scopes": ["https://www.googleapis.com/auth/calendar"],
                "last_error": "",
                "last_error_at": None,
                "last_free_busy_at": timezone.now(),
            },
        )
        return credential

    def create_event(self, appointment: Appointment, credential: GoogleCredential) -> CalendarEvent:
        payload = self._appointment_to_payload(appointment)
        headers = {"Authorization": f"Bearer {credential.get_access_token()}", "Content-Type": "application/json"}
        response = requests.post(
            f"{self.CALENDAR_API}/calendars/{credential.calendar_id}/events",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if response.status_code >= 400:
            credential.last_error = response.text
            credential.last_error_at = timezone.now()
            credential.save(update_fields=["last_error", "last_error_at", "updated_at"])
            raise GoogleCalendarServiceError(response.text)
        data = response.json()
        calendar_event, _ = CalendarEvent.objects.update_or_create(
            appointment=appointment,
            defaults={
                "external_event_id": data.get("id"),
                "provider": "google",
                "sync_status": "created",
                "payload": data,
            },
        )
        credential.last_error = ""
        credential.last_error_at = None
        credential.save(update_fields=["last_error", "last_error_at", "updated_at"])
        return calendar_event

    def cancel_event(self, calendar_event: CalendarEvent, credential: GoogleCredential) -> None:
        headers = {"Authorization": f"Bearer {credential.get_access_token()}", "Content-Type": "application/json"}
        response = requests.delete(
            f"{self.CALENDAR_API}/calendars/{credential.calendar_id}/events/{calendar_event.external_event_id}",
            headers=headers,
            timeout=15,
        )
        if response.status_code >= 400 and response.status_code != 410:
            credential.last_error = response.text
            credential.last_error_at = timezone.now()
            credential.save(update_fields=["last_error", "last_error_at", "updated_at"])
            raise GoogleCalendarServiceError(response.text)
        calendar_event.sync_status = "cancelled"
        calendar_event.save(update_fields=["sync_status", "updated_at"])
        credential.last_error = ""
        credential.last_error_at = None
        credential.save(update_fields=["last_error", "last_error_at", "updated_at"])

    def get_free_busy(
        self,
        credential: GoogleCredential,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """Fetch busy windows for the credential's calendar."""

        headers = {
            "Authorization": f"Bearer {credential.get_access_token()}",
            "Content-Type": "application/json",
        }
        payload = {
            "timeMin": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeMax": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeZone": credential.clinic.tz if hasattr(credential, "clinic") else "UTC",
            "items": [{"id": credential.calendar_id}],
        }
        response = requests.post(
            f"{self.CALENDAR_API}/freeBusy",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if response.status_code >= 400:
            raise GoogleCalendarServiceError(response.text)
        if response.status_code >= 400:
            credential.last_error = response.text
            credential.last_error_at = timezone.now()
            credential.save(update_fields=["last_error", "last_error_at", "updated_at"])
            raise GoogleCalendarServiceError(response.text)
        busy_data = response.json().get("calendars", {}).get(credential.calendar_id, {}).get("busy", [])
        windows: list[tuple[datetime, datetime]] = []
        for entry in busy_data:
            start_str = entry.get("start")
            end_str = entry.get("end")
            if not start_str or not end_str:
                continue
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")).astimezone(timezone.utc)
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00")).astimezone(timezone.utc)
            windows.append((start_dt, end_dt))
        credential.last_free_busy_at = timezone.now()
        credential.last_error = ""
        credential.last_error_at = None
        credential.save(update_fields=["last_free_busy_at", "last_error", "last_error_at", "updated_at"])
        return windows

    def _appointment_to_payload(self, appointment: Appointment) -> Dict[str, Any]:
        attendees = []
        if appointment.patient and appointment.patient.email:
            attendees.append({"email": appointment.patient.email})

        return {
            "summary": appointment.service.name if appointment.service else "Dental appointment",
            "description": appointment.notes,
            "start": {
                "dateTime": appointment.slot.lower.isoformat(),
                "timeZone": appointment.clinic.tz,
            },
            "end": {
                "dateTime": appointment.slot.upper.isoformat(),
                "timeZone": appointment.clinic.tz,
            },
            "attendees": attendees,
        }
