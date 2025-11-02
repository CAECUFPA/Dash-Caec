# app.py
"""
Dashboard Financeiro Caec
Versão refatorada para uso com Streamlit Cloud Secrets.
Alterações: Cores nos KPIs e layout do Gráfico de Bolhas combinado.
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

# ---------- CONFIGURAÇÃO GERAL (NÃO-SENSÍVEL) ----------

# Colunas esperadas na planilha. A ordem importa para a montagem do DataFrame.
EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

# Paleta de cores padrão para os gráficos
COLORS = {
    "receita": "#2ca02c",  # Verde
    "despesa": "#d62728",  # Vermelho
    "saldo": "#636efa",   # Azul
    "neutral": "#6c757d",  # Cinza
}

# Altura padrão para a maioria dos gráficos
DEFAULT_CHART_HEIGHT = 360

# ---------- CSS (Fonte customizada e Estilo de KPI) ----------
FONT_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root { font-family: 'Roboto Mono', monospace; }
  .stApp { font-family: 'Roboto Mono', monospace; }
  /* Estilo para os valores de KPI com cores */
  .kpi-value-receita { color: #2ca02c; font-size: 20px; font-weight: 700; }
  .kpi-value-despesa { color: #d62728; font-size: 20px; font-weight: 700; }
  .kpi-value-saldo { color: #636efa; font-size: 20px; font-weight: 700; }
  .kpi-label { font-size:12px;color:#6c757d;text-transform:uppercase; margin-bottom: 0px; }
  /* Ajusta a aparência do st.metric para que o HTML customizado se encaixe melhor */
  div[data-testid="stMetricValue"] { color: inherit !important; }
</style>
"""

# ---------- UTILITÁRIOS DE FORMATAÇÃO ----------

def parse_val_str_to_float(val) -> float:
    """
    Converte uma string de moeda (ex: "R$ 1.234,56" ou "(1.234,56)")
    para um número float. Trata valores negativos (parênteses ou sinal).
    """
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    if s == "":
        return 0.0
    
    neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-"):
        neg = True
        s = s.strip("()-")
        
    # Limpa a string de formatação monetária
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    
    try:
        v = float(s)
    except ValueError:
        v = 0.0
    
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    """Formata um float para o padrão monetário brasileiro (R$ X.XXX,XX)."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ---------- CONEXÃO GOOGLE SHEETS (via st.secrets) ----------

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[GSpreadClient]:
    """
    Autoriza e retorna um cliente gspread usando credenciais do st.secrets.
    """
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro ao carregar credenciais do Google: {e}")
        st.warning("Verifique se o secrets.toml está configurado corretamente com a [gcp_service_account].")
        return None

def load_sheet_values(client: GSpreadClient) -> List[List[str]]:
    """
    Carrega todos os valores da planilha especificada no st.secrets.
    """
    if not client:
        return []
        
    try:
        spreadsheet_name = st.secrets["SPREADSHEET_NAME"]
        worksheet_index = st.secrets["WORKSHEET_INDEX"]
        sh = client.open(spreadsheet_name)
        ws = sh.get_worksheet(worksheet_index)
        return ws.get_all_values()
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Planilha '{st.secrets.get('SPREADSHEET_NAME', 'N/A')}' não encontrada. Verifique o nome e as permissões de compartilhamento.")
        return []
    except KeyError as e:
        st.error(f"Erro de configuração: Chave '{e}' não encontrada nos seus secrets.")
        return []
    except Exception as e:
        st.error(f"Erro ao acessar a planilha: {e}")
        return []

def build_dataframe(values: List[List[str]]) -> pd.DataFrame:
    """
    Constrói um DataFrame Pandas a partir da lista de valores da planilha.
    """
    if not values or len(values) < 1:
        return pd.DataFrame(columns=EXPECTED_COLS)
        
    header = values[0]
    body = values[1:] if len(values) > 1 else []
    
    if all(col in header for col in EXPECTED_COLS):
        df = pd.DataFrame(body, columns=header)[EXPECTED_COLS].copy()
    else:
        st.warning("Cabeçalho da planilha não corresponde ao esperado. Tentando carregar mesmo assim.")
        padded = [row + [""] * max(0, len(EXPECTED_COLS) - len(row)) for row in body]
        df = pd.DataFrame(padded, columns=EXPECTED_COLS)
        
    return df

# ---------- PREPROCESSAMENTO DOS DADOS ----------

def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica a limpeza e transformação principal no DataFrame.
    """
    df = df_raw.copy()
    
    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).reset_index(drop=True)
    
    df["VALOR_NUM"] = df["VALOR"].apply(parse_val_str_to_float)
    
    df["TIPO"] = df["TIPO"].fillna("").astype(str).str.strip()
    mask_empty_tipo = df["TIPO"] == ""
    df.loc[mask_empty_tipo, "TIPO"] = df.loc[mask_empty_tipo, "VALOR_NUM"].apply(lambda v: "Despesa" if v < 0 else "Receita")
    
    df["CATEGORIA"] = df["CATEGORIA"].fillna("Outros").astype(str).str.strip()
    df["DESCRIÇÃO"] = df["DESCRIÇÃO"].fillna("").astype(str).str.strip()
    df["OBSERVAÇÃO"] = df["OBSERVAÇÃO"].fillna("").astype(str).str.strip()
    
    df = df.sort_values("DATA").reset_index(drop=True)
    df["Saldo Acumulado"] = df["VALOR_NUM"].cumsum()
    
    df["year_month"] = df["DATA"].dt.to_period("M").astype(str)
    
    return df

