"""Run a simple dialog harness for quick flow validation."""

from __future__ import annotations

import random
import uuid
from datetime import timedelta
from contextlib import contextmanager
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.appointments.scheduling import SuggestedSlot
from apps.clinics.models import Clinic
from apps.conversations.models import Conversation, SessionState
from apps.dialog.orchestrator import DialogOrchestrator
from apps.llm.router import LLMRouterError
from apps.patients.models import Patient
import apps.dialog.orchestrator as orchestrator_module


class _StubLLM:
    """No-op LLM stub to keep harness deterministic and offline."""

    def classify_intent(self, **kwargs):  # noqa: D401
        return None

    def answer(self, **kwargs):
        return "Sure. What would you like to know?"

    def select_slot_from_reply(self, **kwargs):
        return None

    def compose_action_reply(self, **kwargs):
        raise LLMRouterError("stub")

    def plan_booking_decision(self, **kwargs):
        return None

    def extract_booking_slots(self, **kwargs):
        clinic = kwargs.get("clinic")
        prompt = (kwargs.get("prompt") or "").lower()
        language = (kwargs.get("language") or "").lower()
        slots = {}
        confidence = {}

        reason_map = {
            "referral": {"referral"},
            "cosmetic": {"cosmetic", "whitening", "ortho"},
            "pain": {"pain", "toothache"},
            "checkup": {"checkup", "exam", "consult"},
            "other": {"other"},
        }
        for reason, tokens in reason_map.items():
            if any(token in prompt for token in tokens):
                slots["reason"] = reason
                confidence["reason"] = 0.9
                break

        if clinic:
            for service in clinic.services.filter(is_active=True):
                if service.name and service.name.lower() in prompt:
                    slots["service_code"] = service.code
                    confidence["service"] = 0.9
                    break

        tz = ZoneInfo(clinic.tz or "UTC") if clinic else timezone.get_current_timezone()
        today = timezone.now().astimezone(tz).date()
        if "tomorrow" in prompt:
            slots["date_iso"] = (today + timedelta(days=1)).isoformat()
            confidence["date"] = 0.9
        elif "today" in prompt:
            slots["date_iso"] = today.isoformat()
            confidence["date"] = 0.9

        if "morning" in prompt:
            slots["time_window"] = "morning"
            confidence["time_window"] = 0.9
        elif "afternoon" in prompt:
            slots["time_window"] = "afternoon"
            confidence["time_window"] = 0.9
        elif "evening" in prompt:
            slots["time_window"] = "evening"
            confidence["time_window"] = 0.9
        elif "any time" in prompt or "anytime" in prompt:
            slots["time_window"] = "any"
            confidence["time_window"] = 0.9

        if slots.get("reason") == "pain":
            if "severe" in prompt or "strong" in prompt:
                slots["pain_level"] = "severe"
                confidence["pain_level"] = 0.9
            elif "moderate" in prompt:
                slots["pain_level"] = "moderate"
                confidence["pain_level"] = 0.9
            elif "mild" in prompt:
                slots["pain_level"] = "mild"
                confidence["pain_level"] = 0.9

        if not slots:
            return None
        return {"slots": slots, "confidence": confidence}

    def answer_with_tools(self, **kwargs):
        return None, None, None

    def plan_tool_call(self, **kwargs):
        return None

    def resolve_appointment_for_confirmation(self, **kwargs):
        return None

    def execute_tool_call(self, **kwargs):
        return "", [], None

    def repair_reply(self, **kwargs):
        raise LLMRouterError("stub")


@contextmanager
def _temp_settings():
    overrides = {
        "LLM_INTENT_ENABLED": False,
        "LLM_DECISION_JSON_ENABLED": False,
        "LLM_SLOT_EXTRACTOR_ENABLED": True,
        "LLM_TOOL_CALLING_ENABLED": False,
        "LLM_TOOL_BOOKING_ENABLED": False,
    }
    original = {key: getattr(settings, key, None) for key in overrides}
    for key, value in overrides.items():
        setattr(settings, key, value)
    try:
        yield
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


