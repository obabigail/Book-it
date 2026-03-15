import re
from typing import Optional

from models import BookResponse, ScoredBook

# Stopwords PT + EN para extração de keywords da descrição
_STOPWORDS = {
    "de", "a", "o", "e", "em", "um", "uma", "para", "com", "que", "do", "da",
    "dos", "das", "no", "na", "nos", "nas", "ao", "aos", "pelo", "pela", "ser",
    "foi", "ele", "ela", "seu", "sua", "como", "mais", "mas", "por", "se", "ou",
    "the", "a", "an", "of", "in", "and", "to", "is", "it", "this", "that",
    "his", "her", "with", "for", "on", "are", "was", "he", "she", "at", "be",
    "have", "from", "not", "but", "they", "their", "when", "who", "which",
    "book", "livro", "story", "historia", "novel", "romance",
}

# Pesos do scoring — soma deve ser 1.0
_WEIGHT_CATEGORY = 0.35
_WEIGHT_AUTHOR   = 0.30
_WEIGHT_PAGES    = 0.20
_WEIGHT_YEAR     = 0.15

# Penalidades por metadados ausentes
_PENALTY_NO_PAGES = 0.08
_PENALTY_NO_YEAR  = 0.04


def normalize_text(value: Optional[str]) -> str:
    return value.casefold().strip() if value else ""


def keywords_from_description(description: str, top_n: int = 3) -> list[str]:
    """Extrai as palavras mais frequentes da descrição, excluindo stopwords."""
    words = re.findall(r'\b[a-zA-ZÀ-ú]{4,}\b', description.lower())
    filtered = [w for w in words if w not in _STOPWORDS]
    freq: dict[str, int] = {}
    for w in filtered:
        freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=lambda w: freq[w], reverse=True)[:top_n]


def filter_books(books: list[BookResponse], filters: dict) -> list[BookResponse]:
    """
    Aplica filtros explicitos do usuario.
    Filtros disponiveis: min_pages, max_pages, min_year, max_year, category, exclude_title.
    """
    result = []

    for book in books:
        if filters.get("exclude_title"):
            if normalize_text(book.title) == normalize_text(filters["exclude_title"]):
                continue

        if filters.get("category"):
            requested_category = normalize_text(filters["category"])
            categories = [normalize_text(category) for category in book.categories]
            if requested_category and not any(
                requested_category in category for category in categories
            ):
                continue

        if filters.get("min_pages") and book.page_count:
            if book.page_count < filters["min_pages"]:
                continue
        if filters.get("max_pages") and book.page_count:
            if book.page_count > filters["max_pages"]:
                continue

        if filters.get("min_year") and book.published_year:
            if book.published_year < filters["min_year"]:
                continue
        if filters.get("max_year") and book.published_year:
            if book.published_year > filters["max_year"]:
                continue

        result.append(book)

    return result


def score_books(books: list[BookResponse], reference: BookResponse) -> list[ScoredBook]:
    """
    Pontua livros por similaridade com o livro de referencia.

    Criterios e pesos:
    - Categoria em comum  : 0.35  (Jaccard sobre conjuntos de categorias)
    - Autor em comum      : 0.30  (bonus binario — mesmo autor = peso completo)
    - Proximidade paginas : 0.20  (diferenca ate 500 paginas, escala linear)
    - Proximidade ano     : 0.15  (diferenca ate 30 anos, escala linear)

    Penalidades aplicadas quando metadados estao ausentes no candidato:
    - Sem page_count      : -0.08
    - Sem published_year  : -0.04
    """
    ref_cats    = {normalize_text(c) for c in reference.categories}
    ref_authors = {normalize_text(a) for a in reference.authors}

    scored = []

    for book in books:
        score = 0.0

        # --- categoria (0.35) ---
        book_cats = {normalize_text(c) for c in book.categories}
        if ref_cats and book_cats:
            overlap = len(ref_cats & book_cats) / len(ref_cats | book_cats)
            score += overlap * _WEIGHT_CATEGORY
        elif not ref_cats and not book_cats:
            # ambos sem categoria: neutro, nao penaliza nem bonifica
            score += _WEIGHT_CATEGORY * 0.5

        # --- autor (0.30) ---
        book_authors = {normalize_text(a) for a in book.authors}
        if ref_authors and book_authors and (ref_authors & book_authors):
            score += _WEIGHT_AUTHOR

        # --- paginas (0.20) ---
        if reference.page_count and book.page_count:
            diff = abs(reference.page_count - book.page_count)
            score += max(0.0, 1.0 - diff / 500) * _WEIGHT_PAGES
        elif not book.page_count:
            score -= _PENALTY_NO_PAGES

        # --- ano (0.15) ---
        if reference.published_year and book.published_year:
            diff = abs(reference.published_year - book.published_year)
            score += max(0.0, 1.0 - diff / 30) * _WEIGHT_YEAR
        elif not book.published_year:
            score -= _PENALTY_NO_YEAR

        scored.append(ScoredBook(**book.model_dump(), score=round(max(0.0, score), 4)))

    scored.sort(key=lambda book: book.score, reverse=True)
    return scored