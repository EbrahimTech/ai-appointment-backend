"""Domain models for the channels module."""

from django.db import models

from apps.clinics.models import Clinic, LanguageChoices
from apps.common.models import TimeStampedModel
from apps.conversations.models import Conversation


class ChannelType(models.TextChoices):
    """Primary supported messaging channels."""

    WHATSAPP = "whatsapp", "WhatsApp"


class HSMTemplateStatus(models.TextChoices):
    """Lifecycle status for WhatsApp HSM templates."""

    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class MessageType(models.TextChoices):
    """Categorise outbound messages for policy enforcement."""

    SESSION = "session", "Session"
    HSM = "hsm", "HSM"


class OutboxStatus(models.TextChoices):
    """Lifecycle status for queued outbound notifications."""

    PENDING = "pending", "Pending"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class ChannelAccount(TimeStampedModel):
    """Provider configuration per clinic and channel."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="channel_accounts"
    )
    channel = models.CharField(
        max_length=20, choices=ChannelType.choices, default=ChannelType.WHATSAPP
    )
    provider_name = models.CharField(max_length=50, default="generic")
    access_token = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("clinic", "channel")


class HSMTemplate(TimeStampedModel):
    """Clinic-specific WhatsApp HSM template definition."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="hsm_templates"
    )
    name = models.CharField(max_length=120)
    language = models.CharField(
        max_length=5, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )
    body = models.TextField()
    variables = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=HSMTemplateStatus.choices,
        default=HSMTemplateStatus.DRAFT,
    )
    provider_template_id = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("clinic", "name", "language")
        ordering = ["clinic_id", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.language})"


class OutboxMessage(TimeStampedModel):
    """Queue for outbound notifications (e.g. WhatsApp HSM)."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="outbox_messages"
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbox_messages",
    )
    message_type = models.CharField(
        max_length=10, choices=MessageType.choices, default=MessageType.HSM
    )
    channel = models.CharField(
        max_length=20, choices=ChannelType.choices, default=ChannelType.WHATSAPP
    )
    hsm_template = models.ForeignKey(
        HSMTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbox_messages",
    )
    payload = models.JSONField(default=dict, blank=True)
    scheduled_for = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=OutboxStatus.choices, default=OutboxStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, null=True, unique=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
            models.Index(fields=["idempotency_key"]),
        ]
        ordering = ["scheduled_for"]


class WebhookEvent(TimeStampedModel):
    """Raw inbound events captured from provider webhooks (WhatsApp)."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="webhook_events"
    )
    channel = models.CharField(
        max_length=20, choices=ChannelType.choices, default=ChannelType.WHATSAPP
    )
    provider_event_id = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
