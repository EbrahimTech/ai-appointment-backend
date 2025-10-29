from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import ClinicMembership, StaffAccount
from apps.appointments.models import Appointment, AppointmentStatus, AppointmentSyncState
from apps.channels.models import OutboxMessage, OutboxStatus
from apps.clinics.models import Clinic, ClinicService
from apps.conversations.models import Conversation, ConversationMessage, MessageDirection
from apps.patients.models import Patient

pytestmark = pytest.mark.django_db


def _make_user(django_user_model, email="owner@example.com"):
    return django_user_model.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="Owner",
        last_name="User",
        is_active=True,
    )


def _auth_headers(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _create_patient(clinic, phone="+15555550111", language="en"):
    return Patient.objects.create(
        clinic=clinic,
        full_name="Test Patient",
        language=language,
        phone_number=phone,
        normalized_phone=phone,
    )


def _create_service(clinic, code="clean"):
    return ClinicService.objects.create(
        clinic=clinic,
        code=code,
        name="Cleaning",
        duration_minutes=30,
        description="",
        language="en",
    )


def _create_conversation(clinic, patient, dedupe_key, *, fsm_state="idle", handoff=False, intent=""):
    return Conversation.objects.create(
        clinic=clinic,
        patient=patient,
        dedupe_key=dedupe_key,
        fsm_state=fsm_state,
        handoff_required=handoff,
        last_intent=intent,
    )


def _add_message(conversation, direction, body, created_at):
    message = ConversationMessage.objects.create(
        conversation=conversation,
        direction=direction,
        language="en",
        body=body,
    )
    ConversationMessage.objects.filter(pk=message.pk).update(
        created_at=created_at, updated_at=created_at
    )
    return message


def test_clinic_dashboard_returns_metrics_for_member(client, django_user_model):
    user = _make_user(django_user_model)
    clinic = Clinic.objects.create(slug="demo-dental", name="Demo Dental", tz="Europe/Istanbul")
    ClinicMembership.objects.create(
        user=user,
        clinic=clinic,
        role=ClinicMembership.Role.ADMIN,
    )

    conversation = Conversation.objects.create(
        clinic=clinic,
        dedupe_key="conv-1",
        handoff_required=False,
    )
    base_time = timezone.now()
    Conversation.objects.filter(pk=conversation.pk).update(
        created_at=base_time, updated_at=base_time
    )

    inbound = ConversationMessage.objects.create(
        conversation=conversation,
        direction=MessageDirection.INBOUND,
        language="en",
        body="Hello",
    )
    ConversationMessage.objects.filter(pk=inbound.pk).update(
        created_at=base_time, updated_at=base_time
    )

    outbound = ConversationMessage.objects.create(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        language="en",
        body="Hi there!",
    )
    outbound_time = base_time + timedelta(seconds=5)
    ConversationMessage.objects.filter(pk=outbound.pk).update(
        created_at=outbound_time, updated_at=outbound_time
    )

    failed = OutboxMessage.objects.create(
        clinic=clinic,
        conversation=conversation,
        scheduled_for=base_time,
        status=OutboxStatus.FAILED,
    )
    OutboxMessage.objects.filter(pk=failed.pk).update(
        created_at=base_time, updated_at=base_time
    )

    sent = OutboxMessage.objects.create(
        clinic=clinic,
        conversation=conversation,
        scheduled_for=base_time,
        status=OutboxStatus.SENT,
    )
    OutboxMessage.objects.filter(pk=sent.pk).update(
        created_at=base_time, updated_at=base_time
    )

    Appointment.objects.create(
        clinic=clinic,
        patient=None,
        service=None,
        slot=(base_time, base_time + timedelta(minutes=30)),
        status=AppointmentStatus.BOOKED,
        sync_state=AppointmentSyncState.TENTATIVE,
    )

    response = client.get(f"/clinic/{clinic.slug}/dashboard", **_auth_headers(user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert set(data.keys()) == {
        "conversations_today",
        "bookings_today",
        "ttfr_p95_ms",
        "handoff_today",
        "delivery_fail_rate",
        "tentative_today",
        "tentative_count",
        "failed_count",
    }
    assert data["conversations_today"] == 1
    assert data["bookings_today"] == 1
    assert data["ttfr_p95_ms"] == 5000
    assert data["handoff_today"] == 0
    assert data["delivery_fail_rate"] == 0.5
    assert data["tentative_today"] == 1
    assert data["tentative_count"] == 1
    assert data["failed_count"] == 0


def test_clinic_dashboard_forbidden_without_membership(client, django_user_model):
    user = _make_user(django_user_model)
    clinic = Clinic.objects.create(slug="demo-dental", name="Demo Dental", tz="Europe/Istanbul")

    response = client.get(f"/clinic/{clinic.slug}/dashboard", **_auth_headers(user))
    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "FORBIDDEN"}


def test_clinic_dashboard_forbidden_for_wrong_slug(client, django_user_model):
    user = _make_user(django_user_model)
    clinic = Clinic.objects.create(slug="demo-dental", name="Demo Dental", tz="Europe/Istanbul")
    ClinicMembership.objects.create(
        user=user,
        clinic=clinic,
        role=ClinicMembership.Role.VIEWER,
    )

    response = client.get("/clinic/other-clinic/dashboard", **_auth_headers(user))
    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "FORBIDDEN"}


def test_hq_endpoints_require_staff_role(client, django_user_model):
    user = _make_user(django_user_model, email="superadmin@example.com")
    StaffAccount.objects.create(user=user, role=StaffAccount.Role.SUPERADMIN)
    Clinic.objects.create(slug="demo-dental", name="Demo Dental", tz="Europe/Istanbul")

    headers = _auth_headers(user)
    metrics = client.get("/hq/metrics/summary", **headers)
    assert metrics.status_code == 200
    assert metrics.json()["ok"] is True

    tenants = client.get("/hq/tenants", **headers)
    assert tenants.status_code == 200
    tenants_payload = tenants.json()
    assert tenants_payload["ok"] is True
    assert tenants_payload["data"]["page"] == 1
    assert tenants_payload["data"]["size"] == 20
    assert "items" in tenants_payload["data"]


def test_hq_endpoints_forbidden_for_non_staff(client, django_user_model):
    user = _make_user(django_user_model, email="regular@example.com")

    headers = _auth_headers(user)
    metrics = client.get("/hq/metrics/summary", **headers)
    assert metrics.status_code == 403
    assert metrics.json() == {"ok": False, "error": "FORBIDDEN"}


def test_hq_endpoints_forbidden_for_disallowed_role(client, django_user_model):
    user = _make_user(django_user_model, email="support@example.com")
    StaffAccount.objects.create(user=user, role=StaffAccount.Role.SUPPORT)

    headers = _auth_headers(user)
    response = client.get("/hq/tenants", **headers)
    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "FORBIDDEN"}