@st.cache_data(ttl=600)
def load_and_preprocess_data() -> pd.DataFrame:
    """
    Função principal de carregamento e processamento de dados (cacheada).
    """
    client = get_gspread_client()
    if not client:
        return pd.DataFrame(columns=EXPECTED_COLS)
        
    raw_vals = load_sheet_values(client)
    df_raw = build_dataframe(raw_vals)
    if df_raw.empty:
        return df_raw
        
    df_processed = preprocess_df(df_raw)
    return df_processed

# ---------- FUNÇÕES DE PLOTAGEM (Gráficos) ----------

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    """Retorna uma figura Plotly vazia com uma anotação central."""
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=DEFAULT_CHART_HEIGHT)
    return fig

def plot_saldo_acumulado(df: pd.DataFrame) -> go.Figure:
    """Plota a evolução do Saldo Acumulado com linha de tendência."""
    if df.empty:
        return _get_empty_fig()
        
    fig = go.Figure()
    daily = df.groupby(df["DATA"].dt.date)["Saldo Acumulado"].last().reset_index()
    daily["DATA"] = pd.to_datetime(daily["DATA"])
    
    fig.add_trace(go.Scatter(
        x=daily["DATA"], 
        y=daily["Saldo Acumulado"],
        mode="lines+markers", 
        name="Saldo", 
        line=dict(color=COLORS["saldo"], width=2)
    ))
    
    # Adiciona regressão linear (linha de tendência)
    if len(daily) > 1:
        X = daily["DATA"].map(pd.Timestamp.toordinal).values.reshape(-1, 1)
        y = daily["Saldo Acumulado"].values
        reg = LinearRegression().fit(X, y)
        X_line = np.linspace(X.min(), X.max(), 100).reshape(-1,1)
        y_pred = reg.predict(X_line)
        dates_line = [datetime.fromordinal(int(x)) for x in X_line.flatten()]
        
        fig.add_trace(go.Scatter(
            x=dates_line, 
            y=y_pred, 
            mode="lines", 
            name="Tendência",
            line=dict(color="#888888", dash="dash")
        ))
                            
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Saldo (R$)")
    return fig

def plot_fluxo_diario(df: pd.DataFrame) -> go.Figure:
    """Plota o fluxo de caixa diário (barras positivas/negativas)."""
    if df.empty:
        return _get_empty_fig()
        
    fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
    
    # Define cores com base no valor (receita/despesa)
    cores = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
    
    fig = go.Figure(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], marker_color=cores))
    
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

