"""Celery tasks for reminders, outbox, and calendar sync retries."""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.appointments.models import (
    Appointment,
    AppointmentStatus,
    AppointmentSyncState,
)
from apps.calendars.models import GoogleCredential
from apps.calendars.services import GoogleCalendarService, GoogleCalendarServiceError
from apps.channels.models import MessageType, OutboxMessage, OutboxStatus
from apps.channels.services import (
    enqueue_whatsapp_hsm,
    mark_outbox_delivered,
    mark_outbox_sent,
)
from apps.conversations.models import ConversationMessage

logger = logging.getLogger(__name__)

OUTBOX_BATCH_SIZE = int(getattr(settings, "OUTBOX_DISPATCH_BATCH_SIZE", 50))
OUTBOX_BACKOFF_MAX_SECONDS = int(getattr(settings, "OUTBOX_BACKOFF_MAX_SECONDS", 300))

GOOGLE_SYNC_MAX_ATTEMPTS = int(getattr(settings, "GOOGLE_SYNC_MAX_ATTEMPTS", 5))
GOOGLE_SYNC_INITIAL_DELAY = int(getattr(settings, "GOOGLE_SYNC_INITIAL_DELAY", 60))
GOOGLE_SYNC_MAX_DELAY = int(getattr(settings, "GOOGLE_SYNC_MAX_DELAY", 1800))
GOOGLE_SYNC_CACHE_SECONDS = int(getattr(settings, "GOOGLE_SYNC_CACHE_SECONDS", 120))
GOOGLE_SYNC_SWEEP_BATCH = int(getattr(settings, "GOOGLE_SYNC_SWEEP_BATCH", 25))


def schedule_google_calendar_retry(appointment_id: int, countdown: int | None = None) -> bool:
    """Idempotently queue a retry task for the given appointment."""
    cache_key = f"appt-google-retry:{appointment_id}"
    if not cache.add(cache_key, True, GOOGLE_SYNC_CACHE_SECONDS):
        return False
    delay_seconds = countdown if countdown is not None else GOOGLE_SYNC_INITIAL_DELAY
    retry_google_calendar_sync.apply_async(
        args=[appointment_id],
        countdown=delay_seconds,
        task_id=f"appt-google-sync-{appointment_id}-initial",
    )
    logger.info(
        "google_sync.retry_scheduled",
        extra={"appointment_id": appointment_id, "countdown": delay_seconds},
    )
    return True


@shared_task(bind=True, max_retries=0)
def retry_google_calendar_sync(self, appointment_id: int) -> str:
    """Attempt to promote tentative appointments to confirmed Google events."""
    appointment = (
        Appointment.objects.select_related("clinic", "service", "patient", "calendar_event")
        .filter(id=appointment_id)
        .first()
    )
    cache.delete(f"appt-google-retry:{appointment_id}")
    if appointment is None:
        logger.warning("google_sync.missing", extra={"appointment_id": appointment_id})
        return "missing"

    if appointment.external_event_id and appointment.sync_state == AppointmentSyncState.OK:
        return "already_synced"

    if appointment.sync_state == AppointmentSyncState.FAILED and appointment.google_retry_count >= GOOGLE_SYNC_MAX_ATTEMPTS:
        return "max_attempts"

    credential: GoogleCredential | None = (
        GoogleCredential.objects.filter(clinic=appointment.clinic).order_by("-updated_at").first()
    )
    if credential is None:
        appointment.sync_state = AppointmentSyncState.FAILED
        appointment.google_last_error = "missing_google_credential"
        appointment.save(
            update_fields=["sync_state", "google_last_error", "updated_at"]
        )
        logger.error(
            "google_sync.no_credentials",
            extra={"appointment_id": appointment.id, "clinic_id": appointment.clinic_id},
        )
        return "missing_credential"

    service = GoogleCalendarService()
    try:
        event = service.create_event(appointment, credential)
    except GoogleCalendarServiceError as exc:
        appointment.google_retry_count += 1
        appointment.google_last_error = str(exc)
        appointment.sync_state = (
            AppointmentSyncState.FAILED
            if appointment.google_retry_count >= GOOGLE_SYNC_MAX_ATTEMPTS
            else AppointmentSyncState.TENTATIVE
        )
        appointment.save(
            update_fields=[
                "sync_state",
                "google_retry_count",
                "google_last_error",
                "updated_at",
            ]
        )
        attempt = appointment.google_retry_count
        if appointment.sync_state == AppointmentSyncState.FAILED:
            logger.error(
                "google_sync.failed",
                extra={
                    "appointment_id": appointment.id,
                    "attempt": attempt,
                    "error": str(exc),
                },
            )
            return "failed"
        countdown = min(
            GOOGLE_SYNC_INITIAL_DELAY * (2 ** (attempt - 1)),
            GOOGLE_SYNC_MAX_DELAY,
        )
        logger.warning(
            "google_sync.retry_backoff",
            extra={
                "appointment_id": appointment.id,
                "attempt": attempt,
                "countdown": countdown,
                "error": str(exc),
            },
        )
        retry_google_calendar_sync.apply_async(
            args=[appointment.id],
            countdown=countdown,
            task_id=f"appt-google-sync-{appointment.id}-retry-{attempt}",
        )
        return "rescheduled"

    appointment.external_event_id = event.external_event_id
    appointment.sync_state = AppointmentSyncState.OK
    appointment.google_retry_count = 0
    appointment.google_last_error = ""
    appointment.save(
        update_fields=[
            "external_event_id",
            "sync_state",
            "google_retry_count",
            "google_last_error",
            "updated_at",
        ]
    )
    logger.info(
        "google_sync.synced",
        extra={"appointment_id": appointment.id, "external_event_id": event.external_event_id},
    )
    return "synced"


@shared_task
def sweep_tentative_google_syncs() -> int:
    """Periodic sweep to retry pending tentative appointments."""
    pending = (
        Appointment.objects.filter(
            sync_state=AppointmentSyncState.TENTATIVE,
            google_retry_count__lt=GOOGLE_SYNC_MAX_ATTEMPTS,
            external_event_id__isnull=True,
        )
        .order_by("updated_at")[:GOOGLE_SYNC_SWEEP_BATCH]
    )
    scheduled = 0
    for appointment in pending:
        if schedule_google_calendar_retry(appointment.id):
            scheduled += 1
    return scheduled


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
