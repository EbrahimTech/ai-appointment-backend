"""Webhook endpoints such as lead ingestion."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.channels.services import enqueue_whatsapp_hsm
from apps.clinics.models import Clinic
from apps.common.utils import minimal_ok
from apps.conversations.models import Conversation
from apps.patients.models import Patient
from apps.patients.utils import normalize_phone_number
from apps.webhooks.models import LeadWebhookEvent


def _validate_signature(body: bytes, provided: str | None) -> bool:
    secret = settings.LEAD_WEBHOOK_SECRET
    if not secret or not provided:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, provided)


def _get_language(payload: Dict[str, Any]) -> str:
    return payload.get("language", "en")


@csrf_exempt
@require_POST
def lead_webhook(request: HttpRequest) -> JsonResponse:
    signature = request.headers.get("X-Lead-Signature")
    if not _validate_signature(request.body, signature):
        return JsonResponse({"ok": False, "error": "invalid signature"}, status=401)

    payload = json.loads(request.body.decode("utf-8") or "{}")
    clinic_slug = payload.get("clinic")
    if not clinic_slug:
        return JsonResponse({"ok": False, "error": "clinic missing"}, status=400)

    try:
        clinic = Clinic.objects.get(slug=clinic_slug)
    except Clinic.DoesNotExist:
        return JsonResponse({"ok": False, "error": "clinic not found"}, status=404)

    dedupe_key = payload.get("lead_id") or normalize_phone_number(payload.get("phone", ""))
    if not dedupe_key:
        return JsonResponse({"ok": False, "error": "dedupe key missing"}, status=400)

    event, created = LeadWebhookEvent.objects.get_or_create(
        clinic=clinic,
        dedupe_key=dedupe_key,
        defaults={
            "signature": signature or "",
            "payload": payload,
        },
    )
    if not created and event.processed:
        return minimal_ok()

    patient, _ = Patient.objects.get_or_create(
        clinic=clinic,
        normalized_phone=normalize_phone_number(payload.get("phone", "")),
        defaults={
            "full_name": payload.get("name", "Guest"),
            "phone_number": payload.get("phone", ""),
            "language": _get_language(payload),
            "email": payload.get("email", ""),
        },
    )

    conversation, _ = Conversation.objects.get_or_create(
        clinic=clinic,
        dedupe_key=f"{clinic.slug}:{patient.normalized_phone}",
        defaults={
            "patient": patient,
            "lead_source": payload.get("source", "lead_webhook"),
        },
    )
    if not conversation.patient:
        conversation.patient = patient
        conversation.save(update_fields=["patient", "updated_at"])

    enqueue_whatsapp_hsm(
        clinic_id=clinic.id,
        conversation=conversation,
        template_name="whatsapp_welcome_en" if _get_language(payload) == "en" else "whatsapp_welcome_ar",
        language=_get_language(payload),
        variables={"name": patient.full_name},
        delay_seconds=5,
    )

    event.processed = True
    event.processed_at = timezone.now()
    event.related_conversation = conversation
    event.save(update_fields=["processed", "processed_at", "related_conversation", "updated_at"])

    return minimal_ok()
