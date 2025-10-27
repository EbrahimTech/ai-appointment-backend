"""Domain models for the calendars module."""

from django.db import models

from apps.appointments.models import Appointment
from apps.clinics.models import Clinic
from apps.common.models import TimeStampedModel
from apps.common.security import decrypt_secret, encrypt_secret, is_encrypted_secret


class GoogleCredential(TimeStampedModel):
    """OAuth tokens for syncing with Google Calendar."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="google_credentials"
    )
    account_email = models.EmailField()
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_at = models.DateTimeField()
    scopes = models.JSONField(default=list, blank=True)
    calendar_id = models.CharField(max_length=255, default="primary")

    class Meta:
        unique_together = ("clinic", "account_email")

    def __str__(self) -> str:
        return f"{self.account_email} ({self.clinic.name})"

    def save(self, *args, **kwargs):
        if self.access_token and not is_encrypted_secret(self.access_token):
            self.access_token = encrypt_secret(self.access_token)
        if self.refresh_token and not is_encrypted_secret(self.refresh_token):
            self.refresh_token = encrypt_secret(self.refresh_token)
        super().save(*args, **kwargs)

    def get_access_token(self) -> str:
        return decrypt_secret(self.access_token)

    def get_refresh_token(self) -> str:
        return decrypt_secret(self.refresh_token)


class CalendarEvent(TimeStampedModel):
    """Mirror of calendar events synced to third-party providers."""

    appointment = models.OneToOneField(
        Appointment, on_delete=models.CASCADE, related_name="calendar_event"
    )
    external_event_id = models.CharField(max_length=255, unique=True)
    provider = models.CharField(max_length=50, default="google")
    sync_status = models.CharField(max_length=20, default="created")
    payload = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_event_id}"


class CalendarSyncLog(TimeStampedModel):
    """Auditable trail of create/cancel operations pushed to providers."""

    calendar_event = models.ForeignKey(
        CalendarEvent, on_delete=models.CASCADE, related_name="sync_logs"
    )
    action = models.CharField(max_length=20)
    success = models.BooleanField(default=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
