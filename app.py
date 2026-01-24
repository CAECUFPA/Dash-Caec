import streamlit as st
from core import PAGE_CONFIG, load_css
from data.loader import load_and_preprocess_data
from page import FinancePage, AnalyticsPage

# 1. Configuração de Página (Primeira chamada obrigatória)
st.set_page_config(**PAGE_CONFIG)

# 2. Estilização Global (Carrega seu style.css com o Saldo Azul e Rádio Amarelo)
load_css()


def main():
    # 3. Carregamento Único de Dados
    df, _ = load_and_preprocess_data()

    if df.empty:
        st.error(
            "❌ Não foi possível carregar a base de dados. Verifique o arquivo de origem."
        )
        return

    # 4. Navegação na Sidebar
    with st.sidebar:
        st.subheader("🧭 Navegação")
        # CORREÇÃO: Os nomes aqui devem ser idênticos aos das chaves do dicionário abaixo
        aba = st.radio(
            "Selecione a visão:",
            ["Analise Base", "Analise Completa"],
            index=0,
            help="Alterne entre o Dashboard Executivo e a Inteligência de Dados.",
        )
        st.divider()

    # 5. Roteamento Dinâmico
    # CORREÇÃO: Ajustado para bater com as strings do st.radio (Case Sensitive)
    pages = {"Analise Base": FinancePage, "Analise Completa": AnalyticsPage}

    # Busca a classe no dicionário usando a opção selecionada
    try:
        page_class = pages[aba]
        page_instance = page_class(df)
        page_instance.run()
    except KeyError:
        st.error(f"Erro de Roteamento: A página '{aba}' não foi encontrada.")


if __name__ == "__main__":
    main()
