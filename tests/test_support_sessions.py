import json
import time
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditLog, StaffAccount, SupportSession
from apps.channels.models import HSMTemplate, HSMTemplateStatus
from apps.clinics.models import Clinic, ClinicService
from apps.conversations.models import Conversation
from apps.patients.models import Patient
from apps.templates.models import MessageTemplate, TemplateCategory

pytestmark = pytest.mark.django_db


def _create_hq_user(django_user_model, role=StaffAccount.Role.SUPERADMIN):
    user = django_user_model.objects.create_user(
        username=f"{role.lower()}@hq.example.com",
        email=f"{role.lower()}@hq.example.com",
        password="Admin!234",
        first_name="HQ",
        last_name="User",
        is_active=True,
    )
    StaffAccount.objects.create(user=user, role=role)
    return user


def _hq_headers(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _support_headers(token: str):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _prepare_conversation(clinic: Clinic):
    service = ClinicService.objects.create(
        clinic=clinic,
        code="clean",
        name="Cleaning",
        duration_minutes=30,
        language="en",
    )
    patient = Patient.objects.create(
        clinic=clinic,
        full_name="John Doe",
        phone_number="+1234567890",
        normalized_phone="+1234567890",
        language="en",
    )
    conversation = Conversation.objects.create(
        clinic=clinic,
        patient=patient,
        dedupe_key="support-test",
        fsm_state="idle",
        handoff_required=False,
    )
    template = MessageTemplate.objects.create(
        clinic=clinic,
        code="greet",
        language="en",
        category=TemplateCategory.WHATSAPP,
        body="Hi {{name}}",
        variables=["name"],
        provider_template_id="greet",
        metadata={"hsm_name": "greet"},
    )
    HSMTemplate.objects.create(
        clinic=clinic,
        name="greet",
        language="en",
        body="Hi {{name}}",
        variables=["name"],
        status=HSMTemplateStatus.APPROVED,
        provider_template_id="greet",
    )
    return conversation, template, service


def _start_support_session(client, hq_user, clinic):
    client.defaults["REMOTE_ADDR"] = f"10.0.2.{int(time.time() * 1000) % 250}"
    response = client.post(
        "/hq/support/start",
        data=json.dumps({"clinic_id": clinic.id, "reason": "Investigate issue"}),
        content_type="application/json",
        **_hq_headers(hq_user),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return data["support_token"], data["expires_at"]


def test_support_session_allows_read_and_reply(client, django_user_model, settings):
    clinic = Clinic.objects.create(slug="support-clinic", name="Support Clinic", tz="UTC", default_lang="en")
    hq_user = _create_hq_user(django_user_model)
    conversation, template, _service = _prepare_conversation(clinic)

    token, _ = _start_support_session(client, hq_user, clinic)

    resp_dashboard = client.get(f"/clinic/{clinic.slug}/dashboard", **_support_headers(token))
    assert resp_dashboard.status_code == 200

    reply_resp = client.post(
        f"/clinic/{clinic.slug}/conversations/{conversation.id}/reply",
        data=json.dumps({"template_key": template.code, "variables": {"name": "John"}}),
        content_type="application/json",
        **_support_headers(token),
    )
    assert reply_resp.status_code == 200

    forbidden = client.put(
        f"/clinic/{clinic.slug}/services",
        data=json.dumps({"services": []}),
        content_type="application/json",
        **_support_headers(token),
    )
    assert forbidden.status_code == 403

    audit_requests = AuditLog.objects.filter(action="SUPPORT_SESSION_REQUEST", meta__clinic_slug=clinic.slug)
    assert audit_requests.count() >= 2  # dashboard + reply recorded


def test_support_session_expiry(client, django_user_model, settings):
    clinic = Clinic.objects.create(slug="expire-clinic", name="Expire Clinic", tz="UTC", default_lang="en")
    hq_user = _create_hq_user(django_user_model)
    token, _ = _start_support_session(client, hq_user, clinic)

    session = SupportSession.objects.first()
    session.expires_at = timezone.now() - timedelta(minutes=1)
    session.save(update_fields=["expires_at"])

    expired = client.get(f"/clinic/{clinic.slug}/dashboard", **_support_headers(token))
    assert expired.status_code == 401
    session.refresh_from_db()
    assert session.active is False


def test_support_session_stop(client, django_user_model):
    clinic = Clinic.objects.create(slug="stop-clinic", name="Stop Clinic", tz="UTC", default_lang="en")
    hq_user = _create_hq_user(django_user_model)
    token, _ = _start_support_session(client, hq_user, clinic)

    stop_resp = client.post(
        "/hq/support/stop",
        data=json.dumps({"support_token": token}),
        content_type="application/json",
        **_hq_headers(hq_user),
    )
    assert stop_resp.status_code == 200

    session = SupportSession.objects.get(clinic=clinic, staff_user=hq_user)
    assert session.active is False
    assert session.ended_at is not None

    after_stop = client.get(f"/clinic/{clinic.slug}/dashboard", **_support_headers(token))
    assert after_stop.status_code == 401

    assert AuditLog.objects.filter(action="SUPPORT_SESSION_STOP", clinic=clinic).exists()


def test_support_session_requires_hq_role(client, django_user_model):
    clinic = Clinic.objects.create(slug="role-clinic", name="Role Clinic", tz="UTC", default_lang="en")
    support_user = _create_hq_user(django_user_model, role=StaffAccount.Role.SUPPORT)

    client.defaults["REMOTE_ADDR"] = "10.0.3.10"
    resp = client.post(
        "/hq/support/start",
        data=json.dumps({"clinic_id": clinic.id, "reason": "Check"}),
        content_type="application/json",
        **_hq_headers(support_user),
    )
    assert resp.status_code == 403


def test_support_session_request_audit_flags_impersonation(client, django_user_model):
    clinic = Clinic.objects.create(slug="audit-clinic", name="Audit Clinic", tz="UTC", default_lang="en")
    hq_user = _create_hq_user(django_user_model)
    _prepare_conversation(clinic)
    token, _ = _start_support_session(client, hq_user, clinic)

    resp = client.get(f"/clinic/{clinic.slug}/conversations", **_support_headers(token))
    assert resp.status_code == 200

    audit_entry = AuditLog.objects.filter(
        action="SUPPORT_SESSION_REQUEST",
        meta__path=f"/clinic/{clinic.slug}/conversations",
        meta__impersonation=True,
    ).first()
    assert audit_entry is not None