def plot_categoria_barras(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
    """Plota um gráfico de barras por categoria (Receita ou Despesa)."""
    assert kind in ("Receita", "Despesa")
    
    if kind == "Receita":
        base = df[df["VALOR_NUM"] > 0]
        color_default = COLORS["receita"]
    else:
        base = df[df["VALOR_NUM"] < 0]
        color_default = COLORS["despesa"]
        
    if base.empty:
        return _get_empty_fig(f"Sem dados de {kind}")
        
    series = base["VALOR_NUM"].abs().groupby(base["CATEGORIA"]).sum().sort_values(ascending=False)
    
    # Inverte para ter a barra maior em cima, melhor para visualização vertical (h)
    fig = px.bar(
        x=series.values, 
        y=series.index, 
        orientation='h', 
        labels={'x':'Valor (R$)', 'y':'Categoria'},
        color_discrete_sequence=[color_default]
    )
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT - 10, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

def plot_pie_composicao(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
    """Plota um gráfico de pizza (donut) da composição de Receita/Despesa."""
    if kind == "Receita":
        series = df[df["VALOR_NUM"] > 0].groupby("CATEGORIA")["VALOR_NUM"].sum()
    else:
        series = (-df[df["VALOR_NUM"] < 0].groupby("CATEGORIA")["VALOR_NUM"].sum())
        
    if series.empty:
        return _get_empty_fig(f"Sem dados de {kind}")
        
    series = series.sort_values(ascending=False)
    
    fig = go.Figure(go.Pie(
        labels=series.index, 
        values=series.values, 
        hole=0.45, 
        textinfo="percent", 
        sort=False
    ))
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=30, b=10, l=10, r=10) # Reduz margens para caber melhor
    )
    return fig

