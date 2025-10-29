"""Tenant-scoped portal APIs (dashboards, conversations, appointments)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import yaml
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.db.models.query import Prefetch, QuerySet
from django.utils import timezone
from rest_framework import permissions
from rest_framework.views import APIView
from django.conf import settings

from apps.accounts.decorators import require_clinic_role, require_hq_role
from apps.accounts.models import AuditLog, ClinicMembership
from apps.appointments.models import Appointment, AppointmentStatus, AppointmentSyncState
from apps.channels.models import (
    ChannelType,
    HSMTemplate,
    HSMTemplateStatus,
    MessageType,
    OutboxMessage,
    OutboxStatus,
    ChannelAccount,
)
from apps.calendars.models import CalendarEvent, GoogleCredential
from apps.calendars.services import GoogleCalendarService, GoogleCalendarServiceError
from apps.clinics.models import Clinic, ClinicService, ServiceHours, LanguageChoices
from apps.common.api import error_response, ok_response
from apps.conversations.models import Conversation, ConversationMessage, MessageDirection
from apps.kb.models import KnowledgeChunk, KnowledgeDocument, KnowledgeIndex
from apps.templates.models import MessageTemplate, TemplateCategory
from apps.channels.services import (
    DEFAULT_SESSION_FALLBACK_HSM,
    SESSION_WINDOW_HOURS,
    enqueue_whatsapp_message,
)
from apps.workers.tasks import schedule_google_calendar_retry


class ClinicDashboardView(APIView):
    """Return per-clinic operational metrics."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        data = _clinic_dashboard_payload(clinic)
        return ok_response(data)


class ClinicConversationListView(APIView):
    """List conversations scoped to a clinic with filtering and pagination."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        query_params = request.GET
        qs = (
            Conversation.objects.filter(clinic=clinic)
            .select_related("patient")
            .annotate(last_message_at=Max("messages__created_at"))
        )

        status_param = (query_params.get("status") or "").lower()
        if status_param:
            qs = _filter_conversation_status(qs, status_param)

        intent = query_params.get("intent")
        if intent:
            qs = qs.filter(last_intent__iexact=intent.strip())

        lang = query_params.get("lang")
        if lang:
            qs = qs.filter(patient__language__iexact=lang.strip())

        dt_from = _parse_clinic_iso_datetime(query_params.get("from"), clinic)
        if dt_from:
            qs = qs.filter(created_at__gte=dt_from)

        dt_to = _parse_clinic_iso_datetime(query_params.get("to"), clinic)
        if dt_to:
            qs = qs.filter(created_at__lte=dt_to)

        search = (query_params.get("q") or "").strip()
        if search:
            qs = qs.filter(
                Q(patient__phone_number__icontains=search)
                | Q(patient__normalized_phone__icontains=search)
                | Q(messages__body__icontains=search)
            ).distinct()

        page = _positive_int(query_params.get("page"), default=1)
        size = _bounded_positive_int(query_params.get("size"), default=20, maximum=100)
        total = qs.count()

        offset = (page - 1) * size
        items = [
            _serialize_conversation_summary(conversation, clinic)
            for conversation in qs.order_by("-updated_at")[offset : offset + size]
        ]

        data = {"items": items, "page": page, "size": size, "total": total}
        return ok_response(data)


class ClinicConversationDetailView(APIView):
    """Return conversation details including recent messages."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str, pk: int):
        clinic: Clinic = request.clinic
        conversation = (
            Conversation.objects.filter(clinic=clinic, pk=pk)
            .select_related("patient")
            .prefetch_related(
                Prefetch(
                    "messages",
                    queryset=ConversationMessage.objects.order_by("created_at"),
                )
            )
            .first()
        )
        if conversation is None:
            return error_response("NOT_FOUND", status_code=404)

        payload = {
            "id": conversation.id,
            "intent": conversation.last_intent or "",
            "lang": _conversation_language(conversation, clinic),
            "fsm_state": conversation.fsm_state,
            "handoff": conversation.handoff_required,
            "messages": [
                {
                    "id": message.id,
                    "dir": "in" if message.direction == MessageDirection.INBOUND else "out",
                    "text": message.body,
                    "ts": message.created_at.isoformat(),
                }
                for message in conversation.messages.all()
            ],
        }
        return ok_response(payload)

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str, pk: int):
        clinic: Clinic = request.clinic
        data = request.data or {}
        template_key = str(data.get("template_key", "")).strip()
        if not template_key:
            return error_response("INVALID_TEMPLATE", status_code=400)

        variables_raw = data.get("variables") or {}
        if variables_raw is None:
            variables_raw = {}
        if not isinstance(variables_raw, dict):
            return error_response("LINT_FAILED", status_code=400)

        with transaction.atomic():
            conversation = (
                Conversation.objects.select_for_update()
                .select_related("patient")
                .filter(clinic=clinic, pk=pk)
                .first()
            )
            if conversation is None:
                return error_response("NOT_FOUND", status_code=404)

            language = _conversation_language(conversation, clinic)
            template = (
                MessageTemplate.objects.filter(
                    clinic=clinic,
                    code=template_key,
                    language=language,
                    is_active=True,
                ).first()
            )
            if template is None:
                return error_response("INVALID_TEMPLATE", status_code=400)

            variables = _normalize_variables(variables_raw)
            expected = template.variables or []
            missing = _missing_variables(expected, variables)
            if missing:
                return error_response("LINT_FAILED", status_code=400)

            rendered_body = _render_template_body(template.body, variables)
            if "{{" in rendered_body and expected:
                return error_response("LINT_FAILED", status_code=400)

            requires_hsm = _requires_hsm(conversation)
            template_hsm_name = (template.metadata or {}).get("hsm_name") or template.code

            hsm_template = None
            outbound_body = rendered_body
            hsm_name_to_use = template_hsm_name or DEFAULT_SESSION_FALLBACK_HSM

            if requires_hsm:
                hsm_template = _select_hsm_template(
                    clinic_id=clinic.id,
                    name=template_hsm_name,
                    language=language,
                )
                if hsm_template is None and DEFAULT_SESSION_FALLBACK_HSM:
                    hsm_template = _select_hsm_template(
                        clinic_id=clinic.id,
                        name=DEFAULT_SESSION_FALLBACK_HSM,
                        language=language,
                    )
                if hsm_template is None:
                    return error_response("NO_HSM_AVAILABLE", status_code=400)
                outbound_body = _render_template_body(hsm_template.body, variables)
                hsm_name_to_use = hsm_template.name

            idempotency_key = _build_idempotency_key(
                conversation_id=conversation.id,
                template_key=template.code,
                variables=variables,
            )

            try:
                outbox = enqueue_whatsapp_message(
                    clinic_id=clinic.id,
                    conversation=conversation,
                    language=language,
                    message_body=rendered_body,
                    hsm_name=hsm_name_to_use or DEFAULT_SESSION_FALLBACK_HSM,
                    variables=variables,
                    idempotency_key=idempotency_key,
                )
            except Exception:
                return error_response("OUTBOX_ERROR", status_code=500)

            if requires_hsm and (
                outbox.message_type != MessageType.HSM or outbox.hsm_template_id is None
            ):
                return error_response("NO_HSM_AVAILABLE", status_code=400)

            conversation_message = ConversationMessage.objects.create(
                conversation=conversation,
                direction=MessageDirection.OUTBOUND,
                language=language,
                body=outbound_body,
                intent="template_reply",
                metadata={
                    "template_key": template.code,
                    "variables": variables,
                    "outbox_id": outbox.id,
                    "message_type": outbox.message_type,
                },
            )

            if (
                not conversation.handoff_required
                and (conversation.fsm_state or "").lower() == "done"
            ):
                conversation.fsm_state = "idle"
                conversation.save(update_fields=["fsm_state", "updated_at"])
            else:
                conversation.save(update_fields=["updated_at"])

            AuditLog.objects.create(
                actor_user=request.user if getattr(request, "user", None) else None,
                action="CONVERSATION_REPLY",
                scope=AuditLog.Scope.CLINIC,
                clinic=clinic,
                meta={"conversation_id": conversation.id, "template_key": template.code},
            )

            return ok_response({"message_id": conversation_message.id})


