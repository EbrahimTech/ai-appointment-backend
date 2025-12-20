"""Coordinates dialog FSM, intent detection, and LLM handoffs."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Tuple

from django.conf import settings
from django.utils import timezone
from zoneinfo import ZoneInfo

from apps.appointments.scheduling import SuggestedSlot, suggest_slots
from apps.accounts.views import book_appointment
from apps.channels.services import enqueue_whatsapp_hsm, enqueue_whatsapp_session_message
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
        normalized = normalize_text(body)
        intent = detect_intent(normalized)
        # LLM intent fallback (structured) to better understand Arabic/free-form requests
        if intent == "clarify" and getattr(settings, "LLM_INTENT_ENABLED", True):
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

        # Track repeated unproductive intents to auto-handoff
        productive_intents = {"book", "confirm", "cancel", "reschedule"}
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
            ConversationMessage.objects.create(
                conversation=conversation,
                direction="outbound",
                language=language,
                body=response_text,
                intent="handoff",
                metadata={"auto_reply": True, "reason": "repeat_intent_threshold"},
            )
            enqueue_whatsapp_session_message(
                clinic_id=conversation.clinic_id,
                conversation=conversation,
                language=language,
                message_body=response_text,
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
                        if tool_slots:
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
            if intent == "confirm" and getattr(settings, "LLM_TOOL_BOOKING_ENABLED", False):
                slot_suggestions = session_state.context.get("slot_suggestions") or []
                service_code = session_state.context.get("slot_service_code")
                selected = self._select_slot_from_reply(body, slot_suggestions, conversation.clinic.tz)
                if selected and service_code and conversation.patient:
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
                            session_state.save(update_fields=["context", "updated_at"])
                            time_label = start_local.astimezone(
                                ZoneInfo(conversation.clinic.tz or "UTC")
                            ).strftime("%A %d %b %I:%M %p")
                            if language == "ar":
                                response_text = f"تم حجز موعدك بنجاح في {time_label}."
                            else:
                                response_text = f"Your appointment is booked for {time_label}."
                            queue_session = False
                        else:
                            error_text = "That slot is no longer available. Please choose another time."
                            if language == "ar":
                                error_text = "هذا الموعد لم يعد متاحًا. يرجى اختيار وقت آخر."
                            response_text = error_text
                            queue_session = True
                    else:
                        response_text = self._handle_terminal_intent(conversation, intent, language)
                        queue_session = False
                elif slot_suggestions:
                    response_text = (
                        "Please choose one of the suggested times (e.g., 1 or 2)."
                        if language != "ar"
                        else "يرجى اختيار أحد الأوقات المقترحة (مثال: 1 أو 2)."
                    )
                    queue_session = True
                else:
                    response_text = self._handle_terminal_intent(conversation, intent, language)
                    queue_session = False
            else:
                response_text = self._handle_terminal_intent(conversation, intent, language)
                queue_session = False
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
                    fallback_template = getattr(settings, "LLM_FALLBACK_TEMPLATE_NAME", "session_clarify")
                    enqueue_whatsapp_hsm(
                        clinic_id=conversation.clinic_id,
                        conversation=conversation,
                        template_name=fallback_template,
                        language=language,
                        variables={"name": conversation.patient.full_name if conversation.patient else AR_GUEST_FALLBACK},
                        delay_seconds=2,
                    )
                    response_text = (
                        AR_FALLBACK_MESSAGE if language == "ar" else "I'll connect you with our support team."
                    )
                    queue_session = False
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
            ConversationMessage.objects.create(
                conversation=conversation,
                direction="outbound",
                language=language,
                body=response_text,
                intent="reply",
                metadata={"auto_reply": True},
            )
            if queue_session:
                enqueue_whatsapp_session_message(
                    clinic_id=conversation.clinic_id,
                    conversation=conversation,
                    language=language,
                    message_body=response_text,
                    # Ensure each inbound message yields its own outbound send, even if text matches
                    idempotency_key=f"{conversation.id}:{inbound_message.id}",
                )
        return response_text, intent

    def _handle_terminal_intent(self, conversation: Conversation, intent: str, language: str) -> str:
        if intent == "confirm":
            try:
                enqueue_whatsapp_hsm(
                    clinic_id=conversation.clinic_id,
                    conversation=conversation,
                    template_name="appointment_confirmed",
                    language=language,
                    variables={"name": conversation.patient.full_name if conversation.patient else AR_GUEST_FALLBACK},
                    delay_seconds=2,
                )
            except Exception as exc:  # pragma: no cover - logging only
                logger.warning("Failed to queue confirmation template: %s", exc)
            return (
                AR_CONFIRM_MESSAGE if language == "ar" else "Your appointment is confirmed. See you soon!"
            )
        if intent == "cancel":
            return (
                AR_CANCEL_MESSAGE if language == "ar" else "Your appointment has been cancelled as requested."
            )
        if intent == "reschedule":
            return (
                AR_RESCHEDULE_MESSAGE if language == "ar" else "Let's pick a new slot for you."
            )
        return ""

    def _build_slot_prompt(self, slots: list[SuggestedSlot], language: str, clinic_timezone: str) -> str:
        tz = ZoneInfo(clinic_timezone or "UTC")
        formatted: list[str] = []
        for slot in slots[:2]:
            local_start = slot.start.astimezone(tz)
            label = local_start.strftime("%A %d %b %I:%M %p")
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
