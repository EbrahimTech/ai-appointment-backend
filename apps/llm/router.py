"""Router for DeepSeek-backed grounded responses."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable, List, Tuple

import requests
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.clinics.models import Clinic, LanguageChoices
from apps.conversations.models import Conversation, SessionState
from apps.kb.models import KnowledgeChunk, KnowledgeIndex
from apps.llm.models import LLMProvider, LLMRequestLog, RetrievalLog

logger = logging.getLogger(__name__)


class LLMRouterError(RuntimeError):
    """Raised for recoverable router errors."""


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
        if not grounded_chunks:
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

    def _system_prompt(self) -> str:
        return (
            "You are an appointment assistant for a dental clinic.\n"
            "- Only answer with facts from the supplied context.\n"
            "- Never invent pricing, policies, or medical advice. If missing, reply with \"I'm sorry, I don't have that information.\"\n"
            "- Keep responses under two sentences.\n"
            "- If the user goes off-topic, politely state so in one sentence and steer back to dental appointments.\n"
            "- Stay professional and concise."
        )

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