class ClinicAppointmentListView(APIView):
    """Return paginated appointments for a clinic (read-only)."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        params = request.GET
        from_dt = _parse_clinic_iso_datetime(params.get("from"), clinic)
        to_dt = _parse_clinic_iso_datetime(params.get("to"), clinic)

        records = list(
            clinic.appointments.select_related("service").order_by("created_at", "id")
        )

        if from_dt:
            records = [
                appt for appt in records if appt.start_at and appt.start_at >= from_dt
            ]
        if to_dt:
            records = [
                appt for appt in records if appt.end_at and appt.end_at <= to_dt
            ]

        page = _positive_int(params.get("page"), default=1)
        size = _bounded_positive_int(params.get("size"), default=50, maximum=200)
        total = len(records)

        offset = (page - 1) * size
        paginated = records[offset : offset + size]
        items = [
            {
                "id": appt.id,
                "service_code": appt.service.code if appt.service else "",
                "start_at": appt.start_at.isoformat() if appt.start_at else None,
                "end_at": appt.end_at.isoformat() if appt.end_at else None,
                "status": appt.status,
                "external_event_id": appt.external_event_id,
            }
            for appt in paginated
        ]

        data = {"items": items, "page": page, "size": size, "total": total}
        return ok_response(data)


class ClinicAppointmentCreateView(APIView):
    """Create appointments while enforcing clinic policies."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        patient_id = payload.get("patient_id")
        service_code = str(payload.get("service_code", "")).strip()
        start_iso = payload.get("start_at_iso")

        if not patient_id or not service_code or not start_iso:
            return error_response("INVALID_SERVICE", status_code=400)

        patient = clinic.patients.filter(id=patient_id).first()
        if patient is None:
            return error_response("INVALID_SERVICE", status_code=400)

        service = _get_service_by_code(clinic, service_code)
        if service is None:
            return error_response("INVALID_SERVICE", status_code=400)

        start_local = _parse_clinic_datetime(start_iso, clinic)
        if start_local is None:
            return error_response("OUT_OF_HOURS", status_code=400)

        duration = timedelta(minutes=service.duration_minutes)
        end_local = start_local + duration

        if not _is_within_service_hours(service, start_local, end_local):
            return error_response("OUT_OF_HOURS", status_code=400)

        google_available, google_failed = _check_google_availability(
            clinic, start_local, end_local
        )

        if not google_available:
            return error_response("SLOT_TAKEN", status_code=409)

        start_utc = start_local.astimezone(dt_timezone.utc)
        end_utc = end_local.astimezone(dt_timezone.utc)

        with transaction.atomic():
            if _has_overlap(clinic, service, start_utc, end_utc):
                return error_response("SLOT_TAKEN", status_code=409)
            try:
                appointment = Appointment.objects.create(
                    clinic=clinic,
                    patient=patient,
                    service=service,
                    slot=(start_utc, end_utc),
                    status=AppointmentStatus.BOOKED,
                )
            except IntegrityError:
                return error_response("SLOT_TAKEN", status_code=409)

        warning = None
        credential = _get_google_credential(clinic)

        if google_failed:
            appointment.sync_state = AppointmentSyncState.TENTATIVE
            appointment.google_retry_count = 0
            appointment.google_last_error = "google_sync_pending"
            appointment.save(
                update_fields=["sync_state", "google_retry_count", "google_last_error", "updated_at"]
            )
            warning = "GOOGLE_TENTATIVE"
            schedule_google_calendar_retry(appointment.id)
        elif credential:
            try:
                calendar_event = GoogleCalendarService().create_event(appointment, credential)
                appointment.external_event_id = calendar_event.external_event_id
                appointment.sync_state = AppointmentSyncState.OK
                appointment.google_retry_count = 0
                appointment.google_last_error = ""
                appointment.save(
                    update_fields=[
                        "external_event_id",
                        "sync_state",
                        "google_retry_count",
                        "google_last_error",
                        "updated_at",
                    ]
                )
            except GoogleCalendarServiceError:
                appointment.sync_state = AppointmentSyncState.TENTATIVE
                appointment.google_retry_count = 1
                appointment.google_last_error = "google_sync_error"
                appointment.save(
                    update_fields=["sync_state", "google_retry_count", "google_last_error", "updated_at"]
                )
                warning = "GOOGLE_TENTATIVE"
                schedule_google_calendar_retry(appointment.id)
        else:
            appointment.sync_state = AppointmentSyncState.OK
            appointment.google_retry_count = 0
            appointment.google_last_error = ""
            appointment.save(
                update_fields=["sync_state", "google_retry_count", "google_last_error", "updated_at"]
            )

        data = {"appointment": _serialize_appointment(appointment)}
        if warning:
            data["error"] = warning
        return ok_response(data)


