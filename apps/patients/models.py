"""Domain models for the patients module."""

from apps.common.fields import CompatArrayField
from django.db import models

from apps.clinics.models import Clinic, LanguageChoices
from apps.common.models import TimeStampedModel


class Patient(TimeStampedModel):
    """Complete profile data for a patient."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="patients"
    )
    
    # Basic Information
    full_name = models.CharField(max_length=255)
    language = models.CharField(
        max_length=10, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )
    
    # Contact Information
    phone_number = models.CharField(max_length=32)
    normalized_phone = models.CharField(max_length=32, db_index=True)
    alternative_phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)
    
    # Personal Information
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
        blank=True
    )
    
    # Address Information
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    
    # Medical Information
    allergies = models.TextField(blank=True, help_text="List of known allergies")
    chronic_diseases = models.TextField(blank=True, help_text="List of chronic diseases")
    current_medications = models.TextField(blank=True, help_text="Current medications")
    blood_type = models.CharField(
        max_length=5,
        choices=[
            ("A+", "A+"), ("A-", "A-"),
            ("B+", "B+"), ("B-", "B-"),
            ("AB+", "AB+"), ("AB-", "AB-"),
            ("O+", "O+"), ("O-", "O-"),
        ],
        blank=True
    )
    
    # General Notes
    notes = models.TextField(blank=True, help_text="General notes about the patient")
    
    # Metadata
    tags = CompatArrayField(models.CharField(max_length=50), blank=True, default=list)

    class Meta:
        unique_together = ("clinic", "normalized_phone")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.full_name
    
    @property
    def age(self) -> int | None:
        """Calculate patient age from date of birth."""
        if self.date_of_birth:
            from datetime import date
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None


class PatientNote(TimeStampedModel):
    """Internal notes captured by support agents or automations."""

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="patient_notes"
    )
    author = models.CharField(max_length=255, blank=True)
    body = models.TextField()

    def __str__(self) -> str:
        return f"Note for {self.patient.full_name}"

