"""Utility helpers for patient data normalization."""

import re


PHONE_CLEANER = re.compile(r"[^\d+]")


def normalize_phone_number(raw: str) -> str:
    """Normalize phone numbers to E.164-ish format without whitespace."""
    if not raw:
        return ""
    cleaned = PHONE_CLEANER.sub("", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned.lstrip("0")
    return cleaned
