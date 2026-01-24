from core import (
    st,
    BasePage,
    FinanceVisualizer,
)


class FinancePage(BasePage):
    """
    Página Principal de Performance.
    Título, KPIs e Footer são geridos pela BasePage.
    """

    def render_sidebar(self):
        """Filtros Globais e Preparação dos Dados para o Extrato."""
        super().render_sidebar()
        # Garante a ordenação dos dados para a tabela
        self.df_table = self.df_f.sort_values("DATA", ascending=False)

    def render_header(self):
        """Subtítulo limpo - sem divider."""
        # Removemos o título redundante e o divider
        st.caption("Visão consolidada da saúde financeira e fluxos de caixa.")

    def render_body(self):
        """Corpo da página otimizado com preenchimento total."""
        viz = FinanceVisualizer(self.df_f)

        tab_perf, tab_data = st.tabs(
            ["📊 Performance Financeira", "📑 Extrato Detalhado"]
        )

        with tab_perf:
            # 1. Evolução de Patrimônio
            st.subheader("Evolução de Patrimônio")
            st.plotly_chart(viz.plot_run_chart(), width="stretch")

            # Espaçamento manual leve em vez de divider
            st.write("")

            # 2. Resultado Financeiro por Setor
            st.subheader("Resultado por Categoria")
            st.plotly_chart(viz.plot_saldo_por_categoria(), width="stretch")

        with tab_data:
            col_title, col_export = st.columns([4, 1])

            with col_title:
                st.subheader("Listagem de Lançamentos")

            with col_export:
                # Conversão segura para CSV
                csv = self.df_table.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 Exportar CSV",
                    data=csv,
                    file_name="extrato_caec_financeiro.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            # Tabela com largura stretch 2026
            st.dataframe(
                self.df_table[["DATA", "CATEGORIA", "DESCRIÇÃO", "VALOR_NUM"]],
                width="stretch",
                height=600,
                hide_index=True,
            )
