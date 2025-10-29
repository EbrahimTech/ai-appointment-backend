import json
import hashlib
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import ClinicMembership
from apps.calendars.models import GoogleCredential
from apps.calendars.services import GoogleCalendarService
from apps.channels.models import (
    ChannelAccount,
    ChannelType,
    OutboxMessage,
    OutboxStatus,
    HSMTemplate,
    HSMTemplateStatus,
)
from apps.clinics.models import Clinic
from apps.templates.models import MessageTemplate

pytestmark = pytest.mark.django_db


def _make_clinic():
    return Clinic.objects.create(slug="status", name="Status Clinic", tz="UTC", default_lang="en")


def _make_user(django_user_model, clinic, email, role):
    user = django_user_model.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="First",
        last_name="Last",
        is_active=True,
    )
    ClinicMembership.objects.create(user=user, clinic=clinic, role=role)
    return user


def _auth_headers(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _post(client, path, data, user, remote="10.20.0.1"):
    client.defaults["REMOTE_ADDR"] = remote
    return client.post(path, data=json.dumps(data), content_type="application/json", **_auth_headers(user))


def _get(client, path, user, remote="10.20.0.1"):
    client.defaults["REMOTE_ADDR"] = remote
    return client.get(path, **_auth_headers(user))


def test_whatsapp_status_and_test_send(client, django_user_model):
    clinic = _make_clinic()
    admin = _make_user(django_user_model, clinic, "admin@example.com", ClinicMembership.Role.ADMIN)

    status_resp = _get(client, f"/clinic/{clinic.slug}/channels/whatsapp", admin)
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] == "DOWN"

    ChannelAccount.objects.create(
        clinic=clinic,
        channel=ChannelType.WHATSAPP,
        provider_name="sandbox",
        access_token="token",
    )

    now = timezone.now()
    OutboxMessage.objects.create(
        clinic=clinic,
        channel=ChannelType.WHATSAPP,
        message_type="hsm",
        payload={},
        scheduled_for=now,
        status=OutboxStatus.FAILED,
    )
    delivered = OutboxMessage.objects.create(
        clinic=clinic,
        channel=ChannelType.WHATSAPP,
        message_type="hsm",
        payload={},
        scheduled_for=now,
        status=OutboxStatus.DELIVERED,
    )
    OutboxMessage.objects.filter(pk=delivered.pk).update(updated_at=timezone.now())

    status_resp = _get(client, f"/clinic/{clinic.slug}/channels/whatsapp", admin, remote="10.20.0.2")
    assert status_resp.json()["data"]["status"] == "OK"

    template = MessageTemplate.objects.create(
        clinic=clinic,
        code="greet",
        language="en",
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

    test_resp = _post(
        client,
        f"/clinic/{clinic.slug}/channels/whatsapp/test",
        {"to_sandbox_phone": "+15555550123", "variables": {"name": "Test"}},
        admin,
        remote="10.20.0.3",
    )
    assert test_resp.status_code == 200
    outbox_id = test_resp.json()["data"]["outbox_id"]
    first_outbox = OutboxMessage.objects.get(id=outbox_id)
    assert first_outbox.idempotency_key
    expected_key = hashlib.sha256(
        json.dumps(
            {
                "clinic": clinic.id,
                "phone": "+15555550123",
                "template": template.code,
                "language": template.language,
                "variables": {"name": "Test"},
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert first_outbox.idempotency_key == expected_key

    second = _post(
        client,
        f"/clinic/{clinic.slug}/channels/whatsapp/test",
        {"to_sandbox_phone": "+15555550123", "variables": {"name": "Test"}},
        admin,
        remote="10.20.0.4",
    )
    assert second.status_code == 200
    second_outbox_id = second.json()["data"]["outbox_id"]
    assert second_outbox_id == outbox_id


def test_google_calendar_status_and_oauth(client, django_user_model, monkeypatch):
    clinic = _make_clinic()
    admin = _make_user(django_user_model, clinic, "admin@example.com", ClinicMembership.Role.ADMIN)

    status_resp = _get(client, f"/clinic/{clinic.slug}/calendar/google", admin)
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] == "DISCONNECTED"

    credential = GoogleCredential.objects.create(
        clinic=clinic,
        account_email="calendar@example.com",
        access_token="token",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        calendar_id="primary",
        last_free_busy_at=timezone.now(),
    )

    status_resp = _get(client, f"/clinic/{clinic.slug}/calendar/google", admin, remote="10.20.0.5")
    assert status_resp.json()["data"]["status"] == "OK"

    credential.last_free_busy_at = timezone.now() - timedelta(hours=48)
    credential.save(update_fields=["last_free_busy_at"])
    status_resp = _get(client, f"/clinic/{clinic.slug}/calendar/google", admin, remote="10.20.0.6")
    assert status_resp.json()["data"]["status"] == "WARN"

    monkeypatch.setattr(GoogleCalendarService, "get_authorization_url", lambda self, clinic_id: "https://auth.example.com")
    start_resp = _get(client, f"/clinic/{clinic.slug}/calendar/google/oauth/start", admin, remote="10.20.0.7")
    assert start_resp.status_code == 200
    assert start_resp.json()["data"]["auth_url"] == "https://auth.example.com"

    def fake_exchange(self, clinic_id, code):
        cred, _ = GoogleCredential.objects.update_or_create(
            clinic_id=clinic_id,
            account_email="calendar@example.com",
            defaults={
                "access_token": "token123",
                "refresh_token": "refresh123",
                "expires_at": timezone.now() + timedelta(hours=2),
            },
        )
        return cred

    monkeypatch.setattr(GoogleCalendarService, "exchange_code", fake_exchange)
    callback_resp = _get(client, f"/clinic/{clinic.slug}/calendar/google/oauth/callback?code=abc", admin, remote="10.20.0.8")
    assert callback_resp.status_code == 200
    credential.refresh_from_db()
    assert credential.get_access_token() == "token123"
