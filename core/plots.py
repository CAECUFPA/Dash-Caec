import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


class FinanceVisualizer:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.color_map = self._generate_color_map()
        self.success_color = "#2ecc71"
        self.danger_color = "#e74c3c"
        self.template_color = "#00d2ff"

    def _generate_color_map(self):
        categorias = sorted(self.df["CATEGORIA"].unique())
        colors = px.colors.qualitative.Prism
        return {cat: colors[i % len(colors)] for i, cat in enumerate(categorias)}

    def _apply_layout(self, fig: go.Figure, title: str, height: int = 600):
        fig.update_layout(
            height=height,
            title=dict(
                text=f"<b>{title.upper()}</b>",
                x=0.5,
                xanchor="center",
                y=0.98,
                font=dict(size=20, color="#FFFFFF"),
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Arial Black, sans-serif", size=13, color="#EAEAF0"),
            # Margens equilibradas para acomodar a barra de cores na direita (r=80)
            margin=dict(l=80, r=80, t=150, b=150),
            legend=dict(
                orientation="h", y=-0.45, x=0.5, xanchor="center", font=dict(size=12)
            ),
            hovermode="closest",
        )

        fig.update_xaxes(
            showgrid=False,
            linecolor="#888",
            tickangle=-45,
            automargin=True,
            title_text=None,
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)",
            linecolor="#888",
            title_text=None,
            automargin=True,
        )
        return fig

    def plot_analise_pareto(self) -> go.Figure:
        df_g = self.df[self.df["VALOR_NUM"] < 0].copy()
        df_grouped = (
            df_g.groupby("CATEGORIA")["VALOR_NUM"]
            .sum()
            .abs()
            .sort_values(ascending=False)
            .reset_index()
        )
        df_grouped["percent_acumulado"] = (
            df_grouped["VALOR_NUM"].cumsum() / df_grouped["VALOR_NUM"].sum()
        ) * 100

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=df_grouped["CATEGORIA"],
                y=df_grouped["VALOR_NUM"],
                name="Custo Total",
                marker_color="#3498db",
                text=df_grouped["VALOR_NUM"].apply(lambda x: f"R$ {x:,.0f}"),
                textposition="outside",
                cliponaxis=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df_grouped["CATEGORIA"],
                y=df_grouped["percent_acumulado"],
                name="% Acumulada",
                yaxis="y2",
                line=dict(color="#f1c40f", width=4),
                mode="lines+markers",
            )
        )
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", range=[0, 110], showgrid=False),
            yaxis=dict(range=[0, df_grouped["VALOR_NUM"].max() * 1.4]),
        )
        return self._apply_layout(fig, "Análise de Pareto: Foco de Custos")

    def plot_volume_dados(self) -> go.Figure:
        df_count = (
            self.df.groupby("CATEGORIA")
            .size()
            .reset_index(name="Quantidade")
            .sort_values("Quantidade", ascending=False)
        )
        # Gradient Bar reativada aqui
        fig = px.bar(
            df_count,
            x="CATEGORIA",
            y="Quantidade",
            color="Quantidade",
            color_continuous_scale="Viridis",
            text_auto=True,
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(
            coloraxis_showscale=True,  # BARRA DE GRADIENTE VOLTOU
            coloraxis_colorbar=dict(title="Qtd", thickness=15, len=0.7, y=0.5),
            yaxis=dict(range=[0, df_count["Quantidade"].max() * 1.3]),
        )
        return self._apply_layout(fig, "Volume de Atividade")

    def plot_ticket_medio(self) -> go.Figure:
        df_mean = (
            self.df.groupby("CATEGORIA")["VALOR_NUM"]
            .mean()
            .abs()
            .sort_values(ascending=False)
            .reset_index()
        )
        # Gradient Bar reativada aqui
        fig = px.bar(
            df_mean,
            x="CATEGORIA",
            y="VALOR_NUM",
            color="VALOR_NUM",
            color_continuous_scale="Turbo",
        )
        fig.update_traces(
            texttemplate="R$ %{y:,.0f}", textposition="outside", cliponaxis=False
        )
        fig.update_layout(
            coloraxis_showscale=True,  # BARRA DE GRADIENTE VOLTOU
            coloraxis_colorbar=dict(title="R$", thickness=15, len=0.7, y=0.5),
            yaxis=dict(range=[0, df_mean["VALOR_NUM"].max() * 1.4]),
        )
        return self._apply_layout(fig, "Ticket Médio por Setor")

    def plot_saldo_por_categoria(self) -> go.Figure:
        df_g = (
            self.df.groupby("CATEGORIA")["VALOR_NUM"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        max_val = df_g["VALOR_NUM"].max()
        min_val = df_g["VALOR_NUM"].min()
        fig = go.Figure(
            go.Bar(
                x=df_g["CATEGORIA"],
                y=df_g["VALOR_NUM"],
                marker_color=[
                    self.success_color if v >= 0 else self.danger_color
                    for v in df_g["VALOR_NUM"]
                ],
                text=df_g["VALOR_NUM"].apply(lambda x: f"R$ {x:,.0f}"),
                textposition="outside",
                cliponaxis=False,
            )
        )
        fig.update_layout(yaxis=dict(range=[min_val * 1.3, max_val * 1.5]))
        return self._apply_layout(fig, "Resultado Financeiro")

    def plot_ranking(self, tipo="despesa") -> go.Figure:
        is_despesa = tipo == "despesa"
        filt = self.df["VALOR_NUM"] < 0 if is_despesa else self.df["VALOR_NUM"] > 0
        df_g = (
            self.df[filt]
            .groupby("CATEGORIA")["VALOR_NUM"]
            .sum()
            .abs()
            .sort_values(ascending=False)
            .reset_index()
        )
        fig = px.bar(
            df_g,
            x="CATEGORIA",
            y="VALOR_NUM",
            color="CATEGORIA",
            color_discrete_map=self.color_map,
        )
        fig.update_traces(
            texttemplate="R$ %{y:,.0f}", textposition="outside", cliponaxis=False
        )
        fig.update_layout(yaxis=dict(range=[0, df_g["VALOR_NUM"].max() * 1.3]))
        return self._apply_layout(
            fig, f"Ranking: {'Gastos' if is_despesa else 'Receitas'}"
        )

    def plot_dispersao(self) -> go.Figure:
        fig = px.scatter(
            self.df,
            x="DATA",
            y="VALOR_NUM",
            color="CATEGORIA",
            color_discrete_map=self.color_map,
            size=self.df["VALOR_NUM"].abs().fillna(1),
        )
        return self._apply_layout(fig, "Análise de Clusters")

    def plot_run_chart(self) -> go.Figure:
        df_run = (
            self.df.sort_values("DATA")
            .groupby("DATA")["VALOR_NUM"]
            .sum()
            .cumsum()
            .reset_index()
        )
        fig = go.Figure(
            go.Scatter(
                x=df_run["DATA"],
                y=df_run["VALOR_NUM"],
                fill="tozeroy",
                line=dict(color=self.template_color, width=3),
            )
        )
        return self._apply_layout(fig, "Evolução do Saldo")
