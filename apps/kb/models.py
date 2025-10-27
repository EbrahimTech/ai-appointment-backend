"""Domain models for the kb module."""

from django.db import models

from apps.clinics.models import Clinic, LanguageChoices
from apps.common.fields import CompatArrayField, CompatVectorField
from apps.common.models import TimeStampedModel


class KnowledgeDocument(TimeStampedModel):
    """Root knowledge asset uploaded by operators."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="knowledge_documents"
    )
    language = models.CharField(
        max_length=2, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )
    title = models.CharField(max_length=255)
    source = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_language_display()})"


class KnowledgeChunk(TimeStampedModel):
    """Chunked representation of a knowledge document with embeddings."""

    document = models.ForeignKey(
        KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = CompatVectorField(dimensions=1536, null=True, blank=True)
    score = models.FloatField(default=0.0)
    metadata = models.JSONField(default=dict, blank=True)
    language = models.CharField(
        max_length=2, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )
    tags = CompatArrayField(models.CharField(max_length=32), default=list, blank=True)

    class Meta:
        unique_together = ("document", "chunk_index")
        ordering = ["document_id", "chunk_index"]


class KnowledgeIndex(TimeStampedModel):
    """Tracks active vector indices per clinic."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="knowledge_indices"
    )
    name = models.CharField(max_length=100)
    dimensions = models.PositiveIntegerField(default=1536)
    is_active = models.BooleanField(default=True)
    retriever_config = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    documents = models.ManyToManyField(
        KnowledgeDocument, related_name="indices", blank=True
    )

    class Meta:
        unique_together = ("clinic", "name")
        ordering = ["clinic_id", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.dimensions}d)"
