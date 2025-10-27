"""Celery tasks for reminders and outbox retries."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.channels.models import MessageType, OutboxMessage, OutboxStatus
from apps.channels.services import (
    enqueue_whatsapp_hsm,
    mark_outbox_delivered,
    mark_outbox_sent,
)
from apps.conversations.models import ConversationMessage

OUTBOX_BATCH_SIZE = int(getattr(settings, "OUTBOX_DISPATCH_BATCH_SIZE", 50))
OUTBOX_BACKOFF_MAX_SECONDS = int(getattr(settings, "OUTBOX_BACKOFF_MAX_SECONDS", 300))


@shared_task
def dispatch_outbox_messages() -> int:
    """Send pending outbox messages immediately (stub provider send)."""
    now = timezone.now()
    dispatched: list[OutboxMessage] = []

    with transaction.atomic():
        candidates = list(
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(
                status=OutboxStatus.PENDING,
                scheduled_for__lte=now,
                attempts__lt=F("max_attempts"),
            )
            .order_by("scheduled_for")[:OUTBOX_BATCH_SIZE]
        )

        for message in candidates:
            if message.message_type == MessageType.HSM and message.hsm_template is None:
                message.scheduled_for = now + timedelta(minutes=30)
                message.metadata["hold_reason"] = "awaiting_template_approval"
                message.save(update_fields=["scheduled_for", "metadata", "updated_at"])
                continue

            message.status = OutboxStatus.SENDING
            message.attempts += 1
            message.metadata["last_attempt_started_at"] = now.isoformat()
            message.save(update_fields=["status", "attempts", "metadata", "updated_at"])
            dispatched.append(message)

    for message in dispatched:
        try:
            mark_outbox_sent(message, provider_message_id=f"simulated-{message.id}")
            mark_outbox_delivered(message)
        except Exception as exc:  # pragma: no cover - network/provider stub
            message.status = (
                OutboxStatus.FAILED
                if message.attempts < message.max_attempts
                else OutboxStatus.CANCELLED
            )
            backoff_seconds = min(OUTBOX_BACKOFF_MAX_SECONDS, 2 ** message.attempts)
            message.last_error = str(exc)
            message.scheduled_for = timezone.now() + timedelta(seconds=backoff_seconds)
            message.save(
                update_fields=["status", "last_error", "scheduled_for", "updated_at"]
            )

    return len(dispatched)


@shared_task
def retry_outbox_failures() -> int:
    """Retry failed outbox entries with exponential backoff."""
    now = timezone.now()
    retry_count = 0
    failures = OutboxMessage.objects.filter(
        status=OutboxStatus.FAILED, attempts__lt=F("max_attempts")
    )
    for message in failures:
        backoff_seconds = min(OUTBOX_BACKOFF_MAX_SECONDS, 2 ** message.attempts)
        if message.scheduled_for <= now:
            message.status = OutboxStatus.PENDING
            message.scheduled_for = now + timedelta(seconds=backoff_seconds)
            message.save(update_fields=["status", "scheduled_for", "updated_at"])
            retry_count += 1
    return retry_count


@shared_task
def schedule_appointment_reminders() -> int:
    """Queue reminders at +24h and +2h before the appointment."""
    now = timezone.now()
    upcoming = Appointment.objects.filter(
        status__in=[AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED],
        slot__lower__gte=now,
        slot__lower__lte=now + timedelta(hours=24),
    )
    queued = 0
    for appt in upcoming:
        if not appt.patient:
            continue
        in_24h = appt.slot.lower - timedelta(hours=24)
        in_2h = appt.slot.lower - timedelta(hours=2)
        for reminder_time, template_name in [
            (in_24h, "reminder_24h"),
            (in_2h, "reminder_2h"),
        ]:
            if reminder_time <= now:
                continue
            conversation = appt.patient.conversations.first()
            if not conversation:
                continue
            enqueue_whatsapp_hsm(
                clinic_id=appt.clinic_id,
                conversation=conversation,
                template_name=template_name,
                language=appt.patient.language,
                variables={"name": appt.patient.full_name},
                delay_seconds=int((reminder_time - now).total_seconds()),
            )
            queued += 1
    return queued


@shared_task
def enforce_message_retention() -> int:
    """Redact PII from historical conversation messages."""
    retention_days = getattr(settings, "DATA_RETENTION_DAYS", 30)
    cutoff = timezone.now() - timedelta(days=retention_days)
    stale_messages = ConversationMessage.objects.filter(
        created_at__lt=cutoff
    ).exclude(metadata__redacted=True)[:500]

    total = 0
    for message in stale_messages:
        digest = hashlib.sha256(message.body.encode("utf-8", "ignore")).hexdigest()
        preview = message.body[:8]
        message.body = "[redacted]"
        message.metadata["redacted"] = True
        message.metadata["body_hash"] = digest
        message.metadata["preview"] = preview
        message.save(update_fields=["body", "metadata", "updated_at"])
        total += 1
    return total