class ClinicAppointmentRescheduleView(APIView):
    """Reschedule existing appointments, re-syncing calendars."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        appointment_id = payload.get("id")
        new_start_iso = payload.get("new_start_at_iso")
        if not appointment_id or not new_start_iso:
            return error_response("INVALID_SERVICE", status_code=400)

        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update()
                .select_related("service", "patient", "calendar_event")
                .filter(clinic=clinic, id=appointment_id)
                .first()
            )
            if appointment is None or appointment.service is None:
                return error_response("INVALID_SERVICE", status_code=400)

            service = appointment.service
            start_local = _parse_clinic_datetime(new_start_iso, clinic)
            if start_local is None:
                return error_response("OUT_OF_HOURS", status_code=400)

            duration = timedelta(minutes=service.duration_minutes)
            end_local = start_local + duration
            if not _is_within_service_hours(service, start_local, end_local):
                return error_response("OUT_OF_HOURS", status_code=400)

            google_available, google_failed = _check_google_availability(
                clinic, start_local, end_local, exclude_appointment=appointment
            )
            if not google_available:
                return error_response("SLOT_TAKEN", status_code=409)

            start_utc = start_local.astimezone(dt_timezone.utc)
            end_utc = end_local.astimezone(dt_timezone.utc)

            if _has_overlap(clinic, service, start_utc, end_utc, exclude=appointment.id):
                return error_response("SLOT_TAKEN", status_code=409)

            appointment.slot = (start_utc, end_utc)
            appointment.status = AppointmentStatus.BOOKED
            appointment.save(update_fields=["slot", "status", "updated_at"])

        warning = None
        credential = _get_google_credential(clinic)
        calendar_event = getattr(appointment, "calendar_event", None)

        if google_failed:
            appointment.sync_state = AppointmentSyncState.TENTATIVE
            appointment.google_last_error = "google_sync_pending"
            appointment.save(
                update_fields=["sync_state", "google_last_error", "updated_at"]
            )
            warning = "GOOGLE_TENTATIVE"
            schedule_google_calendar_retry(appointment.id)
        elif credential:
            try:
                if calendar_event:
                    GoogleCalendarService().cancel_event(calendar_event, credential)
                    calendar_event.delete()
                new_event = GoogleCalendarService().create_event(appointment, credential)
                appointment.external_event_id = new_event.external_event_id
                appointment.sync_state = AppointmentSyncState.OK
                appointment.google_retry_count = 0
                appointment.google_last_error = ""
                appointment.save(
                    update_fields=[
                        "external_event_id",
                        "sync_state",
                        "google_retry_count",
                        "google_last_error",
                        "updated_at",
                    ]
                )
            except GoogleCalendarServiceError:
                appointment.sync_state = AppointmentSyncState.TENTATIVE
                appointment.google_retry_count += 1
                appointment.google_last_error = "google_sync_error"
                appointment.save(
                    update_fields=["sync_state", "google_retry_count", "google_last_error", "updated_at"]
                )
                warning = "GOOGLE_TENTATIVE"
                schedule_google_calendar_retry(appointment.id)
        else:
            appointment.sync_state = AppointmentSyncState.OK
            appointment.google_retry_count = 0
            appointment.google_last_error = ""
            appointment.save(
                update_fields=["sync_state", "google_retry_count", "google_last_error", "updated_at"]
            )

        data = {"appointment": _serialize_appointment(appointment)}
        if warning:
            data["error"] = warning
        return ok_response(data)


class ClinicAppointmentCancelView(APIView):
    """Cancel appointments and sync external calendars."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        appointment_id = payload.get("id")
        if not appointment_id:
            return error_response("INVALID_SERVICE", status_code=400)

        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update()
                .select_related("calendar_event")
                .filter(clinic=clinic, id=appointment_id)
                .first()
            )
            if appointment is None:
                return error_response("INVALID_SERVICE", status_code=400)

            calendar_event = getattr(appointment, "calendar_event", None)
            appointment.status = AppointmentStatus.CANCELLED
            appointment.external_event_id = None
            appointment.sync_state = AppointmentSyncState.OK
            appointment.google_retry_count = 0
            appointment.google_last_error = ""
            appointment.save(
                update_fields=[
                    "status",
                    "external_event_id",
                    "sync_state",
                    "google_retry_count",
                    "google_last_error",
                    "updated_at",
                ]
            )

        warning = None
        credential = _get_google_credential(clinic)
        if calendar_event and credential:
            try:
                GoogleCalendarService().cancel_event(calendar_event, credential)
            except GoogleCalendarServiceError:
                warning = "GOOGLE_TENTATIVE"
            finally:
                calendar_event.delete()

        data: Dict[str, object] = {}
        if warning:
            data["error"] = warning
        return ok_response(data)


