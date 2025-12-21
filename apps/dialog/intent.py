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
            "مواعيد",
            "المواعيد",
            "موعد",
            "الأوقات",
            "اوقات",
            "أوقات",
            "متاح",
            "متاحة",
            "متوفر",
            "available",
            "صباح",
            "مساء",
        },
        "confirm": {"confirm", "yes", "done", "تأكيد", "موافق", "تمام"},
        "cancel": {"cancel", "drop", "no", "الغاء", "إلغاء", "الغي", "ألغي", "ألغى"},
        "reschedule": {"reschedule", "change", "move", "تغيير", "تعديل", "أغير"},
        "pricing": {"price", "pricing", "cost", "fees", "سعر", "اسعار", "أسعار", "تكلفة", "رسوم"},
        "services": {"service", "services", "offer", "خدمات", "الخدمات", "الخدمة", "ماذا تقدمون"},
        "xray": {"xray", "x-ray", "radiograph", "اشعة", "أشعة", "تصوير"},
        "policy": {"policy", "سياسة", "سياسات", "شروط"},
    }

    priority_intents = ["cancel", "reschedule"]
    for intent in priority_intents:
        vocab = keywords.get(intent, set())
        if any(token in text for token in vocab):
            return intent

    for intent, vocab in keywords.items():
        if intent in {"cancel", "reschedule"}:
            continue
        if any(token in text for token in vocab):
            return intent

    # Heuristic: times/dates -> treat as booking intent
    if any(ch.isdigit() for ch in text) and any(marker in text for marker in {":", "مساء", "صباح"}):
        return "book"

    return "clarify"
