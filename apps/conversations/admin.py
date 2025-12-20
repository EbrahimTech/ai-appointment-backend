from django.contrib import admin

from apps.conversations.models import Conversation, ConversationMessage, SessionState


class ConversationMessageInline(admin.TabularInline):
    model = ConversationMessage
    fields = ("direction", "language", "short_body", "created_at")
    readonly_fields = ("short_body", "created_at")
    extra = 0
    show_change_link = True

    def short_body(self, obj: ConversationMessage) -> str:
        body = obj.body or ""
        return body if len(body) <= 80 else f"{body[:77]}..."

    short_body.short_description = "Body"


class SessionStateInline(admin.StackedInline):
    model = SessionState
    fields = ("last_nudged_at", "slot_offer_payload", "context", "llm_guardrails", "updated_at")
    readonly_fields = ("last_nudged_at", "slot_offer_payload", "context", "llm_guardrails", "updated_at")
    can_delete = False
    extra = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "clinic",
        "patient",
        "fsm_state",
        "handoff_required",
        "last_intent",
        "updated_at",
    )
    list_filter = ("clinic", "handoff_required", "fsm_state", "created_at")
    search_fields = (
        "dedupe_key",
        "patient__full_name",
        "patient__phone_number",
        "patient__normalized_phone",
        "last_intent",
    )
    list_select_related = ("clinic", "patient")
    ordering = ("-updated_at",)
    raw_id_fields = ("patient",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [SessionStateInline, ConversationMessageInline]


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "direction",
        "language",
        "short_body",
        "created_at",
    )
    list_filter = ("direction", "language", "created_at", "conversation__clinic")
    search_fields = ("body", "normalized_body", "intent", "conversation__id")
    list_select_related = ("conversation", "conversation__clinic", "conversation__patient")
    ordering = ("-created_at",)
    raw_id_fields = ("conversation",)
    readonly_fields = ("created_at", "updated_at")

    def short_body(self, obj: ConversationMessage) -> str:
        body = obj.body or ""
        return body if len(body) <= 80 else f"{body[:77]}..."

    short_body.short_description = "Body"


@admin.register(SessionState)
class SessionStateAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "last_nudged_at", "updated_at")
    list_filter = ("last_nudged_at", "updated_at")
    search_fields = ("conversation__id", "conversation__patient__full_name")
    list_select_related = ("conversation", "conversation__clinic", "conversation__patient")
    ordering = ("-updated_at",)
    raw_id_fields = ("conversation",)
    readonly_fields = ("created_at", "updated_at")