class ClinicServiceAdminView(APIView):
    """Clinic service catalog management."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        services = clinic.services.order_by("code", "language")
        items = [
            {
                "code": service.code,
                "name": service.name,
                "description": service.description,
                "duration_minutes": service.duration_minutes,
                "language": service.language,
                "is_active": service.is_active,
            }
            for service in services
        ]
        return ok_response({"items": items})

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def put(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        services_payload = payload.get("services")
        if not isinstance(services_payload, list):
            return error_response("INVALID_PAYLOAD", status_code=400)

        updated: List[ClinicService] = []
        with transaction.atomic():
            for entry in services_payload:
                if not isinstance(entry, dict):
                    return error_response("INVALID_PAYLOAD", status_code=400)
                code = str(entry.get("code", "")).strip()
                name = str(entry.get("name", "")).strip()
                language = str(entry.get("language", clinic.default_lang)).strip() or clinic.default_lang
                duration = entry.get("duration_minutes")
                description = str(entry.get("description", "")).strip()
                is_active = bool(entry.get("is_active", True))

                if not code or not name:
                    return error_response("INVALID_SERVICE", status_code=400)
                try:
                    duration_minutes = int(duration)
                except (TypeError, ValueError):
                    return error_response("INVALID_SERVICE", status_code=400)
                if duration_minutes <= 0:
                    return error_response("INVALID_SERVICE", status_code=400)

                service, _ = ClinicService.objects.update_or_create(
                    clinic=clinic,
                    code=code,
                    language=language,
                    defaults={
                        "name": name,
                        "description": description,
                        "duration_minutes": duration_minutes,
                        "is_active": is_active,
                    },
                )
                updated.append(service)

        items = [
            {
                "code": service.code,
                "name": service.name,
                "description": service.description,
                "duration_minutes": service.duration_minutes,
                "language": service.language,
                "is_active": service.is_active,
            }
            for service in clinic.services.order_by("code", "language")
        ]
        return ok_response({"items": items})


class ClinicHoursAdminView(APIView):
    """Manage clinic service hours."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        hours = clinic.service_hours.select_related("service").order_by("service__code", "weekday", "start_time")
        items = [
            {
                "service_code": hour.service.code,
                "weekday": hour.weekday,
                "start_time": hour.start_time.isoformat(),
                "end_time": hour.end_time.isoformat(),
            }
            for hour in hours
        ]
        return ok_response({"items": items})

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def put(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        hours_payload = payload.get("hours")
        if not isinstance(hours_payload, list):
            return error_response("INVALID_PAYLOAD", status_code=400)

        parsed_entries = []
        hours_by_service_weekday: Dict[Tuple[str, int], List[Tuple[datetime, datetime]]] = {}

        for entry in hours_payload:
            if not isinstance(entry, dict):
                return error_response("INVALID_PAYLOAD", status_code=400)
            service_code = str(entry.get("service_code", "")).strip()
            weekday = entry.get("weekday")
            start_raw = entry.get("start_time")
            end_raw = entry.get("end_time")

            if not service_code or weekday is None or start_raw is None or end_raw is None:
                return error_response("INVALID_HOURS", status_code=400)

            service = clinic.services.filter(code=service_code).first()
            if service is None:
                return error_response("INVALID_SERVICE", status_code=400)
            try:
                weekday_int = int(weekday)
            except (TypeError, ValueError):
                return error_response("INVALID_HOURS", status_code=400)
            if weekday_int < 0 or weekday_int > 6:
                return error_response("INVALID_HOURS", status_code=400)

            try:
                start_dt = datetime.strptime(start_raw, "%H:%M").time()
                end_dt = datetime.strptime(end_raw, "%H:%M").time()
            except ValueError:
                return error_response("INVALID_HOURS", status_code=400)

            if end_dt <= start_dt:
                return error_response("INVALID_HOURS", status_code=400)

            key = (service_code, weekday_int)
            existing = hours_by_service_weekday.setdefault(key, [])

            for existing_start, existing_end in existing:
                if (start_dt < existing_end and end_dt > existing_start):
                    return error_response("INVALID_HOURS", status_code=400)

            existing.append((start_dt, end_dt))
            parsed_entries.append((service, weekday_int, start_dt, end_dt))

        with transaction.atomic():
            ServiceHours.objects.filter(service__clinic=clinic).delete()
            for service, weekday_int, start_dt, end_dt in parsed_entries:
                ServiceHours.objects.create(
                    clinic=clinic,
                    service=service,
                    weekday=weekday_int,
                    start_time=start_dt,
                    end_time=end_dt,
                )

        return self.get(request, slug)


class ClinicTemplateAdminView(APIView):
    """Manage clinic templates (enable/disable and variables)."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        templates = clinic.message_templates.order_by("code", "language")
        items = [
            {
                "code": template.code,
                "language": template.language,
                "body": template.body,
                "variables": template.variables or [],
                "is_active": template.is_active,
                "hsm_name": (template.metadata or {}).get("hsm_name"),
            }
            for template in templates
        ]
        return ok_response({"items": items})

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def put(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        templates_payload = payload.get("templates")
        if not isinstance(templates_payload, list):
            return error_response("INVALID_PAYLOAD", status_code=400)

        updated_templates: List[MessageTemplate] = []
        with transaction.atomic():
            for entry in templates_payload:
                if not isinstance(entry, dict):
                    return error_response("INVALID_PAYLOAD", status_code=400)
                code = str(entry.get("code", "")).strip()
                language = str(entry.get("language", clinic.default_lang)).strip() or clinic.default_lang
                if not code:
                    return error_response("INVALID_TEMPLATE", status_code=400)

                template = (
                    clinic.message_templates.filter(code=code, language=language).first()
                )
                if template is None:
                    return error_response("INVALID_TEMPLATE", status_code=400)

                is_active = bool(entry.get("is_active", template.is_active))
                variables = entry.get("variables", template.variables or [])
                if not isinstance(variables, list):
                    return error_response("LINT_FAILED", status_code=400)
                variables_list = [str(var).strip() for var in variables]

                placeholders = _extract_placeholders(template.body)
                unknown = [var for var in variables_list if var and var not in placeholders]
                if unknown:
                    return error_response("LINT_FAILED", status_code=400)

                template.is_active = is_active
                template.variables = variables_list
                template.save(update_fields=["is_active", "variables", "updated_at"])
                updated_templates.append(template)

        return self.get(request, slug)


class ClinicTemplateListView(APIView):
    """Expose WhatsApp templates per clinic/language."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        params = request.GET
        lang = (params.get("lang") or "").strip()
        query = (params.get("q") or "").strip()
        page = _positive_int(params.get("page"), default=1)
        size = _bounded_positive_int(params.get("size"), default=50, maximum=200)

        templates = clinic.message_templates.filter(category=TemplateCategory.WHATSAPP)
        if lang:
            templates = templates.filter(language__iexact=lang)
        if query:
            templates = templates.filter(
                Q(code__icontains=query) | Q(body__icontains=query)
            )
        templates = templates.order_by("code", "language")

        total = templates.count()
        offset = (page - 1) * size
        paginated = list(templates[offset : offset + size])

        hsm_name_map = {
            template.id: (template.metadata or {}).get("hsm_name") or template.code
            for template in paginated
        }
        hsm_names = set(hsm_name_map.values())
        approved_hsms = set(
            HSMTemplate.objects.filter(
                clinic=clinic,
                name__in=hsm_names,
                status=HSMTemplateStatus.APPROVED,
            ).values_list("name", flat=True)
        )

        items = []
        for template in paginated:
            hsm_name = hsm_name_map.get(template.id, template.code)
            items.append(
                {
                    "key": template.code,
                    "lang": template.language,
                    "channel": "whatsapp",
                    "hsm": hsm_name in approved_hsms,
                    "variables": template.variables or [],
                    "enabled": template.is_active,
                }
            )

        return ok_response({"items": items, "page": page, "size": size, "total": total})

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def put(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        templates_payload = payload.get("templates")
        if not isinstance(templates_payload, list):
            return error_response("INVALID_PAYLOAD", status_code=400)

        with transaction.atomic():
            for entry in templates_payload:
                if not isinstance(entry, dict):
                    return error_response("INVALID_PAYLOAD", status_code=400)
                code = str(entry.get("key", entry.get("code", ""))).strip()
                language = str(entry.get("lang", entry.get("language", clinic.default_lang))).strip() or clinic.default_lang
                if not code:
                    return error_response("INVALID_TEMPLATE", status_code=400)
                template = clinic.message_templates.filter(code=code, language=language).first()
                if template is None:
                    return error_response("INVALID_TEMPLATE", status_code=400)

                if "enabled" in entry:
                    template.is_active = bool(entry.get("enabled"))
                if "variables" in entry:
                    variables = entry.get("variables")
                    if not isinstance(variables, list):
                        return error_response("LINT_FAILED", status_code=400)
                    variables_list = [str(var).strip() for var in variables]
                    placeholders = _extract_placeholders(template.body)
                    unknown = [var for var in variables_list if var and var not in placeholders]
                    if unknown:
                        return error_response("LINT_FAILED", status_code=400)
                    template.variables = variables_list
                template.save(update_fields=["is_active", "variables", "updated_at"])

        return self.get(request, slug)


class ClinicTemplatePreviewView(APIView):
    """Render a template with variables without sending."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        template_key = str(payload.get("template_key", "")).strip()
        if not template_key:
            return error_response("INVALID_TEMPLATE", status_code=400)

        variables_raw = payload.get("variables") or {}
        if variables_raw is None or not isinstance(variables_raw, dict):
            return error_response("LINT_FAILED", status_code=400)

        template = (
            clinic.message_templates.filter(
                code=template_key,
                category=TemplateCategory.WHATSAPP,
                is_active=True,
            )
            .order_by("-language")
            .first()
        )
        if template is None:
            return error_response("INVALID_TEMPLATE", status_code=400)

        variables = _normalize_variables(variables_raw)
        expected = template.variables or []
        missing = _missing_variables(expected, variables)
        if missing:
            return error_response("LINT_FAILED", status_code=400)

        rendered = _render_template_body(template.body, variables)
        if "{{" in rendered and expected:
            return error_response("LINT_FAILED", status_code=400)

        return ok_response({"rendered": rendered})




class ClinicGoogleCalendarStatusView(APIView):
    """Google Calendar integration status overview."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        data = _google_calendar_status(clinic)
        return ok_response(data)


class ClinicGoogleOAuthStartView(APIView):
    """Return OAuth URL for Google Calendar."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        service = GoogleCalendarService()
        auth_url = service.get_authorization_url(clinic.id)
        return ok_response({"auth_url": auth_url})


class ClinicGoogleOAuthCallbackView(APIView):
    """Handle Google OAuth callback."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        code = request.GET.get("code")
        if not code:
            return error_response("INVALID_CODE", status_code=400)
        service = GoogleCalendarService()
        try:
            service.exchange_code(clinic.id, code)
        except GoogleCalendarServiceError:
            return error_response("OAUTH_FAILED", status_code=502)
        return ok_response({})
class HQMetricsSummaryView(APIView):
    """Global HQ metrics (read-only)."""

    permission_classes = [permissions.IsAuthenticated]

    @require_hq_role()
    def get(self, request):
        payload = {
            "global": {
                "ttfr_p95_ms": 0,
                "delivery_fail_rate": 0.0,
                "handoff_rate": 0.0,
                "grounded_rate": 0.0,
                "llm_cost_today": 0.0,
            }
        }
        return ok_response(payload)


class HQTenantListView(APIView):
    """List clinics with lightweight operational status indicators."""

    permission_classes = [permissions.IsAuthenticated]

    @require_hq_role()
    def get(self, request):
        page = _positive_int(request.GET.get("page"), default=1)
        size = _positive_int(request.GET.get("size"), default=20)
        search = (request.GET.get("search") or "").strip()

        queryset = Clinic.objects.order_by("slug")
        if search:
            queryset = queryset.filter(Q(slug__icontains=search) | Q(name__icontains=search))

        total = queryset.count()
        start = (page - 1) * size
        clinics = list(queryset[start : start + size])

        items = [
            {
                "clinic": {"slug": clinic.slug, "name": clinic.name},
                "channels_status": _channels_status(clinic),
                "calendar_status": _calendar_status(clinic),
                "last_ttfr_p95_ms": _ttfr_p95_ms(clinic, window=timedelta(days=7)),
            }
            for clinic in clinics
        ]

        data = {"items": items, "page": page, "size": size, "total": total}
        return ok_response(data)


# --------------------------------------------------------------------------- util


def _get_service_by_code(clinic: Clinic, code: str):
    services = clinic.services.filter(code=code, is_active=True).order_by(
        "language"
    )
    if services:
        return services.first()
    return clinic.services.filter(code=code).order_by("language").first()


def _parse_clinic_datetime(raw: str, clinic: Clinic) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    tzinfo = ZoneInfo(clinic.tz or "UTC")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tzinfo)
    else:
        dt = dt.astimezone(tzinfo)
    return dt


def _is_within_service_hours(service, start_local: datetime, end_local: datetime) -> bool:
    tzinfo = start_local.tzinfo
    weekday = start_local.weekday()
    hours = service.hours.filter(weekday=weekday)
    for window in hours:
        window_start = datetime.combine(start_local.date(), window.start_time, tzinfo=tzinfo)
        window_end = datetime.combine(start_local.date(), window.end_time, tzinfo=tzinfo)
        if start_local >= window_start and end_local <= window_end:
            return True
    return False


def _check_google_availability(
    clinic: Clinic,
    start_local: datetime,
    end_local: datetime,
    *,
    exclude_appointment: Appointment | None = None,
) -> Tuple[bool, bool]:
    credential = _get_google_credential(clinic)
    if not credential:
        return True, False
    service = GoogleCalendarService()
    try:
        busy_windows = service.get_free_busy(credential, start_local, end_local)
    except GoogleCalendarServiceError:
        return True, True

    for busy_start, busy_end in busy_windows:
        busy_start_local = busy_start.astimezone(start_local.tzinfo)
        busy_end_local = busy_end.astimezone(start_local.tzinfo)
        if start_local < busy_end_local and end_local > busy_start_local:
            return False, False
    return True, False


def _has_overlap(
    clinic: Clinic,
    service,
    start_utc: datetime,
    end_utc: datetime,
    *,
    exclude: Optional[int] = None,
) -> bool:
    qs = Appointment.objects.filter(
        clinic=clinic,
        status__in=[
            AppointmentStatus.PENDING,
            AppointmentStatus.BOOKED,
            AppointmentStatus.CONFIRMED,
        ],
    )
    if service:
        qs = qs.filter(service=service)
    if exclude:
        qs = qs.exclude(id=exclude)

    for appointment in qs:
        existing_start = appointment.start_at
        existing_end = appointment.end_at
        if not existing_start or not existing_end:
            continue
        if start_utc < existing_end and end_utc > existing_start:
            return True
    return False


def _get_google_credential(clinic: Clinic) -> Optional[GoogleCredential]:
    return clinic.google_credentials.order_by("-updated_at").first()


def _serialize_appointment(appointment: Appointment) -> Dict[str, object]:
    return {
        "id": appointment.id,
        "service_code": appointment.service.code if appointment.service else "",
        "start_at": appointment.start_at.isoformat() if appointment.start_at else None,
        "end_at": appointment.end_at.isoformat() if appointment.end_at else None,
        "status": appointment.status,
        "external_event_id": appointment.external_event_id,
    }


def _normalize_variables(raw: Dict[str, object]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in raw.items():
        key_str = str(key)
        if value is None:
            normalized[key_str] = ""
        elif isinstance(value, str):
            normalized[key_str] = value.strip()
        else:
            normalized[key_str] = str(value)
    return normalized


def _missing_variables(expected: List[str], provided: Dict[str, str]) -> List[str]:
    missing: List[str] = []
    for placeholder in expected:
        value = provided.get(placeholder)
        if value is None or value == "":
            missing.append(placeholder)
    return missing


def _render_template_body(body: str, variables: Dict[str, str]) -> str:
    rendered = body
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(?P<name>[a-zA-Z0-9_]+)\s*\}\}")