def test_conversations_list_filters(client, django_user_model):
    user = _make_user(django_user_model, email="agent@example.com")
    clinic = Clinic.objects.create(slug="demo-dental", name="Demo Dental", tz="Europe/Istanbul")
    ClinicMembership.objects.create(user=user, clinic=clinic, role=ClinicMembership.Role.STAFF)

    patient_en = _create_patient(clinic, phone="+15555550100", language="en")
    patient_ar = _create_patient(clinic, phone="+966511234567", language="ar")

    now = timezone.now()

    conv_open = _create_conversation(
        clinic,
        patient_en,
        "conv-open",
        fsm_state="qualification",
        handoff=False,
        intent="booking",
    )
    Conversation.objects.filter(pk=conv_open.pk).update(
        created_at=now - timedelta(hours=2), updated_at=now - timedelta(hours=1)
    )
    _add_message(
        conv_open,
        MessageDirection.INBOUND,
        "Need a polish tomorrow",
        created_at=now - timedelta(hours=2),
    )
    _add_message(
        conv_open,
        MessageDirection.OUTBOUND,
        "Sure, let's see slots",
        created_at=now - timedelta(hours=1, minutes=55),
    )

    conv_handoff = _create_conversation(
        clinic,
        patient_ar,
        "conv-handoff",
        fsm_state="qualification",
        handoff=True,
        intent="emergency",
    )
    Conversation.objects.filter(pk=conv_handoff.pk).update(
        created_at=now - timedelta(days=2), updated_at=now - timedelta(days=1, hours=12)
    )
    _add_message(
        conv_handoff,
        MessageDirection.INBOUND,
        "حالة طارئة ألم شديد",
        created_at=now - timedelta(days=2),
    )

    conv_resolved = _create_conversation(
        clinic,
        patient_en,
        "conv-resolved",
        fsm_state="done",
        handoff=False,
        intent="followup",
    )
    Conversation.objects.filter(pk=conv_resolved.pk).update(
        created_at=now - timedelta(hours=12), updated_at=now - timedelta(hours=10)
    )
    _add_message(
        conv_resolved,
        MessageDirection.INBOUND,
        "Thanks for the visit",
        created_at=now - timedelta(hours=12),
    )

    headers = _auth_headers(user)

    # Status filter
    resp_status = client.get(
        f"/clinic/{clinic.slug}/conversations", {"status": "handoff"}, **headers
    )
    assert resp_status.status_code == 200
    items = resp_status.json()["data"]["items"]
    assert [item["id"] for item in items] == [conv_handoff.id]

    # Intent filter
    resp_intent = client.get(
        f"/clinic/{clinic.slug}/conversations", {"intent": "booking"}, **headers
    )
    assert resp_intent.status_code == 200
    assert [item["id"] for item in resp_intent.json()["data"]["items"]] == [conv_open.id]

    # Language filter
    resp_lang = client.get(
        f"/clinic/{clinic.slug}/conversations", {"lang": "ar"}, **headers
    )
    assert resp_lang.status_code == 200
    assert [item["id"] for item in resp_lang.json()["data"]["items"]] == [conv_handoff.id]

    # Text search
    resp_search = client.get(
        f"/clinic/{clinic.slug}/conversations", {"q": "polish"}, **headers
    )
    assert resp_search.status_code == 200
    assert [item["id"] for item in resp_search.json()["data"]["items"]] == [conv_open.id]

    # Date window
    date_from = (now - timedelta(hours=13)).isoformat()
    date_to = (now - timedelta(hours=11)).isoformat()
    resp_range = client.get(
        f"/clinic/{clinic.slug}/conversations",
        {"from": date_from, "to": date_to},
        **headers,
    )
    assert resp_range.status_code == 200
    assert [item["id"] for item in resp_range.json()["data"]["items"]] == [conv_resolved.id]


