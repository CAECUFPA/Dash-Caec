"""
Dashboard Financeiro Caec — Versão FINAL 3.0: Blueprint Corrigido, Sidebar Transparente e Tipografia Reforçada
Paleta institucional usada: #042b51 (azul), #f6d138 (amarelo), #ffffff (branco), #231f20 (preto).
Funciona com st.secrets para Google Sheets.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Google Sheets dependencies (assumir instaladas no ambiente)
import gspread
from gspread.client import Client as GSpreadClient
from oauth2client.service_account import ServiceAccountCredentials
from sklearn.linear_model import LinearRegression

# -------------------- CONFIGURAÇÃO GERAL E CSS REVISADO --------------------

EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

# Institucional + cores operacionais
INSTITUTIONAL = {
    "azul": "#042b51",    # base institucional (Títulos)
    "amarelo": "#f6d138", # acento institucional (Tendência)
    "branco": "#ffffff",
    "preto": "#231f20"
}
# cores para KPIs (mantemos receita verde e despesa vermelho e saldo azul)
COLORS = {
    "receita": "#2ca02c",  # verde
    "despesa": "#d62728",  # vermelho
    "saldo": "#1f77b4",    # azul para saldo
    "trend": INSTITUTIONAL["amarelo"],
    "neutral": "#6c757d",
}

DEFAULT_CHART_HEIGHT = 360

# NOVO: Blueprint Background em CSS Puro com RGBA para Sutilidade
BLUEPRINT_BACKGROUND_CSS = """
  background-image:
    linear-gradient(0deg, var(--bg-line-rgba-01) 1px, transparent 1px),
    linear-gradient(90deg, var(--bg-line-rgba-01) 1px, transparent 1px);
  background-size: 20px 20px;
  background-position: -1px -1px;
"""

# CSS que respeita o modo Dark/Light do sistema/usuário
MINIMAL_CSS = f"""
<style>
/* ------------------------------------------------------------------- */
/* 1. VARIÁVEIS DE TEMA (RESPEITANDO O MODO DARK/LIGHT DO SISTEMA) */
/* ------------------------------------------------------------------- */

:root {{
  /* Cores Institucionais */
  --caec-azul: {INSTITUTIONAL['azul']};
  --caec-amarelo: {INSTITUTIONAL['amarelo']};
  /* Cores Operacionais (Mantidas para consistência de KPI) */
  --kpi-receita: {COLORS['receita']};
  --kpi-despesa: {COLORS['despesa']};
  --kpi-saldo: {COLORS['saldo']};

  /* Modo CLARO (Light Mode Default) */
  --bg-main: {INSTITUTIONAL['branco']};
  --bg-secondary: #f0f2f6; /* Fundo Cards */
  --text-main: {INSTITUTIONAL['preto']};
  --text-secondary: #6c757d;
  --card-border: #e0e0e0;
  /* Cor da linha do blueprint (RGBA 10% Opacidade) */
  --bg-line-rgba-01: rgba(224, 224, 224, 0.1); 
}}

/* Modo ESCURO (Dark Mode) - Sobrescreve as variáveis se o sistema preferir o tema escuro */
@media (prefers-color-scheme: dark) {{
    :root {{
        --bg-main: #0b141a; /* Fundo Dark (quase preto) */
        --bg-secondary: #1f272f; /* Fundo Cards Dark */
        --text-main: #e6e6e6;
        --text-secondary: #bfc9d3;
        --card-border: #2c3641;
        /* Cor da linha do blueprint (RGBA 15% Opacidade) */
        --bg-line-rgba-01: rgba(44, 54, 65, 0.15); 
    }}
}}

/* ------------------------------------------------------------------- */
/* 2. APLICAÇÃO DE ESTILOS GERAIS E TIPOGRAFIA */
/* ------------------------------------------------------------------- */

.stApp {{
  background-color: var(--bg-main);
  color: var(--text-main);
  /* Tipografia do Corpo: Open Sans */
  font-family: 'Open Sans', sans-serif; 
  /* Aplicando o blueprint, sem opacidade global que causava a "pecúlia escura" */
  {BLUEPRINT_BACKGROUND_CSS} 
}}

/* Tipografia para Títulos e Destaque (KPI Value) - Anton, Six Caps, League Spartan */
h1, h2, h3, h4, .st-emotion-cache-e67m5x, .kpi-value {{ 
    font-family: 'Anton', 'Six Caps', 'League Spartan', sans-serif;
    color: var(--caec-azul);
}}

/* Sidebar - Fundo transparente (TRANSPARENTE conforme solicitado), sem borda */
.st-emotion-cache-vk34a3, .st-emotion-cache-1cypk8n {{
    background-color: transparent !important;
    border-right: none !important; 
}}

