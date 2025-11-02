# app.py
"""Dashboard Financeiro Caec — versão corrigida (sem st.experimental_rerun problemático)"""
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from sklearn.linear_model import LinearRegression

# ---------- CONFIGURAÇÃO ----------
SERVICE_ACCOUNT_FILE = "caec-api-097d862f0223.json"
SPREADSHEET_NAME = "PLANILHA FINANCEIRA"
WORKSHEET_INDEX = 1
EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

COLORS = {
    "receita": "#2ca02c",
    "despesa": "#d62728",
    "saldo": "#636efa",
    "neutral": "#6c757d",
}

DEFAULT_CHART_HEIGHT = 360

# ---------- CSS mínimo (aplica apenas fonte Roboto Mono) ----------
FONT_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root { font-family: 'Roboto Mono', monospace; }
  .stApp { font-family: 'Roboto Mono', monospace; }
</style>
"""

# ---------- UTILITÁRIOS ----------
def parse_val_str_to_float(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    if s == "":
        return 0.0
    neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-"):
        neg = True
        s = s.strip("()-")
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except Exception:
        v = 0.0
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ---------- GSheets ----------
@st.cache_resource(ttl=600)
def get_gspread_client(service_account_file: str = SERVICE_ACCOUNT_FILE):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(service_account_file, scopes)
    return gspread.authorize(creds)

def load_sheet_values(client: gspread.Client) -> List[List[str]]:
    try:
        sh = client.open(SPREADSHEET_NAME)
        ws = sh.get_worksheet(WORKSHEET_INDEX)
        return ws.get_all_values()
    except Exception as e:
        # não usar st.exception em ambientes que logam detalhes sensíveis;
        # exibimos mensagem curta e retornamos lista vazia
        st.error("Erro ao acessar a planilha. Verifique credenciais/permissões.")
        return []

def build_dataframe(values: List[List[str]]) -> pd.DataFrame:
    if not values or len(values) < 1:
        return pd.DataFrame(columns=EXPECTED_COLS)
    header = values[0]
    body = values[1:] if len(values) > 1 else []
    if all(col in header for col in EXPECTED_COLS):
        df = pd.DataFrame(body, columns=header)[EXPECTED_COLS].copy()
    else:
        padded = [row + [""] * max(0, len(EXPECTED_COLS) - len(row)) for row in body]
        df = pd.DataFrame(padded, columns=EXPECTED_COLS)
    return df

# ---------- PREPROCESSAMENTO ----------
def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
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
    client = get_gspread_client()
    raw_vals = load_sheet_values(client)
    df_raw = build_dataframe(raw_vals)
    df_processed = preprocess_df(df_raw)
    return df_processed

# ---------- GRÁFICOS (mantidos) ----------
def plot_saldo_acumulado(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    daily = df.groupby(df["DATA"].dt.date)["Saldo Acumulado"].last().reset_index()
    daily["DATA"] = pd.to_datetime(daily["DATA"])
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
                                 line=dict(color="#888888", dash="dash")))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h"))
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Saldo (R$)")
    return fig

def plot_fluxo_diario(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
    cores = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
    fig = go.Figure(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], marker_color=cores))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

def plot_categoria_barras(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
    fig = go.Figure()
    assert kind in ("Receita", "Despesa")
    if kind == "Receita":
        base = df[df["VALOR_NUM"] > 0]
        color_default = COLORS["receita"]
    else:
        base = df[df["VALOR_NUM"] < 0]
        color_default = COLORS["despesa"]
    if base.empty:
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    series = base["VALOR_NUM"].abs().groupby(base["CATEGORIA"]).sum().sort_values(ascending=False)
    fig = go.Figure(go.Bar(x=series.index, y=series.values, marker_color=color_default))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT - 10, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="Categoria", tickangle=-45)
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

def plot_pie_composicao(df: pd.DataFrame, kind: str = "Receita") -> go.Figure:
    fig = go.Figure()
    if kind == "Receita":
        series = df[df["VALOR_NUM"] > 0].groupby("CATEGORIA")["VALOR_NUM"].sum()
    else:
        series = (-df[df["VALOR_NUM"] < 0].groupby("CATEGORIA")["VALOR_NUM"].sum())
    if series.empty:
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    series = series.sort_values(ascending=False)
    fig = go.Figure(go.Pie(labels=series.index, values=series.values, hole=0.45, textinfo="percent", sort=False))
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def plot_bubble_transacoes(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="Sem transações", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    dfp = df.copy()
    dfp["VALOR_ABS"] = dfp["VALOR_NUM"].abs()
    fig = px.scatter(dfp, x="DATA", y="VALOR_NUM", size="VALOR_ABS", color="CATEGORIA",
                     hover_name="DESCRIÇÃO", size_max=30)
    fig.update_layout(height=DEFAULT_CHART_HEIGHT + 40, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

# ---------- AVANÇADOS (mantidos) ----------
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
        fig = go.Figure(); fig.add_annotation(text="Sem dados para candlestick", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.72, 0.28])
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
        fig = go.Figure(); fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False); fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"); return fig
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
        fig = go.Figure(); fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False); fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"); return fig
    dfp = df.copy(); dfp['VALOR_ABS'] = dfp['VALOR_NUM'].abs()
    fig = px.box(dfp, x='CATEGORIA', y='VALOR_ABS', points='outliers', labels={'VALOR_ABS':'Valor absoluto (R$)'})
    fig.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(tickangle=-45)
    return fig

# ---------- SIDEBAR: toggle + slider de período (sem experimental_rerun) ----------
def sidebar_filters_and_controls_with_toggle(df: pd.DataFrame) -> Tuple[str, Dict]:
    st.sidebar.title("Dashboard Financeiro Caec")
    st.sidebar.markdown("CAEC © 2025")
    st.sidebar.markdown("---")

    page = st.sidebar.selectbox("Altera visualização", options=["Resumo Financeiro", "Dashboard Detalhado"], key="sb_page")

    toggle_multi = st.sidebar.checkbox("Troca de filtro para Múltipla seleção", value=False, key="sb_toggle_multi")

    # date bounds
    min_ts = df["DATA"].min() if not df.empty else pd.Timestamp(datetime.today() - timedelta(days=365))
    max_ts = df["DATA"].max() if not df.empty else pd.Timestamp(datetime.today())
    min_d = min_ts.date()
    max_d = max_ts.date()

    filters: Dict = {"mode": "month", "month": "Todos", "categories": []}

    if toggle_multi:
        categories = sorted(df["CATEGORIA"].unique()) if not df.empty else []
        selected_cats = st.sidebar.multiselect("Categorias (múltiplas)", options=categories, default=categories if categories else [], key="sb_cat_multi")
        # slider date range (arrasta) using date values
        slider_val = st.sidebar.slider("Período (arraste)", min_value=min_d, max_value=max_d,
                                       value=(min_d, max_d), format="YYYY-MM-DD", step=timedelta(days=1), key="sb_date_slider")
        date_from = pd.to_datetime(slider_val[0])
        date_to = pd.to_datetime(slider_val[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        filters["mode"] = "range"
        filters["date_from"] = date_from
        filters["date_to"] = date_to
        filters["categories"] = selected_cats
    else:
        months = ["Todos"] + sorted(df["year_month"].unique(), reverse=True) if not df.empty else ["Todos"]
        selected_month = st.sidebar.selectbox("Mês (ano-mês)", months, key="sb_month")
        categories = ["Todos"] + sorted(df["CATEGORIA"].unique()) if not df.empty else ["Todos"]
        selected_category = st.sidebar.selectbox("Categoria", categories, key="sb_cat_single")
        filters["mode"] = "month"
        filters["month"] = selected_month
        filters["categories"] = [selected_category] if selected_category != "Todos" else []

    st.sidebar.markdown("---")
    if st.sidebar.button("Limpar cache (não recarrega automaticamente)", key="sb_clear_cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
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
        if month and month != "Todos":
            df_filtered = f[f["year_month"] == month]
        else:
            df_filtered = f
    cats = filters.get("categories", [])
    if cats:
        df_filtered = df_filtered[df_filtered["CATEGORIA"].isin(cats)]
    return df_filtered.reset_index(drop=True)

# ---------- TABELAS & KPI ----------
def render_kpis_without_bg(df: pd.DataFrame):
    receita = df.loc[df["VALOR_NUM"] > 0, "VALOR_NUM"].sum()
    despesa = df.loc[df["VALOR_NUM"] < 0, "VALOR_NUM"].sum()
    saldo = receita + despesa
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"<div style='font-size:12px;color:{COLORS['neutral']};text-transform:uppercase'>Receita</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-weight:700;color:{COLORS['receita']};font-size:20px'>{money_fmt_br(receita)}</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div style='font-size:12px;color:{COLORS['neutral']};text-transform:uppercase'>Despesa</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-weight:700;color:{COLORS['despesa']};font-size:20px'>{money_fmt_br(abs(despesa))}</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div style='font-size:12px;color:{COLORS['neutral']};text-transform:uppercase'>Saldo</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-weight:700;color:{COLORS['saldo']};font-size:20px'>{money_fmt_br(saldo)}</div>", unsafe_allow_html=True)

def render_table(df: pd.DataFrame, key: str):
    if df.empty:
        st.info("Sem lançamentos para mostrar.")
        return
    df_display = df.copy()
    df_display["Data"] = df_display["DATA"].dt.date
    df_display["Valor (R$)"] = df_display["VALOR_NUM"].apply(lambda x: money_fmt_br(x))
    df_display = df_display.rename(columns={"TIPO":"Tipo","CATEGORIA":"Categoria","DESCRIÇÃO":"Descrição","OBSERVAÇÃO":"Observação"})
    column_config = {
        "Data": st.column_config.DatetimeColumn("Data", format="YYYY-MM-DD"),
        "Valor (R$)": st.column_config.TextColumn("Valor (R$)"),
    }
    st.dataframe(df_display[["Data","Tipo","Categoria","Descrição","Valor (R$)","Observação"]], column_config=column_config, use_container_width=True, key=key)

# ---------- MAIN ----------
def main():
    st.set_page_config(page_title="Dashboard Financeiro Caec", layout="wide", initial_sidebar_state="expanded",
                       menu_items={"About": "Dashboard Financeiro Caec"})
    st.markdown(FONT_CSS, unsafe_allow_html=True)

    st.title("Dashboard Financeiro Caec")

    df = load_and_preprocess_data()
    if df.empty:
        st.sidebar.markdown("---")
        st.sidebar.caption("CAEC © 2025")
        st.warning("Planilha vazia ou erro ao importar dados. Verifique planilha/credenciais.")
        return

    page, filters = sidebar_filters_and_controls_with_toggle(df)
    df_filtered = apply_filters(df, filters)

    render_kpis_without_bg(df_filtered)
    st.markdown("---")

    if page == "Resumo Financeiro":
        st.subheader("Evolução do Saldo Acumulado")
        fig_saldo = plot_saldo_acumulado(df_filtered)
        st.plotly_chart(fig_saldo, use_container_width=True, key="chart_saldo_line_resumo")

        st.subheader("Fluxo de Caixa Diário")
        fig_fluxo = plot_fluxo_diario(df_filtered)
        st.plotly_chart(fig_fluxo, use_container_width=True, key="chart_fluxo_bar_resumo")

        st.subheader("Lançamentos Recentes")
        recent = df_filtered.sort_values("DATA", ascending=False).head(10)
        render_table(recent, key="table_recent_resumo")

        export_df = df_filtered[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]]
        csv = export_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_resumo_export.csv", mime="text/csv", key="download_resumo")

    else:
        tab_normais, tab_avancados = st.tabs(["Normais", "Avançados"])

        with tab_normais:
            st.subheader("Receita — por Categoria")
            col1, col2 = st.columns(2)
            with col1:
                fig_rec = plot_categoria_barras(df_filtered, kind="Receita")
                st.plotly_chart(fig_rec, use_container_width=True, key="chart_rec_bar_normais")
            with col2:
                fig_dep = plot_categoria_barras(df_filtered, kind="Despesa")
                st.plotly_chart(fig_dep, use_container_width=True, key="chart_dep_bar_normais")

            st.markdown("---")
            st.subheader("Composição Percentual")
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Receita"), use_container_width=True, key="chart_pie_rec_normais")
            with col2:
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Despesa"), use_container_width=True, key="chart_pie_dep_normais")

            st.markdown("---")
            st.subheader("Visão Temporal de Lançamentos (Bolhas)")
            st.plotly_chart(plot_bubble_transacoes(df_filtered), use_container_width=True, key="chart_bubble_normais")

        with tab_avancados:
            agg_freq = st.selectbox("Agregação Candlestick", options=[("Diário","D"), ("Semanal","W"), ("Mensal","M")], format_func=lambda x: x[0], key="sb_candle_freq")
            freq_code = agg_freq[1]
            st.subheader("Candlestick (Avançado)")
            st.plotly_chart(plot_candlestick(df_filtered, freq=freq_code), use_container_width=True, key=f"chart_candlestick_{freq_code}")

            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Média Móvel (SMA) & Fluxo Diário")
                fluxo = df_filtered.groupby(df_filtered["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
                fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
                fluxo["sma14"] = fluxo["VALOR_NUM"].rolling(window=14, min_periods=1).mean()
                fig_ma = go.Figure()
                fig_ma.add_trace(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], name="Fluxo Diário", marker_color="#888888"))
                fig_ma.add_trace(go.Scatter(x=fluxo["DATA"], y=fluxo["sma14"], mode="lines", name="SMA14", line=dict(color="#ff9900")))
                fig_ma.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ma, use_container_width=True, key="chart_sma14_avancado")
            with col2:
                st.subheader("Boxplot por Categoria")
                st.plotly_chart(plot_boxplot_by_category(df_filtered), use_container_width=True, key="chart_box_avancado")

            st.markdown("---")
            st.subheader("Heatmap Mensal (Avançado)")
            st.plotly_chart(plot_monthly_heatmap(df_filtered), use_container_width=True, key="chart_heatmap_avancado")

        st.markdown("---")
        render_table(df_filtered, key="table_full_detalhado")
        export_df = df_filtered[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]]
        csv = export_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Exportar CSV (Filtro Atual)", csv, file_name="caec_full_export.csv", mime="text/csv", key="download_full")

    st.markdown("---")
    st.markdown("<div style='font-size:12px;color:gray;text-align:center'>CAEC © 2025 — Criador e administrado pela administração comercial e financeiro — by Rick</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
