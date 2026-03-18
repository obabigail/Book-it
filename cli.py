import os
from html import escape

import httpx
import streamlit as st

BASE_URL = os.getenv("BOOKIT_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("BOOKIT_REQUEST_TIMEOUT_SECONDS", "30"))
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

            .book-cover-frame,
            .reference-cover-frame {
                width: 100%;
                aspect-ratio: 2 / 3;
                overflow: hidden;
                border-radius: 18px;
                border: 1px solid rgba(126, 99, 76, 0.16);
                background:
                    linear-gradient(180deg, rgba(255, 252, 247, 0.96), rgba(242, 232, 219, 0.88));
                box-shadow: 0 14px 28px rgba(55, 43, 35, 0.10);
            }

            .book-cover-frame img,
            .reference-cover-frame img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .book-cover-empty,
            .reference-cover-empty {
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 1rem;
                text-align: center;
                color: rgba(63, 51, 43, 0.72);
                font-size: 0.84rem;
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

            .shelf-strip {
                height: 18px;
                border-radius: 999px;
                background: linear-gradient(180deg, #7d5a3b, #5f4129);
                box-shadow: inset 0 2px 4px rgba(255,255,255,0.18), 0 8px 18px rgba(48, 34, 23, 0.16);
                margin: 0.4rem 0 1rem 0;
            }

            .reference-choice {
                min-height: 176px;
                padding: 0.75rem 0.75rem 0.65rem 0.75rem;
                border-radius: 18px;
                background: linear-gradient(180deg, rgba(255, 252, 247, 0.96), rgba(242, 232, 219, 0.88));
                border: 1px solid rgba(126, 99, 76, 0.16);
                box-shadow: 0 12px 24px rgba(55, 43, 35, 0.08);
                margin-top: 0.55rem;
                display: flex;
                flex-direction: column;
                gap: 0.32rem;
            }

            .reference-card-shell {
                display: flex;
                flex-direction: column;
                height: 100%;
                gap: 0.55rem;
            }

            .reference-card-body {
                flex: 1;
                display: flex;
                flex-direction: column;
            }

            .reference-card-action {
                margin-top: auto;
            }

            .reference-choice.is-selected {
                border: 2px solid rgba(128, 89, 43, 0.55);
                box-shadow: 0 14px 28px rgba(89, 59, 29, 0.16);
            }

            .reference-choice-title {
                font-size: 0.96rem;
                font-weight: 700;
                color: #3f332b;
                margin-bottom: 0.1rem;
                min-height: 2.8em;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 2;
                line-clamp: 2;
                overflow: hidden;
            }

            .reference-choice-meta {
                font-size: 0.83rem;
                color: rgba(63, 51, 43, 0.82);
                line-height: 1.45;
                min-height: 2.35em;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 2;
                line-clamp: 2;
                overflow: hidden;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_optional_number(value: int) -> int | None:
    return value if value > 0 else None


def get_recommendations(title: str, author: str, filters: dict, reference_id: str = "") -> dict | None:
    cleaned_filters = {
        key: value
        for key, value in filters.items()
        if value is not None and value != ""
    }
    params = {
        "q": title.strip(),
        "author": author.strip(),
        "reference_id": reference_id.strip(),
        **cleaned_filters,
    }
    params = {key: value for key, value in params.items() if value not in ("", None)}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.get(f"{BASE_URL}/recommend", params=params)
    except httpx.ConnectError:
        st.error(
            f"Não foi possivel conectar ao backend em `{BASE_URL}`. "
            "Verifique se o FastAPI está em execução."
        )
        return None
    except httpx.ReadTimeout:
        st.error(
            "A busca demorou mais do que o esperado. "
            "Tente novamente ou refine a consulta com título, autor ou categoria."
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


def search_reference_books(title: str, author: str = "", max_results: int = 8) -> list[dict]:
    if not title.strip():
        return []

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.get(
                f"{BASE_URL}/search",
                params={
                    "q": title.strip(),
                    "author": author.strip() or None,
                    "max_results": max_results,
                },
            )
    except httpx.ConnectError:
        st.error(
            f"Não foi possivel conectar ao backend em `{BASE_URL}`. "
            "Verifique se o FastAPI está em execução."
        )
        return []
    except httpx.ReadTimeout:
        st.error("A busca de obras-base demorou mais do que o esperado.")
        return []

    if response.status_code != 200:
        st.error(f"Erro da API ao buscar obras-base ({response.status_code}): {response.text}")
        return []

    return response.json()


def clear_reference_candidates() -> None:
    st.session_state["reference_candidates"] = []
    st.session_state["reference_query"] = ""
    st.session_state["selected_reference_id"] = ""

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
    with st.expander("Filtros de recomendação", expanded=False):
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
        render_cover_image(book, frame_class="book-cover-frame", empty_class="book-cover-empty")

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


def render_reference_shelf(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None

    st.markdown('<div class="shelf-strip"></div>', unsafe_allow_html=True)
    columns = st.columns(min(4, len(candidates)), gap="large")

    for index, book in enumerate(candidates):
        selected_id = st.session_state.get("selected_reference_id", "")
        is_selected = selected_id == book.get("id")
        with columns[index % len(columns)]:
            st.markdown('<div class="reference-card-shell">', unsafe_allow_html=True)
            render_cover_image(book, frame_class="reference-cover-frame", empty_class="reference-cover-empty")

            authors = ", ".join(book.get("authors", [])[:2]) or "Autor desconhecido"
            year = book.get("published_year") or "Ano N/A"
            categories = ", ".join(book.get("categories", [])[:2]) or "Genero N/A"
            selected_class = " is-selected" if is_selected else ""
            st.markdown(
                f"""
                <div class="reference-card-body">
                    <div class="reference-choice{selected_class}">
                    <div class="reference-choice-title">{book.get("title", "Sem título")}</div>
                    <div class="reference-choice-meta">{authors}</div>
                    <div class="reference-choice-meta">{year}</div>
                    <div class="reference-choice-meta">{categories}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="reference-card-action">', unsafe_allow_html=True)
            if st.button(
                "Selecionado" if is_selected else "Selecionar",
                key=f"select-reference-{book.get('id', index)}",
                width="stretch",
                disabled=is_selected,
            ):
                st.session_state["selected_reference_id"] = book.get("id", "")
                st.rerun()
            st.markdown("</div></div>", unsafe_allow_html=True)

    selected_id = st.session_state.get("selected_reference_id", "")
    if not selected_id:
        return None

    for book in candidates:
        if book.get("id") == selected_id:
            return book

    return None


def render_cover_image(book: dict, frame_class: str, empty_class: str) -> None:
    thumbnail = (book.get("thumbnail") or "").strip()
    title = escape(book.get("title", "Livro"), quote=True)
    if thumbnail:
        safe_thumbnail = escape(thumbnail, quote=True)
        st.markdown(
            f'<div class="{frame_class}"><img src="{safe_thumbnail}" alt="Capa de {title}" loading="lazy" referrerpolicy="no-referrer"></div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div class="{frame_class}"><div class="{empty_class}">Sem capa disponivel</div></div>',
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Book-it Babi",
        page_icon="./assets/Bit-logo.png",
        layout="wide",
    )

    st.title("Book-it")
    st.caption("Por Babi :)")
    apply_page_styles()
    render_intro()
    render_section_header(
        "Busca",
        "Escolha e confirme a obra-base",
        "Quando houver título, o fluxo te ajuda a selecionar a obra correta antes de buscar recomendações.",
    )

    if "reference_candidates" not in st.session_state:
        st.session_state["reference_candidates"] = []
    if "reference_query" not in st.session_state:
        st.session_state["reference_query"] = ""
    if "selected_reference_id" not in st.session_state:
        st.session_state["selected_reference_id"] = ""

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
        submitted = st.form_submit_button("Encontrar obra-base", width="stretch")

    if not title.strip() and not author.strip():
        st.info("Preencha um título, um autor, ou ambos. Quando houver título, você podera confirmar a obra-base antes da recomendacao.")
        return

    current_query = f"{title.strip()}::{author.strip()}"
    if title.strip() and st.session_state.get("reference_query") != current_query:
        clear_reference_candidates()

    if submitted:
        if title.strip():
            with st.spinner("Buscando obras para confirmar a referência..."):
                candidates = search_reference_books(title.strip(), author.strip(), max_results=8)
            st.session_state["reference_candidates"] = candidates
            st.session_state["reference_query"] = current_query
            st.session_state["selected_reference_id"] = ""
        else:
            clear_reference_candidates()

    title_for_recommendation = title.strip()
    author_for_recommendation = author.strip()
    reference_id_for_recommendation = ""

    if title.strip():
        candidates = st.session_state.get("reference_candidates", [])
        if not candidates:
            st.info("Clique em `Encontrar obra-base` para confirmar qual livro deve ser usado como referência.")
            return

        render_section_header(
            "Referência",
            "Confirme a obra correta",
            "Selecionar explicitamente a obra-base ajuda a evitar ambiguidades entre títulos parecidos, traduções e edições.",
        )
        selected_reference = render_reference_shelf(candidates)

        if not selected_reference:
            st.info("Selecione uma das capas acima para liberar a busca de similares.")
            return

        render_book_card(selected_reference)
        search_recommendations = st.button("Buscar recomendações com esta obra", type="primary", width="stretch")
        if not search_recommendations:
            return

        title_for_recommendation = selected_reference.get("title", "").strip()
        authors = selected_reference.get("authors", [])
        author_for_recommendation = (authors[0] if authors else author.strip()).strip()
        reference_id_for_recommendation = selected_reference.get("id", "").strip()
    else:
        search_recommendations = st.button("Buscar recomendações", type="primary", width="stretch")
        if not search_recommendations:
            st.info("Sem título, a curadoria pode partir diretamente do autor informado.")
            return

    with st.spinner("Buscando recomendações..."):
        data = get_recommendations(
            title_for_recommendation,
            author_for_recommendation,
            filters,
            reference_id=reference_id_for_recommendation,
        )

    if not data:
        return

    reference = data["reference"]
    recommendations = data["recommendations"]

    render_section_header(
        "Referência",
        "Obra usada como base",
        "Esta obra foi confirmada ou escolhida como referência principal para calcular similaridade e ordenar os resultados.",
    )
    render_book_card(reference)

    render_section_header(
        "Resultados",
        f"{len(recommendations)} recomendações encontradas",
        "Os resultados foram ordenados por score de similaridade depois da confirmacao da obra-base.",
    )

    if not recommendations:
        st.info("Nenhum resultado encontrado com os filtros aplicados.")
        return

    for index, book in enumerate(recommendations, start=1):
        render_book_card(book, show_score=True, position=index)


if __name__ == "__main__":
    main()