def _extract_placeholders(body: str) -> List[str]:
    return [match.group("name") for match in PLACEHOLDER_PATTERN.finditer(body or "")]


def _select_hsm_template(clinic_id: int, name: str, language: str) -> HSMTemplate | None:
    template = HSMTemplate.objects.filter(
        clinic_id=clinic_id,
        name=name,
        language=language,
        status=HSMTemplateStatus.APPROVED,
    ).first()
    if template:
        return template
    return (
        HSMTemplate.objects.filter(
            clinic_id=clinic_id,
            name=name,
            status=HSMTemplateStatus.APPROVED,
        )
        .order_by("language")
        .first()
    )


def _within_session_window(conversation: Conversation) -> bool:
    last_inbound = (
        conversation.messages.filter(direction=MessageDirection.INBOUND)
        .order_by("-created_at")
        .first()
    )
    if not last_inbound:
        return False
    return (timezone.now() - last_inbound.created_at) <= timedelta(hours=SESSION_WINDOW_HOURS)


def _requires_hsm(conversation: Conversation) -> bool:
    has_outbound = conversation.messages.filter(direction=MessageDirection.OUTBOUND).exists()
    return not has_outbound or not _within_session_window(conversation)


def _build_idempotency_key(
    *, conversation_id: int, template_key: str, variables: Dict[str, str]
) -> str:
    payload = {
        "conversation": conversation_id,
        "template": template_key,
        "variables": variables,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _chunk_document(body: str) -> List[str]:
    parts = [segment.strip() for segment in (body or "").split("\n\n") if segment.strip()]
    if not parts and body:
        parts = [body.strip()]
    return parts


def _compute_chunk_score(content: str, query: str) -> float:
    lowered = content.lower()
    tokens = [token for token in re.findall(r"\w+", query.lower()) if token]
    if not tokens:
        return 0.0
    score = 0.0
    for token in tokens:
        score += lowered.count(token)
    return score


def _get_default_index(clinic: Clinic) -> KnowledgeIndex:
    index, _ = KnowledgeIndex.objects.get_or_create(
        clinic=clinic,
        name=getattr(settings, "RAG_INDEX_NAME", "default"),
        defaults={"dimensions": 1536, "retriever_config": {"top_k": 4}},
    )
    return index


def _whatsapp_channel_status(clinic: Clinic) -> dict:
    account = clinic.channel_accounts.filter(channel=ChannelType.WHATSAPP).first()
    now = timezone.now()
    if not account:
        return {
            "status": "DOWN",
            "last_success_at": None,
            "last_error_at": None,
            "provider": None,
        }
    last_success = (
        OutboxMessage.objects.filter(
            clinic=clinic,
            channel=ChannelType.WHATSAPP,
            status__in=[OutboxStatus.SENT, OutboxStatus.DELIVERED],
        )
        .order_by("-updated_at")
        .first()
    )
    last_error = (
        OutboxMessage.objects.filter(
            clinic=clinic,
            channel=ChannelType.WHATSAPP,
            status=OutboxStatus.FAILED,
        )
        .order_by("-updated_at")
        .first()
    )
    status = "WARN"
    if last_success and (now - last_success.updated_at) <= timedelta(hours=24):
        status = "OK"
    elif last_error and (not last_success or last_error.updated_at >= last_success.updated_at):
        status = "DOWN"
    return {
        "status": status,
        "last_success_at": last_success.updated_at.isoformat() if last_success else None,
        "last_error_at": last_error.updated_at.isoformat() if last_error else None,
        "provider": account.provider_name,
    }


def _google_calendar_status(clinic: Clinic) -> dict:
    credential = clinic.google_credentials.order_by("-updated_at").first()
    if not credential:
        return {
            "status": "DISCONNECTED",
            "last_auth_at": None,
            "last_error": None,
        }
    now = timezone.now()
    status = "WARN"
    if (
        credential.last_free_busy_at
        and (now - credential.last_free_busy_at) <= timedelta(hours=24)
        and not credential.last_error
    ):
        status = "OK"
    elif credential.last_error and credential.last_error_at:
        status = "WARN"
    return {
        "status": status,
        "last_auth_at": credential.updated_at.isoformat() if credential.updated_at else None,
        "last_error": credential.last_error or None,
    }


def _filter_conversation_status(
    qs: QuerySet[Conversation], status_value: str
) -> QuerySet[Conversation]:
    if status_value == "handoff":
        return qs.filter(handoff_required=True)
    if status_value == "resolved":
        return qs.filter(handoff_required=False, fsm_state__iexact="done")
    if status_value == "open":
        return qs.filter(handoff_required=False).exclude(fsm_state__iexact="done")
    return qs


def _serialize_conversation_summary(conversation: Conversation, clinic: Clinic) -> dict:
    patient = conversation.patient
    last_message_at = getattr(conversation, "last_message_at", None) or conversation.updated_at
    return {
        "id": conversation.id,
        "started_at": conversation.created_at.isoformat(),
        "last_message_at": last_message_at.isoformat() if last_message_at else None,
        "intent": conversation.last_intent or "",
        "lang": _conversation_language(conversation, clinic),
        "status": _conversation_status(conversation),
        "patient": {
            "id": patient.id if patient else None,
            "phone": patient.phone_number if patient else None,
        },
    }


def _conversation_status(conversation: Conversation) -> str:
    if conversation.handoff_required:
        return "handoff"
    if (conversation.fsm_state or "").lower() == "done":
        return "resolved"
    return "open"


def _conversation_language(conversation: Conversation, clinic: Clinic) -> str:
    patient = conversation.patient
    if patient and patient.language:
        return patient.language
    return clinic.default_lang

def _clinic_dashboard_payload(clinic: Clinic) -> dict:
    today = timezone.localdate()

    conversations_today = clinic.conversations.filter(created_at__date=today).count()
    bookings_today = clinic.appointments.filter(
        created_at__date=today, status=AppointmentStatus.BOOKED
    ).count()
    handoff_today = clinic.conversations.filter(
        handoff_required=True, updated_at__date=today
    ).count()
    tentative_today = clinic.appointments.filter(
        sync_state=AppointmentSyncState.TENTATIVE, updated_at__date=today
    ).count()
    tentative_count = clinic.appointments.filter(sync_state=AppointmentSyncState.TENTATIVE).count()
    failed_count = clinic.appointments.filter(sync_state=AppointmentSyncState.FAILED).count()

    ttfr_p95_ms = _ttfr_p95_ms(clinic, window=timedelta(days=1))
    delivery_fail_rate = _delivery_fail_rate(clinic, window=timedelta(days=1))

    return {
        "conversations_today": conversations_today,
        "bookings_today": bookings_today,
        "ttfr_p95_ms": ttfr_p95_ms,
        "handoff_today": handoff_today,
        "delivery_fail_rate": delivery_fail_rate,
        "tentative_today": tentative_today,
        "tentative_count": tentative_count,
        "failed_count": failed_count,
    }


def _ttfr_p95_ms(clinic: Clinic, window: timedelta) -> int:
    deltas = _ttfr_durations_ms(clinic, window=window)
    if not deltas:
        return 0
    deltas.sort()
    index = max(0, math.ceil(0.95 * len(deltas)) - 1)
    return int(deltas[index])


def _ttfr_durations_ms(clinic: Clinic, window: timedelta) -> List[float]:
    cutoff = timezone.now() - window
    inbound_qs = ConversationMessage.objects.filter(
        conversation__clinic=clinic,
        direction=MessageDirection.INBOUND,
        created_at__gte=cutoff,
    ).order_by("created_at")

    conversation_ids = inbound_qs.values_list("conversation_id", flat=True).distinct()
    durations: List[float] = []

    for conversation_id in conversation_ids:
        inbound = inbound_qs.filter(conversation_id=conversation_id).first()
        if inbound is None:
            continue
        outbound = (
            ConversationMessage.objects.filter(
                conversation_id=conversation_id,
                direction=MessageDirection.OUTBOUND,
                created_at__gte=inbound.created_at,
            )
            .order_by("created_at")
            .first()
        )
        if outbound and outbound.created_at > inbound.created_at:
            delta = (outbound.created_at - inbound.created_at).total_seconds() * 1000
            durations.append(delta)

    return durations


def _delivery_fail_rate(clinic: Clinic, window: timedelta) -> float:
    cutoff = timezone.now() - window
    relevant = clinic.outbox_messages.filter(
        created_at__gte=cutoff,
        status__in=[
            OutboxStatus.SENT,
            OutboxStatus.DELIVERED,
            OutboxStatus.FAILED,
        ],
    )
    total = relevant.count()
    if total == 0:
        return 0.0
    failed = relevant.filter(status=OutboxStatus.FAILED).count()
    return failed / total


def _channels_status(clinic: Clinic) -> str:
    if clinic.channel_accounts.filter(channel=ChannelType.WHATSAPP).exists():
        return "OK"
    return "WARN"


def _calendar_status(clinic: Clinic) -> str:
    if clinic.google_credentials.exists():
        return "OK"
    return "DISCONNECTED"


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _bounded_positive_int(value, default: int, maximum: int) -> int:
    parsed = _positive_int(value, default)
    return min(parsed, maximum)


def _parse_clinic_iso_datetime(raw: str | None, clinic: Clinic) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    tzinfo = ZoneInfo(clinic.tz or "UTC")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tzinfo)
    else:
        dt = dt.astimezone(tzinfo)
    return dt.astimezone(dt_timezone.utc)
