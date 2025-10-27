"""Domain models for the patients module."""

from apps.common.fields import CompatArrayField
from django.db import models

from apps.clinics.models import Clinic, LanguageChoices
from apps.common.models import TimeStampedModel


class Patient(TimeStampedModel):
    """Basic profile data for a patient or lead."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="patients"
    )
    full_name = models.CharField(max_length=255)
    language = models.CharField(
        max_length=2, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )
    phone_number = models.CharField(max_length=32)
    normalized_phone = models.CharField(max_length=32, db_index=True)
    email = models.EmailField(blank=True)
    tags = CompatArrayField(models.CharField(max_length=50), blank=True, default=list)

    class Meta:
        unique_together = ("clinic", "normalized_phone")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.full_name


class PatientNote(TimeStampedModel):
    """Internal notes captured by support agents or automations."""

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="notes"
    )
    author = models.CharField(max_length=255, blank=True)
    body = models.TextField()

    def __str__(self) -> str:
        return f"Note for {self.patient.full_name}"

