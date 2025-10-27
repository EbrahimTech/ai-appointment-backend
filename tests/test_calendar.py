from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.db import connection
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.calendars.models import CalendarEvent, GoogleCredential
from apps.calendars.services import GoogleCalendarService

pytestmark = pytest.mark.django_db


def make_slot(start):
    return (start, start + timedelta(minutes=30))


def test_calendar_create_cancel(monkeypatch, clinic, clinic_service, patient):
    if connection.vendor != "postgresql":
        pytest.skip("Calendar sync test requires PostgreSQL range support")
    service = GoogleCalendarService()

    post_calls = {}
    delete_calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        post_calls["url"] = url
        post_calls["payload"] = json
        return SimpleNamespace(status_code=200, json=lambda: {"id": "evt-1", "htmlLink": "http://example"})

    def fake_delete(url, headers=None, timeout=None):
        delete_calls["url"] = url
        return SimpleNamespace(status_code=204)

    monkeypatch.setattr("apps.calendars.services.requests.post", fake_post)
    monkeypatch.setattr("apps.calendars.services.requests.delete", fake_delete)

    credential = GoogleCredential.objects.create(
        clinic=clinic,
        account_email="calendar@example.com",
        access_token="token",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        scopes=["scope"],
        calendar_id="primary",
    )

    appointment = Appointment.objects.create(
        clinic=clinic,
        service=clinic_service,
        patient=patient,
        slot=make_slot(timezone.now()),
        status=AppointmentStatus.BOOKED,
    )

    event = service.create_event(appointment, credential)
    assert event.external_event_id == "evt-1"
    assert "calendar" in post_calls["url"]

    service.cancel_event(event, credential)
    event.refresh_from_db()
    assert event.sync_status == "cancelled"
    assert "events/evt-1" in delete_calls["url"]
