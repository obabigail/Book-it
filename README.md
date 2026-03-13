# Book Recommender — Backend

## Setup no Termux

```bash
# 1. dependências do sistema
pkg update && pkg install python git

# 2. dependências Python
pip install -r requirements.txt

# 3. chave da API (Google Cloud Console)
export GOOGLE_BOOKS_API_KEY="sua_chave_aqui"

# 4. rodar
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Sem chave de API o servidor ainda funciona — o Google Books aceita
requisições sem autenticação com limite menor (~100/dia por IP).

---

## Endpoints

### GET /search
Busca livros por título ou termo.

```
GET /search?q=1984&max_results=10
```

### GET /recommend
Recomenda livros similares com filtros opcionais.

```
GET /recommend?q=1984&min_pages=200&max_pages=400&min_year=1990&limit=5
GET /recommend?q=1984&category=Fiction&limit=5
```

### GET /health
Verifica se o servidor está rodando e se a chave de API está configurada.

---

## Documentação interativa

Com o servidor rodando, acesse no browser do celular:

```
http://localhost:8000/docs
```

O Swagger gerado pelo FastAPI permite testar todos os endpoints sem curl.

---

## Estrutura dos arquivos

```
book-recommender/
├── main.py         # rotas e lógica de fetch
├── models.py       # schemas Pydantic
├── filters.py      # filtragem e scoring de similaridade
└── requirements.txt
```

## Lógica de scoring

O endpoint `/recommend` pontua cada livro candidato por similaridade
com o livro de referência. Pesos atuais:

| Critério           | Peso |
|--------------------|------|
| Categoria em comum | 0.50 |
| Proximidade páginas| 0.30 |
| Proximidade de ano | 0.20 |

Os pesos podem ser ajustados em `filters.py` na função `score_books`.
