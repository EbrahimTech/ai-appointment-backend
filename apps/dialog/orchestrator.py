"""Coordinates dialog FSM, intent detection, and LLM handoffs."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Tuple

from django.conf import settings
from django.utils import timezone
from zoneinfo import ZoneInfo

from apps.appointments.scheduling import SuggestedSlot, find_available_slots, suggest_slots
from apps.accounts.views import book_appointment, reschedule_appointment
from apps.channels.services import enqueue_whatsapp_session_message
from apps.conversations.models import Conversation, ConversationMessage, SessionState
from apps.dialog.fsm import DialogFSM
from apps.dialog.intent import detect_intent
from apps.dialog.normalization import normalize_text
from apps.llm.router import LLMRouter, LLMRouterError

logger = logging.getLogger(__name__)

AR_FALLBACK_MESSAGE = "سأحولك إلى فريق خدمة العملاء."
AR_CONFIRM_MESSAGE = "تم التأكيد. نراك قريباً!"
AR_CANCEL_MESSAGE = "تم إلغاء الموعد بناءً على طلبك."
AR_RESCHEDULE_MESSAGE = "دعنا نختار موعداً جديداً."
AR_GUEST_FALLBACK = "ضيفنا"
AR_NO_AVAILABILITY = "أراجع التقويم وأعود إليك بالخيارات."
AR_TENTATIVE_NOTE = " (موعد مؤقت)"
AR_SINGLE_SLOT_PROMPT = "أقترح {slot}. هل يناسبك؟"
AR_DOUBLE_SLOT_PROMPT = "أستطيع حجز {slot1} أو {slot2}. أيهما أفضل لك؟"


class DialogOrchestrator:
    """Main entrypoint for inbound WhatsApp message handling."""

    def __init__(self) -> None:
        self.fsm = DialogFSM()
        self.llm_router = LLMRouter()

    def handle_inbound(
        self,
        conversation: Conversation,
        body: str,
        language: str,
    ) -> Tuple[str | None, str]:
        if (
            conversation.patient
            and conversation.patient.language
            and not self._contains_letters(body)
        ):
            language = conversation.patient.language
        normalized = normalize_text(body)
        intent = "greet" if self._is_greeting(normalized) else detect_intent(normalized)
        general_inquiry = self._is_general_inquiry(normalized)
        explicit_booking = self._is_explicit_booking_request(normalized)
        handoff_question = self._is_handoff_question(normalized)
        resume_bot = self._wants_bot_resume(normalized)
        # LLM intent fallback (structured) to better understand Arabic/free-form requests
        if intent == "clarify" and getattr(settings, "LLM_INTENT_ENABLED", True) and not general_inquiry:
            try:
                intent_result = self.llm_router.classify_intent(
                    clinic=conversation.clinic,
                    language=language,
                    prompt=body,
                )
                if intent_result:
                    conf = intent_result.get("confidence", 0)
                    threshold = float(getattr(settings, "LLM_INTENT_CONF_THRESHOLD", 0.55))
                    if conf >= threshold and intent_result.get("intent") != "off_topic":
                        intent = intent_result.get("intent", intent)
                    session_state, _ = SessionState.objects.get_or_create(conversation=conversation)
                    session_state.context["llm_intent"] = intent_result
                    session_state.save(update_fields=["context", "updated_at"])
            except LLMRouterError as exc:
                logger.warning("LLM intent fallback skipped: %s", exc)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("LLM intent fallback error: %s", exc, exc_info=True)
        if general_inquiry:
            intent = "clarify"
        elif intent == "book" and not explicit_booking and not self._asks_for_slots(body):
            intent = "clarify"
        previous_inbound = (
            conversation.messages.filter(direction="inbound").order_by("-created_at").first()
        )
        inbound_message = ConversationMessage.objects.create(
            conversation=conversation,
            direction="inbound",
            language=language,
            body=body,
            normalized_body=normalized,
            intent=intent,
            metadata={"received_at": timezone.now().isoformat()},
        )

        session_state, _ = SessionState.objects.get_or_create(conversation=conversation)
        if general_inquiry:
            self._clear_booking_flow(session_state)
            self._clear_action_flow(session_state)
            session_state.context.pop("slot_suggestions", None)
            session_state.context.pop("slot_offer_prompt", None)
            session_state.context.pop("slot_service_code", None)
            session_state.context.pop("reschedule_appointment_id", None)
            session_state.save(update_fields=["context", "updated_at"])
        response_text: str | None = None
        queue_session = True
        suppress_duplicate = False
        now = timezone.now()
        repeat_tracker = session_state.context.get(
            "repeat_tracker",
            {"intent": intent, "count": 0, "last_seen": now.isoformat()},
        )

        # Suppress auto-replies for rapid duplicate messages (same normalized text)
        duplicate_window_minutes = int(getattr(settings, "WHATSAPP_DUPLICATE_SUPPRESS_MINUTES", 5))
        if previous_inbound and previous_inbound.normalized_body == normalized:
            if (timezone.now() - previous_inbound.created_at) <= timedelta(minutes=duplicate_window_minutes):
                suppress_duplicate = True

        if suppress_duplicate and (
            session_state.context.get("slot_suggestions")
            or session_state.context.get("action_flow")
            or session_state.context.get("pending_action")
        ):
            suppress_duplicate = False

        if suppress_duplicate:
            logger.info(
                "Suppressing duplicate inbound for conversation %s within %s minutes",
                conversation.id,
                duplicate_window_minutes,
            )
            return None, intent

        # Respect clinic-level AI toggle: pause automation and alert operators
        patient_ai_enabled = True
        if getattr(conversation, "patient", None) and conversation.patient.ai_enabled is False:
            patient_ai_enabled = False

        if not conversation.clinic.ai_enabled or not patient_ai_enabled:
            if not conversation.handoff_required:
                conversation.handoff_required = True
                conversation.save(update_fields=["handoff_required", "updated_at"])
                try:
                    from apps.accounts.notifications import notify_handoff

                    notify_handoff(conversation)
                except Exception as err:  # pragma: no cover - best effort logging
                    logger.warning("Failed to create handoff notification: %s", err)
                return None, "handoff"

        if conversation.handoff_required:
            if resume_bot:
                conversation.handoff_required = False
                conversation.save(update_fields=["handoff_required", "updated_at"])
                session_state.context.pop("handoff_reason", None)
                session_state.save(update_fields=["context", "updated_at"])
                response_text = (
                    "تم تفعيل المساعد مرة أخرى. كيف أقدر أساعدك؟"
                    if language == "ar"
                    else "Assistant is active again. How can I help you?"
                )
                response_text = self._send_outbound_message(
                    conversation=conversation,
                    language=language,
                    body=response_text,
                    intent="clarify",
                    metadata={"auto_reply": True, "reason": "resume_bot"},
                    idempotency_key=f"resume:{conversation.id}:{inbound_message.id}",
                    queue_session=queue_session,
                )
                return response_text, "clarify"
            if handoff_question:
                response_text = self._handoff_explanation(session_state, language)
                response_text = self._send_outbound_message(
                    conversation=conversation,
                    language=language,
                    body=response_text,
                    intent="handoff",
                    metadata={"auto_reply": True, "reason": "handoff_explain"},
                    idempotency_key=f"handoff-explain:{conversation.id}:{inbound_message.id}",
                    queue_session=queue_session,
                )
                return response_text, "handoff"
            return None, "handoff"

        pending_action = session_state.context.get("pending_action")
        if pending_action:
            pending_reply = self._handle_pending_action(
                conversation=conversation,
                session_state=session_state,
                body=body,
                language=language,
                pending=pending_action,
            )
            if pending_reply:
                response_text, pending_intent = pending_reply
                response_text = self._send_outbound_message(
                    conversation=conversation,
                    language=language,
                    body=response_text,
                    intent=pending_intent,
                    metadata={"auto_reply": True, "pending_action": True},
                    idempotency_key=f"{conversation.id}:{inbound_message.id}",
                    queue_session=queue_session,
                )
                return response_text, pending_intent

        if general_inquiry:
            try:
                response_text = self.llm_router.answer(
                    clinic=conversation.clinic,
                    language=language,
                    prompt=body,
                    conversation_id=conversation.id,
                )
            except LLMRouterError as exc:
                logger.warning("LLM general inquiry skipped: %s", exc)
                response_text = (
                    "أكيد، تفضل سؤالك. أقدر أساعدك بالحجز أو الاستفسارات عن خدمات العيادة."
                    if language == "ar"
                    else "Sure—what would you like to know? I can help with bookings or clinic info."
                )
            response_text = self._send_outbound_message(
                conversation=conversation,
                language=language,
                body=response_text,
                intent="clarify",
                metadata={"auto_reply": True, "reason": "general_inquiry"},
                idempotency_key=f"general:{conversation.id}:{inbound_message.id}",
                queue_session=queue_session,
            )
            return response_text, "clarify"

        if intent == "greet":
            response_text = (
                "أهلًا! كيف أقدر أساعدك بحجز موعد؟"
                if language == "ar"
                else "Hi! How can I help you book an appointment?"
            )
            response_text = self._send_outbound_message(
                conversation=conversation,
                language=language,
                body=response_text,
                intent="greet",
                metadata={"auto_reply": True},
                idempotency_key=f"greet:{conversation.id}:{inbound_message.id}",
            )
            return response_text, "greet"

        if intent == "clarify" and self._is_gratitude(normalized):
            response_text = (
                "العفو! إذا احتجت أي شيء آخر أخبرني."
                if language == "ar"
                else "You're welcome! Let me know if you need anything else."
            )
            response_text = self._send_outbound_message(
                conversation=conversation,
                language=language,
                body=response_text,
                intent="clarify",
                metadata={"auto_reply": True, "reason": "gratitude"},
                idempotency_key=f"gratitude:{conversation.id}:{inbound_message.id}",
            )
            return response_text, "clarify"

        if intent == "book" and self._is_booking_complaint(normalized):
            response_text = (
                "هل ترغب بحجز موعد الآن؟"
                if language == "ar"
                else "Would you like to book an appointment now?"
            )
            response_text = self._send_outbound_message(
                conversation=conversation,
                language=language,
                body=response_text,
                intent="clarify",
                metadata={"auto_reply": True, "reason": "booking_complaint"},
                idempotency_key=f"booking-clarify:{conversation.id}:{inbound_message.id}",
            )
            return response_text, "clarify"

        slot_suggestions = session_state.context.get("slot_suggestions") or []
        preselected_slot = None
        reschedule_appointment_id = session_state.context.get("reschedule_appointment_id")
        should_attempt_slot_selection = bool(slot_suggestions) and intent != "cancel"
        if intent == "reschedule" and not reschedule_appointment_id:
            should_attempt_slot_selection = False
        if should_attempt_slot_selection:
            preselected_slot = self._select_slot_from_reply(body, slot_suggestions, conversation.clinic.tz)
            if not preselected_slot and getattr(settings, "LLM_TOOL_BOOKING_ENABLED", False):
                try:
                    idx = self.llm_router.select_slot_from_reply(
                        clinic=conversation.clinic,
                        language=language,
                        prompt=body,
                        slots=slot_suggestions,
                        conversation_id=conversation.id,
                    )
                    if idx and 1 <= idx <= len(slot_suggestions):
                        preselected_slot = slot_suggestions[idx - 1]
                except LLMRouterError as exc:
                    logger.warning("LLM slot selection skipped: %s", exc)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("LLM slot selection error: %s", exc, exc_info=True)
            if preselected_slot:
                intent = "confirm"

        booking_flow = session_state.context.get("booking_flow") or {}
        should_handle_booking_flow = False
        if intent == "book":
            should_handle_booking_flow = True
        elif self._asks_for_slots(body) and intent not in {"confirm", "cancel", "reschedule"}:
            should_handle_booking_flow = True
        elif booking_flow and booking_flow.get("state") not in {"BOOKED", "DONE"} and intent not in {"confirm", "cancel", "reschedule"}:
            should_handle_booking_flow = True

        if should_handle_booking_flow:
            response_text = self._handle_booking_flow(
                conversation=conversation,
                session_state=session_state,
                body=body,
                language=language,
                intent=intent,
            )
            if response_text:
                response_text = self._send_outbound_message(
                    conversation=conversation,
                    language=language,
                    body=response_text,
                    intent="book",
                    metadata={"auto_reply": True, "flow": "booking"},
                    idempotency_key=f"booking:{conversation.id}:{inbound_message.id}",
                )
                return response_text, "book"

        action_reply = self._handle_action_flow(
            conversation=conversation,
            session_state=session_state,
            body=body,
            language=language,
            intent=intent,
        )
        if action_reply:
            response_text, action_intent = action_reply
            response_text = self._send_outbound_message(
                conversation=conversation,
                language=language,
                body=response_text,
                intent=action_intent,
                metadata={"auto_reply": True, "flow": "action"},
                idempotency_key=f"action:{conversation.id}:{inbound_message.id}",
            )
            return response_text, action_intent

        # Track repeated unproductive intents to auto-handoff
        productive_intents = {"book", "confirm", "cancel", "reschedule", "pricing", "services", "xray", "policy"}
        repeat_threshold = int(getattr(settings, "WHATSAPP_REPEAT_HANDOFF_THRESHOLD", 3))
        repeat_window_minutes = int(
            getattr(settings, "WHATSAPP_REPEAT_RESET_MINUTES", 30)
        )

        last_seen_iso = repeat_tracker.get("last_seen")
        try:
            last_seen = timezone.datetime.fromisoformat(last_seen_iso) if last_seen_iso else None
            if last_seen and timezone.is_naive(last_seen):
                last_seen = timezone.make_aware(last_seen)
        except Exception:
            last_seen = None

        within_window = False
        if last_seen:
            within_window = (now - last_seen) <= timedelta(minutes=repeat_window_minutes)

        if intent in productive_intents:
            repeat_tracker = {"intent": intent, "count": 0, "last_seen": now.isoformat()}
        else:
            if repeat_tracker.get("intent") == intent and within_window:
                repeat_tracker["count"] += 1
            else:
                repeat_tracker = {"intent": intent, "count": 1, "last_seen": now.isoformat()}

        repeat_tracker["last_seen"] = now.isoformat()

        session_state.context["repeat_tracker"] = repeat_tracker
        session_state.save(update_fields=["context", "updated_at"])

        if (
            repeat_tracker.get("intent") not in productive_intents
            and repeat_tracker.get("count", 0) >= repeat_threshold
        ):
            conversation.handoff_required = True
            conversation.save(update_fields=["handoff_required", "updated_at"])
            # reset repeat tracker to avoid immediate retrigger after manual handoff clear
            session_state.context["repeat_tracker"] = {"intent": intent, "count": 0, "last_seen": now.isoformat()}
            session_state.save(update_fields=["context", "updated_at"])
            try:
                from apps.accounts.notifications import notify_handoff

                notify_handoff(conversation)
            except Exception as err:  # pragma: no cover - best effort logging
                logger.warning("Failed to create handoff notification: %s", err)

            response_text = AR_FALLBACK_MESSAGE if language == "ar" else "I'll connect you with our support team."
            response_text = self._send_outbound_message(
                conversation=conversation,
                language=language,
                body=response_text,
                intent="handoff",
                metadata={"auto_reply": True, "reason": "repeat_intent_threshold"},
                idempotency_key=f"handoff:{conversation.id}:{inbound_message.id}",
            )
            return response_text, "handoff"

        # إذا كان التحويل للبشري مفعلاً، لا نرد تلقائياً
        if conversation.handoff_required:
            return None, "handoff"

        if intent == "book":
            self.fsm.apply(conversation, "qualified", context={"message": body, "is_off_topic": False})
            slots: list[SuggestedSlot] | None
            if getattr(settings, "LLM_TOOL_CALLING_ENABLED", False):
                try:
                    tool_reply, tool_slots, tool_meta = self.llm_router.answer_with_tools(
                        clinic=conversation.clinic,
                        language=language,
                        prompt=body,
                        conversation_id=conversation.id,
                    )
                    if tool_reply:
                        if tool_meta and tool_meta.get("action") == "booked":
                            session_state.context.pop("slot_suggestions", None)
                            session_state.context.pop("slot_service_code", None)
                            session_state.context.pop("slot_offer_prompt", None)
                            session_state.context.pop("reschedule_appointment_id", None)
                            self._clear_booking_flow(session_state)
                            session_state.save(update_fields=["context", "updated_at"])
                        elif tool_slots:
                            session_state.context["slot_suggestions"] = [
                                {
                                    "start": slot.start.isoformat(),
                                    "end": slot.end.isoformat(),
                                    "tentative": slot.tentative,
                                    "source": slot.source,
                                }
                                for slot in tool_slots
                            ]
                            session_state.context["slot_offer_prompt"] = tool_reply
                            if tool_meta and tool_meta.get("service_code"):
                                session_state.context["slot_service_code"] = tool_meta.get("service_code")
                            session_state.save(update_fields=["context", "updated_at"])
                        response_text = tool_reply
                        slots = None
                    else:
                        default_service = conversation.clinic.services.filter(is_active=True).order_by("duration_minutes").first()
                        slots = suggest_slots(conversation.clinic, service=default_service)
                        if default_service:
                            session_state.context["slot_service_code"] = default_service.code
                except LLMRouterError as exc:
                    logger.warning("LLM tool call skipped: %s", exc)
                    default_service = conversation.clinic.services.filter(is_active=True).order_by("duration_minutes").first()
                    slots = suggest_slots(conversation.clinic, service=default_service)
                    if default_service:
                        session_state.context["slot_service_code"] = default_service.code
            else:
                default_service = conversation.clinic.services.filter(is_active=True).order_by("duration_minutes").first()
                slots = suggest_slots(conversation.clinic, service=default_service)
                if default_service:
                    session_state.context["slot_service_code"] = default_service.code
            if slots is not None:
                if slots:
                    prompt = self._build_slot_prompt(slots, language, conversation.clinic.tz)
                    session_state.context["slot_suggestions"] = [
                        {
                            "start": slot.start.isoformat(),
                            "end": slot.end.isoformat(),
                            "tentative": slot.tentative,
                            "source": slot.source,
                        }
                        for slot in slots
                    ]
                    session_state.context["slot_offer_prompt"] = prompt
                    session_state.save(update_fields=["context", "updated_at"])
                    response_text = prompt
                else:
                    response_text = AR_NO_AVAILABILITY if language == "ar" else "I'll review the calendar and follow up with options."
        elif intent in {"confirm", "cancel", "reschedule"}:
            self.fsm.apply(conversation, intent, context={"message": body, "is_off_topic": False})
            if intent in {"cancel", "reschedule"} and getattr(settings, "LLM_TOOL_CALLING_ENABLED", False):
                try:
                    plan = self.llm_router.plan_tool_call(
                        clinic=conversation.clinic,
                        language=language,
                        prompt=body,
                        conversation=conversation,
                    )
                    if not plan:
                        response_text = self._handle_terminal_intent(conversation, intent, language)
                    elif "reply" in plan:
                        response_text = str(plan.get("reply") or "")
                    else:
                        tool_name = plan.get("tool")
                        args = plan.get("args") or {}
                        if tool_name not in {"cancel_appointment", "reschedule_appointment"}:
                            response_text = self._handle_terminal_intent(conversation, intent, language)
                        else:
                            appointment = self.llm_router.resolve_appointment_for_confirmation(
                                clinic=conversation.clinic,
                                conversation=conversation,
                                appointment_id=args.get("appointment_id"),
                                start_iso=args.get("start_iso"),
                            )
                            if not appointment:
                                response_text = (
                                    "Please share the date and time of the appointment."
                                    if language != "ar"
                                    else "يرجى ذكر تاريخ ووقت الموعد."
                                )
                            else:
                                args["appointment_id"] = appointment.id
                                if tool_name == "reschedule_appointment" and not args.get("new_start_iso"):
                                    session_state.context["pending_action"] = {
                                        "tool": tool_name,
                                        "args": {"appointment_id": appointment.id},
                                        "appointment_id": appointment.id,
                                        "stage": "await_time",
                                    }
                                    session_state.save(update_fields=["context", "updated_at"])
                                    response_text = (
                                        "What time would you like instead?"
                                        if language != "ar"
                                        else "ما الوقت الجديد المناسب؟"
                                    )
                                else:
                                    response_text = self._build_confirmation_prompt(
                                        tool_name=tool_name,
                                        appointment=appointment,
                                        new_start_iso=args.get("new_start_iso"),
                                        language=language,
                                        clinic_tz=conversation.clinic.tz,
                                    )
                                    session_state.context["pending_action"] = {
                                        "tool": tool_name,
                                        "args": args,
                                        "appointment_id": appointment.id,
                                        "stage": "confirm",
                                    }
                                    session_state.save(update_fields=["context", "updated_at"])
                    queue_session = True
                except LLMRouterError as exc:
                    logger.warning("LLM tool plan skipped: %s", exc)
                    response_text = self._handle_terminal_intent(conversation, intent, language)
                    queue_session = True
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("LLM tool plan error: %s", exc, exc_info=True)
                    response_text = self._handle_terminal_intent(conversation, intent, language)
                    queue_session = True
            elif intent == "confirm" and getattr(settings, "LLM_TOOL_BOOKING_ENABLED", False):
                slot_suggestions = session_state.context.get("slot_suggestions") or []
                service_code = session_state.context.get("slot_service_code")
                selected = preselected_slot or self._select_slot_from_reply(body, slot_suggestions, conversation.clinic.tz)
                if not selected and slot_suggestions:
                    try:
                        idx = self.llm_router.select_slot_from_reply(
                            clinic=conversation.clinic,
                            language=language,
                            prompt=body,
                            slots=slot_suggestions,
                            conversation_id=conversation.id,
                        )
                        if idx and 1 <= idx <= len(slot_suggestions):
                            selected = slot_suggestions[idx - 1]
                    except LLMRouterError as exc:
                        logger.warning("LLM slot selection skipped: %s", exc)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.error("LLM slot selection error: %s", exc, exc_info=True)
                if reschedule_appointment_id and selected and conversation.patient:
                    try:
                        from apps.appointments.models import Appointment

                        appointment = Appointment.objects.filter(
                            id=reschedule_appointment_id,
                            clinic=conversation.clinic,
                            patient=conversation.patient,
                        ).first()
                    except Exception:
                        appointment = None
                    try:
                        start_local = datetime.fromisoformat(selected.get("start", ""))
                    except (TypeError, ValueError):
                        start_local = None
                    if start_local and start_local.tzinfo is None:
                        start_local = start_local.replace(tzinfo=ZoneInfo(conversation.clinic.tz or "UTC"))

                    if appointment and start_local:
                        appointment, error_code, tentative = reschedule_appointment(
                            clinic=conversation.clinic,
                            appointment=appointment,
                            start_local=start_local,
                        )
                        if appointment:
                            session_state.context.pop("slot_suggestions", None)
                            session_state.context.pop("slot_service_code", None)
                            session_state.context.pop("slot_offer_prompt", None)
                            session_state.context.pop("reschedule_appointment_id", None)
                            session_state.save(update_fields=["context", "updated_at"])
                            time_label = self._format_datetime_label(
                                start_local.astimezone(ZoneInfo(conversation.clinic.tz or "UTC")),
                                language,
                            )
                            suffix = ""
                            if tentative:
                                suffix = AR_TENTATIVE_NOTE if language == "ar" else " (tentative hold)"
                            if language == "ar":
                                response_text = f"تم تعديل موعدك إلى {time_label}.{suffix}"
                            else:
                                response_text = f"Your appointment has been rescheduled to {time_label}.{suffix}"
                            try:
                                response_text = self.llm_router.compose_action_reply(
                                    language=language,
                                    action="reschedule",
                                    time_label=time_label,
                                    clinic_name=conversation.clinic.name,
                                    conversation_id=conversation.id,
                                )
                            except LLMRouterError as exc:
                                logger.warning("LLM action reply skipped: %s", exc)
                            except Exception as exc:  # pragma: no cover - defensive
                                logger.error("LLM action reply error: %s", exc, exc_info=True)
                            queue_session = True
                        else:
                            error_text = "That time is no longer available. Please choose another time."
                            if error_code == "OUT_OF_HOURS":
                                error_text = "That time is outside our working hours. Please choose another time."
                            if language == "ar":
                                error_text = "الوقت غير متاح. فضلاً اختر وقتاً آخر."
                            response_text = error_text
                            queue_session = True
                    else:
                        slot_prompt = session_state.context.get("slot_offer_prompt")
                        if slot_prompt:
                            response_text = slot_prompt
                        else:
                            response_text = (
                                "Please choose one of the suggested times (e.g., 1 or 2)."
                                if language != "ar"
                                else "يرجى اختيار أحد الأوقات المقترحة (مثال: 1 أو 2)."
                            )
                        queue_session = True
                elif selected and service_code and conversation.patient:
                    service = conversation.clinic.services.filter(code=service_code).first()
                    try:
                        start_local = datetime.fromisoformat(selected.get("start", ""))
                    except (TypeError, ValueError):
                        start_local = None
                    if start_local and start_local.tzinfo is None:
                        start_local = start_local.replace(tzinfo=ZoneInfo(conversation.clinic.tz or "UTC"))

                    if service and start_local:
                        appointment, error_code, tentative = book_appointment(
                            clinic=conversation.clinic,
                            patient=conversation.patient,
                            service=service,
                            start_local=start_local,
                            source="assistant",
                        )
                        if appointment:
                            session_state.context.pop("slot_suggestions", None)
                            session_state.context.pop("slot_service_code", None)
                            session_state.context.pop("slot_offer_prompt", None)
                            self._clear_booking_flow(session_state)
                            session_state.save(update_fields=["context", "updated_at"])
                            time_label = self._format_datetime_label(
                                start_local.astimezone(ZoneInfo(conversation.clinic.tz or "UTC")),
                                language,
                            )
                            suffix = ""
                            if tentative:
                                suffix = AR_TENTATIVE_NOTE if language == "ar" else " (tentative hold)"
                            if language == "ar":
                                response_text = f"تم حجز موعدك في {time_label}.{suffix}"
                            else:
                                response_text = f"Your appointment is booked for {time_label}.{suffix}"
                            try:
                                response_text = self.llm_router.compose_action_reply(
                                    language=language,
                                    action="confirm",
                                    time_label=time_label,
                                    clinic_name=conversation.clinic.name,
                                    conversation_id=conversation.id,
                                )
                            except LLMRouterError as exc:
                                logger.warning("LLM action reply skipped: %s", exc)
                            except Exception as exc:  # pragma: no cover - defensive
                                logger.error("LLM action reply error: %s", exc, exc_info=True)
                            queue_session = True
                        else:
                            error_text = "That slot is no longer available. Please choose another time."
                            if language == "ar":
                                error_text = "هذا الموعد لم يعد متاحًا. يرجى اختيار وقت آخر."
                            response_text = error_text
                            queue_session = True
                    else:
                        response_text = self._handle_terminal_intent(conversation, intent, language)
                        queue_session = True
                elif slot_suggestions:
                    slot_prompt = session_state.context.get("slot_offer_prompt")
                    if slot_prompt:
                        response_text = slot_prompt
                    else:
                        response_text = (
                            "Please choose one of the suggested times (e.g., 1 or 2)."
                            if language != "ar"
                            else "يرجى اختيار أحد الأوقات المقترحة (مثال: 1 أو 2)."
                        )
                    queue_session = True
                else:
                    response_text = self._handle_terminal_intent(conversation, intent, language)
                    queue_session = True
            else:
                response_text = self._handle_terminal_intent(conversation, intent, language)
                queue_session = True
        else:
            try:
                response_text = self.llm_router.answer(
                    clinic=conversation.clinic,
                    language=language,
                    prompt=body,
                    conversation_id=conversation.id,
                )
            except LLMRouterError as exc:
                error_code = str(exc)
                logger.warning("LLM fallback (%s): %s", error_code, exc)
                if error_code in {"llm_budget_exhausted", "rag_context_missing", "llm_timeout", "llm_latency_exceeded", "llm_provider_error"}:
                    response_text = (
                        AR_FALLBACK_MESSAGE if language == "ar" else "I'll connect you with our support team."
                    )
                    queue_session = True
                else:
                    response_text = (
                        AR_FALLBACK_MESSAGE if language == "ar" else "I'll connect you with our support team."
                    )
                    if not conversation.handoff_required:
                        conversation.handoff_required = True
                        conversation.save(update_fields=["handoff_required", "updated_at"])
                        try:
                            from apps.accounts.notifications import notify_handoff

                            notify_handoff(conversation)
                        except Exception as err:  # pragma: no cover - best effort logging
                            logger.warning("Failed to create handoff notification: %s", err)

        if response_text:
            response_text = self._send_outbound_message(
                conversation=conversation,
                language=language,
                body=response_text,
                intent="reply",
                metadata={"auto_reply": True},
                idempotency_key=f"{conversation.id}:{inbound_message.id}",
                queue_session=queue_session,
            )
        return response_text, intent

    def _send_outbound_message(
        self,
        *,
        conversation: Conversation,
        language: str,
        body: str | None,
        intent: str,
        metadata: dict,
        idempotency_key: str,
        queue_session: bool = True,
    ) -> str:
        clean_body = self._sanitize_response(conversation, body or "", language)
        if not clean_body:
            clean_body = (
                AR_FALLBACK_MESSAGE if language == "ar" else "I'll connect you with our support team."
            )
        ConversationMessage.objects.create(
            conversation=conversation,
            direction="outbound",
            language=language,
            body=clean_body,
            intent=intent,
            metadata=metadata,
        )
        if queue_session:
            enqueue_whatsapp_session_message(
                clinic_id=conversation.clinic_id,
                conversation=conversation,
                language=language,
                message_body=clean_body,
                idempotency_key=idempotency_key,
            )
        return clean_body

    def _sanitize_response(self, conversation: Conversation, text: str, language: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return cleaned
        cleaned = self._strip_service_codes(cleaned, conversation, language)
        cleaned = self._strip_extra_questions(cleaned)
        if language == "ar":
            cleaned = re.sub(r"\(\s*[A-Za-z0-9 _-]+\s*\)", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        cleaned = re.sub(r"\(\s*\)", "", cleaned).strip()
        cleaned = re.sub(r"\s+([,.،:;!?؟])", r"\1", cleaned)
        return cleaned

    def _strip_service_codes(self, text: str, conversation: Conversation, language: str) -> str:
        services = list(conversation.clinic.services.filter(is_active=True))
        lang = (language or "").lower()
        for service in services:
            display_name = self._format_service_label(service, conversation.clinic, language)
            if service.code:
                text = re.sub(
                    rf"\(\s*{re.escape(service.code)}\s*\)",
                    "",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    rf"(?<!\w){re.escape(service.code)}(?!\w)",
                    display_name,
                    text,
                    flags=re.IGNORECASE,
                )
            if (
                lang.startswith("ar")
                and service.name
                and any(ch.isascii() and ch.isalpha() for ch in service.name)
            ):
                text = re.sub(re.escape(service.name), display_name, text, flags=re.IGNORECASE)
        return text

    def _strip_extra_questions(self, text: str) -> str:
        question_marks = [idx for idx in (text.find("?"), text.find("؟")) if idx != -1]
        if (text.count("?") + text.count("؟")) <= 1 or not question_marks:
            return text
        cut_at = min(question_marks)
        return text[: cut_at + 1].strip()

    def _contains_letters(self, text: str) -> bool:
        return any(ch.isalpha() for ch in text)

    def _handle_booking_flow(
        self,
        *,
        conversation: Conversation,
        session_state: SessionState,
        body: str,
        language: str,
        intent: str,
    ) -> str | None:
        ctx = session_state.context.get("booking_flow") or {}
        slots = dict(ctx.get("slots") or {})
        state = ctx.get("state") or "ASK_REASON"
        turns = int(ctx.get("turns", 0)) + 1
        ctx["turns"] = turns
        max_turns = int(getattr(settings, "BOOKING_MAX_TURNS", 8))
        if turns > max_turns:
            self._clear_booking_flow(session_state)
            if not conversation.handoff_required:
                conversation.handoff_required = True
                conversation.save(update_fields=["handoff_required", "updated_at"])
                try:
                    from apps.accounts.notifications import notify_handoff

                    notify_handoff(conversation)
                except Exception as err:  # pragma: no cover - best effort logging
                    logger.warning("Failed to create handoff notification: %s", err)
            return AR_FALLBACK_MESSAGE if language == "ar" else "I'll connect you with our support team."

        clinic = conversation.clinic
        services = self._get_services_for_language(clinic, language)
        if not services:
            self._clear_booking_flow(session_state)
            return "لا توجد خدمات متاحة حالياً." if language == "ar" else "No services are available right now."

        if not slots.get("reason"):
            reason = self._detect_booking_reason(body, language)
            if reason:
                slots["reason"] = reason
        if not slots.get("service_code"):
            service_code = self._match_service(body, services)
            if service_code:
                slots["service_code"] = service_code
        if not slots.get("date"):
            date_value = self._extract_date_from_text(body, clinic.tz)
            if date_value:
                slots["date"] = date_value.isoformat()
        if not slots.get("time_window"):
            time_window = self._detect_time_window(body)
            if time_window:
                slots["time_window"] = time_window

        if not slots.get("service_code") and len(services) == 1:
            slots["service_code"] = services[0].code

        if state == "SHOW_SLOTS":
            if self._wants_new_time(body):
                slots.pop("date", None)
                slots.pop("time_window", None)
                state = "ASK_DATE"
            else:
                slot_prompt = session_state.context.get("slot_offer_prompt")
                if slot_prompt:
                    self._record_booking_decision(
                        session_state,
                        state=state,
                        slots=slots,
                        missing=[],
                        actions=["show_slots"],
                        prompt=slot_prompt,
                    )
                    return slot_prompt

        missing: list[str] = []
        if not slots.get("reason"):
            missing.append("reason")
        if not slots.get("service_code") and len(services) > 1:
            missing.append("service")
        if not slots.get("date"):
            missing.append("date")
        if not slots.get("time_window"):
            missing.append("time_window")

        prompt = ""
        actions: list[str] = []
        if "reason" in missing:
            state = "ASK_REASON"
            prompt = self._format_reason_prompt(language)
        elif "service" in missing:
            state = "ASK_SERVICE"
            prompt = self._format_service_prompt(language, services)
        elif "date" in missing:
            state = "ASK_DATE"
            prompt = self._format_date_prompt(language)
        elif "time_window" in missing:
            state = "ASK_TIME_WINDOW"
            prompt = self._format_time_window_prompt(language)
        else:
            service = clinic.services.filter(code=slots.get("service_code"), is_active=True).first()
            if not service:
                service = services[0]
                slots["service_code"] = service.code

            date_value = date.fromisoformat(slots["date"])
            start_dt, end_dt = self._window_range(date_value, slots["time_window"], clinic.tz)
            actions.append("get_available_slots")
            available = find_available_slots(clinic, service, start=start_dt, end=end_dt, limit=3)
            if not available:
                slots.pop("date", None)
                slots.pop("time_window", None)
                state = "ASK_DATE"
                prompt = (
                    "لا توجد أوقات متاحة في هذا اليوم. ما اليوم المناسب لك؟"
                    if language == "ar"
                    else "No availability on that day. What date works for you?"
                )
            else:
                prompt = self._build_slot_prompt(available, language, clinic.tz)
                session_state.context["slot_suggestions"] = [
                    {
                        "start": slot.start.isoformat(),
                        "end": slot.end.isoformat(),
                        "tentative": slot.tentative,
                        "source": slot.source,
                    }
                    for slot in available
                ]
                session_state.context["slot_service_code"] = service.code
                session_state.context["slot_offer_prompt"] = prompt
                self.fsm.apply(conversation, "slot_proposed", context={"message": body})
                state = "SHOW_SLOTS"

        if (
            prompt
            and state in {"ASK_REASON", "ASK_SERVICE", "ASK_DATE", "ASK_TIME_WINDOW"}
            and getattr(settings, "LLM_DECISION_JSON_ENABLED", False)
        ):
            try:
                decision = self.llm_router.plan_booking_decision(
                    clinic=clinic,
                    language=language,
                    prompt=body,
                    state=state,
                    slots=slots,
                    missing_slots=missing,
                )
                if decision:
                    min_conf = float(getattr(settings, "LLM_DECISION_CONF_THRESHOLD", 0.5))
                    confidence = float(decision.get("confidence", 0))
                    if (
                        confidence >= min_conf
                        and decision.get("state") == state
                        and decision.get("next_question")
                    ):
                        prompt = decision.get("next_question")
                        decision_missing = decision.get("missing_slots") or []
                        if decision_missing and all(item in missing for item in decision_missing):
                            missing = decision_missing
            except LLMRouterError as exc:
                logger.warning("LLM booking decision skipped: %s", exc)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("LLM booking decision error: %s", exc, exc_info=True)

        if state in {"ASK_REASON", "ASK_SERVICE", "ASK_DATE", "ASK_TIME_WINDOW"}:
            session_state.context.pop("slot_suggestions", None)
            session_state.context.pop("slot_offer_prompt", None)

        ctx["state"] = state
        ctx["slots"] = slots
        session_state.context["booking_flow"] = ctx
        self._record_booking_decision(
            session_state,
            state=state,
            slots=slots,
            missing=missing,
            actions=actions,
            prompt=prompt,
        )
        session_state.save(update_fields=["context", "updated_at"])
        return prompt

    def _handle_action_flow(
        self,
        *,
        conversation: Conversation,
        session_state: SessionState,
        body: str,
        language: str,
        intent: str,
    ) -> tuple[str, str] | None:
        ctx = session_state.context.get("action_flow") or {}
        action_intent = ctx.get("intent") or intent
        if action_intent not in {"cancel", "reschedule"}:
            if ctx:
                self._clear_action_flow(session_state)
                session_state.save(update_fields=["context", "updated_at"])
            return None

        turns = int(ctx.get("turns", 0)) + 1
        ctx["turns"] = turns
        max_turns = int(getattr(settings, "BOOKING_MAX_TURNS", 8))
        if turns > max_turns:
            self._clear_action_flow(session_state)
            if not conversation.handoff_required:
                conversation.handoff_required = True
                conversation.save(update_fields=["handoff_required", "updated_at"])
                try:
                    from apps.accounts.notifications import notify_handoff

                    notify_handoff(conversation)
                except Exception as err:  # pragma: no cover - best effort logging
                    logger.warning("Failed to create handoff notification: %s", err)
            fallback = AR_FALLBACK_MESSAGE if language == "ar" else "I'll connect you with our support team."
            session_state.save(update_fields=["context", "updated_at"])
            return fallback, "handoff"

        if not conversation.patient:
            self._clear_action_flow(session_state)
            session_state.save(update_fields=["context", "updated_at"])
            if language == "ar":
                return "احتاج إلى بياناتك قبل تحديث الموعد. هل يمكنك مشاركة اسمك؟", action_intent
            return "I need your details before updating the appointment. Please share your name.", action_intent

        state = ctx.get("state") or "ASK_APPOINTMENT"
        choices = ctx.get("choices") or []

        if state == "ASK_APPOINTMENT":
            appointments = self._list_upcoming_appointments(conversation, limit=3)
            if not appointments:
                self._clear_action_flow(session_state)
                session_state.save(update_fields=["context", "updated_at"])
                if language == "ar":
                    if action_intent == "cancel":
                        return "لا أجد مواعيد قادمة لإلغائها.", action_intent
                    return "لا أجد مواعيد قادمة لتغييرها.", action_intent
                if action_intent == "cancel":
                    return "I couldn't find any upcoming appointments to cancel.", action_intent
                return "I couldn't find any upcoming appointments to reschedule.", action_intent

            if len(appointments) == 1:
                appointment = appointments[0]
                if action_intent == "cancel":
                    prompt = self._build_confirmation_prompt(
                        tool_name="cancel_appointment",
                        appointment=appointment,
                        new_start_iso=None,
                        language=language,
                        clinic_tz=conversation.clinic.tz,
                    )
                    session_state.context["pending_action"] = {
                        "tool": "cancel_appointment",
                        "args": {"appointment_id": appointment.id},
                        "appointment_id": appointment.id,
                        "stage": "confirm",
                    }
                    self._clear_action_flow(session_state)
                    session_state.save(update_fields=["context", "updated_at"])
                    return prompt, action_intent

                session_state.context["pending_action"] = {
                    "tool": "reschedule_appointment",
                    "args": {"appointment_id": appointment.id},
                    "appointment_id": appointment.id,
                    "stage": "await_time",
                }
                session_state.context["reschedule_appointment_id"] = appointment.id
                self._clear_action_flow(session_state)
                session_state.save(update_fields=["context", "updated_at"])
                if language == "ar":
                    return "ما الوقت الذي تريده بدلًا؟", action_intent
                return "What time would you like instead?", action_intent

            prompt = self._format_appointment_choices(
                appointments=appointments,
                clinic_tz=conversation.clinic.tz,
                language=language,
            )
            ctx["state"] = "AWAIT_CHOICE"
            ctx["intent"] = action_intent
            ctx["choices"] = [appointment.id for appointment in appointments]
            session_state.context["action_flow"] = ctx
            self._record_action_decision(
                session_state,
                intent=action_intent,
                state=ctx["state"],
                slots={"choices": ctx["choices"]},
                missing=["appointment"],
                prompt=prompt,
                actions=["list_appointments"],
            )
            session_state.save(update_fields=["context", "updated_at"])
            return prompt, action_intent

        if state == "AWAIT_CHOICE":
            choice = self._extract_choice_index(body, len(choices))
            if not choice:
                if language == "ar":
                    prompt = "الرجاء اختيار رقم من القائمة (مثال: 1 أو 2)."
                else:
                    prompt = "Please reply with one of the listed numbers (e.g., 1 or 2)."
                self._record_action_decision(
                    session_state,
                    intent=action_intent,
                    state=state,
                    slots={"choices": choices},
                    missing=["appointment"],
                    prompt=prompt,
                    actions=["await_choice"],
                )
                session_state.context["action_flow"] = ctx
                session_state.save(update_fields=["context", "updated_at"])
                return prompt, action_intent

            appointment_id = choices[choice - 1]
            appointment = self._resolve_upcoming_appointment(conversation, appointment_id)
            if not appointment:
                appointments = self._list_upcoming_appointments(conversation, limit=3)
                if not appointments:
                    self._clear_action_flow(session_state)
                    session_state.save(update_fields=["context", "updated_at"])
                    if language == "ar":
                        if action_intent == "cancel":
                            return "لا أجد مواعيد قادمة لإلغائها.", action_intent
                        return "لا أجد مواعيد قادمة لتغييرها.", action_intent
                    if action_intent == "cancel":
                        return "I couldn't find any upcoming appointments to cancel.", action_intent
                    return "I couldn't find any upcoming appointments to reschedule.", action_intent

                prompt = self._format_appointment_choices(
                    appointments=appointments,
                    clinic_tz=conversation.clinic.tz,
                    language=language,
                )
                ctx["state"] = "AWAIT_CHOICE"
                ctx["intent"] = action_intent
                ctx["choices"] = [appointment.id for appointment in appointments]
                session_state.context["action_flow"] = ctx
                self._record_action_decision(
                    session_state,
                    intent=action_intent,
                    state=ctx["state"],
                    slots={"choices": ctx["choices"]},
                    missing=["appointment"],
                    prompt=prompt,
                    actions=["list_appointments"],
                )
                session_state.save(update_fields=["context", "updated_at"])
                return prompt, action_intent

            if action_intent == "cancel":
                prompt = self._build_confirmation_prompt(
                    tool_name="cancel_appointment",
                    appointment=appointment,
                    new_start_iso=None,
                    language=language,
                    clinic_tz=conversation.clinic.tz,
                )
                session_state.context["pending_action"] = {
                    "tool": "cancel_appointment",
                    "args": {"appointment_id": appointment.id},
                    "appointment_id": appointment.id,
                    "stage": "confirm",
                }
                self._clear_action_flow(session_state)
                session_state.save(update_fields=["context", "updated_at"])
                return prompt, action_intent

            session_state.context["pending_action"] = {
                "tool": "reschedule_appointment",
                "args": {"appointment_id": appointment.id},
                "appointment_id": appointment.id,
                "stage": "await_time",
            }
            session_state.context["reschedule_appointment_id"] = appointment.id
            self._clear_action_flow(session_state)
            session_state.save(update_fields=["context", "updated_at"])
            if language == "ar":
                return "ما الوقت الذي تريده بدلًا؟", action_intent
            return "What time would you like instead?", action_intent

        return None

    def _record_booking_decision(
        self,
        session_state: SessionState,
        *,
        state: str,
        slots: dict,
        missing: list[str],
        actions: list[str],
        prompt: str,
    ) -> None:
        session_state.context["decision"] = {
            "intent": "book",
            "state": state,
            "slots": slots,
            "missing_slots": missing,
            "next_question": prompt,
            "actions": actions,
        }

    def _record_action_decision(
        self,
        session_state: SessionState,
        *,
        intent: str,
        state: str,
        slots: dict,
        missing: list[str],
        prompt: str,
        actions: list[str],
    ) -> None:
        session_state.context["decision"] = {
            "intent": intent,
            "state": state,
            "slots": slots,
            "missing_slots": missing,
            "next_question": prompt,
            "actions": actions,
        }

    def _clear_booking_flow(self, session_state: SessionState) -> None:
        session_state.context.pop("booking_flow", None)
        session_state.context.pop("decision", None)

    def _clear_action_flow(self, session_state: SessionState) -> None:
        session_state.context.pop("action_flow", None)
        if session_state.context.get("decision", {}).get("intent") in {"cancel", "reschedule"}:
            session_state.context.pop("decision", None)

    def _detect_booking_reason(self, text: str, language: str) -> str | None:
        lowered = text.lower()
        reason_map = {
            "referral": {"تحويل", "محول", "referral"},
            "cosmetic": {"تجميلي", "تجميل", "ابتسامة", "تبييض", "تقويم", "زراعة", "cosmetic", "whitening", "ortho"},
            "pain": {"ألم", "وجع", "مؤلم", "ألم الأسنان", "pain", "toothache"},
            "checkup": {"فحص", "كشف", "استشارة", "تشخيص", "متابعة", "checkup", "exam", "consult"},
            "other": {"أخرى", "اخرى", "غير ذلك", "other"},
        }
        for code, tokens in reason_map.items():
            if any(token in lowered for token in tokens):
                return code
        return None

    def _format_reason_prompt(self, language: str) -> str:
        if language == "ar":
            return "ما سبب الزيارة؟ (تحويل/تجميلي/ألم/فحص/أخرى)"
        return "What is the visit reason? (referral/cosmetic/pain/checkup/other)"

    def _format_service_prompt(self, language: str, services: list) -> str:
        names = ", ".join([svc.name for svc in services[:4] if svc.name])
        if language == "ar":
            if names and any(ch.isascii() and ch.isalpha() for ch in names):
                return "?? ?????? ?????????"
            if names:
                return f"?? ?????? ????????? (????: {names})"
            return "?? ?????? ?????????"
        if names:
            return f"Which service would you like? (e.g., {names})"
        return "Which service would you like?"


    def _get_services_for_language(self, clinic: Clinic, language: str) -> list:
        services = list(clinic.services.filter(is_active=True))
        if not services:
            return []

        lang = (language or "").lower()
        preferred_langs = {lang}
        if lang.startswith("en"):
            preferred_langs = {"en", "en_us"}
        elif lang.startswith("ar"):
            preferred_langs = {"ar"}

        preferred = [svc for svc in services if getattr(svc, "language", "") in preferred_langs]
        by_code: dict[str, object] = {}
        for svc in preferred:
            by_code.setdefault(svc.code, svc)
        for svc in services:
            by_code.setdefault(svc.code, svc)
        return sorted(by_code.values(), key=lambda svc: (svc.name or ""))

    def _format_date_prompt(self, language: str) -> str:
        if language == "ar":
            return "ما اليوم المناسب لك؟"
        return "Which date works for you?"

    def _format_time_window_prompt(self, language: str) -> str:
        if language == "ar":
            return "أي فترة تناسبك؟ (صباح/ظهر/مساء/أي وقت)"
        return "Which time window works for you? (morning/afternoon/evening/any)"

    def _wants_new_time(self, text: str) -> bool:
        lowered = text.lower()
        cues = {"وقت آخر", "موعد آخر", "تغيير", "غير مناسب", "another time", "change"}
        return any(cue in lowered for cue in cues)

    def _asks_for_slots(self, text: str) -> bool:
        lowered = text.lower()
        cues = {"المواعيد", "الأوقات", "المتاح", "available times", "available slots"}
        return any(cue in lowered for cue in cues)

    def _detect_time_window(self, text: str) -> str | None:
        lowered = text.lower()
        if any(token in lowered for token in {"أي وقت", "بدون تفضيل", "any time", "anytime"}):
            return "any"
        if any(token in lowered for token in {"صباح", "morning"}):
            return "morning"
        if any(token in lowered for token in {"ظهر", "عصر", "afternoon", "noon"}):
            return "afternoon"
        if any(token in lowered for token in {"مساء", "ليل", "evening", "night"}):
            return "evening"
        return None

    def _match_service(self, text: str, services: list) -> str | None:
        lowered = text.lower()
        for service in services:
            if service.name and service.name.lower() in lowered:
                return service.code
        for service in services:
            for token in (service.name or "").lower().split():
                if token and token in lowered:
                    return service.code
        return None

    def _normalize_digits(self, text: str) -> str:
        return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))

    def _extract_date_from_text(self, text: str, clinic_tz: str) -> date | None:
        if not text:
            return None
        lowered = self._normalize_digits(text.lower())
        tz = ZoneInfo(clinic_tz or "UTC")
        today = timezone.now().astimezone(tz).date()
        if any(token in lowered for token in {"today", "اليوم"}):
            return today
        if any(token in lowered for token in {"tomorrow", "بكرا", "غدا"}):
            return today + timedelta(days=1)
        if any(token in lowered for token in {"after tomorrow", "بعد بكرة", "بعد غد"}):
            return today + timedelta(days=2)

        match = re.search(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b", lowered)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None

        match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = match.group(3)
            if year:
                year_int = int(year)
                if year_int < 100:
                    year_int += 2000
            else:
                year_int = today.year
            try:
                candidate = date(year_int, month, day)
            except ValueError:
                return None
            if candidate < today:
                try:
                    candidate = date(year_int + 1, month, day)
                except ValueError:
                    return None
            return candidate
        return None

    def _window_range(self, date_value: date, time_window: str, clinic_tz: str) -> tuple[datetime, datetime]:
        tz = ZoneInfo(clinic_tz or "UTC")
        window = time_window or "any"
        if window == "morning":
            start_t, end_t = time(9, 0), time(12, 0)
        elif window == "afternoon":
            start_t, end_t = time(12, 0), time(17, 0)
        elif window == "evening":
            start_t, end_t = time(17, 0), time(21, 0)
        else:
            start_t, end_t = time.min, time(23, 59)
        start_dt = datetime.combine(date_value, start_t, tzinfo=tz)
        end_dt = datetime.combine(date_value, end_t, tzinfo=tz)
        return start_dt, end_dt

    def _handle_terminal_intent(self, conversation: Conversation, intent: str, language: str) -> str:
        action = intent
        try:
            return self.llm_router.compose_action_reply(
                language=language,
                action=action,
                clinic_name=conversation.clinic.name,
                conversation_id=conversation.id,
            )
        except LLMRouterError as exc:
            logger.warning("LLM action reply skipped: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("LLM action reply error: %s", exc, exc_info=True)

        if intent == "confirm":
            return AR_CONFIRM_MESSAGE if language == "ar" else "Your appointment is confirmed. See you soon!"
        if intent == "cancel":
            return AR_CANCEL_MESSAGE if language == "ar" else "Your appointment has been cancelled as requested."
        if intent == "reschedule":
            return AR_RESCHEDULE_MESSAGE if language == "ar" else "Let's pick a new slot for you."
        return ""

    def _build_slot_prompt(self, slots: list[SuggestedSlot], language: str, clinic_timezone: str) -> str:
        tz = ZoneInfo(clinic_timezone or "UTC")
        formatted: list[str] = []
        for slot in slots[:2]:
            local_start = slot.start.astimezone(tz)
            label = self._format_datetime_label(local_start, language)
            if slot.tentative:
                label += AR_TENTATIVE_NOTE if language == "ar" else " (tentative hold)"
            formatted.append(label)
        if not formatted:
            return "I will follow up with available times."
        if language == "ar":
            if len(formatted) == 1:
                return AR_SINGLE_SLOT_PROMPT.format(slot=formatted[0])
            return AR_DOUBLE_SLOT_PROMPT.format(slot1=formatted[0], slot2=formatted[1])
        if len(formatted) == 1:
            return f"I can offer {formatted[0]}. Does that work?"
        return f"I can offer {formatted[0]} or {formatted[1]}. Which works best for you?"

    def _select_slot_from_reply(
        self,
        reply: str,
        slot_suggestions: list[dict],
        clinic_timezone: str,
    ) -> dict | None:
        if not slot_suggestions:
            return None

        normalized = normalize_text(reply)
        any_time_tokens = (
            "any time",
            "anytime",
            "whenever",
            "no preference",
            "first available",
            "earliest",
            "soonest",
            "اي وقت",
            "أي وقت",
            "اي وقت مناسب",
            "أي وقت مناسب",
            "المناسب",
            "اي موعد",
            "أي موعد",
            "اول وقت",
            "أول وقت",
            "اقرب وقت",
            "أقرب وقت",
            "اسرع وقت",
            "أسرع وقت",
        )
        if any(token in normalized for token in any_time_tokens):
            return slot_suggestions[0]
        ordinal_map = {
            "first": 1,
            "1st": 1,
            "one": 1,
            "second": 2,
            "2nd": 2,
            "two": 2,
            "third": 3,
            "3rd": 3,
            "three": 3,
            "الأول": 1,
            "الاول": 1,
            "اول": 1,
            "الثاني": 2,
            "الثانى": 2,
            "الثالث": 3,
            "الرابع": 4,
            "الخامس": 5,
        }
        for token, idx in ordinal_map.items():
            if token.isascii():
                matched = re.search(rf"\b{re.escape(token)}\b", normalized)
            else:
                matched = token in normalized
            if matched and idx <= len(slot_suggestions):
                return slot_suggestions[idx - 1]
        time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", normalized)
        meridiem_match = re.search(r"\b([1-9]|1[0-2])\s*(am|pm|ص|م)\b", normalized)
        target_minutes = None
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            target_minutes = hour * 60 + minute
        elif meridiem_match:
            hour = int(meridiem_match.group(1))
            minute = 0
            meridiem = meridiem_match.group(2).lower()
            if meridiem in {"pm", "م"} and hour != 12:
                hour += 12
            if meridiem in {"am", "ص"} and hour == 12:
                hour = 0
            target_minutes = hour * 60 + minute
        if target_minutes is not None:
            tz = ZoneInfo(clinic_timezone or "UTC")
            closest_slot = None
            closest_delta = None
            for slot in slot_suggestions:
                try:
                    start_dt = datetime.fromisoformat(slot.get("start", ""))
                except (TypeError, ValueError):
                    continue
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=tz)
                local_start = start_dt.astimezone(tz)
                slot_minutes = local_start.hour * 60 + local_start.minute
                delta = abs(slot_minutes - target_minutes)
                if closest_delta is None or delta < closest_delta:
                    closest_delta = delta
                    closest_slot = slot
            if closest_slot:
                return closest_slot
        for idx, slot in enumerate(slot_suggestions):
            if re.search(rf"\b{idx + 1}\b", normalized):
                return slot

        tz = ZoneInfo(clinic_timezone or "UTC")
        for slot in slot_suggestions:
            try:
                start_dt = datetime.fromisoformat(slot.get("start", ""))
            except (TypeError, ValueError):
                continue
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=tz)
            local_start = start_dt.astimezone(tz)
            candidates = {
                local_start.strftime("%H:%M"),
                local_start.strftime("%I:%M").lstrip("0"),
                local_start.strftime("%I:%M %p").lower(),
            }
            if any(candidate and candidate in normalized for candidate in candidates):
                return slot
        return None

    def _is_greeting(self, normalized: str) -> bool:
        if not normalized:
            return False
        greetings = {
            "hi",
            "hello",
            "hey",
            "good morning",
            "good evening",
            "good afternoon",
            "مرحبا",
            "اهلا",
            "أهلا",
            "هلا",
            "السلام عليكم",
            "السلام",
            "سلام",
            "صباح الخير",
            "مساء الخير",
        }
        return any(greet in normalized for greet in greetings)

    def _is_gratitude(self, normalized: str) -> bool:
        if not normalized:
            return False
        tokens = {
            "thanks",
            "thank you",
            "appreciate",
            "شكرا",
            "شكراً",
            "شكرًا",
            "شكرا جزيلا",
            "شكرا جزيلاً",
            "شكرًا جزيلاً",
            "مشكور",
            "مشكورين",
            "يعطيك العافية",
            "الله يعطيك العافية",
            "جزاك الله خير",
            "جزاك الله خيرا",
            "تسلم",
            "يسلمو",
            "شكرا",
            "شكر",
            "مشكور",
            "يعطيك العافية",
            "جزاك الله خير",
        }
        return any(token in normalized for token in tokens)

    def _is_booking_complaint(self, normalized: str) -> bool:
        if not normalized:
            return False
        if any(token in normalized for token in {"لماذا", "ليش"}):
            if any(token in normalized for token in {"تحجز", "حجز", "موعد"}):
                return True
        return False

    def _handle_pending_action(
        self,
        *,
        conversation: Conversation,
        session_state: SessionState,
        body: str,
        language: str,
        pending: dict,
    ) -> tuple[str, str] | None:
        stage = pending.get("stage", "confirm")
        tool_name = pending.get("tool")
        args = pending.get("args") or {}
        normalized = normalize_text(body)
        raw = body.strip().lower()

        if stage == "confirm":
            if self._is_negative_reply(normalized, raw):
                session_state.context.pop("pending_action", None)
                session_state.save(update_fields=["context", "updated_at"])
                reply = "Okay, I won't make that change. How else can I help you?"
                if language == "ar":
                    reply = "حسنًا، لن أقوم بالتغيير. كيف يمكنني مساعدتك؟"
                return reply, "clarify"

            if not self._is_affirmative_reply(normalized, raw):
                reply = "Please reply with yes or no to confirm."
                if language == "ar":
                    reply = "يرجى الرد بنعم أو لا للتأكيد."
                return reply, "clarify"

            tool_reply, tool_slots, tool_meta = self.llm_router.execute_tool_call(
                clinic=conversation.clinic,
                language=language,
                prompt=body,
                conversation_id=conversation.id,
                tool_name=tool_name,
                args=args,
                conversation=conversation,
            )
            session_state.context.pop("pending_action", None)

            if tool_meta and tool_meta.get("action") == "reschedule" and tool_slots:
                session_state.context["slot_suggestions"] = [
                    {
                        "start": slot.start.isoformat(),
                        "end": slot.end.isoformat(),
                        "tentative": slot.tentative,
                        "source": slot.source,
                    }
                    for slot in tool_slots
                ]
                session_state.context["slot_offer_prompt"] = tool_reply
                if tool_meta.get("service_code"):
                    session_state.context["slot_service_code"] = tool_meta.get("service_code")
                if tool_meta.get("appointment_id"):
                    session_state.context["reschedule_appointment_id"] = tool_meta.get("appointment_id")
                session_state.save(update_fields=["context", "updated_at"])
                return tool_reply, "reschedule"

            if tool_name == "reschedule_appointment" and not tool_slots and tool_meta is None:
                appointment_id = pending.get("appointment_id") or args.get("appointment_id")
                if appointment_id:
                    session_state.context["pending_action"] = {
                        "tool": tool_name,
                        "args": {"appointment_id": appointment_id},
                        "appointment_id": appointment_id,
                        "stage": "await_time",
                    }
                    session_state.save(update_fields=["context", "updated_at"])
                return tool_reply, "reschedule"

            session_state.save(update_fields=["context", "updated_at"])
            return tool_reply or "", "confirm"

        if stage == "await_time":
            appointment_id = pending.get("appointment_id") or args.get("appointment_id")
            if not appointment_id:
                session_state.context.pop("pending_action", None)
                session_state.save(update_fields=["context", "updated_at"])
                reply = "Please share the date and time you prefer."
                if language == "ar":
                    reply = "يرجى ذكر التاريخ والوقت المناسب."
                return reply, "reschedule"

            tool_reply, tool_slots, tool_meta = self.llm_router.execute_tool_call(
                clinic=conversation.clinic,
                language=language,
                prompt=body,
                conversation_id=conversation.id,
                tool_name="reschedule_appointment",
                args={"appointment_id": appointment_id},
                conversation=conversation,
            )
            if tool_meta and tool_meta.get("action") == "reschedule" and tool_slots:
                session_state.context["slot_suggestions"] = [
                    {
                        "start": slot.start.isoformat(),
                        "end": slot.end.isoformat(),
                        "tentative": slot.tentative,
                        "source": slot.source,
                    }
                    for slot in tool_slots
                ]
                session_state.context["slot_offer_prompt"] = tool_reply
                if tool_meta.get("service_code"):
                    session_state.context["slot_service_code"] = tool_meta.get("service_code")
                session_state.context["reschedule_appointment_id"] = appointment_id
                session_state.context.pop("pending_action", None)
                session_state.save(update_fields=["context", "updated_at"])
                return tool_reply, "reschedule"

            if tool_meta and tool_meta.get("action") == "rescheduled":
                session_state.context.pop("pending_action", None)
                session_state.save(update_fields=["context", "updated_at"])
                return tool_reply, "reschedule"

            session_state.context["pending_action"] = pending
            session_state.save(update_fields=["context", "updated_at"])
            return tool_reply or "", "reschedule"

        return None

    def _build_confirmation_prompt(
        self,
        *,
        tool_name: str,
        appointment,
        new_start_iso: str | None,
        language: str,
        clinic_tz: str,
    ) -> str:
        time_label, service_label = self._format_appointment_label(
            appointment, clinic_tz, language
        )
        if tool_name == "cancel_appointment":
            if language == "ar":
                return f"?? ???? ????? ????? ?????? {time_label} ????? {service_label}? ??? ??? ??????? ?? ?? ???????."
            return f"Cancel your appointment on {time_label} for {service_label}? Reply YES to confirm or NO to keep it."

        new_label = ""
        if new_start_iso:
            try:
                dt = datetime.fromisoformat(str(new_start_iso))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo(clinic_tz or "UTC"))
                new_label = self._format_datetime_label(
                    dt.astimezone(ZoneInfo(clinic_tz or "UTC")), language
                )
            except (TypeError, ValueError):
                new_label = ""
        if language == "ar":
            if new_label:
                return f"?? ???? ????? ????? ?? {time_label} ??? {new_label}? ??? ??? ??????? ?? ?? ???????."
            return f"?? ???? ????? ????? ?????? {time_label}? ??? ??? ??????? ?? ?? ???????."
        if new_label:
            return f"Reschedule your appointment from {time_label} to {new_label}? Reply YES to confirm or NO to keep it."
        return f"Reschedule your appointment on {time_label}? Reply YES to confirm or NO to keep it."

    def _format_datetime_label(self, dt: datetime, language: str) -> str:
        if language != "ar":
            return dt.strftime("%A %d %b %I:%M %p")

        day_names = [
            "الاثنين",
            "الثلاثاء",
            "الأربعاء",
            "الخميس",
            "الجمعة",
            "السبت",
            "الأحد",
        ]
        month_names = [
            "يناير",
            "فبراير",
            "مارس",
            "أبريل",
            "مايو",
            "يونيو",
            "يوليو",
            "أغسطس",
            "سبتمبر",
            "أكتوبر",
            "نوفمبر",
            "ديسمبر",
        ]
        day_name = day_names[dt.weekday()]
        month_name = month_names[dt.month - 1]
        hour = dt.hour
        period = "صباحًا" if hour < 12 else "مساءً"
        hour12 = hour % 12
        if hour12 == 0:
            hour12 = 12
        return f"{day_name} {dt.day} {month_name} {hour12}:{dt.minute:02d} {period}"

    def _format_service_label(self, service, clinic: Clinic | None, language: str) -> str:
        if not service:
            return "??????" if language == "ar" else "service"
        if language == "ar" and clinic:
            if getattr(service, "language", None) != "ar":
                translated = clinic.services.filter(code=service.code, language="ar").first()
                if translated and translated.name:
                    return translated.name
        label = service.name or ""
        if language == "ar" and any(ch.isascii() and ch.isalpha() for ch in label):
            return "??????"
        return label or ("??????" if language == "ar" else "service")

    def _format_appointment_label(self, appointment, clinic_tz: str, language: str) -> tuple[str, str]:
        tz = ZoneInfo(clinic_tz or "UTC")
        start_label = "unknown time"
        if getattr(appointment, "start_at", None):
            start_label = self._format_datetime_label(
                appointment.start_at.astimezone(tz), language
            )
        service_label = self._format_service_label(
            appointment.service if getattr(appointment, "service", None) else None,
            appointment.clinic if getattr(appointment, "clinic", None) else None,
            language,
        )
        return start_label, service_label

    def _format_appointment_choices(self, *, appointments: list, clinic_tz: str, language: str) -> str:
        tz = ZoneInfo(clinic_tz or "UTC")
        lines: list[str] = []
        for idx, appointment in enumerate(appointments, start=1):
            start_label = "unknown time"
            if getattr(appointment, "start_at", None):
                start_label = self._format_datetime_label(
                    appointment.start_at.astimezone(tz), language
                )
            service_label = self._format_service_label(
                appointment.service if getattr(appointment, "service", None) else None,
                appointment.clinic if getattr(appointment, "clinic", None) else None,
                language,
            )
            if language == "ar":
                lines.append(f"{idx}) {service_label} - {start_label}")
            else:
                lines.append(f"{idx}) {start_label} ? {service_label}")

        if language == "ar":
            intro = "???? ???? ?? ???? ????. ???? ??? ??????:"
            outro = "???? ????? ?????? ??? (????: 1 ?? 2)."
        else:
            intro = "You have multiple upcoming appointments. Please choose one:"
            outro = "Reply with a single number (e.g., 1 or 2)."

        return "\n".join([intro, *lines, outro])
    def _extract_choice_index(self, text: str, max_value: int) -> int | None:
        if not text or max_value < 1:
            return None
        normalized = self._normalize_digits(text)
        match = re.search(r"\b(\d{1,2})\b", normalized)
        if not match:
            return None
        try:
            value = int(match.group(1))
        except ValueError:
            return None
        if 1 <= value <= max_value:
            return value
        return None

    def _list_upcoming_appointments(self, conversation: Conversation, limit: int = 3):
        from apps.appointments.models import Appointment, AppointmentStatus

        now = timezone.now()
        return list(
            Appointment.objects.filter(
                clinic=conversation.clinic,
                patient=conversation.patient,
                status__in=[
                    AppointmentStatus.PENDING,
                    AppointmentStatus.BOOKED,
                    AppointmentStatus.CONFIRMED,
                ],
                slot__lower__gte=now,
            )
            .order_by("slot__lower")[:limit]
        )

    def _resolve_upcoming_appointment(self, conversation: Conversation, appointment_id: int):
        from apps.appointments.models import Appointment, AppointmentStatus

        return Appointment.objects.filter(
            id=appointment_id,
            clinic=conversation.clinic,
            patient=conversation.patient,
            status__in=[
                AppointmentStatus.PENDING,
                AppointmentStatus.BOOKED,
                AppointmentStatus.CONFIRMED,
            ],
        ).order_by("slot__lower").first()

    def _is_affirmative_reply(self, normalized: str, raw: str) -> bool:
        tokens = {"yes", "y", "ok", "okay", "confirm", "sure", "agree"}
        if any(token in normalized for token in tokens):
            return True
        arabic_tokens = {"???", "????", "????", "?????", "????", "?????", "????", "??"}
        return any(token in raw for token in arabic_tokens)

    def _is_negative_reply(self, normalized: str, raw: str) -> bool:
        tokens = {"no", "nah", "nope", "cancel", "stop", "don't"}
        if any(token in normalized for token in tokens):
            return True
        arabic_tokens = {"??", "??", "??", "??? ?????", "?? ????", "??????", "???", "?????", "?????"}
        return any(token in raw for token in arabic_tokens)
