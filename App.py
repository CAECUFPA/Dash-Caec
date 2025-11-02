"""
app_refatorado_caec.py

Refatoração completa do "Dashboard Financeiro Caec" para uso com Streamlit + Google Sheets
- Código modular e comentado
- Usa st.secrets para credenciais (gcp_service_account), nome da planilha e índice da worksheet
- Tratamento robusto de cabeçalho (ignora linha 1 com logo, usa linha 2 como header)
- Parsing de moeda brasileiro e normalização de sinais (Receita/Despesa)
- KPIs com delta calculado contra o período imediatamente anterior ao período filtrado
- Gráficos Plotly preparados com paleta consistente (receita verde, despesa vermelho, saldo azul)

Como usar (Streamlit Cloud): coloque no secrets.toml:

[general]
SPREADSHEET_NAME = "Nome da sua planilha"
WORKSHEET_INDEX = 0  # ou outro índice inteiro

[gcp_service_account]
# colar o JSON de service account como mapeamento, por exemplo:
# type = "service_account"
# project_id = "..."
# private_key_id = "..."
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "..."
# ... (o restante do JSON)

Observação: garanta que a Service Account tenha permissão de leitura sobre a planilha (compartilhar a planilha com o client_email).
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Tentativa de import mais moderno do gspread
try:
    import gspread
except Exception:
    gspread = None

from sklearn.linear_model import LinearRegression

# ---------- CONFIGURAÇÃO GERAL ----------
EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

COLORS = {
    "receita": "#2ca02c",  # verde
    "despesa": "#d62728",  # vermelho
    "saldo": "#636efa",    # azul
    "neutral": "#6c757d",  # cinza
}

DEFAULT_CHART_HEIGHT = 360

FONT_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root { font-family: 'Roboto Mono', monospace; }
  .stApp { font-family: 'Roboto Mono', monospace; }
  /* Estilos básicos para KPIs — o seletor do Streamlit pode variar entre versões */
  .kpi-positive { color: %s; font-weight:700 }
  .kpi-negative { color: %s; font-weight:700 }
  .kpi-saldo { color: %s; font-weight:700 }
</style>
""" % (COLORS["receita"], COLORS["despesa"], COLORS["saldo"])

# ---------- UTILITÁRIOS ----------

def parse_val_str_to_float(val) -> float:
    """Converte formatos comuns (R$ 1.234,56), (1.234,56), -1.234,56 para float.
    Retorna 0.0 caso não seja possível.
    """
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    if s == "":
        return 0.0

    neg = False
    # Parênteses como negativo
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]

    # Remover símbolo R$
    s = s.replace("R$", "").replace("r$", "")

    # Sinal de menos
    if s.startswith("-"):
        neg = True
        s = s[1:]

    # remover espaços
    s = s.replace(" ", "")

    # remover pontos de milhar e trocar vírgula decimal por ponto
    s = s.replace(".", "").replace(",", ".")

    try:
        v = float(s)
    except Exception:
        v = 0.0

    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    """Formata float para R$ 1.234,56 (mantendo sinal quando negativo)."""
    try:
        neg = value < 0
        v = abs(value)
        s = f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"-{s}" if neg else s
    except Exception:
        return "R$ 0,00"

# ---------- CONEXÃO COM GOOGLE SHEETS ----------

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[object]:
    """Cria cliente gspread a partir do dicionário no st.secrets['gcp_service_account'].
    Retorna None e escreve mensagem no app se algo falhar.
    """
    if gspread is None:
        st.error("Biblioteca gspread não encontrada. Instale 'gspread' para acessar Google Sheets.")
        return None

    try:
        creds_dict = st.secrets.get("gcp_service_account")
        if not creds_dict:
            st.error("Chave 'gcp_service_account' não encontrada em st.secrets. Configure o secret com o JSON da service account.")
            return None

        # gspread >=5 tem service_account_from_dict
        if hasattr(gspread, "service_account_from_dict"):
            client = gspread.service_account_from_dict(creds_dict)
            return client

        # Fallback mais antigo
        if hasattr(gspread, "authorize"):
            from oauth2client.service_account import ServiceAccountCredentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
            client = gspread.authorize(creds)
            return client

        st.error("Não foi possível criar o cliente gspread com as bibliotecas disponíveis.")
        return None

    except Exception as e:
        st.error(f"Erro ao criar cliente gspread: {e}")
        return None

