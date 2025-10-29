import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import ClinicMembership
from apps.appointments.models import Appointment, AppointmentStatus, AppointmentSyncState
from apps.calendars.models import CalendarEvent, GoogleCredential
from apps.clinics.models import Clinic, ClinicService, ServiceHours

pytestmark = pytest.mark.django_db


def _create_clinic() -> Clinic:
    return Clinic.objects.create(slug="demo", name="Demo Dental", tz="UTC", default_lang="en")


def _create_service(clinic: Clinic) -> ClinicService:
    service = ClinicService.objects.create(
        clinic=clinic,
        code="clean",
        name="Cleaning",
        duration_minutes=30,
        language="en",
    )
    ServiceHours.objects.create(
        clinic=clinic,
        service=service,
        weekday=timezone.now().astimezone(ZoneInfo(clinic.tz)).weekday(),
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    return service


def _create_patient(clinic: Clinic):
    return clinic.patients.create(
        full_name="Test Patient",
        language="en",
        phone_number="+15555550111",
        normalized_phone="+15555550111",
    )


def _make_user(django_user_model, email: str, role: ClinicMembership.Role, clinic: Clinic):
    user = django_user_model.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="Agent",
        last_name="User",
        is_active=True,
    )
    ClinicMembership.objects.create(user=user, clinic=clinic, role=role)
    return user


def _auth_headers(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _start_iso(clinic: Clinic, minutes_from_now: int = 60) -> str:
    tz = ZoneInfo(clinic.tz)
    start = timezone.now().astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=minutes_from_now)
    start = start.replace(hour=10, minute=0)
    return start.isoformat()


def _set_ip(client, token: int) -> None:
    client.defaults["REMOTE_ADDR"] = f"127.0.0.{token % 250 + 1}"


def _post_json(client, url: str, payload: dict, user, ip_token: int):
    _set_ip(client, ip_token)
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **_auth_headers(user),
    )


@pytest.fixture
def setup_clinic(django_user_model):
    clinic = _create_clinic()
    service = _create_service(clinic)
    patient = _create_patient(clinic)
    staff = _make_user(django_user_model, "staff@example.com", ClinicMembership.Role.STAFF, clinic)
    viewer = _make_user(django_user_model, "viewer@example.com", ClinicMembership.Role.VIEWER, clinic)
    return clinic, service, patient, staff, viewer


def test_appointment_create_success(client, setup_clinic):
    clinic, service, patient, staff, _viewer = setup_clinic
    from apps.accounts import views as appointment_views

    calls = {"count": 0}
    original_scheduler = appointment_views.schedule_google_calendar_retry

    def noop_scheduler(*args, **kwargs):
        calls["count"] += 1
        return True

    appointment_views.schedule_google_calendar_retry = noop_scheduler
    payload = {
        "patient_id": patient.id,
        "service_code": service.code,
        "start_at_iso": _start_iso(clinic),
    }
    try:
        response = _post_json(
            client,
            f"/clinic/{clinic.slug}/appointments/create",
            payload,
            staff,
            ip_token=1,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        appointment = body["data"]["appointment"]
        assert appointment["status"] == AppointmentStatus.BOOKED
        assert appointment["service_code"] == service.code
        assert calls["count"] == 0
    finally:
        appointment_views.schedule_google_calendar_retry = original_scheduler


def test_appointment_create_viewer_forbidden(client, setup_clinic):
    clinic, service, patient, _staff, viewer = setup_clinic
    payload = {
        "patient_id": patient.id,
        "service_code": service.code,
        "start_at_iso": _start_iso(clinic),
    }
    response = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/create",
        payload,
        viewer,
        ip_token=2,
    )
    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "FORBIDDEN"}


def test_appointment_double_booking_return_slot_taken(client, setup_clinic):
    clinic, service, patient, staff, _viewer = setup_clinic
    start_iso = _start_iso(clinic)
    payload = {
        "patient_id": patient.id,
        "service_code": service.code,
        "start_at_iso": start_iso,
    }
    response = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/create",
        payload,
        staff,
        ip_token=3,
    )
    assert response.status_code == 200
    duplicate = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/create",
        payload,
        staff,
        ip_token=4,
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {"ok": False, "error": "SLOT_TAKEN"}


