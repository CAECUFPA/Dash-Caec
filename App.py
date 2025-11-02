from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from sklearn.linear_model import LinearRegression

# Google Sheets dependencies (assumir instaladas no ambiente)
try:
    import gspread
    from gspread.client import Client as GSpreadClient
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    # Classes de placeholder para ambientes sem as dependências
    class GSpreadClient: pass
    class ServiceAccountCredentials:
        @staticmethod
        def from_json_keyfile_dict(a, b): return None

# -------------------- CONFIGURAÇÃO GERAL E CSS CORRIGIDO (Tema Dinâmico, Glassmorphism e Cards) --------------------

EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

INSTITUTIONAL = {
    "azul": "#042b51",    # base institucional (Original)
    "amarelo": "#f6d138", # acento institucional (Tendência)
}
COLORS = {
    "receita": "#2ca02c",
    "despesa": "#d62728",
    "saldo": "#1f77b4",
    "trend": INSTITUTIONAL["amarelo"],
    "neutral": "#6c757d",
}

DEFAULT_CHART_HEIGHT = 360

# CSS para o Blueprint (Linhas de 1px a cada 20px)
BLUEPRINT_BACKGROUND_CSS = """
  background-image:
    linear-gradient(0deg, var(--bg-line-color) 1px, transparent 1px),
    linear-gradient(90deg, var(--bg-line-color) 1px, transparent 1px);
  background-size: 20px 20px;
  background-position: -1px -1px;
"""

