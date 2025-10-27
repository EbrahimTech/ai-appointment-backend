"""Domain models for the templates module."""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.clinics.models import Clinic, LanguageChoices
from apps.common.models import SoftDeletableModel


class TemplateCategory(models.TextChoices):
    """Label templates for their downstream usage."""

    WHATSAPP = "whatsapp", "WhatsApp"
    SMS = "sms", "SMS"
    EMAIL = "email", "Email"
    INTERNAL = "internal", "Internal"


class MessageTemplate(SoftDeletableModel):
    """Provider-agnostic message template storage."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="message_templates"
    )
    code = models.CharField(max_length=100)
    language = models.CharField(
        max_length=2, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )
    category = models.CharField(
        max_length=20, choices=TemplateCategory.choices, default=TemplateCategory.WHATSAPP
    )
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    variables = ArrayField(
        models.CharField(max_length=64), default=list, blank=True, help_text="Template placeholders"
    )
    provider_template_id = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("clinic", "code", "language")
        ordering = ["clinic_id", "code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.get_language_display()})"
