"""Tenant-scoped portal APIs (dashboards, conversations, appointments)."""

from __future__ import annotations

import hashlib
import logging
import json
import math
import re
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import yaml
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.db.models.query import Prefetch, QuerySet
from django.utils import timezone
from rest_framework import permissions
from rest_framework.views import APIView
from django.conf import settings

from apps.accounts.decorators import require_clinic_role, require_hq_role
from apps.accounts.models import (
    AuditLog,
    ClinicMembership,
    Invitation,
    SupportSession,
    Notification,
    NotificationStatus,
)
from apps.accounts.support import hash_support_token, sign_invitation_token
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
from apps.appointments.scheduling import find_available_slots
from apps.clinics.models import Clinic, ClinicService, ServiceHours, LanguageChoices
from apps.common.api import error_response, ok_response
from apps.conversations.models import Conversation, ConversationMessage, MessageDirection
from apps.kb.models import KnowledgeChunk, KnowledgeDocument, KnowledgeIndex
from apps.templates.models import MessageTemplate, TemplateCategory
from apps.channels.services import (
    DEFAULT_SESSION_FALLBACK_HSM,
    SESSION_WINDOW_HOURS,
    enqueue_whatsapp_message,
    enqueue_whatsapp_session_message,
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


class ClinicAvailableSlotsView(APIView):
    """LLM tool endpoint to fetch available slots for a service."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        service_code = str(payload.get("service_code", "")).strip()
        if not service_code:
            return error_response("INVALID_SERVICE", status_code=400)

        service = _get_service_by_code(clinic, service_code)
        if service is None:
            return error_response("INVALID_SERVICE", status_code=400)

        limit_raw = payload.get("limit", 5)
        try:
            limit = max(1, min(10, int(limit_raw)))
        except (TypeError, ValueError):
            limit = 5

        start_iso = payload.get("from_iso")
        end_iso = payload.get("to_iso")

        tzinfo = ZoneInfo(clinic.tz or "UTC")
        start_local = _parse_clinic_datetime(start_iso, clinic) if start_iso else timezone.now().astimezone(tzinfo)
        end_local = _parse_clinic_datetime(end_iso, clinic) if end_iso else start_local + timedelta(days=7)
        if end_local <= start_local:
            return error_response("INVALID_RANGE", status_code=400)

        available = find_available_slots(
            clinic,
            service,
            start=start_local,
            end=end_local,
            limit=limit,
        )

        slots = [
            {
                "start_at": slot.start.isoformat(),
                "end_at": slot.end.isoformat(),
                "tz": clinic.tz or "UTC",
                "tentative": slot.tentative,
                "source": slot.source,
            }
            for slot in available
        ]

        return ok_response(slots=slots)


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

        if conversation.patient is None and conversation.dedupe_key:
            parts = conversation.dedupe_key.split(":", 1)
            if len(parts) == 2 and parts[1]:
                patient = Patient.objects.filter(
                    clinic=clinic, normalized_phone=parts[1]
                ).first()
                if patient:
                    conversation.patient = patient
                    conversation.save(update_fields=["patient", "updated_at"])

        payload = {
            "id": conversation.id,
            "intent": conversation.last_intent or "",
            "lang": _conversation_language(conversation, clinic),
            "fsm_state": conversation.fsm_state,
            "handoff": conversation.handoff_required,
            "patient": {
                "id": conversation.patient.id if conversation.patient else None,
                "full_name": conversation.patient.full_name if conversation.patient else "",
                "ai_enabled": conversation.patient.ai_enabled if conversation.patient else True,
            },
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
        reply_mode = data.get("reply_mode", "template")  # "template" or "direct"
        direct_message = str(data.get("direct_message", "")).strip()

        if reply_mode == "direct":
            # Direct message mode
            if not direct_message:
                return error_response("MESSAGE_REQUIRED", status_code=400)
            if len(direct_message) > 4096:  # WhatsApp limit
                return error_response("MESSAGE_TOO_LONG", status_code=400)
        else:
            # Template mode (existing logic)
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
                Conversation.objects.filter(clinic=clinic, pk=pk)
                .first()
            )
            if conversation is None:
                return error_response("NOT_FOUND", status_code=404)

            language = _conversation_language(conversation, clinic)

            if reply_mode == "direct":
                # Direct message - no template needed
                rendered_body = direct_message
                outbound_body = direct_message
                requires_hsm = _requires_hsm(conversation)
                hsm_template = None
                hsm_name_to_use = None
                variables = {}
                template = None

                if requires_hsm:
                    # For direct messages that require HSM, use default session fallback
                    hsm_template = _select_hsm_template(
                        clinic_id=clinic.id,
                        name=DEFAULT_SESSION_FALLBACK_HSM,
                        language=language,
                    )
                    if hsm_template is None:
                        return error_response("NO_HSM_AVAILABLE", status_code=400)
                    outbound_body = _render_template_body(hsm_template.body, {"message": direct_message})
                    hsm_name_to_use = hsm_template.name

                idempotency_key = _build_idempotency_key(
                    conversation_id=conversation.id,
                    template_key="direct_message",
                    variables={"message": direct_message[:100]},  # Limit for idempotency key
                )
            else:
                # Template mode (existing logic)
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
                if reply_mode == "direct" and not requires_hsm:
                    outbox = enqueue_whatsapp_session_message(
                        clinic_id=clinic.id,
                        conversation=conversation,
                        language=language,
                        message_body=rendered_body,
                        idempotency_key=idempotency_key,
                    )
                else:
                    outbox = enqueue_whatsapp_message(
                        clinic_id=clinic.id,
                        conversation=conversation,
                        language=language,
                        message_body=rendered_body,
                        hsm_name=hsm_name_to_use or DEFAULT_SESSION_FALLBACK_HSM,
                        variables=variables,
                        idempotency_key=idempotency_key,
                    )
            except Exception as exc:
                logger.exception("Failed to enqueue WhatsApp reply", exc_info=True)
                return error_response("OUTBOX_ERROR", status_code=500)

            if requires_hsm and (
                outbox.message_type != MessageType.HSM or outbox.hsm_template_id is None
            ):
                return error_response("NO_HSM_AVAILABLE", status_code=400)

            if reply_mode == "direct":
                intent = "human_reply"
                metadata = {
                    "reply_mode": "direct",
                    "original_message": direct_message,
                    "outbox_id": outbox.id,
                    "message_type": outbox.message_type,
                }
            else:
                intent = "template_reply"
                metadata = {
                    "reply_mode": "template",
                    "template_key": template.code,
                    "variables": variables,
                    "outbox_id": outbox.id,
                    "message_type": outbox.message_type,
                }

            conversation_message = ConversationMessage.objects.create(
                conversation=conversation,
                direction=MessageDirection.OUTBOUND,
                language=language,
                body=direct_message if reply_mode == "direct" else outbound_body,
                intent=intent,
                metadata=metadata,
            )

            update_fields = ["updated_at"]
            if (conversation.fsm_state or "").lower() == "done":
                conversation.fsm_state = "idle"
                update_fields.append("fsm_state")
            conversation.save(update_fields=update_fields)

            # Prepare audit log metadata
            audit_meta = {
                "conversation_id": conversation.id,
                "reply_mode": reply_mode,
            }
            if reply_mode == "direct":
                audit_meta["message_preview"] = direct_message[:50]  # First 50 chars
            else:
                audit_meta["template_key"] = template.code if template else None

            AuditLog.objects.create(
                actor_user=request.user if getattr(request, "user", None) else None,
                action="CONVERSATION_REPLY",
                scope=AuditLog.Scope.CLINIC,
                clinic=clinic,
                meta=audit_meta,
            )

            return ok_response({"message_id": conversation_message.id})


class ClinicConversationResolveHandoffView(APIView):
    """Mark a conversation handoff as resolved by a human."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str, pk: int):
        clinic: Clinic = request.clinic
        conversation = (
            Conversation.objects.filter(clinic=clinic, pk=pk)
            .select_related("patient")
            .first()
        )
        if conversation is None:
            return error_response("NOT_FOUND", status_code=404)

        update_fields = ["updated_at"]
        if conversation.handoff_required:
            conversation.handoff_required = False
            update_fields.append("handoff_required")
        if (conversation.fsm_state or "").lower() == "done":
            conversation.fsm_state = "idle"
            update_fields.append("fsm_state")

        conversation.save(update_fields=update_fields)

        if "handoff_required" in update_fields:
            Notification.objects.filter(
                conversation=conversation, status=NotificationStatus.NEW
            ).update(status=NotificationStatus.READ, updated_at=timezone.now())

        AuditLog.objects.create(
            actor_user=request.user if getattr(request, "user", None) else None,
            action="CONVERSATION_HANDOFF_RESOLVED",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={"conversation_id": conversation.id},
        )

        return ok_response({"handoff": False})


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
            clinic.appointments.select_related("service", "patient").order_by("created_at", "id")
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
        items = [_serialize_appointment(appt) for appt in paginated]

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

        appointment, error_code, tentative = book_appointment(
            clinic=clinic,
            patient=patient,
            service=service,
            start_local=start_local,
            source="clinic_portal",
        )
        if error_code:
            status_code = 409 if error_code == "SLOT_TAKEN" else 400
            return error_response(error_code, status_code=status_code)

        data = {"appointment": _serialize_appointment(appointment)}
        if tentative:
            data["google_tentative"] = True
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
            data["google_tentative"] = True
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

        data: Dict[str, object] = {"appointment": _serialize_appointment(appointment)}
        if warning:
            data["google_tentative"] = True
        return ok_response(data)


class ClinicAppointmentDeleteView(APIView):
    """Delete an appointment and remove external calendar events."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def delete(self, request, slug: str, appointment_id: int):
        clinic: Clinic = request.clinic

        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update()
                .filter(clinic=clinic, id=appointment_id)
                .first()
            )
            if appointment is None:
                return error_response("INVALID_SERVICE", status_code=404)

            calendar_event = getattr(appointment, "calendar_event", None)
            credential = _get_google_credential(clinic)

            # Best-effort cancel external event
            if calendar_event and credential:
                try:
                    GoogleCalendarService().cancel_event(calendar_event, credential)
                except GoogleCalendarServiceError:
                    pass
                finally:
                    calendar_event.delete()

            appointment.delete()

        AuditLog.objects.create(
            actor_user=request.user if getattr(request, "user", None) else None,
            action="APPOINTMENT_DELETE",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={"appointment_id": appointment_id},
        )

        return ok_response({"deleted": True, "id": appointment_id})


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
                if language not in ("ar", "en"):
                    return error_response("INVALID_SERVICE_LANGUAGE", status_code=400)
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
    def post(self, request, slug: str):
        """Create a new template."""
        clinic: Clinic = request.clinic
        payload = request.data or {}
        
        code = str(payload.get("code", "")).strip()
        language = str(payload.get("language", "en")).strip()
        body = str(payload.get("body", "")).strip()
        hsm_name = str(payload.get("hsm_name", "")).strip()
        variables = payload.get("variables", [])
        
        if not code or not body:
            return error_response("INVALID_PAYLOAD", status_code=400)

        if not (
            language in ("ar", "en")
            or (code == "hello_world" and language == "en_US")
        ):
            return error_response("INVALID_TEMPLATE_LANGUAGE", status_code=400)
        
        # Check if template already exists
        existing = clinic.message_templates.filter(code=code, language=language).first()
        if existing:
            return error_response("TEMPLATE_EXISTS", status_code=400)
        
        # Create new template
        template = MessageTemplate.objects.create(
            clinic=clinic,
            code=code,
            language=language,
            body=body,
            category=TemplateCategory.WHATSAPP,
            is_active=True,
            variables=variables if isinstance(variables, list) else [],
            metadata={
                "hsm_name": hsm_name or code,
            }
        )
        
        AuditLog.objects.create(
            actor_user=request.user if request.user.is_authenticated else None,
            action="TEMPLATE_CREATE",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={
                "template_code": code,
                "language": language,
            },
        )
        
        return ok_response({
            "template": {
                "key": template.code,
                "lang": template.language,
                "channel": "whatsapp",
                "hsm": False,  # Not approved yet in Meta
                "variables": template.variables or [],
                "enabled": template.is_active,
            }
        })

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
                code = str(entry.get("code") or entry.get("key") or "").strip()
                language = (
                    str(entry.get("language") or entry.get("lang") or clinic.default_lang).strip()
                    or clinic.default_lang
                )
                if not code:
                    return error_response("INVALID_TEMPLATE", status_code=400)

                if not (
                    language in ("ar", "en")
                    or (code == "hello_world" and language == "en_US")
                ):
                    return error_response("INVALID_TEMPLATE_LANGUAGE", status_code=400)

                template = clinic.message_templates.filter(code=code, language=language).first()
                if template is None:
                    return error_response("INVALID_TEMPLATE", status_code=400)

                enabled_value = entry.get("enabled")
                if enabled_value is None:
                    enabled_value = entry.get("is_active", template.is_active)
                is_active = bool(enabled_value)

                variables_value = entry.get("variables", template.variables or [])
                if not isinstance(variables_value, list):
                    return error_response("LINT_FAILED", status_code=400)
                variables_list = [str(var).strip() for var in variables_value]

                placeholders = _extract_placeholders(template.body)
                unknown = [var for var in variables_list if var and var not in placeholders]
                if unknown:
                    return error_response("LINT_FAILED", status_code=400)

                template.is_active = is_active
                template.variables = variables_list
                template.save(update_fields=["is_active", "variables", "updated_at"])

        return self.get(request, slug)

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

                if not (
                    language in ("ar", "en")
                    or (code == "hello_world" and language == "en_US")
                ):
                    return error_response("INVALID_TEMPLATE_LANGUAGE", status_code=400)
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


class ClinicUserListView(APIView):
    """Manage clinic memberships (list + invite)."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        memberships = (
            ClinicMembership.objects.filter(clinic=clinic)
            .select_related("user")
            .order_by("user__email")
        )
        items = [_serialize_membership(member) for member in memberships]
        return ok_response({"items": items})

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def post(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        email = str(payload.get("email", "")).strip().lower()
        role = str(payload.get("role", "")).strip().upper()
        if not email:
            return error_response("INVALID_EMAIL", status_code=400)
        if role not in ClinicMembership.Role.values:
            return error_response("INVALID_ROLE", status_code=400)

        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                username = email or f"user-{timezone.now().timestamp()}"
                user = User.objects.create(
                    username=username,
                    email=email,
                    first_name=str(payload.get("first_name", "")).strip()[:30],
                    last_name=str(payload.get("last_name", "")).strip()[:30],
                    is_active=False,
                )
                user.set_unusable_password()
                user.save(update_fields=["password"])

            membership, created = ClinicMembership.objects.get_or_create(
                clinic=clinic,
                user=user,
                defaults={"role": role},
            )
            invited = created
            if created:
                AuditLog.objects.create(
                    actor_user=request.user,
                    action="USER_INVITE",
                    scope=AuditLog.Scope.CLINIC,
                    clinic=clinic,
                    meta={
                        "target_user_id": user.id,
                        "target_email": user.email,
                        "role": role,
                    },
                )

        data = {
            "id": membership.id,
            "email": membership.user.email,
            "role": membership.role,
            "invited": invited,
        }
        return ok_response(data)


class ClinicUserDetailView(APIView):
    """Update or remove clinic members."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def put(self, request, slug: str, membership_id: int):
        clinic: Clinic = request.clinic
        payload = request.data or {}
        role = str(payload.get("role", "")).strip().upper()
        if role not in ClinicMembership.Role.values:
            return error_response("INVALID_ROLE", status_code=400)

        membership = (
            ClinicMembership.objects.filter(clinic=clinic, id=membership_id)
            .select_related("user")
            .first()
        )
        if membership is None:
            return error_response("NOT_FOUND", status_code=404)

        if membership.role != role:
            membership.role = role
            membership.save(update_fields=["role", "updated_at"])
            AuditLog.objects.create(
                actor_user=request.user,
                action="USER_ROLE_UPDATE",
                scope=AuditLog.Scope.CLINIC,
                clinic=clinic,
                meta={
                    "target_user_id": membership.user_id,
                    "target_email": membership.user.email,
                    "role": role,
                },
            )

        return ok_response({"id": membership.id, "email": membership.user.email, "role": membership.role})

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def delete(self, request, slug: str, membership_id: int):
        clinic: Clinic = request.clinic
        membership = (
            ClinicMembership.objects.filter(clinic=clinic, id=membership_id)
            .select_related("user")
            .first()
        )
        if membership is None:
            return error_response("NOT_FOUND", status_code=404)

        user = membership.user
        meta = {
            "target_user_id": user.id if user else None,
            "target_email": user.email if user else "",
            "role": membership.role,
        }
        membership.delete()
        AuditLog.objects.create(
            actor_user=request.user,
            action="USER_REMOVE",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta=meta,
        )
        return ok_response({})


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

class HQSupportStartView(APIView):
    """Start an HQ support impersonation session."""

    permission_classes = [permissions.IsAuthenticated]

    @require_hq_role()
    def post(self, request):
        payload = request.data or {}
        clinic_id_raw = payload.get("clinic_id")
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            return error_response("INVALID_REASON", status_code=400)
        try:
            clinic_id = int(clinic_id_raw)
        except (TypeError, ValueError):
            return error_response("INVALID_CLINIC", status_code=400)

        clinic = Clinic.objects.filter(id=clinic_id).first()
        if clinic is None:
            return error_response("INVALID_CLINIC", status_code=404)

        ttl_minutes = int(getattr(settings, "SUPPORT_SESSION_MINUTES", 60))
        expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
        token = secrets.token_urlsafe(32)
        token_hash = hash_support_token(token)
        SupportSession.objects.create(
            token_hash=token_hash,
            staff_user=request.user,
            clinic=clinic,
            reason=reason,
            expires_at=expires_at,
        )
        AuditLog.objects.create(
            actor_user=request.user,
            action="SUPPORT_SESSION_START",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={
                "impersonation": True,
                "clinic_slug": clinic.slug,
                "expires_at": expires_at.isoformat(),
                "reason": reason,
            },
        )
        return ok_response({"support_token": token, "expires_at": expires_at.isoformat()})


class HQSupportStopView(APIView):
    """Stop an active HQ support impersonation session."""

    permission_classes = [permissions.IsAuthenticated]

    @require_hq_role()
    def post(self, request):
        payload = request.data or {}
        token = str(payload.get("support_token", "")).strip()
        if not token:
            return error_response("INVALID_TOKEN", status_code=400)
        token_hash = hash_support_token(token)
        session = (
            SupportSession.objects.select_related("clinic")
            .filter(token_hash=token_hash, staff_user=request.user, active=True)
            .first()
        )
        if session is None:
            return error_response("INVALID_TOKEN", status_code=404)
        session.active = False
        session.ended_at = timezone.now()
        session.save(update_fields=["active", "ended_at", "updated_at"])
        AuditLog.objects.create(
            actor_user=request.user,
            action="SUPPORT_SESSION_STOP",
            scope=AuditLog.Scope.CLINIC,
            clinic=session.clinic,
            meta={
                "impersonation": True,
                "clinic_slug": session.clinic.slug,
                "ended_at": session.ended_at.isoformat(),
            },
        )
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
                "clinic": {"id": clinic.id, "slug": clinic.slug, "name": clinic.name},
                "channels_status": _channels_status(clinic),
                "calendar_status": _calendar_status(clinic),
                "last_ttfr_p95_ms": _ttfr_p95_ms(clinic, window=timedelta(days=7)),
            }
            for clinic in clinics
        ]

        data = {"items": items, "page": page, "size": size, "total": total}
        return ok_response(data)

    @require_hq_role()
    def post(self, request):
        payload = request.data or {}
        name = (payload.get("name") or "").strip()
        slug = (payload.get("slug") or "").strip()
        default_lang = (payload.get("default_lang") or "").strip().lower() or LanguageChoices.ENGLISH
        tz = (payload.get("tz") or "").strip() or "UTC"
        owner_email = (payload.get("owner_email") or "").strip().lower()
        owner_name = (payload.get("owner_name") or "").strip()

        if not name or not slug or not owner_email:
            return error_response("INVALID_PAYLOAD", status_code=400)
        try:
            validate_email(owner_email)
        except ValidationError:
            return error_response("INVALID_EMAIL", status_code=400)

        valid_langs = {choice for choice, _label in LanguageChoices.choices}
        if default_lang not in valid_langs:
            return error_response("INVALID_LANGUAGE", status_code=400)

        with transaction.atomic():
            clinic, clinic_created = Clinic.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "default_lang": default_lang,
                    "tz": tz,
                },
            )
            if not clinic_created:
                clinic.name = name or clinic.name
                clinic.default_lang = default_lang
                clinic.tz = tz or clinic.tz
                clinic.save(update_fields=["name", "default_lang", "tz", "updated_at"])

            user = User.objects.filter(email__iexact=owner_email).first()
            if user is None:
                username = owner_email or f"owner-{slug}"
                user = User.objects.create(
                    username=username,
                    email=owner_email,
                    is_active=False,
                )
                user.set_unusable_password()
                user.save(update_fields=["password"])

            update_fields: List[str] = []
            if owner_name:
                parts = owner_name.split(None, 1)
                first = parts[0][:30]
                last = parts[1][:150] if len(parts) > 1 else ""
                if user.first_name != first:
                    user.first_name = first
                    update_fields.append("first_name")
                if last and user.last_name != last:
                    user.last_name = last
                    update_fields.append("last_name")
            if update_fields:
                user.save(update_fields=update_fields)

            membership, _ = ClinicMembership.objects.get_or_create(
                clinic=clinic,
                user=user,
                defaults={"role": ClinicMembership.Role.OWNER},
            )
            if membership.role != ClinicMembership.Role.OWNER:
                membership.role = ClinicMembership.Role.OWNER
                membership.save(update_fields=["role", "updated_at"])

            expires_at = timezone.now() + timedelta(hours=72)
            invitation, created_invite = Invitation.objects.get_or_create(
                clinic=clinic,
                user=user,
                defaults={"expires_at": expires_at},
            )
            if created_invite:
                invitation.expires_at = expires_at
                invitation.save(update_fields=["expires_at", "updated_at"])
            else:
                if invitation.accepted_at is not None:
                    return error_response("INVITE_ALREADY_ACCEPTED", status_code=400)
                invitation.expires_at = expires_at
                invitation.save(update_fields=["expires_at", "updated_at"])

            invite_token = sign_invitation_token(str(invitation.uid))

            AuditLog.objects.create(
                actor_user=request.user,
                action="HQ_CREATE_TENANT",
                scope=AuditLog.Scope.HQ,
                clinic=clinic,
                meta={
                    "clinic_slug": clinic.slug,
                    "owner_email": owner_email,
                    "invite_uid": str(invitation.uid),
                },
            )

        return ok_response(
            {
                "clinic": {"slug": clinic.slug, "name": clinic.name},
                "owner": {"email": owner_email},
                "invite_token": invite_token,
            }
        )


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


def book_appointment(
    *,
    clinic: Clinic,
    patient,
    service,
    start_local: datetime,
    source: str = "assistant",
) -> tuple[Appointment | None, str | None, bool]:
    """Create an appointment and sync with Google if possible."""
    if not start_local or not service or not patient:
        return None, "INVALID_SERVICE", False

    duration = timedelta(minutes=service.duration_minutes)
    end_local = start_local + duration
    if not _is_within_service_hours(service, start_local, end_local):
        return None, "OUT_OF_HOURS", False

    google_available, google_failed = _check_google_availability(
        clinic, start_local, end_local
    )
    if not google_available:
        return None, "SLOT_TAKEN", False

    start_utc = start_local.astimezone(dt_timezone.utc)
    end_utc = end_local.astimezone(dt_timezone.utc)

    with transaction.atomic():
        if _has_overlap(clinic, service, start_utc, end_utc):
            return None, "SLOT_TAKEN", False
        try:
            appointment = Appointment.objects.create(
                clinic=clinic,
                patient=patient,
                service=service,
                slot=(start_utc, end_utc),
                status=AppointmentStatus.BOOKED,
                source=source,
            )
        except IntegrityError:
            return None, "SLOT_TAKEN", False

    warning = False
    credential = _get_google_credential(clinic)

    if google_failed:
        appointment.sync_state = AppointmentSyncState.TENTATIVE
        appointment.google_retry_count = 0
        appointment.google_last_error = "google_sync_pending"
        appointment.save(
            update_fields=["sync_state", "google_retry_count", "google_last_error", "updated_at"]
        )
        warning = True
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
            warning = True
            schedule_google_calendar_retry(appointment.id)
    else:
        appointment.sync_state = AppointmentSyncState.OK
        appointment.google_retry_count = 0
        appointment.google_last_error = ""
        appointment.save(
            update_fields=["sync_state", "google_retry_count", "google_last_error", "updated_at"]
        )

    return appointment, None, warning


def _serialize_appointment(appointment: Appointment) -> Dict[str, object]:
    """Represent appointment with sync_state (ok|tentative|failed)."""
    return {
        "id": appointment.id,
        "service_code": appointment.service.code if appointment.service else "",
        "patient_name": appointment.patient.full_name if appointment.patient else "",
        "patient_id": appointment.patient.id if appointment.patient else None,
        "start_at": appointment.start_at.isoformat() if appointment.start_at else None,
        "end_at": appointment.end_at.isoformat() if appointment.end_at else None,
        "status": appointment.status,
        "external_event_id": appointment.external_event_id,
        "sync_state": appointment.sync_state,
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
            "phone_number_id": None,
            "business_account_id": None,
            "api_version": None,
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
    
    metadata = account.metadata or {}
    return {
        "status": status,
        "last_success_at": last_success.updated_at.isoformat() if last_success else None,
        "last_error_at": last_error.updated_at.isoformat() if last_error else None,
        "provider": account.provider_name,
        "phone_number_id": metadata.get("phone_number_id"),
        "business_account_id": metadata.get("business_account_id"),
        "api_version": metadata.get("api_version", "v18.0"),
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


def _serialize_outbox(outbox: OutboxMessage) -> Dict[str, object]:
    """Map OutboxMessage to delivery telemetry for portal polling."""
    state_map = {
        OutboxStatus.PENDING: "QUEUED",
        OutboxStatus.SENDING: "QUEUED",
        OutboxStatus.SENT: "SENT",
        OutboxStatus.DELIVERED: "DELIVERED",
        OutboxStatus.FAILED: "FAILED",
        OutboxStatus.CANCELLED: "FAILED",
    }
    state = state_map.get(outbox.status, "QUEUED")
    provider_message_id = outbox.payload.get("provider_message_id") if isinstance(outbox.payload, dict) else None
    return {
        "id": outbox.id,
        "message_type": outbox.message_type,
        "state": state,
        "provider_message_id": provider_message_id,
        "last_error": outbox.last_error or None,
        "created_at": outbox.created_at.isoformat(),
        "updated_at": outbox.updated_at.isoformat(),
    }


def _user_display_name(user: User | None) -> str:
    if user is None:
        return ""
    parts = [user.first_name.strip() if user.first_name else "", user.last_name.strip() if user.last_name else ""]
    name = " ".join(part for part in parts if part).strip()
    if name:
        return name
    if user.email:
        return user.email.split("@")[0]
    return user.username or ""


def _serialize_membership(membership: ClinicMembership) -> Dict[str, object]:
    user = membership.user
    return {
        "id": membership.id,
        "email": user.email if user else "",
        "name": _user_display_name(user),
        "role": membership.role,
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

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def put(self, request, slug: str):
        """Create or update WhatsApp channel configuration."""
        clinic: Clinic = request.clinic
        payload = request.data or {}
        
        try:
            provider = str(payload.get("provider", "meta")).strip().lower()
            phone_number_id = str(payload.get("phone_number_id", "")).strip()
            access_token = str(payload.get("access_token", "")).strip()
            business_account_id = str(payload.get("business_account_id", "")).strip()
            api_version = str(payload.get("api_version", "v18.0")).strip()
            
            if not provider or not phone_number_id:
                return error_response("INVALID_PAYLOAD", status_code=400)
            
            # Get existing account if it exists
            existing_account = ChannelAccount.objects.filter(
                clinic=clinic,
                channel=ChannelType.WHATSAPP
            ).first()
            
            # If access_token is empty and account exists, keep the old one
            if not access_token and existing_account:
                access_token = existing_account.access_token
            elif not access_token:
                return error_response("INVALID_PAYLOAD", status_code=400)
            
            # Create or update channel account
            channel_account, created = ChannelAccount.objects.update_or_create(
                clinic=clinic,
                channel=ChannelType.WHATSAPP,
                defaults={
                    "provider_name": provider,
                    "access_token": access_token,
                    "refresh_token": "",
                    "metadata": {
                        "phone_number_id": phone_number_id,
                        "business_account_id": business_account_id,
                        "api_version": api_version,
                    },
                }
            )
            
            AuditLog.objects.create(
                actor_user=request.user if request.user.is_authenticated else None,
                action="WHATSAPP_CONFIG_UPDATE",
                scope=AuditLog.Scope.CLINIC,
                clinic=clinic,
                meta={
                    "provider": provider,
                    "phone_number_id": phone_number_id,
                    "created": created,
                    "token_updated": bool(payload.get("access_token", "").strip()),
                },
            )
            
            return ok_response({
                "message": "WhatsApp channel configuration saved successfully",
                "created": created,
            })
            
        except Exception as exc:
            logger.error(
                "Failed to save WhatsApp configuration",
                extra={
                    "clinic_id": clinic.id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return error_response("INTERNAL_ERROR", status_code=500)


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

        allowlist = getattr(settings, "WHATSAPP_TEST_ALLOWLIST", {})
        allowed_numbers = allowlist.get(clinic.slug) or allowlist.get("*") or []
        if to_number not in allowed_numbers:
            return error_response("FORBIDDEN_SANDBOX_NUMBER", status_code=403)

        limit = int(getattr(settings, "WHATSAPP_TEST_RPM", 3))
        if limit > 0:
            rate_key = f"whatsapp-test:{clinic.id}"
            current = cache.get(rate_key)
            if current is None:
                cache.add(rate_key, 1, timeout=60)
            else:
                if current >= limit:
                    return error_response("RATE_LIMIT", status_code=429)
                try:
                    cache.incr(rate_key)
                except ValueError:
                    cache.set(rate_key, 1, timeout=60)

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
        metadata = outbox.metadata or {}
        metadata["sandbox_to"] = to_number
        outbox.metadata = metadata
        outbox.save(update_fields=["metadata", "updated_at"])

        AuditLog.objects.create(
            actor_user=request.user if request.user.is_authenticated else None,
            action="WHATSAPP_TEST_SEND",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={"to": to_number, "template_key": template.code, "outbox_id": outbox.id},
        )
        return ok_response({"outbox_id": outbox.id})


class ClinicOutboxStatusView(APIView):
    """Fetch WhatsApp outbox delivery state (queued/sent/delivered/failed)."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def get(self, request, slug: str, outbox_id: int):
        clinic: Clinic = request.clinic
        outbox = (
            OutboxMessage.objects.filter(id=outbox_id, clinic=clinic)
            .select_related("clinic")
            .first()
        )
        if outbox is None:
            return error_response("NOT_FOUND", status_code=404)
        return ok_response({"outbox": _serialize_outbox(outbox)})


class ClinicSetupStatusView(APIView):
    """Return clinic setup completion status for onboarding checklist."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def get(self, request, slug: str):
        clinic: Clinic = request.clinic
        
        # Check services
        has_services = clinic.services.filter(is_active=True).exists()
        
        # Check service hours
        has_hours = ServiceHours.objects.filter(service__clinic=clinic).exists()
        
        # Check WhatsApp channel
        has_whatsapp = ChannelAccount.objects.filter(
            clinic=clinic,
            channel=ChannelType.WHATSAPP
        ).exists()
        
        # Check Google Calendar
        has_google = GoogleCredential.objects.filter(clinic=clinic).exists()
        
        # Check templates
        has_templates = HSMTemplate.objects.filter(
            clinic=clinic,
            status=HSMTemplateStatus.APPROVED
        ).exists()
        
        # Check users (at least 1 user besides owner)
        has_users = ClinicMembership.objects.filter(clinic=clinic).count() > 1
        
        data = {
            "has_services": has_services,
            "has_hours": has_hours,
            "has_whatsapp": has_whatsapp,
            "has_google": has_google,
            "has_templates": has_templates,
            "has_users": has_users,
        }
        return ok_response(data)


class ClinicSettingsView(APIView):
    """Get and update clinic basic information."""

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
        # Get current user's email from membership
        membership = request.clinic_membership
        user_email = membership.user.email if membership else request.user.email
        data = {
            "name": clinic.name,
            "slug": clinic.slug,
            "phone_number": clinic.phone_number or "",
            "whatsapp_number": clinic.whatsapp_number or "",
            "address": clinic.address or "",
            "tz": clinic.tz or "UTC",
            "default_lang": clinic.default_lang or "en",
            "ai_enabled": clinic.ai_enabled,
            "email": user_email or "",
        }
        return ok_response(data)

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def put(self, request, slug: str):
        clinic: Clinic = request.clinic
        payload = request.data or {}

        name = payload.get("name", "").strip()
        phone_number = payload.get("phone_number", "").strip()
        whatsapp_number = payload.get("whatsapp_number", "").strip()
        address = payload.get("address", "").strip()
        tz = payload.get("tz", "").strip()
        default_lang = payload.get("default_lang", "").strip()
        email = str(payload.get("email", "")).strip().lower()
        ai_enabled_raw = payload.get("ai_enabled")

        if not name:
            return error_response("INVALID_NAME", status_code=400)

        valid_langs = {choice for choice, _label in LanguageChoices.choices}
        if default_lang and default_lang not in valid_langs:
            return error_response("INVALID_LANGUAGE", status_code=400)

        # Update user email if provided
        if email:
            try:
                validate_email(email)
            except ValidationError:
                return error_response("INVALID_EMAIL", status_code=400)

            existing_user = User.objects.filter(email__iexact=email).exclude(id=request.user.id).first()
            if existing_user:
                return error_response("EMAIL_ALREADY_EXISTS", status_code=400)

            if request.user.email.lower() != email:
                old_email = request.user.email
                request.user.email = email
                request.user.username = email
                request.user.save(update_fields=["email", "username", "updated_at"])

                AuditLog.objects.create(
                    actor_user=request.user,
                    action="USER_EMAIL_UPDATE",
                    scope=AuditLog.Scope.CLINIC,
                    clinic=clinic,
                    meta={
                        "old_email": old_email,
                        "new_email": email,
                    },
                )

        update_fields: list[str] = []
        if clinic.name != name:
            clinic.name = name
            update_fields.append("name")
        if phone_number is not None and clinic.phone_number != phone_number:
            clinic.phone_number = phone_number
            update_fields.append("phone_number")
        if whatsapp_number is not None and clinic.whatsapp_number != whatsapp_number:
            clinic.whatsapp_number = whatsapp_number
            update_fields.append("whatsapp_number")
        if address is not None and clinic.address != address:
            clinic.address = address
            update_fields.append("address")
        if tz and clinic.tz != tz:
            clinic.tz = tz
            update_fields.append("tz")
        if default_lang and clinic.default_lang != default_lang:
            clinic.default_lang = default_lang
            update_fields.append("default_lang")

        if ai_enabled_raw is not None:
            ai_enabled_value = bool(ai_enabled_raw)
            if clinic.ai_enabled != ai_enabled_value:
                clinic.ai_enabled = ai_enabled_value
                update_fields.append("ai_enabled")

        if update_fields:
            update_fields.append("updated_at")
            clinic.save(update_fields=update_fields)

        membership = request.clinic_membership
        user_email = membership.user.email if membership else request.user.email

        data = {
            "name": clinic.name,
            "slug": clinic.slug,
            "phone_number": clinic.phone_number or "",
            "whatsapp_number": clinic.whatsapp_number or "",
            "address": clinic.address or "",
            "tz": clinic.tz or "UTC",
            "default_lang": clinic.default_lang or "en",
            "ai_enabled": clinic.ai_enabled,
            "email": user_email or "",
        }
        return ok_response(data)


class ClinicNotificationListView(APIView):
    """List notifications for a clinic (e.g., handoff alerts)."""

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
        status_param = (request.GET.get("status") or "").lower()
        qs = Notification.objects.filter(clinic=clinic).order_by("-created_at")
        if status_param in {NotificationStatus.NEW, NotificationStatus.READ}:
            qs = qs.filter(status=status_param)

        limit = min(max(int(request.GET.get("limit", 50)), 1), 200)
        items = [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "patient_name": n.patient_name,
                "patient_phone": n.patient_phone,
                "conversation_id": n.conversation_id,
                "status": n.status,
                "type": n.type,
                "created_at": n.created_at.isoformat(),
            }
            for n in qs[:limit]
        ]
        return ok_response({"items": items})


class ClinicNotificationMarkReadView(APIView):
    """Mark a clinic notification as read."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
            ClinicMembership.Role.VIEWER,
        ]
    )
    def post(self, request, slug: str, notification_id: int):
        clinic: Clinic = request.clinic
        notification = Notification.objects.filter(id=notification_id, clinic=clinic).first()
        if notification is None:
            return error_response("NOT_FOUND", status_code=404)
        if notification.status != NotificationStatus.READ:
            notification.status = NotificationStatus.READ
            notification.save(update_fields=["status", "updated_at"])
        return ok_response({"id": notification.id, "status": notification.status})


