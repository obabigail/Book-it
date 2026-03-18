import asyncio
import json
import os
import re
import time
from collections import OrderedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
MIN_RECOMMENDATION_SCORE = float(os.getenv("BOOKIT_MIN_RECOMMENDATION_SCORE", "0.18"))
MAX_SEARCH_TERMS = int(os.getenv("BOOKIT_MAX_SEARCH_TERMS", "4"))
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


def upgrade_thumbnail_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None

    normalized = url.replace("http://", "https://")
    if "covers.openlibrary.org" in normalized:
        return normalized.replace("-S.jpg", "-L.jpg").replace("-M.jpg", "-L.jpg")

    parts = urlsplit(normalized)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.pop("edge", None)
    if "zoom" in query:
        query["zoom"] = "2"
    elif "books.google." in parts.netloc:
        query["zoom"] = "2"

    upgraded_query = urlencode(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, upgraded_query, parts.fragment))


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


async def fetch_google_book_by_id(volume_id: str) -> Optional[dict]:
    if not _google_books_available():
        raise GoogleBooksUnavailable("Google Books temporariamente indisponivel")

    params = {}
    if API_KEY:
        params["key"] = API_KEY

    cache_key = _cache_key("google_book_by_id", {"id": volume_id, "keyed": bool(API_KEY)})
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{GOOGLE_BOOKS_API}/{volume_id}", params=params)

    if response.status_code in (403, 429):
        _mark_google_unavailable()
        raise GoogleBooksUnavailable("Google Books quota excedida")
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Falha ao consultar Google Books por id")

    item = response.json()
    _cache_set(cache_key, item)
    return item


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
        thumbnail = upgrade_thumbnail_url(
            f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
        )
        subjects = doc.get("subject", []) or []
        language = ""
        if isinstance(doc.get("language"), list) and doc["language"]:
            language = doc["language"][0]

        return BookResponse(
            id=doc.get("key", ""),
            title=doc.get("title", "Sem titulo"),
            authors=doc.get("author_name", []) or [],
            categories=subjects[:6],
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


async def fetch_open_library_book_by_id(book_id: str) -> Optional[BookResponse]:
    params = {
        "q": book_id.strip(),
        "limit": 10,
        "fields": "key,title,author_name,first_publish_year,cover_i,subject,language,number_of_pages_median",
    }
    docs = await fetch_open_library_search(params)
    books = [parse_open_library_doc(doc) for doc in docs]
    normalized_id = normalize_text(book_id)
    for book in books:
        if book and normalize_text(book.id) == normalized_id:
            return book
    return None


async def fetch_open_library_books_by_subject(
    subject: str,
    author: Optional[str] = None,
    language: Optional[str] = None,
    max_results: int = 20,
) -> list[BookResponse]:
    params = {
        "subject": subject.strip(),
        "limit": max_results,
        "fields": "key,title,author_name,first_publish_year,cover_i,subject,language,number_of_pages_median",
    }
    if has_text(author):
        params["author"] = author.strip()
    if has_text(language):
        params["language"] = language.strip()

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


async def resolve_reference_book(reference_id: str) -> Optional[BookResponse]:
    if not has_text(reference_id):
        return None

    if reference_id.startswith("/works/") or reference_id.startswith("/books/"):
        return await fetch_open_library_book_by_id(reference_id)

    try:
        item = await fetch_google_book_by_id(reference_id)
    except GoogleBooksUnavailable:
        item = None

    if item:
        return parse_book(item)

    return await fetch_open_library_book_by_id(reference_id)


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

    ordered_terms.extend(select_specific_subjects(reference.categories, limit=4))

    deduped_terms = []
    seen = set()
    for term in ordered_terms:
        normalized = normalize_text(term)
        if not normalized or normalized in seen or normalized in GENERIC_SUBJECTS:
            continue
        seen.add(normalized)
        deduped_terms.append(term)
        if len(deduped_terms) >= MAX_SEARCH_TERMS:
            break

    return deduped_terms


async def fetch_candidate_books(
    search_terms: list[str],
    reference: Optional[BookResponse] = None,
    max_results: int = 40,
) -> list[BookResponse]:
    candidates: list[BookResponse] = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()
    per_term_limit = max(6, max_results // max(1, len(search_terms)))
    reference_author = reference.authors[0] if reference and reference.authors else None

    for term in search_terms:
        queries = []
        if has_text(reference_author):
            queries.append(f'subject:"{term.strip()}" inauthor:"{reference_author.strip()}"')
        queries.append(f'subject:"{term.strip()}"')

        items_batches = await asyncio.gather(
            *[fetch_google_books(query, max_results=per_term_limit) for query in queries]
        )
        for items in items_batches:
            parsed_books = [parse_book(item) for item in items]
            for book in parsed_books:
                if not book or book.id in seen_ids:
                    continue
                signature = normalize_book_signature(book)
                if signature in seen_signatures:
                    continue
                seen_ids.add(book.id)
                seen_signatures.add(signature)
                candidates.append(book)
                if len(candidates) >= max_results:
                    return candidates

    # fallback: se candidatos insuficientes e temos autor de referencia,
    # busca por inauthor — garante resultados mesmo sem categories/subjects
    if len(candidates) < 5 and reference and reference.authors:
        author = reference.authors[0]
        items = await fetch_google_books(f'inauthor:"{author}"', max_results=20)
        for item in items:
            book = parse_book(item)
            if not book or book.id in seen_ids:
                continue
            signature = normalize_book_signature(book)
            if signature in seen_signatures:
                continue
            seen_ids.add(book.id)
            seen_signatures.add(signature)
            candidates.append(book)

    return candidates


async def fetch_open_library_candidates(
    search_terms: list[str],
    reference: Optional[BookResponse] = None,
    max_results: int = 40,
) -> list[BookResponse]:
    candidates: list[BookResponse] = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()
    per_term_limit = max(6, max_results // max(1, len(search_terms)))
    reference_author = reference.authors[0] if reference and reference.authors else None
    reference_language = reference.language if reference else None

    for term in search_terms:
        batches = await asyncio.gather(
            fetch_open_library_books_by_subject(
                term.strip(),
                author=reference_author,
                language=reference_language,
                max_results=per_term_limit,
            ),
            fetch_open_library_books_by_subject(
                term.strip(),
                language=reference_language,
                max_results=per_term_limit,
            ),
        )

        for books in batches:
            for book in books:
                if not book or book.id in seen_ids:
                    continue
                signature = normalize_book_signature(book)
                if signature in seen_signatures:
                    continue
                seen_ids.add(book.id)
                seen_signatures.add(signature)
                candidates.append(book)
                if len(candidates) >= max_results:
                    return candidates

    if len(candidates) < 5 and reference and reference.authors:
        fallback_books = await fetch_open_library_books_by_author(
            reference.authors[0],
            max_results=min(20, max_results),
        )
        for book in fallback_books:
            if not book or book.id in seen_ids:
                continue
            signature = normalize_book_signature(book)
            if signature in seen_signatures:
                continue
            seen_ids.add(book.id)
            seen_signatures.add(signature)
            candidates.append(book)
            if len(candidates) >= max_results:
                return candidates

    return candidates


def dedupe_books(books: list[BookResponse]) -> list[BookResponse]:
    deduped = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()

    for book in books:
        signature = normalize_book_signature(book)
        if book.id in seen_ids or signature in seen_signatures:
            continue
        seen_ids.add(book.id)
        seen_signatures.add(signature)
        deduped.append(book)

    return deduped


def _author_match_score(authors: list[str], author_query: Optional[str]) -> float:
    if not has_text(author_query):
        return 0.0

    normalized_query = normalize_text(author_query)
    normalized_authors = {normalize_text(author) for author in authors}
    if normalized_query in normalized_authors:
        return 1.0
    if any(normalized_query in author or author in normalized_query for author in normalized_authors):
        return 0.6
    return 0.0


def _search_result_score(item: dict, title_query: str, author_query: Optional[str] = None) -> float:
    info = item.get("volumeInfo", {})
    score = _reference_score(item, title_query)

    authors = info.get("authors", []) or []
    score += _author_match_score(authors, author_query) * 4.0

    ratings_count = info.get("ratingsCount") or 0
    if ratings_count:
        score += min(3.0, ratings_count / 500)

    categories = [normalize_text(category) for category in info.get("categories", []) or []]
    if any(category not in GENERIC_SUBJECTS for category in categories):
        score += 1.0

    return score


def _open_library_search_score(book: BookResponse, title_query: str, author_query: Optional[str] = None) -> float:
    score = _title_similarity(book.title, title_query) * 8.0
    score += _author_match_score(book.authors, author_query) * 4.0
    if book.thumbnail:
        score += 1.0
    if book.categories and any(normalize_text(category) not in GENERIC_SUBJECTS for category in book.categories):
        score += 1.0
    if book.published_year:
        score += 0.5
    return score

@app.get("/")
async def root():
    return {"service": "Book Recommender API"}

@app.get("/search", response_model=list[BookResponse])
async def search_books(
    q: str = Query(..., description="Titulo ou termo de busca"),
    author: Optional[str] = Query(None, description="Autor opcional para refinar a referencia"),
    max_results: int = Query(10, ge=1, le=40),
):
    try:
        queries = [f'intitle:"{q.strip()}"']
        if has_text(author):
            queries.insert(0, f'intitle:"{q.strip()}" inauthor:"{author.strip()}"')
            queries.append(f'{q.strip()} inauthor:"{author.strip()}"')
        queries.append(q.strip())

        batches = await asyncio.gather(*[fetch_google_books(query, max_results=max_results) for query in queries])
        seen_ids: set[str] = set()
        ranked_items: list[dict] = []
        for items in batches:
            for item in items:
                item_id = item.get("id")
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                ranked_items.append(item)

        ranked_items.sort(
            key=lambda item: _search_result_score(item, q.strip(), author),
            reverse=True,
        )
        books = [parse_book(item) for item in ranked_items[:max_results]]
        return [book for book in books if book is not None]
    except GoogleBooksUnavailable:
        query = f"{q.strip()} {author.strip()}" if has_text(author) else q.strip()
        books = await fetch_open_library_books_by_query(query, max_results=max_results)
        books.sort(
            key=lambda book: _open_library_search_score(book, q.strip(), author),
            reverse=True,
        )
        return books[:max_results]


@app.get("/recommend", response_model=RecommendationResponse)
async def recommend_books(
    q: Optional[str] = Query(None, description="Titulo de referencia para recomendacao"),
    author: Optional[str] = Query(None, description="Autor para priorizar obras relacionadas"),
    reference_id: Optional[str] = Query(None, description="Id explicito da obra-base selecionada"),
    min_pages: Optional[int] = Query(None, ge=1),
    max_pages: Optional[int] = Query(None, ge=1),
    min_year: Optional[int] = Query(None, ge=1000, le=2100),
    max_year: Optional[int] = Query(None, ge=1000, le=2100),
    category: Optional[str] = Query(None, description="Genero/categoria desejada"),
    limit: int = Query(5, ge=1, le=20),
):
    if not has_text(q) and not has_text(author) and not has_text(reference_id):
        raise HTTPException(
            status_code=422,
            detail="Informe pelo menos um titulo ou autor para recomendar livros",
        )

    google_available = True
    author_books: list[BookResponse] = []
    if has_text(author) and not has_text(reference_id):
        try:
            author_books = await fetch_books_by_author(author.strip(), q, max_results=20)
        except GoogleBooksUnavailable:
            google_available = False
            author_books = await fetch_open_library_books_by_author(author.strip(), q, max_results=20)

    reference: Optional[BookResponse] = None
    if has_text(reference_id):
        reference = await resolve_reference_book(reference_id.strip())

    if reference is None:
        reference = author_books[0] if author_books else None

    if reference is None and has_text(q):
        if google_available:
            try:
                reference = await pick_best_reference(q.strip())
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
            thematic_candidates = await fetch_candidate_books(search_terms, reference=reference, max_results=40)
        except GoogleBooksUnavailable:
            google_available = False
            thematic_candidates = await fetch_open_library_candidates(search_terms, reference=reference, max_results=40)
    else:
        thematic_candidates = await fetch_open_library_candidates(search_terms, reference=reference, max_results=40)
    candidates = dedupe_books(author_books + thematic_candidates)
    reference_signature = normalize_book_signature(reference)
    candidates = [book for book in candidates if normalize_book_signature(book) != reference_signature]

    filters = {
        "min_pages": min_pages,
        "max_pages": max_pages,
        "min_year": min_year,
        "max_year": max_year,
        "category": normalize_text(category),
        "exclude_title": reference.title,
    }
    filtered = filter_books(candidates, filters)
    scored = score_books(filtered, reference)
    scored = [book for book in scored if book.score >= MIN_RECOMMENDATION_SCORE]

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
            thumbnail=upgrade_thumbnail_url(info.get("imageLinks", {}).get("thumbnail")),
            language=info.get("language", ""),
        )
    except Exception:
        return None


def _title_similarity(a: str, b: str) -> float:
    """
    Retorna score de similaridade entre dois titulos normalizados (0.0 a 1.0).
    Usa Jaccard sobre tokens para lidar com traducoes parciais e abreviacoes.
    Exemplos:
      "duna" vs "dune"                           -> 0.0  (tokens diferentes)
      "1984" vs "nineteen eighty-four"           -> 0.0  (sem token comum)
      "do androids dream" vs "androids dream"    -> 0.67 (2/3 tokens em comum)
    """
    tokens_a = set(normalize_text(a).split())
    tokens_b = set(normalize_text(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _reference_score(item: dict, query: str) -> float:
    """
    Pontua um candidato a livro de referencia.

    Criterios:
    - Titulo exato                    : +10.0
    - Similaridade de tokens (Jaccard): +0 a +6.0
    - Tem description preenchida      : +3.0  (proxy de obra relevante)
    - Tem pageCount                   : +2.0
    - Tem thumbnail                   : +1.0
    - averageRating da API            : +0 a +1.0 (normalizado por 5.0)
    - ratingsCount deliberadamente EXCLUIDO — enviesado por docs governamentais
    """
    info   = item.get("volumeInfo", {})
    title  = info.get("title", "")
    q_norm = normalize_text(query)
    score  = 0.0

    if normalize_text(title) == q_norm:
        score += 10.0
    else:
        sim = _title_similarity(title, query)
        score += sim * 6.0

    if info.get("description"):
        score += 3.0
    if info.get("pageCount"):
        score += 2.0
    if info.get("imageLinks", {}).get("thumbnail"):
        score += 1.0

    avg_rating = info.get("averageRating")
    if avg_rating:
        score += (avg_rating / 5.0)

    return score


async def pick_best_reference(query: str) -> Optional[BookResponse]:
    """
    Busca o livro de referencia usando duas estrategias complementares:

    1. intitle:"query" — restringe a API a titulos que contenham o termo exato,
       reduzindo drasticamente falsos positivos como documentos governamentais
       ou periodicos academicos.
    2. query livre — fallback caso intitle nao retorne resultados uteis.

    Dentre todos os candidatos coletados, escolhe o melhor pelo _reference_score,
    que prioriza correspondencia de titulo e presenca de metadados (description,
    pageCount), sem usar ratingsCount que e enviesado.
    """
    all_items: list[dict] = []

    # estrategia 1: intitle restringe bem
    try:
        intitle_items = await fetch_google_books(f'intitle:"{query.strip()}"', max_results=10)
        all_items.extend(intitle_items)
    except GoogleBooksUnavailable:
        pass

    # estrategia 2: busca livre como complemento
    try:
        free_items = await fetch_google_books(query.strip(), max_results=10)
        seen_ids = {item.get("id") for item in all_items}
        all_items.extend(item for item in free_items if item.get("id") not in seen_ids)
    except GoogleBooksUnavailable:
        pass

    if not all_items:
        return None

    ranked = sorted(all_items, key=lambda item: _reference_score(item, query), reverse=True)
    return parse_book(ranked[0])


@app.get("/health")
async def health():
    return {"status": "ok", "api_key_set": bool(API_KEY)}
