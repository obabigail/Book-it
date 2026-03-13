import httpx
import streamlit as st

BASE_URL = "http://localhost:8000"
COMMON_GENRES = [
    "",
    "Fiction",
    "Fantasy",
    "Science Fiction",
    "Romance",
    "Mystery",
    "Thriller",
    "Horror",
    "Young Adult",
    "Historical Fiction",
    "Biography",
    "History",
    "Philosophy",
    "Self-Help",
    "Business",
    "Psychology",
    "Poetry",
]


def normalize_optional_number(value: int) -> int | None:
    return value if value > 0 else None


def get_recommendations(title: str, filters: dict) -> dict | None:
    params = {"q": title, **filters}
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(f"{BASE_URL}/recommend", params=params)
    except httpx.ConnectError:
        st.error(
            f"Nao foi possivel conectar ao backend em `{BASE_URL}`. "
            "Verifique se o FastAPI esta em execucao."
        )
        return None

    if response.status_code == 404:
        st.warning("Livro de referencia nao encontrado na Google Books API.")
        return None

    if response.status_code != 200:
        st.error(f"Erro da API ({response.status_code}): {response.text}")
        return None

    return response.json()


def render_book_card(book: dict, show_score: bool = False) -> None:
    col_image, col_content = st.columns([1, 3], gap="medium")

    with col_image:
        if book.get("thumbnail"):
            st.image(book["thumbnail"], use_container_width=True)
        else:
            st.caption("Sem capa")

    with col_content:
        st.subheader(book["title"])
        authors = ", ".join(book.get("authors", [])) or "Desconhecido"
        categories = ", ".join(book.get("categories", [])) or "N/A"
        st.write(f"**Autor(es):** {authors}")
        st.write(f"**Genero(s):** {categories}")
        st.write(f"**Paginas:** {book.get('page_count') or 'N/A'}")
        st.write(f"**Ano:** {book.get('published_year') or 'N/A'}")
        if show_score:
            st.write(f"**Score:** {book['score']:.2f}")
        if book.get("description"):
            st.write(book["description"])


def build_filters() -> dict:
    with st.sidebar:
        st.header("Filtros")
        st.caption("Use 0 para ignorar um filtro numerico.")

        min_pages = st.number_input(
            "Paginas minimas",
            min_value=0,
            value=0,
            step=10,
            help="Aceita digitacao manual e setas em incrementos de 10.",
        )
        max_pages = st.number_input(
            "Paginas maximas",
            min_value=0,
            value=0,
            step=10,
            help="Aceita digitacao manual e setas em incrementos de 10.",
        )
        min_year = st.number_input(
            "Ano minimo",
            min_value=0,
            value=0,
            step=10,
            help="Aceita digitacao manual e setas em incrementos de 10 anos.",
        )
        max_year = st.number_input(
            "Ano maximo",
            min_value=0,
            value=0,
            step=10,
            help="Aceita digitacao manual e setas em incrementos de 10 anos.",
        )

        selected_genre = st.selectbox(
            "Genero sugerido",
            options=COMMON_GENRES,
            index=0,
            help="O dropdown permite localizar opcoes digitando.",
        )
        custom_genre = st.text_input(
            "Ou digite um genero",
            placeholder="Ex.: fantasy, romance, historia",
            help="Se preenchido, este valor tem prioridade sobre o dropdown.",
        )

        limit = st.number_input(
            "Quantidade de recomendacoes",
            min_value=1,
            max_value=20,
            value=5,
            step=1,
        )

    genre = custom_genre.strip() or selected_genre.strip()

    return {
        "min_pages": normalize_optional_number(min_pages),
        "max_pages": normalize_optional_number(max_pages),
        "min_year": normalize_optional_number(min_year),
        "max_year": normalize_optional_number(max_year),
        "category": genre or None,
        "limit": int(limit),
    }


def main() -> None:
    st.set_page_config(
        page_title="Book Recomendations",
        page_icon=":books:",
        layout="wide",
    )

    st.title("Book Recomendations")
    st.write(
        "Busque um livro de referencia e receba sugestoes similares com filtros "
        "de paginas, ano e genero."
    )

    filters = build_filters()

    with st.form("book-search-form"):
        title = st.text_input(
            "Nome do livro",
            placeholder="Ex.: Duna, 1984, O Hobbit",
        )
        submitted = st.form_submit_button("Buscar recomendacoes", use_container_width=True)

    if not submitted:
        st.info("Preencha o titulo do livro e clique em buscar.")
        return

    if not title.strip():
        st.warning("Informe um titulo para continuar.")
        return

    with st.spinner("Buscando recomendacoes..."):
        data = get_recommendations(title.strip(), filters)

    if not data:
        return

    reference = data["reference"]
    recommendations = data["recommendations"]

    st.divider()
    st.header("Livro de referencia")
    render_book_card(reference)

    st.divider()
    st.header(f"Recomendacoes encontradas: {len(recommendations)}")

    if not recommendations:
        st.info("Nenhum resultado encontrado com os filtros aplicados.")
        return

    for index, book in enumerate(recommendations, start=1):
        with st.container():
            st.markdown(f"### {index}.")
            render_book_card(book, show_score=True)
            st.divider()


if __name__ == "__main__":
    main()
