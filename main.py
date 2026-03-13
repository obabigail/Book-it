import os
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from filters import filter_books, score_books
from models import BookResponse, RecommendationResponse

app = FastAPI(
    title="Book Recommender API",
    description="Recomendacao de livros via Google Books API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_SEARCH_API = "https://openlibrary.org/search.json"
API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")
GENERIC_SUBJECTS = {
    "fiction",
    "ficcao",
    "general",
    "literature",
    "novel",
    "book",
    "books",
}


def normalize_text(value: Optional[str]) -> str:
    return value.casefold().strip() if value else ""


def has_text(value: Optional[str]) -> bool:
    return bool(value and value.strip())


async def fetch_google_books(query: str, max_results: int = 20) -> list[dict]:
    params = {
        "q": query,
        "maxResults": max_results,
        "printType": "books",
    }
    if API_KEY:
        params["key"] = API_KEY

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GOOGLE_BOOKS_API, params=params)

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Falha ao contatar Google Books API")

    data = response.json()
    return data.get("items", [])


async def fetch_books_by_author(author: str, title: Optional[str] = None, max_results: int = 20) -> list[BookResponse]:
    query_parts = [f'inauthor:"{author.strip()}"']
    if has_text(title):
        query_parts.append(f'intitle:"{title.strip()}"')

    items = await fetch_google_books(" ".join(query_parts), max_results=max_results)
    books = [parse_book(item) for item in items]
    return [book for book in books if book is not None]


async def fetch_open_library_subjects(
    title: str,
    authors: list[str],
    published_year: Optional[int],
) -> list[str]:
    params = {
        "title": title,
        "limit": 5,
        "fields": "key,title,author_name,first_publish_year",
    }
    if authors:
        params["author"] = authors[0]

    headers = {"User-Agent": "BookRecomendations/0.1 (Open Library enrichment)"}

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            search_response = await client.get(OPEN_LIBRARY_SEARCH_API, params=params)
            search_response.raise_for_status()
            docs = search_response.json().get("docs", [])
            work_key = choose_open_library_work(docs, title, authors, published_year)
            if not work_key:
                return []

            work_response = await client.get(f"https://openlibrary.org{work_key}.json")
            work_response.raise_for_status()
    except httpx.HTTPError:
        return []

    return select_specific_subjects(work_response.json().get("subjects", []))


def choose_open_library_work(
    docs: list[dict],
    title: str,
    authors: list[str],
    published_year: Optional[int],
) -> Optional[str]:
    normalized_title = normalize_text(title)
    normalized_authors = {normalize_text(author) for author in authors}
    best_key = None
    best_score = -1.0

    for doc in docs:
        score = 0.0
        doc_title = normalize_text(doc.get("title"))
        if doc_title == normalized_title:
            score += 2.0
        elif normalized_title and normalized_title in doc_title:
            score += 1.0

        doc_authors = {normalize_text(author) for author in doc.get("author_name", [])}
        if normalized_authors and doc_authors and normalized_authors & doc_authors:
            score += 1.0

        doc_year = doc.get("first_publish_year")
        if published_year and isinstance(doc_year, int):
            score += max(0.0, 1.0 - abs(published_year - doc_year) / 20)

        if score > best_score:
            best_score = score
            best_key = doc.get("key")

    return best_key


def select_specific_subjects(subjects: list[str], limit: int = 3) -> list[str]:
    selected = []
    seen = set()

    for subject in subjects:
        normalized = normalize_text(subject)
        if not normalized or normalized in seen:
            continue
        if normalized in GENERIC_SUBJECTS:
            continue
        if any(token in normalized for token in {"fiction", "general"}) and len(normalized) < 18:
            continue

        selected.append(subject.strip())
        seen.add(normalized)
        if len(selected) >= limit:
            break

    return selected


