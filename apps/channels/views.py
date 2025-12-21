"""HTTP endpoints for messaging channels."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional
import logging

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.conf import settings

from apps.channels.models import (
    ChannelAccount,
    ChannelType,
    OutboxMessage,
    OutboxStatus,
    WebhookEvent,
)
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


logger = logging.getLogger(__name__)
orchestrator = DialogOrchestrator()


def _get_language(message: Dict[str, Any]) -> str:
    return message.get("language", "en")


def _detect_language_from_text(text: str) -> Optional[str]:
    """Detect language from text content (simple heuristic)."""
    if not text:
        return None
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    latin_chars = sum(1 for c in text if "A" <= c <= "Z" or "a" <= c <= "z")
    total_letters = arabic_chars + latin_chars
    if total_letters == 0:
        return None
    if arabic_chars / total_letters > 0.3:
        return "ar"
    return "en"


def _get_clinic_from_phone_number(phone_number_id: str) -> Optional[Clinic]:
    """Resolve clinic by provider phone_number_id; fall back to default slug."""
    if phone_number_id:
        account = (
            ChannelAccount.objects.filter(
                channel=ChannelType.WHATSAPP,
                provider_name__iexact="meta",
                metadata__phone_number_id=str(phone_number_id).strip(),
            )
            .select_related("clinic")
            .first()
        )
        if account:
            return account.clinic

    default_slug = getattr(settings, 'WHATSAPP_DEFAULT_CLINIC_SLUG', 'prime-dental')
    try:
        return Clinic.objects.get(slug=default_slug)
    except Clinic.DoesNotExist:
        # Fallback to first clinic
        return Clinic.objects.first()


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
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle Meta WhatsApp Cloud API webhooks.

    GET: Webhook verification (required by Meta)
    POST: Incoming messages and status updates
    """

    # GET request: Webhook verification
    if request.method == "GET":
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        mode = request.GET.get("hub.mode")

        expected_token = getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', 'thebestverifytokenpassword')

        if mode == "subscribe" and verify_token == expected_token:
            logger.info("WhatsApp webhook verified successfully")
            return HttpResponse(challenge, content_type="text/plain")
        else:
            logger.warning(f"WhatsApp webhook verification failed. Token: {verify_token}")
            return HttpResponse("Forbidden", status=403)

    # POST request: Handle incoming messages
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        logger.info(f"Received WhatsApp webhook: {json.dumps(payload, indent=2)}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Meta WhatsApp format
    if "object" in payload and payload.get("object") == "whatsapp_business_account":
        return _handle_meta_webhook(payload)

    # Legacy format (for backwards compatibility)
    elif "clinic" in payload:
        return _handle_legacy_webhook(payload)

    # Unknown format
    logger.warning(f"Unknown webhook format: {payload}")
    return JsonResponse({"status": "ignored"}, status=200)


def _handle_meta_webhook(payload: Dict[str, Any]) -> JsonResponse:
    """Handle Meta WhatsApp Cloud API webhook format."""

    entries = payload.get("entry", [])

    for entry in entries:
        changes = entry.get("changes", [])

        for change in changes:
            value = change.get("value", {})

            # Get phone number ID to determine clinic
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            clinic = _get_clinic_from_phone_number(phone_number_id)

            if not clinic:
                logger.error(f"No clinic found for phone_number_id: {phone_number_id}")
                continue

            provider_event_root = entry.get("id", str(uuid.uuid4()))

            # Process incoming messages
            messages = value.get("messages", [])
            for idx, msg in enumerate(messages):
                # Deduplicate on provider message id when present
                provider_event_id = msg.get("id") or f"{provider_event_root}-msg-{idx}"
                webhook_event, created = WebhookEvent.objects.get_or_create(
                    provider_event_id=provider_event_id,
                    defaults={
                        "clinic": clinic,
                        "channel": ChannelType.WHATSAPP,
                        "payload": payload,
                    },
                )
                if not created:
                    # Duplicate delivery; skip processing
                    continue
                _process_whatsapp_message(clinic, msg, value)

            # Process status updates
            statuses = value.get("statuses", []) if value else []
            for idx, status in enumerate(statuses):
                provider_event_id = status.get("id") or f"{provider_event_root}-status-{idx}"
                webhook_event, created = WebhookEvent.objects.get_or_create(
                    provider_event_id=provider_event_id,
                    defaults={
                        "clinic": clinic,
                        "channel": ChannelType.WHATSAPP,
                        "payload": payload,
                    },
                )
                if not created:
                    continue
                _process_whatsapp_status(status)

    return JsonResponse({"status": "ok"}, status=200)


def _process_whatsapp_message(clinic: Clinic, msg: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    """Process a single WhatsApp message from Meta format."""

    # Extract message data
    from_number = msg.get("from", "")
    phone = normalize_phone_number(from_number)

    if not phone:
        logger.warning(f"Invalid phone number: {from_number}")
        return

    # Get message text
    msg_type = msg.get("type", "text")
    text_body = ""

    if msg_type == "text":
        text_body = msg.get("text", {}).get("body", "")
    elif msg_type == "button":
        text_body = msg.get("button", {}).get("text", "")
    elif msg_type == "interactive":
        interactive = msg.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text_body = interactive.get("button_reply", {}).get("title", "")
        elif interactive.get("type") == "list_reply":
            text_body = interactive.get("list_reply", {}).get("title", "")
    else:
        logger.info(f"Unsupported message type: {msg_type}")
        return

    # Detect language
    detected_language = _detect_language_from_text(text_body)
    language = detected_language or clinic.default_lang or "en"

    # Get or create patient
    profile_name = metadata.get("contacts", [{}])[0].get("profile", {}).get("name", "Guest")

    patient, created = Patient.objects.get_or_create(
        clinic=clinic,
        normalized_phone=phone,
        defaults={
            "full_name": profile_name,
            "phone_number": phone,
            "language": language,
        },
    )

    if not created:
        if detected_language is None:
            language = patient.language or language
        else:
            language = detected_language

    # Update patient language if detected
    if patient.language != language:
        patient.language = language
        patient.save(update_fields=["language"])

    # Get or create conversation
    conversation = _ensure_conversation(clinic, phone, lead_source="whatsapp")
    if not conversation.patient:
        conversation.patient = patient
        conversation.save(update_fields=["patient", "updated_at"])

    # Process through dialog orchestrator
    try:
        response_text, intent = orchestrator.handle_inbound(
            conversation,
            body=text_body,
            language=language,
        )

        logger.info(f"Conversation {conversation.id} - Intent: {intent}, Response: {response_text[:100] if response_text else 'None'}")

        # Send welcome message for booking intent
        if intent == "book" and response_text:
            template_name = "whatsapp_welcome_en" if language == "en" else "whatsapp_welcome_ar"
            enqueue_whatsapp_hsm(
                clinic_id=clinic.id,
                conversation=conversation,
                template_name=template_name,
                language=language,
                variables={"name": patient.full_name},
                delay_seconds=3,
            )
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


def _process_whatsapp_status(status: Dict[str, Any]) -> None:
    """Process WhatsApp message status update."""

    message_id = status.get("id")
    recipient = status.get("recipient_id")
    status_type = status.get("status", "").lower()

    logger.info(f"Status update for message {message_id}: {status_type}")

    # Find outbox message by provider message ID
    outbox = OutboxMessage.objects.filter(
        payload__provider_message_id=message_id
    ).first()

    if not outbox:
        logger.warning(f"Outbox message not found for provider_message_id: {message_id}")
        return

    # Update status
    if status_type == "delivered":
        mark_outbox_delivered(outbox, status.get("timestamp"))
    elif status_type == "failed":
        outbox.status = OutboxStatus.FAILED
        outbox.last_error = status.get("errors", [{}])[0].get("message", "delivery_failed")
        outbox.metadata["provider_status"] = status
        outbox.save(update_fields=["status", "last_error", "metadata", "updated_at"])
    elif status_type in ["sent", "read"]:
        if outbox.status in {OutboxStatus.PENDING, OutboxStatus.SENDING}:
            outbox.status = OutboxStatus.SENT
            outbox.metadata["provider_status"] = status
            outbox.save(update_fields=["status", "metadata", "updated_at"])


def _handle_legacy_webhook(payload: Dict[str, Any]) -> JsonResponse:
    """Handle legacy webhook format for backwards compatibility."""

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
