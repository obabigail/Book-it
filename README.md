# Book-it

Aplicação de recomendação de livros com:

- backend em `FastAPI`
- interface web em `Streamlit`
- busca em `Google Books` com fallback para `Open Library`

O fluxo atual do app foi desenhado para reduzir ambiguidades:

1. o usuário pesquisa um título
2. o app mostra sugestões de obras-base
3. a obra correta é selecionada visualmente
4. a recomendação usa o `id` da obra escolhida
5. resultados repetidos por edições muito parecidas são deduplicados

## Principais recursos

- seleção guiada da obra-base antes de recomendar similares
- ordenação de sugestões para priorizar versões mais conhecidas em buscas vagas como `1984` e `Duna`
- busca de recomendações com filtros por gênero, páginas, ano e limite
- score de similaridade com título, categorias, autor, idioma, descrição, páginas e ano
- deduplicação de edições parecidas no ranking final
- fallback para Open Library quando Google Books estiver indisponível

## Requisitos

- Python 3.10+

Dependências atuais em [`requirements.txt`](.\requirements.txt):

- `fastapi`
- `uvicorn`
- `httpx`
- `pydantic`
- `streamlit`

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Variáveis de ambiente

Opcional:

- `GOOGLE_BOOKS_API_KEY`

Ajustes úteis:

- `BOOKIT_BASE_URL`
  URL do backend usada pelo Streamlit.
  Padrão: `http://localhost:8000`
- `BOOKIT_REQUEST_TIMEOUT_SECONDS`
  Timeout do frontend ao chamar o backend.
  Padrão: `30`
- `BOOKIT_CACHE_TTL_SECONDS`
  TTL do cache em memória no backend.
  Padrão: `21600`
- `BOOKIT_CACHE_MAX_ITEMS`
  Quantidade máxima de itens em cache.
  Padrão: `512`
- `BOOKIT_GOOGLE_COOLDOWN_SECONDS`
  Janela de cooldown quando Google Books devolve quota excedida.
  Padrão: `900`
- `BOOKIT_MIN_RECOMMENDATION_SCORE`
  Score mínimo para um livro entrar nas recomendações.
  Padrão: `0.18`
- `BOOKIT_MAX_SEARCH_TERMS`
  Quantidade máxima de termos temáticos usados na busca de candidatos.
  Padrão: `4`

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

1. preencher `Título do livro` e opcionalmente `Autor`
2. clicar em `Encontrar obra-base`
3. escolher uma capa na estante de referências
4. clicar em `Buscar recomendações com esta obra`
5. revisar a obra-base confirmada e os livros recomendados

Se o usuário informar apenas autor, o app ainda permite partir diretamente desse autor.

## Endpoints

### `GET /`

Health simples do serviço.

### `GET /search`

Busca sugestões de obras-base para a etapa guiada.

Parâmetros:

- `q`: título ou termo principal
- `author`: autor opcional para refinar
- `max_results`: quantidade máxima de sugestões

Exemplo:

```text
GET /search?q=1984&author=George Orwell&max_results=8
```

### `GET /recommend`

Retorna recomendações similares.

Parâmetros principais:

- `reference_id`: id explícito da obra-base selecionada
- `q`: título de apoio
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

Retorna status básico da API e informa se a chave do Google Books está configurada.

## Estrutura do projeto

```text
Book-it/
|- main.py          # backend FastAPI e lógica de busca/recomendação
|- cli.py           # interface Streamlit
|- filters.py       # filtros e score de similaridade
|- models.py        # modelos Pydantic
|- requirements.txt
|- assets/
```

## Como a recomendação funciona hoje

De forma resumida:

1. resolve a obra-base a partir do `reference_id` selecionado ou por busca assistida
2. enriquece subjects/categorias da referência
3. busca candidatos temáticos em Google Books ou Open Library
4. remove duplicatas e edições muito parecidas
5. aplica filtros do usuário
6. calcula score de similaridade
7. devolve apenas livros acima do score mínimo

Sinais usados no score:

- categorias em comum
- mesmo autor
- proximidade de páginas
- proximidade de ano
- idioma
- similaridade de título
- overlap de keywords da descrição
- especificidade das categorias

## Observações

- a seleção guiada melhora bastante consultas vagas, mas ainda depende da qualidade dos metadados das APIs externas
- ids do Google Books tendem a ser resolvidos com mais precisão do que ids do Open Library
- recomendações podem variar conforme disponibilidade e metadados retornados pelas APIs externas