def build_search_terms(
    q: Optional[str],
    reference: BookResponse,
    category: Optional[str],
    enriched_subjects: list[str],
) -> list[str]:
    ordered_terms: list[str] = []

    if category and category.strip():
        ordered_terms.append(category.strip())

    ordered_terms.extend(subject for subject in enriched_subjects if subject.strip())

    if reference.categories:
        ordered_terms.append(reference.categories[0].strip())

    if has_text(q):
        ordered_terms.append(q.strip())

    deduped_terms = []
    seen = set()
    for term in ordered_terms:
        normalized = normalize_text(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped_terms.append(term)
        if len(deduped_terms) >= 3:
            break

    return deduped_terms


async def fetch_candidate_books(search_terms: list[str], max_results: int = 40) -> list[BookResponse]:
    candidates: list[BookResponse] = []
    seen_ids: set[str] = set()
    per_term_limit = max(10, max_results // max(1, len(search_terms)))

    for term in search_terms:
        items = await fetch_google_books(f"subject:{term.strip()}", max_results=per_term_limit)
        parsed_books = [parse_book(item) for item in items]
        for book in parsed_books:
            if not book or book.id in seen_ids:
                continue
            seen_ids.add(book.id)
            candidates.append(book)
            if len(candidates) >= max_results:
                return candidates

    return candidates


def dedupe_books(books: list[BookResponse]) -> list[BookResponse]:
    deduped = []
    seen_ids: set[str] = set()

    for book in books:
        if book.id in seen_ids:
            continue
        seen_ids.add(book.id)
        deduped.append(book)

    return deduped


def split_same_author_books(
    books: list[BookResponse],
    author: Optional[str],
    reference: BookResponse,
) -> tuple[list[BookResponse], list[BookResponse]]:
    if not has_text(author):
        return [], books

    requested_author = normalize_text(author)
    same_author = []
    other_authors = []

    for book in books:
        if normalize_text(book.title) == normalize_text(reference.title):
            continue

        book_authors = {normalize_text(book_author) for book_author in book.authors}
        if requested_author in book_authors:
            same_author.append(book)
        else:
            other_authors.append(book)

    return same_author, other_authors


@app.get("/search", response_model=list[BookResponse])
async def search_books(
    q: str = Query(..., description="Titulo ou termo de busca"),
    max_results: int = Query(10, ge=1, le=40),
):
    items = await fetch_google_books(q, max_results)
    books = [parse_book(item) for item in items]
    return [book for book in books if book is not None]


@app.get("/recommend", response_model=RecommendationResponse)
async def recommend_books(
    q: Optional[str] = Query(None, description="Titulo de referencia para recomendacao"),
    author: Optional[str] = Query(None, description="Autor para priorizar obras relacionadas"),
    min_pages: Optional[int] = Query(None, ge=1),
    max_pages: Optional[int] = Query(None, ge=1),
    min_year: Optional[int] = Query(None, ge=1000, le=2100),
    max_year: Optional[int] = Query(None, ge=1000, le=2100),
    category: Optional[str] = Query(None, description="Genero/categoria desejada"),
    limit: int = Query(5, ge=1, le=20),
):
    if not has_text(q) and not has_text(author):
        raise HTTPException(
            status_code=422,
            detail="Informe pelo menos um titulo ou autor para recomendar livros",
        )

    author_books: list[BookResponse] = []
    if has_text(author):
        author_books = await fetch_books_by_author(author.strip(), q, max_results=20)

    reference: Optional[BookResponse] = author_books[0] if author_books else None

    if reference is None and has_text(q):
        reference_items = await fetch_google_books(q.strip(), max_results=5)
        if not reference_items:
            raise HTTPException(status_code=404, detail="Livro de referencia nao encontrado")

        reference = parse_book(reference_items[0])

    if not reference:
        raise HTTPException(
            status_code=404,
            detail="Nao foi possivel localizar uma obra de referencia",
        )

    enriched_subjects = await fetch_open_library_subjects(
        reference.title,
        reference.authors,
        reference.published_year,
    )
    if enriched_subjects:
        reference.categories = list(dict.fromkeys(reference.categories + enriched_subjects))

    search_terms = build_search_terms(q, reference, category, enriched_subjects)
    thematic_candidates = await fetch_candidate_books(search_terms, max_results=40)
    candidates = dedupe_books(author_books + thematic_candidates)

    filters = {
        "min_pages": min_pages,
        "max_pages": max_pages,
        "min_year": min_year,
        "max_year": max_year,
        "category": normalize_text(category),
        "exclude_title": reference.title,
    }
    filtered = filter_books(candidates, filters)
    same_author_books, other_author_books = split_same_author_books(filtered, author, reference)
    scored_same_author = score_books(same_author_books, reference)
    scored_other_authors = score_books(other_author_books, reference)
    scored = scored_same_author + scored_other_authors

    return RecommendationResponse(reference=reference, recommendations=scored[:limit])


def parse_book(item: dict) -> Optional[BookResponse]:
    try:
        info = item.get("volumeInfo", {})
        published = info.get("publishedDate", "")
        year = int(published[:4]) if published and len(published) >= 4 else None

        return BookResponse(
            id=item.get("id", ""),
            title=info.get("title", "Sem titulo"),
            authors=info.get("authors", []),
            categories=info.get("categories", []),
            page_count=info.get("pageCount"),
            published_year=year,
            description=info.get("description", "")[:300] if info.get("description") else "",
            thumbnail=info.get("imageLinks", {}).get("thumbnail"),
            language=info.get("language", ""),
        )
    except Exception:
        return None


@app.get("/health")
async def health():
    return {"status": "ok", "api_key_set": bool(API_KEY)}