class ClinicKnowledgeUploadView(APIView):
    """Accept knowledge base YAML uploads."""

    permission_classes = [permissions.IsAuthenticated]

    TAG_OPTIONS = {"service", "policy", "faq", "about", "glossary"}

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        upload = request.FILES.get("file") or request.FILES.get("kb") or None
        if upload is None:
            return error_response("INVALID_SCHEMA", status_code=400)

        try:
            payload = yaml.safe_load(upload.read()) or {}
        except yaml.YAMLError:
            return error_response("INVALID_SCHEMA", status_code=400)

        documents = payload.get("documents")
        if not isinstance(documents, list) or not documents:
            return error_response("INVALID_SCHEMA", status_code=400)

        with transaction.atomic():
            for entry in documents:
                if not isinstance(entry, dict):
                    return error_response("INVALID_SCHEMA", status_code=400)
                title = str(entry.get("title", "")).strip()
                language = str(entry.get("lang", entry.get("language", clinic.default_lang))).strip() or clinic.default_lang
                body = entry.get("body")
                tag = str(entry.get("tag", "")).strip().lower()
                source = str(entry.get("source", "")).strip()

                if not title or not body or tag not in self.TAG_OPTIONS:
                    return error_response("INVALID_SCHEMA", status_code=400)
                if language not in {lang[0] for lang in LanguageChoices.choices}:
                    return error_response("INVALID_SCHEMA", status_code=400)

                doc, _ = KnowledgeDocument.objects.update_or_create(
                    clinic=clinic,
                    title=title,
                    language=language,
                    defaults={
                        "body": body,
                        "source": source or "upload",
                        "metadata": {"tag": tag, "pending": True},
                    },
                )
                KnowledgeChunk.objects.filter(document=doc).delete()

        return ok_response({"documents": len(documents)})


