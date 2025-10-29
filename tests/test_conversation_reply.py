import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditLog, ClinicMembership
from apps.channels.models import (
    HSMTemplate,
    HSMTemplateStatus,
    MessageType,
    OutboxMessage,
    OutboxStatus,
)
from apps.channels.services import SESSION_WINDOW_HOURS
from apps.clinics.models import Clinic
from apps.conversations.models import Conversation, ConversationMessage, MessageDirection
from apps.templates.models import MessageTemplate

pytestmark = pytest.mark.django_db


def _make_user(email: str, role: ClinicMembership.Role, clinic: Clinic) -> User:
    user = User.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="Agent",
        last_name="User",
        is_active=True,
    )
    ClinicMembership.objects.create(user=user, clinic=clinic, role=role)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _create_clinic(slug: str = "demo") -> Clinic:
    return Clinic.objects.create(slug=slug, name="Demo Dental", tz="UTC", default_lang="en")


def _create_conversation(clinic: Clinic, patient=None, *, fsm_state="idle", handoff=False) -> Conversation:
    conversation = Conversation.objects.create(
        clinic=clinic,
        patient=patient,
        dedupe_key=f"conv-{timezone.now().timestamp()}",
        fsm_state=fsm_state,
        handoff_required=handoff,
    )
    return conversation


def _create_patient(clinic: Clinic):
    return clinic.patients.create(
        full_name="Test Patient",
        language="en",
        phone_number="+15555550111",
        normalized_phone="+15555550111",
    )


def _create_template(clinic: Clinic, code: str, body: str, variables: list[str], *, hsm_name: str | None = None):
    metadata = {"hsm_name": hsm_name} if hsm_name else {}
    return MessageTemplate.objects.create(
        clinic=clinic,
        code=code,
        language="en",
        body=body,
        variables=variables,
        provider_template_id=f"{code}_provider",
        metadata=metadata,
    )


def _create_hsm_template(clinic: Clinic, name: str, body: str):
    return HSMTemplate.objects.create(
        clinic=clinic,
        name=name,
        language="en",
        body=body,
        variables=["first_name"],
        status=HSMTemplateStatus.APPROVED,
        provider_template_id=f"{name}_provider",
    )


def _add_inbound(conversation: Conversation, created_at: timezone.datetime):
    message = ConversationMessage.objects.create(
        conversation=conversation,
        direction=MessageDirection.INBOUND,
        language="en",
        body="Hello",
    )
    ConversationMessage.objects.filter(pk=message.pk).update(
        created_at=created_at, updated_at=created_at
    )
    return message


def _add_outbound(conversation: Conversation, created_at: timezone.datetime):
    message = ConversationMessage.objects.create(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        language="en",
        body="Hi!",
    )
    ConversationMessage.objects.filter(pk=message.pk).update(
        created_at=created_at, updated_at=created_at
    )
    return message


