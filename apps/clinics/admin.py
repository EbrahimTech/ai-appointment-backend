from django.contrib import admin

from apps.clinics.models import Clinic, ClinicService, ServiceHours
from apps.patients.models import Patient


class PatientInline(admin.TabularInline):
    model = Patient
    fields = ("full_name", "phone_number", "language", "ai_enabled", "created_at")
    readonly_fields = ("created_at",)
    extra = 0
    show_change_link = True


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "tz",
        "ai_enabled",
        "default_lang",
        "updated_at",
    )
    list_filter = ("ai_enabled", "default_lang", "tz")
    search_fields = ("name", "slug", "phone_number", "whatsapp_number")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [PatientInline]


@admin.register(ClinicService)
class ClinicServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "clinic",
        "code",
        "name",
        "duration_minutes",
        "language",
        "is_active",
    )
    list_filter = ("clinic", "language", "is_active")
    search_fields = ("name", "code", "clinic__name")
    list_select_related = ("clinic",)
    ordering = ("clinic_id", "name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ServiceHours)
class ServiceHoursAdmin(admin.ModelAdmin):
    list_display = ("id", "clinic", "service", "weekday", "start_time", "end_time")
    list_filter = ("clinic", "weekday")
    search_fields = ("service__name", "clinic__name")
    list_select_related = ("clinic", "service")
    ordering = ("service_id", "weekday", "start_time")
    readonly_fields = ("created_at", "updated_at")
