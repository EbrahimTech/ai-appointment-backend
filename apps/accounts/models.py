"""Accounts and tenancy models."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from uuid import uuid4

from apps.clinics.models import Clinic
from apps.common.models import TimeStampedModel


class ClinicMembership(TimeStampedModel):
    """Relationship between a user and a clinic with a role."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        ADMIN = "ADMIN", "Admin"
        STAFF = "STAFF", "Staff"
        VIEWER = "VIEWER", "Viewer"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="clinic_memberships")
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)

    class Meta:
        unique_together = ("user", "clinic")


class StaffAccount(TimeStampedModel):
    """HQ staff roles not tied to a specific clinic."""

    class Role(models.TextChoices):
        SUPERADMIN = "SUPERADMIN", "Super Admin"
        OPS = "OPS", "Ops"
        SUPPORT = "SUPPORT", "Support"
        SALES = "SALES", "Sales"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_account")
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self) -> str:
        return f"{self.user.email} ({self.role})"


class NotificationType(models.TextChoices):
    """Types of notifications emitted for clinic operators."""

    HANDOFF = "handoff", "Handoff"


class NotificationStatus(models.TextChoices):
    """Lifecycle of a notification."""

    NEW = "new", "New"
    READ = "read", "Read"


class Notification(TimeStampedModel):
    """Operator-facing alerts scoped to a clinic (e.g., handoff required)."""

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="notifications"
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    type = models.CharField(
        max_length=20, choices=NotificationType.choices, default=NotificationType.HANDOFF
    )
    status = models.CharField(
        max_length=10, choices=NotificationStatus.choices, default=NotificationStatus.NEW, db_index=True
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    patient_name = models.CharField(max_length=255, blank=True)
    patient_phone = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["clinic", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "type"],
                name="unique_notification_per_conversation_type",
                condition=models.Q(conversation__isnull=False),
            )
        ]

    def __str__(self) -> str:
        return f"Notification<{self.id}> {self.type} {self.status}"


class AuditLog(TimeStampedModel):
    """Audit records for critical actions."""

    class Scope(models.TextChoices):
        AUTH = "AUTH", "Auth"
        CLINIC = "CLINIC", "Clinic"
        HQ = "HQ", "HQ"

    actor_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    scope = models.CharField(max_length=10, choices=Scope.choices)
    clinic = models.ForeignKey(Clinic, null=True, blank=True, on_delete=models.SET_NULL)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


class SupportSession(TimeStampedModel):
    """Temporary HQ support impersonation sessions."""

    token_hash = models.CharField(max_length=128, unique=True)
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="support_sessions")
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="support_sessions")
    reason = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def is_active(self) -> bool:
        return self.active and self.expires_at >= timezone.now()


class Invitation(TimeStampedModel):
    """Owner invitation issued by HQ (or clinic admins)."""

    uid = models.UUIDField(default=uuid4, editable=False, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invitations")
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="invitations")
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "clinic")
        ordering = ["-created_at"]

    def is_active(self) -> bool:
        return self.accepted_at is None and self.expires_at >= timezone.now()