def test_viewer_cannot_reply(client):
    clinic = _create_clinic("viewer-clinic")
    user = _make_user("viewer@example.com", ClinicMembership.Role.VIEWER, clinic)
    patient = _create_patient(clinic)
    conversation = _create_conversation(clinic, patient)
    _add_inbound(conversation, timezone.now())
    _create_template(clinic, "greet", "Hi {{first_name}}", ["first_name"])

    response = client.post(
        f"/clinic/{clinic.slug}/conversations/{conversation.id}/reply",
        data=json.dumps({"template_key": "greet", "variables": {"first_name": "Omar"}}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "FORBIDDEN"}


def test_reply_invalid_template(client):
    clinic = _create_clinic("invalid-template")
    user = _make_user("agent@example.com", ClinicMembership.Role.STAFF, clinic)
    patient = _create_patient(clinic)
    conversation = _create_conversation(clinic, patient)
    _add_inbound(conversation, timezone.now())

    response = client.post(
        f"/clinic/{clinic.slug}/conversations/{conversation.id}/reply",
        data=json.dumps({"template_key": "unknown"}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "INVALID_TEMPLATE"}


def test_reply_lint_failed(client):
    clinic = _create_clinic("lint-error")
    user = _make_user("agent@example.com", ClinicMembership.Role.ADMIN, clinic)
    patient = _create_patient(clinic)
    conversation = _create_conversation(clinic, patient)
    _add_inbound(conversation, timezone.now())
    _create_template(clinic, "slot_offer", "Slots {{slot1}} {{slot2}}", ["slot1", "slot2"])

    response = client.post(
        f"/clinic/{clinic.slug}/conversations/{conversation.id}/reply",
        data=json.dumps({"template_key": "slot_offer", "variables": {"slot1": "9am"}}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "LINT_FAILED"}


def test_reply_within_session_creates_outbox(client):
    clinic = _create_clinic("session-clinic")
    user = _make_user("agent@example.com", ClinicMembership.Role.STAFF, clinic)
    patient = _create_patient(clinic)
    conversation = _create_conversation(clinic, patient)
    now = timezone.now()
    _add_inbound(conversation, now - timedelta(hours=1))
    _add_outbound(conversation, now - timedelta(minutes=30))
    template = _create_template(clinic, "greet", "Hi {{first_name}}", ["first_name"])

    response = client.post(
        f"/clinic/{clinic.slug}/conversations/{conversation.id}/reply",
        data=json.dumps({"template_key": "greet", "variables": {"first_name": "Omar"}}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    message_id = payload["data"]["message_id"]

    outbox = OutboxMessage.objects.get(conversation=conversation)
    assert outbox.message_type == MessageType.SESSION
    assert outbox.payload["body"] == "Hi Omar"
    assert outbox.idempotency_key
    assert outbox.status == OutboxStatus.PENDING

    message = ConversationMessage.objects.get(pk=message_id)
    assert message.body == "Hi Omar"
    assert message.metadata["template_key"] == template.code

    audit = AuditLog.objects.filter(
        action="CONVERSATION_REPLY",
        clinic=clinic,
        meta__template_key="greet",
    )
    assert audit.exists()


def test_reply_outside_session_uses_hsm(client):
    clinic = _create_clinic("hsm-clinic")
    user = _make_user("agent@example.com", ClinicMembership.Role.ADMIN, clinic)
    patient = _create_patient(clinic)
    conversation = _create_conversation(clinic, patient, fsm_state="done")
    old_time = timezone.now() - timedelta(hours=SESSION_WINDOW_HOURS + 2)
    _add_inbound(conversation, old_time)
    template = _create_template(
        clinic,
        "greet",
        "Hi {{first_name}}",
        ["first_name"],
        hsm_name="greet_hsm",
    )
    hsm = HSMTemplate.objects.create(
        clinic=clinic,
        name="greet_hsm",
        language="en",
        body="Hi {{first_name}}",
        variables=["first_name"],
        status=HSMTemplateStatus.APPROVED,
        provider_template_id="greet_hsm_provider",
    )

    response = client.post(
        f"/clinic/{clinic.slug}/conversations/{conversation.id}/reply",
        data=json.dumps({"template_key": "greet", "variables": {"first_name": "Omar"}}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    message_id = body["data"]["message_id"]

    outbox = OutboxMessage.objects.get(conversation=conversation)
    assert outbox.message_type == MessageType.HSM
    assert outbox.hsm_template_id == hsm.id
    assert outbox.idempotency_key

    message = ConversationMessage.objects.get(pk=message_id)
    assert message.body == "Hi Omar"
    conversation.refresh_from_db()
    assert conversation.fsm_state == "idle"


def test_reply_outside_session_without_hsm(client):
    clinic = _create_clinic("no-hsm-clinic")
    user = _make_user("agent@example.com", ClinicMembership.Role.STAFF, clinic)
    patient = _create_patient(clinic)
    conversation = _create_conversation(clinic, patient)
    _add_inbound(conversation, timezone.now() - timedelta(hours=SESSION_WINDOW_HOURS + 1))
    _create_template(clinic, "greet", "Hi {{first_name}}", ["first_name"], hsm_name="missing_hsm")

    response = client.post(
        f"/clinic/{clinic.slug}/conversations/{conversation.id}/reply",
        data=json.dumps({"template_key": "greet", "variables": {"first_name": "Omar"}}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "NO_HSM_AVAILABLE"}
    assert OutboxMessage.objects.count() == 0
