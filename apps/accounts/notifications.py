"""Helper utilities for operator notifications."""

from __future__ import annotations

from apps.accounts.models import Notification, NotificationStatus, NotificationType
from apps.conversations.models import Conversation


def notify_handoff(conversation: Conversation) -> Notification:
    """Create (or reuse) a handoff notification for this conversation."""

    patient = getattr(conversation, "patient", None)
    patient_name = patient.full_name if patient else "Guest"
    patient_phone = patient.phone_number if patient else ""

    defaults = {
        "clinic": conversation.clinic,
        "patient": patient,
        "title": "Handoff required",
        "body": "The assistant paused this chat and needs a human follow-up.",
        "patient_name": patient_name,
        "patient_phone": patient_phone,
        "status": NotificationStatus.NEW,
    }

    notification, _ = Notification.objects.get_or_create(
        conversation=conversation,
        type=NotificationType.HANDOFF,
        defaults=defaults,
    )
    return notification
