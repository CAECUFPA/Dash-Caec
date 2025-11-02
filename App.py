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

# -------------------- CONFIGURAÇÃO GERAL --------------------

EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

# Paleta de Cores Institucionais
INSTITUTIONAL = {
    "azul": "#042b51",    # base institucional
    "amarelo": "#f6d138",
    "branco": "#ffffff",
    "preto": "#231f20"
}

# Cores Operacionais
COLORS = {
    "receita": "#2ca02c",  # verde (valor positivo)
    "despesa": "#d62728",  # vermelho (valor negativo)
    "saldo": "#1f77b4",    # azul para saldo
    "neutral": "#6c757d",
    "trend": INSTITUTIONAL["amarelo"]
}

DEFAULT_CHART_HEIGHT = 360

# URL de Imagem de Blueprint de Exemplo (pode ser substituída por Base64 de uma imagem local)
# Para uma imagem local 'logo.png', use a codificação Base64. Aqui, usamos um URL genérico.
# ATENÇÃO: Substitua pelo Base64 do seu blueprint ou URL de imagem hospedada.
BLUEPRINT_URL = "https://i.imgur.com/uRj0R0Y.png" 

# Tipografia
FONT_PRIMARY = "Anton, sans-serif"
FONT_SECONDARY = "Open Sans, sans-serif"

# CSS mínimo + Fundo Blueprint + Tipografia
MINIMAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Open+Sans:wght@300;400;700&display=swap');

