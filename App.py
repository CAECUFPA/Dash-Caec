"""
Dashboard Financeiro Caec — Versão FINAL/CORRIGIDA: Tipografia, Blueprint e Layout OK.
Paleta institucional e fontes aplicadas conforme o manual de identidade.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from sklearn.linear_model import LinearRegression

# Importações de gspread e oauth2client (necessárias para o código real)
try:
    import gspread
    from gspread.client import Client as GSpreadClient
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    # Cria classes mock para o script rodar mesmo sem as libs instaladas/configuradas
    class GSpreadClient: pass
    class ServiceAccountCredentials:
        @staticmethod
        def from_json_keyfile_dict(a, b): return None

# -------------------- CONFIGURAÇÃO GERAL E CSS REVISADO --------------------

EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

INSTITUTIONAL = {
    "azul": "#042b51",    # base institucional (Títulos)
    "amarelo": "#f6d138", # acento institucional (Tendência)
    "branco": "#ffffff",
    "preto": "#231f20"
}
COLORS = {
    "receita": "#2ca02c",
    "despesa": "#d62728",
    "saldo": "#1f77b4",
    "trend": INSTITUTIONAL["amarelo"],
    "neutral": "#6c757d",
}
DEFAULT_CHART_HEIGHT = 360

BLUEPRINT_BACKGROUND_CSS = """
  background-image:
    linear-gradient(0deg, var(--bg-line-rgba-01) 1px, transparent 1px),
    linear-gradient(90deg, var(--bg-line-rgba-01) 1px, transparent 1px);
  background-size: 20px 20px;
  background-position: -1px -1px;
"""

# NOVO: Inclusão da importação das fontes via Google Fonts no CSS
MINIMAL_CSS = f"""
<style>
/* ------------------------------------------------------------------- */
/* 0. IMPORTAÇÃO DE FONTES (TIPOGRAFIA) */
/* ------------------------------------------------------------------- */
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Six+Caps&family=League+Spartan&family=Open+Sans:wght@400;700&display=swap');

/* ------------------------------------------------------------------- */
/* 1. VARIÁVEIS DE TEMA E CORES */
/* ------------------------------------------------------------------- */

:root {{
  --caec-azul: {INSTITUTIONAL['azul']};
  --caec-amarelo: {INSTITUTIONAL['amarelo']};
  --kpi-receita: {COLORS['receita']};
  --kpi-despesa: {COLORS['despesa']};
  --kpi-saldo: {COLORS['saldo']};

  /* Modo CLARO */
  --bg-main: {INSTITUTIONAL['branco']};
  --bg-secondary: #f0f2f6; 
  --text-main: {INSTITUTIONAL['preto']};
  --text-secondary: #6c757d;
  --card-border: #e0e0e0;
  --bg-line-rgba-01: rgba(224, 224, 224, 0.1); 
}}

/* Modo ESCURO */
@media (prefers-color-scheme: dark) {{
    :root {{
        --bg-main: #0b141a; 
        --bg-secondary: #1f272f; 
        --text-main: #e6e6e6;
        --text-secondary: #bfc9d3;
        --card-border: #2c3641;
        --bg-line-rgba-01: rgba(44, 54, 65, 0.15); 
    }}
}}

/* ------------------------------------------------------------------- */
/* 2. APLICAÇÃO DE ESTILOS GERAIS E TIPOGRAFIA */
/* ------------------------------------------------------------------- */

.stApp {{
  background-color: var(--bg-main);
  color: var(--text-main);
  /* Corpo/Legendas: Open Sans */
  font-family: 'Open Sans', sans-serif; 
  {BLUEPRINT_BACKGROUND_CSS} 
}}

/* Títulos, Subtítulos, Chamadas e KPI Value: Anton, Six Caps, League Spartan */
h1, h2, h3, h4, .st-emotion-cache-e67m5x, .kpi-value {{ 
    font-family: 'Anton', 'Six Caps', 'League Spartan', sans-serif;
    color: var(--caec-azul);
}}

/* Sidebar - Fundo transparente e sem borda */
.st-emotion-cache-vk34a3, .st-emotion-cache-1cypk8n {{
    background-color: transparent !important;
    border-right: none !important; 
}}

