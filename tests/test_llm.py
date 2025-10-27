from datetime import timedelta
from types import SimpleNamespace

import pytest

from apps.clinics.models import LanguageChoices
from apps.kb.models import KnowledgeChunk, KnowledgeDocument, KnowledgeIndex
from apps.llm.models import RetrievalLog
from apps.llm.router import LLMRouter

pytestmark = pytest.mark.django_db


def test_rag_response_grounded(monkeypatch, clinic, settings):
    settings.DEEPSEEK_API_KEY = "test-key"
    settings.RAG_TOP_K = 1

    document = KnowledgeDocument.objects.create(
        clinic=clinic,
        language=LanguageChoices.ENGLISH,
        title="Root Canal",
        source="seed",
        body="Root canal takes 60 minutes.",
    )
    chunk = KnowledgeChunk.objects.create(
        document=document,
        chunk_index=0,
        content="Root canal takes 60 minutes.",
        score=0.9,
    )
    index = KnowledgeIndex.objects.create(clinic=clinic, name="default", dimensions=1536)
    index.documents.add(document)

    called = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        called["payload"] = json
        return SimpleNamespace(status_code=200, json=lambda: {
            "choices": [{"message": {"content": "It takes 60 minutes."}}]
        })

    monkeypatch.setattr("apps.llm.router.requests.post", fake_post)

    router = LLMRouter()
    answer = router.answer(clinic=clinic, language="en", prompt="How long is a root canal?", conversation_id=None)

    assert "Root canal takes 60 minutes." in called["payload"]["messages"][1]["content"]
    assert answer == "It takes 60 minutes."
    assert RetrievalLog.objects.count() == 1
