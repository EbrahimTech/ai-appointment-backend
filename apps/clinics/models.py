"""Domain models for the clinics module."""

from django.db import models

from apps.common.models import SoftDeletableModel, TimeStampedModel


class LanguageChoices(models.TextChoices):
    """Supported languages for multi-lingual content."""

    ENGLISH = "en", "English"
    ARABIC = "ar", "Arabic"


class WeekdayChoices(models.IntegerChoices):
    """Weekday enumeration aligned with Python's weekday numbering."""

    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class Clinic(TimeStampedModel):
    """Clinic-specific configuration and contact information."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    timezone = models.CharField(max_length=64, default="UTC")
    phone_number = models.CharField(max_length=32, blank=True)
    whatsapp_number = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ClinicService(SoftDeletableModel):
    """Services offered by the clinic with localized descriptors."""

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="services")
    code = models.CharField(max_length=100, blank=True, default="")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
    language = models.CharField(
        max_length=2, choices=LanguageChoices.choices, default=LanguageChoices.ENGLISH
    )

    class Meta:
        unique_together = ("clinic", "code", "language")
        ordering = ["clinic_id", "name"]

    def __str__(self) -> str:
        return f"{self.clinic.name}: {self.code} ({self.get_language_display()})"


class ServiceHours(TimeStampedModel):
    """Office hours for each service by weekday."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="service_hours"
    )
    service = models.ForeignKey(
        ClinicService, on_delete=models.CASCADE, related_name="hours"
    )
    weekday = models.PositiveSmallIntegerField(choices=WeekdayChoices.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ("service", "weekday", "start_time")
        ordering = ["service_id", "weekday", "start_time"]

    def __str__(self) -> str:
        return (
            f"{self.service} {self.get_weekday_display()} "
            f"{self.start_time}-{self.end_time}"
        )
