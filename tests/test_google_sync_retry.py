from datetime import timedelta

import pytest
from django.utils import timezone

from apps.appointments.models import (
    Appointment,
    AppointmentStatus,
    AppointmentSyncState,
)
from apps.calendars.models import GoogleCredential
from apps.clinics.models import Clinic, ClinicService
from apps.calendars.services import GoogleCalendarServiceError
from apps.workers.tasks import (
    GOOGLE_SYNC_INITIAL_DELAY,
    retry_google_calendar_sync,
    schedule_google_calendar_retry,
)

pytestmark = pytest.mark.django_db


def _create_appointment(sync_state=AppointmentSyncState.TENTATIVE):
    clinic = Clinic.objects.create(slug="clinic", name="Clinic", tz="UTC", default_lang="en")
    service = ClinicService.objects.create(
        clinic=clinic,
        code="clean",
        name="Cleaning",
        duration_minutes=30,
        language="en",
    )
    appointment = Appointment.objects.create(
        clinic=clinic,
        service=service,
        slot=(timezone.now(), timezone.now() + timedelta(minutes=30)),
        status=AppointmentStatus.BOOKED,
        sync_state=sync_state,
    )
    return appointment


def test_retry_promotes_tentative_to_ok(monkeypatch):
    appointment = _create_appointment()
    GoogleCredential.objects.create(
        clinic=appointment.clinic,
        account_email="calendar@example.com",
        access_token="token",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        calendar_id="primary",
    )

    class DummyEvent:
        def __init__(self, appointment_id):
            self.external_event_id = f"evt-{appointment_id}"

    monkeypatch.setattr(
        "apps.workers.tasks.GoogleCalendarService.create_event",
        lambda self, appt, cred: DummyEvent(appt.id),
    )

    result = retry_google_calendar_sync.run(appointment.id)
    appointment.refresh_from_db()
    assert result == "synced"
    assert appointment.sync_state == AppointmentSyncState.OK
    assert appointment.external_event_id.startswith("evt-")
    assert appointment.google_retry_count == 0
    assert appointment.google_last_error == ""


def test_retry_backoff_and_failure(monkeypatch, settings):
    appointment = _create_appointment()
    GoogleCredential.objects.create(
        clinic=appointment.clinic,
        account_email="calendar@example.com",
        access_token="token",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        calendar_id="primary",
    )

    attempts = []

    def failing_create_event(self, appt, cred):
        attempts.append(appt.id)
        raise GoogleCalendarServiceError("transient")

    monkeypatch.setattr(
        "apps.workers.tasks.GoogleCalendarService.create_event",
        failing_create_event,
    )
    monkeypatch.setattr("apps.workers.tasks.GOOGLE_SYNC_MAX_ATTEMPTS", 2, raising=False)

    applied = []

    def fake_apply_async(args=None, countdown=None, task_id=None):
        applied.append((args, countdown, task_id))

    monkeypatch.setattr("apps.workers.tasks.retry_google_calendar_sync.apply_async", fake_apply_async)

    result = retry_google_calendar_sync.run(appointment.id)
    appointment.refresh_from_db()
    assert result == "rescheduled"
    assert appointment.sync_state == AppointmentSyncState.TENTATIVE
    assert appointment.google_retry_count == 1
    assert applied and applied[0][1] == GOOGLE_SYNC_INITIAL_DELAY

    # second attempt should mark failed
    result2 = retry_google_calendar_sync.run(appointment.id)
    appointment.refresh_from_db()
    assert result2 == "failed"
    assert appointment.sync_state == AppointmentSyncState.FAILED
    assert appointment.google_retry_count == 2


def test_schedule_google_calendar_retry_idempotent(monkeypatch, settings):
    appointment = _create_appointment()

    calls = []

    def fake_apply_async(args=None, countdown=None, task_id=None):
        calls.append(task_id)

    monkeypatch.setattr("apps.workers.tasks.retry_google_calendar_sync.apply_async", fake_apply_async)

    first = schedule_google_calendar_retry(appointment.id, countdown=10)
    second = schedule_google_calendar_retry(appointment.id, countdown=10)

    assert first is True
    assert second is False
    assert calls == [f"appt-google-sync-{appointment.id}-initial"]
