import json
import os
import time
from collections import OrderedDict
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
CACHE_TTL_SECONDS = int(os.getenv("BOOKIT_CACHE_TTL_SECONDS", "21600"))
CACHE_MAX_ITEMS = int(os.getenv("BOOKIT_CACHE_MAX_ITEMS", "512"))
GOOGLE_COOLDOWN_SECONDS = int(os.getenv("BOOKIT_GOOGLE_COOLDOWN_SECONDS", "900"))
GENERIC_SUBJECTS = {
    "fiction",
    "ficcao",
    "general",
    "literature",
    "novel",
    "book",
    "books",
}


class GoogleBooksUnavailable(Exception):
    pass


_google_unavailable_until = 0.0
_CACHE: "OrderedDict[str, tuple[float, object]]" = OrderedDict()


def _cache_get(key: str):
    if CACHE_TTL_SECONDS <= 0:
        return None

    entry = _CACHE.get(key)
    if not entry:
        return None

    timestamp, value = entry
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None

    _CACHE.move_to_end(key)
    return value


def _cache_set(key: str, value: object) -> None:
    if CACHE_TTL_SECONDS <= 0:
        return

    _CACHE[key] = (time.time(), value)
    _CACHE.move_to_end(key)

    if CACHE_MAX_ITEMS <= 0:
        return

    while len(_CACHE) > CACHE_MAX_ITEMS:
        _CACHE.popitem(last=False)


def _cache_key(prefix: str, params: dict) -> str:
    return f"{prefix}:{json.dumps(params, sort_keys=True, separators=(',', ':'))}"


def _google_books_available() -> bool:
    return time.time() >= _google_unavailable_until


def _mark_google_unavailable() -> None:
    global _google_unavailable_until
    _google_unavailable_until = time.time() + GOOGLE_COOLDOWN_SECONDS


def normalize_text(value: Optional[str]) -> str:
    return value.casefold().strip() if value else ""


def has_text(value: Optional[str]) -> bool:
    return bool(value and value.strip())


async def fetch_google_books(query: str, max_results: int = 20) -> list[dict]:
    if not _google_books_available():
        raise GoogleBooksUnavailable("Google Books temporariamente indisponivel")

    params = {
        "q": query,
        "maxResults": max_results,
        "printType": "books",
    }
    if API_KEY:
        params["key"] = API_KEY

    cache_key = _cache_key("google_books", {"q": query, "max": max_results, "keyed": bool(API_KEY)})
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GOOGLE_BOOKS_API, params=params)

    if response.status_code in (403, 429):
        _mark_google_unavailable()
        raise GoogleBooksUnavailable("Google Books quota excedida")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Falha ao contatar Google Books API")

    data = response.json()
    items = data.get("items", [])
    _cache_set(cache_key, items)
    return items


async def fetch_open_library_search(params: dict) -> list[dict]:
    cache_key = _cache_key("open_library_search", params)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    headers = {"User-Agent": "BookRecomendations/0.1 (Open Library search)"}
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        response = await client.get(OPEN_LIBRARY_SEARCH_API, params=params)
        response.raise_for_status()

    docs = response.json().get("docs", [])
    _cache_set(cache_key, docs)
    return docs


def parse_open_library_doc(doc: dict) -> Optional[BookResponse]:
    try:
        cover_id = doc.get("cover_i")
        thumbnail = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None
        subjects = doc.get("subject", []) or []
        language = ""
        if isinstance(doc.get("language"), list) and doc["language"]:
            language = doc["language"][0]

        return BookResponse(
            id=doc.get("key", ""),
            title=doc.get("title", "Sem titulo"),
            authors=doc.get("author_name", []) or [],
            categories=subjects[:3],
            page_count=doc.get("number_of_pages_median"),
            published_year=doc.get("first_publish_year"),
            description="",
            thumbnail=thumbnail,
            language=language,
        )
    except Exception:
        return None


async def fetch_open_library_books_by_author(
    author: str,
    title: Optional[str] = None,
    max_results: int = 20,
) -> list[BookResponse]:
    params = {
        "author": author.strip(),
        "limit": max_results,
        "fields": "key,title,author_name,first_publish_year,cover_i,subject,language,number_of_pages_median",
    }
    if has_text(title):
        params["title"] = title.strip()

    docs = await fetch_open_library_search(params)
    books = [parse_open_library_doc(doc) for doc in docs]
    return [book for book in books if book is not None]


async def fetch_open_library_books_by_query(query: str, max_results: int = 20) -> list[BookResponse]:
    params = {
        "q": query.strip(),
        "limit": max_results,
        "fields": "key,title,author_name,first_publish_year,cover_i,subject,language,number_of_pages_median",
    }
    docs = await fetch_open_library_search(params)
    books = [parse_open_library_doc(doc) for doc in docs]
    return [book for book in books if book is not None]


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
        docs = await fetch_open_library_search(params)
        work_key = choose_open_library_work(docs, title, authors, published_year)
        if not work_key:
            return []

        work_cache_key = _cache_key("open_library_work", {"key": work_key})
        cached = _cache_get(work_cache_key)
        if cached is not None:
            return select_specific_subjects(cached.get("subjects", []))

        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            work_response = await client.get(f"https://openlibrary.org{work_key}.json")
            work_response.raise_for_status()
            work_data = work_response.json()
            _cache_set(work_cache_key, work_data)
    except httpx.HTTPError:
        return []

    return select_specific_subjects(work_data.get("subjects", []))


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


async def fetch_open_library_candidates(search_terms: list[str], max_results: int = 40) -> list[BookResponse]:
    candidates: list[BookResponse] = []
    seen_ids: set[str] = set()
    per_term_limit = max(10, max_results // max(1, len(search_terms)))

    for term in search_terms:
        books = await fetch_open_library_books_by_query(term.strip(), max_results=per_term_limit)
        for book in books:
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

@app.get("/")
async def root():
    return {"service": "Book Recommender API"}

@app.get("/search", response_model=list[BookResponse])
async def search_books(
    q: str = Query(..., description="Titulo ou termo de busca"),
    max_results: int = Query(10, ge=1, le=40),
):
    try:
        items = await fetch_google_books(q, max_results)
        books = [parse_book(item) for item in items]
        return [book for book in books if book is not None]
    except GoogleBooksUnavailable:
        books = await fetch_open_library_books_by_query(q, max_results=max_results)
        return books


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

    google_available = True
    author_books: list[BookResponse] = []
    if has_text(author):
        try:
            author_books = await fetch_books_by_author(author.strip(), q, max_results=20)
        except GoogleBooksUnavailable:
            google_available = False
            author_books = await fetch_open_library_books_by_author(author.strip(), q, max_results=20)

    reference: Optional[BookResponse] = author_books[0] if author_books else None

    if reference is None and has_text(q):
        if google_available:
            try:
                reference_items = await fetch_google_books(q.strip(), max_results=5)
                if reference_items:
                    reference = parse_book(reference_items[0])
            except GoogleBooksUnavailable:
                google_available = False

        if reference is None:
            reference_candidates = await fetch_open_library_books_by_query(q.strip(), max_results=5)
            reference = reference_candidates[0] if reference_candidates else None

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
    if google_available:
        try:
            thematic_candidates = await fetch_candidate_books(search_terms, max_results=40)
        except GoogleBooksUnavailable:
            google_available = False
            thematic_candidates = await fetch_open_library_candidates(search_terms, max_results=40)
    else:
        thematic_candidates = await fetch_open_library_candidates(search_terms, max_results=40)
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
