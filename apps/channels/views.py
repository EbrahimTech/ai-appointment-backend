"""HTTP endpoints for messaging channels."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any, Dict

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.channels.models import ChannelType, OutboxMessage, OutboxStatus, WebhookEvent
from apps.channels.services import (
    enqueue_whatsapp_hsm,
    mark_outbox_delivered,
)
from apps.common.utils import minimal_ok
from apps.conversations.models import Conversation
from apps.dialog.orchestrator import DialogOrchestrator
from apps.patients.models import Patient
from apps.patients.utils import normalize_phone_number
from apps.clinics.models import Clinic


orchestrator = DialogOrchestrator()


def _get_language(message: Dict[str, Any]) -> str:
    return message.get("language", "en")


def _ensure_conversation(clinic: Clinic, phone: str, lead_source: str) -> Conversation:
    dedupe_key = f"{clinic.slug}:{phone}"
    conversation, _ = Conversation.objects.get_or_create(
        clinic=clinic,
        dedupe_key=dedupe_key,
        defaults={
            "lead_source": lead_source,
            "fsm_state": "idle",
        },
    )
    return conversation


@csrf_exempt
@require_POST
def whatsapp_webhook(request: HttpRequest) -> JsonResponse:
    payload = json.loads(request.body.decode("utf-8") or "{}")
    clinic_slug = payload.get("clinic")
    if not clinic_slug:
        return JsonResponse({"ok": False, "error": "clinic missing"}, status=400)

    try:
        clinic = Clinic.objects.get(slug=clinic_slug)
    except Clinic.DoesNotExist:
        return JsonResponse({"ok": False, "error": "clinic not found"}, status=404)

    WebhookEvent.objects.create(
        clinic=clinic,
        channel=ChannelType.WHATSAPP,
        provider_event_id=payload.get("event_id") or str(uuid.uuid4()),
        payload=payload,
    )

    messages = payload.get("messages", [])
    for message in messages:
        phone = normalize_phone_number(message.get("from", ""))
        if not phone:
            continue
        patient, _ = Patient.objects.get_or_create(
            clinic=clinic,
            normalized_phone=phone,
            defaults={
                "full_name": message.get("name", "Guest"),
                "phone_number": phone,
                "language": _get_language(message),
            },
        )
        conversation = _ensure_conversation(clinic, phone, lead_source="whatsapp")
        if not conversation.patient:
            conversation.patient = patient
            conversation.save(update_fields=["patient", "updated_at"])

        response_text, intent = orchestrator.handle_inbound(
            conversation,
            body=message.get("body", ""),
            language=_get_language(message),
        )

        if intent == "book" and response_text:
            enqueue_whatsapp_hsm(
                clinic_id=clinic.id,
                conversation=conversation,
                template_name="whatsapp_welcome_en" if _get_language(message) == "en" else "whatsapp_welcome_ar",
                language=_get_language(message),
                variables={"name": patient.full_name},
                delay_seconds=3,
            )

    return minimal_ok()


@csrf_exempt
@require_POST
def whatsapp_delivery_receipt(request: HttpRequest) -> JsonResponse:
    payload = json.loads(request.body.decode("utf-8") or "{}")
    provider_message_id = payload.get("provider_message_id")
    idempotency_key = payload.get("idempotency_key")
    status = (payload.get("status") or "").lower()

    outbox: OutboxMessage | None = None
    if idempotency_key:
        outbox = OutboxMessage.objects.filter(idempotency_key=idempotency_key).first()
    if not outbox and provider_message_id:
        outbox = OutboxMessage.objects.filter(
            payload__provider_message_id=provider_message_id
        ).first()
    if not outbox:
        return JsonResponse({"ok": False, "error": "message not found"}, status=404)

    if status == "delivered":
        mark_outbox_delivered(outbox, payload.get("delivered_at"))
    elif status == "failed":
        outbox.status = OutboxStatus.FAILED
        outbox.last_error = payload.get("error", "provider_failure")
        outbox.metadata["provider_status"] = payload
        outbox.scheduled_for = timezone.now() + timedelta(seconds=30)
        outbox.save(update_fields=["status", "last_error", "metadata", "scheduled_for", "updated_at"])
    else:
        # treat as acknowledged send
        outbox.status = OutboxStatus.SENT
        outbox.metadata["provider_status"] = payload
        outbox.save(update_fields=["status", "metadata", "updated_at"])

    return minimal_ok()
