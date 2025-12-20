from django.contrib import admin

from apps.channels.models import OutboxMessage


@admin.register(OutboxMessage)
class OutboxMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "clinic",
        "conversation",
        "message_type",
        "status",
        "channel",
        "provider_message_id",
        "created_at",
    )
    list_filter = ("status", "message_type", "channel", "clinic", "created_at")
    search_fields = (
        "idempotency_key",
        "last_error",
        "conversation__id",
        "conversation__patient__phone_number",
        "conversation__patient__normalized_phone",
        "clinic__name",
    )
    list_select_related = ("clinic", "conversation", "hsm_template")
    ordering = ("-created_at",)
    raw_id_fields = ("clinic", "conversation", "hsm_template")
    readonly_fields = ("created_at", "updated_at")

    def provider_message_id(self, obj: OutboxMessage) -> str:
        payload = obj.payload or {}
        if isinstance(payload, dict):
            return payload.get("provider_message_id") or payload.get("id") or ""
        return ""

    provider_message_id.short_description = "Provider ID"