def plot_bubble_transacoes(df: pd.DataFrame) -> go.Figure:
    """Plota um gráfico de bolhas de todas as transações (Valor vs Data)."""
    if df.empty:
        return _get_empty_fig("Sem transações")
        
    dfp = df.copy()
    dfp["VALOR_ABS"] = dfp["VALOR_NUM"].abs()
    dfp["Tipo"] = dfp["TIPO"].apply(lambda x: "Receita" if x.lower() == "receita" else "Despesa")
    
    fig = px.scatter(
        dfp, 
        x="DATA", 
        y="VALOR_NUM", 
        size="VALOR_ABS", 
        color="Tipo", # Colore por Tipo para diferenciar Receita/Despesa
        color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]},
        hover_name="DESCRIÇÃO", 
        size_max=30
    )
    fig.update_layout(
        title="Transações (Tamanho=Valor Absoluto)",
        height=DEFAULT_CHART_HEIGHT + 40, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    fig.update_yaxes(title_text="Valor (R$)")
    fig.update_xaxes(title_text="Data")
    return fig

# Funções plot_candlestick, plot_monthly_heatmap, plot_boxplot_by_category... (manter)
# ... [Código das funções plot_candlestick, prepare_ohlc_period, plot_monthly_heatmap, plot_boxplot_by_category aqui, mantendo a originalidade do código do usuário, pois elas não precisam ser alteradas.] ...

def prepare_ohlc_period(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """
    Agrupa os dados de transações em formato OHLC (Open, High, Low, Close)
    para um período específico (Diário, Semanal, Mensal).
    """
    if df.empty:
        return pd.DataFrame()
        
    if freq == "D":
        period = df["DATA"].dt.to_period("D")
    elif freq == "W":
        period = df["DATA"].dt.to_period("W")
    else: # "M"
        period = df["DATA"].dt.to_period("M")
        
    dfp = df.copy()
    dfp["PERIOD"] = period
    
    groups = []
    # Agrega manualmente para pegar o primeiro (open) e último (close) valor
    for per, g in dfp.groupby("PERIOD"):
        g_sorted = g.sort_values("DATA")
        open_v = g_sorted.iloc[0]["VALOR_NUM"]
        close_v = g_sorted.iloc[-1]["VALOR_NUM"]
        high_v = g_sorted["VALOR_NUM"].max()
        low_v = g_sorted["VALOR_NUM"].min()
        vol = g_sorted["VALOR_NUM"].abs().sum()
        groups.append({
            "PERIOD": per, 
            "ts": per.to_timestamp(), 
            "open": open_v, 
            "high": high_v, 
            "low": low_v, 
            "close": close_v, 
            "volume": vol
        })
        
    ohlc = pd.DataFrame(groups).sort_values("ts").reset_index(drop=True)
    return ohlc

def plot_candlestick(df: pd.DataFrame, freq: str = "D") -> go.Figure:
    """Plota um gráfico Candlestick (OHLC) e um gráfico de Volume."""
    ohlc = prepare_ohlc_period(df, freq)
    
    if ohlc.empty:
        return _get_empty_fig("Sem dados para candlestick")

    # Cria subplots: 1 para candles, 1 para volume
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.04,
        row_heights=[0.72, 0.28]
    )
    
    # 1. Candlestick
    fig.add_trace(go.Candlestick(
        x=ohlc["ts"], 
        open=ohlc["open"], 
        high=ohlc["high"], 
        low=ohlc["low"], 
        close=ohlc["close"], 
        name="OHLC"
    ), row=1, col=1)
    
    # 2. Volume
    fig.add_trace(go.Bar(
        x=ohlc["ts"], 
        y=ohlc["volume"], 
        name="Volume", 
        marker_color="#888888"
    ), row=2, col=1)
    
    # 3. Média Móvel Simples (ex: 7 períodos)
    ohlc["sma7"] = ohlc["close"].rolling(window=7, min_periods=1).mean()
    fig.add_trace(go.Scatter(
        x=ohlc["ts"], 
        y=ohlc["sma7"], 
        mode="lines", 
        name="SMA7", 
        line=dict(color="#ff9900")
    ), row=1, col=1)
    
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT + 80, 
        showlegend=True, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    fig.update_xaxes(title_text="Período")
    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_xaxes(rangeslider_visible=False) # Desliga o slider default
    return fig

def plot_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    """Plota um heatmap da soma de valores por Dia do Mês vs. Mês."""
    if df.empty:
        return _get_empty_fig()
        
    dfh = df.copy()
    dfh['day'] = dfh['DATA'].dt.day
    dfh['ym'] = dfh['DATA'].dt.to_period('M').astype(str)
    
    # Pivota os dados
    pivot = dfh.groupby(['ym','day'])['VALOR_NUM'].sum().reset_index()
    heat = pivot.pivot(index='ym', columns='day', values='VALOR_NUM').fillna(0)
    
    fig = go.Figure(data=go.Heatmap(
        z=heat.values, 
        x=heat.columns, 
        y=heat.index, 
        colorscale='Viridis' # Escala de cor (pode mudar)
    ))
    
    fig.update_layout(
        title='Heatmap Mensal (soma diária por mês)', 
        height=DEFAULT_CHART_HEIGHT+40, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    fig.update_xaxes(title_text="Dia do mês")
    fig.update_yaxes(title_text="Mês")
    return fig

def plot_boxplot_by_category(df: pd.DataFrame) -> go.Figure:
    """Plota um boxplot do valor absoluto das transações por categoria."""
    if df.empty:
        return _get_empty_fig()
        
    dfp = df.copy()
    dfp['VALOR_ABS'] = dfp['VALOR_NUM'].abs()
    
    fig = px.box(
        dfp, 
        x='CATEGORIA', 
        y='VALOR_ABS', 
        points='outliers', 
        labels={'VALOR_ABS':'Valor absoluto (R$)'}
    )
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    fig.update_xaxes(tickangle=-45)
    return fig


# ---------- SIDEBAR (Filtros e Controles) (Manter o original) ----------
def sidebar_filters_and_controls(df: pd.DataFrame) -> Tuple[str, Dict]:
    """
    Renderiza a barra lateral com os filtros de página, período e categoria.
    Retorna a página selecionada e um dicionário de filtros.
    """
    st.sidebar.title("Dashboard Financeiro Caec")
    st.sidebar.markdown("CAEC © 2025")
    st.sidebar.markdown("---")

    # 1. Seletor de Página/Visualização
    page = st.sidebar.selectbox(
        "Altera visualização", 
        options=["Resumo Financeiro", "Dashboard Detalhado"], 
        key="sb_page"
    )

    # 2. Toggle para modo de filtro
    toggle_multi = st.sidebar.checkbox(
        "Ativar filtro avançado (múltipla seleção e período)", 
        value=False, 
        key="sb_toggle_multi"
    )

    # 3. Limites de data para os filtros
    min_ts = df["DATA"].min() if not df.empty else pd.Timestamp(datetime.today() - timedelta(days=365))
    max_ts = df["DATA"].max() if not df.empty else pd.Timestamp(datetime.today())
    min_d = min_ts.date()
    max_d = max_ts.date()

    filters: Dict = {"mode": "month", "month": "Todos", "categories": []}

    if toggle_multi:
        # Modo Avançado: Multiselect de Categoria + Slider de Data
        st.sidebar.markdown("### Filtros Avançados")
        categories = sorted(df["CATEGORIA"].unique()) if not df.empty else []
        selected_cats = st.sidebar.multiselect(
            "Categorias (múltiplas)", 
            options=categories, 
            default=categories if categories else [], 
            key="sb_cat_multi"
        )
        
        slider_val = st.sidebar.slider(
            "Período (arraste)", 
            min_value=min_d, 
            max_value=max_d,
            value=(min_d, max_d), 
            format="YYYY-MM-DD", 
            step=timedelta(days=1), 
            key="sb_date_slider"
        )
        
        # Ajusta o 'date_to' para incluir o dia inteiro
        date_from = pd.to_datetime(slider_val[0])
        date_to = pd.to_datetime(slider_val[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        
        filters["mode"] = "range"
        filters["date_from"] = date_from
        filters["date_to"] = date_to
        filters["categories"] = selected_cats
    else:
        # Modo Simples: Selectbox de Mês + Selectbox de Categoria
        st.sidebar.markdown("### Filtro Rápido")
        months = ["Todos"] + sorted(df["year_month"].unique(), reverse=True) if not df.empty else ["Todos"]
        selected_month = st.sidebar.selectbox("Mês (ano-mês)", months, key="sb_month")
        
        categories = ["Todos"] + sorted(df["CATEGORIA"].unique()) if not df.empty else ["Todos"]
        selected_category = st.sidebar.selectbox("Categoria", categories, key="sb_cat_single")
        
        filters["mode"] = "month"
        filters["month"] = selected_month
        filters["categories"] = [selected_category] if selected_category != "Todos" else []

    st.sidebar.markdown("---")
    
    # 4. Botão de Limpar Cache
    if st.sidebar.button("Limpar cache de dados", key="sb_clear_cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.sidebar.success("Cache limpo! O app recarregará os dados.")

    st.sidebar.markdown("---")
    st.sidebar.caption("Criado e administrado pela diretoria de Administração Comercial e Financeiro — by Rick")

    return page, filters

def apply_filters(df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    """Aplica o dicionário de filtros ao DataFrame principal."""
    f = df.copy()
    
    # 1. Filtro de Data
    if filters.get("mode") == "range":
        f = f[(f["DATA"] >= filters["date_from"]) & (f["DATA"] <= filters["date_to"])]
    else: # mode == "month"
        month = filters.get("month", "Todos")
        if month and month != "Todos":
            f = f[f["year_month"] == month]
    
    # 2. Filtro de Categoria
    cats = filters.get("categories", [])
    if cats:
        f = f[f["CATEGORIA"].isin(cats)]
        
    return f.reset_index(drop=True)

# ---------- COMPONENTES DE UI (KPIs e Tabelas) ----------

def render_kpis(df: pd.DataFrame):
    """
    Renderiza os 3 KPIs principais: Receita, Despesa e Saldo.
    *** MODIFICADO PARA INCLUIR CORES NOS VALORES ***
    """
    receita = df.loc[df["VALOR_NUM"] > 0, "VALOR_NUM"].sum()
    despesa = df.loc[df["VALOR_NUM"] < 0, "VALOR_NUM"].sum()
    saldo = receita + despesa
    
    c1, c2, c3 = st.columns(3)
    
    # KPI 1: Receita (Verde)
    with c1:
        st.markdown("<div class='kpi-label'>Receita Total</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-value-receita'>{money_fmt_br(receita)}</div>", unsafe_allow_html=True)
    
    # KPI 2: Despesa (Vermelho)
    with c2:
        st.markdown("<div class='kpi-label'>Despesa Total (Abs.)</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-value-despesa'>{money_fmt_br(abs(despesa))}</div>", unsafe_allow_html=True)

    # KPI 3: Saldo (Azul)
    with c3:
        st.markdown("<div class='kpi-label'>Saldo (Receita - Despesa)</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-value-saldo'>{money_fmt_br(saldo)}</div>", unsafe_allow_html=True)
        delta_text = "⬆️ Positivo" if saldo >= 0 else "⬇️ Negativo"
        # Usamos um st.metric auxiliar para o delta colorido
        st.metric(label="", value="", delta=delta_text, delta_color="normal" if saldo >= 0 else "inverse")


def render_table(df: pd.DataFrame, key: str):
    """Renderiza a tabela de lançamentos usando st.dataframe."""
    if df.empty:
        st.info("Sem lançamentos para mostrar com os filtros atuais.")
        return
        
    df_display = df.copy()
    df_display["Data"] = df_display["DATA"].dt.date
    df_display["Valor (R$)"] = df_display["VALOR_NUM"].apply(money_fmt_br)
    
    df_display = df_display.rename(columns={
        "TIPO":"Tipo",
        "CATEGORIA":"Categoria",
        "DESCRIÇÃO":"Descrição",
        "OBSERVAÇÃO":"Observação"
    })
    
    column_config = {
        "Data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
        "Valor (R$)": st.column_config.TextColumn("Valor (R$)"),
    }
    
    st.dataframe(
        df_display[["Data","Tipo","Categoria","Descrição","Valor (R$)","Observação"]], 
        column_config=column_config, 
        use_container_width=True, 
        key=key,
        hide_index=True
    )

def _prepare_export_csv(df: pd.DataFrame) -> str:
    """Prepara o DataFrame para exportação e o converte para CSV."""
    export_df = df[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]]
    return export_df.to_csv(index=False, encoding="utf-8-sig")

# ---------- FUNÇÃO COMBINADA (Gráficos Principais) ----------

def plot_combined_charts(df: pd.DataFrame):
    """
    Combina os gráficos de barras, pizza e bolhas em um único layout compacto.
    *** NOVO ***
    """
    st.subheader("Análise por Categoria e Composição")
    
    col1, col2 = st.columns(2)
    with col1:
        # Gráfico de Barras de Receita
        st.markdown("##### Receita por Categoria", unsafe_allow_html=True)
        fig_rec = plot_categoria_barras(df, kind="Receita")
        st.plotly_chart(fig_rec, use_container_width=True, key="chart_rec_bar_comb")

        # Gráfico de Pizza de Receita
        st.markdown("##### Composição de Receita", unsafe_allow_html=True)
        st.plotly_chart(plot_pie_composicao(df, kind="Receita"), use_container_width=True, key="chart_pie_rec_comb")

    with col2:
        # Gráfico de Barras de Despesa
        st.markdown("##### Despesa por Categoria", unsafe_allow_html=True)
        fig_dep = plot_categoria_barras(df, kind="Despesa")
        st.plotly_chart(fig_dep, use_container_width=True, key="chart_dep_bar_comb")

        # Gráfico de Pizza de Despesa
        st.markdown("##### Composição de Despesa", unsafe_allow_html=True)
        st.plotly_chart(plot_pie_composicao(df, kind="Despesa"), use_container_width=True, key="chart_pie_dep_comb")

    st.markdown("---")
    st.subheader("Visão Temporal de Lançamentos (Bolhas)")
    # Gráfico de Bolhas no centro (combinado)
    st.plotly_chart(plot_bubble_transacoes(df), use_container_width=True, key="chart_bubble_comb")


# ---------- FUNÇÃO PRINCIPAL (MAIN) ----------

def main():
    """Função principal que executa o aplicativo Streamlit."""
    
    # --- Configuração da Página ---
    st.set_page_config(
        page_title="Dashboard Financeiro Caec", 
        layout="wide", 
        initial_sidebar_state="expanded",
        menu_items={"About": "Dashboard Financeiro Caec © 2025 by Rick"}
    )
    # Aplica o CSS (Com estilo de KPI)
    st.markdown(FONT_CSS, unsafe_allow_html=True)
    st.title("Dashboard Financeiro Caec")

    # --- Carregamento de Dados ---
    try:
        df = load_and_preprocess_data()
    except Exception as e:
        st.error(f"Erro fatal ao carregar os dados: {e}")
        st.warning("Verifique a configuração dos Secrets e o formato da planilha.")
        return

    if df.empty:
        st.sidebar.markdown("---")
        st.sidebar.caption("CAEC © 2025")
        st.warning("Planilha vazia ou erro ao importar dados. Verifique a planilha ou as credenciais nos Secrets.")
        return

    # --- Sidebar e Filtros ---
    page, filters = sidebar_filters_and_controls(df)
    df_filtered = apply_filters(df, filters)

    # --- KPIs (Com cores) ---
    render_kpis(df_filtered)
    st.markdown("---")

    # --- Renderização de Página ---
    if page == "Resumo Financeiro":
        st.subheader("Evolução do Saldo Acumulado")
        fig_saldo = plot_saldo_acumulado(df_filtered)
        st.plotly_chart(fig_saldo, use_container_width=True, key="chart_saldo_line_resumo")

        st.subheader("Fluxo de Caixa Diário")
        fig_fluxo = plot_fluxo_diario(df_filtered)
        st.plotly_chart(fig_fluxo, use_container_width=True, key="chart_fluxo_bar_resumo")

        st.subheader("Lançamentos Recentes (Últimos 10)")
        recent = df_filtered.sort_values("DATA", ascending=False).head(10)
        render_table(recent, key="table_recent_resumo")

        # Botão de Download
        csv = _prepare_export_csv(df_filtered)
        st.download_button(
            "Exportar CSV (Filtro Atual)", 
            csv, 
            file_name="caec_resumo_export.csv", 
            mime="text/csv", 
            key="download_resumo"
        )

    else: # page == "Dashboard Detalhado"
        tab_normais, tab_avancados = st.tabs(["📊 Gráficos Principais", "📈 Gráficos Avançados"])

        with tab_normais:
            # *** USO DA NOVA FUNÇÃO COMBINADA ***
            plot_combined_charts(df_filtered)

        with tab_avancados:
            agg_freq = st.selectbox(
                "Agregação Candlestick", 
                options=[("Diário","D"), ("Semanal","W"), ("Mensal","M")], 
                format_func=lambda x: x[0], 
                key="sb_candle_freq"
            )
            freq_code = agg_freq[1] 
            
            st.subheader(f"Análise Candlestick ({agg_freq[0]}) e Volume")
            st.plotly_chart(plot_candlestick(df_filtered, freq=freq_code), use_container_width=True, key=f"chart_candlestick_{freq_code}")

            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Fluxo Diário com Média Móvel (14 dias)")
                fluxo = df_filtered.groupby(df_filtered["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
                fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
                fluxo["sma14"] = fluxo["VALOR_NUM"].rolling(window=14, min_periods=1).mean()
                
                fig_ma = go.Figure()
                fig_ma.add_trace(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], name="Fluxo Diário", marker_color="#888888"))
                fig_ma.add_trace(go.Scatter(x=fluxo["DATA"], y=fluxo["sma14"], mode="lines", name="SMA14 (14 dias)", line=dict(color="#ff9900")))
                fig_ma.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ma, use_container_width=True, key="chart_sma14_avancado")
                
            with col2:
                st.subheader("Distribuição de Valores por Categoria")
                st.plotly_chart(plot_boxplot_by_category(df_filtered), use_container_width=True, key="chart_box_avancado")

            st.markdown("---")
            st.subheader("Heatmap de Atividade Financeira")
            st.plotly_chart(plot_monthly_heatmap(df_filtered), use_container_width=True, key="chart_heatmap_avancado")

        # Tabela completa no final da página detalhada
        st.markdown("---")
        st.subheader("Todos os Lançamentos (Filtro Atual)")
        render_table(df_filtered, key="table_full_detalhado")
        
        # Botão de Download
        csv = _prepare_export_csv(df_filtered)
        st.download_button(
            "Exportar CSV (Filtro Atual)", 
            csv, 
            file_name="caec_full_export.csv", 
            mime="text/csv", 
            key="download_full"
        )

    # --- Rodapé ---
    st.markdown("---")
    st.markdown(
        "<div style='font-size:12px;color:gray;text-align:center'>"
        "CAEC © 2025 — Criado e administrado pela diretoria de Administração Comercial e Financeiro — by Rick"
        "</div>", 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
