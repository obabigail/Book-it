from pydantic import BaseModel
from typing import Optional


class BookResponse(BaseModel):
    id: str
    title: str
    authors: list[str]
    categories: list[str]
    page_count: Optional[int]
    published_year: Optional[int]
    description: str
    thumbnail: Optional[str]
    language: str


class ScoredBook(BookResponse):
    score: float  # 0.0 a 1.0 — similaridade com o livro de referência


class RecommendationResponse(BaseModel):
    reference: BookResponse
    recommendations: list[ScoredBook]