def get_dynamic_css() -> str:
    """
    Gera o CSS dinâmico. CORRIGIDO: Cores de H1 e Bordas de Cards/Gráficos.
    """
    
    css_vars = f"""
    @import url('https://fonts.googleapis.com/css2?family=Anton&family=Six+Caps&family=League+Spartan&family=Open+Sans:wght@400;700&display=swap');

    :root {{
      --caec-azul: {INSTITUTIONAL['azul']};
      --caec-amarelo: {INSTITUTIONAL['amarelo']};
      --kpi-receita: {COLORS['receita']};
      --kpi-despesa: {COLORS['despesa']};
      --kpi-saldo: {COLORS['saldo']};
      
      /* Cores base para Light Mode */
      --bg-line-color-light: rgba(200, 200, 200, 0.8);
      --sidebar-bg-transparent: rgba(255, 255, 255, 0.15); 
      --sidebar-border: rgba(200, 200, 200, 0.8);
      --bg-line-color: var(--bg-line-color-light);
      --card-padding: 18px; 
      --h1-color: #000000; /* Preto forte para Light Mode (Solicitado) */
      --kpi-label-color: var(--st-font-color); /* Usa a cor de texto padrão do tema (Escuro no Light Mode) */
    }}

    @media (prefers-color-scheme: dark) {{
        :root {{
            /* Cores base para Dark Mode */
            --bg-line-color-dark: rgba(44, 54, 65, 0.8); 
            --sidebar-bg-transparent: rgba(11, 20, 26, 0.4); 
            --sidebar-border: rgba(44, 54, 65, 0.8);
            --bg-line-color: var(--bg-line-color-dark);
            --h1-color: #FFFFFF; /* Branco forte para Dark Mode (Solicitado) */
            --kpi-label-color: var(--st-font-color-weak); /* Usa a cor de texto fraca do tema (Claro no Dark Mode) */
        }}
    }}
    
    /* ------------------------------------------------------------------- */
    /* 1. Glassmorphism na Sidebar */
    /* ------------------------------------------------------------------- */

    /* Seletores para o contêiner principal da sidebar */
    .st-emotion-cache-vk34a3, .st-emotion-cache-1cypk8n, .st-emotion-cache-1d371w8 {{ 
        background-color: var(--sidebar-bg-transparent) !important; 
        backdrop-filter: blur(12px) saturate(180%); 
        -webkit-backdrop-filter: blur(12px) saturate(180%);
        border-right: 1px solid var(--sidebar-border) !important; 
    }}

    /* Garante que o texto da sidebar use a cor de fonte padrão do tema */
    .st-emotion-cache-1cypk8n *, .st-emotion-cache-1d371w8 * {{
        color: var(--st-font-color) !important; 
        font-family: 'Open Sans', sans-serif; 
    }}

    /* ------------------------------------------------------------------- */
    /* 2. Aplicação de Estilos Gerais, Blueprint e Tipografia */
    /* ------------------------------------------------------------------- */

    .stApp {{
      background-color: var(--st-bgs1);
      color: var(--st-font-color);
      font-family: 'Open Sans', sans-serif; 
      {BLUEPRINT_BACKGROUND_CSS} 
    }}

    /* CORRIGIDO: Título H1 com cor dinâmica (preto/branco) - usa var(--h1-color) */
    h1 {{ 
        margin-top: 0rem; 
        margin-bottom: 1rem; 
        color: var(--h1-color) !important;
    }}
    
    /* Títulos e KPI Value */
    h2, h3, h4, .st-emotion-cache-e67m5x, .kpi-value {{ 
        font-family: 'Anton', 'Six Caps', 'League-Spartan', sans-serif;
    }}
    
    /* ------------------------------------------------------------------- */
    /* 3. Estilos de CARD para Gráficos e Tabelas (FUNDO e BORDAS ARREDONDADAS) */
    /* ------------------------------------------------------------------- */

    /* Seletores para os containers de COLUMNS, TABS e CONTAINER (que encapsulam os gráficos/tabelas) */
    .st-emotion-cache-1v4f50, .st-emotion-cache-1n743z1, .st-emotion-cache-1d9g9l8, .st-emotion-cache-0 {{
        background: var(--st-bgs2); /* Fundo sólido, coeso com o tema (Solicitado) */
        border: 1px solid var(--st-bgs3);
        border-radius: 12px; /* Arredondamento (Solicitado) */
        padding: var(--card-padding); 
        margin-bottom: 1.5rem; 
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15); /* Sombra mais forte para destacar */
        transition: all 0.2s ease-in-out;
    }}
    
    /* Regras para limpar cards aninhados e garantir a harmonia */
    .st-emotion-cache-1d9g9l8 .st-emotion-cache-1d9g9l8, .st-emotion-cache-0 .st-emotion-cache-0,
    .st-emotion-cache-1v4f50 .st-emotion-cache-1v4f50, .st-emotion-cache-1n743z1 .st-emotion-cache-1n743z1 {{
        background: transparent;
        border: none;
        padding: 0;
        margin-bottom: 0;
        box-shadow: none;
    }}

    /* Ajustar o container que envolve os KPIs, removendo o estilo de card nele (para não ficar aninhado) */
    .st-emotion-cache-1d9g9l8:has(.kpi-card) {{
        background: transparent;
        border: none;
        padding: 0;
        margin-bottom: 0;
        box-shadow: none;
    }}

    /* CORRIGIDO: Fundo dos Gráficos (Plotly) */
    /* Define um fundo SÓLIDO para a área de plotagem e arredonda (Solicitado) */
    /* Isso garante a cor de fundo coesa e anula a opacidade */
    .modebar, .plotly, .js-plotly-plot, .plotly-container {{
      background-color: var(--st-bgs2) !important;
      border-radius: 10px; /* Arredonda o fundo do gráfico (Solicitado) */
    }}
    .js-plotly-plot {{ 
        overflow: hidden; 
    }}

    /* ------------------------------------------------------------------- */
    /* 4. Estilos de KPI (MANTIDOS COM CORREÇÃO DE COR) */
    /* ------------------------------------------------------------------- */

    .kpi-card {{
      background: var(--st-bgs2); 
      border: 1px solid var(--st-bgs3);
      border-radius: 12px; /* Borda arredondada também no KPI */
      padding: 12px 14px;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); /* Sombra suave */
      width: 100%;
      height: 120px; 
      display: flex; 
      flex-direction: column;
      justify-content: space-between; 
      overflow: hidden; 
    }}
    /* CORRIGIDO: Usa var(--kpi-label-color) que é dinâmico, mas tende a ser escuro no Light Mode e fraco no Dark Mode */
    .kpi-label, .kpi-delta {{ 
        color: var(--kpi-label-color); 
        font-size: 13px;
    }}
    .kpi-value {{ 
        font-size: 26px; 
        font-weight:700; 
    }}

    /* Footer */
    /* CORRIGIDO: Usa var(--st-font-color-weak) para o footer */
    footer {{ color: var(--st-font-color-weak); text-align:center; padding-top:10px; }}
    """
    return f"<style>{css_vars}</style>"