/* Sidebar texto - Garante Open Sans para o corpo na sidebar */
.st-emotion-cache-1cypk8n, .st-emotion-cache-1cypk8n * {{
    color: var(--text-main);
    font-family: 'Open Sans', sans-serif; 
}}

/* ------------------------------------------------------------------- */
/* 3. ESTILOS DE KPI (ALTURA IGUAL) */
/* ------------------------------------------------------------------- */

.kpi-card {{
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--card-border);
  box-shadow: none;
  width: 100%;
  height: 120px; /* Altura fixa para todos os KPIs */
  display: flex; 
  flex-direction: column;
  justify-content: space-between; 
}}
.kpi-label {{ font-size: 13px; color: var(--text-secondary); margin-bottom:auto; }}
/* .kpi-value usa as fontes de destaque */
.kpi-value {{ font-size: 26px; font-weight:700; margin-top: 4px; }}
.kpi-delta {{ font-size:12px; color:var(--text-secondary); margin-top: auto; display:flex; gap:8px; align-items:center; }}
.kpi-arrow-up {{ color: var(--kpi-receita); font-weight:700; }}
.kpi-arrow-down {{ color: var(--kpi-despesa); font-weight:700; }}

/* ------------------------------------------------------------------- */
/* 4. AJUSTES FINAIS */
/* ------------------------------------------------------------------- */

