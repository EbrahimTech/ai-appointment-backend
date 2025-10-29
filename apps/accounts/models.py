"""Accounts and tenancy models."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models

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