class ClinicKnowledgePublishView(APIView):
    """Chunk and index uploaded knowledge."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        pending = KnowledgeDocument.objects.filter(
            clinic=clinic, metadata__pending=True
        )
        if not pending.exists():
            return ok_response({"published": 0})

        index = _get_default_index(clinic)

        total_chunks = 0
        with transaction.atomic():
            for document in pending:
                KnowledgeChunk.objects.filter(document=document).delete()
                tag = (document.metadata or {}).get("tag", "service")
                chunks = _chunk_document(document.body)
                for idx, content in enumerate(chunks):
                    KnowledgeChunk.objects.create(
                        document=document,
                        chunk_index=idx,
                        content=content,
                        language=document.language,
                        tags=[tag],
                        metadata={"source": document.source, "tag": tag},
                    )
                    total_chunks += 1
                document.metadata["pending"] = False
                document.save(update_fields=["metadata", "updated_at"])
            index.documents.set(clinic.knowledge_documents.all())
            index.last_synced_at = timezone.now()
            index.save(update_fields=["last_synced_at", "updated_at"])

        return ok_response({"published": pending.count(), "chunks": total_chunks})


class ClinicKnowledgePreviewView(APIView):
    """Preview RAG retrieval for a query."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        query = str(payload.get("q", "")).strip()
        language = str(payload.get("lang", clinic.default_lang)).strip().lower()

        if not query:
            return error_response("INVALID_QUERY", status_code=400)
        if language not in {lang[0] for lang in LanguageChoices.choices}:
            return error_response("INVALID_QUERY", status_code=400)

        chunks = list(
            KnowledgeChunk.objects.filter(document__clinic=clinic).select_related("document")
        )
        if not chunks:
            return ok_response({"chunks": []})

        scored = []
        for chunk in chunks:
            score = _compute_chunk_score(chunk.content, query)
            if score <= 0:
                continue
            scored.append((chunk, score))

        if not scored:
            return ok_response({"chunks": []})

        desired = [item for item in scored if item[0].language == language]
        fallback = [item for item in scored if item[0].language != language]

        desired.sort(key=lambda x: x[1], reverse=True)
        fallback.sort(key=lambda x: x[1], reverse=True)
        combined = desired + fallback

        char_budget = getattr(settings, "RAG_MAX_TOKENS", 1000) * getattr(settings, "RAG_CHARS_PER_TOKEN", 4)
        selected = []
        running = 0
        for chunk, score in combined:
            content = chunk.content.strip()
            addition = len(content)
            if selected and running + addition > char_budget:
                break
            selected.append((chunk, score))
            running += addition

        response_chunks = [
            {
                "id": chunk.id,
                "lang": chunk.language,
                "tag": (chunk.metadata or {}).get("tag") or (chunk.tags[0] if chunk.tags else ""),
                "score": float(score),
                "excerpt": content[:char_budget],
            }
            for chunk, score in selected
            if (content := chunk.content.strip())
        ]

        return ok_response({"chunks": response_chunks})