class ClinicPatientListView(APIView):
    """Manage clinic patients (list, create)."""

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
        """List all patients for the clinic."""
        clinic: Clinic = request.clinic
        patients = clinic.patients.order_by("-created_at")
        
        # Optional search filter
        search = request.GET.get("search", "").strip()
        if search:
            patients = patients.filter(
                models.Q(full_name__icontains=search) |
                models.Q(phone_number__icontains=search) |
                models.Q(email__icontains=search)
            )
        
        items = [
            {
                "id": patient.id,
                "full_name": patient.full_name,
                "phone_number": patient.phone_number,
                "alternative_phone": patient.alternative_phone or "",
                "email": patient.email or "",
                "emergency_contact_name": patient.emergency_contact_name or "",
                "emergency_contact_phone": patient.emergency_contact_phone or "",
                "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                "age": patient.age,
                "gender": patient.gender or "",
                "city": patient.city or "",
                "district": patient.district or "",
                "address": patient.address or "",
                "allergies": patient.allergies or "",
                "chronic_diseases": patient.chronic_diseases or "",
                "current_medications": patient.current_medications or "",
                "blood_type": patient.blood_type or "",
                "notes": patient.notes or "",
                "language": patient.language,
                "ai_enabled": patient.ai_enabled,
                "created_at": patient.created_at.isoformat(),
            }
            for patient in patients
        ]
        return ok_response({"items": items})

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str):
        """Create a new patient."""
        from apps.common.normalize import normalize_phone
        from datetime import datetime
        
        clinic: Clinic = request.clinic
        payload = request.data or {}
        
        # Required fields
        full_name = str(payload.get("full_name", "")).strip()
        phone_number = str(payload.get("phone_number", "")).strip()
        
        # Optional fields
        alternative_phone = str(payload.get("alternative_phone", "")).strip()
        email = str(payload.get("email", "")).strip()
        emergency_contact_name = str(payload.get("emergency_contact_name", "")).strip()
        emergency_contact_phone = str(payload.get("emergency_contact_phone", "")).strip()
        date_of_birth = payload.get("date_of_birth")
        gender = str(payload.get("gender", "")).strip()
        city = str(payload.get("city", "")).strip()
        district = str(payload.get("district", "")).strip()
        address = str(payload.get("address", "")).strip()
        allergies = str(payload.get("allergies", "")).strip()
        chronic_diseases = str(payload.get("chronic_diseases", "")).strip()
        current_medications = str(payload.get("current_medications", "")).strip()
        blood_type = str(payload.get("blood_type", "")).strip()
        notes = str(payload.get("notes", "")).strip()
        language = str(payload.get("language", "ar")).strip()
        
        if not full_name or not phone_number:
            return error_response("INVALID_PAYLOAD", status_code=400)
        
        # Validate email if provided
        if email:
            try:
                validate_email(email)
            except ValidationError:
                return error_response("INVALID_EMAIL", status_code=400)
        
        # Normalize phone numbers
        normalized = normalize_phone(phone_number)
        normalized_alt = normalize_phone(alternative_phone) if alternative_phone else ""
        normalized_emergency = normalize_phone(emergency_contact_phone) if emergency_contact_phone else ""
        
        # Check for duplicate phone number
        if clinic.patients.filter(normalized_phone=normalized).exists():
            return error_response("PHONE_EXISTS", status_code=400)
        
        # Parse date of birth if provided
        dob = None
        if date_of_birth:
            try:
                dob = datetime.fromisoformat(date_of_birth.replace('Z', '+00:00')).date()
            except (ValueError, AttributeError):
                return error_response("INVALID_DATE", status_code=400)
        
        patient = Patient.objects.create(
            clinic=clinic,
            full_name=full_name,
            phone_number=phone_number,
            normalized_phone=normalized,
            alternative_phone=alternative_phone,
            email=email,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
            date_of_birth=dob,
            gender=gender,
            city=city,
            district=district,
            address=address,
            allergies=allergies,
            chronic_diseases=chronic_diseases,
            current_medications=current_medications,
            blood_type=blood_type,
            notes=notes,
            language=language,
            ai_enabled=True,
        )
        
        AuditLog.objects.create(
            actor_user=request.user,
            action="PATIENT_CREATE",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={"patient_id": patient.id, "full_name": full_name},
        )
        
        return ok_response({
            "id": patient.id,
            "full_name": patient.full_name,
            "phone_number": patient.phone_number,
            "alternative_phone": patient.alternative_phone or "",
            "email": patient.email or "",
            "emergency_contact_name": patient.emergency_contact_name or "",
            "emergency_contact_phone": patient.emergency_contact_phone or "",
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "age": patient.age,
            "gender": patient.gender or "",
            "city": patient.city or "",
            "district": patient.district or "",
            "address": patient.address or "",
            "allergies": patient.allergies or "",
            "chronic_diseases": patient.chronic_diseases or "",
            "current_medications": patient.current_medications or "",
            "blood_type": patient.blood_type or "",
            "notes": patient.notes or "",
            "language": patient.language,
            "ai_enabled": patient.ai_enabled,
            "created_at": patient.created_at.isoformat(),
        })


