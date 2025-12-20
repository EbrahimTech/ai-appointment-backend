from django.contrib import admin

from apps.conversations.models import Conversation
from apps.patients.models import Patient, PatientNote


class ConversationInline(admin.TabularInline):
    model = Conversation
    fields = ("id", "fsm_state", "handoff_required", "last_intent", "updated_at")
    readonly_fields = ("updated_at",)
    extra = 0
    show_change_link = True


class PatientNoteInline(admin.TabularInline):
    model = PatientNote
    fields = ("author", "body", "created_at")
    readonly_fields = ("created_at",)
    extra = 0
    show_change_link = True


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "phone_number",
        "clinic",
        "ai_enabled",
        "language",
        "created_at",
    )
    list_filter = ("clinic", "ai_enabled", "language", "gender", "blood_type", "created_at")
    search_fields = ("full_name", "phone_number", "normalized_phone", "email", "clinic__name")
    list_select_related = ("clinic",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [ConversationInline, PatientNoteInline]


@admin.register(PatientNote)
class PatientNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "author", "short_body", "created_at")
    list_filter = ("created_at",)
    search_fields = ("patient__full_name", "patient__phone_number", "author", "body")
    list_select_related = ("patient", "patient__clinic")
    ordering = ("-created_at",)
    raw_id_fields = ("patient",)
    readonly_fields = ("created_at", "updated_at")

    def short_body(self, obj: PatientNote) -> str:
        body = obj.body or ""
        return body if len(body) <= 80 else f"{body[:77]}..."

    short_body.short_description = "Body"
