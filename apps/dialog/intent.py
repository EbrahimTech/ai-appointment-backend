"""Rule-based intent detection for gray/clear intents."""

from __future__ import annotations


def detect_intent(text: str) -> str:
    """Return basic intents using keywords (EN + simple AR heuristics)."""

    keywords = {
        "book": {
            "book",
            "appointment",
            "schedule",
            "slot",
            # Arabic booking cues
            "موعد",
            "حجز",
            "زيارة",
            "السبت",
            "الاحد",
            "الأحد",
            "الاثنين",
            "الثلاثاء",
            "الاربعاء",
            "الأربعاء",
            "الخميس",
            "الجمعة",
            "صباح",
            "مساء",
        },
        "confirm": {"confirm", "yes", "done", "تأكيد", "موافق", "تمام"},
        "cancel": {"cancel", "drop", "no", "الغاء", "إلغاء", "الغي", "ألغي", "ألغى"},
        "reschedule": {"reschedule", "change", "move", "تغيير", "تعديل", "أغير"},
    }

    for intent, vocab in keywords.items():
        if any(token in text for token in vocab):
            return intent

    # Heuristic: times/dates -> treat as booking intent
    if any(ch.isdigit() for ch in text) and any(marker in text for marker in {":", "مساء", "صباح"}):
        return "book"

    return "clarify"
