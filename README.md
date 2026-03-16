# Book-it

Aplicacao de recomendacao de livros com:

- backend em `FastAPI`
- interface web em `Streamlit`
- busca em `Google Books` com fallback para `Open Library`

O fluxo atual do app foi desenhado para reduzir ambiguidades:

1. o usuario pesquisa um titulo
2. o app mostra sugestoes de obras-base
3. a obra correta e selecionada visualmente
4. a recomendacao usa o `id` da obra escolhida
5. resultados repetidos por edicoes muito parecidas sao deduplicados

## Principais recursos

- selecao guiada da obra-base antes de recomendar similares
- ordenacao de sugestoes para priorizar versoes mais conhecidas em buscas vagas como `1984` e `Duna`
- busca de recomendacoes com filtros por genero, paginas, ano e limite
- score de similaridade com titulo, categorias, autor, idioma, descricao, paginas e ano
- deduplicacao de edicoes parecidas no ranking final
- fallback para Open Library quando Google Books estiver indisponivel

## Requisitos

- Python 3.10+

Dependencias atuais em [`requirements.txt`](C:\Users\riquelmy.fernandes\Downloads\Book-it\requirements.txt):

- `fastapi`
- `uvicorn`
- `httpx`
- `pydantic`
- `streamlit`

## Instalacao

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Variaveis de ambiente

Opcional:

- `GOOGLE_BOOKS_API_KEY`

Ajustes uteis:

- `BOOKIT_BASE_URL`
  URL do backend usada pelo Streamlit.
  Padrao: `http://localhost:8000`
- `BOOKIT_REQUEST_TIMEOUT_SECONDS`
  Timeout do frontend ao chamar o backend.
  Padrao: `30`
- `BOOKIT_CACHE_TTL_SECONDS`
  TTL do cache em memoria no backend.
  Padrao: `21600`
- `BOOKIT_CACHE_MAX_ITEMS`
  Quantidade maxima de itens em cache.
  Padrao: `512`
- `BOOKIT_GOOGLE_COOLDOWN_SECONDS`
  Janela de cooldown quando Google Books devolve quota excedida.
  Padrao: `900`
- `BOOKIT_MIN_RECOMMENDATION_SCORE`
  Score minimo para um livro entrar nas recomendacoes.
  Padrao: `0.18`
- `BOOKIT_MAX_SEARCH_TERMS`
  Quantidade maxima de termos tematicos usados na busca de candidatos.
  Padrao: `4`

Sem chave de API o servidor ainda funciona, mas o limite do Google Books tende a ser menor.

## Como rodar

Suba o backend:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Em outro terminal, suba o web app:

```bash
streamlit run cli.py
```

## Fluxo do web app

1. preencher `Titulo do livro` e opcionalmente `Autor`
2. clicar em `Encontrar obra-base`
3. escolher uma capa na estante de referencias
4. clicar em `Buscar recomendacoes com esta obra`
5. revisar a obra-base confirmada e os livros recomendados

Se o usuario informar apenas autor, o app ainda permite partir diretamente desse autor.

## Endpoints

### `GET /`

Health simples do servico.

### `GET /search`

Busca sugestoes de obras-base para a etapa guiada.

Parametros:

- `q`: titulo ou termo principal
- `author`: autor opcional para refinar
- `max_results`: quantidade maxima de sugestoes

Exemplo:

```text
GET /search?q=1984&author=George Orwell&max_results=8
```

### `GET /recommend`

Retorna recomendacoes similares.

Parametros principais:

- `reference_id`: id explicito da obra-base selecionada
- `q`: titulo de apoio
- `author`: autor de apoio
- `category`
- `min_pages`
- `max_pages`
- `min_year`
- `max_year`
- `limit`

Exemplos:

```text
GET /recommend?reference_id=zyTCAlFPjgYC&limit=5
GET /recommend?reference_id=zyTCAlFPjgYC&category=Science%20Fiction&limit=8
GET /recommend?q=1984&author=George%20Orwell&limit=5
```

### `GET /health`

Retorna status basico da API e informa se a chave do Google Books esta configurada.

## Estrutura do projeto

```text
Book-it/
|- main.py          # backend FastAPI e logica de busca/recomendacao
|- cli.py           # interface Streamlit
|- filters.py       # filtros e score de similaridade
|- models.py        # modelos Pydantic
|- requirements.txt
|- assets/
```

## Como a recomendacao funciona hoje

De forma resumida:

1. resolve a obra-base a partir do `reference_id` selecionado ou por busca assistida
2. enriquece subjects/categorias da referencia
3. busca candidatos tematicos em Google Books ou Open Library
4. remove duplicatas e edicoes muito parecidas
5. aplica filtros do usuario
6. calcula score de similaridade
7. devolve apenas livros acima do score minimo

Sinais usados no score:

- categorias em comum
- mesmo autor
- proximidade de paginas
- proximidade de ano
- idioma
- similaridade de titulo
- overlap de keywords da descricao
- especificidade das categorias

## Observacoes

- a selecao guiada melhora bastante consultas vagas, mas ainda depende da qualidade dos metadados das APIs externas
- ids do Google Books tendem a ser resolvidos com mais precisao do que ids do Open Library
- recomendacoes podem variar conforme disponibilidade e metadata retornada pelas APIs externas
