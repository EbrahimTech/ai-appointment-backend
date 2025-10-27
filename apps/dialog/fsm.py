"""Finite-state machine for the appointment dialog flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from apps.conversations.models import Conversation
from apps.dialog.topic_corridor import TopicCorridor, TopicCorridorDecision


class DialogState:
    """Enumeration of FSM states."""

    IDLE = "idle"
    QUALIFICATION = "qualification"
    SLOT_OFFER = "slot_offer"
    CONFIRM = "confirm"
    DONE = "done"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"


TransitionGuard = Callable[[Conversation, dict], bool]
TransitionAction = Callable[[Conversation, dict], None]


@dataclass(frozen=True)
class Transition:
    source: str
    trigger: str
    destination: str
    guard: Optional[TransitionGuard] = None
    action: Optional[TransitionAction] = None


class DialogFSM:
    """Simple FSM with pluggable transition guards."""

    def __init__(self, corridor: TopicCorridor | None = None) -> None:
        self.corridor = corridor or TopicCorridor()
        self.transitions: Dict[str, list[Transition]] = {}
        self._register_default_transitions()

    def _register_default_transitions(self) -> None:
        add = self._register
        add(DialogState.IDLE, "lead_received", DialogState.QUALIFICATION)
        add(DialogState.QUALIFICATION, "qualified", DialogState.SLOT_OFFER)
        add(DialogState.SLOT_OFFER, "slot_proposed", DialogState.CONFIRM)
        add(DialogState.CONFIRM, "confirmed", DialogState.DONE)
        add(DialogState.CONFIRM, "reschedule", DialogState.RESCHEDULE)
        add(DialogState.CONFIRM, "cancel", DialogState.CANCEL)
        add(DialogState.RESCHEDULE, "slot_proposed", DialogState.CONFIRM)
        add(DialogState.CANCEL, "restart", DialogState.QUALIFICATION)

    def _register(self, source: str, trigger: str, destination: str) -> None:
        self.transitions.setdefault(source, []).append(
            Transition(source=source, trigger=trigger, destination=destination)
        )

    def can_transition(self, conversation: Conversation, trigger: str) -> bool:
        return any(t.trigger == trigger for t in self.transitions.get(conversation.fsm_state, []))

    def apply(
        self,
        conversation: Conversation,
        trigger: str,
        context: dict | None = None,
    ) -> bool:
        context = context or {}
        topic_decision: TopicCorridorDecision = self.corridor.evaluate(conversation, context)
        if topic_decision.handoff_required:
            conversation.handoff_required = True
            conversation.save(update_fields=["handoff_required", "updated_at"])
            return False

        for transition in self.transitions.get(conversation.fsm_state, []):
            if transition.trigger != trigger:
                continue
            if transition.guard and not transition.guard(conversation, context):
                continue
            conversation.fsm_state = transition.destination
            if transition.action:
                transition.action(conversation, context)
            conversation.save(update_fields=["fsm_state", "updated_at"])
            return True
        return False
