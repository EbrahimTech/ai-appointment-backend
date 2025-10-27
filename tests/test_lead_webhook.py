import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.channels.models import OutboxMessage

pytestmark = pytest.mark.django_db


def test_lead_webhook_queues_hsm(client, clinic, hmac_signature):
    payload = {
        "clinic": clinic.slug,
        "lead_id": "lead-123",
        "name": "John Doe",
        "phone": "+15555550123",
        "language": "en",
    }
    body = json.dumps(payload).encode()
    signature = hmac_signature(body)

    response = client.post(
        "/webhooks/lead",
        data=body,
        content_type="application/json",
        HTTP_X_LEAD_SIGNATURE=signature,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True

    outbox = OutboxMessage.objects.order_by("-created_at").first()
    delta = outbox.scheduled_for - timezone.now()
    assert delta.total_seconds() <= 10
