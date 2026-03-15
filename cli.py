import os

import httpx
import streamlit as st

BASE_URL = os.getenv("BOOKIT_BASE_URL", "http://localhost:8000")
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


def apply_page_styles() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(194, 154, 108, 0.10), transparent 34%),
                    radial-gradient(circle at top right, rgba(108, 128, 109, 0.10), transparent 28%);
            }

            .hero-block {
                margin: 0.4rem 0 1rem 0;
                padding: 1.2rem 1.25rem;
                border-radius: 22px;
                background: linear-gradient(135deg, rgba(94, 74, 58, 0.94), rgba(38, 54, 44, 0.92));
                border: 1px solid rgba(201, 166, 126, 0.28);
                box-shadow: 0 18px 50px rgba(35, 28, 24, 0.18);
                color: #f6f0e7;
            }

            .hero-kicker {
                display: inline-block;
                padding: 0.24rem 0.62rem;
                border-radius: 999px;
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                background: rgba(230, 204, 170, 0.16);
                color: #f3ddbf;
                margin-bottom: 0.75rem;
            }

            .hero-title {
                font-size: 2rem;
                line-height: 1.1;
                font-weight: 700;
                margin-bottom: 0.4rem;
            }

            .hero-copy {
                font-size: 1rem;
                line-height: 1.6;
                max-width: 900px;
                color: rgba(246, 240, 231, 0.88);
            }

            .chip-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 0.8rem;
                margin: 1rem 0 1.1rem 0;
            }

            .chip-card {
                padding: 0.95rem 1rem;
                border-radius: 18px;
                border: 1px solid rgba(126, 99, 76, 0.18);
                background: linear-gradient(180deg, rgba(255, 250, 244, 0.82), rgba(247, 239, 228, 0.70));
                backdrop-filter: blur(6px);
            }

            .chip-card strong {
                display: block;
                font-size: 0.95rem;
                margin-bottom: 0.18rem;
                color: #4f3f34;
            }

            .chip-card span {
                color: rgba(79, 63, 52, 0.82);
                font-size: 0.92rem;
            }

            .section-card {
                padding: 1.05rem 1.1rem 1.15rem 1.1rem;
                border-radius: 20px;
                border: 1px solid rgba(126, 99, 76, 0.16);
                background: linear-gradient(180deg, rgba(255, 252, 247, 0.90), rgba(247, 239, 228, 0.76));
                box-shadow: 0 12px 34px rgba(55, 43, 35, 0.08);
                margin-bottom: 1rem;
            }

            .section-kicker {
                display: inline-block;
                padding: 0.18rem 0.58rem;
                border-radius: 999px;
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                background: rgba(164, 126, 84, 0.12);
                color: #8a6238;
                margin-bottom: 0.6rem;
            }

            .section-title {
                font-size: 1.18rem;
                font-weight: 700;
                color: #3f332b;
                margin-bottom: 0.2rem;
            }

            .section-copy {
                color: rgba(63, 51, 43, 0.82);
                font-size: 0.94rem;
                line-height: 1.55;
                margin-bottom: 0.2rem;
            }

            .result-card {
                padding: 1rem 1rem 1.05rem 1rem;
                border-radius: 20px;
                border: 1px solid rgba(126, 99, 76, 0.16);
                background: linear-gradient(180deg, rgba(255, 252, 247, 0.96), rgba(245, 236, 223, 0.80));
                margin-bottom: 1rem;
            }

            .meta-row {
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                margin: 0.45rem 0 0.75rem 0;
            }

            .meta-pill {
                padding: 0.28rem 0.64rem;
                border-radius: 999px;
                background: rgba(85, 106, 86, 0.10);
                border: 1px solid rgba(85, 106, 86, 0.12);
                color: #3e5846;
                font-size: 0.8rem;
            }

            .score-pill {
                display: inline-block;
                margin-bottom: 0.6rem;
                padding: 0.24rem 0.62rem;
                border-radius: 999px;
                background: rgba(182, 133, 72, 0.14);
                color: #8c5f22;
                font-size: 0.8rem;
                font-weight: 700;
            }

            div[data-testid="stExpander"] {
                border: 1px solid rgba(126, 99, 76, 0.16);
                border-radius: 18px;
                background: rgba(255, 252, 247, 0.72);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_optional_number(value: int) -> int | None:
    return value if value > 0 else None


def get_recommendations(title: str, author: str, filters: dict) -> dict | None:
    cleaned_filters = {
        key: value
        for key, value in filters.items()
        if value is not None and value != ""
    }
    params = {"q": title.strip(), "author": author.strip(), **cleaned_filters}
    params = {key: value for key, value in params.items() if value not in ("", None)}

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(f"{BASE_URL}/recommend", params=params)
    except httpx.ConnectError:
        st.error(
            f"Não foi possivel conectar ao backend em `{BASE_URL}`. "
            "Verifique se o FastAPI está em execução."
        )
        return None

    if response.status_code == 404:
        st.warning("Livro de referência não encontrado na base de dados.")
        return None

    if response.status_code == 422:
        st.warning("Informe um título ou um autor para continuar.")
        return None

    if response.status_code != 200:
        st.error(f"Erro da API ({response.status_code}): {response.text}")
        return None

    return response.json()

st.title("Book-it")
st.caption("Por Babi :)")

def render_intro() -> None:
    st.markdown(
        """
        <div class="hero-block">
            <div class="hero-kicker">Recomendações literárias</div>
            <div class="hero-title">Encontre sua próxima leitura a partir de livros e autores favoritos.</div>
            <div class="hero-copy">
                Pesquise por título, por autor, ou pelos dois ao mesmo tempo. Quando um autor é informado,
                as obras dele ganham prioridade antes da exploração por autores similares.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="chip-grid">
            <div class="chip-card">
                <strong>Busca guiada</strong>
                <span>Parta de um título ou autor conhecido para explorar livros relacionados.</span>
            </div>
            <div class="chip-card">
                <strong>Autor em foco</strong>
                <span>Obras do autor pesquisado aparecem primeiro antes dos autores similares.</span>
            </div>
            <div class="chip-card">
                <strong>Filtros intuitivos</strong>
                <span>Páginas e ano aceitam digitação manual e setas em passos de 10.</span>
            </div>
            <div class="chip-card">
                <strong>Gênero flexível</strong>
                <span>Escolha um gênero sugerido ou digite o termo que quiser.</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <div class="section-kicker">{kicker}</div>
            <div class="section-title">{title}</div>
            <div class="section-copy">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_filters() -> dict:
    with st.expander("Filtros de recomendação", expanded=True):
        st.caption("Use 0 para ignorar filtros numéricos.")

        top_left, top_right = st.columns([1.6, 1], gap="large")
        with top_left:
            selected_genre = st.selectbox(
                "Gênero literário",
                options=COMMON_GENRES,
                index=0,
                help="Você pode digitar para localizar opções dentro do dropdown.",
            )
            custom_genre = st.text_input(
                "Ou digite um gênero",
                placeholder="Ex.: fantasia sombria, romance, filosofia",
                help="Se preenchido, este texto tem prioridade sobre o gênero sugerido.",
            )
        with top_right:
            limit = st.number_input(
                "Quantidade de recomendações",
                min_value=1,
                max_value=20,
                value=5,
                step=1,
            )

        col1, col2 = st.columns(2, gap="large")
        with col1:
            min_pages = st.number_input(
                "Páginas mínimas",
                min_value=0,
                value=0,
                step=10,
                help="Aceita digitação manual ou incrementos de 10 páginas.",
            )
            min_year = st.number_input(
                "Ano mínimo",
                min_value=0,
                value=0,
                step=10,
                help="Aceita digitação manual ou incrementos de 10 anos.",
            )
        with col2:
            max_pages = st.number_input(
                "Páginas máximas",
                min_value=0,
                value=0,
                step=10,
                help="Aceita digitação manual ou incrementos de 10 páginas.",
            )
            max_year = st.number_input(
                "Ano máximo",
                min_value=0,
                value=0,
                step=10,
                help="Aceita digitação manual ou incrementos de 10 anos.",
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


def render_book_card(book: dict, show_score: bool = False, position: int | None = None) -> None:
    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    image_col, content_col = st.columns([1, 3.2], gap="large")

    with image_col:
        if book.get("thumbnail"):
            st.image(book["thumbnail"], width="stretch")
        else:
            st.caption("Sem capa disponivel")

    with content_col:
        if position is not None:
            st.caption(f"Recomendação {position}")
        if show_score:
            st.markdown(
                f'<div class="score-pill">Score {book["score"]:.2f}</div>',
                unsafe_allow_html=True,
            )
        st.subheader(book["title"])
        authors = ", ".join(book.get("authors", [])) or "Desconhecido"
        categories = ", ".join(book.get("categories", [])) or "N/A"
        st.markdown(
            f"""
            <div class="meta-row">
                <div class="meta-pill">Autores: {authors}</div>
                <div class="meta-pill">Gênero: {categories}</div>
                <div class="meta-pill">Páginas: {book.get("page_count") or "N/A"}</div>
                <div class="meta-pill">Ano: {book.get("published_year") or "N/A"}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if book.get("description"):
            st.write(book["description"])

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Book-it Babi",
        page_icon="./assets/Bit-logo.png",
        layout="wide",
    )

    apply_page_styles()
    render_intro()
    render_section_header(
        "Busca",
        "Escolha um livro, um autor, ou combine os dois",
        "Quando um autor é informado, o sistema tenta mostrar primeiro as obras dele e depois amplia a curadoria para autores similares.",
    )

    with st.form("book-search-form"):
        input_col1, input_col2 = st.columns(2, gap="large")
        with input_col1:
            title = st.text_input(
                "Título do livro",
                placeholder="Ex.: Duna, 1984, O Hobbit, No Longer Human",
            )
        with input_col2:
            author = st.text_input(
                "Autor",
                placeholder="Ex.: Osamu Dazai, Ursula K. Le Guin, Machado de Assis",
            )

        filters = build_filters()
        submitted = st.form_submit_button("Buscar recomendações", width="stretch")

    if not submitted:
        st.info("Preencha um título, um autor, ou ambos, e clique em buscar para ver a curadoria.")
        return

    if not title.strip() and not author.strip():
        st.warning("Informe pelo menos um título ou um autor para continuar.")
        return

    with st.spinner("Buscando recomendações..."):
        data = get_recommendations(title.strip(), author.strip(), filters)

    if not data:
        return

    reference = data["reference"]
    recommendations = data["recommendations"]

    render_section_header(
        "Referência",
        "Obra usada como base",
        "Esta obra foi escolhida como referência principal para calcular similaridade e ordenar os resultados.",
    )
    render_book_card(reference)

    render_section_header(
        "Resultados",
        f"{len(recommendations)} recomendações encontradas",
        "Quando houver autor informado, as obras do proprio autor aparecem primeiro. Depois entram livros de autores similares ordenados pelo score.",
    )

    if not recommendations:
        st.info("Nenhum resultado encontrado com os filtros aplicados.")
        return

    for index, book in enumerate(recommendations, start=1):
        render_book_card(book, show_score=True, position=index)


if __name__ == "__main__":
    main()
