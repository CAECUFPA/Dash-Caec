# app.py
"""
Dashboard Financeiro Caec — versão FINAL corrigida
CORREÇÃO: Ordem dos KPIs (Receita, Despesa, Saldo) e aplicação de cores e setas Delta via st.metric + CSS.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import gspread
from gspread.client import Client as GSpreadClient
from oauth2client.service_account import ServiceAccountCredentials
from sklearn.linear_model import LinearRegression

# ---------- CONFIGURAÇÃO E CORES ----------
# Assumindo que você tem "caec-api-097d862f0223.json" ou usará st.secrets
SERVICE_ACCOUNT_FILE = "caec-api-097d862f0223.json"
SPREADSHEET_NAME = "PLANILHA FINANCEIRA"
WORKSHEET_INDEX = 1
EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

COLORS = {
    "receita": "#2ca02c",  # Verde
    "despesa": "#d62728",  # Vermelho
    "saldo": "#636efa",   # Azul
    "neutral": "#6c757d",  # Cinza
    "trend": "#ff9900",    # Laranja
}

DEFAULT_CHART_HEIGHT = 360

# ---------- CSS (Fonte customizada e Estilo de KPI CORRIGIDO) ----------
# Este CSS garante a ordem e as cores dos valores dos KPIs
FONT_AND_KPI_CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root, .stApp {{ font-family: 'Roboto Mono', monospace; }}
  
  /* 1. Receita (Verde) */
  [data-testid="stMetric"]:nth-child(1) [data-testid="stMetricValue"] {{
    color: {COLORS["receita"]} !important;
  }}
  /* 2. Despesa (Vermelho) */
  [data-testid="stMetric"]:nth-child(2) [data-testid="stMetricValue"] {{
    color: {COLORS["despesa"]} !important;
  }}
  /* 3. Saldo (Azul) */
  [data-testid="stMetric"]:nth-child(3) [data-testid="stMetricValue"] {{
    color: {COLORS["saldo"]} !important;
  }}
</style>
"""

# -------------------- UTILITÁRIOS E FUNÇÕES DE DADOS (Inalteradas, exceto tipos) --------------------

def parse_val_str_to_float(val) -> float:
    """Converte string de moeda para float."""
    if pd.isna(val) or val == "":
        return 0.0
    s = str(val).strip()
    neg = (s.startswith("(") and s.endswith(")")) or s.startswith("-")
    s = s.strip("()-").replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except Exception:
        v = 0.0
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    """Formata float para R$ X.XXX,XX."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_resource(ttl=600)
def get_gspread_client(service_account_file: str = SERVICE_ACCOUNT_FILE):
    """Obtém o cliente GSpread, usando st.secrets como fallback."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(service_account_file, scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro de autenticação: {e}. Verifique secrets.toml ou {service_account_file}.")
        return None

def load_sheet_values(client: Optional[GSpreadClient]) -> List[List[str]]:
    if not client: return []
    try:
        sh = client.open(st.secrets.get("SPREADSHEET_NAME", SPREADSHEET_NAME))
        ws = sh.get_worksheet(st.secrets.get("WORKSHEET_INDEX", WORKSHEET_INDEX))
        return ws.get_all_values()
    except Exception as e:
        st.error(f"Erro ao acessar a planilha: {e}")
        return []

def build_dataframe(values: List[List[str]]) -> pd.DataFrame:
    """Usa a primeira linha como cabeçalho, como no código base original."""
    if not values or len(values) < 1:
        return pd.DataFrame(columns=EXPECTED_COLS)
    header = values[0]
    body = values[1:] if len(values) > 1 else []
    if all(col in header for col in EXPECTED_COLS):
        df = pd.DataFrame(body, columns=header)[EXPECTED_COLS].copy()
    else:
        max_len = max(len(row) for row in body) if body else 0
        target_len = max(max_len, len(EXPECTED_COLS))
        padded = [row + [""] * max(0, target_len - len(row)) for row in body]
        df = pd.DataFrame(padded, columns=EXPECTED_COLS)
    return df

