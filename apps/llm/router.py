"""Router for DeepSeek-backed grounded responses."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, List, Tuple
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.clinics.models import Clinic, LanguageChoices
from apps.conversations.models import Conversation, SessionState
from apps.kb.models import KnowledgeChunk, KnowledgeIndex
from apps.llm.models import LLMProvider, LLMRequestLog, RetrievalLog
from apps.appointments.models import Appointment, AppointmentStatus
from apps.appointments.scheduling import SuggestedSlot, find_available_slots, suggest_slots

logger = logging.getLogger(__name__)


class LLMRouterError(RuntimeError):
    """Raised for recoverable router errors."""


def create_embedding(text: str, api_key: str = None, api_base: str = None) -> List[float] | None:
    """
    Create embedding vector for text using DeepSeek API.

    Returns None if embedding fails.
    """
    if not api_key:
        api_key = settings.DEEPSEEK_API_KEY
    if not api_base:
        api_base = settings.DEEPSEEK_API_BASE.rstrip("/")

    if not api_key:
        logger.error("DeepSeek API key not configured for embeddings")
        return None

    try:
        response = requests.post(
            f"{api_base}/v1/embeddings",
            json={
                "model": "text-embedding-3-small",
                "input": text[:8000],  # Limit input length
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.error(f"Embedding API error {response.status_code}: {response.text}")
            return None

        payload = response.json()
        embedding = payload["data"][0]["embedding"]
        return embedding

    except Exception as e:
        logger.error(f"Failed to create embedding: {e}")
        return None


class LLMRouter:
    """Resolve gray intents via DeepSeek constrained by knowledge base chunks."""

    def __init__(self) -> None:
        self.api_key = settings.DEEPSEEK_API_KEY
        self.api_base = settings.DEEPSEEK_API_BASE.rstrip("/")
        self.model = getattr(settings, "LLM_DEFAULT_MODEL", "deepseek-chat")
        self.top_k = getattr(settings, "RAG_TOP_K", 4)
        self.max_tokens = getattr(settings, "RAG_MAX_TOKENS", 1000)
        self.chars_per_token = getattr(settings, "RAG_CHARS_PER_TOKEN", 4)
        self.max_latency_ms = getattr(settings, "LLM_MAX_LATENCY_MS", 12000)
        self.daily_budget = Decimal(str(getattr(settings, "LLM_COST_BUDGET_PER_DAY", 0)))
        self.cost_per_request = Decimal(str(getattr(settings, "LLM_COST_PER_REQUEST", 0.002)))
        self.fallback_template_name = getattr(settings, "LLM_FALLBACK_TEMPLATE_NAME", "session_clarify")

    def answer(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
        conversation_id: int | None = None,
    ) -> str:
        if not self.api_key:
            raise LLMRouterError("DeepSeek API key not configured.")

        conversation: Conversation | None = None
        session_state: SessionState | None = None
        if conversation_id:
            conversation = Conversation.objects.filter(pk=conversation_id).first()
            if conversation:
                session_state, _ = SessionState.objects.get_or_create(conversation=conversation)

        if not self._budget_available():
            self._mark_economy_mode(session_state, conversation)
            raise LLMRouterError("llm_budget_exhausted")

        chunks = self._retrieve_chunks(clinic, language)
        context_text, grounded_chunks = self._build_context(chunks)
        # add live clinic snapshot (services/pricing/slots)
        snapshot = self._clinic_snapshot(clinic)
        if snapshot:
            context_text = snapshot + "\n\n" + context_text

        if not grounded_chunks and not snapshot:
            self._register_not_understood(session_state, conversation)
            raise LLMRouterError("rag_context_missing")

        guardrails = self._system_prompt()
        messages = [
            {"role": "system", "content": guardrails},
            {
                "role": "user",
                "content": (
                    f"Context:\n{context_text}\n\nQuestion:\n{prompt}\n\n"
                    f"Answer in {language.upper()}"
                ),
            },
        ]

        start = timezone.now()
        try:
            response = requests.post(
                f"{self.api_base}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=getattr(settings, "LLM_TIMEOUT_SECONDS", 15),
            )
        except requests.Timeout as exc:  # pragma: no cover - network path
            self._register_not_understood(session_state, conversation)
            raise LLMRouterError("llm_timeout") from exc

        latency_ms = int((timezone.now() - start).total_seconds() * 1000)
        if latency_ms > self.max_latency_ms:
            self._register_not_understood(session_state, conversation)
            raise LLMRouterError("llm_latency_exceeded")

        if response.status_code >= 400:
            logger.error("DeepSeek error %s: %s", response.status_code, response.text)
            self._register_not_understood(session_state, conversation)
            raise LLMRouterError("llm_provider_error")

        payload = response.json()
        content = payload["choices"][0]["message"]["content"].strip()

        llm_log = LLMRequestLog.objects.create(
            provider=LLMProvider.DEEPSEEK,
            model=self.model,
            prompt=prompt,
            response=content,
            request_metadata={"messages": messages},
            response_metadata=payload,
            latency_ms=latency_ms,
            success=True,
            cost_estimate=self.cost_per_request,
        )
        for chunk in grounded_chunks:
            RetrievalLog.objects.create(
                llm_log=llm_log,
                chunk=chunk,
                relevance_score=chunk.score,
            )

        if "I don't have that information" in content:
            self._register_not_understood(session_state, conversation)

        return content

    def answer_with_tools(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
        conversation_id: int | None = None,
    ) -> tuple[str | None, list[SuggestedSlot], dict | None]:
        """Attempt a tool call for availability queries, else return a reply."""
        if not self.api_key:
            raise LLMRouterError("DeepSeek API key not configured.")

        conversation: Conversation | None = None
        session_state: SessionState | None = None
        if conversation_id:
            conversation = Conversation.objects.filter(pk=conversation_id).first()
            if conversation:
                session_state, _ = SessionState.objects.get_or_create(conversation=conversation)

        if not self._budget_available():
            self._mark_economy_mode(session_state, conversation)
            raise LLMRouterError("llm_budget_exhausted")

        plan = self.plan_tool_call(
            clinic=clinic,
            language=language,
            prompt=prompt,
            conversation=conversation,
        )
        if not plan:
            return None, [], None

        if "reply" in plan:
            return str(plan.get("reply") or ""), [], None

        tool_name = plan.get("tool")
        return self.execute_tool_call(
            clinic=clinic,
            language=language,
            prompt=prompt,
            conversation_id=conversation_id,
            tool_name=tool_name,
            args=plan.get("args") or {},
            conversation=conversation,
        )

    def plan_tool_call(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
        conversation: Conversation | None,
    ) -> dict | None:
        return self._plan_tool_call(
            clinic=clinic,
            language=language,
            prompt=prompt,
            conversation=conversation,
        )

    def execute_tool_call(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
        conversation_id: int | None,
        tool_name: str | None,
        args: dict,
        conversation: Conversation | None = None,
    ) -> tuple[str | None, list[SuggestedSlot], dict | None]:
        if tool_name == "book_appointment":
            if not getattr(settings, "LLM_TOOL_BOOKING_ENABLED", False):
                return None, [], None

            tool_result = self._tool_book_appointment(
                clinic=clinic,
                conversation=conversation,
                args=args,
                language=language,
                prompt=prompt,
            )
            appointment = tool_result.get("appointment")
            if appointment:
                start_local = tool_result.get("start_local")
                time_label = None
                if isinstance(start_local, datetime):
                    tz = ZoneInfo(clinic.tz or "UTC")
                    time_label = start_local.astimezone(tz).strftime("%A %d %b %I:%M %p")
                reply = (
                    f"Your appointment is booked for {time_label}."
                    if time_label
                    else "Your appointment is booked."
                )
                try:
                    reply = self.compose_action_reply(
                        language=language,
                        action="confirm",
                        time_label=time_label,
                        clinic_name=clinic.name,
                        conversation_id=conversation_id,
                    )
                except LLMRouterError as exc:
                    logger.warning("LLM action reply skipped: %s", exc)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("LLM action reply error: %s", exc, exc_info=True)
                return reply, [], {
                    "action": "booked",
                    "appointment_id": appointment.id,
                    "service_code": tool_result.get("service_code"),
                }

            slots = tool_result.get("slots") or []
            if slots:
                reply = self._finalize_tool_reply(language, prompt, slots)
                return reply, slots, {"service_code": tool_result.get("service_code")}

            error = tool_result.get("error")
            if error == "missing_service":
                return "Which service would you like to book?", [], None
            if error == "missing_time":
                return "What time works for you?", [], None
            if error == "OUT_OF_HOURS":
                return "That time is outside our working hours. Please choose another time.", [], None
            if error == "SLOT_TAKEN":
                return "That time is no longer available. Please choose another time.", [], None
            if error == "missing_patient":
                return "I need your details before I can book. Please share your name.", [], None
            return "I could not book that time. Please choose another time.", [], None

        if tool_name == "cancel_appointment":
            if not getattr(settings, "LLM_TOOL_BOOKING_ENABLED", False):
                return None, [], None
            tool_result = self._tool_cancel_appointment(
                clinic=clinic,
                conversation=conversation,
                args=args,
                language=language,
                prompt=prompt,
            )
            appointment = tool_result.get("appointment")
            if appointment:
                time_label = None
                if appointment.start_at:
                    tz = ZoneInfo(clinic.tz or "UTC")
                    time_label = appointment.start_at.astimezone(tz).strftime("%A %d %b %I:%M %p")
                reply = (
                    f"Your appointment for {time_label} has been cancelled."
                    if time_label
                    else "Your appointment has been cancelled."
                )
                try:
                    reply = self.compose_action_reply(
                        language=language,
                        action="cancel",
                        time_label=time_label,
                        clinic_name=clinic.name,
                        conversation_id=conversation_id,
                    )
                except LLMRouterError as exc:
                    logger.warning("LLM action reply skipped: %s", exc)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("LLM action reply error: %s", exc, exc_info=True)
                return reply, [], {"action": "cancelled", "appointment_id": appointment.id}

            error = tool_result.get("error")
            if error == "missing_patient":
                return "I need your details before I can cancel. Please share your name.", [], None
            if error == "no_upcoming":
                return "I couldn't find an upcoming appointment to cancel.", [], None
            if error == "not_found":
                return "I couldn't match that appointment. Please share the date/time.", [], None
            return "I couldn't cancel that appointment. Please share the date/time.", [], None

        if tool_name == "reschedule_appointment":
            if not getattr(settings, "LLM_TOOL_BOOKING_ENABLED", False):
                return None, [], None
            tool_result = self._tool_reschedule_appointment(
                clinic=clinic,
                conversation=conversation,
                args=args,
                language=language,
                prompt=prompt,
            )
            appointment = tool_result.get("appointment")
            if appointment:
                start_local = tool_result.get("start_local")
                time_label = None
                if isinstance(start_local, datetime):
                    tz = ZoneInfo(clinic.tz or "UTC")
                    time_label = start_local.astimezone(tz).strftime("%A %d %b %I:%M %p")
                reply = (
                    f"Your appointment has been rescheduled to {time_label}."
                    if time_label
                    else "Your appointment has been rescheduled."
                )
                try:
                    reply = self.compose_action_reply(
                        language=language,
                        action="reschedule",
                        time_label=time_label,
                        clinic_name=clinic.name,
                        conversation_id=conversation_id,
                    )
                except LLMRouterError as exc:
                    logger.warning("LLM action reply skipped: %s", exc)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("LLM action reply error: %s", exc, exc_info=True)
                return reply, [], {
                    "action": "rescheduled",
                    "appointment_id": appointment.id,
                }

            slots = tool_result.get("slots") or []
            if slots:
                reply = self._finalize_tool_reply(language, prompt, slots)
                return reply, slots, {
                    "action": "reschedule",
                    "appointment_id": tool_result.get("appointment_id"),
                    "service_code": tool_result.get("service_code"),
                }

            error = tool_result.get("error")
            if error == "missing_patient":
                return "I need your details before I can reschedule. Please share your name.", [], None
            if error == "missing_service":
                return "Which service would you like to reschedule?", [], None
            if error == "missing_time":
                return "What time would you like instead?", [], None
            if error == "no_upcoming":
                return "I couldn't find an upcoming appointment to reschedule.", [], None
            if error == "SLOT_TAKEN":
                return "That time is no longer available. Please choose another time.", [], None
            if error == "OUT_OF_HOURS":
                return "That time is outside our working hours. Please choose another time.", [], None
            return "I couldn't reschedule that appointment. Please share a new time.", [], None

        if tool_name != "get_available_slots":
            return str(args.get("reply") or ""), [], None

        tool_result = self._tool_get_available_slots(clinic, args)
        slots = tool_result.get("slots", [])
        meta = {"service_code": tool_result.get("service_code")}
        if not slots:
            return self._finalize_tool_reply(language, prompt, []), [], meta

        reply = self._finalize_tool_reply(language, prompt, slots)
        return reply, slots, meta

    # ------------------------------------------------------------------ intent classification
    def classify_intent(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
    ) -> dict | None:
        """
        Lightweight intent/slot extraction with strict JSON output.
        Returns dict or raises LLMRouterError on provider issues.
        """
        if not self.api_key:
            raise LLMRouterError("DeepSeek API key not configured.")

        model = getattr(settings, "LLM_INTENT_MODEL", self.model)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a dental clinic virtual assistant. "
                    "You MUST answer with a single JSON object only. No prose. "
                    "Fields: intent (book|confirm|cancel|reschedule|clarify|off_topic), "
                    "confidence (0-1), time_text, service_text, language_guess, summary. "
                    "If off-topic, set intent='off_topic'. "
                    "If unsure, set intent='clarify' with confidence<=0.4. "
                    "Do NOT invent pricing/policies; do NOT leave JSON. "
                    "Keep summary max 20 words."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        try:
            response = requests.post(
                f"{self.api_base}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": 200,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=getattr(settings, "LLM_TIMEOUT_SECONDS", 15),
            )
        except requests.Timeout as exc:  # pragma: no cover - network path
            raise LLMRouterError("llm_timeout") from exc

        if response.status_code >= 400:
            logger.error("DeepSeek intent error %s: %s", response.status_code, response.text)
            raise LLMRouterError("llm_provider_error")

        payload = response.json()
        content = payload["choices"][0]["message"]["content"].strip()

        try:
            parsed = json.loads(content)
        except Exception:
            logger.warning("Intent parsing failed, content: %s", content)
            raise LLMRouterError("llm_parse_error")

        # Basic sanitization/defaults
        intent = (parsed.get("intent") or "clarify").lower()
        confidence = float(parsed.get("confidence", 0))
        parsed["intent"] = intent
        parsed["confidence"] = confidence
        parsed.setdefault("time_text", "")
        parsed.setdefault("service_text", "")
        parsed.setdefault("language_guess", language)
        parsed.setdefault("summary", "")

        return parsed

    # ------------------------------------------------------------------ helpers
    def _budget_available(self) -> bool:
        if not self.daily_budget:
            return True
        today = timezone.now().date()
        total = (
            LLMRequestLog.objects.filter(created_at__date=today)
            .aggregate(total=Sum("cost_estimate"))
            .get("total")
            or Decimal("0")
        )
        return (total + self.cost_per_request) <= self.daily_budget

    def _mark_economy_mode(self, session_state: SessionState | None, conversation: Conversation | None) -> None:
        if not session_state:
            return
        guardrails = session_state.llm_guardrails or {}
        guardrails["economy_mode"] = True
        session_state.llm_guardrails = guardrails
        session_state.save(update_fields=["llm_guardrails", "updated_at"])
        if conversation and not conversation.handoff_required:
            conversation.handoff_required = True
            conversation.save(update_fields=["handoff_required", "updated_at"])

    def _register_not_understood(
        self,
        session_state: SessionState | None,
        conversation: Conversation | None,
    ) -> None:
        if not session_state:
            return
        guardrails = session_state.llm_guardrails or {}
        guardrails["not_understood"] = guardrails.get("not_understood", 0) + 1
        session_state.llm_guardrails = guardrails
        session_state.save(update_fields=["llm_guardrails", "updated_at"])
        if guardrails["not_understood"] >= 2 and conversation and not conversation.handoff_required:
            conversation.handoff_required = True
            conversation.save(update_fields=["handoff_required", "updated_at"])
            try:
                from apps.accounts.notifications import notify_handoff

                notify_handoff(conversation)
            except Exception as exc:  # pragma: no cover - best effort log
                logger.warning("Failed to create handoff notification: %s", exc)

    def _system_prompt(self) -> str:
        return (
            "You are an appointment assistant for a dental clinic.\n"
            "- Use ONLY the facts in the provided context (services, prices, durations, slots).\n"
            "- Never invent or guess. If information is missing, say you don't have it.\n"
            "- Keep responses under two sentences; be concise and patient-friendly.\n"
            "- If off-topic, say so and steer back to dental appointments.\n"
            "- Do not provide medical advice or pricing not present in context."
        )

    def _plan_tool_call(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
        conversation: Conversation | None,
    ) -> dict | None:
        services = list(clinic.services.filter(is_active=True).order_by("name")[:20])
        service_list = "\n".join([f"- {svc.code}: {svc.name}" for svc in services]) or "No services"
        tz = clinic.tz or "UTC"
        now_local = timezone.now().astimezone(ZoneInfo(tz))
        upcoming_text = "No upcoming appointments"
        if conversation and conversation.patient:
            upcoming = self._list_upcoming_appointments(clinic, conversation.patient, limit=3)
            if upcoming:
                lines = []
                for appt in upcoming:
                    start_local = appt.start_at.astimezone(ZoneInfo(tz)) if appt.start_at else None
                    start_label = start_local.strftime("%Y-%m-%d %H:%M") if start_local else "unknown"
                    service_label = appt.service.name if appt.service else "service"
                    lines.append(f"- id:{appt.id} {start_label} {service_label} status:{appt.status}")
                upcoming_text = "\n".join(lines)

        system = (
            "You are a dental clinic assistant. "
            "Decide if you should call a tool. "
            "If the user asks about available times, return JSON with a tool call: "
            '{"tool":"get_available_slots","args":{"service_code":"...", "from_iso":"", "to_iso":"", "limit":3}}. '
            "If the user provides a specific date/time and wants to book, return: "
            '{"tool":"book_appointment","args":{"service_code":"...", "start_iso":"YYYY-MM-DDTHH:MM:SS+TZ"}}. '
            "If the user asks to cancel an upcoming appointment, return: "
            '{"tool":"cancel_appointment","args":{"appointment_id":123,"start_iso":""}}. '
            "If the user asks to reschedule, return: "
            '{"tool":"reschedule_appointment","args":{"appointment_id":123,"new_start_iso":"YYYY-MM-DDTHH:MM:SS+TZ"}}. '
            "Use a service_code from the list (or the only service if there is one). "
            "Use the clinic timezone when producing start_iso. "
            "If you need clarification, return JSON with a reply: "
            '{"reply":"..."} in the requested language. '
            "Return only JSON, no extra text."
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"Clinic time now: {now_local.isoformat()} ({tz})\n"
                    f"Services:\n{service_list}\n"
                    f"Upcoming appointments:\n{upcoming_text}\n\n"
                    f"User: {prompt}\nLanguage: {language}"
                ),
            },
        ]

        content = self._send_llm_request(
            messages=messages,
            prompt=prompt,
            model=getattr(settings, "LLM_TOOL_PLANNER_MODEL", self.model),
            max_tokens=220,
            temperature=0,
        )
        try:
            return json.loads(content)
        except Exception:
            logger.warning("Tool planner parse failed: %s", content)
            return None

    def _tool_get_available_slots(self, clinic: Clinic, args: dict) -> dict:
        service_code = str(args.get("service_code", "")).strip()
        if not service_code:
            return {"slots": []}

        service = clinic.services.filter(code=service_code, is_active=True).first()
        if not service:
            return {"slots": []}

        tzinfo = ZoneInfo(clinic.tz or "UTC")
        start_local = self._parse_tool_datetime(args.get("from_iso"), tzinfo) or timezone.now().astimezone(tzinfo)
        end_local = self._parse_tool_datetime(args.get("to_iso"), tzinfo) or (start_local + timedelta(days=7))

        try:
            limit = int(args.get("limit", 3))
        except (TypeError, ValueError):
            limit = 3
        limit = max(1, min(5, limit))

        slots = find_available_slots(
            clinic,
            service,
            start=start_local,
            end=end_local,
            limit=limit,
        )
        return {"slots": slots, "tz": clinic.tz or "UTC", "service_code": service_code}

    def _tool_book_appointment(
        self,
        *,
        clinic: Clinic,
        conversation: Conversation | None,
        args: dict,
        language: str,
        prompt: str,
    ) -> dict:
        service_code = str(args.get("service_code", "")).strip()
        service = None
        if service_code:
            service = clinic.services.filter(code=service_code, is_active=True).first()
        if not service:
            services = list(clinic.services.filter(is_active=True).order_by("duration_minutes")[:2])
            if len(services) == 1:
                service = services[0]
                service_code = service.code
        if not service:
            return {"error": "missing_service"}

        tzinfo = ZoneInfo(clinic.tz or "UTC")
        start_local = self._parse_tool_datetime(args.get("start_iso"), tzinfo)
        if not start_local:
            start_local = self._interpret_time_text(
                clinic=clinic,
                language=language,
                prompt=prompt,
                purpose="book",
            )
        if not start_local:
            return {"error": "missing_time", "service_code": service_code}
        if start_local.tzinfo is None:
            start_local = start_local.replace(tzinfo=tzinfo)

        patient = conversation.patient if conversation else None
        if not patient:
            return {"error": "missing_patient"}

        from apps.accounts.views import book_appointment

        appointment, error_code, tentative = book_appointment(
            clinic=clinic,
            patient=patient,
            service=service,
            start_local=start_local,
            source="assistant",
        )
        if appointment:
            return {
                "appointment": appointment,
                "tentative": tentative,
                "start_local": start_local,
                "service_code": service_code,
            }

        slots = []
        if error_code in {"SLOT_TAKEN", "OUT_OF_HOURS"}:
            start_window = start_local
            end_window = start_local + timedelta(days=7)
            slots = find_available_slots(
                clinic,
                service,
                start=start_window,
                end=end_window,
                limit=3,
            )

        return {
            "error": error_code or "BOOKING_FAILED",
            "slots": slots,
            "service_code": service_code,
        }

    def _tool_cancel_appointment(
        self,
        *,
        clinic: Clinic,
        conversation: Conversation | None,
        args: dict,
        language: str,
        prompt: str,
    ) -> dict:
        patient = conversation.patient if conversation else None
        if not patient:
            return {"error": "missing_patient"}

        start_iso = args.get("start_iso")
        if not start_iso:
            parsed = self._interpret_time_text(
                clinic=clinic,
                language=language,
                prompt=prompt,
                purpose="cancel",
            )
            if parsed:
                start_iso = parsed.isoformat()

        appointment = self._resolve_appointment(
            clinic=clinic,
            patient=patient,
            appointment_id=args.get("appointment_id"),
            start_iso=start_iso,
        )
        if not appointment:
            if self._list_upcoming_appointments(clinic, patient, limit=1):
                return {"error": "not_found"}
            return {"error": "no_upcoming"}

        from apps.accounts.views import cancel_appointment

        cancel_appointment(clinic=clinic, appointment=appointment)
        return {"appointment": appointment}

    def _tool_reschedule_appointment(
        self,
        *,
        clinic: Clinic,
        conversation: Conversation | None,
        args: dict,
        language: str,
        prompt: str,
    ) -> dict:
        patient = conversation.patient if conversation else None
        if not patient:
            return {"error": "missing_patient"}

        start_iso = args.get("start_iso")
        if not start_iso:
            parsed = self._interpret_time_text(
                clinic=clinic,
                language=language,
                prompt=prompt,
                purpose="reschedule",
            )
            if parsed:
                start_iso = parsed.isoformat()

        appointment = self._resolve_appointment(
            clinic=clinic,
            patient=patient,
            appointment_id=args.get("appointment_id"),
            start_iso=start_iso,
        )
        if not appointment:
            if self._list_upcoming_appointments(clinic, patient, limit=1):
                return {"error": "not_found"}
            return {"error": "no_upcoming"}

        start_iso = args.get("new_start_iso") or args.get("start_iso")
        tzinfo = ZoneInfo(clinic.tz or "UTC")
        start_local = self._parse_tool_datetime(start_iso, tzinfo) if start_iso else None
        if not start_local:
            start_local = self._interpret_time_text(
                clinic=clinic,
                language=language,
                prompt=prompt,
                purpose="reschedule",
            )
        if not start_local:
            service = appointment.service
            if not service:
                return {"error": "missing_service"}
            slots = find_available_slots(
                clinic,
                service,
                start=timezone.now().astimezone(tzinfo),
                end=timezone.now().astimezone(tzinfo) + timedelta(days=7),
                limit=3,
            )
            return {
                "slots": slots,
                "appointment_id": appointment.id,
                "service_code": service.code if service else "",
            }

        from apps.accounts.views import reschedule_appointment

        appointment, error_code, _warning = reschedule_appointment(
            clinic=clinic,
            appointment=appointment,
            start_local=start_local,
        )
        if appointment:
            return {"appointment": appointment, "start_local": start_local}

        slots = []
        if error_code in {"SLOT_TAKEN", "OUT_OF_HOURS"} and appointment and appointment.service:
            slots = find_available_slots(
                clinic,
                appointment.service,
                start=start_local,
                end=start_local + timedelta(days=7),
                limit=3,
            )
        return {
            "error": error_code or "RESCHEDULE_FAILED",
            "slots": slots,
            "appointment_id": appointment.id if appointment else None,
            "service_code": appointment.service.code if appointment and appointment.service else "",
        }

    def resolve_appointment_for_confirmation(
        self,
        *,
        clinic: Clinic,
        conversation: Conversation | None,
        appointment_id: object | None,
        start_iso: object | None,
    ) -> Appointment | None:
        patient = conversation.patient if conversation else None
        if not patient:
            return None
        return self._resolve_appointment(
            clinic=clinic,
            patient=patient,
            appointment_id=appointment_id,
            start_iso=start_iso,
        )

    def _list_upcoming_appointments(self, clinic: Clinic, patient, limit: int = 3) -> list[Appointment]:
        now = timezone.now()
        return list(
            Appointment.objects.filter(
                clinic=clinic,
                patient=patient,
                status__in=[
                    AppointmentStatus.PENDING,
                    AppointmentStatus.BOOKED,
                    AppointmentStatus.CONFIRMED,
                ],
                slot__lower__gte=now,
            )
            .order_by("slot__lower")[:limit]
        )

    def _resolve_appointment(
        self,
        *,
        clinic: Clinic,
        patient,
        appointment_id: object | None,
        start_iso: object | None,
    ) -> Appointment | None:
        qs = Appointment.objects.filter(
            clinic=clinic,
            patient=patient,
            status__in=[
                AppointmentStatus.PENDING,
                AppointmentStatus.BOOKED,
                AppointmentStatus.CONFIRMED,
            ],
        )
        if appointment_id:
            try:
                appointment_id_int = int(appointment_id)
            except (TypeError, ValueError):
                appointment_id_int = None
            if appointment_id_int:
                return qs.filter(id=appointment_id_int).order_by("slot__lower").first()

        tzinfo = ZoneInfo(clinic.tz or "UTC")
        start_local = self._parse_tool_datetime(str(start_iso), tzinfo) if start_iso else None
        candidates = list(qs.order_by("slot__lower")[:5])
        if start_local and candidates:
            target_date = start_local.astimezone(tzinfo).date()
            same_day = [
                appt
                for appt in candidates
                if appt.start_at and appt.start_at.astimezone(tzinfo).date() == target_date
            ]
            pool = same_day or candidates
            closest = None
            closest_delta = None
            for appt in pool:
                if not appt.start_at:
                    continue
                delta = abs((appt.start_at - start_local).total_seconds())
                if closest_delta is None or delta < closest_delta:
                    closest_delta = delta
                    closest = appt
            if closest:
                return closest

        if not start_local:
            upcoming = list(qs.order_by("slot__lower")[:2])
            if len(upcoming) == 1:
                return upcoming[0]
            return None

        return None

    def _interpret_time_text(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
        purpose: str,
    ) -> datetime | None:
        if not prompt or not self.api_key:
            return None
        if not self._budget_available():
            return None
        tz = clinic.tz or "UTC"
        now_local = timezone.now().astimezone(ZoneInfo(tz))
        system = (
            "You are a scheduling assistant. "
            "Extract the requested time from the user's message. "
            "If the user is rescheduling, extract the NEW requested time (ignore the old time). "
            "Return only JSON: {\"start_iso\":\"YYYY-MM-DDTHH:MM:SS+TZ\"} or {\"start_iso\": null}. "
            "Use the clinic timezone shown. If the time is ambiguous, choose the nearest reasonable time within 30 days."
        )
        user = (
            f"Purpose: {purpose}\n"
            f"Clinic time now: {now_local.isoformat()} ({tz})\n"
            f"User message: {prompt}\n"
            f"Language: {language}"
        )
        content = self._send_llm_request(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            prompt=prompt,
            model=getattr(settings, "LLM_TIME_PARSER_MODEL", self.model),
            max_tokens=120,
            temperature=0,
        )
        try:
            parsed = json.loads(content)
        except Exception:
            logger.warning("Time parse failed: %s", content)
            return None
        start_iso = parsed.get("start_iso")
        if not start_iso:
            return None
        try:
            dt = datetime.fromisoformat(str(start_iso))
        except ValueError:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ZoneInfo(tz))
        return dt.astimezone(ZoneInfo(tz))

    def _finalize_tool_reply(self, language: str, prompt: str, slots: list[SuggestedSlot]) -> str:
        lang = (language or "en").lower()
        if not slots:
            return "لا توجد مواعيد متاحة حالياً. هل تود وقتاً آخر؟" if lang == "ar" else "No slots are available right now. Would you like another time?"

        tentative_note = " (حجز مبدئي)" if lang == "ar" else " (tentative hold)"
        lines: list[str] = []
        for idx, slot in enumerate(slots[:3], start=1):
            label = slot.start.strftime("%A %d %b %I:%M %p")
            if slot.tentative:
                label += tentative_note
            lines.append(f"{idx}) {label}")

        if lang == "ar":
            intro = "هذه أقرب الأوقات المتاحة:"
            outro = "اختر رقم الموعد المناسب."
        else:
            intro = "Here are the next available times:"
            outro = "Reply with the number of the time that works for you."

        return f"{intro}\n" + "\n".join(lines) + f"\n{outro}"

    def select_slot_from_reply(
        self,
        *,
        clinic: Clinic,
        language: str,
        prompt: str,
        slots: list[dict],
        conversation_id: int | None = None,
    ) -> int | None:
        """Use the LLM to pick a slot index based on the user's reply."""
        if not slots:
            return None
        if not self.api_key:
            raise LLMRouterError("DeepSeek API key not configured.")

        conversation: Conversation | None = None
        session_state: SessionState | None = None
        if conversation_id:
            conversation = Conversation.objects.filter(pk=conversation_id).first()
            if conversation:
                session_state, _ = SessionState.objects.get_or_create(conversation=conversation)

        if not self._budget_available():
            self._mark_economy_mode(session_state, conversation)
            raise LLMRouterError("llm_budget_exhausted")

        tz = ZoneInfo(clinic.tz or "UTC")
        slot_lines: list[str] = []
        for idx, slot in enumerate(slots, start=1):
            start_raw = slot.get("start") or slot.get("start_at") or slot.get("start_at_iso") or ""
            label = str(start_raw)
            try:
                parsed = datetime.fromisoformat(str(start_raw))
            except (TypeError, ValueError):
                parsed = None
            if parsed:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=tz)
                label = parsed.astimezone(tz).strftime("%A %d %b %I:%M %p")
            slot_lines.append(f"{idx}. {label}")

        system = (
            "You are a scheduling assistant. Choose which slot best matches the user's reply. "
            "Return only JSON: {\"index\": 1} or {\"index\": null}. "
            "If the user says any time / first available, choose 1. "
            "If the user mentions a time (e.g., 10am, 14:30), choose the closest slot. "
            "Prefer the closest reasonable match instead of null."
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"Language: {language}\n"
                    f"User reply: {prompt}\n"
                    f"Slots:\n" + "\n".join(slot_lines)
                ),
            },
        ]

        content = self._send_llm_request(
            messages=messages,
            prompt=prompt,
            model=self.model,
            max_tokens=80,
            temperature=0,
        )
        try:
            parsed = json.loads(content)
        except Exception:
            logger.warning("Slot selection parse failed: %s", content)
            return None

        idx = parsed.get("index")
        if idx is None:
            idx = parsed.get("slot_index")
        try:
            idx_value = int(idx)
        except (TypeError, ValueError):
            return None
        if 1 <= idx_value <= len(slots):
            return idx_value
        return None

    def compose_action_reply(
        self,
        *,
        language: str,
        action: str,
        time_label: str | None = None,
        clinic_name: str | None = None,
        conversation_id: int | None = None,
    ) -> str:
        """Generate a short action response (confirm/cancel/reschedule) without KB grounding."""
        if not self.api_key:
            raise LLMRouterError("DeepSeek API key not configured.")

        conversation: Conversation | None = None
        session_state: SessionState | None = None
        if conversation_id:
            conversation = Conversation.objects.filter(pk=conversation_id).first()
            if conversation:
                session_state, _ = SessionState.objects.get_or_create(conversation=conversation)

        if not self._budget_available():
            self._mark_economy_mode(session_state, conversation)
            raise LLMRouterError("llm_budget_exhausted")

        lang = (language or "en").lower()
        action_clean = (action or "").strip().lower()
        time_text = time_label or ""
        clinic_text = clinic_name or ""

        system = (
            "You are a dental clinic assistant. "
            "Write one concise sentence that matches the action. "
            "Actions: confirm, cancel, reschedule. "
            "If time is provided, mention it. "
            "Do not ask questions."
        )
        user = (
            f"Language: {lang}\n"
            f"Action: {action_clean}\n"
            f"Time: {time_text}\n"
            f"Clinic: {clinic_text}\n"
        )

        return self._send_llm_request(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            prompt=user,
            model=self.model,
            max_tokens=120,
            temperature=0.2,
        )

    def _parse_tool_datetime(self, raw: str | None, tzinfo: ZoneInfo) -> datetime | None:
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tzinfo)
        return dt.astimezone(tzinfo)

    def _send_llm_request(
        self,
        *,
        messages: list[dict],
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        start = timezone.now()
        try:
            response = requests.post(
                f"{self.api_base}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=getattr(settings, "LLM_TIMEOUT_SECONDS", 15),
            )
        except requests.Timeout as exc:  # pragma: no cover - network path
            raise LLMRouterError("llm_timeout") from exc

        latency_ms = int((timezone.now() - start).total_seconds() * 1000)
        if latency_ms > self.max_latency_ms:
            raise LLMRouterError("llm_latency_exceeded")

        if response.status_code >= 400:
            logger.error("DeepSeek error %s: %s", response.status_code, response.text)
            raise LLMRouterError("llm_provider_error")

        payload = response.json()
        content = payload["choices"][0]["message"]["content"].strip()

        LLMRequestLog.objects.create(
            provider=LLMProvider.DEEPSEEK,
            model=model,
            prompt=prompt,
            response=content,
            request_metadata={"messages": messages},
            response_metadata=payload,
            latency_ms=latency_ms,
            success=True,
            cost_estimate=self.cost_per_request,
        )
        return content

    def _build_context(self, chunks: List[KnowledgeChunk]) -> Tuple[str, List[KnowledgeChunk]]:
        char_budget = self.max_tokens * self.chars_per_token
        selected: List[KnowledgeChunk] = []
        parts: List[str] = []
        running = 0
        for chunk in chunks:
            snippet = chunk.content.strip()
            if not snippet:
                continue
            addition = len(snippet)
            if selected and running + addition > char_budget:
                break
            parts.append(f"- {snippet}")
            running += addition
            selected.append(chunk)
        return "\n".join(parts), selected

    def _clinic_snapshot(self, clinic: Clinic) -> str:
        """Build real-time context from DB (services, pricing, durations, next slots)."""
        lines: list[str] = []

        try:
            services = clinic.services.filter(is_active=True).order_by("name")[:20]
        except Exception:
            services = []

        if services:
            lines.append("Services:")
            for svc in services:
                price = getattr(svc, "price", None)
                duration = getattr(svc, "duration_minutes", None)
                parts = [f"- {svc.code}: {svc.name}"]
                if duration:
                    parts.append(f"{duration} min")
                if price is not None:
                    parts.append(f"price: {price}")
                lines.append(", ".join(parts))

        try:
            slots = suggest_slots(clinic)
        except Exception:
            slots = []

        if slots:
            lines.append("Next available slots:")
            tz = clinic.tz or "UTC"
            for slot in slots[:3]:
                start = slot.start.astimezone(slot.start.tzinfo)
                label = start.strftime("%Y-%m-%d %H:%M")
                lines.append(f"- {label} ({tz})")

        return "\n".join(lines)

    def _retrieve_chunks(self, clinic: Clinic, language: str) -> List[KnowledgeChunk]:
        desired_language = language or LanguageChoices.ENGLISH
        try:
            index = KnowledgeIndex.objects.get(
                clinic=clinic,
                name=getattr(settings, "RAG_INDEX_NAME", "default"),
                is_active=True,
            )
        except KnowledgeIndex.DoesNotExist:
            return []

        primary = list(
            KnowledgeChunk.objects.filter(
                document__clinic=clinic,
                language=desired_language,
                document__indices=index,
            )
            .order_by("-score", "chunk_index")[: self.top_k]
        )

        if len(primary) >= self.top_k:
            return primary

        fallback = list(
            KnowledgeChunk.objects.filter(
                document__clinic=clinic,
                document__indices=index,
            )
            .exclude(language=desired_language)
            .order_by("-score", "chunk_index")[: self.top_k]
        )
        combined: List[KnowledgeChunk] = primary[:]
        for chunk in fallback:
            if chunk not in combined:
                combined.append(chunk)
            if len(combined) >= self.top_k:
                break
        return combined
