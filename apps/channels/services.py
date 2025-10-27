"""Messaging channel helpers (primarily WhatsApp)."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Optional
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.channels.models import (
    ChannelType,
    HSMTemplate,
    HSMTemplateStatus,
    MessageType,
    OutboxMessage,
    OutboxStatus,
)
from apps.conversations.models import Conversation, ConversationMessage

SESSION_WINDOW_HOURS = int(getattr(settings, "WHATSAPP_SESSION_WINDOW_HOURS", 24))
MAX_INITIAL_DELAY_SECONDS = int(getattr(settings, "WHATSAPP_MAX_INITIAL_DELAY_SECONDS", 10))
DEFAULT_MAX_ATTEMPTS = int(getattr(settings, "OUTBOX_MAX_ATTEMPTS", 5))
DEFAULT_SESSION_FALLBACK_HSM = getattr(
    settings, "WHATSAPP_SESSION_FALLBACK_HSM_NAME", "session_clarify"
)


def _render_body(body: str, variables: dict[str, str]) -> str:
    result = body
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def _get_hsm_template(
    clinic_id: int,
    name: str,
    language: str,
    *,
    allow_fallback_language: bool = True,
) -> HSMTemplate | None:
    """Fetch an approved HSM template; optionally fall back to other languages."""

    template = HSMTemplate.objects.filter(
        clinic_id=clinic_id,
        name=name,
        language=language,
        status=HSMTemplateStatus.APPROVED,
    ).first()
    if template or not allow_fallback_language:
        return template
    return (
        HSMTemplate.objects.filter(
            clinic_id=clinic_id,
            name=name,
            status=HSMTemplateStatus.APPROVED,
        )
        .order_by("language")
        .first()
    )


def _within_session_window(conversation: Conversation | None) -> bool:
    if not conversation:
        return False
    last_inbound = (
        conversation.messages.filter(direction="inbound").order_by("-created_at").first()
    )
    if not last_inbound:
        return False
    return (timezone.now() - last_inbound.created_at) <= timedelta(hours=SESSION_WINDOW_HOURS)


def _has_prior_outbound(conversation: Conversation | None) -> bool:
    if not conversation:
        return False
    return conversation.messages.filter(direction="outbound").exists()


def _build_idempotency(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def enqueue_whatsapp_message(
    *,
    clinic_id: int,
    conversation: Conversation | None,
    language: str,
    message_body: Optional[str] = None,
    hsm_name: Optional[str] = None,
    variables: Optional[dict[str, str]] = None,
    delay_seconds: int = 5,
    idempotency_key: Optional[str] = None,
) -> OutboxMessage:
    """Route WhatsApp messages through session/HSM policies automatically."""

    variables = variables or {}
    now = timezone.now()
    within_window = _within_session_window(conversation)
    first_outbound = not _has_prior_outbound(conversation)
    requires_hsm = first_outbound or not within_window

    message_type = MessageType.SESSION
    hsm_template: HSMTemplate | None = None
    payload: dict[str, str | dict] = {}

    if requires_hsm or not message_body:
        if not hsm_name:
            raise ValueError("HSM template name required for first message or outside 24h window.")
        hsm_template = _get_hsm_template(clinic_id, hsm_name, language)
        if not hsm_template:
            metadata = {
                "queued_at": now.isoformat(),
                "reason": "template_not_approved",
                "requested_template": {"name": hsm_name, "language": language},
            }
            return OutboxMessage.objects.create(
                clinic_id=clinic_id,
                conversation=conversation,
                message_type=MessageType.HSM,
                channel=ChannelType.WHATSAPP,
                hsm_template=None,
                payload={},
                scheduled_for=now + timedelta(minutes=5),
                status=OutboxStatus.PENDING,
                attempts=0,
                max_attempts=DEFAULT_MAX_ATTEMPTS,
                idempotency_key=str(uuid4()),
                metadata=metadata,
            )

        payload = {
            "template_id": hsm_template.provider_template_id,
            "body": _render_body(hsm_template.body, variables),
            "variables": variables,
        }
        message_type = MessageType.HSM
    else:
        payload = {
            "body": message_body,
        }

    scheduled_for = now + timedelta(
        seconds=min(max(delay_seconds, 0), MAX_INITIAL_DELAY_SECONDS)
    )
    if not idempotency_key:
        idempotency_key = _build_idempotency(
            {
                "clinic_id": clinic_id,
                "conversation_id": conversation.id if conversation else None,
                "payload": payload,
                "message_type": message_type,
            }
        )

    outbox_defaults = dict(
        clinic_id=clinic_id,
        conversation=conversation,
        message_type=message_type,
        channel=ChannelType.WHATSAPP,
        hsm_template=hsm_template,
        payload=payload,
        scheduled_for=scheduled_for,
        status=OutboxStatus.PENDING,
        attempts=0,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        metadata={"variables": variables, "auto_id": str(uuid4())},
    )

    try:
        outbox, created = OutboxMessage.objects.get_or_create(
            idempotency_key=idempotency_key, defaults=outbox_defaults
        )
    except IntegrityError:
        idempotency_key = f"{idempotency_key}-{uuid4()}"
        outbox_defaults["idempotency_key"] = idempotency_key
        outbox = OutboxMessage.objects.create(**outbox_defaults)
        created = True

    if not created and outbox.status in {OutboxStatus.SENT, OutboxStatus.DELIVERED}:
        return outbox

    if not created:
        # refresh payload in case retry intention differs
        for field, value in outbox_defaults.items():
            setattr(outbox, field, value)
        outbox.save()

    return outbox


def enqueue_whatsapp_session_message(
    *,
    clinic_id: int,
    conversation: Conversation,
    language: str,
    message_body: str,
    fallback_hsm_name: Optional[str] = None,
    delay_seconds: int = 0,
    idempotency_key: Optional[str] = None,
) -> OutboxMessage:
    """Send a session message with automatic HSM fallback when required."""

    return enqueue_whatsapp_message(
        clinic_id=clinic_id,
        conversation=conversation,
        language=language,
        message_body=message_body,
        hsm_name=fallback_hsm_name or DEFAULT_SESSION_FALLBACK_HSM,
        delay_seconds=delay_seconds,
        idempotency_key=idempotency_key,
    )


def enqueue_whatsapp_hsm(
    *,
    clinic_id: int,
    conversation: Conversation | None,
    template_name: str,
    language: str,
    variables: dict[str, str],
    delay_seconds: int = 5,
    idempotency_key: Optional[str] = None,
) -> OutboxMessage:
    """Compatibility helper to queue an HSM-only notification."""

    return enqueue_whatsapp_message(
        clinic_id=clinic_id,
        conversation=conversation,
        language=language,
        hsm_name=template_name,
        variables=variables,
        delay_seconds=delay_seconds,
        idempotency_key=idempotency_key,
    )


def mark_outbox_sent(outbox: OutboxMessage, provider_message_id: str) -> None:
    outbox.status = OutboxStatus.SENT
    outbox.payload["provider_message_id"] = provider_message_id
    outbox.sent_at = timezone.now()
    outbox.save(update_fields=["status", "payload", "sent_at", "updated_at"])


def mark_outbox_delivered(outbox: OutboxMessage, provider_timestamp: Optional[str] = None) -> None:
    outbox.status = OutboxStatus.DELIVERED
    outbox.delivered_at = timezone.now()
    if provider_timestamp:
        outbox.metadata["delivered_at_provider"] = provider_timestamp
    outbox.save(update_fields=["status", "delivered_at", "metadata", "updated_at"])