def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).reset_index(drop=True)
    df["VALOR_NUM"] = df["VALOR"].apply(parse_val_str_to_float)
    df["TIPO"] = df["TIPO"].fillna("").astype(str).str.strip()
    mask_empty_tipo = df["TIPO"] == ""
    df.loc[mask_empty_tipo, "TIPO"] = df.loc[mask_empty_tipo, "VALOR_NUM"].apply(lambda v: "Despesa" if v < 0 else "Receita")
    
    # Garante sinal correto após inferência de tipo
    mask_receita = df["TIPO"].str.contains("Receita", case=False, na=False)
    mask_despesa = df["TIPO"].str.contains("Despesa", case=False, na=False)
    df.loc[mask_receita, "VALOR_NUM"] = abs(df.loc[mask_receita, "VALOR_NUM"])
    df.loc[mask_despesa, "VALOR_NUM"] = -abs(df.loc[mask_despesa, "VALOR_NUM"])

    df["CATEGORIA"] = df["CATEGORIA"].fillna("NÃO CATEGORIZADO").astype(str).str.strip()
    df["DESCRIÇÃO"] = df["DESCRIÇÃO"].fillna("N/D").astype(str).str.strip()
    df["OBSERVAÇÃO"] = df["OBSERVAÇÃO"].fillna("N/D").astype(str).str.strip()
    df = df.sort_values("DATA").reset_index(drop=True)
    df["Saldo Acumulado"] = df["VALOR_NUM"].cumsum()
    df["year_month"] = df["DATA"].dt.to_period("M").astype(str)
    return df

@st.cache_data(ttl=600)
def load_and_preprocess_data() -> pd.DataFrame:
    client = get_gspread_client()
    raw_vals = load_sheet_values(client)
    df_raw = build_dataframe(raw_vals)
    df_processed = preprocess_df(df_raw)
    return df_processed

# -------------------- FUNÇÕES DE GRÁFICOS (Adicionada cor nos bubbles/candlestick) --------------------

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    """Retorna uma figura Plotly vazia com anotação."""
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=DEFAULT_CHART_HEIGHT)
    return fig