def load_sheet_values(client: object) -> List[List[str]]:
    """Retorna get_all_values() da worksheet configurada em st.secrets.
    Em caso de erro, retorna lista vazia.
    """
    if client is None:
        return []

    try:
        spreadsheet_name = st.secrets.get("SPREADSHEET_NAME")
        worksheet_index = st.secrets.get("WORKSHEET_INDEX", 0)

        if not spreadsheet_name:
            st.error("SPREADSHEET_NAME não configurado em st.secrets")
            return []

        try:
            worksheet_index = int(worksheet_index)
        except Exception:
            worksheet_index = 0

        sh = client.open(spreadsheet_name)
        ws = sh.get_worksheet(worksheet_index)
        values = ws.get_all_values()
        return values

    except Exception as e:
        st.error(f"Erro ao ler a planilha: {e}")
        return []

def build_dataframe(values: List[List[str]]) -> Tuple[pd.DataFrame, bool]:
    """Constroi DataFrame a partir do get_all_values().
    - Ignora a primeira linha (logo) e usa a segunda como header (se presente).
    - Retorna (df, header_mismatch)
    """
    if not values or len(values) < 2:
        # Sem dados ou apenas uma linha
        return pd.DataFrame(columns=EXPECTED_COLS), False

    header_row = [str(x).strip() for x in values[1]]
    body = values[2:] if len(values) > 2 else []

    header_norm = [str(h).strip().upper() for h in header_row]

    header_mismatch = not all(c in header_norm for c in EXPECTED_COLS)

    if not header_mismatch:
        col_indices = {col: header_norm.index(col) for col in EXPECTED_COLS}
        rows = []
        for r in body:
            row = []
            for col in EXPECTED_COLS:
                idx = col_indices[col]
                row.append(r[idx] if idx < len(r) else "")
            rows.append(row)
        df = pd.DataFrame(rows, columns=EXPECTED_COLS)
    else:
        max_len = max((len(r) for r in body), default=0)
        padded = [r + [""] * max(0, max_len - len(r)) for r in body]
        # Tentar mapear por palavras-chave simples
        mapping = {}
        for i, h in enumerate(header_row):
            hh = str(h).lower()
            if "data" in hh:
                mapping["DATA"] = i
            if "tipo" in hh:
                mapping["TIPO"] = i
            if "categoria" in hh:
                mapping["CATEGORIA"] = i
            if "descri" in hh:
                mapping["DESCRIÇÃO"] = i
            if "valor" in hh:
                mapping["VALOR"] = i
            if "observ" in hh or "obs" in hh:
                mapping["OBSERVAÇÃO"] = i

        final_rows = []
        for r in padded:
            row = []
            for expected in EXPECTED_COLS:
                if expected in mapping:
                    idx = mapping[expected]
                    row.append(r[idx] if idx < len(r) else "")
                else:
                    row.append("")
            final_rows.append(row)
        df = pd.DataFrame(final_rows, columns=EXPECTED_COLS)

    return df, header_mismatch

# ---------- PREPROCESSAMENTO ----------

def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()

    for c in EXPECTED_COLS:
        if c not in df.columns:
            df[c] = ""

    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).reset_index(drop=True)

    df["VALOR_NUM"] = df["VALOR"].apply(parse_val_str_to_float) if "VALOR" in df.columns else 0.0

    df["TIPO"] = df["TIPO"].fillna("").astype(str).str.strip()
    mask_empty_tipo = df["TIPO"] == ""
    df.loc[mask_empty_tipo, "TIPO"] = df.loc[mask_empty_tipo, "VALOR_NUM"].apply(lambda v: "Despesa" if v < 0 else "Receita")

    mask_receita = df["TIPO"].str.contains("Receita", case=False, na=False)
    mask_despesa = df["TIPO"].str.contains("Despesa", case=False, na=False)

    df.loc[mask_receita, "VALOR_NUM"] = df.loc[mask_receita, "VALOR_NUM"].abs()
    df.loc[mask_despesa, "VALOR_NUM"] = -df.loc[mask_despesa, "VALOR_NUM"].abs()

    df["CATEGORIA"] = df["CATEGORIA"].fillna("").astype(str).str.strip()
    df["DESCRIÇÃO"] = df["DESCRIÇÃO"].fillna("").astype(str).str.strip()
    df["OBSERVAÇÃO"] = df["OBSERVAÇÃO"].fillna("").astype(str).str.strip()

    def is_mostly_numeric_or_empty_category(s):
        s = str(s).strip()
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
    if client is None:
        return pd.DataFrame(columns=EXPECTED_COLS), False

    values = load_sheet_values(client)
    df_raw, header_mismatch = build_dataframe(values)
    if df_raw.empty:
        return df_raw, header_mismatch

    df_proc = preprocess_df(df_raw)
    return df_proc, header_mismatch

