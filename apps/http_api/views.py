from __future__ import annotations

from datetime import timedelta
from statistics import mean

from django.http import JsonResponse
from django.utils import timezone

from apps.channels.models import OutboxMessage, OutboxStatus
from apps.conversations.models import Conversation, ConversationMessage
from apps.llm.models import LLMRequestLog


def metrics_summary(request):
    now = timezone.now()
    metrics = {
        "ttfr_seconds": {
            "day": _average_ttfr(1),
            "week": _average_ttfr(7),
        },
        "intent_accuracy": _intent_accuracy(7),
        "grounded_answer_rate": _grounded_answer_rate(7),
        "handoff_rate": _handoff_rate(7),
        "delivery_fail_rate": _delivery_fail_rate(7),
    }
    return JsonResponse({"ok": True, "generated_at": now.isoformat(), "metrics": metrics})


def _average_ttfr(days: int) -> float:
    cutoff = timezone.now() - timedelta(days=days)
    conversation_ids = (
        ConversationMessage.objects.filter(created_at__gte=cutoff)
        .values_list("conversation_id", flat=True)
        .distinct()
    )
    durations = []
    for conversation_id in conversation_ids:
        inbound = (
            ConversationMessage.objects.filter(
                conversation_id=conversation_id,
                direction="inbound",
                created_at__gte=cutoff,
            )
            .order_by("created_at")
            .first()
        )
        outbound = (
            ConversationMessage.objects.filter(
                conversation_id=conversation_id,
                direction="outbound",
                created_at__gte=cutoff,
            )
            .order_by("created_at")
            .first()
        )
        if inbound and outbound and outbound.created_at > inbound.created_at:
            durations.append((outbound.created_at - inbound.created_at).total_seconds())
    return mean(durations) if durations else 0.0


def _intent_accuracy(days: int) -> float:
    cutoff = timezone.now() - timedelta(days=days)
    inbound = ConversationMessage.objects.filter(direction="inbound", created_at__gte=cutoff)
    total = inbound.count()
    if not total:
        return 1.0
    confident = inbound.exclude(intent__in={"clarify", "unknown"}).count()
    return confident / total


def _grounded_answer_rate(days: int) -> float:
    cutoff = timezone.now() - timedelta(days=days)
    logs = LLMRequestLog.objects.filter(created_at__gte=cutoff, success=True)
    total = logs.count()
    if not total:
        return 1.0
    grounded = logs.filter(retrievals__isnull=False).distinct().count()
    return grounded / total


def _handoff_rate(days: int) -> float:
    cutoff = timezone.now() - timedelta(days=days)
    conversations = Conversation.objects.filter(updated_at__gte=cutoff)
    total = conversations.count()
    if not total:
        return 0.0
    handoffs = conversations.filter(handoff_required=True).count()
    return handoffs / total


def _delivery_fail_rate(days: int) -> float:
    cutoff = timezone.now() - timedelta(days=days)
    messages = OutboxMessage.objects.filter(created_at__gte=cutoff)
    total = messages.filter(status__in=[OutboxStatus.SENT, OutboxStatus.DELIVERED, OutboxStatus.FAILED]).count()
    if not total:
        return 0.0
    failed = messages.filter(status=OutboxStatus.FAILED).count()
    return failed / total