st.set_page_config(page_title="Dashboard Financeiro Caec", layout="wide", initial_sidebar_state="expanded",
                   menu_items={"About": "Dashboard Financeiro Caec © 2025"})

# -------------------- UTILITÁRIOS E PRÉ-PROCESSAMENTO (MANTIDOS) --------------------

def parse_val_str_to_float(val) -> float:
    if pd.isna(val) or val == "": return 0.0
    s = str(val).strip()
    neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-"):
        neg = True
        s = s.strip("()-")
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try: v = float(s)
    except Exception: return 0.0
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_category_color_map(df: pd.DataFrame) -> Dict[str, str]:
    if df is None or df.empty: return {}
    cats = sorted(df["CATEGORIA"].dropna().unique())
    base = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
        "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]
    palette = [INSTITUTIONAL["azul"], INSTITUTIONAL["amarelo"]] + base
    colors = [palette[i % len(palette)] for i in range(len(cats))]
    return {cat: colors[i] for i, cat in enumerate(cats)}

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[GSpreadClient]:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        return gspread.authorize(creds)
    except Exception: return None

def load_sheet_values(client: GSpreadClient) -> List[List[str]]:
    if not client: return []
    try:
        spreadsheet_name = st.secrets["SPREADSHEET_NAME"]
        worksheet_index = int(st.secrets.get("WORKSHEET_INDEX", 0))
        sh = client.open(spreadsheet_name)
        ws = sh.get_worksheet(worksheet_index)
        return ws.get_all_values()
    except Exception as e: return []

def build_dataframe(values: List[List[str]]) -> Tuple[pd.DataFrame, bool]:
    if not values or len(values) < 2: return pd.DataFrame(columns=EXPECTED_COLS), False
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
        if padded: df = pd.DataFrame(padded, columns=EXPECTED_COLS)
        else: df = pd.DataFrame(columns=EXPECTED_COLS)
    return df, header_mismatch

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
        if s == "": return True
        if s.isdigit() and len(s) < 5: return True
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
        # Mock data para o caso de erro ou falta de credenciais
        mock_data = {
            "DATA": [datetime.now() - timedelta(days=d) for d in range(60)] * 2,
            "TIPO": ["Receita"] * 60 + ["Despesa"] * 60,
            "CATEGORIA": ["Mensalidade", "Marketing", "Evento", "Aluguel", "NÃO CATEGORIZADO"] * 24,
            "DESCRIÇÃO": [f"Item {i}" for i in range(120)],
            "VALOR": [f"{1000 * (1 if i % 2 == 0 else -1)}" for i in range(120)],
            "OBSERVAÇÃO": ["N/D"] * 120,
        }
        df_full = preprocess_df(pd.DataFrame(mock_data))
        return df_full, False

    df_raw, header_mismatch = build_dataframe(load_sheet_values(client))
    if df_raw.empty: return df_raw, header_mismatch
    df_processed = preprocess_df(df_raw)
    return df_processed, header_mismatch

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

# -------------------- PLOTS (AJUSTADOS - Fundo Plotly Transparente para herdar do Card/CSS) --------------------

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    fig = go.Figure()
    # Garante que o fundo do Plotly seja transparente para que o fundo do card CSS funcione
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(color="var(--st-font-color-weak)"))
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
    # Fundo transparente para herdar do card (Solicitado)
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
    # Fundo transparente para herdar do card (Solicitado)
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
    # Fundo transparente para herdar do card (Solicitado)
    fig.update_layout(height=DEFAULT_CHART_HEIGHT-10, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      title=f'{kind} por Categoria (Barras)') 
    fig.update_xaxes(title_text="Valor (R$)")
    fig.update_yaxes(title_text="Categoria")
    return fig

