from core import (
    st,
    BasePage,
    FinanceVisualizer,
)


class AnalyticsPage(BasePage):
    """
    Página de análise profunda.
    Nota: Título principal, KPIs e Footer agora são gerados pela BasePage.
    """

    def render_sidebar(self):
        """Atualiza o filtro interno da BasePage sem causar erro de setter."""
        super().render_sidebar()

    def render_header(self):
        """Subtítulo específico para a área de inteligência."""
        st.markdown("#### 📊 Inteligência de Dados e Auditoria")

    def render_body(self):
        """Layout focado em análise 80/20 e volume com suporte a stretch."""
        viz = FinanceVisualizer(self.df_f)

        tab1, tab2, tab3 = st.tabs(
            [
                "🎯 Performance & Saldo",
                "⚖️ Auditoria & Impacto",
                "📈 Volume & Frequência",
            ]
        )

        with tab1:
            st.subheader("Resultado por Categoria")
            st.plotly_chart(viz.plot_saldo_por_categoria(), width="stretch")

            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(viz.plot_ranking(tipo="receita"), width="stretch")
            with c2:
                st.plotly_chart(viz.plot_ranking(tipo="despesa"), width="stretch")

        with tab2:
            st.subheader("Análise de Pareto (Regra 80/20)")
            st.plotly_chart(viz.plot_analise_pareto(), width="stretch")

            st.subheader("Distribuição de Lançamentos (Clusters)")
            st.plotly_chart(viz.plot_dispersao(), width="stretch")

        with tab3:
            st.subheader("Volume Operacional")
            st.plotly_chart(viz.plot_volume_dados(), width="stretch")

            st.subheader("Ticket Médio por Setor")
            st.plotly_chart(viz.plot_ticket_medio(), width="stretch")

        with st.expander("📥 Exportar Dados Analíticos"):
            csv = self.df_f.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="Download Base Filtrada (CSV)",
                data=csv,
                file_name="analytics_caec_export.csv",
                mime="text/csv",
                width="stretch",
            )
