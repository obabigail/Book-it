from typing import Optional

from models import BookResponse, ScoredBook


def normalize_text(value: Optional[str]) -> str:
    return value.casefold().strip() if value else ""


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
    - Categoria em comum:     0.50
    - Proximidade de paginas: 0.30
    - Proximidade de ano:     0.20
    """
    scored = []

    for book in books:
        score = 0.0

        ref_cats = set(normalize_text(category) for category in reference.categories)
        book_cats = set(normalize_text(category) for category in book.categories)
        if ref_cats and book_cats:
            overlap = len(ref_cats & book_cats) / len(ref_cats | book_cats)
            score += overlap * 0.50
        elif not ref_cats and not book_cats:
            score += 0.25

        if reference.page_count and book.page_count:
            diff = abs(reference.page_count - book.page_count)
            page_score = max(0.0, 1.0 - diff / 500)
            score += page_score * 0.30

        if reference.published_year and book.published_year:
            diff = abs(reference.published_year - book.published_year)
            year_score = max(0.0, 1.0 - diff / 30)
            score += year_score * 0.20

        scored.append(ScoredBook(**book.model_dump(), score=round(score, 4)))

    scored.sort(key=lambda book: book.score, reverse=True)
    return scored
