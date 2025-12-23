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


class DialogTurnLog(TimeStampedModel):
    """Structured log per inbound turn for debugging and analysis."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="turn_logs"
    )
    message = models.ForeignKey(
        ConversationMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="turn_logs",
    )
    intent_predicted = models.CharField(max_length=100, blank=True)
    intent_confidence = models.FloatField(default=0)
    state = models.CharField(max_length=50, blank=True)
    slots = models.JSONField(default=dict, blank=True)
    missing_slots = models.JSONField(default=list, blank=True)
    handoff_reason = models.CharField(max_length=100, blank=True)
    validator_fail_reason = models.CharField(max_length=100, blank=True)
    llm_calls = models.PositiveIntegerField(default=0)
    llm_tokens = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
