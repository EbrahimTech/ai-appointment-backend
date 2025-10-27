"""Domain models for the conversations module."""

from django.db import models

from apps.clinics.models import Clinic, LanguageChoices
from apps.common.models import TimeStampedModel
from apps.patients.models import Patient


class MessageDirection(models.TextChoices):
    """Flow direction for a message record."""

    INBOUND = "inbound", "Inbound"
    OUTBOUND = "outbound", "Outbound"


class Conversation(TimeStampedModel):
    """Orchestrates the dialog finite-state-machine per patient."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="conversations"
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )
    lead_source = models.CharField(max_length=100, blank=True)
    fsm_state = models.CharField(max_length=50, default="idle")
    topic_state = models.CharField(max_length=50, default="default")
    handoff_required = models.BooleanField(default=False)
    last_intent = models.CharField(max_length=100, blank=True)
    dedupe_key = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Conversation<{self.pk}> {self.fsm_state}"


class ConversationMessage(TimeStampedModel):
    """Individual inbound/outbound WhatsApp messages."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    direction = models.CharField(
        max_length=10, choices=MessageDirection.choices, db_index=True
    )
    language = models.CharField(
        max_length=2, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )
    body = models.TextField()
    normalized_body = models.TextField(blank=True)
    intent = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    llm_response_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at"]


class SessionState(TimeStampedModel):
    """Conversation memory used by the FSM and LLM router."""

    conversation = models.OneToOneField(
        Conversation, on_delete=models.CASCADE, related_name="session_state"
    )
    slot_offer_payload = models.JSONField(default=dict, blank=True)
    last_nudged_at = models.DateTimeField(null=True, blank=True)
    context = models.JSONField(default=dict, blank=True)
    llm_guardrails = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"State<{self.conversation_id}>"