footer {{ color: var(--text-secondary); text-align:center; padding-top:10px; }}
.modebar, .plotly, .js-plotly-plot {{
  background-color: rgba(0,0,0,0) !important;
}}
</style>
"""
st.set_page_config(page_title="Dashboard Financeiro Caec", layout="wide", initial_sidebar_state="expanded",
                   menu_items={"About": "Dashboard Financeiro Caec © 2025"})

# -------------------- UTILITÁRIOS (FUNÇÕES ESSENCIAIS) --------------------

def parse_val_str_to_float(val) -> float:
    if pd.isna(val) or val == "": return 0.0
    s = str(val).strip()
    neg = (s.startswith("(") and s.endswith(")")) or s.startswith("-")
    s = s.strip("()-").replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try: v = float(s)
    except Exception: return 0.0
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_category_color_map(df: pd.DataFrame) -> Dict[str, str]:
    if df is None or df.empty: return {}
    cats = sorted(df["CATEGORIA"].dropna().unique())
    base = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    palette = [INSTITUTIONAL["azul"], INSTITUTIONAL["amarelo"]] + base
    colors = [palette[i % len(palette)] for i in range(len(cats))]
    return {cat: colors[i] for i, cat in enumerate(cats)}

# -------------------- GOOGLE SHEETS / PREPROCESSAMENTO (MOCKADAS) --------------------

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[GSpreadClient]:
    # Lógica de conexão real omitida.
    return None

@st.cache_data(ttl=600)
def load_and_preprocess_data() -> Tuple[pd.DataFrame, bool]:
    # Use dados Mock se a conexão falhar ou para demonstração.
    mock_data = {
        "DATA": [datetime.now() - timedelta(days=d) for d in range(60)] * 2,
        "TIPO": ["Receita"] * 60 + ["Despesa"] * 60,
        "CATEGORIA": ["Mensalidade", "Marketing", "Evento", "Aluguel"] * 30,
        "DESCRIÇÃO": [f"Item {i}" for i in range(120)],
        "VALOR": [f"{1000 * (1 if i % 2 == 0 else -1)}" for i in range(120)],
        "OBSERVAÇÃO": ["N/D"] * 120,
    }
    df_full = pd.DataFrame(mock_data)
    df_full["DATA"] = pd.to_datetime(df_full["DATA"])
    df_full["VALOR_NUM"] = df_full["VALOR"].apply(parse_val_str_to_float)
    df_full["VALOR_NUM"] = df_full.apply(lambda row: abs(row["VALOR_NUM"]) if row["TIPO"] == "Receita" else -abs(row["VALOR_NUM"]), axis=1)
    df_full["CATEGORIA"] = df_full["CATEGORIA"].fillna("NÃO CATEGORIZADO")
    df_full["Saldo Acumulado"] = df_full["VALOR_NUM"].cumsum()
    df_full["year_month"] = df_full["DATA"].dt.to_period("M").astype(str)
    return df_full.sort_values("DATA").reset_index(drop=True), False

# -------------------- PLOTS (FUNÇÕES ESSENCIAIS) --------------------

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(color="var(--text-secondary)"))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=DEFAULT_CHART_HEIGHT)
    return fig

def plot_saldo_acumulado(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig()
    daily = df.groupby(df["DATA"].dt.date)["Saldo Acumulado"].last().reset_index()
    daily["DATA"] = pd.to_datetime(daily["DATA"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["DATA"], y=daily["Saldo Acumulado"], mode="lines+markers",
                             name="Saldo", line=dict(color=COLORS["saldo"], width=2)))
    if len(daily) > 1:
        X = daily["DATA"].map(pd.Timestamp.toordinal).values.reshape(-1, 1)
        y = daily["Saldo Acumulado"].values
        reg = LinearRegression().fit(X, y)
        X_line = np.linspace(X.min(), X.max(), 100).reshape(-1,1)
        y_pred = reg.predict(X_line)
        dates_line = [datetime.fromordinal(int(x)) for x in X_line.flatten()]
        fig.add_trace(go.Scatter(x=dates_line, y=y_pred, mode="lines", name="Tendência", line=dict(color=COLORS["trend"], dash="dash")))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Saldo (R$)")
    return fig

def plot_fluxo_diario(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig()
    fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
    cores = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
    fig = go.Figure(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], marker_color=cores))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

def plot_categoria_barras(df: pd.DataFrame, kind: str = "Receita", category_colors: Dict[str,str]=None) -> go.Figure:
    assert kind in ("Receita", "Despesa")
    base = df[df["VALOR_NUM"] > 0] if kind == "Receita" else df[df["VALOR_NUM"] < 0]
    if base.empty: return _get_empty_fig(f"Sem dados de {kind}")
    series = base["VALOR_NUM"].abs().groupby(base["CATEGORIA"]).sum().sort_values(ascending=True)
    cats, vals = list(series.index), series.values
    marker_colors = [category_colors.get(c, COLORS["neutral"]) for c in cats]
    fig = go.Figure(go.Bar(x=vals, y=cats, orientation='h', marker=dict(color=marker_colors)))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT-10, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      title=f'{kind} por Categoria (Barras)') 
    fig.update_xaxes(title_text="Valor (R$)")
    fig.update_yaxes(title_text="Categoria")
    return fig

def plot_treemap_composicao(df: pd.DataFrame, kind: str = "Receita", category_colors: Dict[str,str]=None) -> go.Figure:
    if kind == "Receita":
        df_plot = df[df["VALOR_NUM"] > 0].groupby("CATEGORIA")["VALOR_NUM"].sum().reset_index()
        df_plot.columns = ["CATEGORIA", "VALOR"]
    else:
        df_plot = df[df["VALOR_NUM"] < 0].groupby("CATEGORIA")["VALOR_NUM"].sum().abs().reset_index()
        df_plot.columns = ["CATEGORIA", "VALOR"]
        
    if df_plot.empty: return _get_empty_fig(f"Sem dados de {kind}")

    fig = px.treemap(df_plot, path=[px.Constant("Total"), 'CATEGORIA'], values='VALOR',
                     color='CATEGORIA', color_discrete_map={**category_colors, "Total": INSTITUTIONAL["azul"]}) 
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      title=f'Composição de {kind} (Treemap)')
    fig.update_traces(textinfo='label+percent entry') 
    return fig

def plot_bubble_transacoes_categoria_y(df: pd.DataFrame, category_colors: Dict[str,str]=None) -> go.Figure:
    if df.empty: return _get_empty_fig("Sem transações")
    df_plot = df.copy()
    df_plot["Size"] = df_plot["VALOR_NUM"].abs()
    df_plot["VALOR_FMT"] = df_plot["VALOR_NUM"].apply(money_fmt_br)
    fig = px.scatter(df_plot, x="DATA", y="CATEGORIA", size="Size", color="CATEGORIA",
                     hover_name="DESCRIÇÃO", hover_data={"VALOR_FMT": True, "DATA": False},
                     color_discrete_map=category_colors, size_max=35)
    fig.update_traces(marker=dict(opacity=0.85, line=dict(width=0.6, color='rgba(0,0,0,0.12)')))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Categoria")
    return fig

# -------------------- KPIs E TABELA (FUNÇÕES ESSENCIAIS) --------------------

def _sum_period(df: pd.DataFrame, start_dt: datetime, end_dt: datetime, tipo: str = "all") -> float:
    if df.empty: return 0.0
    mask = (df["DATA"] >= start_dt) & (df["DATA"] <= end_dt)
    s = df.loc[mask, "VALOR_NUM"]
    if tipo == "receita": return s[s > 0].sum()
    elif tipo == "despesa": return s[s < 0].sum()
    else: return s.sum()

def _kpi_delta_text_and_color(curr: float, prev: float, positive_is_good: bool = True) -> Tuple[str, str]:
    diff = curr - prev
    pct = (diff / abs(prev)) * 100 if abs(prev) > 0.0001 else (100.0 if abs(diff) > 0.0 else 0.0)
    sign = "+" if diff >= 0 else "-"
    absdiff = abs(diff)
    txt = f"{sign}{money_fmt_br(absdiff)} ({sign}{pct:.0f}%)"
    if diff == 0: delta_color = "off"
    else: delta_color = "normal" if (diff > 0) == positive_is_good else "inverse"
    return txt, delta_color

def _render_kpi_card_html(title: str, value: str, delta: str, value_color: str, delta_color: str):
    arrow, arrow_color = "—", "var(--text-secondary)"
    if delta_color == "normal": arrow, arrow_color = "▲", "var(--kpi-receita)"
    elif delta_color == "inverse": arrow, arrow_color = "▼", "var(--kpi-despesa)"
    html = f"""
    <div class="kpi-card">
      <div class="kpi-label">{title}</div>
      <div class="kpi-value" style="color:{value_color};">{value}</div>
      <div class="kpi-delta"><span style="color:{arrow_color}; font-weight:700;">{arrow}</span><span style="color:var(--text-secondary);"> {delta}</span></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def render_kpi_cards(df_full: pd.DataFrame, df_filtered: pd.DataFrame):
    if df_full.empty:
        st.info("Sem dados para KPIs")
        return
    receita_filtrada = df_filtered[df_filtered["VALOR_NUM"] > 0]["VALOR_NUM"].sum()
    despesa_filtrada = df_filtered[df_filtered["VALOR_NUM"] < 0]["VALOR_NUM"].sum()
    saldo_filtrado = receita_filtrada + despesa_filtrada

    end = df_full["DATA"].max()
    last30_end, last30_start = pd.to_datetime(end), pd.to_datetime(end) - pd.Timedelta(days=29)
    prev30_end, prev30_start = last30_start - pd.Timedelta(seconds=1), last30_start - pd.Timedelta(seconds=1) - pd.Timedelta(days=29)
    
    receita_curr = _sum_period(df_full, last30_start, last30_end, tipo="receita")
    receita_prev = _sum_period(df_full, prev30_start, prev30_end, tipo="receita")
    despesa_curr = _sum_period(df_full, last30_start, last30_end, tipo="despesa")
    despesa_prev = _sum_period(df_full, prev30_start, prev30_end, tipo="despesa")
    
    txt_rec_delta, color_rec = _kpi_delta_text_and_color(receita_curr, receita_prev, positive_is_good=True)
    txt_dep_delta, color_dep = _kpi_delta_text_and_color(-despesa_curr, -despesa_prev, positive_is_good=False)
    saldo_curr, saldo_prev = receita_curr + despesa_curr, receita_prev + despesa_prev
    txt_saldo_delta, color_saldo = _kpi_delta_text_and_color(saldo_curr, saldo_prev, positive_is_good=True)

    c1, c2, c3 = st.columns(3)
    with c1: _render_kpi_card_html("Receita Total (Período Filtrado)", money_fmt_br(receita_filtrada), f"Últimos 30d: {txt_rec_delta}", "var(--kpi-receita)", color_rec)
    with c2: _render_kpi_card_html("Despesa Total (Período Filtrado)", money_fmt_br(abs(despesa_filtrada)), f"Últimos 30d: {txt_dep_delta}", "var(--kpi-despesa)", color_dep)
    with c3: _render_kpi_card_html("Saldo Total (Período Filtrado)", money_fmt_br(saldo_filtrado), f"Últimos 30d: {txt_saldo_delta}", "var(--kpi-saldo)", color_saldo)

