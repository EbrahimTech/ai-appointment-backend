"""Topic corridor enforcement to keep conversation aligned."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.conversations.models import Conversation, SessionState


@dataclass(slots=True)
class TopicCorridorDecision:
    """Outcome of evaluating the topic corridor."""

    allow: bool = True
    nudge_required: bool = False
    handoff_required: bool = False


class TopicCorridor:
    """Applies soft nudges and escalations for off-topic interactions."""

    def __init__(self, polite_window: timedelta | None = None) -> None:
        self.polite_window = polite_window or timedelta(minutes=10)

    def evaluate(self, conversation: Conversation, context: dict) -> TopicCorridorDecision:
        message = context.get("message")
        if not message:
            return TopicCorridorDecision()

        session_state, _ = SessionState.objects.get_or_create(conversation=conversation)
        now = timezone.now()
        violation_count = session_state.context.get("violations", 0)

        if context.get("is_off_topic"):
            violation_count += 1
            session_state.context["violations"] = violation_count
            session_state.last_nudged_at = now
            session_state.save(update_fields=["context", "last_nudged_at", "updated_at"])

            if violation_count == 1:
                return TopicCorridorDecision(allow=False, nudge_required=True)

            if violation_count > 1:
                return TopicCorridorDecision(allow=False, handoff_required=True)

        # decay violations over time
        if session_state.last_nudged_at and now - session_state.last_nudged_at > self.polite_window:
            session_state.context["violations"] = 0
            session_state.save(update_fields=["context", "updated_at"])

        return TopicCorridorDecision()
