from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated tracking."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeletableModel(TimeStampedModel):
    """Provide soft delete semantics while keeping history."""

    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
