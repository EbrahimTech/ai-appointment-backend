"""Domain models for the appointments module."""

from datetime import datetime, time, timedelta

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.indexes import GistIndex
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.clinics.models import Clinic, ClinicService
from apps.common.models import TimeStampedModel
from apps.patients.models import Patient


class AppointmentStatus(models.TextChoices):
    """Possible lifecycle states for an appointment."""

    PENDING = "pending", "Pending"
    BOOKED = "booked", "Booked"
    CONFIRMED = "confirmed", "Confirmed"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    RESCHEDULED = "rescheduled", "Rescheduled"


class AppointmentQuerySet(models.QuerySet):
    """Custom queryset helpers for appointments."""

    def booked(self):
        return self.filter(status=AppointmentStatus.BOOKED)

    def for_day(self, date_value):
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(date_value, time.min), tz)
        end = start + timedelta(days=1)
        return self.filter(slot__overlap=(start, end))


class Appointment(TimeStampedModel):
    """Scheduled time slot reserved for a clinic service."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="appointments"
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    service = models.ForeignKey(
        ClinicService,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    slot = DateTimeRangeField()
    status = models.CharField(
        max_length=16,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.PENDING,
    )
    source = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    external_event_id = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )

    objects = AppointmentQuerySet.as_manager()

    class Meta:
        ordering = ["slot"]
        indexes = [GistIndex(fields=["slot"])]
        constraints = [
            ExclusionConstraint(
                name="prevent_double_booking",
                expressions=[("clinic", "="), ("slot", "&&")],
                condition=Q(status=AppointmentStatus.BOOKED),
            ),
            models.UniqueConstraint(
                fields=["clinic", "external_event_id"],
                name="unique_external_event_per_clinic",
                condition=Q(external_event_id__isnull=False),
            ),
        ]

    @property
    def start_at(self):
        return self.slot.lower

    @property
    def end_at(self):
        return self.slot.upper