def test_reschedule_updates_google(client, django_user_model, monkeypatch):
    clinic = _create_clinic()
    service = _create_service(clinic)
    patient = _create_patient(clinic)
    staff = _make_user(django_user_model, "agent@example.com", ClinicMembership.Role.ADMIN, clinic)
    GoogleCredential.objects.create(
        clinic=clinic,
        account_email="calendar@example.com",
        access_token="token",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        calendar_id="primary",
    )

    def fake_get_free_busy(self, credential, start, end):
        return []

    created_events = []

    def fake_create_event(self, appointment, credential):
        event, _ = CalendarEvent.objects.update_or_create(
            appointment=appointment,
            defaults={
                "external_event_id": f"evt-{appointment.id}-{len(created_events)}",
                "provider": "google",
                "sync_status": "created",
                "payload": {},
            },
        )
        created_events.append(event.external_event_id)
        return event

    cancel_calls = []

    def fake_cancel_event(self, calendar_event, credential):
        cancel_calls.append(calendar_event.external_event_id)

    monkeypatch.setattr("apps.accounts.views.GoogleCalendarService.get_free_busy", fake_get_free_busy)
    monkeypatch.setattr("apps.accounts.views.GoogleCalendarService.create_event", fake_create_event)
    monkeypatch.setattr("apps.accounts.views.GoogleCalendarService.cancel_event", fake_cancel_event)

    start_iso = _start_iso(clinic)
    create_payload = {
        "patient_id": patient.id,
        "service_code": service.code,
        "start_at_iso": start_iso,
    }
    create_resp = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/create",
        create_payload,
        staff,
        ip_token=5,
    )
    assert create_resp.status_code == 200
    appointment_id = create_resp.json()["data"]["appointment"]["id"]

    new_start_iso = _start_iso(clinic, minutes_from_now=120)
    reschedule_payload = {"id": appointment_id, "new_start_at_iso": new_start_iso}
    reschedule_resp = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/reschedule",
        reschedule_payload,
        staff,
        ip_token=6,
    )
    assert reschedule_resp.status_code == 200
    data = reschedule_resp.json()["data"]["appointment"]
    assert data["external_event_id"].startswith("evt-")
    assert len(cancel_calls) == 1
    appointment = Appointment.objects.get(id=appointment_id)
    appointment.refresh_from_db()
    assert appointment.sync_state == AppointmentSyncState.OK
    assert appointment.google_retry_count == 0


def test_cancel_clears_external_event(client, django_user_model, monkeypatch):
    clinic = _create_clinic()
    service = _create_service(clinic)
    patient = _create_patient(clinic)
    staff = _make_user(django_user_model, "agent@example.com", ClinicMembership.Role.ADMIN, clinic)
    credential = GoogleCredential.objects.create(
        clinic=clinic,
        account_email="calendar@example.com",
        access_token="token",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        calendar_id="primary",
    )

    monkeypatch.setattr("apps.accounts.views.GoogleCalendarService.get_free_busy", lambda *args, **kwargs: [])

    def fake_create_event(self, appointment, cred):
        event, _ = CalendarEvent.objects.update_or_create(
            appointment=appointment,
            defaults={
                "external_event_id": f"evt-{appointment.id}",
                "provider": "google",
                "sync_status": "created",
                "payload": {},
            },
        )
        return event

    monkeypatch.setattr("apps.accounts.views.GoogleCalendarService.create_event", fake_create_event)
    monkeypatch.setattr("apps.accounts.views.GoogleCalendarService.cancel_event", lambda *args, **kwargs: None)

    start_iso = _start_iso(clinic)
    create_payload = {
        "patient_id": patient.id,
        "service_code": service.code,
        "start_at_iso": start_iso,
    }
    create_resp = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/create",
        create_payload,
        staff,
        ip_token=7,
    )
    appointment_id = create_resp.json()["data"]["appointment"]["id"]

    cancel_resp = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/cancel",
        {"id": appointment_id},
        staff,
        ip_token=8,
    )
    assert cancel_resp.status_code == 200
    appointment = Appointment.objects.get(id=appointment_id)
    assert appointment.status == AppointmentStatus.CANCELLED
    assert appointment.external_event_id is None
    assert not CalendarEvent.objects.filter(appointment=appointment).exists()
    assert appointment.sync_state == AppointmentSyncState.OK


def test_google_failure_returns_tentative(client, django_user_model, monkeypatch):
    clinic = _create_clinic()
    service = _create_service(clinic)
    patient = _create_patient(clinic)
    staff = _make_user(django_user_model, "agent@example.com", ClinicMembership.Role.ADMIN, clinic)
    GoogleCredential.objects.create(
        clinic=clinic,
        account_email="calendar@example.com",
        access_token="token",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        calendar_id="primary",
    )

    from apps.accounts.views import GoogleCalendarServiceError

    monkeypatch.setattr("apps.accounts.views.GoogleCalendarService.get_free_busy", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "apps.accounts.views.GoogleCalendarService.create_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(GoogleCalendarServiceError("fail")),
    )
    scheduler_calls = {"count": 0}

    def fake_scheduler(appointment_id, countdown=None):
        scheduler_calls["count"] += 1
        return True

    monkeypatch.setattr("apps.accounts.views.schedule_google_calendar_retry", fake_scheduler)
    monkeypatch.setattr("apps.workers.tasks.schedule_google_calendar_retry", fake_scheduler)
    monkeypatch.setattr("apps.workers.tasks.retry_google_calendar_sync.apply_async", lambda *args, **kwargs: None)

    payload = {
        "patient_id": patient.id,
        "service_code": service.code,
        "start_at_iso": _start_iso(clinic),
    }
    response = _post_json(
        client,
        f"/clinic/{clinic.slug}/appointments/create",
        payload,
        staff,
        ip_token=9,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["error"] == "GOOGLE_TENTATIVE"
    appointment = Appointment.objects.get(id=data["appointment"]["id"])
    assert appointment.status == AppointmentStatus.BOOKED
    assert appointment.sync_state == AppointmentSyncState.TENTATIVE
    assert scheduler_calls["count"] == 1
