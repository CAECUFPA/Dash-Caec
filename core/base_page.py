from abc import ABC, abstractmethod
import streamlit as st
from .filters import apply_sidebar_filters
from .kpis import render_kpis  # Certifique-se de que o path está correto


class BasePage(ABC):
    """Motor central do BI: Título, KPIs e Footer automáticos."""

    def __init__(self, df):
        self.df = df
        self._df_filtered = None

    @property
    def df_f(self):
        """Property de leitura: evita o erro de 'setter' que você teve."""
        if self._df_filtered is None:
            self._df_filtered = apply_sidebar_filters(self.df)
        return self._df_filtered

    def run(self):
        """Fluxo de execução padronizado."""
        # 1. Sidebar (Filtros)
        self.render_sidebar()

        # 2. Validação de dados
        if self.df_f.empty:
            st.warning("⚠️ Nenhum dado encontrado para os filtros selecionados.")
            return

        # 3. Cabeçalho Padrão (Título + KPIs)
        self._render_base_header()

        # 4. Conteúdo Específico da Página
        self.render_body()

        # 5. Footer fixo da diretoria
        self._render_base_footer()

    def render_sidebar(self):
        """Aplica os filtros globais."""
        self._df_filtered = apply_sidebar_filters(self.df)

    def _render_base_header(self):
        """Renderiza o topo comum a todas as páginas."""
        st.title("DashBoard Financeiro Caec")
        render_kpis(self.df_f)
        # Aqui chamamos o header específico se a página precisar de algo extra
        self.render_header()

    def _render_base_footer(self):
        """Footer oficial ADM/Fin com seu link."""
        st.markdown("---")
        footer_html = """
            <div style="text-align: center; color: #888; padding: 10px;">
                <p style="margin-bottom: 5px;">Produzido pela diretoria <b>ADM/Fin - Setor Comercial</b></p>
                <p>by <a href="https://www.instagram.com/r.henriques2/" target="_blank"
                   style="color: #f6d138; text-decoration: none;">rick 🦉</a></p>
            </div>
        """
        st.markdown(footer_html, unsafe_allow_html=True)

    @abstractmethod
    def render_header(self):
        """Para títulos secundários ou descrições específicas."""
        pass

    @abstractmethod
    def render_body(self):
        """Aqui entram os gráficos específicos de cada página."""
        pass