:root {{
  --caec-azul: {INSTITUTIONAL['azul']};
  --caec-amarelo: {INSTITUTIONAL['amarelo']};
  --caec-branco: {INSTITUTIONAL['branco']};
  --caec-preto: {INSTITUTIONAL['preto']};
  --kpi-font-size: 26px;
  --kpi-label-size: 13px;
}}
/* Aplica fundo Blueprint, cor institucional escura para fallback, e fonte Open Sans */
body .stApp {{
  background-image: url("{BLUEPRINT_URL}");
  background-repeat: repeat;
  background-attachment: fixed;
  background-size: 300px; /* Ajuste o tamanho da repetição, se necessário */
  background-color: var(--caec-azul); /* Fallback dark institutional color */
  color: var(--caec-branco);
  font-family: {FONT_SECONDARY};
}}
/* Ajusta o título principal e subtítulos para a fonte Anton */
.stApp h1 {{
  font-family: {FONT_PRIMARY};
  color: var(--caec-amarelo); /* Destaque com o amarelo institucional */
}}
.stApp h2, .stApp h3, .stApp h4 {{
  font-family: {FONT_PRIMARY};
}}
/* Kartões de KPI simples */
.kpi-card {{
  border-radius: 8px;
  padding: 12px 14px;
  background: rgba(4,43,81,0.6); /* Azul institucional transparente */
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
  display: inline-block;
  width: 100%;
}}
.kpi-label {{ font-size: var(--kpi-label-size); color: #bfc9d3; margin-bottom:6px; font-weight:700; }}
.kpi-value {{ font-size: var(--kpi-font-size); font-weight:700; font-family: {FONT_PRIMARY}; }}
.kpi-delta {{ font-size:12px; color:#bfc9d3; margin-top:4px; display:flex; gap:8px; align-items:center; font-family: {FONT_SECONDARY}; }}
.kpi-arrow-up {{ color: {COLORS['receita']}; font-weight:700; }}
.kpi-arrow-down {{ color: {COLORS['despesa']}; font-weight:700; }}
/* Ajustes para os charts: fundo transparente, mas com uma leve cor institucional para legibilidade */
.chart-container {{ background: rgba(4,43,81,0.6); padding: 10px; border-radius: 8px; }}
footer {{ color: #cbd5e1; text-align:center; padding-top:10px; }}
</style>
"""
st.set_page_config(page_title="Dashboard Financeiro Caec", layout="wide", initial_sidebar_state="expanded",
menu_items={"About": "Dashboard Financeiro Caec © 2025"})

# -------------------- UTILITÁRIOS (Sem Alteração) --------------------

def parse_val_str_to_float(val) -> float:
    if pd.isna(val) or val == "":
        return 0.0
    s = str(val).strip()
    neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-"):
        neg = True
    s = s.strip("()-")
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except Exception:
        return 0.0
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_category_color_map(df: pd.DataFrame) -> Dict[str, str]:
    if df is None or df.empty:
        return {}
    cats = sorted(df["CATEGORIA"].dropna().unique())
    base = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
        "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]
    palette = [INSTITUTIONAL["azul"], INSTITUTIONAL["amarelo"]] + base
    colors = [palette[i % len(palette)] for i in range(len(cats))]
    return {cat: colors[i] for i, cat in enumerate(cats)}

# -------------------- GOOGLE SHEETS (Sem Alteração) --------------------

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[GSpreadClient]:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        return gspread.authorize(creds)
    except Exception:
        st.warning("Não foi possível autenticar Google Sheets via st.secrets. Se preferir, posso adaptar para CSV local.")
        return None

def load_sheet_values(client: GSpreadClient) -> List[List[str]]:
    if not client:
        return []
    try:
        spreadsheet_name = st.secrets["SPREADSHEET_NAME"]
        worksheet_index = int(st.secrets.get("WORKSHEET_INDEX", 0))
        sh = client.open(spreadsheet_name)
        ws = sh.get_worksheet(worksheet_index)
        return ws.get_all_values()
    except Exception as e:
        st.error(f"Erro ao acessar planilha: {e}")
        return []

def build_dataframe(values: List[List[str]]) -> Tuple[pd.DataFrame, bool]:
    if not values or len(values) < 2:
        return pd.DataFrame(columns=EXPECTED_COLS), False
    header = [str(h).strip() for h in values[1]]
    body = values[2:] if len(values) > 2 else []
    header_mismatch = False
    if all(col in header for col in EXPECTED_COLS):
        df = pd.DataFrame(body, columns=header)[EXPECTED_COLS].copy()
    else:
        header_mismatch = True
        max_len = max((len(row) for row in body), default=0)
        target_len = max(max_len, len(EXPECTED_COLS))
        padded = [row + [""] * max(0, target_len - len(row)) for row in body]
        if padded:
            df = pd.DataFrame(padded, columns=EXPECTED_COLS)
        else:
            df = pd.DataFrame(columns=EXPECTED_COLS)
    return df, header_mismatch

# -------------------- PREPROCESSAMENTO (Sem Alteração) --------------------

def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).reset_index(drop=True)
    df["VALOR_NUM"] = df["VALOR"].apply(parse_val_str_to_float)
    df["TIPO"] = df["TIPO"].fillna("").astype(str).str.strip()
    mask_empty_tipo = df["TIPO"] == ""
    df.loc[mask_empty_tipo, "TIPO"] = df.loc[mask_empty_tipo, "VALOR_NUM"].apply(lambda v: "Despesa" if v < 0 else "Receita")
    mask_receita = df["TIPO"].str.contains("Receita", case=False, na=False)
    mask_despesa = df["TIPO"].str.contains("Despesa", case=False, na=False)
    df.loc[mask_receita, "VALOR_NUM"] = abs(df.loc[mask_receita, "VALOR_NUM"])
    df.loc[mask_despesa, "VALOR_NUM"] = -abs(df.loc[mask_despesa, "VALOR_NUM"])
    df["CATEGORIA"] = df["CATEGORIA"].fillna("").astype(str).str.strip()
    df["DESCRIÇÃO"] = df["DESCRIÇÃO"].fillna("").astype(str).str.strip()
    df["OBSERVAÇÃO"] = df["OBSERVAÇÃO"].fillna("").astype(str).str.strip()
    def is_mostly_numeric_or_empty_category(s):
        s = str(s)
        if s == "":
            return True
        if s.isdigit() and len(s) < 5:
            return True
        return False
    mask_invalid_cat = df["CATEGORIA"].apply(is_mostly_numeric_or_empty_category)
    df.loc[mask_invalid_cat, "CATEGORIA"] = "NÃO CATEGORIZADO"
    df.loc[df["DESCRIÇÃO"] == "", "DESCRIÇÃO"] = "N/D"
    df.loc[df["OBSERVAÇÃO"] == "", "OBSERVAÇÃO"] = "N/D"
    df = df.sort_values("DATA").reset_index(drop=True)
    df["Saldo Acumulado"] = df["VALOR_NUM"].cumsum()
    df["year_month"] = df["DATA"].dt.to_period("M").astype(str)
    return df

@st.cache_data(ttl=600)
def load_and_preprocess_data() -> Tuple[pd.DataFrame, bool]:
    client = get_gspread_client()
    if not client:
        return pd.DataFrame(columns=EXPECTED_COLS), False
    df_raw, header_mismatch = build_dataframe(load_sheet_values(client))
    if df_raw.empty:
        return df_raw, header_mismatch
    df_processed = preprocess_df(df_raw)
    return df_processed, header_mismatch

# -------------------- PLOTS (Com Modificações) --------------------

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    # Fundo transparente, mas com uma leve cor institucional no plot area para legibilidade
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", height=DEFAULT_CHART_HEIGHT, font_color=INSTITUTIONAL["branco"])
    return fig

def plot_saldo_acumulado(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()
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
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(title_text="Data", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    fig.update_yaxes(title_text="Saldo (R$)", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    return fig

def plot_fluxo_diario(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()
    fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
    cores = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
    fig = go.Figure(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], marker_color=cores))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(title_text="Data", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    fig.update_yaxes(title_text="Valor (R$)", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    return fig

def plot_categoria_barras(df: pd.DataFrame, kind: str = "Receita", category_colors: Dict[str,str]=None) -> go.Figure:
    assert kind in ("Receita", "Despesa")
    if kind == "Receita":
        base = df[df["VALOR_NUM"] > 0]
    else:
        base = df[df["VALOR_NUM"] < 0]
    if base.empty:
        return _get_empty_fig(f"Sem dados de {kind}")
    series = base["VALOR_NUM"].abs().groupby(base["CATEGORIA"]).sum().sort_values(ascending=True)
    cats = list(series.index)
    vals = series.values
    marker_colors = [category_colors.get(c, COLORS["neutral"]) for c in cats] if category_colors else [COLORS["receita"]]*len(cats)
    fig = go.Figure(go.Bar(x=vals, y=cats, orientation='h', marker=dict(color=marker_colors)))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT-10, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(title_text="Valor (R$)", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    fig.update_yaxes(title_text="Categoria")
    return fig

def plot_composicao_barras_horizontal(df: pd.DataFrame, kind: str = "Receita", category_colors: Dict[str,str]=None) -> go.Figure:
    """NOVA FUNÇÃO: Substitui o gráfico de Pizza/Donut por um gráfico de Barras com %"""
    if kind == "Receita":
        series = df[df["VALOR_NUM"] > 0].groupby("CATEGORIA")["VALOR_NUM"].sum()
        color_base = COLORS["receita"]
    else:
        series = (-df[df["VALOR_NUM"] < 0].groupby("CATEGORIA")["VALOR_NUM"].sum())
        color_base = COLORS["despesa"]
    
    if series.empty:
        return _get_empty_fig(f"Sem composição de {kind}")
        
    series = series.sort_values(ascending=True)
    total = series.sum()
    series_pct = (series / total) * 100
    
    cats = series.index.tolist()
    
    # Criar rótulos formatados com Valor e Percentual
    text_labels = [
        f"{money_fmt_br(series.loc[cat])} ({series_pct.loc[cat]:.1f}%)" 
        for cat in cats
    ]
    
    marker_colors = [category_colors.get(c, color_base) for c in cats] if category_colors else [color_base] * len(cats)
    
    fig = go.Figure(go.Bar(
        x=series_pct.values, 
        y=cats, 
        orientation='h', 
        marker=dict(color=marker_colors),
        text=text_labels, # Adiciona os rótulos de valor/percentual
        textposition='outside'
    ))
    
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT-10, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(4,43,81,0.4)", 
        font_color=INSTITUTIONAL["branco"],
        margin=dict(l=10, r=100, t=10, b=10) # Aumenta margem direita para caber o texto
    )
    fig.update_xaxes(
        title_text="Percentual (%)", 
        range=[0, 100], # Range fixo de 0 a 100%
        gridcolor='rgba(255,255,255,0.1)', 
        zerolinecolor='rgba(255,255,255,0.2)'
    )
    fig.update_yaxes(title_text="Categoria")
    return fig

# Funções de plotagem subsequentes (mantidas, mas com ajustes de estilo)

def plot_bubble_transacoes_categoria_y(df: pd.DataFrame, category_colors: Dict[str,str]=None) -> go.Figure:
    if df.empty:
        return _get_empty_fig("Sem transações")
    df_plot = df.copy()
    df_plot["Size"] = df_plot["VALOR_NUM"].abs()
    df_plot["VALOR_FMT"] = df_plot["VALOR_NUM"].apply(money_fmt_br)
    fig = px.scatter(df_plot, x="DATA", y="CATEGORIA", size="Size", color="CATEGORIA",
                     hover_name="DESCRIÇÃO", hover_data={"VALOR_FMT": True, "DATA": False},
                     color_discrete_map=category_colors, size_max=35)
    fig.update_traces(marker=dict(opacity=0.85, line=dict(width=0.6, color='rgba(0,0,0,0.12)')))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(title_text="Data", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    fig.update_yaxes(title_text="Categoria", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    return fig

def plot_bubble_transacoes_valor_y(df: pd.DataFrame, category_colors: Dict[str,str]=None) -> go.Figure:
    if df.empty:
        return _get_empty_fig("Sem transações")
    dfp = df.copy()
    dfp["VALOR_ABS"] = dfp["VALOR_NUM"].abs()
    dfp["VALOR_FMT"] = dfp["VALOR_NUM"].apply(money_fmt_br)
    fig = px.scatter(dfp, x="DATA", y="VALOR_NUM", size="VALOR_ABS", color="CATEGORIA",
                     hover_name="DESCRIÇÃO", hover_data={"VALOR_FMT": True, "DATA": False},
                     size_max=35, color_discrete_map=category_colors)
    fig.update_traces(marker=dict(opacity=0.85, line=dict(width=0.6, color='rgba(0,0,0,0.12)')))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(title_text="Data", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    fig.update_yaxes(title_text="Valor (R$)", gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    return fig

# Funções Candlestick, Heatmap e Boxplot (mantidas, mas com ajustes de estilo)

def prepare_ohlc_period(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if freq == "D":
        period = df["DATA"].dt.to_period("D")
    elif freq == "W":
        period = df["DATA"].dt.to_period("W")
    else:
        period = df["DATA"].dt.to_period("M")
    dfp = df.copy()
    dfp["PERIOD"] = period
    groups = []
    for per, g in dfp.groupby("PERIOD"):
        g_sorted = g.sort_values("DATA")
        open_v = g_sorted.iloc[0]["VALOR_NUM"]
        close_v = g_sorted.iloc[-1]["VALOR_NUM"]
        high_v = g_sorted["VALOR_NUM"].max()
        low_v = g_sorted["VALOR_NUM"].min()
        vol = g_sorted["VALOR_NUM"].abs().sum()
        groups.append({"PERIOD": per, "ts": per.to_timestamp(), "open": open_v, "high": high_v, "low": low_v, "close": close_v, "volume": vol})
    ohlc = pd.DataFrame(groups).sort_values("ts").reset_index(drop=True)
    return ohlc

def plot_candlestick(df: pd.DataFrame, freq: str = "D") -> go.Figure:
    ohlc = prepare_ohlc_period(df, freq)
    if ohlc.empty:
        return _get_empty_fig("Sem dados para candlestick")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.72, 0.28])
    fig.add_trace(go.Candlestick(x=ohlc["ts"], open=ohlc["open"], high=ohlc["high"], low=ohlc["low"], close=ohlc["close"],
                                 increasing_line_color=COLORS["receita"], decreasing_line_color=COLORS["despesa"]), row=1, col=1)
    fig.add_trace(go.Bar(x=ohlc["ts"], y=ohlc["volume"], name="Volume", marker_color=COLORS["neutral"]), row=2, col=1)
    ohlc["sma7"] = ohlc["close"].rolling(window=7, min_periods=1).mean()
    fig.add_trace(go.Scatter(x=ohlc["ts"], y=ohlc["sma7"], mode="lines", name="SMA7", line=dict(color=COLORS["trend"])), row=1, col=1)
    fig.update_layout(height=DEFAULT_CHART_HEIGHT+80, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", xaxis_rangeslider_visible=False, font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(title_text="Período", row=2, col=1, gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1, gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    return fig

def plot_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()
    dfh = df.copy()
    dfh['day'] = dfh['DATA'].dt.day
    dfh['ym'] = dfh['DATA'].dt.to_period('M').astype(str)
    pivot = dfh.groupby(['ym','day'])['VALOR_NUM'].sum().reset_index()
    heat = pivot.pivot(index='ym', columns='day', values='VALOR_NUM').fillna(0)
    fig = go.Figure(data=go.Heatmap(z=heat.values, x=heat.columns, y=heat.index, colorscale='RdBu', reversescale=True,
                                    hovertemplate="Mês: %{y}<br>Dia: %{x}<br>Saldo Diário: %{z:.2f} R$<extra></extra>"))
    fig.update_layout(title='Heatmap Mensal de Saldo Diário', height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(title_text="Dia do Mês")
    fig.update_yaxes(title_text="Mês")
    return fig

def plot_boxplot_by_category(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()
    dfp = df.copy()
    dfp['VALOR_ABS'] = dfp['VALOR_NUM'].abs()
    fig = px.box(dfp, x='CATEGORIA', y='VALOR_ABS', points='outliers', color='TIPO', color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]})
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", 
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), font_color=INSTITUTIONAL["branco"])
    fig.update_xaxes(tickangle=-45)
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.1)', zerolinecolor='rgba(255,255,255,0.2)')
    return fig

# -------------------- SIDEBAR E FILTROS (Sem Alteração) --------------------

def sidebar_filters_and_controls(df: pd.DataFrame) -> Tuple[str, Dict]:
    st.sidebar.title("Dashboard Financeiro Caec")
    st.sidebar.markdown("---")
    page = st.sidebar.selectbox("Altere a visualização", options=["Resumo Financeiro", "Dashboard Detalhado"], key="sb_page")
    toggle_multi = st.sidebar.checkbox("Ativar filtro avançado (múltipla seleção e período)", value=False, key="sb_toggle_multi")
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

# -------------------- KPIs (Com Alterações Mínimas) --------------------

def _sum_period(df: pd.DataFrame, start_dt: datetime, end_dt: datetime, tipo: str = "all") -> float:
    if df.empty:
        return 0.0
    mask = (df["DATA"] >= start_dt) & (df["DATA"] <= end_dt)
    s = df.loc[mask, "VALOR_NUM"]
    if tipo == "receita":
        return s[s > 0].sum()
    elif tipo == "despesa":
        return s[s < 0].sum()  # negativo
    else:
        return s.sum()

def _kpi_delta_text_and_color(curr: float, prev: float, positive_is_good: bool = True) -> Tuple[str, str]:
    """
    Retorna (texto_delta, delta_color) para st.metric.
    positive_is_good=True: aumento é bom (verde). False: aumento é ruim (despesa).
    """
    diff = curr - prev
    pct = (diff / abs(prev)) * 100 if abs(prev) > 0.0001 else (100.0 if abs(diff) > 0.0 else 0.0)
    sign = "+" if diff >= 0 else "-"
    absdiff = abs(diff)
    txt = f"{sign}{money_fmt_br(absdiff)} ({sign}{pct:.0f}%)"
    if diff == 0:
        delta_color = "off"
    else:
        increased = diff > 0
        if increased:
            delta_color = "normal" if positive_is_good else "inverse"
        else:
            delta_color = "inverse" if positive_is_good else "normal"
    return txt, delta_color

def render_kpi_cards(df: pd.DataFrame):
    """
    Renderiza 3 KPIs com delta baseado nos últimos 30 dias vs 30 dias anteriores.
    Ordem visual: Receita (verde), Despesa (vermelho), Saldo (azul).
    """
    if df.empty:
        st.info("Sem dados para KPIs")
        return

    # Usar data máxima do DF filtrado para definir o período
    end = df["DATA"].max()
    last30_end = pd.to_datetime(end)
    last30_start = last30_end - pd.Timedelta(days=29)
    prev30_end = last30_start - pd.Timedelta(seconds=1)
    prev30_start = prev30_end - pd.Timedelta(days=29)

    receita_curr = _sum_period(df, last30_start, last30_end, tipo="receita")
    receita_prev = _sum_period(df, prev30_start, prev30_end, tipo="receita")
    despesa_curr = _sum_period(df, last30_start, last30_end, tipo="despesa")
    despesa_prev = _sum_period(df, prev30_start, prev30_end, tipo="despesa")
    saldo_curr = receita_curr + despesa_curr
    saldo_prev = receita_prev + despesa_prev

    txt_rec_delta, color_rec = _kpi_delta_text_and_color(receita_curr, receita_prev, positive_is_good=True)
    txt_dep_delta, color_dep = _kpi_delta_text_and_color(-despesa_curr, -despesa_prev, positive_is_good=False)
    txt_saldo_delta, color_saldo = _kpi_delta_text_and_color(saldo_curr, saldo_prev, positive_is_good=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        _render_kpi_card_html(
            title="Receita (últimos 30d)",
            value=money_fmt_br(receita_curr),
            delta=txt_rec_delta,
            value_color=COLORS["receita"],
            delta_color=color_rec
        )
    with c2:
        _render_kpi_card_html(
            title="Despesa (últimos 30d)",
            value=money_fmt_br(abs(despesa_curr)),
            delta=txt_dep_delta,
            value_color=COLORS["despesa"],
            delta_color=color_dep
        )
    with c3:
        _render_kpi_card_html(
            title="Saldo (últimos 30d)",
            value=money_fmt_br(saldo_curr),
            delta=txt_saldo_delta,
            value_color=COLORS["saldo"],
            delta_color=color_saldo
        )

def _render_kpi_card_html(title: str, value: str, delta: str, value_color: str, delta_color: str):
    arrow = "—"
    arrow_color = "#bfc9d3"
    if delta_color == "normal":
        arrow = "▲"
        arrow_color = COLORS["receita"]
    elif delta_color == "inverse":
        arrow = "▼"
        arrow_color = COLORS["despesa"]
    html = f"""
    <div class="kpi-card">
    <div class="kpi-label">{title}</div>
    <div class="kpi-value" style="color:{value_color};">{value}</div>
    <div class="kpi-delta"><span style="color:{arrow_color}; font-weight:700;">{arrow}</span><span style="color:#bfc9d3;"> {delta}</span></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# -------------------- TABELA / EXPORT (Sem Alteração) --------------------

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

# -------------------- MAIN (Com Alterações) --------------------

def main():
    st.markdown(MINIMAL_CSS, unsafe_allow_html=True)
    st.title("Dashboard Financeiro Caec")

    try:
        df, header_mismatch = load_and_preprocess_data()
    except Exception as e:
        st.error(f"Erro ao carregar os dados: {e}")
        st.stop()

    if header_mismatch:
        st.warning("Cabeçalho da planilha (Linha 2) não corresponde ao esperado. Tentando carregar mesmo assim.")

    if df.empty:
        st.sidebar.markdown("---")
        st.sidebar.caption("CAEC © 2025")
        st.warning("Planilha vazia ou erro ao importar dados. Verifique a planilha/credenciais.")
        return

    page, filters = sidebar_filters_and_controls(df)
    df_filtered = apply_filters(df, filters)

    category_colors = get_category_color_map(df_filtered)

    # KPIs refatorados (últimos 30 dias)
    render_kpi_cards(df_filtered)
    st.markdown("---")

    if page == "Resumo Financeiro":
        st.subheader("Evolução do Saldo Acumulado")
        st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(plot_saldo_acumulado(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_saldo_line_resumo")
        st.markdown('</div>', unsafe_allow_html=True)

        st.subheader("Fluxo de Caixa Diário")
        st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(plot_fluxo_diario(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_fluxo_bar_resumo")
        st.markdown('</div>', unsafe_allow_html=True)

        st.subheader("Lançamentos Recentes (Últimos 10)")
        recent = df_filtered.sort_values("DATA", ascending=False).head(10)
        render_table(recent, key="table_recent_resumo")

        csv = _prepare_export_csv(df_filtered)
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_resumo_export.csv", mime="text/csv", key="download_resumo")

    else:
        tab_normais, tab_avancados, tab_tabela = st.tabs(["📊 Gráficos Principais", "📈 Análise Avançada", "📋 Tabela Completa"])
        with tab_normais:
            st.subheader("Análise por Categoria e Composição")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("##### Receita por Categoria (Barras)")
                st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
                st.plotly_chart(plot_categoria_barras(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_rec_bar_comb")
                st.markdown('</div>', unsafe_allow_html=True)
                
                st.markdown("##### Composição Percentual de Receita")
                st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
                # **FUNÇÃO SUBSTITUÍDA**
                st.plotly_chart(plot_composicao_barras_horizontal(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_pie_rec_comb")
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown("##### Despesa por Categoria (Barras)")
                st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
                st.plotly_chart(plot_categoria_barras(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_dep_bar_comb")
                st.markdown('</div>', unsafe_allow_html=True)
                
                st.markdown("##### Composição Percentual de Despesa")
                st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
                # **FUNÇÃO SUBSTITUÍDA**
                st.plotly_chart(plot_composicao_barras_horizontal(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_pie_dep_comb")
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("Visão Temporal de Lançamentos (por Categoria)")
            st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(plot_bubble_transacoes_categoria_y(df_filtered, category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_bubble_cat_y")
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("---")
            st.subheader("Visão Detalhada de Transações")
            st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(plot_bubble_transacoes_valor_y(df_filtered, category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_bubble_valor_y")
            st.markdown('</div>', unsafe_allow_html=True)

        with tab_avancados:
            agg_freq = st.selectbox("Agregação Candlestick", options=[("Diário","D"), ("Semanal","W"), ("Mensal","M")], format_func=lambda x: x[0], key="sb_candle_freq")
            freq_code = agg_freq[1]
            st.subheader(f"Análise Candlestick ({agg_freq[0]}) e Volume")
            st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(plot_candlestick(df_filtered, freq=freq_code), use_container_width=True, config={'displayModeBar': False}, key=f"chart_candlestick_{freq_code}")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Fluxo Diário com Média Móvel (14 dias)")
                fluxo = df_filtered.groupby(df_filtered["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
                fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
                fluxo["sma14"] = fluxo["VALOR_NUM"].rolling(window=14, min_periods=1).mean()
                fig_ma = go.Figure()
                cores_fluxo = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
                fig_ma.add_trace(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], name="Fluxo Diário", marker_color=cores_fluxo))
                fig_ma.add_trace(go.Scatter(x=fluxo["DATA"], y=fluxo["sma14"], mode="lines", name="SMA14 (14 dias)", line=dict(color=COLORS["trend"])))
                fig_ma.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(4,43,81,0.4)", font_color=INSTITUTIONAL["branco"])
                st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
                st.plotly_chart(fig_ma, use_container_width=True, config={'displayModeBar': False}, key="chart_sma14_avancado")
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.subheader("Distribuição de Valores por Categoria (Boxplot)")
                st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
                st.plotly_chart(plot_boxplot_by_category(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_box_avancado")
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("Heatmap de Saldo Diário")
            st.markdown(f'<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(plot_monthly_heatmap(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_heatmap_avancado")
            st.markdown('</div>', unsafe_allow_html=True)

        with tab_tabela:
            st.subheader("Todos os Lançamentos (Filtro Atual)")
            render_table(df_filtered, key="table_full_detalhado")
            csv = _prepare_export_csv(df_filtered)
            st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_full_export.csv", mime="text/csv", key="download_full")

    st.markdown("---")
    st.markdown(f"<div style='text-align:center;color:#cbd5e1; font-family: {FONT_SECONDARY};'>CAEC © 2025 — Criado e administrado pela diretoria de Administração Comercial e Financeiro — <strong>by Rick</strong></div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
