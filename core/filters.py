import streamlit as st


def apply_sidebar_filters(df):
    """Lógica global de filtros para o BI com Multiselect auto-populado."""
    if df.empty:
        return df

    with st.sidebar:
        st.header("Filtros:")

        # --- CONTROLE DE MODO ---
        multi_mode = st.toggle("Ativar seleção múltipla", value=False)

        # Preparação das listas
        meses_lista = sorted(df["year_month"].unique(), reverse=True)
        cats_lista = sorted(df["CATEGORIA"].unique())

        if not multi_mode:
            # ==========================================
            # MODO RÁPIDO (Selectbox com "Todos")
            # ==========================================
            st.subheader("Filtro Rápido")

            sel_m = st.selectbox(
                "Mês (ano-mês)", ["Todos"] + meses_lista, key="global_m_uni"
            )
            sel_c = st.selectbox(
                "Categoria", ["Todos"] + cats_lista, key="global_c_uni"
            )

            meses_sel = meses_lista if sel_m == "Todos" else [sel_m]
            cats_sel = cats_lista if sel_c == "Todos" else [sel_c]

        else:
            # ==========================================
            # MODO AVANÇADO (Multiselect TOTALMENTE PREENCHIDO)
            # ==========================================
            st.subheader("Seleção Manual")

            # Aqui o 'default' recebe a lista completa para já vir selecionado
            ms_m = st.multiselect(
                "Filtrar Meses",
                options=meses_lista,
                default=meses_lista,  # Preenche tudo por padrão
                key="global_m_multi",
            )

            ms_c = st.multiselect(
                "Filtrar Categorias",
                options=cats_lista,
                default=cats_lista,  # Preenche tudo por padrão
                key="global_c_multi",
            )

            # Garante que se o usuário desmarcar TUDO, o gráfico não quebre (retorna vazio ou todos)
            # Aqui vou manter a lógica de que se estiver vazio, não mostra nada (filtro real)
            meses_sel = ms_m
            cats_sel = ms_c

    # Retorna o DataFrame já filtrado
    return df[
        (df["year_month"].isin(meses_sel)) & (df["CATEGORIA"].isin(cats_sel))
    ].copy()