class Command(BaseCommand):
    help = "Run a 30-conversation dialog harness (10 booking, 10 FAQ, 10 random)."

    def add_arguments(self, parser):
        parser.add_argument("--clinic", default="prime-dental", help="Clinic slug")
        parser.add_argument("--seed", type=int, default=7, help="Random seed")

    def handle(self, *args, **options):
        random.seed(options["seed"])
        clinic = Clinic.objects.filter(slug=options["clinic"]).first()
        if not clinic:
            self.stdout.write(self.style.ERROR("Clinic not found."))
            return

        used_numbers: set[str] = set()

        def _unique_phone() -> tuple[str, str]:
            max_attempts = 50
            for _ in range(max_attempts):
                suffix = f"{uuid.uuid4().int % 10**7:07d}"
                phone = f"+1555{suffix}"
                normalized = phone.replace("+", "")
                if normalized in used_numbers:
                    continue
                if Patient.objects.filter(clinic=clinic, normalized_phone=normalized).exists():
                    continue
                used_numbers.add(normalized)
                return phone, normalized
            raise RuntimeError("Failed to generate unique phone number for harness.")

        service = clinic.services.filter(is_active=True).order_by("id").first()
        service_name = service.name if service and service.name else "consultation"

        booking_scripts = [
            ["I want to book", "checkup", service_name, "tomorrow", "morning"],
            ["Book appointment", "cosmetic", service_name, "tomorrow", "afternoon"],
            ["Need an appointment", "pain", "severe", service_name, "tomorrow", "evening"],
            ["Book checkup tomorrow morning " + service_name],
            ["Book cosmetic tomorrow afternoon " + service_name],
            ["I want to book", "referral", service_name, "tomorrow", "morning"],
            ["Schedule checkup " + service_name, "tomorrow", "morning"],
            ["Book visit", "other", service_name, "tomorrow", "afternoon"],
            ["Need checkup", service_name, "tomorrow", "evening"],
            ["Book", "checkup", service_name, "tomorrow", "morning"],
        ]

        faq_scripts = [
            ["What are your prices?"],
            ["Do you offer X-ray services?"],
            ["What services are available?"],
            ["Where are you located?"],
            ["What are your working hours?"],
            ["Tell me about prices"],
            ["Do you have whitening?"],
            ["Services list please"],
            ["Location info"],
            ["Hours today"],
        ]

        random_scripts = [
            ["hello"],
            ["I have a question"],
            ["help"],
            ["can you assist me"],
            ["random text here"],
            ["hi there"],
            ["thanks"],
            ["ok"],
            ["cool"],
            ["what can you do"],
        ]

        scenarios = (
            [("booking", script) for script in booking_scripts]
            + [("faq", script) for script in faq_scripts]
            + [("random", script) for script in random_scripts]
        )

        orchestrator = DialogOrchestrator()
        orchestrator.llm_router = _StubLLM()
        def _stub_find_available_slots(clinic_obj, service_obj, *, start, end, limit=5):
            tz = ZoneInfo(clinic_obj.tz or "UTC")
            now_local = timezone.now().astimezone(tz).replace(minute=0, second=0, microsecond=0)
            duration = timedelta(minutes=service_obj.duration_minutes if service_obj else 30)
            slots = []
            cursor = now_local + timedelta(hours=1)
            for _ in range(limit):
                slots.append(
                    SuggestedSlot(
                        start=cursor,
                        end=cursor + duration,
                        tentative=False,
                        source="local",
                    )
                )
                cursor += duration
            return slots

        def _stub_suggest_slots(clinic_obj, *, service=None, count=2):
            service_obj = (
                service
                or clinic_obj.services.filter(is_active=True)
                .order_by("duration_minutes")
                .first()
            )
            if not service_obj:
                return []
            return _stub_find_available_slots(
                clinic_obj,
                service_obj,
                start=timezone.now(),
                end=timezone.now() + timedelta(days=1),
                limit=count,
            )

        orchestrator_module.enqueue_whatsapp_session_message = lambda *args, **kwargs: None
        orchestrator_module.find_available_slots = _stub_find_available_slots
        orchestrator_module.suggest_slots = _stub_suggest_slots

        results = []
        clarify_hits = 0
        ask_reason_loops = 0
        slot_within_2_4 = 0
        handoff_reasons = {}

        with _temp_settings():
            for scenario_type, script in scenarios:
                phone, normalized = _unique_phone()
                patient = Patient.objects.create(
                    clinic=clinic,
                    full_name=f"Harness {uuid.uuid4().hex[:6]}",
                    phone_number=phone,
                    normalized_phone=normalized,
                    language="en",
                )
                conversation = Conversation.objects.create(
                    clinic=clinic,
                    patient=patient,
                    lead_source="harness",
                    fsm_state="idle",
                    dedupe_key=f"harness:{uuid.uuid4().hex}",
                )

                states = []
                clarify_menu = False
                slot_turn = None

                for idx, text in enumerate(script, start=1):
                    response_text, intent = orchestrator.handle_inbound(
                        conversation, body=text, language="en"
                    )
                    session_state = SessionState.objects.filter(conversation=conversation).first()
                    decision = session_state.context.get("decision") if session_state else {}
                    booking_flow = session_state.context.get("booking_flow") if session_state else {}
                    state = ""
                    if isinstance(booking_flow, dict):
                        state = booking_flow.get("state") or ""
                    if not state and isinstance(decision, dict):
                        state = decision.get("state") or ""
                    states.append(state or intent)
                    if response_text and "choose a number" in response_text.lower():
                        clarify_menu = True
                    if session_state and session_state.context.get("slot_suggestions") and slot_turn is None:
                        slot_turn = idx

                session_state = SessionState.objects.filter(conversation=conversation).first()
                handoff_reason = (session_state.context.get("handoff_reason") or "") if session_state else ""
                if conversation.handoff_required:
                    handoff_reason = handoff_reason or "handoff"

                max_same = 0
                current = None
                streak = 0
                for state in states:
                    if state == current and state:
                        streak += 1
                    else:
                        current = state
                        streak = 1
                    max_same = max(max_same, streak)
                if "ASK_REASON" in states and max_same > 2:
                    ask_reason_loops += 1
                if clarify_menu:
                    clarify_hits += 1
                if slot_turn and 2 <= slot_turn <= 4:
                    slot_within_2_4 += 1
                if handoff_reason:
                    handoff_reasons[handoff_reason] = handoff_reasons.get(handoff_reason, 0) + 1

                results.append(
                    {
                        "conversation_id": conversation.id,
                        "type": scenario_type,
                        "turns": len(script),
                        "last_state": states[-1] if states else "",
                        "clarify_menu": clarify_menu,
                        "slot_turn": slot_turn or "",
                        "handoff_reason": handoff_reason,
                    }
                )

        self.stdout.write("Harness summary")
        self.stdout.write(f"Total conversations: {len(results)}")
        self.stdout.write(f"Clarify menu triggered: {clarify_hits}")
        self.stdout.write(f"ASK_REASON loops >2: {ask_reason_loops}")
        self.stdout.write(f"Slots within 2-4 turns: {slot_within_2_4}")
        if handoff_reasons:
            self.stdout.write("Handoff reasons:")
            for reason, count in sorted(handoff_reasons.items()):
                self.stdout.write(f"  - {reason}: {count}")
        else:
            self.stdout.write("Handoff reasons: none")

        self.stdout.write("\nConversation results:")
        for row in results:
            self.stdout.write(
                f"{row['conversation_id']}\t{row['type']}\tturns={row['turns']}\t"
                f"last={row['last_state']}\tclarify={row['clarify_menu']}\t"
                f"slot_turn={row['slot_turn']}\thandoff={row['handoff_reason']}"
            )