def plot_categoria_barras_pct(df: pd.DataFrame, kind: str = "Receita", category_colors: Dict[str,str]=None) -> go.Figure:
    """NOVO: Gráfico de barras verticais com porcentagem de composição."""
    assert kind in ("Receita", "Despesa")
    base = df[df["VALOR_NUM"] > 0] if kind == "Receita" else df[df["VALOR_NUM"] < 0]
    if base.empty: return _get_empty_fig(f"Sem dados de {kind}")
    
    df_plot = base["VALOR_NUM"].abs().groupby(base["CATEGORIA"]).sum().reset_index()
    df_plot.columns = ["CATEGORIA", "VALOR"]
    total = df_plot["VALOR"].sum()
    df_plot["PERCENT"] = (df_plot["VALOR"] / total) * 100
    df_plot = df_plot.sort_values("PERCENT", ascending=False)
    
    # Formatação do hover text
    df_plot["HOVER_TEXT"] = df_plot.apply(
        lambda row: f"**{row['CATEGORIA']}**<br>Valor: {money_fmt_br(row['VALOR'])}<br>% Total: {row['PERCENT']:.1f}%", axis=1
    )
    
    marker_colors = [category_colors.get(c, COLORS["neutral"]) for c in df_plot["CATEGORIA"]]

    fig = go.Figure(go.Bar(
        x=df_plot["CATEGORIA"], 
        y=df_plot["PERCENT"], 
        marker_color=marker_colors,
        hovertemplate="%{customdata}<extra></extra>",
        customdata=df_plot["HOVER_TEXT"]
    ))
    
    # Fundo transparente para herdar do card (Solicitado)
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        title=f'Composição de {kind} (Porcentagem)',
        xaxis_tickangle=-45
    )
    fig.update_xaxes(title_text="Categoria")
    fig.update_yaxes(title_text="Porcentagem (%)", ticksuffix="%")
    return fig

def plot_bubble_transacoes_categoria_y(df: pd.DataFrame, category_colors: Dict[str,str]=None) -> go.Figure:
    if df.empty: return _get_empty_fig("Sem transações")
    df_plot = df.copy()
    df_plot["Size"] = df_plot["VALOR_NUM"].abs()
    df_plot["VALOR_FMT"] = df_plot["VALOR_NUM"].apply(money_fmt_br)
    fig = px.scatter(df_plot, x="DATA", y="CATEGORIA", size="Size", color="CATEGORIA",
                     hover_name="DESCRIÇÃO", hover_data={"VALOR_FMT": True, "DATA": False},
                     color_discrete_map=category_colors, size_max=35)
    # Opacidade leve para os marcadores (bolhas), mas fundo transparente (Solicitado)
    fig.update_traces(marker=dict(opacity=0.85, line=dict(width=0.6, color='rgba(0,0,0,0.12)')))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Categoria")
    return fig

def plot_bubble_transacoes_valor_y(df: pd.DataFrame, category_colors: Dict[str,str]=None) -> go.Figure:
    if df.empty: return _get_empty_fig("Sem transações")
    dfp = df.copy()
    dfp["VALOR_ABS"] = dfp["VALOR_NUM"].abs()
    dfp["VALOR_FMT"] = dfp["VALOR_NUM"].apply(money_fmt_br)
    fig = px.scatter(dfp, x="DATA", y="VALOR_NUM", size="VALOR_ABS", color="CATEGORIA",
                     hover_name="DESCRIÇÃO", hover_data={"VALOR_FMT": True, "DATA": False},
                     size_max=35, color_discrete_map=category_colors)
    # Opacidade leve para os marcadores (bolhas), mas fundo transparente (Solicitado)
    fig.update_traces(marker=dict(opacity=0.85, line=dict(width=0.6, color='rgba(0,0,0,0.12)')))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

