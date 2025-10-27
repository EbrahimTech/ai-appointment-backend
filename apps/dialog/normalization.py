"""Normalization helpers for bilingual Arabic/English conversations."""

from __future__ import annotations

import re

ARABIC_DIACRITICS = re.compile(r"[ؗ-ًؚ-ْ]")
EASTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")  # Arabic-Indic digits to Western digits

ARABIC_CHAR_VARIANTS = {
    "إ": "ا",  # Alif with hamza below -> Alif
    "أ": "ا",  # Alif with hamza above -> Alif
    "آ": "ا",  # Alif with madda -> Alif
    "ى": "ي",  # Alif maksura -> Ya
    "ة": "ه",  # Ta marbuta -> Ha
    "ؤ": "و",  # Waw with hamza -> Waw
    "ئ": "ي",  # Ya with hamza -> Ya
}

PHRASE_REPLACEMENTS = {
    "بعد بكرة": "بعد غد",
    "بعد غدا": "بعد غد",
    "after tomorrow": "بعد غد",
    "tomorrow": "غد",
    "today": "اليوم",
}

TOKEN_REPLACEMENTS = {
    "بكرة": "غد",
    "غدا": "غد",
    "تنضيف": "تنظيف",
    "تنضيفة": "تنظيف",
    "الثمن": "سعر",
    "بكم": "سعر",
    "كم": "سعر",
    "price": "سعر",
    "cost": "سعر",
    "cleaning": "تنظيف",
}

PRICE_KEYWORDS = {"سعر", "price", "cost"}
SERVICE_KEYWORDS = {"تنظيف", "استشارة", "تنظيفات"}


def _apply_char_variants(text: str) -> str:
    for original, replacement in ARABIC_CHAR_VARIANTS.items():
        text = text.replace(original, replacement)
    return text


def _apply_phrase_replacements(text: str) -> str:
    lowered = text
    for phrase, replacement in PHRASE_REPLACEMENTS.items():
        lowered = lowered.replace(phrase, replacement)
    return lowered


def _replace_tokens(tokens: list[str]) -> list[str]:
    return [TOKEN_REPLACEMENTS.get(token, token) for token in tokens]


def _append_intent_tokens(tokens: list[str]) -> list[str]:
    if any(token in PRICE_KEYWORDS for token in tokens):
        tokens.append("intent_price")
    if any(token in SERVICE_KEYWORDS for token in tokens):
        tokens.append("intent_service")
    return tokens


def normalize_text(value: str) -> str:
    """Normalize bilingual text: digits, diacritics, synonyms, and intent hints."""
    if not value:
        return ""

    text = value.strip().lower()
    text = text.translate(EASTERN_DIGITS)
    text = ARABIC_DIACRITICS.sub("", text)
    text = _apply_char_variants(text)
    text = _apply_phrase_replacements(text)

    tokens = text.split()
    tokens = _replace_tokens(tokens)
    tokens = _append_intent_tokens(tokens)
    return " ".join(tokens)
