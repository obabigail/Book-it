import re
from html import unescape
from typing import Optional

from models import BookResponse

_LANGUAGE_ALIASES = {
    "pt": "pt",
    "por": "pt",
    "pt-br": "pt",
    "pt-pt": "pt",
    "en": "en",
    "eng": "en",
    "es": "es",
    "spa": "es",
    "fr": "fr",
    "fra": "fr",
    "fre": "fr",
    "de": "de",
    "deu": "de",
    "ger": "de",
    "it": "it",
    "ita": "it",
    "ja": "ja",
    "jpn": "ja",
    "ko": "ko",
    "kor": "ko",
    "zh": "zh",
    "zho": "zh",
    "chi": "zh",
    "ru": "ru",
    "rus": "ru",
}


def normalize_text(value: Optional[str]) -> str:
    return value.casefold().strip() if value else ""


def has_text(value: Optional[str]) -> bool:
    return bool(value and value.strip())


def normalize_language_code(value: Optional[str]) -> str:
    normalized = normalize_text(value)
    return _LANGUAGE_ALIASES.get(normalized, normalized)


def normalize_categories(categories: list[str], limit: int = 6) -> list[str]:
    normalized_categories: list[str] = []
    seen: set[str] = set()

    for category in categories or []:
        raw_parts = re.split(r"\s*/\s*|\s*>\s*|\s+\|\s+", category)
        for part in raw_parts:
            cleaned = re.sub(r"\s+", " ", part).strip(" -:/")
            if not cleaned:
                continue
            normalized = normalize_text(cleaned)
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_categories.append(cleaned)
            if len(normalized_categories) >= limit:
                return normalized_categories

    return normalized_categories


def clean_description(value: Optional[object], max_length: int = 900) -> str:
    if not value:
        return ""

    if isinstance(value, dict):
        value = value.get("value", "")
    elif isinstance(value, list):
        parts = [str(part).strip() for part in value if part]
        value = " ".join(parts)

    text = unescape(str(value))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<li\s*>", "- ", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if len(text) <= max_length:
        return text

    cutoff = text.rfind(" ", 0, max_length)
    if cutoff < max_length * 0.6:
        cutoff = max_length
    return text[:cutoff].rstrip(" ,;:-") + "..."


def canonicalize_title(title: str) -> str:
    normalized = normalize_text(title)
    normalized = re.sub(r"\(.*?\)|\[.*?\]", " ", normalized)
    normalized = re.split(r"[:\-|/]", normalized, maxsplit=1)[0]
    normalized = re.sub(
        r"\b(edition|edicao|edição|revised|updated|illustrated|illustrado|illustrated edition|anniversary|special edition|collector'?s edition|box set|paperback|hardcover)\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"\b(book|livro|volume|vol\.?)\s+\d+\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_book_signature(book: BookResponse) -> str:
    author = normalize_text(book.authors[0]) if book.authors else ""
    return f"{canonicalize_title(book.title)}::{author}"