class ClinicWhatsAppStatusView(APIView):
    """Report WhatsApp channel health."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        data = _whatsapp_channel_status(clinic)
        return ok_response(data)


class ClinicWhatsAppTestView(APIView):
    """Send a sandbox WhatsApp test message."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        to_number = str(payload.get("to_sandbox_phone", "")).strip()
        template_key = str(payload.get("template_key", "greet")).strip() or "greet"
        if not to_number:
            return error_response("INVALID_PAYLOAD", status_code=400)

        template = clinic.message_templates.filter(code=template_key).order_by("language").first()
        if template is None:
            return error_response("INVALID_TEMPLATE", status_code=400)

        variables = _normalize_variables(payload.get("variables") or {})
        placeholders = _extract_placeholders(template.body)
        unknown = [var for var in variables if var and var not in placeholders]
        if unknown:
            return error_response("LINT_FAILED", status_code=400)

        hsm_name = (template.metadata or {}).get("hsm_name") or template.code
        idempotency_key = hashlib.sha256(
            json.dumps(
                {
                    "clinic": clinic.id,
                    "phone": to_number,
                    "template": template.code,
                    "language": template.language,
                    "variables": variables,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        outbox = OutboxMessage.objects.filter(idempotency_key=idempotency_key).first()
        if outbox is None:
            outbox = enqueue_whatsapp_message(
                clinic_id=clinic.id,
                conversation=None,
                language=template.language,
                hsm_name=hsm_name,
                variables=variables,
                idempotency_key=idempotency_key,
            )
        outbox.metadata["sandbox_to"] = to_number
        outbox.save(update_fields=["metadata", "updated_at"])
        return ok_response({"outbox_id": outbox.id})