def prepare_ohlc_period(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    if df.empty: return pd.DataFrame()
    period = df["DATA"].dt.to_period(freq)
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
    if ohlc.empty: return _get_empty_fig("Sem dados para candlestick")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.72, 0.28])
    fig.add_trace(go.Candlestick(x=ohlc["ts"], open=ohlc["open"], high=ohlc["high"], low=ohlc["low"], close=ohlc["close"],
                                 increasing_line_color=COLORS["receita"], decreasing_line_color=COLORS["despesa"]), row=1, col=1)
    fig.add_trace(go.Bar(x=ohlc["ts"], y=ohlc["volume"], name="Volume", marker_color=COLORS["neutral"]), row=2, col=1)
    ohlc["sma7"] = ohlc["close"].rolling(window=7, min_periods=1).mean()
    fig.add_trace(go.Scatter(x=ohlc["ts"], y=ohlc["sma7"], mode="lines", name="SMA7", line=dict(color=COLORS["trend"])), row=1, col=1)
    # Fundo transparente para herdar do card (Solicitado)
    fig.update_layout(height=DEFAULT_CHART_HEIGHT+80, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_rangeslider_visible=False)
    fig.update_xaxes(title_text="Período", row=2, col=1)
    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig

def plot_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig()
    dfh = df.copy()
    dfh['day'] = dfh['DATA'].dt.day
    dfh['ym'] = dfh['DATA'].dt.to_period('M').astype(str)
    pivot = dfh.groupby(['ym','day'])['VALOR_NUM'].sum().reset_index()
    heat = pivot.pivot(index='ym', columns='day', values='VALOR_NUM').fillna(0)
    fig = go.Figure(data=go.Heatmap(z=heat.values, x=heat.columns, y=heat.index, colorscale='RdBu', reversescale=True,
                                    hovertemplate="Mês: %{y}<br>Dia: %{x}<br>Saldo Diário: %{z:.2f} R$<extra></extra>"))
    # Fundo transparente para herdar do card (Solicitado)
    fig.update_layout(title='Heatmap Mensal de Saldo Diário', height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Dia do Mês")
    fig.update_yaxes(title_text="Mês")
    return fig

def plot_boxplot_by_category(df: pd.DataFrame) -> go.Figure:
    if df.empty: return _get_empty_fig()
    dfp = df.copy()
    dfp['VALOR_ABS'] = dfp['VALOR_NUM'].abs()
    fig = px.box(dfp, x='CATEGORIA', y='VALOR_ABS', points='outliers', color='TIPO', color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]})
    # Fundo transparente para herdar do card (Solicitado)
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(tickangle=-45)
    return fig

# -------------------- SIDEBAR E FILTROS (MANTIDOS) --------------------

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

# -------------------- KPIS (MANTIDOS) --------------------

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