class ClinicPatientDetailView(APIView):
    """Update or delete a specific patient."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def put(self, request, slug: str, patient_id: int):
        """Update patient information."""
        from apps.common.normalize import normalize_phone
        from datetime import datetime
        
        clinic: Clinic = request.clinic
        patient = clinic.patients.filter(id=patient_id).first()
        
        if not patient:
            return error_response("PATIENT_NOT_FOUND", status_code=404)
        
        payload = request.data or {}
        
        # Required fields
        full_name = str(payload.get("full_name", "")).strip()
        phone_number = str(payload.get("phone_number", "")).strip()
        
        # Optional fields
        alternative_phone = str(payload.get("alternative_phone", "")).strip()
        email = str(payload.get("email", "")).strip()
        emergency_contact_name = str(payload.get("emergency_contact_name", "")).strip()
        emergency_contact_phone = str(payload.get("emergency_contact_phone", "")).strip()
        date_of_birth = payload.get("date_of_birth")
        gender = str(payload.get("gender", "")).strip()
        city = str(payload.get("city", "")).strip()
        district = str(payload.get("district", "")).strip()
        address = str(payload.get("address", "")).strip()
        allergies = str(payload.get("allergies", "")).strip()
        chronic_diseases = str(payload.get("chronic_diseases", "")).strip()
        current_medications = str(payload.get("current_medications", "")).strip()
        blood_type = str(payload.get("blood_type", "")).strip()
        notes = str(payload.get("notes", "")).strip()
        language = str(payload.get("language", patient.language)).strip()
        ai_enabled_raw = payload.get("ai_enabled", patient.ai_enabled)
        
        if not full_name or not phone_number:
            return error_response("INVALID_PAYLOAD", status_code=400)
        
        # Validate email if provided
        if email:
            try:
                validate_email(email)
            except ValidationError:
                return error_response("INVALID_EMAIL", status_code=400)
        
        # Normalize phone numbers
        normalized = normalize_phone(phone_number)
        
        # Check for duplicate phone number (excluding current patient)
        if clinic.patients.filter(normalized_phone=normalized).exclude(id=patient_id).exists():
            return error_response("PHONE_EXISTS", status_code=400)
        
        # Parse date of birth if provided
        dob = patient.date_of_birth
        if date_of_birth:
            try:
                dob = datetime.fromisoformat(date_of_birth.replace('Z', '+00:00')).date()
            except (ValueError, AttributeError):
                return error_response("INVALID_DATE", status_code=400)
        
        # Update all fields
        patient.full_name = full_name
        patient.phone_number = phone_number
        patient.normalized_phone = normalized
        patient.alternative_phone = alternative_phone
        patient.email = email
        patient.emergency_contact_name = emergency_contact_name
        patient.emergency_contact_phone = emergency_contact_phone
        patient.date_of_birth = dob
        patient.gender = gender
        patient.city = city
        patient.district = district
        patient.address = address
        patient.allergies = allergies
        patient.chronic_diseases = chronic_diseases
        patient.current_medications = current_medications
        patient.blood_type = blood_type
        patient.notes = notes
        patient.language = language
        patient.ai_enabled = bool(ai_enabled_raw)
        patient.save()
        
        AuditLog.objects.create(
            actor_user=request.user,
            action="PATIENT_UPDATE",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={"patient_id": patient.id, "full_name": full_name},
        )
        
        return ok_response({
            "id": patient.id,
            "full_name": patient.full_name,
            "phone_number": patient.phone_number,
            "alternative_phone": patient.alternative_phone or "",
            "email": patient.email or "",
            "emergency_contact_name": patient.emergency_contact_name or "",
            "emergency_contact_phone": patient.emergency_contact_phone or "",
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "age": patient.age,
            "gender": patient.gender or "",
            "city": patient.city or "",
            "district": patient.district or "",
            "address": patient.address or "",
            "allergies": patient.allergies or "",
            "chronic_diseases": patient.chronic_diseases or "",
            "current_medications": patient.current_medications or "",
            "blood_type": patient.blood_type or "",
            "notes": patient.notes or "",
            "language": patient.language,
            "ai_enabled": patient.ai_enabled,
            "created_at": patient.created_at.isoformat(),
        })

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
        ]
    )
    def delete(self, request, slug: str, patient_id: int):
        """Delete a patient."""
        clinic: Clinic = request.clinic
        patient = clinic.patients.filter(id=patient_id).first()
        
        if not patient:
            return error_response("PATIENT_NOT_FOUND", status_code=404)
        
        # Check if patient has appointments
        if patient.appointments.exists():
            return error_response("PATIENT_HAS_APPOINTMENTS", status_code=400)
        
        patient_name = patient.full_name
        patient.delete()
        
        AuditLog.objects.create(
            actor_user=request.user,
            action="PATIENT_DELETE",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={"patient_id": patient_id, "full_name": patient_name},
        )
        
        return ok_response({"message": "Patient deleted successfully"})


class ClinicPatientAIToggleView(APIView):
    """Enable/disable AI for a specific patient."""

    permission_classes = [permissions.IsAuthenticated]

    @require_clinic_role(
        allowed=[
            ClinicMembership.Role.OWNER,
            ClinicMembership.Role.ADMIN,
            ClinicMembership.Role.STAFF,
        ]
    )
    def post(self, request, slug: str, patient_id: int):
        clinic: Clinic = request.clinic
        patient = clinic.patients.filter(id=patient_id).first()
        if not patient:
            return error_response("PATIENT_NOT_FOUND", status_code=404)

        payload = request.data or {}
        ai_enabled = payload.get("ai_enabled")
        if ai_enabled is None:
            return error_response("INVALID_PAYLOAD", status_code=400)

        patient.ai_enabled = bool(ai_enabled)
        patient.save(update_fields=["ai_enabled", "updated_at"])

        AuditLog.objects.create(
            actor_user=request.user,
            action="PATIENT_AI_TOGGLE",
            scope=AuditLog.Scope.CLINIC,
            clinic=clinic,
            meta={"patient_id": patient.id, "ai_enabled": patient.ai_enabled},
        )

        return ok_response({"id": patient.id, "ai_enabled": patient.ai_enabled})
logger = logging.getLogger(__name__)