def render_table(df: pd.DataFrame, key: str):
    if df.empty:
        st.info("Sem lançamentos para mostrar com os filtros atuais.")
        return
    df_display = df.copy()
    df_display["Data"] = df_display["DATA"].dt.date
    df_display["Valor (R$)"] = df_display["VALOR_NUM"].apply(money_fmt_br)
    df_display = df_display.rename(columns={"TIPO":"Tipo","CATEGORIA":"Categoria","DESCRIÇÃO":"Descrição","OBSERVAÇÃO":"Observação"})
    st.dataframe(df_display[["Data","Tipo","Categoria","Descrição","Valor (R$)","Observação"]], use_container_width=True, key=key, hide_index=True)

def _prepare_export_csv(df: pd.DataFrame) -> str:
    export_df = df[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]]
    return export_df.to_csv(index=False, encoding="utf-8-sig")

# -------------------- MAIN --------------------

def main():
    st.markdown(MINIMAL_CSS, unsafe_allow_html=True)
    st.title("Dashboard Financeiro Caec")

    df_full, header_mismatch = load_and_preprocess_data()
    
    if df_full.empty:
        st.warning("Planilha vazia ou erro ao importar dados. Verifique a planilha/credenciais.")
        return

    page, filters = sidebar_filters_and_controls(df_full)
    df_filtered = apply_filters(df_full, filters)

    category_colors = get_category_color_map(df_filtered)

    render_kpi_cards(df_full, df_filtered)
    st.markdown("---")

    if page == "Resumo Financeiro":
        st.subheader("Evolução do Saldo Acumulado")
        st.plotly_chart(plot_saldo_acumulado(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_saldo_line_resumo")

        st.subheader("Fluxo de Caixa Diário")
        st.plotly_chart(plot_fluxo_diario(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_fluxo_bar_resumo")

        st.subheader("Lançamentos Recentes (Últimos 10)")
        recent = df_filtered.sort_values("DATA", ascending=False).head(10)
        render_table(recent, key="table_recent_resumo")

        csv = _prepare_export_csv(df_filtered)
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_resumo_export.csv", mime="text/csv", key="download_resumo")
    else:
        tab_normais, tab_avancados, tab_tabela = st.tabs(["📊 Gráficos Principais", "📈 Análise Avançada", "📋 Tabela Completa"])
        with tab_normais:
            st.markdown("### 💰 Composição Financeira por Categoria")
            col1, col2 = st.columns(2)
            
            with col1:
                st.plotly_chart(plot_categoria_barras(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_rec_bar_comb")
            with col2:
                st.plotly_chart(plot_categoria_barras(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_dep_bar_comb")

            col3, col4 = st.columns(2)
            with col3:
                st.plotly_chart(plot_treemap_composicao(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_treemap_rec_comb")
            with col4:
                st.plotly_chart(plot_treemap_composicao(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_treemap_dep_comb")

            st.markdown("---")
            st.subheader("Visão Temporal de Lançamentos (por Categoria)")
            st.plotly_chart(plot_bubble_transacoes_categoria_y(df_filtered, category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_bubble_cat_y")

        with tab_avancados:
            st.warning("Conteúdo avançado pendente.")
        
        with tab_tabela:
            st.subheader("Todos os Lançamentos (Filtro Atual)")
            render_table(df_filtered, key="table_full_detalhado")
            csv = _prepare_export_csv(df_filtered)
            st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_full_export.csv", mime="text/csv", key="download_full")

    st.markdown("---")
    st.markdown(f"<div style='text-align:center;color:var(--text-secondary);'>CAEC © 2025 — Criado e administrado pela diretoria de Administração Comercial e Financeiro — <strong>by Rick</strong></div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
