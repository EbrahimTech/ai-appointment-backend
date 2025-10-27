"""Domain models for the llm module."""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.conversations.models import ConversationMessage
from apps.kb.models import KnowledgeChunk


class LLMProvider(models.TextChoices):
    """Supported language model providers."""

    DEEPSEEK = "deepseek", "DeepSeek"
    FALLBACK = "fallback", "Fallback"


class LLMRequestLog(TimeStampedModel):
    """Persists outbound LLM calls for audit and grounding validation."""

    provider = models.CharField(
        max_length=20, choices=LLMProvider.choices, default=LLMProvider.DEEPSEEK
    )
    model = models.CharField(max_length=100)
    prompt = models.TextField()
    response = models.TextField(blank=True)
    request_metadata = models.JSONField(default=dict, blank=True)
    response_metadata = models.JSONField(default=dict, blank=True)
    success = models.BooleanField(default=True)
    latency_ms = models.PositiveIntegerField(default=0)
    cost_estimate = models.DecimalField(max_digits=8, decimal_places=5, default=0)


class RetrievalLog(TimeStampedModel):
    """Records which chunks were used for RAG answers."""

    llm_log = models.ForeignKey(
        LLMRequestLog, on_delete=models.CASCADE, related_name="retrievals"
    )
    chunk = models.ForeignKey(
        KnowledgeChunk, on_delete=models.CASCADE, related_name="retrieval_logs"
    )
    relevance_score = models.FloatField(default=0.0)
    conversation_message = models.ForeignKey(
        ConversationMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retrieval_logs",
    )