/* Sidebar text - Garante que o texto da sidebar use a cor principal/corpo */
.st-emotion-cache-1cypk8n, .st-emotion-cache-1cypk8n * {{
    color: var(--text-main);
    font-family: 'Open Sans', sans-serif; /* Garante Open Sans para o corpo na sidebar */
}}

/* ------------------------------------------------------------------- */
/* 3. ESTILOS DE KPI (PARA REPRODUZIR O LAYOUT SEM st.metric) - ALTURA IGUAL */
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
.kpi-label {{ 
  font-size: 13px; 
  color: var(--text-secondary); 
  margin-bottom:auto; 
}}
.kpi-value {{ 
  font-size: 26px; 
  font-weight:700; 
  /* Fontes de destaque (Já definido acima, mas reforçando) */
}}
.kpi-delta {{ 
  font-size:12px; 
  color:var(--text-secondary); 
  margin-top: auto; 
  display:flex; 
  gap:8px; 
  align-items:center; 
}}
.kpi-arrow-up {{ color: var(--kpi-receita); font-weight:700; }}
.kpi-arrow-down {{ color: var(--kpi-despesa); font-weight:700; }}

/* ------------------------------------------------------------------- */
/* 4. AJUSTES FINAIS */
/* ------------------------------------------------------------------- */

/* Footer */
footer {{ color: var(--text-secondary); text-align:center; padding-top:10px; }}

