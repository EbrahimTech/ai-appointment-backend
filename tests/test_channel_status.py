import hashlib
import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from django.core.cache import cache

from apps.accounts.models import AuditLog, ClinicMembership
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


def _make_clinic(slug="status"):
    return Clinic.objects.create(slug=slug, name=f"{slug.title()} Clinic", tz="UTC", default_lang="en")


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


def test_whatsapp_status_and_test_send(client, django_user_model, settings):
    clinic = _make_clinic("status")
    settings.WHATSAPP_TEST_ALLOWLIST = {"status": ["+15555550123"]}
    settings.WHATSAPP_TEST_RPM = 3
    cache.delete(f"whatsapp-test:{clinic.id}")
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


def test_whatsapp_test_rejects_non_allowlisted_number(client, django_user_model, settings):
    clinic = _make_clinic("sandbox-reject")
    settings.WHATSAPP_TEST_ALLOWLIST = {"sandbox-reject": ["+15555550123"]}
    settings.WHATSAPP_TEST_RPM = 3
    cache.delete(f"whatsapp-test:{clinic.id}")
    admin = _make_user(django_user_model, clinic, "admin2@example.com", ClinicMembership.Role.ADMIN)

    MessageTemplate.objects.create(
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

    resp = _post(
        client,
        f"/clinic/{clinic.slug}/channels/whatsapp/test",
        {"to_sandbox_phone": "+16666660000", "variables": {"name": "Test"}},
        admin,
    )
    assert resp.status_code == 403
    assert resp.json() == {"ok": False, "error": "FORBIDDEN_SANDBOX_NUMBER"}


def test_whatsapp_test_rate_limit(client, django_user_model, settings):
    clinic = _make_clinic("sandbox-throttle")
    settings.WHATSAPP_TEST_ALLOWLIST = {"sandbox-throttle": ["+15555550123"]}
    settings.WHATSAPP_TEST_RPM = 3
    cache.delete(f"whatsapp-test:{clinic.id}")
    admin = _make_user(django_user_model, clinic, "throttle@example.com", ClinicMembership.Role.ADMIN)

    MessageTemplate.objects.create(
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

    for i in range(3):
        resp = _post(
            client,
            f"/clinic/{clinic.slug}/channels/whatsapp/test",
            {"to_sandbox_phone": "+15555550123", "variables": {"name": f"User {i}"}},
            admin,
            remote=f"10.20.0.{10 + i}",
        )
        assert resp.status_code == 200

    fourth = _post(
        client,
        f"/clinic/{clinic.slug}/channels/whatsapp/test",
        {"to_sandbox_phone": "+15555550123", "variables": {"name": "User 3"}},
        admin,
        remote="10.20.0.99",
    )
    assert fourth.status_code == 429
    assert fourth.json() == {"ok": False, "error": "RATE_LIMIT"}


def test_whatsapp_test_audit_logged(client, django_user_model, settings):
    clinic = _make_clinic("sandbox-audit")
    settings.WHATSAPP_TEST_ALLOWLIST = {"sandbox-audit": ["+15555550123"]}
    settings.WHATSAPP_TEST_RPM = 3
    cache.delete(f"whatsapp-test:{clinic.id}")
    admin = _make_user(django_user_model, clinic, "audit@example.com", ClinicMembership.Role.ADMIN)

    MessageTemplate.objects.create(
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

    resp = _post(
        client,
        f"/clinic/{clinic.slug}/channels/whatsapp/test",
        {"to_sandbox_phone": "+15555550123", "variables": {"name": "Audit"}},
        admin,
    )
    assert resp.status_code == 200
    outbox_id = resp.json()["data"]["outbox_id"]
    audit = AuditLog.objects.filter(
        action="WHATSAPP_TEST_SEND",
        clinic=clinic,
        meta__outbox_id=outbox_id,
    ).first()
    assert audit is not None
    assert audit.meta["to"] == "+15555550123"
    assert audit.meta["template_key"] == "greet"
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


def test_outbox_status_success(client, django_user_model):
    clinic = _make_clinic()
    staff = _make_user(django_user_model, clinic, "staff@example.com", ClinicMembership.Role.STAFF)
    outbox = OutboxMessage.objects.create(
        clinic=clinic,
        channel=ChannelType.WHATSAPP,
        message_type="session",
        payload={"provider_message_id": "abc123"},
        scheduled_for=timezone.now(),
        status=OutboxStatus.SENT,
    )
    OutboxMessage.objects.filter(pk=outbox.pk).update(updated_at=timezone.now())

    resp = _get(client, f"/clinic/{clinic.slug}/outbox/{outbox.id}", staff, remote="10.20.0.9")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]["outbox"]
    assert data["id"] == outbox.id
    assert data["message_type"] == "session"
    assert data["state"] == "SENT"
    assert data["provider_message_id"] == "abc123"
    assert "created_at" in data and "updated_at" in data
    assert data["last_error"] is None


def test_outbox_status_forbidden_for_viewer(client, django_user_model):
    clinic = _make_clinic()
    viewer = _make_user(django_user_model, clinic, "viewer@example.com", ClinicMembership.Role.VIEWER)
    outbox = OutboxMessage.objects.create(
        clinic=clinic,
        channel=ChannelType.WHATSAPP,
        message_type="hsm",
        payload={},
        scheduled_for=timezone.now(),
        status=OutboxStatus.PENDING,
    )

    resp = _get(client, f"/clinic/{clinic.slug}/outbox/{outbox.id}", viewer, remote="10.20.0.10")
    assert resp.status_code == 403
    assert resp.json() == {"ok": False, "error": "FORBIDDEN"}