# ---------- PLOTAGENS ----------

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=DEFAULT_CHART_HEIGHT)
    return fig

def plot_saldo_acumulado(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()

    fig = go.Figure()
    daily = df.groupby(df["DATA"].dt.date)["Saldo Acumulado"].last().reset_index()
    daily["DATA"] = pd.to_datetime(daily["DATA"])

    fig.add_trace(go.Scatter(x=daily["DATA"], y=daily["Saldo Acumulado"], mode="lines+markers", name="Saldo", line=dict(color=COLORS["saldo"], width=2)))

    if len(daily) > 1:
        X = daily["DATA"].map(pd.Timestamp.toordinal).values.reshape(-1, 1)
        y = daily["Saldo Acumulado"].values
        try:
            reg = LinearRegression().fit(X, y)
            X_line = np.linspace(X.min(), X.max(), 100).reshape(-1, 1)
            y_pred = reg.predict(X_line)
            dates_line = [datetime.fromordinal(int(x)) for x in X_line.flatten()]
            fig.add_trace(go.Scatter(x=dates_line, y=y_pred, mode="lines", name="Tendência", line=dict(color="#888888", dash="dash")))
        except Exception:
            pass

    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Saldo (R$)")
    return fig

def plot_fluxo_diario(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()
    fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
    cores = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
    fig = go.Figure(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], marker_color=cores))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

def plot_categoria_barras(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
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

    fig = px.bar(x=series.values, y=series.index, orientation='h', labels={'x':'Valor (R$)', 'y':'Categoria'}, color_discrete_sequence=[color_default])
    fig.update_layout(height=DEFAULT_CHART_HEIGHT - 10, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis={'categoryorder':'total ascending'})
    return fig

def plot_pie_composicao(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
    if kind == "Receita":
        series = df[df["VALOR_NUM"] > 0].groupby("CATEGORIA")["VALOR_NUM"].sum()
    else:
        series = (-df[df["VALOR_NUM"] < 0].groupby("CATEGORIA")["VALOR_NUM"].sum())

    if series.empty:
        return _get_empty_fig(f"Sem dados de {kind}")

    series = series.sort_values(ascending=False)
    fig = go.Figure(go.Pie(labels=series.index, values=series.values, hole=0.45, textinfo="percent+label", sort=False))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=30, b=10, l=10, r=10))
    return fig