def plot_saldo_acumulado(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig()
    daily = df.groupby(df["DATA"].dt.date)["Saldo Acumulado"].last().reset_index()
    daily["DATA"] = pd.to_datetime(daily["DATA"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["DATA"], y=daily["Saldo Acumulado"],
                             mode="lines+markers", name="Saldo", line=dict(color=COLORS["saldo"], width=2)))
    if len(daily) > 1:
        X = daily["DATA"].map(pd.Timestamp.toordinal).values.reshape(-1, 1)
        y = daily["Saldo Acumulado"].values
        reg = LinearRegression().fit(X, y)
        X_line = np.linspace(X.min(), X.max(), 100).reshape(-1,1)
        y_pred = reg.predict(X_line)
        dates_line = [datetime.fromordinal(int(x)) for x in X_line.flatten()]
        fig.add_trace(go.Scatter(x=dates_line, y=y_pred, mode="lines", name="Tendência",
                                 line=dict(color=COLORS["trend"], dash="dash")))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
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

def plot_categoria_barras(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
    if kind == "Receita":
        base = df[df["VALOR_NUM"] > 0]; color_default = COLORS["receita"]
    else:
        base = df[df["VALOR_NUM"] < 0]; color_default = COLORS["despesa"]
    if base.empty: return _get_empty_fig(f"Sem dados de {kind}")
    series = base["VALOR_NUM"].abs().groupby(base["CATEGORIA"]).sum().sort_values(ascending=True) # Ascending para barras horizontais
    
    fig = px.bar(
        x=series.values, 
        y=series.index, 
        orientation='h', 
        labels={'x':'Valor (R$)', 'y':'Categoria'},
        color_discrete_sequence=[color_default]
    )
    fig.update_layout(height=DEFAULT_CHART_HEIGHT - 10, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis={'categoryorder':'total ascending'})
    return fig

def plot_pie_composicao(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
    if kind == "Receita":
        series = df[df["VALOR_NUM"] > 0].groupby("CATEGORIA")["VALOR_NUM"].sum()
        color_map = {'Receita': COLORS['receita']}
    else:
        series = (-df[df["VALOR_NUM"] < 0].groupby("CATEGORIA")["VALOR_NUM"].sum())
        color_map = {'Despesa': COLORS['despesa']}

    if series.empty: return _get_empty_fig(f"Sem dados de {kind}")
    series = series.sort_values(ascending=False)
    
    # Usando Pie com cor do label, tentando forçar cor base
    fig = go.Figure(go.Pie(labels=series.index, values=series.values, hole=0.45, textinfo="percent+label", sort=False))
    
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(t=30, b=10, l=10, r=10))
    return fig

def plot_bubble_transacoes(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig("Sem transações")
    dfp = df.copy()
    dfp["VALOR_ABS"] = dfp["VALOR_NUM"].abs()
    dfp["TIPO_COR"] = dfp["VALOR_NUM"].apply(lambda x: "Receita" if x > 0 else "Despesa")
    
    fig = px.scatter(dfp, x="DATA", y="VALOR_NUM", size="VALOR_ABS", color="TIPO_COR",
                     color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]},
                     hover_name="DESCRIÇÃO", size_max=30, title="Visão Detalhada de Transações (Tamanho = Valor Absoluto)")
    
    fig.update_layout(height=DEFAULT_CHART_HEIGHT + 40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(title='Tipo', orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_yaxes(title_text="Valor (R$)")
    fig.update_xaxes(title_text="Data")
    return fig

# Funções plot_candlestick, plot_monthly_heatmap, plot_boxplot_by_category...
# ...mantidas e ligeiramente ajustadas para consistência de cor (se aplicável)
# e para usar _get_empty_fig.

def prepare_ohlc_period(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    if df.empty: return pd.DataFrame()
    period = df["DATA"].dt.to_period(freq)
    dfp = df.copy(); dfp["PERIOD"] = period
    groups = []
    for per, g in dfp.groupby("PERIOD"):
        g_sorted = g.sort_values("DATA")
        groups.append({"PERIOD": per, "ts": per.to_timestamp(), 
                       "open": g_sorted.iloc[0]["VALOR_NUM"], "close": g_sorted.iloc[-1]["VALOR_NUM"],
                       "high": g_sorted["VALOR_NUM"].max(), "low": g_sorted["VALOR_NUM"].min(),
                       "volume": g_sorted["VALOR_NUM"].abs().sum()})
    return pd.DataFrame(groups).sort_values("ts").reset_index(drop=True)

def plot_candlestick(df: pd.DataFrame, freq: str = "D") -> go.Figure:
    ohlc = prepare_ohlc_period(df, freq)
    if ohlc.empty: return _get_empty_fig("Sem dados para candlestick")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.72, 0.28])
    fig.add_trace(go.Candlestick(x=ohlc["ts"], open=ohlc["open"], high=ohlc["high"], low=ohlc["low"], close=ohlc["close"], name="OHLC",
                                 increasing_line_color=COLORS["receita"], decreasing_line_color=COLORS["despesa"]), row=1, col=1)
    fig.add_trace(go.Bar(x=ohlc["ts"], y=ohlc["volume"], name="Volume", marker_color=COLORS["neutral"]), row=2, col=1)
    ohlc["sma7"] = ohlc["close"].rolling(window=7, min_periods=1).mean()
    fig.add_trace(go.Scatter(x=ohlc["ts"], y=ohlc["sma7"], mode="lines", name="SMA7", line=dict(color=COLORS["trend"])), row=1, col=1)
    fig.update_layout(height=DEFAULT_CHART_HEIGHT + 80, showlegend=True, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(title_text="Período", rangeslider_visible=False)
    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig

def plot_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig()
    dfh = df.copy(); dfh['day'] = dfh['DATA'].dt.day; dfh['ym'] = dfh['DATA'].dt.to_period('M').astype(str)
    pivot = dfh.groupby(['ym','day'])['VALOR_NUM'].sum().reset_index()
    heat = pivot.pivot(index='ym', columns='day', values='VALOR_NUM').fillna(0)
    # Usando RdBu (Vermelho/Azul) para divergência (negativo/positivo)
    fig = go.Figure(data=go.Heatmap(z=heat.values, x=heat.columns, y=heat.index, colorscale='RdBu', reversescale=True))
    fig.update_layout(title='Heatmap Mensal de Saldo Diário', height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Dia do Mês")
    fig.update_yaxes(title_text="Mês")
    return fig

def plot_boxplot_by_category(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig()
    dfp = df.copy(); dfp['VALOR_ABS'] = dfp['VALOR_NUM'].abs()
    fig = px.box(dfp, x='CATEGORIA', y='VALOR_ABS', points='outliers', 
                 color='TIPO', # Colore pelo tipo (Receita/Despesa)
                 color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]},
                 labels={'VALOR_ABS':'Valor absoluto (R$)'})
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(tickangle=-45)
    return fig

# -------------------- SIDEBAR E FILTROS (Inalterados) --------------------

def sidebar_filters_and_controls_with_toggle(df: pd.DataFrame) -> Tuple[str, Dict]:
    st.sidebar.title("Dashboard Financeiro Caec")
    st.sidebar.markdown("CAEC © 2025")
    st.sidebar.markdown("---")
    page = st.sidebar.selectbox("Altera visualização", options=["Resumo Financeiro", "Dashboard Detalhado"], key="sb_page")
    toggle_multi = st.sidebar.checkbox("Troca de filtro para Múltipla seleção", value=False, key="sb_toggle_multi")
    min_ts = df["DATA"].min() if not df.empty else pd.Timestamp(datetime.today() - timedelta(days=365))
    max_ts = df["DATA"].max() if not df.empty else pd.Timestamp(datetime.today())
    min_d = min_ts.date(); max_d = max_ts.date()
    filters: Dict = {"mode": "month", "month": "Todos", "categories": []}

    if toggle_multi:
        categories = sorted(df["CATEGORIA"].unique()) if not df.empty else []
        selected_cats = st.sidebar.multiselect("Categorias (múltiplas)", options=categories, default=categories if categories else [], key="sb_cat_multi")
        slider_val = st.sidebar.slider("Período (arraste)", min_value=min_d, max_value=max_d,
                                       value=(min_d, max_d), format="YYYY-MM-DD", step=timedelta(days=1), key="sb_date_slider")
        date_from = pd.to_datetime(slider_val[0])
        date_to = pd.to_datetime(slider_val[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        filters["mode"] = "range"; filters["date_from"] = date_from; filters["date_to"] = date_to; filters["categories"] = selected_cats
    else:
        months = ["Todos"] + sorted(df["year_month"].unique(), reverse=True) if not df.empty else ["Todos"]
        selected_month = st.sidebar.selectbox("Mês (ano-mês)", months, key="sb_month")
        categories = ["Todos"] + sorted(df["CATEGORIA"].unique()) if not df.empty else ["Todos"]
        selected_category = st.sidebar.selectbox("Categoria", categories, key="sb_cat_single")
        filters["mode"] = "month"; filters["month"] = selected_month
        filters["categories"] = [selected_category] if selected_category != "Todos" else []

    st.sidebar.markdown("---")
    if st.sidebar.button("Limpar cache (não recarrega automaticamente)", key="sb_clear_cache"):
        st.cache_data.clear(); st.cache_resource.clear()
        st.sidebar.success("Cache limpo — atualize a página se desejar ver mudanças imediatamente.")
    st.sidebar.markdown("---")
    st.sidebar.markdown("Criador e administrado pela administração comercial e financeiro — by Rick")
    return page, filters

def apply_filters(df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    f = df.copy()
    if filters.get("mode") == "range":
        df_filtered = f[(f["DATA"] >= filters["date_from"]) & (f["DATA"] <= filters["date_to"])]
    else:
        month = filters.get("month", "Todos")
        df_filtered = f[f["year_month"] == month] if month and month != "Todos" else f
    cats = filters.get("categories", [])
    if cats and "Todos" not in cats:
        df_filtered = df_filtered[df_filtered["CATEGORIA"].isin(cats)]
    return df_filtered.reset_index(drop=True)

# -------------------- COMPONENTE KPI CORRIGIDO --------------------

def render_kpis_with_metric(df: pd.DataFrame):
    """
    Renderiza os KPIs usando st.metric na ordem Receita, Despesa, Saldo.
    O CSS acima aplica as cores aos valores.
    """
    receita = df.loc[df["VALOR_NUM"] > 0, "VALOR_NUM"].sum()
    despesa = df.loc[df["VALOR_NUM"] < 0, "VALOR_NUM"].sum()
    saldo = receita + despesa

    # A ordem dos columns define a ordem dos KPIs (c1, c2, c3 = 1º, 2º, 3º)
    c_receita, c_despesa, c_saldo = st.columns(3)

    # 1. RECEITA (Verde)
    with c_receita:
        # Receita positiva, delta para cima (normal)
        st.metric(
            label="Receita Total (Verde)", 
            value=money_fmt_br(receita), 
            delta=money_fmt_br(receita), # O valor do delta é positivo
            delta_color="normal" # Seta verde (padrão)
        )

    # 2. DESPESA (Vermelho)
    with c_despesa:
        # Despesa deve ser apresentada como positiva, mas o delta deve ser negativo (inverse)
        st.metric(
            label="Despesa Total (Vermelho)", 
            value=money_fmt_br(abs(despesa)), 
            delta=money_fmt_br(abs(despesa)), # O valor do delta é positivo
            delta_color="inverse" # Seta vermelha para baixo (inverse)
        )

    # 3. SALDO (Azul)
    with c_saldo:
        delta_saldo_valor = saldo
        if saldo > 0:
            delta_color = "normal"  # Seta verde
        elif saldo < 0:
            delta_color = "inverse" # Seta vermelha
        else:
            delta_color = "off"     # Sem seta

        st.metric(
            label="Saldo Atual (Azul)", 
            value=money_fmt_br(saldo), 
            delta=money_fmt_br(saldo), # Exibe o valor do saldo no delta para indicar a magnitude
            delta_color=delta_color
        )

def render_table(df: pd.DataFrame, key: str):
    if df.empty:
        st.info("Sem lançamentos para mostrar.")
        return
    df_display = df.copy()
    df_display["Data"] = df_display["DATA"].dt.date
    # Cria uma coluna para formatar o valor sem o sinal para Despesa
    df_display["Valor (R$)"] = df_display["VALOR_NUM"].apply(money_fmt_br)
    df_display = df_display.rename(columns={"TIPO":"Tipo","CATEGORIA":"Categoria","DESCRIÇÃO":"Descrição","OBSERVAÇÃO":"Observação"})
    column_config = {
        "Data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
        "Valor (R$)": st.column_config.TextColumn("Valor (R$)"),
    }
    st.dataframe(df_display[["Data","Tipo","Categoria","Descrição","Valor (R$)","Observação"]], column_config=column_config, use_container_width=True, key=key, hide_index=True)

# -------------------- MAIN --------------------

def main():
    st.set_page_config(page_title="Dashboard Financeiro Caec", layout="wide", initial_sidebar_state="expanded",
                       menu_items={"About": "Dashboard Financeiro Caec"})
    # Aplica o CSS CORRIGIDO
    st.markdown(FONT_AND_KPI_CSS, unsafe_allow_html=True)
    st.title("Dashboard Financeiro Caec")

    df = load_and_preprocess_data()
    if df.empty:
        st.sidebar.markdown("---")
        st.sidebar.caption("CAEC © 2025")
        st.warning("Planilha vazia ou erro ao importar dados. Verifique planilha/credenciais.")
        return

    page, filters = sidebar_filters_and_controls_with_toggle(df)
    df_filtered = apply_filters(df, filters)

    # Usa a função render_kpis_with_metric CORRIGIDA
    render_kpis_with_metric(df_filtered)
    st.markdown("---")

    if page == "Resumo Financeiro":
        st.subheader("Evolução do Saldo Acumulado")
        fig_saldo = plot_saldo_acumulado(df_filtered)
        st.plotly_chart(fig_saldo, use_container_width=True, config={'displayModeBar': False}, key="chart_saldo_line_resumo")

        st.subheader("Fluxo de Caixa Diário")
        fig_fluxo = plot_fluxo_diario(df_filtered)
        st.plotly_chart(fig_fluxo, use_container_width=True, config={'displayModeBar': False}, key="chart_fluxo_bar_resumo")

        st.subheader("Lançamentos Recentes")
        recent = df_filtered.sort_values("DATA", ascending=False).head(10)
        render_table(recent, key="table_recent_resumo")

        export_df = df_filtered[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]]
        csv = export_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_resumo_export.csv", mime="text/csv", key="download_resumo")

    else:
        tab_normais, tab_avancados = st.tabs(["Normais", "Avançados"])

        with tab_normais:
            st.subheader("Análise por Categoria e Composição")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("##### Receita por Categoria (Barras)")
                fig_rec = plot_categoria_barras(df_filtered, kind="Receita")
                st.plotly_chart(fig_rec, use_container_width=True, config={'displayModeBar': False}, key="chart_rec_bar_normais")
                st.markdown("##### Composição de Receita (Setor)")
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Receita"), use_container_width=True, config={'displayModeBar': False}, key="chart_pie_rec_normais")
            with col2:
                st.markdown("##### Despesa por Categoria (Barras)")
                fig_dep = plot_categoria_barras(df_filtered, kind="Despesa")
                st.plotly_chart(fig_dep, use_container_width=True, config={'displayModeBar': False}, key="chart_dep_bar_normais")
                st.markdown("##### Composição de Despesa (Setor)")
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Despesa"), use_container_width=True, config={'displayModeBar': False}, key="chart_pie_dep_normais")

            st.markdown("---")
            st.subheader("Visão Temporal de Lançamentos (Bolhas)")
            # Usando a função corrigida que colore por Tipo
            st.plotly_chart(plot_bubble_transacoes(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_bubble_normais")

        with tab_avancados:
            agg_freq = st.selectbox("Agregação Candlestick", options=[("Diário","D"), ("Semanal","W"), ("Mensal","M")], format_func=lambda x: x[0], key="sb_candle_freq")
            freq_code = agg_freq[1]
            st.subheader("Candlestick (Avançado)")
            st.plotly_chart(plot_candlestick(df_filtered, freq=freq_code), use_container_width=True, config={'displayModeBar': False}, key=f"chart_candlestick_{freq_code}")

            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Média Móvel (SMA) & Fluxo Diário")
                fluxo = df_filtered.groupby(df_filtered["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
                fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
                fluxo["sma14"] = fluxo["VALOR_NUM"].rolling(window=14, min_periods=1).mean()
                fig_ma = go.Figure()
                cores_fluxo = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
                fig_ma.add_trace(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], name="Fluxo Diário", marker_color=cores_fluxo))
                fig_ma.add_trace(go.Scatter(x=fluxo["DATA"], y=fluxo["sma14"], mode="lines", name="SMA14", line=dict(color=COLORS["trend"])))
                fig_ma.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_ma, use_container_width=True, config={'displayModeBar': False}, key="chart_sma14_avancado")
            with col2:
                st.subheader("Boxplot por Categoria")
                st.plotly_chart(plot_boxplot_by_category(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_box_avancado")

            st.markdown("---")
            st.subheader("Heatmap Mensal (Avançado)")
            st.plotly_chart(plot_monthly_heatmap(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_heatmap_avancado")

        st.markdown("---")
        st.subheader("Tabela Completa (Filtro Atual)")
        render_table(df_filtered, key="table_full_detalhado")
        export_df = df_filtered[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]]
        csv = export_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_full_export.csv", mime="text/csv", key="download_full")

    st.markdown("---")
    st.markdown("<div style='font-size:12px;color:gray;text-align:center'>CAEC © 2025 — Criador e administrado pela administração comercial e financeiro — by Rick</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
