import pytest
from django.utils import timezone

from apps.conversations.models import Conversation, SessionState
from apps.dialog.topic_corridor import TopicCorridor

pytestmark = pytest.mark.django_db


def test_topic_corridor_nudge(clinic, patient):
    convo = Conversation.objects.create(
        clinic=clinic,
        patient=patient,
        dedupe_key=f"{clinic.slug}:{patient.normalized_phone}",
    )
    corridor = TopicCorridor()

    decision = corridor.evaluate(convo, {"message": "random", "is_off_topic": True})
    assert not decision.allow
    assert decision.nudge_required

    decision = corridor.evaluate(convo, {"message": "random", "is_off_topic": True})
    assert not decision.allow
    assert decision.handoff_required