def plot_bubble_transacoes_categoria_y(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig("Sem transações")

    df_plot = df.copy()
    df_plot["Size"] = df_plot["VALOR_NUM"].abs()
    df_plot["Color"] = df_plot["VALOR_NUM"].apply(lambda x: "Receita" if x > 0 else "Despesa")

    fig = px.scatter(df_plot, x="DATA", y="CATEGORIA", size="Size", color="Color", hover_name="DESCRIÇÃO",
                     hover_data={"VALOR_NUM": True, "DATA": False, "CATEGORIA": False, "Size": False},
                     color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]},
                     title="Transações por Categoria ao Longo do Tempo (Tamanho = Valor Absoluto)")
    fig.update_layout(height=DEFAULT_CHART_HEIGHT + 40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Categoria")
    return fig

def plot_bubble_transacoes_valor_y(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig("Sem transações")

    dfp = df.copy()
    dfp["VALOR_ABS"] = dfp["VALOR_NUM"].abs()

    fig = px.scatter(dfp, x="DATA", y="VALOR_NUM", size="VALOR_ABS", color="CATEGORIA", hover_name="DESCRIÇÃO", size_max=30, title="Visão Detalhada de Transações (Tamanho = Valor Absoluto)")
    fig.update_layout(height=DEFAULT_CHART_HEIGHT + 40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

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
    ohlc = prepare_ohlc_period(df, freq)
    if ohlc.empty:
        return _get_empty_fig("Sem dados para candlestick")

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.72, 0.28])
    fig.add_trace(go.Candlestick(x=ohlc["ts"], open=ohlc["open"], high=ohlc["high"], low=ohlc["low"], close=ohlc["close"], name="OHLC"), row=1, col=1)
    fig.add_trace(go.Bar(x=ohlc["ts"], y=ohlc["volume"], name="Volume", marker_color="#888888"), row=2, col=1)

    ohlc["sma7"] = ohlc["close"].rolling(window=7, min_periods=1).mean()
    fig.add_trace(go.Scatter(x=ohlc["ts"], y=ohlc["sma7"], mode="lines", name="SMA7", line=dict(color="#ff9900")), row=1, col=1)

    fig.update_layout(height=DEFAULT_CHART_HEIGHT + 80, showlegend=True, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Período")
    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_xaxes(rangeslider_visible=False)
    return fig

def plot_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()

    dfh = df.copy()
    dfh['day'] = dfh['DATA'].dt.day
    dfh['ym'] = dfh['DATA'].dt.to_period('M').astype(str)
    pivot = dfh.groupby(['ym','day'])['VALOR_NUM'].sum().reset_index()
    heat = pivot.pivot(index='ym', columns='day', values='VALOR_NUM').fillna(0)

    fig = go.Figure(data=go.Heatmap(z=heat.values, x=heat.columns, y=heat.index, colorscale='Viridis'))
    fig.update_layout(title='Heatmap Mensal (soma diária por mês)', height=DEFAULT_CHART_HEIGHT+40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Dia do mês")
    fig.update_yaxes(title_text="Mês")
    return fig

def plot_boxplot_by_category(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()

    dfp = df.copy()
    dfp['VALOR_ABS'] = dfp['VALOR_NUM'].abs()
    fig = px.box(dfp, x='CATEGORIA', y='VALOR_ABS', points='outliers', labels={'VALOR_ABS':'Valor absoluto (R$)'})
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(tickangle=-45)
    return fig

# ---------- SIDEBAR E FILTROS ----------

def sidebar_filters_and_controls(df: pd.DataFrame) -> Tuple[str, Dict]:
    st.sidebar.title("Dashboard Financeiro Caec")
    st.sidebar.markdown("---")

    page = st.sidebar.selectbox("Altera visualização", options=["Resumo Financeiro", "Dashboard Detalhado"], key="sb_page")
    toggle_multi = st.sidebar.checkbox("Ativar filtro avançado (múltipla seleção e período)", value=False, key="sb_toggle_multi")

    min_ts = df["DATA"].min() if not df.empty else pd.Timestamp(datetime.today() - timedelta(days=365))
    max_ts = df["DATA"].max() if not df.empty else pd.Timestamp(datetime.today())
    min_d = min_ts.date()
    max_d = max_ts.date()

    filters: Dict = {"mode": "month", "month": "Todos", "categories": []}

    if toggle_multi:
        st.sidebar.markdown("### Filtros Avançados")
        categories = sorted(df["CATEGORIA"].unique()) if not df.empty else []
        categories = [c for c in categories if c != ""]

        selected_cats = st.sidebar.multiselect("Categorias (múltiplas)", options=categories, default=categories if categories else [], key="sb_cat_multi")

        slider_val = st.sidebar.slider("Período (arraste)", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD", step=timedelta(days=1), key="sb_date_slider")

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
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Cache limpo! O app recarregará os dados.")

    st.sidebar.markdown("---")
    st.sidebar.caption("Criado e administrado pela diretoria de Administração Comercial e Financeiro — by Rick")

    return page, filters

def apply_filters(df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    f = df.copy()
    if filters.get("mode") == "range":
        f = f[(f["DATA"] >= filters["date_from"]) & (f["DATA"] <= filters["date_to"]) ]
    else:
        month = filters.get("month", "Todos")
        if month and month != "Todos":
            f = f[f["year_month"] == month]

    cats = filters.get("categories", [])
    if cats:
        f = f[f["CATEGORIA"].isin(cats)]

    return f.reset_index(drop=True)

# ---------- KPIs E TABELAS ----------

def render_kpis(df: pd.DataFrame):
    receita = df.loc[df["VALOR_NUM"] > 0, "VALOR_NUM"].sum()
    despesa = df.loc[df["VALOR_NUM"] < 0, "VALOR_NUM"].sum()
    saldo = receita + despesa

    # Calcular delta simples: comparar com período anterior do mesmo tamanho
    try:
        # período atual = range de datas no df
        if df.empty:
            delta_rec = 0
            delta_dep = 0
            delta_saldo = 0
        else:
            min_d = df["DATA"].min()
            max_d = df["DATA"].max()
            period_len = max_d - min_d
            prev_from = min_d - period_len - pd.Timedelta(days=1)
            prev_to = min_d - pd.Timedelta(days=1)
            # Carregar data original (sem filtros) para comparar
            full_df, _ = load_and_preprocess_data()
            prev = full_df[(full_df["DATA"] >= prev_from) & (full_df["DATA"] <= prev_to)]
            prev_rec = prev.loc[prev["VALOR_NUM"] > 0, "VALOR_NUM"].sum()
            prev_dep = prev.loc[prev["VALOR_NUM"] < 0, "VALOR_NUM"].sum()
            prev_saldo = prev_rec + prev_dep
            delta_rec = receita - prev_rec
            delta_dep = abs(despesa) - abs(prev_dep)
            delta_saldo = saldo - prev_saldo
    except Exception:
        delta_rec = 0
        delta_dep = 0
        delta_saldo = 0

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(label="Receita Total", value=money_fmt_br(receita), delta=money_fmt_br(delta_rec) if delta_rec !=0 else "—")
    with c2:
        st.metric(label="Despesa Total", value=money_fmt_br(abs(despesa)), delta=money_fmt_br(-delta_dep) if delta_dep !=0 else "—")
    with c3:
        st.metric(label="Saldo (Receita - Despesa)", value=money_fmt_br(saldo), delta=money_fmt_br(delta_saldo) if delta_saldo!=0 else "—")

def render_table(df: pd.DataFrame, key: str):
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

    # Exibir com st.dataframe (configuração de colunas disponível em versões recentes)
    cols = ["Data","Tipo","Categoria","Descrição","Valor (R$)","Observação"]
    st.dataframe(df_display[cols], use_container_width=True, key=key)

def _prepare_export_csv(df: pd.DataFrame) -> str:
    export_df = df[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]].copy()
    export_df["DATA"] = export_df["DATA"].dt.strftime("%Y-%m-%d")
    return export_df.to_csv(index=False, encoding="utf-8-sig")

# ---------- MAIN ----------

def main():
    st.set_page_config(page_title="Dashboard Financeiro Caec", layout="wide", initial_sidebar_state="expanded", menu_items={"About":"Dashboard Financeiro Caec © 2025"})
    st.markdown(FONT_CSS, unsafe_allow_html=True)
    st.title("Dashboard Financeiro Caec")

    try:
        df, header_mismatch = load_and_preprocess_data()
    except Exception as e:
        st.error(f"Erro fatal ao carregar os dados: {e}")
        st.warning("Verifique a configuração dos Secrets e o formato da planilha.")
        return

    if header_mismatch:
        st.warning("Cabeçalho da planilha (Linha 2) não corresponde ao esperado. Tentando carregar mesmo assim.")

    if df.empty:
        st.sidebar.markdown("---")
        st.sidebar.caption("CAEC © 2025")
        st.warning("Planilha vazia ou erro ao importar dados. Verifique a planilha, as credenciais ou se a linha 2 contém o cabeçalho correto.")
        return

    page, filters = sidebar_filters_and_controls(df)
    df_filtered = apply_filters(df, filters)

    render_kpis(df_filtered)
    st.markdown("---")

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

        csv = _prepare_export_csv(df_filtered)
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_resumo_export.csv", mime="text/csv", key="download_resumo")

    else:
        tab_normais, tab_avancados = st.tabs(["📊 Gráficos Principais", "📈 Gráficos Avançados"])

        with tab_normais:
            st.subheader("Análise por Categoria e Composição")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("##### Receita por Categoria", unsafe_allow_html=True)
                fig_rec = plot_categoria_barras(df_filtered, kind="Receita")
                st.plotly_chart(fig_rec, use_container_width=True, key="chart_rec_bar_comb")

                st.markdown("##### Composição de Receita", unsafe_allow_html=True)
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Receita"), use_container_width=True, key="chart_pie_rec_comb")

            with col2:
                st.markdown("##### Despesa por Categoria", unsafe_allow_html=True)
                fig_dep = plot_categoria_barras(df_filtered, kind="Despesa")
                st.plotly_chart(fig_dep, use_container_width=True, key="chart_dep_bar_comb")

                st.markdown("##### Composição de Despesa", unsafe_allow_html=True)
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Despesa"), use_container_width=True, key="chart_pie_dep_comb")

            st.markdown("---")
            st.subheader("Visão Temporal de Lançamentos")
            st.plotly_chart(plot_bubble_transacoes_categoria_y(df_filtered), use_container_width=True, key="chart_bubble_cat_y")

            st.markdown("---")
            st.plotly_chart(plot_bubble_transacoes_valor_y(df_filtered), use_container_width=True, key="chart_bubble_valor_y")

        with tab_avancados:
            agg_freq = st.selectbox("Agregação Candlestick", options=[("Diário","D"), ("Semanal","W"), ("Mensal","M")], format_func=lambda x: x[0], key="sb_candle_freq")
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

        st.markdown("---")
        st.subheader("Todos os Lançamentos (Filtro Atual)")
        render_table(df_filtered, key="table_full_detalhado")

        csv = _prepare_export_csv(df_filtered)
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_full_export.csv", mime="text/csv", key="download_full")

    st.markdown("---")
    st.markdown("<div style='font-size:12px;color:gray;text-align:center'>CAEC © 2025 — Criado e administrado pela diretoria de Administração Comercial e Financeiro — <b>by Rick</b></div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
