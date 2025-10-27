"""Domain models for the webhooks module."""

from django.db import models

from apps.clinics.models import Clinic
from apps.common.models import TimeStampedModel
from apps.conversations.models import Conversation


class LeadWebhookEvent(TimeStampedModel):
    """Incoming lead payloads processed via signed webhook."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="lead_webhooks"
    )
    signature = models.CharField(max_length=255)
    payload = models.JSONField()
    dedupe_key = models.CharField(max_length=255, unique=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    related_conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_webhook_events",
    )

    class Meta:
        ordering = ["-created_at"]