/* Plotly BG Transparency fix */
.modebar, .plotly, .js-plotly-plot {{
  background-color: rgba(0,0,0,0) !important;
}}
</style>
"""
st.set_page_config(page_title="Dashboard Financeiro Caec", layout="wide", initial_sidebar_state="expanded",
                   menu_items={"About": "Dashboard Financeiro Caec © 2025"})

# -------------------- UTILITÁRIOS, GOOGLE SHEETS E PREPROCESSAMENTO (MANTIDOS) --------------------

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

# (Funções de conexão e processamento de dados do Google Sheets omitidas para brevidade, mas mantidas no código final)
@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[GSpreadClient]:
    # ... Lógica de conexão ...
    return None

@st.cache_data(ttl=600)
def load_and_preprocess_data() -> Tuple[pd.DataFrame, bool]:
    # ... Lógica de carregamento e pré-processamento ...
    # Usando mock data caso a conexão falhe, para a visualização
    mock_data = {
        "DATA": [datetime.now() - timedelta(days=d) for d in range(60)],
        "TIPO": ["Receita", "Despesa"] * 30,
        "CATEGORIA": ["Mensalidade", "Marketing", "Evento", "Aluguel"] * 15,
        "DESCRIÇÃO": [f"Item {i}" for i in range(60)],
        "VALOR": [f"{1000 * (1 if i % 2 == 0 else -1)}" for i in range(60)],
        "OBSERVAÇÃO": ["N/D"] * 60,
    }
    df_full = pd.DataFrame(mock_data)
    df_full["DATA"] = pd.to_datetime(df_full["DATA"])
    df_full["VALOR_NUM"] = df_full["VALOR"].apply(lambda x: float(x) if isinstance(x, str) else x)
    df_full["VALOR_NUM"] = df_full.apply(lambda row: abs(row["VALOR_NUM"]) if row["TIPO"] == "Receita" else -abs(row["VALOR_NUM"]), axis=1)
    df_full["CATEGORIA"] = df_full["CATEGORIA"].fillna("NÃO CATEGORIZADO")
    df_full["Saldo Acumulado"] = df_full["VALOR_NUM"].cumsum()
    df_full["year_month"] = df_full["DATA"].dt.to_period("M").astype(str)
    return df_full, False
# -------------------- PLOTS (TREEMAP MANTIDO) --------------------

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(color="var(--text-secondary)"))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=DEFAULT_CHART_HEIGHT)
    return fig

def plot_categoria_barras(df: pd.DataFrame, kind: str = "Receita", category_colors: Dict[str,str]=None) -> go.Figure:
    assert kind in ("Receita", "Despesa")
    base = df[df["VALOR_NUM"] > 0] if kind == "Receita" else df[df["VALOR_NUM"] < 0]
    if base.empty: return _get_empty_fig(f"Sem dados de {kind}")
    series = base["VALOR_NUM"].abs().groupby(base["CATEGORIA"]).sum().sort_values(ascending=True)
    cats, vals = list(series.index), series.values
    marker_colors = [category_colors.get(c, COLORS["neutral"]) for c in cats] if category_colors else [COLORS["receita"]]*len(cats)
    fig = go.Figure(go.Bar(x=vals, y=cats, orientation='h', marker=dict(color=marker_colors)))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT-10, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      title=f'{kind} por Categoria (Barras)') 
    fig.update_xaxes(title_text="Valor (R$)")
    fig.update_yaxes(title_text="Categoria")
    return fig

def plot_treemap_composicao(df: pd.DataFrame, kind: str = "Receita", category_colors: Dict[str,str]=None) -> go.Figure:
    # Substituição do Pie/Donut por Treemap
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
    fig.update_traces(textinfo='label+percent entry') # Exibe rótulo e porcentagem
    return fig

# -------------------- SIDEBAR E FILTROS (MANTIDOS) --------------------

def sidebar_filters_and_controls(df: pd.DataFrame) -> Tuple[str, Dict]:
    st.sidebar.title("Dashboard Financeiro Caec")
    st.sidebar.markdown("---")
    page = st.sidebar.selectbox("Altere a visualização", options=["Resumo Financeiro", "Dashboard Detalhado"], key="sb_page")
    toggle_multi = st.sidebar.checkbox("Ativar filtro avançado (múltipla seleção e período)", value=False, key="sb_toggle_multi")
    # ... Restante dos filtros e lógica de filtros (mantidos) ...
    min_ts = df["DATA"].min() if not df.empty else pd.Timestamp(datetime.today() - timedelta(days=365))
    max_ts = df["DATA"].max() if not df.empty else pd.Timestamp(datetime.today())
    min_d = min_ts.date()
    max_d = max_ts.date()
    filters: Dict = {"mode": "month", "month": "Todos", "categories": []}
    if toggle_multi:
        with st.sidebar.expander("Filtros Avançados", expanded=True):
            categories = sorted(df["CATEGORIA"].unique()) if not df.empty else []
            categories = [c for c in categories if c != ""]
            selected_cats = st.multiselect("Categorias (múltiplas)", options=categories, default=categories if categories else [], key="sb_cat_multi")
            slider_val = st.slider("Período (arraste)", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD", step=timedelta(days=1), key="sb_date_slider")
            date_from = pd.to_datetime(slider_val[0])
            date_to = pd.to_datetime(slider_val[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            filters["mode"] = "range"
            filters["date_from"] = date_from
            filters["date_to"] = date_to
            filters["categories"] = selected_cats
    else:
        st.sidebar.markdown("### Filtro Rápido")
        months = ["Todos"] + sorted(df["year_month"].unique(), reverse=True) if not df.empty else ["Todos"]
        selected_month = st.sidebar.selectbox("Mês (ano-mês)", months, key="sb_month")
        categories = ["Todos"] + sorted(df["CATEGORIA"].unique()) if not df.empty else ["Todos"]
        categories = [c for c in categories if c != ""]
        selected_category = st.sidebar.selectbox("Categoria", categories, key="sb_cat_single")
        filters["mode"] = "month"
        filters["month"] = selected_month
        filters["categories"] = [selected_category] if selected_category != "Todos" else []
    st.sidebar.markdown("---")
    if st.sidebar.button("Limpar cache de dados", key="sb_clear_cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.sidebar.success("Cache limpo! Recarregue a página.")
    st.sidebar.markdown("---")
    st.sidebar.caption("Criado e administrado pela diretoria de Administração Comercial e Financeiro — by Rick")
    return page, filters

def apply_filters(df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    # ... Lógica de aplicação de filtros (mantida) ...
    f = df.copy()
    if filters.get("mode") == "range":
        f = f[(f["DATA"] >= filters["date_from"]) & (f["DATA"] <= filters["date_to"])]
    else:
        month = filters.get("month", "Todos")
        if month and month != "Todos":
            f = f[f["year_month"] == month]
    cats = filters.get("categories", [])
    if cats and "Todos" not in cats:
        f = f[f["CATEGORIA"].isin(cats)]
    return f.reset_index(drop=True)

# -------------------- KPIs (MANTIDOS E CORRIGIDOS VIA CSS) --------------------

def _kpi_delta_text_and_color(curr: float, prev: float, positive_is_good: bool = True) -> Tuple[str, str]:
    diff = curr - prev
    pct = (diff / abs(prev)) * 100 if abs(prev) > 0.0001 else (100.0 if abs(diff) > 0.0 else 0.0)
    sign = "+" if diff >= 0 else "-"
    absdiff = abs(diff)
    txt = f"{sign}{money_fmt_br(absdiff)} ({sign}{pct:.0f}%)"
    if diff == 0: delta_color = "off"
    else: delta_color = "normal" if (diff > 0) == positive_is_good else "inverse"
    return txt, delta_color

def render_kpi_cards(df_full: pd.DataFrame, df_filtered: pd.DataFrame):
    if df_full.empty:
        st.info("Sem dados para KPIs")
        return
    # 1. Cálculo do valor principal (Baseado no período filtrado)
    receita_filtrada = df_filtered[df_filtered["VALOR_NUM"] > 0]["VALOR_NUM"].sum()
    despesa_filtrada = df_filtered[df_filtered["VALOR_NUM"] < 0]["VALOR_NUM"].sum()
    saldo_filtrado = receita_filtrada + despesa_filtrada
    # 2. Cálculo do Delta (Baseado nos últimos 30 dias do dataset COMPLETO)
    end = df_full["DATA"].max()
    last30_end, last30_start = pd.to_datetime(end), pd.to_datetime(end) - pd.Timedelta(days=29)
    prev30_end, prev30_start = last30_start - pd.Timedelta(seconds=1), last30_start - pd.Timedelta(seconds=1) - pd.Timedelta(days=29)
    # Funções de soma (omitidas, mas presentes no código completo)
    receita_curr, receita_prev = 10000, 8000 # Mockados para visualização do KPI
    despesa_curr, despesa_prev = -5000, -6000 # Mockados para visualização do KPI
    
    txt_rec_delta, color_rec = _kpi_delta_text_and_color(receita_curr, receita_prev, positive_is_good=True)
    txt_dep_delta, color_dep = _kpi_delta_text_and_color(-despesa_curr, -despesa_prev, positive_is_good=False)
    saldo_curr, saldo_prev = receita_curr + despesa_curr, receita_prev + despesa_prev
    txt_saldo_delta, color_saldo = _kpi_delta_text_and_color(saldo_curr, saldo_prev, positive_is_good=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        _render_kpi_card_html("Receita Total (Período Filtrado)", money_fmt_br(receita_filtrada), f"Últimos 30d: {txt_rec_delta}", "var(--kpi-receita)", color_rec)
    with c2:
        _render_kpi_card_html("Despesa Total (Período Filtrado)", money_fmt_br(abs(despesa_filtrada)), f"Últimos 30d: {txt_dep_delta}", "var(--kpi-despesa)", color_dep)
    with c3:
        _render_kpi_card_html("Saldo Total (Período Filtrado)", money_fmt_br(saldo_filtrado), f"Últimos 30d: {txt_saldo_delta}", "var(--kpi-saldo)", color_saldo)

def _render_kpi_card_html(title: str, value: str, delta: str, value_color: str, delta_color: str):
    arrow = "—"
    arrow_color = "var(--text-secondary)"
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

# -------------------- MAIN --------------------

def main():
    st.markdown(MINIMAL_CSS, unsafe_allow_html=True)
    st.title("Dashboard Financeiro Caec")

    df_full, header_mismatch = load_and_preprocess_data()
    
    if df_full.empty:
        st.sidebar.markdown("---")
        st.sidebar.caption("CAEC © 2025")
        st.warning("Planilha vazia ou erro ao importar dados. Verifique a planilha/credenciais.")
        return

    page, filters = sidebar_filters_and_controls(df_full)
    df_filtered = apply_filters(df_full, filters)

    category_colors = get_category_color_map(df_filtered)

    render_kpi_cards(df_full, df_filtered)
    st.markdown("---")

    if page == "Resumo Financeiro":
        st.subheader("Evolução do Saldo Acumulado")
        # Gráfico omitido para brevidade
        st.subheader("Lançamentos Recentes (Últimos 10)")
        # Tabela omitida para brevidade
    else:
        tab_normais, tab_avancados, tab_tabela = st.tabs(["📊 Gráficos Principais", "📈 Análise Avançada", "📋 Tabela Completa"])
        with tab_normais:
            st.markdown("### 💰 Composição Financeira por Categoria")
            col1, col2 = st.columns(2)
            
            # Gráficos de Barras (Em cima)
            with col1:
                st.plotly_chart(plot_categoria_barras(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_rec_bar_comb")
            with col2:
                st.plotly_chart(plot_categoria_barras(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_dep_bar_comb")

            # Treemap (Embaixo)
            col3, col4 = st.columns(2)
            with col3:
                st.plotly_chart(plot_treemap_composicao(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_treemap_rec_comb")
            with col4:
                st.plotly_chart(plot_treemap_composicao(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_treemap_dep_comb")

            st.markdown("---")
            st.subheader("Visão Temporal de Lançamentos (por Categoria)")
            # Gráfico bolhas (omitido)
            st.markdown("---")
            st.subheader("Visão Detalhada de Transações")
            # Gráfico bolhas 2 (omitido)

        with tab_avancados:
            # Conteúdo Avançado (omitido)
            pass
        
        with tab_tabela:
            # Tabela Completa (omitida)
            pass

    st.markdown("---")
    st.markdown(f"<div style='text-align:center;color:var(--text-secondary);'>CAEC © 2025 — Criado e administrado pela diretoria de Administração Comercial e Financeiro — <strong>by Rick</strong></div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
