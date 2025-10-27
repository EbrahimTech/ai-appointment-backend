"""Rule-based intent detection for gray/clear intents."""

from __future__ import annotations


def detect_intent(text: str) -> str:
    """Return basic intents using keywords."""
    keywords = {
        "book": {"book", "appointment", "schedule", "slot"},
        "confirm": {"confirm", "yes", "done"},
        "cancel": {"cancel", "drop", "no"},
        "reschedule": {"reschedule", "change", "move"},
    }
    for intent, vocab in keywords.items():
        if any(token in text for token in vocab):
            return intent
    return "clarify"
