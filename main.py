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
API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")


def normalize_text(value: Optional[str]) -> str:
    return value.casefold().strip() if value else ""


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
    q: str = Query(..., description="Titulo de referencia para recomendacao"),
    min_pages: Optional[int] = Query(None, ge=1),
    max_pages: Optional[int] = Query(None, ge=1),
    min_year: Optional[int] = Query(None, ge=1000, le=2100),
    max_year: Optional[int] = Query(None, ge=1000, le=2100),
    category: Optional[str] = Query(None, description="Genero/categoria desejada"),
    limit: int = Query(5, ge=1, le=20),
):
    reference_items = await fetch_google_books(q, max_results=5)
    if not reference_items:
        raise HTTPException(status_code=404, detail="Livro de referencia nao encontrado")

    reference = parse_book(reference_items[0])
    if not reference:
        raise HTTPException(
            status_code=404,
            detail="Nao foi possivel extrair dados do livro",
        )

    search_category = (category or (reference.categories[0] if reference.categories else q)).strip()
    candidates_items = await fetch_google_books(f"subject:{search_category}", max_results=40)
    candidates = [parse_book(item) for item in candidates_items]
    candidates = [book for book in candidates if book is not None]

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