def _render_kpi_card_html(title: str, value: str, delta: str, value_color_css_var: str, delta_color: str):
    arrow = "—"
    arrow_color = "var(--kpi-label-color)" # Usa a cor do label/delta
    if delta_color == "normal":
        arrow = "▲"
        arrow_color = "var(--kpi-receita)"
    elif delta_color == "inverse":
        arrow = "▼"
        arrow_color = "var(--kpi-despesa)"
    
    html = f"""
    <div class="kpi-card">
      <div class="kpi-label">{title}</div>
      <div class="kpi-value" style="color:{value_color_css_var};">{value}</div>
      <div class="kpi-delta"><span style="color:{arrow_color}; font-weight:700;">{arrow}</span><span style="color:var(--kpi-label-color);"> {delta}</span></div>
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
    last30_end = pd.to_datetime(end)
    last30_start = last30_end - pd.Timedelta(days=29)
    prev30_end = last30_start - pd.Timedelta(seconds=1)
    prev30_start = prev30_end - pd.Timedelta(days=29)

    receita_curr = _sum_period(df_full, last30_start, last30_end, tipo="receita")
    receita_prev = _sum_period(df_full, prev30_start, prev30_end, tipo="receita")
    despesa_curr = _sum_period(df_full, last30_start, last30_end, tipo="despesa")
    despesa_prev = _sum_period(df_full, prev30_start, prev30_end, tipo="despesa")

    txt_rec_delta, color_rec = _kpi_delta_text_and_color(receita_curr, receita_prev, positive_is_good=True)
    txt_dep_delta, color_dep = _kpi_delta_text_and_color(-despesa_curr, -despesa_prev, positive_is_good=False)
    saldo_curr = receita_curr + despesa_curr
    saldo_prev = receita_prev + despesa_prev
    txt_saldo_delta, color_saldo = _kpi_delta_text_and_color(saldo_curr, saldo_prev, positive_is_good=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        _render_kpi_card_html(
            title="Receita Total (Período Filtrado)",
            value=money_fmt_br(receita_filtrada),
            delta=f"Últimos 30d: {txt_rec_delta}",
            value_color_css_var="var(--kpi-receita)", 
            delta_color=color_rec
        )
    with c2:
        _render_kpi_card_html(
            title="Despesa Total (Período Filtrado)",
            value=money_fmt_br(abs(despesa_filtrada)),
            delta=f"Últimos 30d: {txt_dep_delta}",
            value_color_css_var="var(--kpi-despesa)",
            delta_color=color_dep
        )
    with c3:
        _render_kpi_card_html(
            title="Saldo Total (Período Filtrado)",
            value=money_fmt_br(saldo_filtrado),
            delta=f"Últimos 30d: {txt_saldo_delta}",
            value_color_css_var="var(--kpi-saldo)", 
            delta_color=color_saldo
        )

# -------------------- TABELA / EXPORT (MANTIDOS) --------------------

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


# -------------------- MAIN FUNCTION --------------------

def main():
    # CORRIGIDO: Injeção de CSS no topo
    st.markdown(get_dynamic_css(), unsafe_allow_html=True)
    
    # H1 usará a cor dinâmica definida no CSS (preto no light mode, branco no dark mode)
    st.title("Dashboard Financeiro Caec")

    try:
        df_full, header_mismatch = load_and_preprocess_data()
    except Exception as e:
        # Mock data se a importação falhar
        mock_data = {
            "DATA": [datetime.now() - timedelta(days=d) for d in range(60)] * 2,
            "TIPO": ["Receita"] * 60 + ["Despesa"] * 60,
            "CATEGORIA": ["Mensalidade", "Marketing", "Evento", "Aluguel", "NÃO CATEGORIZADO"] * 24,
            "DESCRIÇÃO": [f"Item {i}" for i in range(120)],
            "VALOR": [f"{1000 * (1 if i % 2 == 0 else -1)}" for i in range(120)],
            "OBSERVAÇÃO": ["N/D"] * 120,
        }
        df_full = preprocess_df(pd.DataFrame(mock_data))
        header_mismatch = False
    
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
        
        # CARD 1: Saldo Acumulado
        # st.container() herdará o estilo de card (fundo coeso e arredondado) do CSS
        with st.container():
            st.subheader("Evolução do Saldo Acumulado")
            st.plotly_chart(plot_saldo_acumulado(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_saldo_line_resumo")

        # CARD 2: Fluxo de Caixa Diário
        with st.container():
            st.subheader("Fluxo de Caixa Diário")
            st.plotly_chart(plot_fluxo_diario(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_fluxo_bar_resumo")

        # CARD 3: Lançamentos Recentes
        with st.container():
            st.subheader("Lançamentos Recentes (Últimos 10)")
            recent = df_filtered.sort_values("DATA", ascending=False).head(10)
            render_table(recent, key="table_recent_resumo")
            st.markdown("---") 
            csv = _prepare_export_csv(df_filtered)
            st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_resumo_export.csv", mime="text/csv", key="download_resumo")


    else:
        # Garante que o container de tabs use o estilo de card
        tab_normais, tab_avancados, tab_tabela = st.tabs(["📊 Gráficos Principais", "📈 Análise Avançada", "📋 Tabela Completa"])
        
        with tab_normais:
            
            # CARD 1.1 e 1.2: Barras de Valores (Mantidas)
            with st.container():
                st.markdown("### 💰 Composição Financeira por Categoria (Valores Absolutos)")
                col1, col2 = st.columns(2)
                with col1:
                    st.plotly_chart(plot_categoria_barras(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_rec_bar_comb")
                with col2:
                    st.plotly_chart(plot_categoria_barras(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_dep_bar_comb")

            # CARD 2.1 e 2.2: Barras de Porcentagem (NOVO: Substitui Treemap)
            with st.container():
                st.markdown("### 📈 Composição Financeira por Categoria (Porcentagem)")
                col3, col4 = st.columns(2)
                with col3:
                    st.plotly_chart(plot_categoria_barras_pct(df_filtered, kind="Receita", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_rec_bar_pct")
                with col4:
                    st.plotly_chart(plot_categoria_barras_pct(df_filtered, kind="Despesa", category_colors=category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_dep_bar_pct")

            # CARD 3: Visão Temporal Categoria Y
            with st.container():
                st.subheader("Visão Temporal de Lançamentos (por Categoria)")
                st.plotly_chart(plot_bubble_transacoes_categoria_y(df_filtered, category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_bubble_cat_y")

            # CARD 4: Visão Detalhada Valor Y
            with st.container():
                st.subheader("Visão Detalhada de Transações")
                st.plotly_chart(plot_bubble_transacoes_valor_y(df_filtered, category_colors), use_container_width=True, config={'displayModeBar': False}, key="chart_bubble_valor_y")

        with tab_avancados:
            
            # CARD 1: Candlestick
            with st.container():
                agg_freq = st.selectbox("Agregação Candlestick", options=[("Diário","D"), ("Semanal","W"), ("Mensal","M")], format_func=lambda x: x[0], key="sb_candle_freq_adv")
                freq_code = agg_freq[1]
                st.subheader(f"Análise Candlestick ({agg_freq[0]}) e Volume")
                st.plotly_chart(plot_candlestick(df_filtered, freq=freq_code), use_container_width=True, config={'displayModeBar': False}, key=f"chart_candlestick_{freq_code}")

            # CARD 2.1 e 2.2: Fluxo/SMA e Boxplot
            col1, col2 = st.columns(2)
            with col1:
                with st.container():
                    st.subheader("Fluxo Diário com Média Móvel (14 dias)")
                    fluxo = df_filtered.groupby(df_filtered["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
                    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
                    fluxo["sma14"] = fluxo["VALOR_NUM"].rolling(window=14, min_periods=1).mean()
                    fig_ma = go.Figure()
                    cores_fluxo = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
                    fig_ma.add_trace(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], name="Fluxo Diário", marker_color=cores_fluxo))
                    fig_ma.add_trace(go.Scatter(x=fluxo["DATA"], y=fluxo["sma14"], mode="lines", name="SMA14 (14 dias)", line=dict(color=COLORS["trend"])))
                    # Fundo transparente para herdar do card (Solicitado)
                    fig_ma.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_ma, use_container_width=True, config={'displayModeBar': False}, key="chart_sma14_avancado")
            with col2:
                with st.container():
                    st.subheader("Distribuição de Valores por Categoria (Boxplot)")
                    st.plotly_chart(plot_boxplot_by_category(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_box_avancado")

            # CARD 3: Heatmap
            with st.container():
                st.subheader("Heatmap de Saldo Diário")
                st.plotly_chart(plot_monthly_heatmap(df_filtered), use_container_width=True, config={'displayModeBar': False}, key="chart_heatmap_avancado")

        with tab_tabela:
            # CARD 4: Tabela Completa
            with st.container():
                st.subheader("Todos os Lançamentos (Filtro Atual)")
                render_table(df_filtered, key="table_full_detalhado")
                st.markdown("---") 
                csv = _prepare_export_csv(df_filtered)
                st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_full_export.csv", mime="text/csv", key="download_full")

    st.markdown("---")
    st.markdown(f"<div style='text-align:center;color:var(--st-font-color-weak);'>CAEC © 2025 — Criado e administrado pela diretoria de Administração Comercial e Financeiro — <strong>by Rick</strong></div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
