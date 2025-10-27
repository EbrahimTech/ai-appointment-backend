"""Domain models for the dialog module."""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.conversations.models import Conversation, ConversationMessage


class DialogTransition(TimeStampedModel):
    """Records FSM transitions for observability and analytics."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="transitions"
    )
    from_state = models.CharField(max_length=50)
    to_state = models.CharField(max_length=50)
    trigger = models.CharField(max_length=50)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


class TopicCorridorEvent(TimeStampedModel):
    """Logs nudges and escalations triggered by topic corridor enforcement."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="topic_events"
    )
    message = models.ForeignKey(
        ConversationMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="topic_events",
    )
    violation_count = models.PositiveIntegerField(default=0)
    action = models.CharField(max_length=50)
    notes = models.TextField(blank=True)