def test_conversations_list_pagination(client, django_user_model):
    user = _make_user(django_user_model, email="viewer@example.com")
    clinic = Clinic.objects.create(slug="city-dental", name="City Dental", tz="UTC")
    ClinicMembership.objects.create(user=user, clinic=clinic, role=ClinicMembership.Role.VIEWER)
    patient = _create_patient(clinic)

    now = timezone.now()
    conversations = []
    for idx in range(3):
        conv = _create_conversation(
            clinic,
            patient,
            f"conv-{idx}",
            fsm_state="idle",
            handoff=False,
            intent=f"intent-{idx}",
        )
        Conversation.objects.filter(pk=conv.pk).update(
            created_at=now - timedelta(minutes=idx * 5),
            updated_at=now - timedelta(minutes=idx * 5),
        )
        _add_message(
            conv,
            MessageDirection.INBOUND,
            f"message {idx}",
            created_at=now - timedelta(minutes=idx * 5),
        )
        conversations.append(conv)

    headers = _auth_headers(user)
    resp = client.get(
        f"/clinic/{clinic.slug}/conversations",
        {"page": 2, "size": 2},
        **headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["page"] == 2
    assert data["size"] == 2
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == conversations[2].id


def test_conversation_detail_includes_messages(client, django_user_model):
    user = _make_user(django_user_model, email="detail@example.com")
    clinic = Clinic.objects.create(slug="detail-dental", name="Detail Dental", tz="UTC")
    ClinicMembership.objects.create(user=user, clinic=clinic, role=ClinicMembership.Role.ADMIN)
    patient = _create_patient(clinic)

    conv = _create_conversation(
        clinic,
        patient,
        "conv-detail",
        fsm_state="confirm",
        handoff=False,
        intent="clarify",
    )
    now = timezone.now()
    inbound = _add_message(conv, MessageDirection.INBOUND, "مرحبا", now - timedelta(minutes=3))
    outbound = _add_message(conv, MessageDirection.OUTBOUND, "أهلا بك", now - timedelta(minutes=2))

    headers = _auth_headers(user)
    resp = client.get(
        f"/clinic/{clinic.slug}/conversations/{conv.id}",
        **headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == conv.id
    assert data["intent"] == "clarify"
    assert data["fsm_state"] == "confirm"
    assert data["handoff"] is False
    message_ids = [msg["id"] for msg in data["messages"]]
    assert message_ids == [inbound.id, outbound.id]
    assert data["messages"][0]["dir"] == "in"
    assert data["messages"][1]["dir"] == "out"


def test_conversation_detail_not_found_for_other_clinic(client, django_user_model):
    user = _make_user(django_user_model, email="notfound@example.com")
    clinic = Clinic.objects.create(slug="primary", name="Primary", tz="UTC")
    other = Clinic.objects.create(slug="other", name="Other", tz="UTC")
    ClinicMembership.objects.create(user=user, clinic=clinic, role=ClinicMembership.Role.VIEWER)
    patient = _create_patient(other)
    conv = _create_conversation(other, patient, "foreign", fsm_state="idle", handoff=False)

    headers = _auth_headers(user)
    resp = client.get(
        f"/clinic/{clinic.slug}/conversations/{conv.id}",
        **headers,
    )
    assert resp.status_code == 404
    assert resp.json() == {"ok": False, "error": "NOT_FOUND"}


def test_appointments_list_filters(client, django_user_model):
    user = _make_user(django_user_model, email="staff@example.com")
    clinic = Clinic.objects.create(slug="appointments", name="Appointments", tz="UTC")
    ClinicMembership.objects.create(user=user, clinic=clinic, role=ClinicMembership.Role.STAFF)
    service = _create_service(clinic, code="clean")
    patient = _create_patient(clinic)

    now = timezone.now()
    slot_one = (now, now + timedelta(minutes=30))
    slot_two = (now + timedelta(days=2), now + timedelta(days=2, minutes=30))

    appt_one = Appointment.objects.create(
        clinic=clinic,
        service=service,
        patient=patient,
        slot=slot_one,
        status=AppointmentStatus.BOOKED,
    )
    appt_two = Appointment.objects.create(
        clinic=clinic,
        service=service,
        patient=patient,
        slot=slot_two,
        status=AppointmentStatus.PENDING,
    )

    headers = _auth_headers(user)
    resp_range = client.get(
        f"/clinic/{clinic.slug}/appointments",
        {"from": (now + timedelta(days=1)).isoformat()},
        **headers,
    )
    assert resp_range.status_code == 200
    data = resp_range.json()["data"]
    assert [item["id"] for item in data["items"]] == [appt_two.id]

    resp_all = client.get(
        f"/clinic/{clinic.slug}/appointments",
        {"page": 1, "size": 1},
        **headers,
    )
    assert resp_all.status_code == 200
    paged = resp_all.json()["data"]
    assert paged["total"] == 2
    assert paged["size"] == 1
    assert len(paged["items"]) == 1
    assert paged["items"][0]["id"] == appt_one.id
    assert paged["items"][0]["service_code"] == "clean"


def test_appointments_forbidden_cross_tenant(client, django_user_model):
    user = _make_user(django_user_model, email="apptviewer@example.com")
    clinic = Clinic.objects.create(slug="primary-clinic", name="Primary Clinic", tz="UTC")
    other = Clinic.objects.create(slug="other-clinic", name="Other Clinic", tz="UTC")
    ClinicMembership.objects.create(user=user, clinic=clinic, role=ClinicMembership.Role.VIEWER)

    headers = _auth_headers(user)
    resp = client.get(f"/clinic/{other.slug}/appointments", **headers)
    assert resp.status_code == 403
    assert resp.json() == {"ok": False, "error": "FORBIDDEN"}
